from typing import Any, Dict
from app.agents.alibaba_base_agent import AlibabaBaseAgent
from app.prompts import report_prompts
from app.llm_registry import get_generation_params, get_model_name
from app.env import load_env
import dashscope
from http import HTTPStatus
import os

load_env()
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")


class ComplianceAgent(AlibabaBaseAgent):
    """
    Generates non-legal compliance tips and safety checklists.
    """

    def __init__(self):
        self.name = "ComplianceAgent"

    def build_compliance(self, hazards) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": report_prompts.compliance_system_message()},
            {"role": "user", "content": report_prompts.compliance_user_prompt(hazards)},
        ]
        try:
            response_content = self.call_alibaba_api(messages)
            return self.parse_json_response(response_content)
        except Exception as exc:
            return {
                "notes": [],
                "checklist": [],
                "error": f"compliance_failed: {str(exc)}",
            }

    def call_alibaba_api(self, messages):
        model = get_model_name("L2")
        params = get_generation_params("L2")
        response = dashscope.Generation.call(
            model=model,
            messages=messages,
            result_format="message",
            top_p=params["top_p"],
            temperature=params["temperature"],
        )
        if response.status_code != HTTPStatus.OK:
            raise Exception(f"API call failed: {response.code}, {response.message}")
        return response.output.choices[0].message.content
