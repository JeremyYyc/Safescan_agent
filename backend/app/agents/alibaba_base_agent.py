from typing import Dict, Any, List
import json
import dashscope
from autogen import ConversableAgent
from app.env import load_env
from app.llm_registry import get_model_name, get_generation_params
import os

load_env()

# 设置阿里云API密钥
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")


class AlibabaBaseAgent(ConversableAgent):
    """
    基于阿里云通义千问的代理基类，用于百炼平台部署
    """
    
    def __init__(self, name: str, llm_config: Dict[str, Any], **kwargs):
        # 设置默认的阿里云模型配置
        default_params = get_generation_params("L2")
        alibaba_llm_config = {
            "config_list": [{
                "model": get_model_name("L2"),
                "api_key": os.getenv("DASHSCOPE_API_KEY"),
                "api_type": "dashscope",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"
            }],
            "temperature": llm_config.get("temperature", default_params["temperature"])
        }
        
        super().__init__(
            name=name,
            llm_config=alibaba_llm_config,
            **kwargs
        )
    
    def parse_json_response(self, response: str) -> Dict[str, Any]:
        """
        解析来自LLM的JSON响应，处理常见格式问题。
        
        Args:
            response: 来自LLM的原始响应字符串
            
        Returns:
            解析后的JSON字典
        """
        # 清理响应字符串
        cleaned_response = response.strip()
        
        # 移除markdown代码块标记（如果存在）
        if cleaned_response.startswith("```json"):
            cleaned_response = cleaned_response[7:]  # 移除 ```json
        if cleaned_response.startswith("```"):
            cleaned_response = cleaned_response[3:]   # 移除 ```
        if cleaned_response.endswith("```"):
            cleaned_response = cleaned_response[:-3]  # 移除 ```
        
        cleaned_response = cleaned_response.strip()
        
        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            # 尝试在响应中查找JSON
            import re
            json_match = re.search(r'\{.*\}', cleaned_response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    raise ValueError(f"无法从响应中解析JSON: {response}")
            else:
                raise ValueError(f"无法从响应中解析JSON: {response}")
    
    def call_alibaba_api(self, messages: List[Dict[str, str]], model: str = None) -> str:
        """
        调用阿里云通义千问API
        """
        import dashscope
        from http import HTTPStatus
        
        if model is None:
            model = get_model_name("L2")
        
        params = get_generation_params("L2")
        try:
            response = dashscope.Generation.call(
                model=model,
                messages=messages,
                result_format='message',  # return message format
                top_p=params["top_p"],
                temperature=params["temperature"],
            )
            
            if response.status_code == HTTPStatus.OK:
                return response.output.choices[0].message.content
            else:
                raise Exception(f"API调用失败: {response.code}, {response.message}")
                
        except Exception as e:
            raise Exception(f"阿里云API调用异常: {str(e)}")
