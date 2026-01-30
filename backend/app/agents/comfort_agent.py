from typing import Dict, Any

from app.agents.autogen_agent_base import AutoGenDashscopeAgent
from app.prompts import report_prompts


class ComfortAgent(AutoGenDashscopeAgent):
    """
    Analyzes comfort, lighting, noise, and air quality impacts.
    """

    def __init__(self):
        super().__init__(name="ComfortAgent", model_tier="L2")

    def analyze_comfort(self, region_info, user_attributes: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response_content = self._call_llm(
                system_message=report_prompts.comfort_system_message(),
                user_content=report_prompts.comfort_user_prompt(region_info, user_attributes),
                tier="L2",
            )
            return self.parse_json_response(response_content)
        except Exception as exc:
            return {
                "observations": [],
                "suggestions": [],
                "error": f"comfort_analysis_failed: {str(exc)}",
            }

    def call_alibaba_api(self, messages):
        user_content = messages[-1]["content"] if messages else ""
        return self._call_llm(
            system_message=report_prompts.comfort_system_message(),
            user_content=user_content,
            tier="L2",
            name_suffix="compat",
        )
