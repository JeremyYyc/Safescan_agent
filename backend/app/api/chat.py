import json
import os
import random
import re
import time
from typing import Any, Dict, Optional, Tuple

import dashscope
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.env import load_env
from app.db import (
    add_chat_message,
    get_chat,
    get_latest_report_region_info,
    get_recent_chat_messages,
    get_recent_user_questions,
    is_db_available,
    update_chat_title,
)
from app.auth import require_user
from app.prompts.chat_prompts import build_classifier_prompt, build_chat_system_prompt

load_env()
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")

router = APIRouter()

MAX_SMALLTALK_TURNS = 3
INTENT_SAFETY = "SAFETY"
INTENT_REPORT = "REPORT_EXPLANATION"
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
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_memory(questions):
    if not questions:
        return "NO QUESTIONS"
    return "\n".join([f"Q{idx + 1}: {question}" for idx, question in enumerate(questions)])


def _build_classifier_prompt(memory: str, remaining_smalltalk: int) -> str:
    return build_classifier_prompt(memory, remaining_smalltalk)


def _classify_query(memory: str, new_question: str, remaining_smalltalk: int) -> Tuple[str, bool, str]:
    system_prompt = _build_classifier_prompt(memory, remaining_smalltalk)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": new_question},
    ]
    response, error = _call_dashscope_with_retry(messages, temperature=0.2, top_p=0.2)
    if not response:
        return INTENT_OTHER, False, f"classifier_error:{error}"
    content = response.output.choices[0].message.content.strip()
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


@router.post("/processChat")
async def process_chat(
    request: Request, current_user: Dict[str, Any] = Depends(require_user)
) -> JSONResponse:
    try:
        payload = None
        form_data = None
        if request.headers.get("content-type", "").startswith("application/json"):
            try:
                payload = await request.json()
            except Exception:
                payload = None

        if not isinstance(payload, dict):
            form_data = await request.form()

        chat_id = _parse_chat_id(payload, form_data)
        if chat_id is None:
            raise HTTPException(status_code=400, detail="chat_id is required")
        if not is_db_available():
            raise HTTPException(status_code=500, detail="Database is not configured")
        chat = get_chat(chat_id)
        if not chat or chat.get("user_id") != current_user.get("user_id"):
            raise HTTPException(status_code=404, detail="Chat not found")

        message, questions = _extract_question(payload, form_data)
        if message is None and questions:
            new_question = questions[-1]
        else:
            new_question = message

        if not new_question:
            raise HTTPException(status_code=400, detail="Question is required")

        previous_questions = get_recent_user_questions(chat_id, limit=20)
        memory = _format_memory(previous_questions)
        smalltalk_used = _count_recent_smalltalk_turns(chat_id)
        remaining_smalltalk = max(0, MAX_SMALLTALK_TURNS - smalltalk_used)
        intent, allowed, reason = _classify_query(memory, new_question, remaining_smalltalk)

        add_chat_message(
            chat_id,
            "user",
            new_question,
            user_id=current_user.get("user_id"),
            meta={"intent": intent, "allowed": allowed, "reason": reason},
        )
        if chat and (not chat.get("title") or chat.get("title") == "New Chat"):
            update_chat_title(chat_id, new_question.strip()[:48])

        if intent == INTENT_REPORT:
            region_info = get_latest_report_region_info(chat_id)
            if not region_info:
                region_info = _extract_region_info(payload, form_data)
            reply = _handle_report_explanation(new_question, region_info)
        elif intent in (INTENT_GREETING, INTENT_SMALLTALK) and allowed:
            if remaining_smalltalk <= 0:
                reply = _build_smalltalk_limit_reply()
            else:
                reply = _handle_llm_query(memory, new_question, smalltalk_used)
        elif intent == INTENT_SAFETY and allowed:
            reply = _handle_llm_query(memory, new_question, smalltalk_used)
        else:
            reply = _build_refusal_reply(new_question)

        add_chat_message(
            chat_id,
            "assistant",
            reply,
            user_id=current_user.get("user_id"),
        )

        return JSONResponse({"reply": reply})
    except HTTPException as exc:
        raise exc
    except Exception as exc:
        return JSONResponse({"error": f"Chat processing failed: {str(exc)}"}, status_code=500)


def _handle_report_explanation(user_query: str, region_info: list) -> str:
    if not region_info:
        return (
            "I can help explain your safety report, but I need the report data first. "
            f"Your question was: '{user_query}'."
        )

    query_lower = user_query.lower()
    for region in region_info:
        region_name = "Unknown Region"
        if isinstance(region.get("regionName"), list) and region.get("regionName"):
            region_name = region.get("regionName")[0]
        elif isinstance(region.get("regionName"), str):
            region_name = region.get("regionName")

        if region_name and region_name.lower() in query_lower:
            hazards = region.get("potentialHazards", [])
            suggestions = region.get("suggestions", [])
            explanation = f"About {region_name}:\n"
            if hazards:
                explanation += f"Potential hazards: {', '.join(hazards[:2])}...\n"
            if suggestions:
                explanation += f"Suggestions: {', '.join(suggestions[:2])}...\n"
            return explanation

    return (
        f"For your question '{user_query}', the report generally analyzes each area, "
        "identifies risks, and offers improvements."
    )


def _build_smalltalk_limit_reply() -> str:
    return (
        "I'm happy to help with home safety, but I've already handled a few rounds of small talk. "
        "What home safety or indoor environment question can I help with?"
    )


def _build_refusal_reply(user_query: str) -> str:
    return (
        "Sorry, I can only answer questions related to home safety or indoor environments. "
        f"Your question was: '{user_query}'."
    )


def _handle_llm_query(memory: str, new_question: str, smalltalk_turns_used: int) -> str:
    system_prompt = _build_system_prompt(memory, smalltalk_turns_used)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": new_question},
    ]

    response, error = _call_dashscope_with_retry(messages)
    if response:
        return response.output.choices[0].message.content
    return f"Unable to answer right now: {error}"


def _call_dashscope_with_retry(messages, temperature: float = 0.7, top_p: float = 0.8):
    from http import HTTPStatus

    max_retries = 3
    base_delay = 0.8
    last_error = None

    for attempt in range(max_retries):
        try:
            response = dashscope.Generation.call(
                model=os.getenv("ALIBABA_TEXT_MODEL") or os.getenv("ALIBABA_MODEL", "qwen-plus"),
                messages=messages,
                result_format="message",
                top_p=top_p,
                temperature=temperature,
            )
            if response.status_code == HTTPStatus.OK:
                return response, None
            last_error = f"{response.code}, {response.message}"
        except Exception as exc:
            last_error = str(exc)

        if attempt < max_retries - 1:
            time.sleep(base_delay * (2 ** attempt) + random.uniform(0, 0.2))

    return None, last_error


def _build_system_prompt(memory: str, smalltalk_turns_used: int) -> str:
    return build_chat_system_prompt(memory, smalltalk_turns_used, MAX_SMALLTALK_TURNS)
