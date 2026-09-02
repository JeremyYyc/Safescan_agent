"""Private business objects. Never accepts filesystem paths or arbitrary URLs."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from io import BytesIO
import hashlib
import os
from pathlib import Path
import tempfile
from uuid import UUID
from minio import Minio
import urllib3
from app.settings import get_settings
from app.persistence.database import get_connection
from app.utils.uuid7 import uuid7_hex

_owner=ContextVar('asset_owner',default=None)
_created=ContextVar('created_assets',default=None)

def asset_uuid(ref):
    text=str(ref)
    if text.startswith('/api/assets/'): text=text[len('/api/assets/'):]
    try: return UUID(text).hex
    except ValueError: raise ValueError('Expected an asset ID, not a path or URL')

def asset_ref(value): return '/api/assets/'+asset_uuid(value)

@lru_cache(maxsize=1)
def client():
    s=get_settings()
    http_client=urllib3.PoolManager(
        num_pools=1,
        maxsize=s.MINIO_POOL_MAXSIZE,
        block=True,
        timeout=urllib3.Timeout(connect=3,read=30),
        retries=2,
    )
    return Minio(s.MINIO_ENDPOINT,access_key=s.require_secret('MINIO_ACCESS_KEY'),
                 secret_key=s.require_secret('MINIO_SECRET_KEY'),secure=s.MINIO_SECURE,region=s.MINIO_REGION,
                 http_client=http_client)

def initialize_buckets():
    s=get_settings()
    for bucket in (s.MINIO_MEDIA_BUCKET,s.MINIO_DERIVED_BUCKET,s.MINIO_REPORTS_BUCKET):
        if not client().bucket_exists(bucket): client().make_bucket(bucket)

def record(ref,user_id=None):
    owner=user_id if user_id is not None else _owner.get()
    if owner is None: raise PermissionError('Missing trusted asset owner')
    with get_connection() as conn, conn.cursor(True) as cur:
        cur.execute('SELECT * FROM files WHERE file_uuid=%s AND user_id=%s',(asset_uuid(ref),owner))
        row=cur.fetchone()
    if not row: raise FileNotFoundError('Asset not found')
    return row

def put(data: bytes, mime: str, *, user_id=None, category='derived', name=''):
    owner=user_id if user_id is not None else _owner.get()
    if owner is None: raise PermissionError('Missing trusted asset owner')
    s=get_settings();uid=uuid7_hex()
    bucket={'media':s.MINIO_MEDIA_BUCKET,'derived':s.MINIO_DERIVED_BUCKET,'reports':s.MINIO_REPORTS_BUCKET}[category]
    key=f'{owner}/{uid}'
    client().put_object(bucket,key,BytesIO(data),len(data),content_type=mime)
    try:
        with get_connection() as conn,conn.cursor() as cur:
            cur.execute('INSERT INTO files (file_uuid,user_id,bucket,object_key,mime_type,file_size,sha256,original_name) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',
                        (uid,owner,bucket,key,mime,len(data),hashlib.sha256(data).hexdigest(),name[:255]))
    except BaseException:
        client().remove_object(bucket,key)
        raise
    ref=asset_ref(uid)
    if _created.get() is not None: _created.get().append(ref)
    return ref

def put_file(path, mime: str, *, user_id=None, category='media', name=''):
    """Persist a local file without loading the complete object into memory."""
    owner=user_id if user_id is not None else _owner.get()
    if owner is None: raise PermissionError('Missing trusted asset owner')
    source=Path(path);size=source.stat().st_size
    digest=hashlib.sha256()
    with source.open('rb') as handle:
        for chunk in iter(lambda: handle.read(get_settings().VIDEO_IO_CHUNK_BYTES),b''):
            digest.update(chunk)
    s=get_settings();uid=uuid7_hex()
    bucket={'media':s.MINIO_MEDIA_BUCKET,'derived':s.MINIO_DERIVED_BUCKET,'reports':s.MINIO_REPORTS_BUCKET}[category]
    key=f'{owner}/{uid}'
    with source.open('rb') as handle:
        client().put_object(bucket,key,handle,size,content_type=mime)
    try:
        with get_connection() as conn,conn.cursor() as cur:
            cur.execute('INSERT INTO files (file_uuid,user_id,bucket,object_key,mime_type,file_size,sha256,original_name) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',
                        (uid,owner,bucket,key,mime,size,digest.hexdigest(),name[:255]))
    except BaseException:
        client().remove_object(bucket,key)
        raise
    ref=asset_ref(uid)
    if _created.get() is not None: _created.get().append(ref)
    return ref

@contextmanager
def local_copy(ref, user_id=None, *, maximum=None):
    """Materialize a bounded object on disk for seekable media processing."""
    row=record(ref,user_id)
    limit=maximum if maximum is not None else get_settings().MAX_UPLOAD_BYTES
    if row['file_size'] is not None and row['file_size']>limit:
        raise ValueError('Asset exceeds configured file-size limit')
    suffix=Path(row.get('original_name') or '').suffix
    descriptor,path=tempfile.mkstemp(prefix='safescan-media-',suffix=suffix)
    response=None
    total=0
    try:
        response=client().get_object(row['bucket'],row['object_key'])
        with os.fdopen(descriptor,'wb') as output:
            descriptor=None
            while True:
                chunk=response.read(get_settings().VIDEO_IO_CHUNK_BYTES)
                if not chunk: break
                total+=len(chunk)
                if total>limit: raise ValueError('Object exceeds configured file-size limit')
                output.write(chunk)
        yield path
    finally:
        if descriptor is not None: os.close(descriptor)
        if response is not None:
            response.close();response.release_conn()
        Path(path).unlink(missing_ok=True)

def read(ref,user_id=None):
    row=record(ref,user_id)
    if row['file_size'] > get_settings().MAX_VIDEO_MEMORY_BYTES:
        raise ValueError('Asset exceeds in-memory processing limit')
    response=client().get_object(row['bucket'],row['object_key'])
    try:
        data=response.read(get_settings().MAX_VIDEO_MEMORY_BYTES+1)
        if len(data)>get_settings().MAX_VIDEO_MEMORY_BYTES:
            raise ValueError('Object exceeds configured memory limit')
        return data
    finally:
        response.close();response.release_conn()

def replace(ref,data,mime='image/jpeg'):
    row=record(ref)
    client().put_object(row['bucket'],row['object_key'],BytesIO(data),len(data),content_type=mime)
    with get_connection() as conn,conn.cursor() as cur:
        cur.execute('UPDATE files SET file_size=%s,sha256=%s,mime_type=%s WHERE id=%s',
                    (len(data),hashlib.sha256(data).hexdigest(),mime,row['id']))

def remove_unreferenced(ref,user_id=None):
    try: row=record(ref,user_id)
    except FileNotFoundError: return False
    # Lock metadata while checking references. RESTRICT foreign keys prevent races.
    with get_connection() as conn,conn.cursor() as cur:
        cur.execute('SELECT id FROM files WHERE id=%s FOR UPDATE',(row['id'],))
        cur.execute('SELECT (SELECT count(*) FROM report_assets WHERE file_id=%s)+(SELECT count(*) FROM report_analysis WHERE video_file_id=%s)+(SELECT count(*) FROM report_pdf WHERE file_id=%s)',(row['id'],)*3)
        if cur.fetchone()[0]: return False
        client().remove_object(row['bucket'],row['object_key'])
        cur.execute('DELETE FROM files WHERE id=%s',(row['id'],))
    return True

@contextmanager
def owner_scope(user_id):
    """Trusted caller identity, independent of the lifetime of produced objects."""
    token=_owner.set(user_id)
    try: yield
    finally: _owner.reset(token)

@contextmanager
def media_scope(user_id):
    token=_owner.set(user_id);created=[];ct=_created.set(created)
    try: yield
    finally:
        # Unselected/failed derived objects are never left as local temp files.
        # Failed remote cleanup keeps the metadata so it can be retried explicitly.
        for ref in created:
            try: remove_unreferenced(ref,user_id)
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Object cleanup requires retry: %s',ref)
        _created.reset(ct);_owner.reset(token)
