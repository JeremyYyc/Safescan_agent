from typing import Dict, Any, List
from app.agents.alibaba_base_agent import AlibabaBaseAgent
import dashscope
from http import HTTPStatus
import json
import os
from app.env import load_env

load_env()
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")


class ReportExplainerAgent(AlibabaBaseAgent):
    """
    代理基于结构化区域信息解释安全报告。
    """
    
    def __init__(self):
        self.name = "ReportExplainerAgent"
    
    def _get_system_message(self) -> str:
        return """你是家居安全报告解释员。你的角色是使用结构化区域数据中的信息回答用户关于其家居安全报告的问题。只能使用报告中提供的信息，不要编造超出报告范围的信息。要有帮助，但严格遵守报告中的事实。"""
    
    def explain_report(self, 
                      user_query: str, 
                      region_info: List[Dict[str, Any]]) -> str:
        """
        根据用户查询解释安全报告。
        
        Args:
            user_query: 用户关于报告的问题
            region_info: 报告中的结构化区域信息
            
        Returns:
            基于报告数据的解释
        """
        # 构建消息用于阿里云API调用
        messages = [
            {
                "role": "system",
                "content": self._get_system_message()
            },
            {
                "role": "user",
                "content": f"用户问题：{user_query}\n\n报告数据：{json.dumps(region_info, ensure_ascii=False, indent=2)}"
            }
        ]
        
        try:
            # 调用阿里云API
            response_content = self.call_alibaba_api(messages)
            return response_content
        except Exception as e:
            return f"报告解释过程中出现错误: {str(e)}"
    
    def call_alibaba_api(self, messages: List[Dict[str, Any]]) -> str:
        """
        调用阿里云通义千问API进行报告解释
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
