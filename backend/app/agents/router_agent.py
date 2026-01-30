from typing import Dict, Any, List
import json

from app.agents.autogen_agent_base import AutoGenDashscopeAgent
from app.prompts import report_prompts


class RouterAgent(AutoGenDashscopeAgent):
    """
    代理将传入的聊天请求路由到适当的处理程序。
    """
    
    def __init__(self):
        super().__init__(name="RouterAgent", model_tier="L1")
    
    def _get_system_message(self) -> str:
        return report_prompts.router_system_message()

    def plan_report_agents(
        self,
        region_evidence: List[Dict[str, Any]],
        user_attributes: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        system_message = (
            "You are a workflow planner for a home safety report. "
            "Decide which specialist agents are needed based on the evidence and user attributes. "
            "Output JSON only with this schema: "
            "{\"agents\": [\"HazardAgent|ComfortAgent|ComplianceAgent|ScoringAgent|RecommendationAgent|ReportWriterAgent\"], "
            "\"notes\": \"string\"}. "
            "Rules: Always include HazardAgent and ReportWriterAgent. "
            "Keep order dependencies: HazardAgent -> ComfortAgent (optional) -> ComplianceAgent (optional) "
            "-> ScoringAgent (optional) -> RecommendationAgent (optional) -> ReportWriterAgent. "
            "Return JSON only."
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
    
    def route_query(self, user_query: str) -> str:
        """
        将用户查询路由到适当的处理程序。
        
        Args:
            user_query: 用户的查询
            
        Returns:
            查询的类别
        """
        # 构建消息用于阿里云API调用
        messages = [
            {
                "role": "system",
                "content": self._get_system_message()
            },
            {
                "role": "user",
                "content": report_prompts.router_user_prompt(user_query)
            }
        ]
        
        try:
            # 调用阿里云API
            response_content = self._call_llm(
                system_message=self._get_system_message(),
                user_content=report_prompts.router_user_prompt(user_query),
                tier="L1",
            )
            
            # 解析响应，获取分类结果
            response_lower = response_content.lower()
            
            if "report_explanation" in response_lower or "解释报告" in response_lower or "报告解释" in response_lower:
                return "REPORT_EXPLANATION"
            elif "reanalysis_request" in response_lower or "重新分析" in response_lower or "再分析" in response_lower:
                return "REANALYSIS_REQUEST"
            else:
                # 默认为GENERAL_SAFETY
                return "GENERAL_SAFETY"
        except Exception as e:
            # 如果API调用失败，使用简单的关键字匹配
            return self._simple_route_fallback(user_query)
    
    def call_alibaba_api(self, messages: List[Dict[str, Any]]) -> str:
        user_content = messages[-1]["content"] if messages else ""
        return self._call_llm(
            system_message=self._get_system_message(),
            user_content=user_content,
            tier="L1",
            name_suffix="compat",
        )
        """
        调用阿里云通义千问API进行查询路由
        """
        import dashscope
        from http import HTTPStatus
        
        model = get_model_name("L1")
        params = get_generation_params("L1")
        
        try:
            response = dashscope.Generation.call(
                model=model,
                messages=messages,
                result_format='message',
                top_p=params["top_p"],
                temperature=params["temperature"],
            )
            
            if response.status_code == HTTPStatus.OK:
                return response.output.choices[0].message.content
            else:
                raise Exception(f"API调用失败: {response.code}, {response.message}")
                
        except Exception as e:
            raise Exception(f"阿里云API调用异常: {str(e)}")
    
    def _simple_route_fallback(self, user_query: str) -> str:
        """
        API失败时的简单回退路由逻辑
        """
        query_lower = user_query.lower()
        
        report_keywords = ["报告", "report", "explain", "解释", "details", "细节", "meaning", "意思", "安全报告"]
        if any(keyword in query_lower for keyword in report_keywords):
            return "REPORT_EXPLANATION"
        
        reanalysis_keywords = ["重新", "重新分析", "再分析", "update", "更新", "review", "复查"]
        if any(keyword in query_lower for keyword in reanalysis_keywords):
            return "REANALYSIS_REQUEST"
        
        return "GENERAL_SAFETY"
