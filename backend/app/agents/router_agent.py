from typing import Any, Dict, List
import json

from app.agents.autogen_agent_base import AutoGenDashscopeAgent
from app.prompts import report_prompts


class RouterAgent(AutoGenDashscopeAgent):
    """Plan which specialist agents to run for a report."""

    def __init__(self) -> None:
        super().__init__(name="RouterAgent", model_tier="L1")

    def _get_system_message(self) -> str:
        return report_prompts.router_system_message()

    def plan_report_agents(
        self,
        region_evidence: List[Dict[str, Any]],
        user_attributes: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        system_message = (
            "You are a workflow planner for a home safety report. "
            "Decide which specialist agents are needed based on the evidence and user attributes. "
            "Output JSON only with this schema: "
            "{\"agents\": [\"HazardAgent|ComfortAgent|ComplianceAgent|ScoringAgent|RecommendationAgent|ReportWriterAgent\"], "
            "\"notes\": \"string\"}. "
            "Rules: Always include HazardAgent and ReportWriterAgent. "
            "Keep order dependencies: HazardAgent -> ComfortAgent (optional) -> ComplianceAgent (optional) "
            "-> ScoringAgent (optional) -> RecommendationAgent (optional) -> ReportWriterAgent. "
            "Return JSON only."
        )
        payload = {
            "region_evidence": region_evidence,
            "user_attributes": user_attributes or {},
        }
        try:
            response = self._call_llm(
                system_message=system_message,
                user_content=json.dumps(payload, ensure_ascii=False),
                tier="L1",
                name_suffix="planner",
            )
        except Exception:
            return None
        return self._parse_plan_json(response)

    def _parse_plan_json(self, response: str) -> Dict[str, Any] | None:
        try:
            parsed = self.parse_json_response(response)
        except Exception:
            return None
        if not isinstance(parsed, dict):
            return None
        agents = parsed.get("agents")
        if not isinstance(agents, list):
            return None
        return parsed
