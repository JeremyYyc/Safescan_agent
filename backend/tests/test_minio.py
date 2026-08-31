from io import BytesIO
from pathlib import Path
import tempfile
import numpy as np
import av
import pytest
from fastapi.testclient import TestClient
from test_postgres import database, user
from app import storage,db
from app.auth import create_token
from app.tools.video_tools import extract_frames,_read_image
from app.pdf.report_pdf import render_report_pdf

def video_bytes():
    target=BytesIO()
    with av.open(target,'w',format='mp4') as out:
        stream=out.add_stream('mpeg4',rate=2);stream.width=64;stream.height=64;stream.pix_fmt='yuv420p'
        for i in range(6):
            frame=av.VideoFrame.from_ndarray(np.full((64,64,3),40+i*30,dtype=np.uint8),format='rgb24')
            for packet in stream.encode(frame): out.mux(packet)
        for packet in stream.encode(): out.mux(packet)
    return target.getvalue()

def test_private_assets_and_memory_decode(monkeypatch):
    u=user();other=user();payload=video_bytes()
    ref=storage.put(payload,'video/mp4',user_id=u['user_id'],category='media')
    with pytest.raises(FileNotFoundError): storage.read(ref,other['user_id'])
    def deny(*args,**kwargs): raise AssertionError('Business file disk I/O forbidden')
    monkeypatch.setattr(Path,'open',deny);monkeypatch.setattr(tempfile,'SpooledTemporaryFile',deny)
    with storage.media_scope(u['user_id']):
        frames=extract_frames(ref)
        assert len(frames)==3
        assert [round(float(_read_image(f).mean())/10)*10 for f in frames]==[40,100,160]
        target=BytesIO();render_report_pdf({'title':'Fixture','regions':[], 'compliance':{'checklist':[]},'action_plan':{}},target)
        assert target.getvalue().startswith(b'%PDF-')
    for f in frames:
        with pytest.raises(FileNotFoundError): storage.record(f,u['user_id'])

def test_upload_and_download_no_multipart(monkeypatch):
    from main import app
    u=user();headers={'Authorization':'Bearer '+create_token(u),'Content-Type':'application/pdf'}
    def deny(*a,**k): raise AssertionError('Multipart spooling forbidden')
    monkeypatch.setattr(tempfile,'SpooledTemporaryFile',deny)
    client=TestClient(app)
    response=client.post('/api/reports/upload-pdf',headers=headers,content=b'%PDF-1.4\nfixture')
    assert response.status_code==200,response.text
    report=db.get_report_by_public_id(response.json()['report']['report_id'])
    ref=report['source_path']
    assert client.get(ref,headers=headers).content==b'%PDF-1.4\nfixture'
    assert client.get(ref).status_code==401
    other={'Authorization':'Bearer '+create_token(user())}
    assert client.get(ref,headers=other).status_code==404
    assert client.get('/uploads/anything').status_code==404

def test_object_compensation_on_metadata_failure(monkeypatch):
    u=user();removed=[]
    original=storage.client().remove_object
    def track(bucket,key): removed.append(key);return original(bucket,key)
    monkeypatch.setattr(storage.client(),'remove_object',track)
    def fail(): raise RuntimeError('database unavailable')
    monkeypatch.setattr(storage,'get_connection',fail)
    with pytest.raises(RuntimeError): storage.put(b'x','image/jpeg',user_id=u['user_id'])
    assert len(removed)==1

def test_invalid_asset_is_not_path_or_url():
    for value in ('/etc/passwd','https://example.com/video','../../uploads/a'):
        with pytest.raises(ValueError): storage.asset_uuid(value)
