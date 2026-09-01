"""Chat state graph; preserves existing intent, guide and report-answer policies."""
from typing import TypedDict,Any
from fastapi import HTTPException
from langgraph.graph import StateGraph,START,END
from app.tools.registry import ToolContext,tool_context
from app.workflow.chat_policy import (
    _parse_chat_id,
    _extract_question,
    _format_memory,
    _count_recent_smalltalk_turns,
    _classify_query,
    _answer_from_guide,
    _handle_guide_query,
    _handle_multi_report_query,
    _handle_report_query,
    _extract_region_info,
    _handle_report_explanation,
    _build_smalltalk_limit_reply,
    _handle_llm_query,
    _build_refusal_reply,
    MAX_SMALLTALK_TURNS,
    INTENT_REPORT,
    INTENT_GUIDE,
    INTENT_GREETING,
    INTENT_SMALLTALK,
    INTENT_SAFETY,
    is_db_available,
    resolve_chat_internal_id,
    get_chat,
    get_recent_user_questions,
    get_latest_report_assets,
    add_chat_message,
    update_chat_title,
    get_active_report_payloads_for_chat,
    get_latest_report_region_info
)

class ChatState(TypedDict,total=False):
    payload: dict
    form_data: Any
    current_user: dict
    chat_id: int
    chat: dict
    chat_type: str
    new_question: str
    memory: str
    smalltalk_used: int
    remaining_smalltalk: int
    intent: str
    allowed: bool
    reason: str
    report_assets: dict
    guide_answer: str | None
    reply: str


def load_context(s):
    chat_ref = _parse_chat_id(s['payload'], s.get('form_data'))
    if chat_ref is None:
        raise HTTPException(400, "chat_id is required")
    if not is_db_available():
        raise HTTPException(500, "Database is not configured")
    chat_id = resolve_chat_internal_id(chat_ref)
    chat = get_chat(chat_id) if chat_id is not None else None
    if not chat or chat.get("user_id") != s['current_user']['user_id']:
        raise HTTPException(404, "Chat not found")
    message, questions = _extract_question(s['payload'], s.get('form_data'))
    question = questions[-1] if message is None and questions else message
    if not question:
        raise HTTPException(400, "Question is required")
    used = _count_recent_smalltalk_turns(chat_id)
    return {'chat_id': chat_id, 'chat': chat, 'chat_type': chat.get('chat_type') or 'report',
            'new_question': question, 'memory': _format_memory(get_recent_user_questions(chat_id, limit=20)),
            'smalltalk_used': used, 'remaining_smalltalk': max(0, MAX_SMALLTALK_TURNS-used)}


def classify(s):
    intent, allowed, reason = _classify_query(s['memory'], s['new_question'], s['remaining_smalltalk'])
    assets = (get_latest_report_assets(s['chat_id']) or {}) if s['chat_type'] != 'bot' else {}
    guide = _answer_from_guide(s['new_question'])
    if intent != INTENT_REPORT and guide:
        intent, allowed, reason = INTENT_GUIDE, True, "guide_match"
    return {'intent': intent, 'allowed': allowed, 'reason': reason, 'report_assets': assets, 'guide_answer': guide}


def persist_user(s):
    add_chat_message(s['chat_id'], "user", s['new_question'], user_id=s['current_user']['user_id'],
                     meta={k: s[k] for k in ('intent', 'allowed', 'reason')})
    if not s['chat'].get('title') or s['chat']['title'] == 'New Chat':
        update_chat_title(s['chat_id'], s['new_question'].strip()[:48])
    return {}


def route_answer(s):
    if s['intent'] == INTENT_GUIDE:
        return 'guide'
    if s['intent'] == INTENT_REPORT:
        return 'multi_report' if s['chat_type'] == 'bot' else 'report'
    if s['intent'] in (INTENT_GREETING, INTENT_SMALLTALK) and s['allowed']:
        return 'smalltalk'
    if s['intent'] == INTENT_SAFETY and s['allowed']:
        return 'safety'
    return 'refusal'


def guide(s):
    return {'reply': _handle_guide_query(s['new_question'], s['guide_answer'] or "")}


def multi_report(s):
    reports = get_active_report_payloads_for_chat(s['chat_id'])
    if reports:
        payloads = [{k: report.get(k) for k in ('report_id', 'source_chat_id', 'report_json', 'region_info')}
                    for report in reports]
        reply = _handle_multi_report_query(s['new_question'], payloads)
    else:
        reply = ("I don't see any reports attached to this chatbot session. "
                 "Please attach at least one report to compare or analyze.")
    return {'reply': reply}


def report(s):
    region_info = get_latest_report_region_info(s['chat_id'])
    if not region_info:
        region_info = _extract_region_info(s['payload'], s.get('form_data'))
    report_json = s['report_assets'].get('report_json')
    if isinstance(report_json, dict) and report_json:
        reply = _handle_report_query(s['new_question'], report_json)
    elif region_info:
        reply = _handle_report_explanation(s['new_question'], region_info)
    else:
        reply = ("I don't see a report for this chat yet. "
                 "Please run a video analysis first, then ask about the report.")
    return {'reply': reply}


def safety(s):
    return {'reply': _handle_llm_query(s['memory'], s['new_question'], s['smalltalk_used'])}


def smalltalk(s):
    if s['remaining_smalltalk'] <= 0:
        return {'reply': _build_smalltalk_limit_reply()}
    return safety(s)


def refusal(s):
    return {'reply': _build_refusal_reply(s['new_question'])}


def persist_answer(s):
    add_chat_message(s['chat_id'], "assistant", s['reply'], user_id=s['current_user']['user_id'])
    return {}


def build_chat_graph():
    graph = StateGraph(ChatState)
    def scoped(fn):
        def run(state):
            with tool_context(ToolContext(state['current_user']['user_id'], state.get('chat_id'))):
                return fn(state)
        return run
    branches = ['guide', 'report', 'multi_report', 'smalltalk', 'safety', 'refusal']
    for name in ['load_context', 'classify', 'persist_user', *branches, 'persist_answer']:
        graph.add_node(name, scoped(globals()[name]))
    graph.add_edge(START, 'load_context')
    graph.add_edge('load_context', 'classify')
    graph.add_edge('classify', 'persist_user')
    graph.add_conditional_edges('persist_user', route_answer, {name: name for name in branches})
    for name in branches:
        graph.add_edge(name, 'persist_answer')
    graph.add_edge('persist_answer', END)
    return graph.compile()


def process_chat(payload, form_data, current_user):
    state = build_chat_graph().invoke({'payload': payload, 'form_data': form_data,
                                     'current_user': {'user_id': current_user['user_id']}})
    return {'reply': state['reply']}
