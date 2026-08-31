"""Prompt/response adapters; all model/tool execution is a LangGraph subgraph."""
import json
import re
from app.llm import complete,complete_sync
from app.tools.registry import current_tool_context

class GraphModelAgent:
    def __init__(self,name,model_tier='L2'):
        self.name,self.model_tier=name,model_tier

    def _messages(self,system_message,user_content):
        return [{'role':'system','content':system_message},{'role':'user','content':user_content}]

    def _tools(self):
        return ('validate_report',) if self.name in ('ReportWriterAgent','ReportPdfRepairAgent') else ()

    def _call_llm(self,system_message,user_content,tier=None,name_suffix=None):
        return complete_sync(self._messages(system_message,user_content),tier or self.model_tier,
                             allowed_tools=self._tools(),context=current_tool_context())

    async def _call_llm_async(self,system_message,user_content,tier=None,name_suffix=None):
        return await complete(self._messages(system_message,user_content),tier or self.model_tier,
                              allowed_tools=self._tools(),context=current_tool_context())

    @staticmethod
    def parse_json_response(response):
        cleaned=response.strip() if isinstance(response,str) else str(response)
        if cleaned.startswith('```json'): cleaned=cleaned[7:]
        if cleaned.startswith('```'): cleaned=cleaned[3:]
        if cleaned.endswith('```'): cleaned=cleaned[:-3]
        try: return json.loads(cleaned.strip())
        except json.JSONDecodeError:
            match=re.search(r'\{.*\}',cleaned,re.DOTALL)
            if match:
                try: return json.loads(match.group())
                except json.JSONDecodeError: pass
            raise ValueError('Could not parse model JSON')
