import json
from app.settings import get_settings
import random
import re
import time
from typing import Any, Dict, Optional, Tuple

from app.llm import complete_sync
from app.tools.registry import current_tool_context
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.db import (
    add_chat_message,
    get_chat,
    get_active_report_payloads_for_chat,
    get_latest_report_assets,
    get_latest_report_region_info,
    get_recent_chat_messages,
    get_recent_user_questions,
    is_db_available,
    resolve_chat_internal_id,
    update_chat_title,
)
from app.auth import require_user
from app.prompts.chat_prompts import build_classifier_prompt, build_chat_system_prompt
from app.localization import llm_language_directive
from app.llm_registry import get_generation_params, get_model_name
from app.knowledge.guide import search_guide



MAX_SMALLTALK_TURNS = 3
INTENT_SAFETY = "SAFETY"
INTENT_REPORT = "REPORT_EXPLANATION"
INTENT_GUIDE = "GUIDE"
INTENT_GREETING = "GREETING"
INTENT_SMALLTALK = "SMALLTALK"
INTENT_OTHER = "OTHER"
INTENT_FALLBACK = "UNKNOWN"
INTENT_ALIASES = {
    "REPORT": INTENT_REPORT,
    "REPORT_EXPLAIN": INTENT_REPORT,
    "REPORT_EXPLAINER": INTENT_REPORT,
    "GREETING_SMALLTALK": INTENT_SMALLTALK,
    "SMALL_TALK": INTENT_SMALLTALK,
    "CHITCHAT": INTENT_SMALLTALK,
}
ALLOWED_INTENTS = {
    INTENT_SAFETY,
    INTENT_REPORT,
    INTENT_GUIDE,
    INTENT_GREETING,
    INTENT_SMALLTALK,
    INTENT_OTHER,
}


def _safe_parse_json(text: str) -> Optional[Dict[str, Any]]:
    if not text or not isinstance(text, str):
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None


def _normalize_intent(value: Optional[str]) -> str:
    if not value or not isinstance(value, str):
        return INTENT_FALLBACK
    normalized = value.strip().upper()
    if normalized in INTENT_ALIASES:
        return INTENT_ALIASES[normalized]
    if normalized in ALLOWED_INTENTS:
        return normalized
    return INTENT_FALLBACK


def _count_recent_smalltalk_turns(chat_id: int, limit: int = 30) -> int:
    messages = get_recent_chat_messages(chat_id, limit=limit) or []
    count = 0
    for message in messages:
        if message.get("role") != "user":
            continue
        meta_raw = message.get("meta")
        meta: Optional[Dict[str, Any]] = None
        if isinstance(meta_raw, dict):
            meta = meta_raw
        elif isinstance(meta_raw, str) and meta_raw.strip():
            meta = _safe_parse_json(meta_raw)
        if not meta:
            continue
        intent = _normalize_intent(meta.get("intent"))
        if intent in (INTENT_GREETING, INTENT_SMALLTALK) and meta.get("allowed") is True:
            count += 1
    return count


def _parse_chat_id(payload, form_data):
    value = None
    if isinstance(payload, dict):
        value = payload.get("chat_id")
    if value is None and form_data is not None:
        value = form_data.get("chat_id")
    if value is None or value == "":
        return None
    return str(value).strip() or None


def _format_memory(questions):
    if not questions:
        return "暂无问题"
    return "\n".join([f"Q{idx + 1}: {question}" for idx, question in enumerate(questions)])


def _build_classifier_prompt(memory: str, remaining_smalltalk: int) -> str:
    return build_classifier_prompt(memory, remaining_smalltalk)


def _answer_from_guide(user_query: str) -> Optional[str]:
    if not isinstance(user_query, str) or not user_query.strip():
        return None
    matches = search_guide(user_query, top_k=3)
    if not matches:
        return None
    best_score = matches[0][1]
    if best_score < 0.6:
        return None
    parts = []
    for section, _score in matches:
        title = section.get("title") or "快速指南"
        summary = (section.get("summary") or "").strip()
        items = section.get("items") if isinstance(section.get("items"), list) else []
        steps = section.get("steps") if isinstance(section.get("steps"), list) else []
        payload = [summary]
        payload.extend([str(item) for item in items if str(item).strip()])
        payload.extend([f"步骤：{step}" for step in steps if str(step).strip()])
        content = "\n".join([line for line in payload if line]).strip()
        if not content:
            continue
        parts.append(f"{title}\n{content}")
    if not parts:
        return None
    return "\n\n".join(parts[:2]).strip()


def _handle_guide_query(user_query: str, guide_answer: str) -> str:
    system_prompt = (
        "你是 Safe-Scan 产品支持助手。只能依据提供的指南内容回答用户问题。"
        "所有回答遵循末尾的强制输出语言要求；适合时提供简洁、具体的步骤。"
        "如果指南未涵盖该问题，请如实说明并提出一个澄清问题。"
        f"{llm_language_directive()}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"用户问题：{user_query}\n\n指南内容：\n{guide_answer}",
        },
    ]
    params = get_generation_params("L2")
    model = get_model_name("L2")
    response, error = _call_model_with_retry(
        messages,
        model=model,
        temperature=params["temperature"],
        top_p=params["top_p"],
    )
    if response:
        return response
    return guide_answer


def _handle_report_query(user_query: str, report_json: Dict[str, Any]) -> str:
    system_prompt = (
        "你是 Safe-Scan 家居安全报告分析助手。只能依据提供的报告数据回答用户问题，不得虚构细节。"
        "如果报告不包含所需信息，请明确说明并提出澄清问题。"
        f"{llm_language_directive()}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"用户问题：{user_query}\n\n报告 JSON：\n{json.dumps(report_json, ensure_ascii=False)}",
        },
    ]
    params = get_generation_params("L2")
    model = get_model_name("L2")
    response, error = _call_model_with_retry(
        messages,
        model=model,
        temperature=params["temperature"],
        top_p=params["top_p"],
    )
    if response:
        return response
    return "暂时无法读取报告详情，请稍后重试。"


def _handle_multi_report_query(user_query: str, reports: list) -> str:
    system_prompt = (
        "你是 Safe-Scan 家居安全报告分析助手。你会收到来自不同分析会话的多份安全报告。"
        "必须严格依据报告数据进行对比和评估，不得虚构细节。"
        "如果某份报告缺少所需信息，请明确说明并聚焦现有内容。"
        f"{llm_language_directive()}"
    )
    payload = json.dumps(reports, ensure_ascii=False)
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"用户问题：{user_query}\n\n报告 JSON：\n{payload}",
        },
    ]
    params = get_generation_params("L2")
    model = get_model_name("L2")
    response, error = _call_model_with_retry(
        messages,
        model=model,
        temperature=params["temperature"],
        top_p=params["top_p"],
    )
    if response:
        return response
    return "暂时无法读取报告详情，请稍后重试。"


def _classify_query(memory: str, new_question: str, remaining_smalltalk: int) -> Tuple[str, bool, str]:
    system_prompt = _build_classifier_prompt(memory, remaining_smalltalk)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": new_question},
    ]
    params = get_generation_params("L1")
    model = get_model_name("L1")
    response, error = _call_model_with_retry(
        messages,
        model=model,
        temperature=params["temperature"],
        top_p=params["top_p"],
    )
    if not response:
        return INTENT_OTHER, False, f"classifier_error:{error}"
    content = response.strip()
    parsed = _safe_parse_json(content)
    if not parsed:
        return INTENT_OTHER, False, "classifier_invalid_json"

    intent = _normalize_intent(parsed.get("intent"))
    allowed = parsed.get("allowed")
    reason = parsed.get("reason")

    if intent not in ALLOWED_INTENTS:
        intent = INTENT_OTHER
    if not isinstance(reason, str) or not reason:
        reason = "classifier_default"
    if not isinstance(allowed, bool):
        if intent in (INTENT_SAFETY, INTENT_REPORT):
            allowed = True
        elif intent in (INTENT_GREETING, INTENT_SMALLTALK):
            allowed = remaining_smalltalk > 0
        else:
            allowed = False

    if intent in (INTENT_GREETING, INTENT_SMALLTALK) and remaining_smalltalk <= 0:
        allowed = False
        reason = "smalltalk_limit_reached"

    if intent == INTENT_OTHER:
        allowed = False
    return intent, allowed, reason


def _extract_region_info(payload, form_data):
    if payload and isinstance(payload.get("regionInfo"), list):
        return payload.get("regionInfo", [])
    if payload and isinstance(payload.get("regionInfo"), str):
        try:
            parsed = json.loads(payload.get("regionInfo", "[]"))
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    if form_data is None:
        return []
    region_info_str = form_data.get("regionInfo", "[]")
    try:
        parsed = json.loads(region_info_str)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def _extract_question(payload, form_data):
    if isinstance(payload, dict):
        if isinstance(payload.get("message"), str):
            return payload.get("message"), None
        if isinstance(payload.get("question"), str):
            return payload.get("question"), None
        questions_payload = payload.get("user_input", payload)
    else:
        if form_data is not None:
            if isinstance(form_data.get("message"), str):
                return form_data.get("message"), None
            if isinstance(form_data.get("question"), str):
                return form_data.get("question"), None
        questions_payload = form_data.get("user_input") if form_data is not None else None

    if isinstance(questions_payload, str):
        try:
            questions_dict = json.loads(questions_payload)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid user_input format")
    elif isinstance(questions_payload, dict):
        questions_dict = questions_payload
    else:
        raise HTTPException(status_code=400, detail="Invalid user_input format")

    if (
        "questions" in questions_dict
        and isinstance(questions_dict["questions"], list)
        and questions_dict["questions"]
    ):
        return None, questions_dict["questions"]

    raise HTTPException(
        status_code=400,
        detail="'questions' key is missing or not a list or empty",
    )



def _handle_report_explanation(user_query: str, region_info: list) -> str:
    if not region_info:
        return (
            "我可以帮助解读安全报告，但需要先获取报告数据。"
            f"你刚才的问题是：“{user_query}”。"
        )

    query_lower = user_query.lower()
    for region in region_info:
        region_name = "未知区域"
        if isinstance(region.get("regionName"), list) and region.get("regionName"):
            region_name = region.get("regionName")[0]
        elif isinstance(region.get("regionName"), str):
            region_name = region.get("regionName")

        if region_name and region_name.lower() in query_lower:
            hazards = region.get("potentialHazards", [])
            suggestions = region.get("suggestions", [])
            explanation = f"关于{region_name}：\n"
            if hazards:
                explanation += f"潜在隐患：{'、'.join(hazards[:2])}……\n"
            if suggestions:
                explanation += f"改进建议：{'、'.join(suggestions[:2])}……\n"
            return explanation

    return (
        f"关于“{user_query}”，报告会按区域分析居住环境、识别风险并给出改进建议。"
    )


def _build_smalltalk_limit_reply() -> str:
    return (
        "我很乐意继续协助家居安全问题，不过本次对话的闲聊轮数已经用完。"
        "你想了解哪方面的家居安全或室内环境问题？"
    )


def _build_refusal_reply(user_query: str) -> str:
    return (
        "抱歉，我只能回答与家居安全或室内环境相关的问题。"
        f"你刚才的问题是：“{user_query}”。"
    )


def _handle_llm_query(memory: str, new_question: str, smalltalk_turns_used: int) -> str:
    system_prompt = _build_system_prompt(memory, smalltalk_turns_used)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": new_question},
    ]

    params = get_generation_params("L2")
    model = get_model_name("L2")
    response, error = _call_model_with_retry(
        messages,
        model=model,
        temperature=params["temperature"],
        top_p=params["top_p"],
    )
    if response:
        return response
    return f"暂时无法回答，请稍后重试。错误信息：{error}"


def _call_model_with_retry(messages, model: str, temperature: float, top_p: float):
    tier=next((t for t in ('L1','L2','L3','VL') if get_generation_params(t)=={'temperature':temperature,'top_p':top_p}), 'L2')
    last_error=None
    for attempt in range(3):
        try:
            result=complete_sync(messages,tier,allowed_tools=() if tier=='L1' else ('search_guide','read_report'),context=current_tool_context())
            return result,None
        except Exception:
            last_error='model_request_failed'
        if attempt<2:
            time.sleep(.8*(2**attempt)+random.uniform(0,.2))
    return None,last_error


def _build_system_prompt(memory: str, smalltalk_turns_used: int) -> str:
    return build_chat_system_prompt(memory, smalltalk_turns_used, MAX_SMALLTALK_TURNS)
