"""Deterministic task routing and serialization for the Dify prototype."""
import json
import re


def route_tasks(raw_text: str, original: str) -> dict:
    def out(route, message, tasks=None):
        return {'route':route,'message':message,'tasks':tasks or [],'task_count':len(tasks or [])}
    if not isinstance(raw_text,str) or not isinstance(original,str):
        return out('clarify','请求或拆分结果格式无效。')
    text=raw_text.strip()
    if text.startswith('```') and text.endswith('```'):
        text='\n'.join(text.splitlines()[1:-1]).strip()
    try: result=json.loads(text)
    except (TypeError,ValueError): return out('clarify','未能可靠拆分请求，请重新说明。')
    if not isinstance(result,dict): return out('clarify','任务拆分格式无效。')
    tasks=result.get('tasks');unassigned=result.get('unassigned_text')
    if not isinstance(tasks,list) or not tasks: return out('clarify','没有识别到明确任务，请补充请求。')
    if not isinstance(unassigned,list) or any(not isinstance(x,str) for x in unassigned):
        return out('clarify','任务拆分格式无效。')
    allowed={'knowledge_question','record_query','action_request','unclear'}
    ids=set();spans=[]
    for task in tasks:
        if not isinstance(task,dict): return out('clarify','任务格式无效。')
        task_id=task.get('id');source=task.get('source_text');kind=task.get('type')
        deps=task.get('depends_on');condition=task.get('condition_text')
        if not isinstance(task_id,str) or not task_id.strip() or task_id in ids:
            return out('clarify','任务编号缺失或重复。')
        ids.add(task_id)
        if not isinstance(source,str) or not source.strip(): return out('clarify','任务缺少原文。')
        source=source.strip();task['source_text']=source
        # Match whitespace-insensitively, but map back to the exact original span.
        # Only whitespace is ignored; punctuation, numbers and words must still match.
        positions=[i for i,char in enumerate(original) if not char.isspace()]
        compact=''.join(original[i] for i in positions)
        needle=''.join(char for char in source if not char.isspace())
        match=compact.find(needle)
        start=-1
        while match>=0:
            candidate_start=positions[match]
            candidate_end=positions[match+len(needle)-1]+1
            if not any(candidate_start<b and candidate_end>a for a,b in spans):
                start=candidate_start
                end=candidate_end
                break
            match=compact.find(needle,match+1)
        if start<0: return out('clarify','任务原文缺失、重复或发生改写，请重新说明。')
        task['source_text']=original[start:end]
        spans.append((start,end))
        if kind not in allowed: return out('clarify','任务类型无效。')
        if not isinstance(deps,list) or any(not isinstance(x,str) for x in deps):
            return out('clarify','任务依赖格式无效。')
        if not isinstance(condition,str) or (condition and condition not in original):
            return out('clarify','任务条件与原文不一致。')
    # Decide this BEFORE any business subtask executes.
    if len(tasks)>1 and any(t['type']=='action_request' for t in tasks):
        return out('human','该请求包含多个任务及写入操作，需要人工处理。本次没有自动执行任何子任务。'
                   '当前原型尚未接入人工受理队列，因此尚未提交人工工单。',tasks)
    if any(x.strip() for x in unassigned): return out('clarify','请求中还有未明确的内容，请补充或拆分说明。')
    if any(t['type']=='unclear' for t in tasks): return out('clarify','部分任务类型不明确，请补充说明。')
    for task in tasks:
        if any(dep not in ids or dep==task['id'] for dep in task['depends_on']):
            return out('clarify','任务依赖引用无效。')
    covered=[False]*len(original)
    for start,end in spans:
        for i in range(start,end):covered[i]=True
    remainder=''.join(char if not covered[i] else ' ' for i,char in enumerate(original))
    remainder=re.sub(r'并且|同时|另外|以及|然后|并|和|及','',remainder)
    remainder=re.sub(r'[\W_]+','',remainder)
    if remainder: return out('clarify','原问题仍有未被任务覆盖的内容，请重新说明。')
    if len(tasks)>10: return out('clarify','当前原型单次最多处理 10 项任务，请分批提出。')
    if any(t['depends_on'] or t['condition_text'] for t in tasks):
        return out('clarify','任务包含需要前置结果的依赖或条件。当前版本请先完成前置查询，再提出后续请求。')
    return out('execute','允许逐项处理任务。',tasks)


def task_context(item: dict, staff_context: str) -> dict:
    if not isinstance(item,dict): raise ValueError('当前任务格式无效')
    kind=item.get('type');query=item.get('source_text')
    if kind not in {'knowledge_question','record_query','action_request'}: raise ValueError('当前任务类型无效')
    if not isinstance(query,str) or not query.strip(): raise ValueError('当前任务内容为空')
    staff=json.loads(staff_context)
    if not isinstance(staff,dict): raise ValueError('员工上下文无效')
    readers={'staff_amy','staff_ben','staff_chloe','staff_david'}
    kb_allowed=staff.get('staff_id') in readers
    if kind=='knowledge_question' and not kb_allowed: raise ValueError('当前员工无该知识库访问权限')
    plan={'origin':'single','knowledge_query':query if kind=='knowledge_question' else '',
          'record_query':query if kind=='record_query' else '',
          'action_query':query if kind=='action_request' else '',
          'dependency':'none','condition_property':'','condition_id':'','condition_status':''}
    return {'plan':json.dumps(plan,ensure_ascii=False),'origin':'single','task_id':item['id'],
            'task_type':kind,'task_query':query,'knowledge_query':plan['knowledge_query'],
            'record_query':plan['record_query'],'action_query':plan['action_query'],
            'has_knowledge':kind=='knowledge_question','has_record':kind=='record_query','kb_allowed':kb_allowed}


def task_result(task_id: str, task_query: str, answer: str, task_results: str) -> dict:
    results=json.loads(task_results)
    if not isinstance(results,list) or len(results)!=1 or not isinstance(results[0],dict):
        raise ValueError('单任务结果数量或格式不正确')
    return {'result':json.dumps({'task_id':task_id,'query':task_query,
                                'status':results[0].get('status','unknown'),'answer':answer},ensure_ascii=False)}


def final_result(tasks: list, results: list) -> dict:
    by_id={};duplicates=set()
    for value in results or []:
        if not isinstance(value,str):continue
        try:item=json.loads(value)
        except (TypeError,ValueError):continue
        if isinstance(item,dict) and isinstance(item.get('task_id'),str):
            if item['task_id'] in by_id:duplicates.add(item['task_id'])
            by_id[item['task_id']]=item
    sections=[]
    for i,task in enumerate(tasks,start=1):
        item=by_id.get(task['id'])
        if item is None or task['id'] in duplicates:
            answer='本项处理发生异常，未获得可靠结果，请重试。'
        else:
            answer=item.get('answer')
            if not isinstance(answer,str) or not answer.strip():answer='本项未返回有效回答。'
        sections.append(answer if len(tasks)==1 else f"{i}. {task['source_text']}\n\n{answer}")
    return {'answer':'\n\n'.join(sections)}
