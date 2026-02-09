from __future__ import annotations

from typing import Any, Dict, Optional
import json

from app.agents.autogen_agent_base import AutoGenDashscopeAgent
from app.prompts import report_prompts


class ReportPdfRepairAgent(AutoGenDashscopeAgent):
    """Repair/fill report JSON before PDF rendering."""

    def __init__(self) -> None:
        super().__init__(name="ReportPdfRepairAgent", model_tier="L1")

    def repair_report(self, report: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(report, dict):
            return None
        system_message = report_prompts.report_pdf_repair_system_message()
        user_content = report_prompts.report_pdf_repair_user_prompt(report)
        try:
            response = self._call_llm(
                system_message=system_message,
                user_content=user_content,
                tier="L1",
                name_suffix="pdf-repair",
            )
            parsed = self.parse_json_response(response)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
