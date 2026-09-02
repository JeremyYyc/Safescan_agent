import asyncio
import copy
from dataclasses import replace
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

def test_model_logs_size_and_usage_without_prompt_content(caplog):
    private='private-prompt-must-not-be-logged'
    client=FakeClient([message('done')])
    with caplog.at_level('INFO',logger='app.llm'):
        assert asyncio.run(complete([{'role':'user','content':private}],client=client))=='done'
    assert 'LLM request start' in caplog.text
    assert f'text_chars={len(private)}' in caplog.text
    assert 'LLM request complete' in caplog.text
    assert private not in caplog.text

def test_tool_failure_logs_location_without_private_values(monkeypatch, caplog):
    private_value = 'private-token-do-not-log'
    def fail(args, ctx):
        raise AttributeError(private_value)
    monkeypatch.setitem(TOOLS, 'validate_report', replace(TOOLS['validate_report'], function=fail))
    result = asyncio.run(execute_tool('validate_report', {'report': {'secret': private_value}},
                                      ToolContext(), ['validate_report']))
    assert result == {'ok': False, 'error': {'code': 'tool_failed'}}
    assert 'Tool validate_report failed (AttributeError)' in caplog.text
    assert 'in fail' in caplog.text
    assert private_value not in caplog.text
