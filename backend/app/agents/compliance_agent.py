from typing import Any, Dict

from app.agents.autogen_agent_base import AutoGenDashscopeAgent
from app.prompts import report_prompts


class ComplianceAgent(AutoGenDashscopeAgent):
    """
    Generates non-legal compliance tips and safety checklists.
    """

    def __init__(self):
        super().__init__(name="ComplianceAgent", model_tier="L2")

    def build_compliance(self, hazards) -> Dict[str, Any]:
        try:
            response_content = self._call_llm(
                system_message=report_prompts.compliance_system_message(),
                user_content=report_prompts.compliance_user_prompt(hazards),
                tier="L2",
            )
            return self.parse_json_response(response_content)
        except Exception as exc:
            return {
                "notes": [],
                "checklist": [],
                "error": f"compliance_failed: {str(exc)}",
            }

    def call_alibaba_api(self, messages):
        user_content = messages[-1]["content"] if messages else ""
        return self._call_llm(
            system_message=report_prompts.compliance_system_message(),
            user_content=user_content,
            tier="L2",
            name_suffix="compat",
        )
