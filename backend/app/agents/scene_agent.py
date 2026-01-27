from typing import Dict, Any, List
from app.agents.alibaba_base_agent import AlibabaBaseAgent
from app.prompts import report_prompts
import dashscope
from http import HTTPStatus
import os
from app.env import load_env

load_env()
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")


class SceneUnderstandingAgent(AlibabaBaseAgent):
    """
    代理负责理解代表性图像中的场景并识别区域及其特征。
    """
    
    def __init__(self):
        # 不调用父类的初始化，因为我们要使用阿里云API直接调用
        self.name = "SceneUnderstandingAgent"
    
    def _get_system_message(self) -> str:
        return report_prompts.scene_system_message()
    
    def analyze_scene(self, image_paths: List[str], user_attributes: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        分析提供的图像中的场景。
        
        Args:
            image_paths: 要分析的图像文件路径列表
            user_attributes: 用户特定属性
            
        Returns:
            场景分析结果列表
        """
        analyses = []
        
        for image_path in image_paths:
            # 构建消息用于阿里云API调用
            messages = [
                {
                    "role": "system",
                    "content": self._get_system_message()
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "image": f"file://{image_path}"
                        },
                        {
                            "text": report_prompts.scene_user_text_prompt()
                        }
                    ]
                }
            ]
            
            try:
                # 调用阿里云API
                response_content = self.call_alibaba_api(messages)
                
                analysis = {
                    "image_path": image_path,
                    "region_label": self._extract_region_label(response_content),  # 从响应中提取区域标签
                    "description": response_content
                }
                analyses.append(analysis)
            except Exception as e:
                # 如果API调用失败，添加错误信息
                analysis = {
                    "image_path": image_path,
                    "region_label": "unknown",
                    "description": f"分析失败: {str(e)}",
                    "error": str(e)
                }
                analyses.append(analysis)
        
        return analyses
    
    def call_alibaba_api(self, messages: List[Dict[str, Any]]) -> str:
        """
        调用阿里云通义千问API进行图像分析
        """
        import dashscope
        from http import HTTPStatus
        
        model = os.getenv("ALIBABA_VISION_MODEL")
        if not model:
            fallback = os.getenv("ALIBABA_MODEL", "")
            model = fallback if "vl" in fallback or "vision" in fallback else "qwen-vl-plus"
        
        try:
            response = dashscope.MultiModalConversation.call(
                model=model,
                messages=messages
            )
            
            if response.status_code == HTTPStatus.OK:
                return response.output.choices[0].message.content[0]['text']
            else:
                raise Exception(f"API调用失败: {response.code}, {response.message}")
                
        except Exception as e:
            raise Exception(f"阿里云API调用异常: {str(e)}")
    
    def _extract_region_label(self, description: str) -> str:
        """
        从描述中提取区域标签
        """
        # 这里应该有更复杂的文本处理逻辑
        # 简化版本：查找常见的房间类型词汇
        description_lower = description.lower()
        
        room_types = [
            ("kitchen", "厨房"), ("bedroom", "卧室"), ("bathroom", "浴室"), 
            ("living room", "客厅"), ("dining room", "餐厅"), ("study", "书房"),
            ("hallway", "走廊"), ("balcony", "阳台"), ("toilet", "厕所")
        ]
        
        for eng, chn in room_types:
            if eng in description_lower or chn in description:
                return eng.replace(" ", "_").title()
        
        return "Unknown"
