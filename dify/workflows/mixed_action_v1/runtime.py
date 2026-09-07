"""Pure functions embedded into Dify Code nodes. No network or persistence."""
import json
import re


def single_plan(query: str, kind: str) -> dict:
    p = dict(origin='single', knowledge_query='', record_query='', action_query='',
             dependency='none', condition_property='', condition_id='', condition_status='')
    p[kind + '_query'] = query
    return {'plan': json.dumps(p, ensure_ascii=False)}


def validate_plan(plan_json: str, extract_success: float, original: str) -> dict:
    def stop(message):
        return {'decision': 'stop', 'message': message, 'plan': '{}'}
    if extract_success != 1:
        return stop('请求拆分失败，未执行任何子任务。请补充完整问题后重试。')
    try:
        p = json.loads(plan_json)
    except (TypeError, ValueError):
        return stop('请求计划格式无效，未执行任何子任务。')
    if not isinstance(p, dict):
        return stop('请求计划格式无效，未执行任何子任务。')
    keys = ['knowledge_query', 'record_query', 'action_query', 'dependency',
            'condition_property', 'condition_id', 'condition_status']
    if any(not isinstance(p.get(k), str) for k in keys):
        return stop('请求计划字段不完整，未执行任何子任务。')
    p = {k: p[k].strip() for k in keys} | {'origin': 'mixed'}
    if sum(bool(p[k]) for k in keys[:3]) < 2:
        return stop('无法拆成不同类型的子任务，请分别说明查询、咨询或操作需求。')
    # The planner also supplies hard task counts; never silently discard extra tasks.
    raw = json.loads(plan_json)
    counts = raw.get('task_counts')
    if not isinstance(counts, dict) or any(type(counts.get(k)) is not int for k in ('knowledge','record','action')):
        return stop('子任务数量不明确，请拆分后重试。')
    if any(counts[k] != int(bool(p[k+'_query'])) for k in counts if k in ('knowledge','record','action')):
        return stop('本版本每次最多一项知识咨询、一项记录查询和一项操作；未执行，请拆分。')
    if raw.get('coverage') != 'complete':
        return stop('请求含有无法完整保留的条件或任务，未执行，请拆分或补充说明。')
    if p['dependency'] not in ('none','after_query','maintenance_status','manual'):
        return stop('无法识别操作依赖条件，未执行任何子任务。')
    if p['dependency'] in ('after_query','maintenance_status') and not (p['record_query'] and p['action_query']):
        return stop('操作依赖缺少前置查询，未执行任何子任务。')
    if not p['action_query'] and p['dependency'] != 'none':
        return stop('请求的依赖关系不完整，未执行任何子任务。')
    original_upper = original.upper()
    # Prevent invented IDs in rewritten sub-questions; arbitrary unknown IDs are retained and denied downstream.
    for text in [p[k] for k in keys[:3]]:
        for ref in re.findall(r'\b[A-Z]{2,10}-\d+(?:-\d+)?\b', text.upper()):
            if ref not in original_upper:
                return stop('拆分结果新增了原问题没有的对象编号，请明确目标后重试。')
    for key in ('condition_property','condition_id'):
        p[key] = p[key].upper()
        if p[key] and p[key] not in original_upper:
            return stop('条件目标未在原问题中明确提供，请补充目标编号。')
    # A conservative backstop, not a general natural-language policy engine.
    if p['action_query'] and p['dependency'] == 'none' and re.search(
        r'如果|假如|只有|否则|符合.*(?:才|就)|依据.*(?:创建|提交|关闭)|\b(if|unless|provided)\b', original, re.I
    ):
        p['dependency'] = 'manual'
    if p['dependency'] == 'maintenance_status' and (
        not p['condition_property'] or p['condition_status'] not in ('open','in_progress','resolved','closed')
    ):
        p['dependency'] = 'manual'
    return {'decision':'allow','message':'计划有效。','plan':json.dumps(p,ensure_ascii=False)}


def expand_context(plan: str, staff_context: str) -> dict:
    p = json.loads(plan)
    staff = json.loads(staff_context)
    # Explicit prototype access policy for the existing EMP common library only.
    kb_readers = {'staff_amy','staff_ben','staff_chloe','staff_david'}
    kb_allowed = staff.get('staff_id') in kb_readers
    return {'plan': plan, 'origin':p['origin'], 'knowledge_query':p['knowledge_query'],
            'record_query':p['record_query'], 'action_query':p['action_query'],
            'has_knowledge':bool(p['knowledge_query']) and kb_allowed,
            'has_record':bool(p['record_query']), 'kb_allowed':kb_allowed}


def pack_result(text: str, raw: str, kind: str, fallback: str) -> dict:
    data = {}
    if raw:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            data = {'status':'error','message':'工具结果格式无效。'}
    if not isinstance(data, dict):
        data = {'status':'error','message':'工具结果格式无效。'}
    status = data.get('status', fallback)
    status = {'forbidden':'denied','deny':'denied'}.get(status,status)
    if status == 'ok':
        for key in ('items','properties','leases','rent_records'):
            if key in data and isinstance(data[key],list) and not data[key]:
                status = 'empty'
    return {'result':json.dumps({'kind':kind,'status':status,'text':text,'data':data,
                                'executed':False},ensure_ascii=False)}


def action_gate(plan: str, record_result: str) -> dict:
    p = json.loads(plan)
    r = json.loads(record_result)
    def out(allow, status, message, bound=''):
        return {'allow':allow, 'bound_property':bound,
                'result':json.dumps({'kind':'action','status':status,'text':message,
                                     'data':{},'executed':False},ensure_ascii=False)}
    if not p['action_query']:
        return out(False,'skipped','')
    dep = p['dependency']
    if dep == 'none':
        return out(True,'pending','')
    if dep == 'manual':
        return out(False,'needs_review','操作条件需要人工确认；未创建草稿、修改记录或提交审批。')
    if r['status'] != 'ok':
        return out(False,'dependency_failed','前置查询未成功或无匹配记录，依赖该查询的操作未执行。')
    # Cross-task automatic dependency evaluation is limited to exact maintenance records.
    data = r.get('data',{})
    if data.get('tool') != 'search_maintenance':
        return out(False,'needs_review','当前仅支持根据维修工单原始状态自动判断操作条件；本次操作未执行。')
    items = data.get('items',[])
    if p['condition_id']:
        items = [x for x in items if x.get('maintenance_id') == p['condition_id']]
    if len(items) != 1 or not p['condition_property'] or items[0].get('property_reference') != p['condition_property']:
        return out(False,'needs_input','前置结果未唯一定位到指定房源的工单，操作未执行。')
    if dep == 'maintenance_status' and items[0].get('status') != p['condition_status']:
        return out(False,'condition_not_met','原始工单状态不满足指定条件，操作未执行。')
    return out(True,'pending','',p['condition_property'])


def collect_final(plan: str, knowledge_result: str, record_result: str, action_result: str) -> dict:
    p = json.loads(plan)
    results = [json.loads(v) for v in (knowledge_result,record_result,action_result)]
    active = [r for r in results if r['status'] != 'skipped']
    labels = {'knowledge':'政策说明','record':'记录查询','action':'操作结果'}
    if p['origin'] == 'single':
        answer = active[0]['text'] if active else '本次未产生结果。'
    else:
        answer = '\n\n'.join(labels[r['kind']]+'\n'+r['text'] for r in active)
        answer += '\n\n本次业务记录及草稿来自 Mock 验证；未写入业务系统、未派单、未提交审批。'
    return {'answer':answer,'task_results':json.dumps(active,ensure_ascii=False),'request_origin':p['origin']}


def maintenance_authorize(staff_context: str, property_reference: str, action: str) -> dict:
    try:
        s=json.loads(staff_context)
    except (TypeError,ValueError):
        s={}
    if not isinstance(s,dict): s={}
    allowed=s.get('managed_properties',[])
    permissions=s.get('permissions',[])
    valid=isinstance(allowed,list) and all(isinstance(x,str) for x in allowed) and isinstance(permissions,list)
    target=(property_reference or '').strip().upper()
    ok=bool(valid and s.get('staff_id') and 'maintenance:read' in permissions and action=='search'
            and (not target or target in allowed))
    return {'is_authorized':ok,'safe_scope':'、'.join(allowed) if valid else '',
            'authorization_message':'允许在授权房源范围查询维修记录。' if ok else '维修读取权限、查询类型或目标范围校验未通过。'}


def maintenance_mock(staff_context: str, action: str, property_reference: str,
                     priority: str, status: str, maintenance_id: str) -> dict:
    def out(status_value, message, items=None):
        return {'tool_result':json.dumps({'tool':'search_maintenance','status':status_value,'message':message,
                                          'items':items or [],'source':'mock'},ensure_ascii=False),
                'audit_id':'mock-maintenance-read-only'}
    try: s=json.loads(staff_context)
    except (TypeError,ValueError): s={}
    if not isinstance(s,dict): s={}
    allowed=s.get('managed_properties',[])
    permissions=s.get('permissions',[])
    if (not s.get('staff_id') or not isinstance(allowed,list) or not all(isinstance(x,str) for x in allowed)
        or not isinstance(permissions,list) or 'maintenance:read' not in permissions or action!='search'):
        return out('forbidden','维修读取权限或操作类型校验未通过。')
    target=(property_reference or '').strip().upper()
    ticket=(maintenance_id or '').strip().upper()
    if target and target not in allowed: return out('forbidden','目标不在授权范围。')
    if priority and priority not in ('low','medium','high','urgent'): return out('invalid_request','优先级无效。')
    if status and status not in ('open','in_progress','resolved','closed'): return out('invalid_request','状态无效。')
    rows=[{'maintenance_id':'MAINT-HV102-01','property_reference':'HV-102','priority':'high',
           'status':'in_progress','summary':'Bathroom ceiling water stain'},
          {'maintenance_id':'MAINT-PA201-01','property_reference':'PA-201','priority':'medium',
           'status':'open','summary':'Bedroom blind repair'}]
    items=[x for x in rows if x['property_reference'] in allowed and (not target or x['property_reference']==target)
           and (not ticket or x['maintenance_id']==ticket) and (not priority or x['priority']==priority)
           and (not status or x['status']==status)]
    return out('ok','仅返回 Mock 当前状态，未提供预计完成时间。',items)
