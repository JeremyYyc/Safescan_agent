import json
import re

def main(raw_text: str, original: str) -> dict:
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
