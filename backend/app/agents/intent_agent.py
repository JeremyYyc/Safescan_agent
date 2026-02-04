from __future__ import annotations

from typing import Any, Dict, Optional
import json

from app.agents.autogen_agent_base import AutoGenDashscopeAgent
from app.prompts.chat_prompts import build_intent_agent_system_prompt


class IntentRecognitionAgent(AutoGenDashscopeAgent):
    """LLM-first intent recognizer for chat routing."""

    def __init__(self) -> None:
        super().__init__(name="IntentRecognitionAgent", model_tier="L1")

    def classify_intent(
        self,
        *,
        user_query: str,
        memory: str,
        remaining_smalltalk: int,
        has_report: bool,
        guide_candidates: list[Dict[str, Any]] | None = None,
    ) -> Optional[Dict[str, Any]]:
        payload = {
            "user_query": user_query,
            "recent_user_questions": memory,
            "remaining_smalltalk": remaining_smalltalk,
            "has_report": has_report,
            "guide_candidates": guide_candidates or [],
        }
        try:
            response = self._call_llm(
                system_message=build_intent_agent_system_prompt(),
                user_content=json.dumps(payload, ensure_ascii=False),
                tier="L1",
                name_suffix="router",
            )
            parsed = self.parse_json_response(response)
            if not isinstance(parsed, dict):
                return None
            return self._normalize_result(parsed, user_query)
        except Exception:
            return None

    @staticmethod
    def _normalize_result(parsed: Dict[str, Any], fallback_question: str) -> Optional[Dict[str, Any]]:
        sub_queries_raw = parsed.get("sub_queries")
        if isinstance(sub_queries_raw, list) and sub_queries_raw:
            normalized_items = []
            for item in sub_queries_raw:
                if not isinstance(item, dict):
                    continue
                question = item.get("question")
                if not isinstance(question, str) or not question.strip():
                    question = fallback_question
                normalized_items.append(
                    {
                        "question": question.strip(),
                        "intent": item.get("intent"),
                        "reason": item.get("reason"),
                        "confidence": item.get("confidence"),
                        "allowed": item.get("allowed"),
                        "need_clarification": item.get("need_clarification"),
                        "clarification_question": item.get("clarification_question"),
                    }
                )
            if normalized_items:
                return {
                    "is_multi_intent": bool(parsed.get("is_multi_intent")) or len(normalized_items) > 1,
                    "sub_queries": normalized_items,
                }

        # Backward compatibility with single-intent schema.
        intent = parsed.get("intent")
        if intent is None:
            return None
        return {
            "is_multi_intent": False,
            "sub_queries": [
                {
                    "question": fallback_question,
                    "intent": intent,
                    "reason": parsed.get("reason"),
                    "confidence": parsed.get("confidence"),
                    "allowed": parsed.get("allowed"),
                    "need_clarification": parsed.get("need_clarification"),
                    "clarification_question": parsed.get("clarification_question"),
                }
            ],
        }
