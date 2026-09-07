"""Offline graph execution. LLM/extraction/retrieval are explicit fixtures, NOT online tests."""
from pathlib import Path
import hashlib
import inspect
import json
import re
import unittest
import yaml
from jinja2 import Environment, StrictUndefined
import runtime

ROOT=Path(__file__).resolve().parent
DOC=yaml.safe_load((ROOT/'Safescan 员工侧 Agent - Mixed共用链路.yml').read_text())
N={n['id']:n['data'] for n in DOC['workflow']['graph']['nodes']}
E=DOC['workflow']['graph']['edges']
START='1788353269350'; ROUTER='1788596096943'


def run_code(id,**kwargs):
    ns={};exec(N[id]['code'],ns)
    return ns['main'](**kwargs)


def plan(k='',q='',a='',dependency='none',prop='',status='',ticket=''):
    return dict(knowledge_query=k,record_query=q,action_query=a,dependency=dependency,
                condition_property=prop,condition_id=ticket,condition_status=status,
                task_counts=dict(knowledge=int(bool(k)),record=int(bool(q)),action=int(bool(a))),coverage='complete')


class GraphRun:
    def __init__(self, kind='mixed', p=None, staff='staff_amy', domain='maintenance', prop='HV-102',
                 action='create_draft', action_prop=None, query=None, retrieval=True, extract_success=1):
        self.values={};self.trace=[];self.kind=kind;self.p=p or plan(k='独岗政策？',q='查询 HV-102 维修进度')
        self.staff=staff;self.domain=domain;self.prop=prop;self.action=action;self.action_prop=action_prop or prop
        self.query=query or '；'.join(self.p.get(k,'') for k in ('knowledge_query','record_query','action_query'))
        self.retrieval=retrieval;self.extract_success=extract_success
    def get(self,selector):
        id,*path=selector
        value=self.values[id]
        for part in path:value=value[part]
        return value
    def render(self,text):
        return re.sub(r'\{\{#([^#]+)#\}\}',lambda m: str(self.get(m[1].split('.'))) if m[1]!='context' else '[fixture evidence]',text)
    def execute(self):
        current=START
        while current:
            if current in self.trace:raise AssertionError('cycle')
            self.trace.append(current);d=N[current];typ=d['type'];handle='source'
            if typ=='start':out={'staff_id':self.staff,'locale':'zh-CN','query':self.query}
            elif typ=='code':out=run_code(current,**{v['variable']:self.get(v['value_selector']) for v in d['variables']})
            elif typ=='question-classifier':
                self.get(d['query_variable_selector'])
                if current==ROUTER:
                    handle={'knowledge':'1','record':'2','action':'1788596195643','mixed':'1788596222705','clarify':'1788596234003','disallowed':'1788596268356'}[self.kind]
                elif current=='1788354025939':
                    handle={'property':'1','lease':'2','rent':'2','maintenance':'1788354410675','inspection':'1788354435210','analytics':'1788354460599','unsupported':'1788354473605'}[self.domain]
                else:handle='1' if self.action!='other' else '2'
                out={'class_name':handle}
            elif typ=='parameter-extractor':
                self.get(d['query'])
                out={p['name']:0 if p['type']=='number' else '' for p in d['parameters']}
                if current=='mx-planner':out['plan_json']=json.dumps(self.p,ensure_ascii=False)
                elif current=='1788617561916':out.update(action=self.action,property_reference=self.action_prop,summary='浴室漏水',priority='high',request_scope='single')
                elif current=='sc-maint-extract':out.update(action='search',property_reference=self.prop)
                elif current=='1788356099148':out.update(property_reference=self.prop,bedrooms=None)
                elif current=='1788357840930':out.update(property_reference=self.prop,request_type=self.domain,due_within_days=None)
                elif current=='sc-inspect-extract':out.update(property_reference=self.prop,request_type='inspection_history')
                elif current=='sc-analytics-extract':out.update(metric='vacancy_rate',scope='my_portfolio')
                out.update(__is_success=self.extract_success,__reason='')
            elif typ=='if-else':
                handle='false'
                for c in d['cases']:
                    checks=[]
                    for cond in c['conditions']:
                        value=self.get(cond['variable_selector']);op=cond['comparison_operator'];want=cond.get('value')
                        if op=='is':checks.append(value==want)
                        elif op=='not empty':checks.append(bool(value))
                        elif op=='contains':checks.append(want in value)
                        else:raise AssertionError('Unsupported test comparator '+op)
                    if (all(checks) if c['logical_operator']=='and' else any(checks)):
                        handle=c['case_id'];break
                out={}
            elif typ=='variable-aggregator':
                candidates=[self.get(s) for s in d['variables'] if s[0] in self.values]
                assert len(candidates)==1,(current,len(candidates))
                out={'output':candidates[0]}
            elif typ=='template-transform':
                out={'output':Environment(undefined=StrictUndefined).from_string(d['template']).render(**{v['variable']:self.get(v['value_selector']) for v in d['variables']})}
            elif typ=='knowledge-retrieval':
                self.get(d['query_variable_selector'])
                out={'result':[{'content':'[offline fixture]','title':'EMP fixture'}] if self.retrieval else []}
            elif typ=='llm':
                # Render EVERY reference to catch references to skipped stages. No actual model is called.
                texts=[self.render(p['text']) for p in d['prompt_template']]
                if d.get('context',{}).get('enabled'):self.get(d['context']['variable_selector'])
                out={'text':'[离线模型占位，不代表真实回答质量] '+d['title']}
            elif typ=='end':
                return {o['variable']:self.get(o['value_selector']) for o in d['outputs']}
            else:raise AssertionError(typ)
            self.values[current]=out
            edges=[e for e in E if e['source']==current and e['sourceHandle']==handle]
            assert len(edges)==1,(current,handle,edges)
            current=edges[0]['target']
        raise AssertionError('No end')


class WorkflowTests(unittest.TestCase):
    def test_source_unchanged(self):
        m=json.loads((ROOT/'build_manifest.json').read_text())
        self.assertEqual(hashlib.sha256(Path(m['source']).read_bytes()).hexdigest(),m['source_sha256'])
    def test_all_code_signatures_compile(self):
        for id,d in N.items():
            if d['type']=='code':
                ns={};exec(d['code'],ns)
                self.assertEqual(set(inspect.signature(ns['main']).parameters),{v['variable'] for v in d['variables']},id)
    def test_all_nodes_reachable_and_no_dangling_references(self):
        self.assertEqual(len(N),len(DOC['workflow']['graph']['nodes']))
        reached={START}
        while True:
            updated=reached|{e['target'] for e in E if e['source'] in reached}
            if updated==reached:break
            reached=updated
        self.assertEqual(reached,set(N))
        for e in E:self.assertIn(e['source'],N);self.assertIn(e['target'],N)
        def visit(x):
            if isinstance(x,dict):
                for k,v in x.items():
                    if k in ('value_selector','variable_selector','query_variable_selector','query') and isinstance(v,list) and v:
                        self.assertIn(v[0],N)
                    visit(v)
            elif isinstance(x,list):
                for v in x:visit(v)
            elif isinstance(x,str):
                for ref in re.findall(r'\{\{#([^#]+)#\}\}',x):
                    if ref!='context':self.assertIn(ref.split('.')[0],N)
        visit(list(N.values()))
    def test_single_domains_and_reuse(self):
        for domain in ['property','lease','rent','maintenance','inspection','analytics','unsupported']:
            with self.subTest(domain=domain):
                run=GraphRun(kind='record',domain=domain)
                result=run.execute();self.assertEqual(result['request_origin'],'single')
                self.assertIn('1788354025939',run.trace);self.assertNotIn('mx-planner',run.trace)
                mixed=GraphRun(domain=domain);mixed.execute()
                self.assertIn('1788354025939',mixed.trace)
    def test_knowledge_single_and_empty(self):
        for retrieval in [True,False]:
            run=GraphRun(kind='knowledge',retrieval=retrieval);out=run.execute()
            self.assertEqual(len(json.loads(out['task_results'])),1)
            self.assertNotIn('1788354025939',run.trace)
    def test_single_actions(self):
        for staff,prop,status in [('staff_amy','HV-102','draft_simulated'),('staff_ben','PA-201','draft_simulated'),('staff_chloe','HV-101','denied'),('staff_amy','PA-201','denied'),('staff_david','HV-102','denied')]:
            run=GraphRun(kind='action',staff=staff,prop=prop);out=run.execute()
            self.assertEqual(json.loads(out['task_results'])[0]['status'],status)
    def test_mixed_knowledge_action(self):
        run=GraphRun(p=plan(k='独岗安全要求',a='给 HV-102 创建浴室漏水草稿'))
        out=run.execute();rs=json.loads(out['task_results'])
        self.assertEqual([r['kind'] for r in rs],['knowledge','action'])
        self.assertEqual(rs[-1]['status'],'draft_simulated')
        self.assertIn('1788618003603',run.trace);self.assertNotIn('1788354025939',run.trace)
    def test_condition_pass_and_fail(self):
        for status,expected in [('in_progress','draft_simulated'),('resolved','condition_not_met')]:
            run=GraphRun(p=plan(q='查 HV-102 维修',a='给 HV-102 创建浴室漏水草稿',dependency='maintenance_status',prop='HV-102',status=status))
            rs=json.loads(run.execute()['task_results']);self.assertEqual(rs[-1]['status'],expected)
            self.assertEqual('1788618634869' in run.trace,expected=='draft_simulated')
    def test_dependent_query_denied_empty_and_unsupported(self):
        for staff,prop,domain in [('staff_chloe','HV-101','maintenance'),('staff_amy','PA-201','maintenance'),('staff_amy','HV-101','maintenance'),('staff_amy','HV-102','unsupported')]:
            run=GraphRun(staff=staff,prop=prop,domain=domain,p=plan(q=f'查 {prop} 维修',a=f'给 {prop} 创建漏水草稿',dependency='after_query',prop=prop))
            rs=json.loads(run.execute()['task_results']);self.assertEqual(rs[-1]['status'],'dependency_failed')
            self.assertNotIn('1788618634869',run.trace)
    def test_independent_action_not_authorized_by_query(self):
        run=GraphRun(staff='staff_amy',prop='HV-102',action_prop='PA-201',p=plan(q='查 HV-102 维修',a='给 PA-201 创建漏水草稿'))
        rs=json.loads(run.execute()['task_results']);self.assertEqual(rs[0]['status'],'ok');self.assertEqual(rs[-1]['status'],'denied')
    def test_independent_action_can_succeed_after_denied_unrelated_query(self):
        run=GraphRun(prop='PA-201',action_prop='HV-102',p=plan(q='查 PA-201 维修',a='给 HV-102 创建漏水草稿'))
        rs=json.loads(run.execute()['task_results']);self.assertEqual(rs[0]['status'],'denied');self.assertEqual(rs[-1]['status'],'draft_simulated')
    def test_high_privilege_is_not_granted_by_condition(self):
        run=GraphRun(action='close_record',p=plan(q='查 HV-102 维修',a='关闭 HV-102 工单',dependency='maintenance_status',prop='HV-102',status='in_progress'))
        rs=json.loads(run.execute()['task_results']);self.assertEqual(rs[-1]['status'],'denied');self.assertNotIn('1788618634869',run.trace)
    def test_dependent_target_rechecked(self):
        run=GraphRun(action_prop='HV-101',p=plan(q='查 HV-102 维修',a='给 HV-102 创建漏水草稿',dependency='after_query',prop='HV-102'))
        rs=json.loads(run.execute()['task_results']);self.assertEqual(rs[-1]['status'],'denied')
        self.assertEqual(run.values['1788618003603']['reason_code'],'DEPENDENCY_TARGET_MISMATCH')
    def test_manual_policy_dependency(self):
        run=GraphRun(p=plan(k='独岗安全要求',a='依据政策给 HV-102 创建草稿',dependency='manual'))
        rs=json.loads(run.execute()['task_results']);self.assertEqual(rs[-1]['status'],'needs_review');self.assertNotIn('1788618003603',run.trace)
    def test_three_parts(self):
        run=GraphRun(p=plan(k='独岗安全要求',q='查 HV-102 维修',a='给 HV-102 创建漏水草稿'))
        rs=json.loads(run.execute()['task_results']);self.assertEqual(len(rs),3)
        self.assertLess(run.trace.index('sc-knowledge-llm'),run.trace.index('1788354025939'))
        self.assertLess(run.trace.index('sc-maint-llm'),run.trace.index('1788618003603'))
    def test_unknown_identity(self):
        run=GraphRun(staff='staff_unknown');run.execute();self.assertNotIn('mx-planner',run.trace)
    def test_other_exits(self):
        for kind in ['clarify','disallowed']:
            run=GraphRun(kind=kind);run.execute();self.assertNotIn('mx-context',run.trace)
    def test_planner_failures(self):
        p=plan(k='政策',a='给 HV-102 创建草稿');p['task_counts']['action']=2
        run=GraphRun(p=p);run.execute();self.assertNotIn('mx-context',run.trace)
        run=GraphRun(extract_success=0);run.execute();self.assertNotIn('mx-context',run.trace)
        p=plan(k='政策',a='给 PA-201 创建草稿')
        run=GraphRun(p=p,query='说明政策并创建 HV-102 草稿');run.execute();self.assertNotIn('mx-context',run.trace)
    def test_read_mock_cannot_write_and_filters(self):
        ctx=run_code('1788353701188',staff_id='staff_amy')['staff_context']
        for action in ['create','update','create_draft','unknown']:
            r=runtime.maintenance_mock(ctx,action,'HV-102','','','')
            self.assertEqual(json.loads(r['tool_result'])['status'],'forbidden')
        r=runtime.maintenance_mock(ctx,'search','HV-101','','','')
        self.assertEqual(json.loads(r['tool_result'])['items'],[])
        r=runtime.maintenance_mock(ctx,'search','HV-102','','','MAINT-PA201-01')
        self.assertEqual(json.loads(r['tool_result'])['items'],[])
    def test_tools_check_trusted_permissions(self):
        ctx=run_code('1788353701188',staff_id='staff_chloe')['staff_context']
        r=run_code('17883597438570',staff_id='staff_amy',property_reference='HV-102',rent_status='',staff_context=ctx)
        self.assertEqual(json.loads(r['tool_result'])['status'],'forbidden')
    def test_conditional_backstop(self):
        p=plan(q='查 HV-102 维修',a='给 HV-102 创建草稿')
        result=runtime.validate_plan(json.dumps(p),1,'查 HV-102 维修，如果已经完成就给 HV-102 创建草稿')
        self.assertEqual(json.loads(result['plan'])['dependency'],'manual')


if __name__=='__main__':unittest.main(verbosity=2)
