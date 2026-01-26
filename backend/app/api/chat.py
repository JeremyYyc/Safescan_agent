import json
import os
from typing import Any, Dict

import dashscope
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.env import load_env
from app.db import (
    add_chat_message,
    get_chat,
    get_latest_report_region_info,
    get_recent_user_questions,
    is_db_available,
    update_chat_title,
)
from app.auth import require_user

load_env()
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")

router = APIRouter()


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
        add_chat_message(
            chat_id,
            "user",
            new_question,
            user_id=current_user.get("user_id"),
        )
        if chat and (not chat.get("title") or chat.get("title") == "New Chat"):
            update_chat_title(chat_id, new_question.strip()[:48])

        query_category = _simple_route_query(new_question)

        if query_category == "REPORT_EXPLANATION":
            region_info = get_latest_report_region_info(chat_id)
            if not region_info:
                region_info = _extract_region_info(payload, form_data)
            reply = _handle_report_explanation(new_question, region_info)
        else:
            reply = _handle_general_safety_query(memory, new_question)

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


def _simple_route_query(question: str) -> str:
    question_lower = question.lower()
    report_keywords = ["report", "explain", "details", "meaning", "summary"]
    if any(keyword in question_lower for keyword in report_keywords):
        return "REPORT_EXPLANATION"
    return "GENERAL_SAFETY"


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


def _handle_general_safety_query(memory: str, new_question: str) -> str:
    if not _is_home_safety_question(new_question):
        return (
            "Sorry, I can only answer questions related to home safety or indoor environments."
        )

    system_prompt = _build_system_prompt(memory)

    try:
        from http import HTTPStatus

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": new_question},
        ]

        response = dashscope.Generation.call(
            model=os.getenv("ALIBABA_TEXT_MODEL") or os.getenv("ALIBABA_MODEL", "qwen-plus"),
            messages=messages,
            result_format="message",
            top_p=0.8,
            temperature=0.7,
        )

        if response.status_code == HTTPStatus.OK:
            return response.output.choices[0].message.content
        return f"Unable to answer right now: {response.code}, {response.message}"
    except Exception as exc:
        return f"Error while processing your question: {str(exc)}"


def _build_system_prompt(memory: str) -> str:
    prompt = f"""You are a chatbot in a home safety analysis app. Based on the user's previous questions (if 'NO QUESTIONS' are shown, it is their first question), answer their new question. Please avoid making the response too lengthy or too summarized. Your primary tasks are to:
1. If the user asks how to address personal safety hazards or mental health issues, provide solutions from different perspectives (e.g., simple methods, cost-effective options, etc.).
2. Help tenants identify potential personal safety/mental health issues in their homes.
3. Provide safety guidelines for emergency situations, such as responding to fires and other unexpected incidents, and offer corresponding prevention advice.
4. Provide suggestions for maintaining a safe and comfortable indoor environment.
5. Explain why indoor lighting and color schemes affect mental health.
6. If the user identifies as belonging to any specific group, provide targeted safety suggestions accordingly.
7. Advise tenants on how to discuss personal safety/mental health or concerns with their landlords.
* Only answer questions related to home safety, indoor environment, or safety-related mental health. For other unrelated questions, politely decline to answer.

Previous user questions:
{memory}
    """
    return prompt.strip()


def _is_home_safety_question(question: str) -> bool:
    if not question:
        return False

    question_lower = question.lower()
    keywords = [
        "home",
        "house",
        "apartment",
        "tenant",
        "landlord",
        "room",
        "kitchen",
        "bathroom",
        "bedroom",
        "living room",
        "hallway",
        "stairs",
        "safety",
        "hazard",
        "risk",
        "fire",
        "smoke",
        "gas",
        "electrical",
        "lighting",
        "color",
        "ventilation",
        "indoor",
        "air quality",
        "mold",
        "slip",
        "fall",
        "emergency",
        "mental health",
    ]

    return any(k in question_lower for k in keywords)
