from typing import Any, Dict

from app.agents.autogen_agent_base import AutoGenDashscopeAgent
from app.prompts import report_prompts


class RecommendationAgent(AutoGenDashscopeAgent):
    """
    Generates action recommendations with budget and difficulty tiers.
    """

    def __init__(self):
        super().__init__(name="RecommendationAgent", model_tier="L2")

    def build_recommendations(self, hazards, scores, comfort, user_attributes: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response_content = self._call_llm(
                system_message=report_prompts.recommendation_system_message(),
                user_content=report_prompts.recommendation_user_prompt(hazards, scores, comfort, user_attributes),
                tier="L2",
            )
            return self.parse_json_response(response_content)
        except Exception as exc:
            return {
                "actions": [],
                "error": f"recommendation_failed: {str(exc)}",
            }

    def call_alibaba_api(self, messages):
        user_content = messages[-1]["content"] if messages else ""
        return self._call_llm(
            system_message=report_prompts.recommendation_system_message(),
            user_content=user_content,
            tier="L2",
            name_suffix="compat",
        )
