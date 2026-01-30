from typing import Any, Dict

from app.agents.autogen_agent_base import AutoGenDashscopeAgent
from app.prompts import report_prompts


class TitleAgent(AutoGenDashscopeAgent):
    """
    Generates a concise, single-sentence English title for a chat based on the report.
    """

    def __init__(self) -> None:
        super().__init__(name="TitleAgent", model_tier="L2")

    def summarize_title(self, report: Dict[str, Any]) -> str:
        messages = [
            {"role": "system", "content": report_prompts.title_system_message()},
            {"role": "user", "content": report_prompts.title_user_prompt(report)},
        ]
        response = self._call_llm(
            system_message=report_prompts.title_system_message(),
            user_content=report_prompts.title_user_prompt(report),
            tier="L2",
        )
        return self._sanitize_title(response)

    def _call_alibaba_api(self, messages):
        user_content = messages[-1]["content"] if messages else ""
        return self._call_llm(
            system_message=report_prompts.title_system_message(),
            user_content=user_content,
            tier="L2",
            name_suffix="compat",
        )

    def _sanitize_title(self, text: str) -> str:
        if not isinstance(text, str):
            return ""
        cleaned = text.strip().strip('"').strip("'")
        if ":" in cleaned and cleaned.lower().startswith(("title", "summary")):
            cleaned = cleaned.split(":", 1)[1].strip()
        if "\n" in cleaned:
            cleaned = cleaned.splitlines()[0].strip()
        if len(cleaned) > 80:
            cleaned = cleaned[:80].rstrip()
        return cleaned
