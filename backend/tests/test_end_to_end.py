"""Real HTTP/graph/PG/MinIO; only external inference is deterministic."""
import json
from io import BytesIO
from types import SimpleNamespace as NS
from uuid import uuid4
import av
import numpy as np
import pytest
from fastapi.testclient import TestClient
from test_postgres import database,user
from test_graph import valid_report
from app import db,storage
from app.auth import create_token
from app.workflow.graph import ReportServices

def textured_video():
    target=BytesIO();rng=np.random.default_rng(41)
    with av.open(target,'w',format='mp4') as out:
        stream=out.add_stream('mpeg4',rate=2);stream.width=128;stream.height=128;stream.pix_fmt='yuv420p'
        for _ in range(6):
            frame=av.VideoFrame.from_ndarray(rng.integers(60,250,(128,128,3),dtype=np.uint8),format='rgb24')
            for packet in stream.encode(frame): out.mux(packet)
        for packet in stream.encode(): out.mux(packet)
    return target.getvalue()

@pytest.fixture
def inference(monkeypatch):
    from app.agents.scene_agent import SceneUnderstandingAgent
    from app.agents.router_agent import RouterAgent
    from app.agents.report_writer_agent import ReportWriterAgent
    from app.agents.title_agent import TitleAgent
    from app.agents.report_pdf_agent import ReportPdfRepairAgent
    class Model:
        names={}
        def __call__(self,*a,**k): return [NS(boxes=[])]
    monkeypatch.setattr(ReportServices,'_model',lambda self:Model())
    monkeypatch.setattr(SceneUnderstandingAgent,'_call_llm',lambda *a,**k:json.dumps({'room_type':'Kitchen','description':'A bright kitchen with a stove','key_objects':['stove']}))
    monkeypatch.setattr(RouterAgent,'_call_llm',lambda *a,**k:json.dumps({'agents':['HazardAgent','ComfortAgent','ComplianceAgent','ScoringAgent','RecommendationAgent','ReportWriterAgent']}))
    monkeypatch.setattr(ReportWriterAgent,'_call_llm',lambda *a,**k:json.dumps(valid_report()))
    monkeypatch.setattr(TitleAgent,'_call_llm',lambda *a,**k:'Fixture Kitchen')
    monkeypatch.setattr(ReportPdfRepairAgent,'_call_llm',lambda *a,**k:json.dumps(valid_report()))
    async def role(self,system,prompt):
        return [] if 'Output a JSON array with one entry per region' in system else {}
    monkeypatch.setattr(ReportServices,'_json',role)

def test_upload_to_report_to_pdf_and_reload(inference):
    from main import app
    client=TestClient(app);u=user();headers={'Authorization':'Bearer '+create_token(u)}
    c=db.create_chat('New Chat',u['user_id']);cid=db.get_chat(c)['id']
    upload=client.post('/api/uploadVideo',headers={**headers,'Content-Type':'video/mp4'},content=textured_video())
    assert upload.status_code==200,upload.text
    ref=upload.json()['video_asset_id']
    invalid=client.post('/api/processVideoStream',headers=headers,json={'chat_id':cid,'video_asset_id':'/etc/passwd'})
    assert invalid.status_code==404
    response=client.post('/api/processVideoStream',headers=headers,json={'chat_id':cid,'video_asset_id':ref,'attributes':{'isChildren':True}})
    assert response.status_code==200,response.text
    events=[json.loads(line) for line in response.text.splitlines() if line]
    assert events[-1]['type']=='end'
    assert not [e for e in events if e['type']=='error'],events
    result=next(e['result'] for e in events if e['type']=='complete')
    assert result['report_id'] and result['validation']['success']
    assert result['report']['regions'][0]['scores']==[1,2,3,4,5]
    assert result['representativeImages']
    for image in result['representativeImages']:
        assert client.get(image,headers=headers).status_code==200
    assert client.get(f'/api/chats/{cid}/messages',headers=headers).status_code==200
    pdf=client.post(f'/api/reports/{cid}/export-pdf',headers=headers)
    assert pdf.status_code==200,pdf.text
    assert client.get(pdf.json()['download_url'],headers=headers).content.startswith(b'%PDF-')
    latest=client.get(f'/api/reports/{cid}/pdf-latest',headers=headers).json()['pdf']
    assert client.get(latest['download_url'],headers=headers).status_code==200
    # Recreate API object; no process-local business cache is required.
    from main import create_app
    assert TestClient(create_app()).get(result['representativeImages'][0],headers=headers).status_code==200

def test_chat_graph_keeps_guide_and_report_policy(monkeypatch):
    from main import app
    from app.workflow import chat_graph as graph,chat_policy as policy
    client=TestClient(app);u=user();c=db.create_chat('Chat',u['user_id'],'bot');cid=db.get_chat(c)['id']
    headers={'Authorization':'Bearer '+create_token(u)}
    monkeypatch.setattr(graph,'_classify_query',lambda *a:('REPORT_EXPLANATION',True,'fixture'))
    response=client.post('/api/processChat',headers=headers,json={'chat_id':cid,'message':'Explain my reports'})
    assert response.status_code==200,response.text
    assert 'attach at least one report' in response.json()['reply']
    assert len(db.get_chat_messages(c))==2
    monkeypatch.setattr(graph,'_classify_query',lambda *a:('OTHER',False,'fixture'))
    monkeypatch.setattr(graph,'_answer_from_guide',lambda *a:'Guide fixture')
    monkeypatch.setattr(graph,'_handle_guide_query',lambda *a:'Guide answer')
    response=client.post('/api/processChat',headers=headers,json={'chat_id':cid,'message':'How to upload?'})
    assert response.json()['reply']=='Guide answer'

def test_persistence_failure_is_not_complete(inference,monkeypatch):
    from main import app
    client=TestClient(app);u=user();c=db.create_chat('Failure',u['user_id'])
    ref=storage.put(textured_video(),'video/mp4',user_id=u['user_id'],category='media')
    def fail(*args): raise RuntimeError('injected persistence failure')
    monkeypatch.setattr(ReportServices,'persist',fail)
    response=client.post('/api/processVideoStream',headers={'Authorization':'Bearer '+create_token(u)},json={'chat_id':db.get_chat(c)['id'],'video_asset_id':ref})
    events=[json.loads(line) for line in response.text.splitlines() if line]
    assert any(e['type']=='error' for e in events)
    assert not any(e['type']=='complete' for e in events)
    assert db.get_latest_report_id(c) is None
