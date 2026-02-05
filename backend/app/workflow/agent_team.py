from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List

from openai import OpenAI

from app.agents.router_agent import RouterAgent
from app.llm_registry import get_generation_params, get_model_name
from app.agents.report_writer_agent import ReportWriterAgent
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


def _has_regions(report: Any) -> bool:
    if not isinstance(report, dict):
        return False
    regions = report.get("regions")
    return isinstance(regions, list) and len(regions) > 0


def _openai_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=DASHSCOPE_BASE_URL)


async def _call_json_model(
    api_key: str,
    tier: str,
    system_message: str,
    user_message: str,
    retries: int = 2,
) -> Any:
    params = get_generation_params(tier)
    model = get_model_name(tier)
    client = _openai_client(api_key)
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ],
                temperature=params["temperature"],
                top_p=params["top_p"],
            )
            content = ""
            if response and response.choices:
                content = response.choices[0].message.content or ""
            parsed = _parse_json_blob(content)
            return parsed if parsed is not None else content
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                await asyncio.sleep(0.8 * (attempt + 1))
                continue
            break
    if last_exc:
        raise last_exc
    return None


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
    plan = _plan_agents(region_evidence, user_attributes)
    plan_agents = [name for name in plan["agents"] if name in AGENT_ORDER]
    if not plan_agents:
        plan_agents = ["HazardAgent", "ReportWriterAgent"]

    if trace_cb:
        trace_cb("agent_team_plan", {"agents": plan_agents, "source": plan.get("source", "heuristic")})

    async def _run_parallel():
        outputs: Dict[str, Any] = {
            "hazards": [],
            "comfort": {},
            "compliance": {},
            "scoring": {},
            "recommendations": {},
            "draft_report": {},
        }

        # Stage 1: Hazard + Comfort in parallel (if selected)
        hazard_task = None
        comfort_task = None
        if "HazardAgent" in plan_agents:
            hazard_system = report_prompts.hazard_system_message(attributes_desc)
            hazard_system += (
                "\nOutput a JSON array with one entry per region: "
                "[{\"region_name\": \"string\", \"general_hazards\": [\"string\"], "
                "\"specific_hazards\": [\"string\"]}]."
            )
            hazard_user = (
                "Region evidence JSON:\n"
                f"{json.dumps(region_evidence, ensure_ascii=False)}\n\n"
                "User attributes JSON:\n"
                f"{json.dumps(user_attributes or {}, ensure_ascii=False)}"
            )
            hazard_task = _call_json_model(api_key, "L2", hazard_system, hazard_user)
        if "ComfortAgent" in plan_agents:
            comfort_system = report_prompts.comfort_system_message()
            comfort_user = report_prompts.comfort_user_prompt(region_evidence, user_attributes)
            comfort_task = _call_json_model(api_key, "L2", comfort_system, comfort_user)

        hazard_result, comfort_result = await asyncio.gather(
            hazard_task or asyncio.sleep(0, result=[]),
            comfort_task or asyncio.sleep(0, result={}),
        )
        outputs["hazards"] = hazard_result if isinstance(hazard_result, list) else []
        outputs["comfort"] = comfort_result if isinstance(comfort_result, dict) else {}

        # Stage 2: Compliance + Scoring in parallel (if selected)
        compliance_task = None
        scoring_task = None
        if "ComplianceAgent" in plan_agents:
            compliance_system = report_prompts.compliance_system_message()
            compliance_user = report_prompts.compliance_user_prompt(outputs["hazards"])
            compliance_task = _call_json_model(api_key, "L2", compliance_system, compliance_user)
        if "ScoringAgent" in plan_agents:
            scoring_system = report_prompts.scoring_system_message()
            scoring_user = report_prompts.scoring_user_prompt(
                outputs["hazards"], outputs["comfort"], user_attributes
            )
            scoring_task = _call_json_model(api_key, "L2", scoring_system, scoring_user)

        compliance_result, scoring_result = await asyncio.gather(
            compliance_task or asyncio.sleep(0, result={}),
            scoring_task or asyncio.sleep(0, result={}),
        )
        outputs["compliance"] = compliance_result if isinstance(compliance_result, dict) else {}
        outputs["scoring"] = scoring_result if isinstance(scoring_result, dict) else {}

        # Stage 3: Recommendation (depends on scoring)
        if "RecommendationAgent" in plan_agents:
            recommendation_system = report_prompts.recommendation_system_message()
            recommendation_user = report_prompts.recommendation_user_prompt(
                outputs["hazards"],
                outputs["scoring"],
                outputs["comfort"],
                user_attributes,
            )
            recommendation_result = await _call_json_model(
                api_key, "L2", recommendation_system, recommendation_user
            )
            outputs["recommendations"] = (
                recommendation_result if isinstance(recommendation_result, dict) else {}
            )

        # Stage 4: ReportWriter (single)
        writer = ReportWriterAgent()
        outputs["draft_report"] = writer.write_report(
            region_evidence,
            outputs.get("hazards") or [],
            user_attributes,
            outputs.get("scoring") or {},
            outputs.get("comfort") or {},
            outputs.get("compliance") or {},
            outputs.get("recommendations") or {},
        )

        return outputs

    outputs = asyncio.run(_run_parallel())

    if not _has_regions(outputs.get("draft_report")):
        try:
            writer = ReportWriterAgent()
            outputs["draft_report"] = writer.write_report(
                region_evidence,
                outputs.get("hazards") or [],
                user_attributes,
                outputs.get("scoring") or {},
                outputs.get("comfort") or {},
                outputs.get("compliance") or {},
                outputs.get("recommendations") or {},
            )
        except Exception:
            pass

    if trace_cb:
        trace_cb("agent_team_complete", {"agents": plan_agents})

    return outputs
