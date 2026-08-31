import asyncio
import copy
import json
from types import SimpleNamespace as NS
import pytest
from app.llm import complete,ToolBudgetExceeded
from app.tools.registry import TOOLS,ToolContext,execute_tool
from app.settings import get_settings,Settings

def message(content='',calls=()):
    return NS(choices=[NS(message=NS(content=content,tool_calls=[
        NS(id=cid,function=NS(name=name,arguments=args)) for cid,name,args in calls]))])

class FakeClient:
    def __init__(self,responses):
        self.responses=iter(responses);self.requests=[]
        self.chat=NS(completions=NS(create=self.create))
    async def create(self,**kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        return next(self.responses)

def test_real_protocol_round_trip():
    client=FakeClient([message(calls=[('call-1','validate_report','{"report":{"regions":[]}}')]),message('corrected response')])
    result=asyncio.run(complete([{'role':'user','content':'validate'}],allowed_tools=['validate_report'],client=client))
    assert result=='corrected response'
    first,second=client.requests
    assert first['tools'][0]['function']['name']=='validate_report'
    tool=second['messages'][-1]
    assert tool['role']=='tool' and tool['tool_call_id']=='call-1'
    assert json.loads(tool['content'])['result']['valid'] is False

@pytest.mark.parametrize('name,args,allowed,code',[
    ('delete_everything','{}',['validate_report'],'tool_not_allowed'),
    ('validate_report','not-json',['validate_report'],'invalid_arguments'),
    ('read_report','{"report_id":"x","user_id":999}',['read_report'],'invalid_arguments'),
    ('read_report','{"report_id":"x"}',['read_report'],'resource_not_available'),
])
def test_tool_rejection(name,args,allowed,code):
    out=asyncio.run(execute_tool(name,args,ToolContext(),allowed))
    assert out=={'ok':False,'error':{'code':code}}

def test_hidden_runtime_and_bounded_schema():
    for tool in TOOLS.values():
        assert 'user_id' not in tool.schema()['function']['parameters']['properties']
        assert tool.schema()['function']['parameters']['additionalProperties'] is False
    out=asyncio.run(execute_tool('search_guide',{'query':'upload video','top_k':2},ToolContext(),['search_guide']))
    assert out['ok'] and isinstance(out['result'],list)

def test_multiple_tool_calls_all_correlated():
    client=FakeClient([message(calls=[('a','validate_report','{"report":{}}'),('b','search_guide','{"query":"report"}')]),message('done')])
    asyncio.run(complete([],allowed_tools=['validate_report','search_guide'],client=client))
    assert [x['tool_call_id'] for x in client.requests[-1]['messages'] if x['role']=='tool']==['a','b']

def test_budget(monkeypatch):
    import app.llm as llm
    monkeypatch.setattr(llm,'get_settings',lambda:Settings(TOOL_MAX_ROUNDS=1))
    response=message(calls=[('a','validate_report','{"report":{}}')])
    with pytest.raises(ToolBudgetExceeded):
        asyncio.run(complete([],allowed_tools=['validate_report'],client=FakeClient([response,response])))

def test_unknown_model_tool_is_returned_as_error():
    client=FakeClient([message(calls=[('a','unknown','{}')]),message('handled')])
    assert asyncio.run(complete([],allowed_tools=['validate_report'],client=client))=='handled'
    assert json.loads(client.requests[-1]['messages'][-1]['content'])['error']['code']=='tool_not_allowed'
