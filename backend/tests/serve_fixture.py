"""Local UI verification only. Serves built SPA with deterministic model responses.

Never used by Compose or the normal app. Requires an isolated TEST_DATABASE_URL.
Run with PYTHONPATH=backend:backend/tests python backend/tests/serve_fixture.py.
"""
import os
from pathlib import Path
from uuid import uuid4
import json
from types import SimpleNamespace as NS

if not os.environ.get('TEST_DATABASE_URL'):
    raise RuntimeError('Only run this fixture against an isolated TEST_DATABASE_URL')
os.environ['DATABASE_URL']=os.environ['TEST_DATABASE_URL']

from app import db,storage
from app.workflow.graph import ReportServices
from app.agents.scene_agent import SceneUnderstandingAgent
from app.agents.router_agent import RouterAgent
from app.agents.report_writer_agent import ReportWriterAgent
from app.agents.title_agent import TitleAgent
from app.agents.report_pdf_agent import ReportPdfRepairAgent
from test_graph import valid_report
from test_end_to_end import textured_video
from app.workflow.orchestrator import WorkflowOrchestrator

class Model:
    names={}
    def __call__(self,*a,**k): return [NS(boxes=[])]
ReportServices._model=lambda self:Model()
SceneUnderstandingAgent._call_llm=lambda *a,**k:json.dumps({'room_type':'Kitchen','description':'Fixture kitchen with stove','key_objects':['stove']})
RouterAgent._call_llm=lambda *a,**k:json.dumps({'agents':['HazardAgent','ReportWriterAgent']})
ReportWriterAgent._call_llm=lambda *a,**k:json.dumps(valid_report())
TitleAgent._call_llm=lambda *a,**k:'Fixture Kitchen'
ReportPdfRepairAgent._call_llm=lambda *a,**k:json.dumps(valid_report())
async def role(self,system,prompt): return [] if 'Output a JSON array' in system else {}
ReportServices._json=role

from app.workflow import chat_graph
chat_graph._classify_query=lambda *a:('SAFETY',True,'fixture')
chat_graph._answer_from_guide=lambda *a:None
chat_graph._handle_llm_query=lambda *a:'Fixture answer: keep the stove clear.'

storage.initialize_buckets()
email='browser-'+uuid4().hex[:8]+'@test.invalid'
u=db.create_user(email,'Browser Fixture','fixture-password')
c=db.create_chat('New Chat',u['user_id'])
ref=storage.put(textured_video(),'video/mp4',user_id=u['user_id'],category='media')
WorkflowOrchestrator().execute_workflow(ref,{},user_id=u['user_id'],chat_id=c)
print('FIXTURE_LOGIN',email,'fixture-password',flush=True)

from main import app
from fastapi.responses import StreamingResponse
import asyncio

@app.get('/api/gateway-stream-probe')
def gateway_stream_probe():
    async def chunks():
        yield b'first\n'
        await asyncio.sleep(1.5)
        yield b'last\n'
    return StreamingResponse(chunks(), media_type='application/x-ndjson')
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
dist=Path(__file__).resolve().parents[2]/'frontend'/'dist'
app.mount('/assets',StaticFiles(directory=dist/'assets'),name='test-build-assets')
@app.get('/{route:path}')
def spa(route:str):
    if route=='smart-home.png': return FileResponse(dist/'smart-home.png')
    return FileResponse(dist/'index.html')

if __name__=='__main__':
    import uvicorn
    # Docker Nginx reaches this disposable fixture via host.docker.internal.
    uvicorn.run(app,host='0.0.0.0',port=18007)
