from typing import Any, Dict, List
import json

from app.agents.model_agent import GraphModelAgent
from app.prompts import report_prompts
from app.localization import llm_language_directive


class RouterAgent(GraphModelAgent):
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
            "你是家居安全报告的工作流规划器。根据证据和用户属性决定需要哪些专业代理。"
            "Output JSON only with this schema: "
            "{\"agents\": [\"HazardAgent|ComfortAgent|ComplianceAgent|ScoringAgent|RecommendationAgent|ReportWriterAgent\"], "
            "\"notes\": \"string\"}. "
            "Rules: Always include HazardAgent and ReportWriterAgent. "
            "Keep order dependencies: HazardAgent -> ComfortAgent (optional) -> ComplianceAgent (optional) "
            "-> ScoringAgent (optional) -> RecommendationAgent (optional) -> ReportWriterAgent. "
            f"只返回 JSON；notes 遵循输出语言要求。{llm_language_directive()}"
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
