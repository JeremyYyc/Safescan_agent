from typing import Any, Dict

from app.agents.autogen_agent_base import AutoGenDashscopeAgent
from app.prompts import report_prompts


class ScoringAgent(AutoGenDashscopeAgent):
    """
    Computes overall and dimension scores plus top risks.
    """

    def __init__(self):
        super().__init__(name="ScoringAgent", model_tier="L2")

    def score_home(self, hazards, comfort, user_attributes: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response_content = self._call_llm(
                system_message=report_prompts.scoring_system_message(),
                user_content=report_prompts.scoring_user_prompt(hazards, comfort, user_attributes),
                tier="L2",
            )
            return self.parse_json_response(response_content)
        except Exception as exc:
            return {
                "overall": 0.0,
                "dimensions": {},
                "top_risks": [],
                "rationale": "",
                "error": f"scoring_failed: {str(exc)}",
            }

    def call_alibaba_api(self, messages):
        user_content = messages[-1]["content"] if messages else ""
        return self._call_llm(
            system_message=report_prompts.scoring_system_message(),
            user_content=user_content,
            tier="L2",
            name_suffix="compat",
        )
