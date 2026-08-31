from __future__ import annotations

import json
import re
from typing import Any, Dict, List


from app.agents.router_agent import RouterAgent
from app.llm_registry import get_generation_params, get_model_name



AGENT_ORDER = [
    "HazardAgent",
    "ComfortAgent",
    "ComplianceAgent",
    "ScoringAgent",
    "RecommendationAgent",
    "ReportWriterAgent",
]


def _format_user_attributes(attributes: Dict[str, Any]) -> str:
    if not attributes:
        return "No special user groups."
    mapping = {
        "isPregnant": "Pregnant",
        "isChildren": "Children",
        "isElderly": "Elderly",
        "isDisabled": "Disabled",
        "isAllergic": "Allergic",
        "isPets": "Pets",
    }
    active = [label for key, label in mapping.items() if attributes.get(key)]
    return ", ".join(active) + "." if active else "No special user groups."


def _parse_json_blob(text: str) -> Dict[str, Any] | List[Any] | None:
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
        match = re.search(r"\[.*\]", text, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
    return None


def _text_blob(region_evidence: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for item in region_evidence:
        label = str(item.get("region_label", "") or "")
        desc = str(item.get("description", "") or "")
        parts.append(label)
        parts.append(desc)
    return " ".join(parts).lower()


def _needs_comfort(region_evidence: List[Dict[str, Any]], user_attributes: Dict[str, Any]) -> bool:
    if any(user_attributes.values()):
        return True
    text = _text_blob(region_evidence)
    keywords = [
        "mold",
        "humidity",
        "ventilation",
        "air",
        "odor",
        "smell",
        "noise",
        "lighting",
        "light",
        "dark",
        "glare",
        "damp",
        "stuffy",
    ]
    return any(key in text for key in keywords)


def _needs_compliance(region_evidence: List[Dict[str, Any]]) -> bool:
    text = _text_blob(region_evidence)
    room_keywords = ["kitchen", "bathroom", "laundry", "garage"]
    safety_keywords = ["gas", "electrical", "fire", "smoke", "stairs", "balcony", "window"]
    return any(key in text for key in room_keywords + safety_keywords)


def _heuristic_plan(
    region_evidence: List[Dict[str, Any]],
    user_attributes: Dict[str, Any],
) -> List[str]:
    selected = ["HazardAgent"]
    if _needs_comfort(region_evidence, user_attributes):
        selected.append("ComfortAgent")
    if _needs_compliance(region_evidence):
        selected.append("ComplianceAgent")
    if region_evidence:
        selected.append("ScoringAgent")
        selected.append("RecommendationAgent")
    selected.append("ReportWriterAgent")
    return selected


def _normalize_plan(selected: List[str]) -> List[str]:
    ordered = [name for name in AGENT_ORDER if name in selected]
    if "HazardAgent" not in ordered:
        ordered.insert(0, "HazardAgent")
    if "ReportWriterAgent" not in ordered:
        ordered.append("ReportWriterAgent")
    if "RecommendationAgent" in ordered and "ScoringAgent" not in ordered:
        insert_at = ordered.index("RecommendationAgent")
        ordered.insert(insert_at, "ScoringAgent")
    return ordered


def _plan_agents(
    region_evidence: List[Dict[str, Any]],
    user_attributes: Dict[str, Any],
) -> Dict[str, Any]:
    router = RouterAgent()
    plan = router.plan_report_agents(region_evidence, user_attributes) or {}
    selected = []
    if isinstance(plan, dict):
        raw_agents = plan.get("agents")
        if isinstance(raw_agents, list):
            selected = [name for name in raw_agents if name in AGENT_ORDER]
    if not selected:
        selected = _heuristic_plan(region_evidence, user_attributes)
        source = "heuristic"
    else:
        source = "router"
    return {
        "agents": _normalize_plan(selected),
        "source": source,
        "raw": plan,
    }
