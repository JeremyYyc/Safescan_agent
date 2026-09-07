"""Meaningful offline contract checks; these are not a substitute for PostgreSQL execution."""
import json
import pytest
from sqlalchemy import ForeignKeyConstraint
from intent_agent import StaffIntentAgent, Identity, mock_planner, validate_and_route
from schema import metadata, SERVICE_TABLES

@pytest.mark.parametrize('query,route',[
 ('查询 HV-102 的维修状态','execute'),
 ('查询 HV-102 的维修状态；查询 HV-102 的租金账单','execute'),
 ('查询 HV-102 的维修状态；创建 HV-102 的漏水维修草稿','human'),
 ('如何关闭维修工单','execute'),
 ('创建 HV-102 的漏水维修草稿','execute'),
 ('如果维修已完成，查询该房的检查报告','clarify'),
 ('你好','clarify'),
])
def test_routing(query,route):
    result=StaffIntentAgent().recognize(query,Identity(1,1))
    assert result['route']==route
    assert not result['business_executed'] and not result['human_submitted']
    if route=='human': assert result['tasks']==[]

def test_identity_is_checked_before_model():
    def fail(_): raise AssertionError('Must never call planner')
    assert StaffIntentAgent(fail).recognize('查询房源',Identity(1,1,False))['route']=='deny'

def test_model_error_fails_closed():
    def fail(_): raise RuntimeError('model unavailable')
    assert StaffIntentAgent(fail).recognize('查询房源',Identity(1,1))['reason']=='PLANNER_FAILED'

def test_invented_source_rejected():
    plan=mock_planner('查询 HV-999 的维修状态')
    assert validate_and_route('查询 HV-102 的维修状态',plan)['route']=='clarify'

def test_omitted_task_rejected():
    query='查询房源；查询租金'
    plan=mock_planner(query);plan['tasks'].pop()
    assert validate_and_route(query,plan)['reason']=='INCOMPLETE_COVERAGE'

def test_model_cannot_supply_permission_fields():
    query='查询房源';plan=mock_planner(query)
    plan['tasks'][0]['permissions']=['*']
    assert validate_and_route(query,plan)['reason']=='INVALID_MODEL_OUTPUT'

def test_overlap_rejected():
    plan=mock_planner('查询房源'); second=dict(plan['tasks'][0],id='t2');plan['tasks'].append(second)
    assert validate_and_route('查询房源',plan)['route']=='clarify'

def test_dependency_is_not_automatically_executed():
    query='查询房源；查询租金';plan=mock_planner(query);plan['tasks'][1]['depends_on']=['t1']
    assert validate_and_route(query,plan)['reason']=='DEPENDENCY_REQUIRES_INPUT'

def test_cross_service_foreign_keys_absent():
    for t in metadata.tables.values():
        for fk in t.foreign_key_constraints:
            assert all(e.column.table.schema==t.schema for e in fk.elements)

def test_local_business_links_include_organization():
    for t in metadata.tables.values():
        for fk in t.foreign_key_constraints:
            assert 'organization_id' in fk.column_keys

def test_all_tables_owned_once():
    declared=[n for names in SERVICE_TABLES.values() for n in names.split()]
    assert len(declared)==len(set(declared))==len(metadata.tables)

def test_mock_result_cannot_claim_business_write():
    t=metadata.tables['staff_agent.task_results']
    assert any("source != 'mock'" in str(getattr(c,'sqltext','')) for c in t.constraints)


def test_prompt_contract_export():
    from intent_agent import Plan
    schema=Plan.model_json_schema()
    assert schema['additionalProperties'] is False
    assert schema['$defs']['Task']['additionalProperties'] is False
