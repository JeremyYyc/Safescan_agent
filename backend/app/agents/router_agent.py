from typing import Dict, Any, List
from app.agents.alibaba_base_agent import AlibabaBaseAgent
from app.prompts import report_prompts
import dashscope
from http import HTTPStatus
import os
from app.env import load_env

load_env()
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")


class RouterAgent(AlibabaBaseAgent):
    """
    代理将传入的聊天请求路由到适当的处理程序。
    """
    
    def __init__(self):
        self.name = "RouterAgent"
    
    def _get_system_message(self) -> str:
        return report_prompts.router_system_message()
    
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
            response_content = self.call_alibaba_api(messages)
            
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
        """
        调用阿里云通义千问API进行查询路由
        """
        import dashscope
        from http import HTTPStatus
        
        model = os.getenv("ALIBABA_TEXT_MODEL") or os.getenv("ALIBABA_MODEL", "qwen-plus")
        
        try:
            response = dashscope.Generation.call(
                model=model,
                messages=messages,
                result_format='message',
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
