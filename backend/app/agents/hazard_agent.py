from typing import Dict, Any, List
from app.agents.alibaba_base_agent import AlibabaBaseAgent
import dashscope
from http import HTTPStatus
import os
from app.env import load_env

load_env()
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")


class SafetyHazardAgent(AlibabaBaseAgent):
    """
    代理负责基于场景描述和用户属性识别家居安全风险。
    """
    
    def __init__(self):
        self.name = "SafetyHazardAgent"
    
    def _get_system_message(self, user_attributes: Dict[str, Any]) -> str:
        # 根据用户属性构建个性化提示
        attributes_desc = self._format_user_attributes(user_attributes)
        
        return f"""你是一个家居安全风险识别专家。你的任务是分析房间描述并识别潜在的安全风险，考虑一般风险和与用户属性相关的特定风险。
        
        用户属性: {attributes_desc}
        
        对于每个房间描述，请识别：
        1. 一般安全风险（火灾风险、绊倒风险、电气危险等）
        2. 与用户属性相关的风险（如果用户年长，注意跌倒风险；如果用户有儿童，注意窒息风险等）
        3. 环境风险（照明不足、空气质量等）
        
        将你的响应结构化为每个区域的风险列表。"""
    
    def identify_hazards(self, 
                        region_evidence: List[Dict[str, Any]], 
                        user_attributes: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        识别所提供区域中的安全风险。
        
        Args:
            region_evidence: 区域描述列表
            user_attributes: 用于个性化分析的用户特定属性
            
        Returns:
            每个区域的已识别风险列表
        """
        hazards_list = []
        
        for region in region_evidence:
            region_desc = region.get("description", "")
            region_name = region.get("region_label", "unknown")
            
            # 构建消息用于阿里云API调用
            messages = [
                {
                    "role": "system",
                    "content": self._get_system_message(user_attributes)
                },
                {
                    "role": "user",
                    "content": f"请分析以下区域的潜在安全风险：\n\n{region_desc}"
                }
            ]
            
            try:
                # 调用阿里云API
                response_content = self.call_alibaba_api(messages)
                
                # 解析API响应以提取风险信息
                parsed_hazards = self._parse_hazard_response(response_content)
                
                hazards = {
                    "region_name": region_name,
                    "general_hazards": parsed_hazards.get("general_hazards", []),
                    "specific_hazards": parsed_hazards.get("specific_hazards", [])
                }
                hazards_list.append(hazards)
            except Exception as e:
                # 如果API调用失败，添加错误信息
                hazards = {
                    "region_name": region_name,
                    "general_hazards": [],
                    "specific_hazards": [],
                    "error": f"风险识别失败: {str(e)}"
                }
                hazards_list.append(hazards)
        
        return hazards_list
    
    def call_alibaba_api(self, messages: List[Dict[str, Any]]) -> str:
        """
        调用阿里云通义千问API进行风险识别
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
    
    def _parse_hazard_response(self, response: str) -> Dict[str, List[str]]:
        """
        解析风险识别的响应
        """
        # 简化的解析逻辑，实际应用中可能需要更复杂的自然语言处理
        general_hazards = []
        specific_hazards = []
        
        # 检查响应是否包含特定风险部分
        if "特定风险" in response or "特殊风险" in response:
            # 分离一般风险和特定风险
            parts = response.split("特定风险") if "特定风险" in response else response.split("特殊风险")
            if len(parts) > 1:
                general_part = parts[0]
                specific_part = parts[1]
                
                # 提取一般风险（简化处理）
                general_hazards = [item.strip() for item in general_part.split('\n') if item.strip() and '风险' in item]
                
                # 提取特定风险
                specific_hazards = [item.strip() for item in specific_part.split('\n') if item.strip() and ('风险' in item or '隐患' in item)]
            else:
                # 如果没有明确区分，将所有风险归入一般风险
                general_hazards = [line.strip() for line in response.split('\n') if line.strip() and ('风险' in line or '隐患' in line)]
        else:
            # 默认将所有风险归入一般风险
            general_hazards = [line.strip() for line in response.split('\n') if line.strip() and ('风险' in line or '隐患' in line)]
        
        return {
            "general_hazards": general_hazards,
            "specific_hazards": specific_hazards
        }
    
    def _format_user_attributes(self, attributes: Dict[str, Any]) -> str:
        """
        格式化用户属性为可读字符串
        """
        if not attributes:
            return "用户不属于任何特殊群体。"
        
        attribute_descriptions = {
            'isPregnant': "怀孕",
            'isChildren': "有小孩",
            'isElderly': "年长",
            'isDisabled': "残疾",
            'isAllergic': "过敏",
            'isPets': "养宠物"
        }
        
        # 过滤出值为True的属性
        active_attributes = [desc for key, desc in attribute_descriptions.items() 
                            if attributes.get(key, False)]
        
        if not active_attributes:
            return "用户不属于任何特殊群体。"
        
        return "、".join(active_attributes) + "。"
