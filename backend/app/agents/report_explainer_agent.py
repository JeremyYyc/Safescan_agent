from typing import Dict, Any, List
from app.agents.alibaba_base_agent import AlibabaBaseAgent
from app.prompts import report_prompts
from app.llm_registry import get_generation_params, get_model_name
import dashscope
from http import HTTPStatus
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
        return report_prompts.report_explainer_system_message()
    
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
                "content": report_prompts.report_explainer_user_prompt(user_query, region_info)
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
        
        model = get_model_name("L2")
        params = get_generation_params("L2")
        
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
