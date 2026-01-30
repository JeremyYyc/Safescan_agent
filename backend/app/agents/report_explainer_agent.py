from typing import Dict, Any, List

from app.agents.autogen_agent_base import AutoGenDashscopeAgent
from app.prompts import report_prompts


class ReportExplainerAgent(AutoGenDashscopeAgent):
    """
    代理基于结构化区域信息解释安全报告。
    """
    
    def __init__(self):
        super().__init__(name="ReportExplainerAgent", model_tier="L2")
    
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
            response_content = self._call_llm(
                system_message=self._get_system_message(),
                user_content=report_prompts.report_explainer_user_prompt(user_query, region_info),
                tier="L2",
            )
            return response_content
        except Exception as e:
            return f"报告解释过程中出现错误: {str(e)}"
    
    def call_alibaba_api(self, messages: List[Dict[str, Any]]) -> str:
        user_content = messages[-1]["content"] if messages else ""
        return self._call_llm(
            system_message=self._get_system_message(),
            user_content=user_content,
            tier="L2",
            name_suffix="compat",
        )
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
