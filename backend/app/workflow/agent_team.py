from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.teams import SelectorGroupChat

from app.agents.dashscope_client import DashScopeChatCompletionClient
from app.agents.router_agent import RouterAgent
from app.llm_registry import get_generation_params, get_model_name
from app.prompts import report_prompts


DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
AGENT_ORDER = [
    "HazardAgent",
    "ComfortAgent",
    "ComplianceAgent",
    "ScoringAgent",
    "RecommendationAgent",
    "ReportWriterAgent",
]


def _model_client(tier: str, api_key: str, vision: bool = False) -> DashScopeChatCompletionClient:
    params = get_generation_params(tier)
    return DashScopeChatCompletionClient(
        model=get_model_name(tier),
        api_key=api_key,
        base_url=DASHSCOPE_BASE_URL,
        temperature=params["temperature"],
        top_p=params["top_p"],
        vision=vision,
    )


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


def _hazards_empty(messages: List[Any]) -> bool:
    for message in messages:
        source = getattr(message, "source", "")
        if source != "HazardAgent":
            continue
        content = getattr(message, "content", "")
        if isinstance(content, list):
            content = " ".join([str(item) for item in content])
        parsed = _parse_json_blob(str(content))
        if isinstance(parsed, list):
            return len(parsed) == 0
        if isinstance(parsed, dict):
            general = parsed.get("general_hazards", []) or []
            specific = parsed.get("specific_hazards", []) or []
            return len(general) == 0 and len(specific) == 0
    return False


def run_agent_team(
    region_evidence: List[Dict[str, Any]],
    user_attributes: Dict[str, Any],
    trace_cb=None,
) -> Dict[str, Any]:
    api_key = ""
    try:
        import os

        api_key = os.getenv("DASHSCOPE_API_KEY", "")
    except Exception:
        api_key = ""

    attributes_desc = _format_user_attributes(user_attributes)

    hazard_system = report_prompts.hazard_system_message(attributes_desc)
    hazard_system += (
        "\nFor this team task, output a JSON array with one entry per region: "
        "[{\"region_name\": \"string\", \"general_hazards\": [\"string\"], \"specific_hazards\": [\"string\"]}]."
    )
    hazard_agent = AssistantAgent(
        name="HazardAgent",
        model_client=_model_client("L2", api_key),
        system_message=hazard_system,
        description="Identify hazards for each region.",
    )
    comfort_system = report_prompts.comfort_system_message()
    comfort_system += "\nUse the provided region evidence and user attributes JSON."
    comfort_agent = AssistantAgent(
        name="ComfortAgent",
        model_client=_model_client("L2", api_key),
        system_message=comfort_system,
        description="Assess comfort, lighting, noise, and air quality.",
    )
    compliance_system = report_prompts.compliance_system_message()
    compliance_system += "\nUse the hazards JSON produced by HazardAgent."
    compliance_agent = AssistantAgent(
        name="ComplianceAgent",
        model_client=_model_client("L2", api_key),
        system_message=compliance_system,
        description="Provide compliance notes and checklist.",
    )
    scoring_system = report_prompts.scoring_system_message()
    scoring_system += "\nUse hazards JSON and comfort JSON already produced in this thread."
    scoring_agent = AssistantAgent(
        name="ScoringAgent",
        model_client=_model_client("L2", api_key),
        system_message=scoring_system,
        description="Score safety dimensions and summarize top risks.",
    )
    recommendation_system = report_prompts.recommendation_system_message()
    recommendation_system += "\nUse hazards, scores, comfort, and user attributes from the thread."
    recommendation_agent = AssistantAgent(
        name="RecommendationAgent",
        model_client=_model_client("L2", api_key),
        system_message=recommendation_system,
        description="Generate prioritized recommendations.",
    )
    report_system = report_prompts.report_writer_system_message(attributes_desc)
    report_system += (
        "\nUse region evidence plus HazardAgent/ComfortAgent/ComplianceAgent/"
        "ScoringAgent/RecommendationAgent outputs from this thread."
    )
    report_agent = AssistantAgent(
        name="ReportWriterAgent",
        model_client=_model_client("L3", api_key),
        system_message=report_system,
        description="Compose the full report JSON.",
    )

    agent_map = {
        "HazardAgent": hazard_agent,
        "ComfortAgent": comfort_agent,
        "ComplianceAgent": compliance_agent,
        "ScoringAgent": scoring_agent,
        "RecommendationAgent": recommendation_agent,
        "ReportWriterAgent": report_agent,
    }

    plan = _plan_agents(region_evidence, user_attributes)
    plan_agents = [name for name in plan["agents"] if name in agent_map]
    participants = [agent_map[name] for name in plan_agents]
    if len(participants) < 2:
        participants = [hazard_agent, report_agent]
        plan_agents = ["HazardAgent", "ReportWriterAgent"]

    termination = TextMentionTermination("TERMINATE")
    plan_queue = list(plan_agents)

    def _selector_func(thread):
        nonlocal plan_queue
        responded = {
            getattr(msg, "source", "")
            for msg in thread
            if getattr(msg, "source", "")
        }
        if "HazardAgent" in responded and "ComplianceAgent" in plan_queue:
            if _hazards_empty(list(thread)):
                plan_queue = [name for name in plan_queue if name != "ComplianceAgent"]
        for name in plan_queue:
            if name and name not in responded:
                return name
        return plan_queue[-1] if plan_queue else participants[0].name

    team = SelectorGroupChat(
        participants,
        model_client=_model_client("L1", api_key),
        termination_condition=termination,
        max_turns=len(participants),
        selector_func=_selector_func,
    )

    task_payload = (
        "You are a team completing a home safety report.\n"
        f"Selected agents (in order): {', '.join(plan_agents)}\n"
        "Each agent must output JSON ONLY for its task.\n"
        "ReportWriterAgent must output TERMINATE after the final JSON.\n\n"
        f"Region evidence JSON:\n{json.dumps(region_evidence, ensure_ascii=False)}\n\n"
        f"User attributes JSON:\n{json.dumps(user_attributes or {}, ensure_ascii=False)}\n"
    )

    async def _run():
        return await team.run(task=task_payload)

    result = asyncio.run(_run())

    outputs: Dict[str, Any] = {
        "hazards": [],
        "comfort": {},
        "compliance": {},
        "scoring": {},
        "recommendations": {},
        "draft_report": {},
    }

    for message in result.messages:
        source = getattr(message, "source", "")
        content = getattr(message, "content", "")
        if isinstance(content, list):
            content = " ".join([str(item) for item in content])
        parsed = _parse_json_blob(str(content))
        if not parsed:
            continue
        if source == "HazardAgent":
            outputs["hazards"] = parsed
        elif source == "ComfortAgent":
            outputs["comfort"] = parsed
        elif source == "ComplianceAgent":
            outputs["compliance"] = parsed
        elif source == "ScoringAgent":
            outputs["scoring"] = parsed
        elif source == "RecommendationAgent":
            outputs["recommendations"] = parsed
        elif source == "ReportWriterAgent":
            outputs["draft_report"] = parsed

    if trace_cb:
        trace_cb("agent_team_plan", {"agents": plan_agents, "source": plan.get("source", "heuristic")})
        trace_cb("agent_team_complete", {"agents": [p.name for p in participants]})

    return outputs
