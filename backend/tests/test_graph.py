import asyncio
import copy
import threading
import pytest
from app.workflow.graph import ReportServices,build_report_graph,WorkflowCancelled
from app.workflow.role_policy import _normalize_plan
from app.report_errors import ReportGenerationError

def valid_report():
    return {'title':'Fixture','regions':[{'regionName':['Kitchen'],'potentialHazards':['Fire'],
        'colorAndLightingEvaluation':['Bright'],'suggestions':['Clear stove'],'scores':[1,2,3,4,5]}],
        'meta':{},'scores':{'overall':4,'dimensions':{}},'top_risks':[{'risk':'Fire'}],
        'recommendations':{'actions':[{'action':'Clear stove'}]},'comfort':{},'compliance':{'checklist':[]},
        'action_plan':[{'action':'Clear stove'}],'limitations':['Visual inspection only']}

class FakeServices(ReportServices):
    def __init__(self,fail_repairs=0,empty=False,writer_retry=False):
        self.events=[];self.writes=0;self.repairs=0;self.validations=0
        self.fail_repairs=fail_repairs;self.empty=empty;self.writer_retry=writer_retry
    def authorize(self,s): return {}
    async def extract(self,s): return {'frames':[] if self.empty else ['asset']}
    async def filter(self,s): return {'frames':s['frames'],'filter_stats':{}}
    async def select(self,s): return {'representative_images':s['frames']}
    async def detect(self,s): return {'yolo_summaries':{}}
    def scene(self,s): return {'region_evidence':[{'region_label':'Kitchen','image_paths':['asset']}]}
    def router(self,s): return {'plan':_normalize_plan(['ComfortAgent','ComplianceAgent','RecommendationAgent'])}
    async def hazard(self,s):
        await asyncio.sleep(.001);self.events.append('hazard');return {'hazards':[]}
    async def comfort(self,s):
        await asyncio.sleep(.002);self.events.append('comfort');return {'comfort':{}}
    async def compliance(self,s):
        assert 'hazards' in s and 'comfort' in s
        self.events.append('compliance');return {'compliance':{}}
    async def scoring(self,s):
        assert 'hazards' in s and 'comfort' in s
        self.events.append('scoring');return {'scoring':{}}
    async def recommendations(self,s):
        assert 'scoring' in s and 'compliance' in s
        self.events.append('recommendations');return {'recommendations':{}}
    def write(self,s):
        assert 'recommendations' in s
        self.writes+=1
        if self.writer_retry and self.writes==1: return {'draft_report':{}}
        report=valid_report()
        if self.fail_repairs: report['regions'][0]['scores']=[9]*5
        return {'draft_report':report}
    async def validate(self,s):
        self.validations+=1
        return await super().validate(s)
    def repair(self,s):
        self.repairs+=1;report=valid_report()
        if self.repairs<=self.fail_repairs: report['regions'][0]['scores']=[9]*5
        return {'draft_report':report}
    def title(self,s): return {'title':'Fixture'}
    def persist(self,s): self.events.append('persist');return {'report_id':123}

def run(services,cancel=None):
    return asyncio.run(build_report_graph(services,cancel=cancel).ainvoke(
        {'user_id':1,'chat_id':1,'video_asset_id':'fixture','user_attributes':{},'iterations':0},
        config={'recursion_limit':64}))

def test_graph_barriers_and_evidence():
    services=FakeServices();state=run(services)
    assert set(services.events[:2])=={'hazard','comfort'}
    assert set(services.events[2:4])=={'compliance','scoring'}
    assert services.events[-2:]==['recommendations','persist']
    assert state['draft_report']['regions'][0]['evidenceImages']==['asset']
    assert state['validation']['valid'] and services.validations==1 and services.repairs==0

def test_three_repairs_without_extra_final_validation():
    services=FakeServices(fail_repairs=10);state=run(services)
    assert services.repairs==services.validations==state['iterations']==3
    assert state['validation']['valid'] is False
    assert state['report_id']==123  # Original report persistence policy retained.

def test_repair_success_and_writer_retry():
    services=FakeServices(fail_repairs=1);state=run(services)
    assert state['validation']['valid'] and services.repairs==2
    retry=FakeServices(writer_retry=True);run(retry)
    assert retry.writes==2

def test_empty_frames_exit_before_agents():
    services=FakeServices(empty=True);state=run(services)
    assert state['warning'] and not services.events and 'report_id' not in state

def test_error_draft_after_repairs_is_never_persisted():
    class ErrorWriter(FakeServices):
        def write(self, state): return {'draft_report':{'error':'bad JSON'}}
        def repair(self, state):
            self.repairs += 1
            return {'draft_report':{'error':'bad JSON'}}
    services = ErrorWriter()
    with pytest.raises(ReportGenerationError): run(services)
    assert services.repairs == 3
    assert 'persist' not in services.events

def test_cancel_before_work():
    cancel=threading.Event();cancel.set()
    with pytest.raises(WorkflowCancelled): run(FakeServices(),cancel)

def test_optional_specialists_dont_call_llm():
    services=ReportServices()
    async def forbidden(*a): raise AssertionError('Optional model must not run')
    services._json=forbidden
    async def check():
        for method in (services.comfort,services.compliance,services.scoring,services.recommendations):
            assert list((await method({'plan':[]})).values())==[{}]
    asyncio.run(check())
    assert _normalize_plan(['RecommendationAgent'])==['HazardAgent','ScoringAgent','RecommendationAgent','ReportWriterAgent']
