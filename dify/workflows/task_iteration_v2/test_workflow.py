"""Offline tests. Model and retrieval outputs are explicit fixtures, not actual Dify execution."""
from pathlib import Path
from collections import Counter
import copy,hashlib,inspect,json,re,unittest
import yaml
from jinja2 import Environment,StrictUndefined
import runtime
ROOT=Path(__file__).resolve().parent
DOC=yaml.safe_load((ROOT/'Safescan 员工侧 Agent - 多任务串行与人工分流 v2.yml').read_text())
N={n['id']:n['data'] for n in DOC['workflow']['graph']['nodes']}
NODE={n['id']:n for n in DOC['workflow']['graph']['nodes']}
E=DOC['workflow']['graph']['edges']
START='1788353269350';STAFF='1788353701188';CTX='1788675778490';SPLIT='1788680503664';CHECK='1788680639254'
IT='task-iteration-v2';PACK='task-result-v2'


def task(id,text,kind='record_query',deps=None,condition=''):
    return dict(id=id,source_text=text,type=kind,depends_on=deps or [],condition_text=condition)


def execute_code(id,**kwargs):
    ns={};exec(N[id]['code'],ns)
    return ns['main'](**kwargs)


class Run:
    def __init__(self,tasks,staff='staff_amy',original=None,fixtures=None,fail_node=None,unassigned=None):
        self.tasks=tasks;self.staff=staff;self.original=original or '，并'.join(t['source_text'] for t in tasks)
        self.fixtures=fixtures or {};self.fail_node=fail_node;self.unassigned=unassigned or []
        self.values={};self.trace=[];self.child_values=[]
    def get(self,s):
        value=self.values[s[0]]
        for part in s[1:]:value=value[part]
        return value
    def render(self,s):
        return re.sub(r'\{\{#([^#]+)#\}\}',lambda m: str(self.get(m[1].split('.'))) if m[1]!='context' else '[fixture evidence]',s)
    def execute(self,start=START,stop=None):
        current=start
        while True:
            d=N[current];typ=d['type'];handle='source';self.trace.append(current)
            item=self.values.get(IT,{}).get('item',{});tid=item.get('id')
            cfg=self.fixtures.get(tid,{})
            if self.fail_node==(tid,current):raise RuntimeError('Injected node failure')
            if typ=='start':out={'staff_id':self.staff,'query':self.original,'locale':'zh-CN'}
            elif typ=='iteration-start':out={}
            elif typ=='code':
                kwargs={v['variable']:self.get(v['value_selector']) for v in d['variables']}
                out=execute_code(current,**kwargs)
                assert set(out)==set(d['outputs']),(current,'output mismatch')
                for key,schema in d['outputs'].items():
                    t=schema['type'];v=out[key]
                    assert (t=='string' and isinstance(v,str) or t=='number' and isinstance(v,(int,float))
                            or t=='boolean' and isinstance(v,bool) or t.startswith('array') and isinstance(v,list)),(current,key,t,type(v))
            elif typ=='iteration':
                base=copy.deepcopy(self.values);results=[]
                for i,t in enumerate(self.get(d['iterator_selector'])):
                    child=Run(self.tasks,self.staff,self.original,self.fixtures,self.fail_node,self.unassigned)
                    child.values=copy.deepcopy(base);child.values[IT]={'item':t,'index':i}
                    try:
                        child.execute(d['start_node_id'],d['output_selector'][0]);results.append(child.get(d['output_selector']))
                    except Exception:
                        if d['error_handle_mode']!='continue-on-error':raise
                        results.append(None)
                    self.trace+=child.trace;self.child_values.append(child.values)
                out={'output':results}
            elif typ=='llm':
                for p in d['prompt_template']:self.render(p['text'])
                if current==SPLIT:out={'text':json.dumps({'tasks':self.tasks,'unassigned_text':self.unassigned},ensure_ascii=False)}
                else:
                    if d.get('context',{}).get('enabled'):self.get(d['context']['variable_selector'])
                    out={'text':'[离线模型占位] '+d['title']}
            elif typ=='question-classifier':
                self.get(d['query_variable_selector'])
                if current=='1788354025939':
                    handle={'property':'1','lease':'2','rent':'2','maintenance':'1788354410675','inspection':'1788354435210','analytics':'1788354460599','unsupported':'1788354473605'}[cfg.get('domain','maintenance')]
                else:handle='2' if cfg.get('action')=='other' else '1'
                out={'class_name':handle}
            elif typ=='parameter-extractor':
                query=self.get(d['query']);refs=re.findall(r'\b(?:HV|PA)-\d+\b',query)
                prop=cfg.get('prop',refs[0] if refs else '')
                out={p['name']:None if p['type']=='number' else '' for p in d['parameters']}
                if current=='1788617561916':out.update(action=cfg.get('action','create_draft'),property_reference=prop,summary=cfg.get('summary','浴室漏水'),priority='high',request_scope='single')
                elif current=='sc-maint-extract':out.update(action='search',property_reference=prop,maintenance_id=cfg.get('maintenance_id',''))
                elif current=='1788356099148':out.update(property_reference=prop)
                elif current=='1788357840930':out.update(property_reference=prop,request_type=cfg.get('domain','lease'))
                elif current=='sc-inspect-extract':out.update(property_reference=prop,request_type=cfg.get('request_type','inspection_history'))
                elif current=='sc-analytics-extract':out.update(metric='vacancy_rate',scope=cfg.get('scope','my_portfolio'))
                out.update(__is_success=cfg.get('extract_success',1),__reason='')
            elif typ=='knowledge-retrieval':
                self.get(d['query_variable_selector'])
                out={'result':[{'content':'fixture','title':'EMP fixture'}] if cfg.get('retrieval',True) else []}
            elif typ=='if-else':
                handle='false'
                for case in d['cases']:
                    checks=[]
                    for c in case['conditions']:
                        value=self.get(c['variable_selector']);op=c['comparison_operator'];want=c.get('value')
                        checks.append(value==want if op=='is' else bool(value) if op=='not empty' else want in value if op=='contains' else False)
                    if (all(checks) if case['logical_operator']=='and' else any(checks)):
                        handle=case['case_id'];break
                out={}
            elif typ=='template-transform':
                out={'output':Environment(undefined=StrictUndefined).from_string(d['template']).render(**{v['variable']:self.get(v['value_selector']) for v in d['variables']})}
            elif typ=='variable-aggregator':
                found=[self.get(s) for s in d['variables'] if s[0] in self.values]
                assert len(found)==1,(current,'stale or missing branches',len(found));out={'output':found[0]}
            elif typ=='end':return {v['variable']:self.get(v['value_selector']) for v in d['outputs']}
            else:raise AssertionError('Unsupported node '+typ)
            self.values[current]=out
            if current==stop:return out
            es=[e for e in E if e['source']==current and e['sourceHandle']==handle]
            assert len(es)==1,(current,handle,es)
            current=es[0]['target']


class Tests(unittest.TestCase):
    def test_source_unchanged(self):
        m=json.loads((ROOT/'build_manifest.json').read_text())
        self.assertEqual(hashlib.sha256(Path(m['source']).read_bytes()).hexdigest(),m['source_sha256'])
    def test_code_inputs_outputs(self):
        for id,d in N.items():
            if d['type']=='code':
                ns={};exec(d['code'],ns)
                self.assertEqual(set(inspect.signature(ns['main']).parameters),{v['variable'] for v in d['variables']},id)
    def test_iteration_schema_and_no_cross_container_edges(self):
        self.assertEqual(N[IT]['iterator_input_type'],'array[object]')
        self.assertEqual(N[IT]['output_type'],'array[string]')
        self.assertFalse(N[IT]['is_parallel']);self.assertEqual(N[IT]['error_handle_mode'],'continue-on-error')
        children={id for id,n in NODE.items() if n.get('parentId')==IT}
        self.assertIn(N[IT]['start_node_id'],children);self.assertIn(PACK,children)
        for id in children:
            self.assertEqual(N[id]['iteration_id'],IT)
            self.assertNotEqual(N[id]['type'],'end')
            p=NODE[id]['position'];self.assertGreaterEqual(p['x'],0);self.assertGreaterEqual(p['y'],0)
            self.assertLessEqual(p['x']+NODE[id]['width'],NODE[IT]['width'])
            self.assertLessEqual(p['y']+NODE[id]['height'],NODE[IT]['height'])
        for e in E:self.assertEqual(e['source'] in children,e['target'] in children,e)
    def test_references_reachable_and_acyclic(self):
        edges=[(e['source'],e['target']) for e in E]+[(IT,N[IT]['start_node_id'])]
        self.assertEqual(len(N),len(DOC['workflow']['graph']['nodes']))
        seen=set();visiting=set()
        def walk(id):
            self.assertNotIn(id,visiting,'cycle')
            if id in seen:return
            visiting.add(id)
            for a,b in edges:
                if a==id:walk(b)
            visiting.remove(id);seen.add(id)
        walk(START);self.assertEqual(seen,set(N))
        def verify(x):
            if isinstance(x,dict):
                for k,v in x.items():
                    if k in ('value_selector','variable_selector','query_variable_selector','iterator_selector','output_selector','query') and isinstance(v,list) and v:self.assertIn(v[0],N)
                    verify(v)
            elif isinstance(x,list):
                for v in x:verify(v)
            elif isinstance(x,str):
                for ref in re.findall(r'\{\{#([^#]+)#\}\}',x):
                    if ref!='context':self.assertIn(ref.split('.')[0],N)
        verify(list(N.values()))
    def statuses(self,r):
        return [json.loads(v)['status'] if v else 'error' for v in r.values[IT]['output']]
    def test_three_queries_shared_nodes(self):
        ts=[task('t1','查询 HV-102 的维修进度'),task('t2','查询 HV-102 的租金情况'),task('t3','查询 HV-102 的合同到期时间')]
        r=Run(ts,fixtures={'t2':{'domain':'rent'},'t3':{'domain':'lease'}});out=r.execute()
        self.assertEqual(self.statuses(r),['ok','ok','ok']);self.assertEqual(r.trace.count('1788354025939'),3)
        self.assertEqual(set(out),{'answer'});self.assertNotIn('task_results',out['answer']);self.assertNotIn('"tool"',out['answer'])
    def test_one_query_two_knowledge(self):
        ts=[task('t1','查询 HV-102 维修'),task('t2','说明独岗安全要求','knowledge_question'),task('t3','说明员工隐私要求','knowledge_question')]
        r=Run(ts);r.execute();self.assertEqual(self.statuses(r),['ok','answered','answered'])
        self.assertEqual(r.trace.count('1788573491089'),2)
    def test_independent_denial_does_not_stop_other(self):
        r=Run([task('t1','查询 PA-201 维修'),task('t2','查询 HV-102 维修')]);r.execute()
        self.assertEqual(self.statuses(r),['denied','ok']);self.assertEqual(r.trace.count('17884266709080'),1)
    def test_knowledge_survives_query_denial(self):
        r=Run([task('t1','查询 HV-101 维修'),task('t2','员工隐私要求','knowledge_question')],staff='staff_chloe');r.execute()
        self.assertEqual(self.statuses(r),['denied','answered'])
    def test_single_knowledge_empty(self):
        r=Run([task('t1','员工隐私要求','knowledge_question')],fixtures={'t1':{'retrieval':False}});r.execute()
        self.assertEqual(self.statuses(r),['insufficient_evidence'])
    def test_single_query_domains(self):
        for domain in ['property','rent','lease','inspection','analytics','maintenance','unsupported']:
            with self.subTest(domain=domain):
                r=Run([task('t1','查询 HV-102 业务情况')],fixtures={'t1':{'domain':domain}});r.execute()
                self.assertNotIn('error',self.statuses(r));self.assertEqual(len(self.statuses(r)),1)
    def test_single_action_permissions(self):
        for staff,prop,want in [('staff_amy','HV-102','draft_simulated'),('staff_ben','PA-201','draft_simulated'),('staff_chloe','HV-101','denied'),('staff_amy','PA-201','denied'),('staff_david','HV-102','denied')]:
            r=Run([task('t1',f'给 {prop} 创建漏水草稿','action_request')],staff=staff);r.execute()
            self.assertEqual(self.statuses(r),[want]);self.assertEqual('1788618634869' in r.trace,want=='draft_simulated')
    def test_high_privilege_single_denied(self):
        r=Run([task('t1','关闭 HV-102 工单','action_request')],fixtures={'t1':{'action':'close_record'}});r.execute()
        self.assertEqual(self.statuses(r),['denied']);self.assertNotIn('1788618634869',r.trace)
    def test_all_multi_write_combinations_human(self):
        variants=[
            [task('t1','查 HV-102 维修'),task('t2','如果处理中就关闭 HV-102 工单','action_request',['t1'],'如果处理中')],
            [task('t1','查 HV-102 维修'),task('t2','查 HV-102 租金'),task('t3','给 HV-102 创建草稿','action_request')],
            [task('t1','给 HV-101 创建草稿','action_request'),task('t2','给 HV-102 创建草稿','action_request')],
            [task('t1','独岗安全要求','knowledge_question'),task('t2','给 HV-102 创建草稿','action_request')]]
        for ts in variants:
            r=Run(ts);out=r.execute();self.assertEqual(r.values[CHECK]['route'],'human')
            self.assertNotIn(IT,r.trace);self.assertNotIn('1788573491089',r.trace);self.assertNotIn('1788618634869',r.trace)
            self.assertIn('尚未提交人工工单',out['answer'])
    def test_iteration_exception_continues_without_stale_results(self):
        ts=[task('t1','查询 HV-102 维修'),task('t2','查询 HV-101 维修'),task('t3','员工隐私要求','knowledge_question')]
        r=Run(ts,fail_node=('t2','sc-maint-llm'));out=r.execute()
        self.assertEqual(self.statuses(r),['ok','error','answered']);self.assertIn('本项处理发生异常',out['answer'])
        self.assertEqual(r.trace.count(CTX),3)
    def test_identity_invalid_before_split(self):
        r=Run([task('t1','查房源')],staff='unknown');r.execute();self.assertNotIn(SPLIT,r.trace)
    def test_unclear(self):
        r=Run([task('t1','随便处理一下','unclear')]);r.execute();self.assertNotIn(IT,r.trace)
    def test_missing_coverage_duplicate_and_unknown_dependency(self):
        variants=[([task('t1','查 HV-102 维修')],'查 HV-102 维修并说明隐私要求'),
                  ([task('t1','查 HV-102'),task('t1','查 PA-201')],None),
                  ([task('t1','查 HV-102',deps=['t9'])],None)]
        for ts,original in variants:
            r=Run(ts,original=original);r.execute();self.assertEqual(r.values[CHECK]['route'],'clarify');self.assertNotIn(IT,r.trace)
    def test_repeated_identical_text_uses_distinct_spans(self):
        ts=[task('t1','查询 HV-102 维修'),task('t2','查询 HV-102 维修')]
        r=Run(ts);r.execute();self.assertEqual(self.statuses(r),['ok','ok'])
    def test_limit_ten_and_eleven(self):
        for count in [10,11]:
            ts=[task('t'+str(i),f'说明第{i}项员工政策','knowledge_question') for i in range(count)]
            r=Run(ts);r.execute();self.assertEqual(IT in r.trace,count==10)
    def test_read_dependency_clarifies(self):
        r=Run([task('t1','查 HV-102 维修'),task('t2','依据结果查询对应政策','knowledge_question',['t1'])]);r.execute()
        self.assertEqual(r.values[CHECK]['route'],'clarify');self.assertNotIn(IT,r.trace)
    def test_read_tool_cannot_write(self):
        ctx=execute_code(STAFF,staff_id='staff_amy')['staff_context']
        for action in ['create','update','create_draft']:
            out=execute_code('17884266709080',staff_context=ctx,action=action,property_reference='HV-102',priority='',status='',maintenance_id='')
            self.assertEqual(json.loads(out['tool_result'])['status'],'forbidden')
    def test_final_joins_by_id_and_preserves_missing(self):
        ts=[task('t1','任务一'),task('t2','任务二'),task('t3','任务三')]
        raw=[json.dumps({'task_id':'t3','answer':'三'}),None,json.dumps({'task_id':'t1','answer':'一'})]
        out=runtime.final_result(ts,raw)['answer'];self.assertLess(out.index('一'),out.index('三'));self.assertIn('发生异常',out)
    def test_parser_invalid_json(self):
        for raw in ['','[]','{"tasks":null}','{"tasks":[1],"unassigned_text":[]}']:
            self.assertEqual(runtime.route_tasks(raw,'query')['route'],'clarify')
    def test_whitespace_difference_restores_original(self):
        original='查询我名下有哪些房产满足以下要求。\n要求3B2B，通勤 UNSW 和 USYD 方便，距离超市近，并且租金价格在 $2500 - $3000。'
        source=original.replace('\n','')
        r=runtime.route_tasks(json.dumps({'tasks':[task('t1',source)],'unassigned_text':[]}),original)
        self.assertEqual(r['route'],'execute')
        self.assertEqual(r['tasks'][0]['source_text'],original)
        for changed in [source.replace('2500','2000'),source.replace('，距离超市近','')]:
            r=runtime.route_tasks(json.dumps({'tasks':[task('t1',changed)],'unassigned_text':[]}),original)
            self.assertEqual(r['route'],'clarify')
    def test_action_extract_failure_cannot_execute(self):
        r=Run([task('t1','给 HV-102 创建草稿','action_request')],fixtures={'t1':{'extract_success':0}});r.execute()
        self.assertEqual(self.statuses(r),['needs_input']);self.assertNotIn('1788618634869',r.trace)


if __name__=='__main__':unittest.main(verbosity=2)
