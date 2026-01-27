from typing import Any, Dict
from http import HTTPStatus
import os

import dashscope

from app.env import load_env
from app.llm_registry import get_generation_params, get_model_name
from app.prompts import report_prompts

load_env()
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")


class TitleAgent:
    """
    Generates a concise, single-sentence English title for a chat based on the report.
    """

    def __init__(self) -> None:
        self.name = "TitleAgent"

    def summarize_title(self, report: Dict[str, Any]) -> str:
        messages = [
            {"role": "system", "content": report_prompts.title_system_message()},
            {"role": "user", "content": report_prompts.title_user_prompt(report)},
        ]
        response = self._call_alibaba_api(messages)
        return self._sanitize_title(response)

    def _call_alibaba_api(self, messages):
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
