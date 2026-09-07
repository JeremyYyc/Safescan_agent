"""Build v2 from the user's latest DSL; source stays untouched."""
from pathlib import Path
from collections import defaultdict,deque
import copy,hashlib,inspect,json,sys,yaml
import runtime
ROOT=Path(__file__).resolve().parent
SOURCE=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/Users/jeremyyang/Downloads/Safescan 员工侧 Agent - Internal Knowledge Base (1).yml')
doc=yaml.safe_load(SOURCE.read_text());g=doc['workflow']['graph']
N={n['id']:copy.deepcopy(n) for n in g['nodes']};E=copy.deepcopy(g['edges'])
START='1788353269350';STAFF='1788353701188';IDENTITY='1788573604635'
SPLIT='1788680503664';CHECK='1788680639254';CTX='1788675778490'
IT='task-iteration-v2';ITSTART=IT+'start';PACK='task-result-v2';FINAL='tasks-final-v2';ROUTE='task-route-v2'
# Keep the existing business region intact; mx-end is external and replaced below.
inside=set();todo=[CTX]
while todo:
 id=todo.pop()
 if id=='mx-end' or id in inside:continue
 inside.add(id);todo.extend(e['target'] for e in E if e['source']==id)
keep=inside|{START,STAFF,IDENTITY,SPLIT,CHECK,'17885972759980','17885972759981'}
removed=sorted(set(N)-keep)
N={id:n for id,n in N.items() if id in keep}
E=[e for e in E if e['source'] in keep and e['target'] in keep]
E=[e for e in E if e['source']!=CHECK and not (e['source']==IDENTITY and e['sourceHandle']=='true')]


def add(id,title,typ,**data):
 N[id]={'id':id,'type':'custom','data':{'title':title,'type':typ,'desc':'','selected':False,**data},
        'position':{'x':0,'y':0},'positionAbsolute':{'x':0,'y':0},'width':260,'height':100,
        'sourcePosition':'right','targetPosition':'left','selected':False,'zIndex':0}


def edge(src,dst,handle='source'):
 E.append({'id':f'{src}-{handle}-{dst}-target','source':src,'sourceHandle':handle,'target':dst,'targetHandle':'target',
           'type':'custom','zIndex':0,'selected':False,'data':{}})


def function(fn):return 'import json\nimport re\n\n'+inspect.getsource(fn).replace('def '+fn.__name__+'(','def main(',1)


def code(id,title,fn,inputs,outputs):
 add(id,title,'code',code_language='python3',code=function(fn),
     variables=[{'variable':k,'value_selector':v[0],'value_type':v[1]} for k,v in inputs.items()],
     outputs={k:{'type':v,'children':None} for k,v in outputs.items()})

code(CHECK,'MX-任务校验与路由',runtime.route_tasks,{'raw_text':([SPLIT,'text'],'string'),'original':([START,'query'],'string')},
     {'route':'string','message':'string','tasks':'array[object]','task_count':'number'})
edge(IDENTITY,SPLIT,'true');edge(CHECK,ROUTE)
# Keep the user's current LLM and business split instructions; add global entry/count semantics.
sys_prompt=N[SPLIT]['data']['prompt_template'][0]['text']
sys_prompt+='''\n\n本节点现在处理全部员工请求，不仅处理 Mixed。单个任务也输出只有一项的 tasks 数组。
不得要求必须同时包含知识与查询；每类可以有多项，不要输出任务数量或 plan_json。
创建草稿属于 action_request，即使目前只是 Mock。
查询维修、查询租金、查询合同属于三个不同业务任务；一个房源查询的多个条件仍是一个任务。
为两个房源分别创建草稿属于两个操作任务。查状态后按条件关闭工单属于查询加操作两个任务。
source_text 必须包含原文中的限定词和条件。为便于原文覆盖验证，保留礼貌前缀和连接词也可以。
不同任务不得共享重叠的原文片段；不明确的代词、共享目标或不能独立表达的省略应放入 unassigned_text，不能猜测目标。
与员工业务无关或明显要求绕过权限、伪造记录的内容标为 unclear；不得转成普通查询或操作。
将多任务是否需要人工处理交给后续代码决定，自己不得删减任务或执行操作。
'''
N[SPLIT]['data']['prompt_template'][0]['text']=sys_prompt
N[SPLIT]['data']['model']['completion_params']['temperature']=0
N[SPLIT]['data']['desc']='全部请求先拆分为任务列表；不生成嵌套 JSON 字符串。'

cases=[]
for id,value in [('human','human'),('execute','execute')]:
 cases.append({'case_id':id,'id':id,'logical_operator':'and','conditions':[{'id':'route-'+id,'comparison_operator':'is',
     'variable_selector':[CHECK,'route'],'varType':'string','value':value}]})
add(ROUTE,'处理方式分支','if-else',cases=cases)
for handle,name in [('human','人工处理说明'),('false','补充信息说明')]:
 id='task-'+handle+'-message'
 add(id,name,'template-transform',template='{{ message }}',variables=[{'variable':'message','value_selector':[CHECK,'message'],'value_type':'string'}])
 edge(ROUTE,id,handle)
 add(id+'-end','输出','end',outputs=[{'variable':'answer','value_selector':[id,'output'],'value_type':'string'}]);edge(id,id+'-end')

add(IT,'任务迭代（串行）','iteration',iterator_selector=[CHECK,'tasks'],iterator_input_type='array[object]',
    output_selector=[PACK,'result'],output_type='array[string]',start_node_id=ITSTART,
    is_parallel=False,parallel_nums=3,error_handle_mode='continue-on-error',flatten_output=False)
edge(ROUTE,IT,'execute')
add(ITSTART,'','iteration-start')
N[ITSTART].update(type='custom-iteration-start',draggable=False,selectable=False,width=44,height=48)
edge(ITSTART,CTX)
code(CTX,'统一子任务上下文',runtime.task_context,{'item':([IT,'item'],'object'),'staff_context':([STAFF,'staff_context'],'string')},
     {**{k:'string' for k in ['plan','origin','task_id','task_type','task_query','knowledge_query','record_query','action_query']},
      **{k:'boolean' for k in ['has_knowledge','has_record','kb_allowed']}})
# Existing answer logic is retained, including all per-task ACLs and Mock boundaries.
code(PACK,'单任务结果封装',runtime.task_result,
     {'task_id':([CTX,'task_id'],'string'),'task_query':([CTX,'task_query'],'string'),
      'answer':(['mx-final','answer'],'string'),'task_results':(['mx-final','task_results'],'string')},{'result':'string'})
inside|={ITSTART,PACK};edge('mx-final',PACK)
code(FINAL,'多任务结果整理',runtime.final_result,{'tasks':([CHECK,'tasks'],'array[object]'),'results':([IT,'output'],'array[string]')},{'answer':'string'})
edge(IT,FINAL)
add('mx-end','统一输出','end',outputs=[{'variable':'answer','value_selector':[FINAL,'answer'],'value_type':'string'}]);edge(FINAL,'mx-end')

# Source may have stale selector names from manual recreation. This known old ID is replaced consistently.
def replace_context(x):
 if isinstance(x,list):return [replace_context(v) for v in x]
 if isinstance(x,dict):return {k:replace_context(v) for k,v in x.items()}
 if isinstance(x,str):return x.replace('{{#mx-context.','{{#'+CTX+'.') if x!='mx-context' else CTX
 return x
for id in inside:N[id]['data']=replace_context(N[id]['data'])

# Position inner region in topological columns; container parent metadata is required by Dify.
def layout(ids,edges,offset_x=30,offset_y=80):
 indeg={id:0 for id in ids};children=defaultdict(list)
 for e in edges:
  if e['source'] in ids and e['target'] in ids:indeg[e['target']]+=1;children[e['source']].append(e['target'])
 queue=deque(sorted(id for id in ids if indeg[id]==0));level={id:0 for id in queue};seen=[]
 while queue:
  id=queue.popleft();seen.append(id)
  for child in children[id]:
   level[child]=max(level.get(child,0),level[id]+1);indeg[child]-=1
   if not indeg[child]:queue.append(child)
 assert len(seen)==len(ids),'Cycle detected'
 rows=defaultdict(int)
 for id in seen:
  x=offset_x+level[id]*310;y=offset_y+rows[level[id]]*400;rows[level[id]]+=1
  N[id]['position']={'x':x,'y':y};N[id]['positionAbsolute']={'x':x,'y':y}
 return max(n['position']['x']+n['width'] for id,n in N.items() if id in ids)+60, max(n['position']['y']+n['height'] for id,n in N.items() if id in ids)+60
for id in inside:
 N[id]['parentId']=IT;N[id]['extent']='parent';N[id]['zIndex']=1002
 N[id]['data'].update(isInIteration=True,isInLoop=False,iteration_id=IT)
 N[id]['selected']=False;N[id]['data']['selected']=False
 if N[id]['data']['type']=='question-classifier':N[id]['height']=330
width,height=layout(inside,E)
N[IT]['width']=width;N[IT]['height']=height;N[IT]['data'].update(width=width,height=height);N[IT]['zIndex']=1
outer=set(N)-inside
layout(outer,E,0,0)
# Keep downstream outer nodes beyond the right edge of the expanded container.
itx=N[IT]['position']['x'];ity=N[IT]['position']['y']
for id in [FINAL,'mx-end']:
 N[id]['position']['x']=itx+width+(330 if id==FINAL else 650)
 N[id]['position']['y']=ity
 N[id]['positionAbsolute']=copy.deepcopy(N[id]['position'])
for id in inside:
 N[id]['positionAbsolute']={'x':itx+N[id]['position']['x'],'y':ity+N[id]['position']['y']}
for e in E:
 e['data']={'isInIteration':e['source'] in inside,'isInLoop':False,
            'sourceType':N[e['source']]['data']['type'],'targetType':N[e['target']]['data']['type']}
 if e['source'] in inside:e['data']['iteration_id']=IT;e['zIndex']=1002
for n in N.values():n['selected']=False;n['data']['selected']=False
# Put parent before children for consistent canvas loading.
g['nodes']=[N[id] for id in N if id not in inside]+[N[id] for id in N if id in inside]
g['edges']=E;g['viewport']={'x':30,'y':60,'zoom':0.45}
doc['app']['name']='Safescan 员工侧 Agent - 多任务串行与人工分流 v2'
doc['app']['description']='全部请求先拆分；多任务含写操作整单人工处理；单任务及独立只读多任务串行逐项授权与汇总。仅 Mock 草稿，无真实写入或人工队列提交。'
OUT=ROOT/'Safescan 员工侧 Agent - 多任务串行与人工分流 v2.yml'
OUT.write_text(yaml.safe_dump(doc,allow_unicode=True,sort_keys=False,width=120))
manifest={'source':str(SOURCE),'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'output':OUT.name,
          'nodes':len(N),'edges':len(E),'iteration_children':len(inside),'removed_old_entry_nodes':removed,
          'online_dify_import':'not_run','online_llm_and_retrieval':'not_run'}
(ROOT/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps(manifest,ensure_ascii=False))
