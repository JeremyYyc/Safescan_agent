"""Upload exactly the objects referenced by dataset.sql. Dry-run by default."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def validated_objects(root):
    root=root.resolve()
    rows=json.loads((root/'objects.json').read_text(encoding='utf-8'))
    seen=set()
    for row in rows:
        path=(root/row['local_path']).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Missing or unsafe object path: '+row['local_path'])
        if path.stat().st_size!=row['byte_size'] or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('Object checksum mismatch: '+row['local_path'])
        key=(row['bucket'],row['object_key'])
        if key in seen:
            raise ValueError('Duplicate object key')
        seen.add(key)
    return rows


def upload(root, client, error_type, create_bucket=False):
    rows=validated_objects(root)
    for bucket in sorted({r['bucket'] for r in rows}):
        if not client.bucket_exists(bucket):
            if not create_bucket:
                raise RuntimeError('Missing bucket; provision it or pass --create-bucket: '+bucket)
            client.make_bucket(bucket)
    uploaded=skipped=0
    for r in rows:
        try:
            current=client.stat_object(r['bucket'],r['object_key'])
        except error_type as exc:
            if exc.code not in {'NoSuchKey','NoSuchObject'}:
                raise
        else:
            # Read the existing object: don't treat user-editable metadata as a checksum.
            response=client.get_object(r['bucket'],r['object_key'])
            try:
                sha=hashlib.sha256()
                for chunk in response.stream(1024*1024):
                    sha.update(chunk)
            finally:
                response.close()
                response.release_conn()
            if current.size!=r['byte_size'] or sha.hexdigest()!=r['sha256']:
                raise RuntimeError('Existing object differs; refusing overwrite: '+r['object_key'])
            skipped+=1
            continue
        client.fput_object(r['bucket'],r['object_key'],str(root/r['local_path']),
                           content_type=r['content_type'],metadata={'sha256':r['sha256']})
        uploaded+=1
        print(f'Uploaded {uploaded}: {r["object_key"]}',flush=True)
    print(f'Completed: uploaded={uploaded}, existing_verified={skipped}')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--upload',action='store_true')
    parser.add_argument('--create-bucket',action='store_true')
    args=parser.parse_args()
    rows=validated_objects(args.root)
    if not args.upload:
        print(f'DRY RUN: verified {len(rows)} local objects; no network requests.')
        return
    from minio import Minio
    from minio.error import S3Error
    endpoint=os.environ['MINIO_ENDPOINT']
    if '://' in endpoint or '/' in endpoint:
        raise ValueError('MINIO_ENDPOINT must be host:port without URL scheme or path')
    secure=os.environ.get('MINIO_SECURE','true').lower()
    if secure not in {'true','false'}:
        raise ValueError('MINIO_SECURE must be true or false')
    client=Minio(endpoint,access_key=os.environ['MINIO_ACCESS_KEY'],
                 secret_key=os.environ['MINIO_SECRET_KEY'],secure=secure=='true')
    upload(args.root,client,S3Error,args.create_bucket)


if __name__=='__main__':
    main()
