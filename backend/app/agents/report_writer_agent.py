from typing import Dict, Any, List, Optional
from app.agents.alibaba_base_agent import AlibabaBaseAgent
import dashscope
from http import HTTPStatus
import os
from app.env import load_env
from app.prompts import report_prompts

load_env()
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")


class ReportWriterAgent(AlibabaBaseAgent):
    """
    代理负责根据收集的证据和风险信息生成结构化的家居安全报告。
    """
    
    def __init__(self):
        self.name = "ReportWriterAgent"
    
    def _get_system_message(self, user_attributes: Dict[str, Any]) -> str:
        attributes_desc = self._format_user_attributes(user_attributes)
        
        return report_prompts.report_writer_system_message(attributes_desc)
    
    def write_report(self, 
                    region_evidence: List[Dict[str, Any]], 
                    hazards: List[Dict[str, Any]], 
                    user_attributes: Dict[str, Any],
                    repair_instructions: Optional[str] = None) -> Dict[str, Any]:
        """
        根据证据和风险编写结构化安全报告。
        
        Args:
            region_evidence: 区域描述和证据列表
            hazards: 每个区域的已识别风险列表
            user_attributes: 用于个性化报告的用户属性
            repair_instructions: 修复指令（可选）
            
        Returns:
            JSON格式的结构化安全报告
        """
        # 组合证据和风险信息
        combined_info = self._combine_evidence_and_hazards(region_evidence, hazards)
        
        # 构建消息用于阿里云API调用
        user_content = report_prompts.report_writer_user_prompt(
            combined_info,
            repair_instructions=repair_instructions,
        )

        messages = [
            {
                "role": "system",
                "content": self._get_system_message(user_attributes)
            },
            {
                "role": "user", 
                "content": user_content
            }
        ]
        
        try:
            # 调用阿里云API
            response_content = self.call_alibaba_api(messages)
            
            # 尝试解析API返回的JSON
            try:
                report = self.parse_json_response(response_content)
                return report
            except ValueError as e:
                # 如果JSON解析失败，返回错误信息
                return {
                    "error": f"JSON解析失败: {str(e)}",
                    "raw_response": response_content
                }
        except Exception as e:
            # 如果API调用失败，返回错误信息
            return {
                "error": f"报告生成失败: {str(e)}"
            }
    
    def call_alibaba_api(self, messages: List[Dict[str, Any]]) -> str:
        """
        调用阿里云通义千问API进行报告生成
        """
        import dashscope
        from http import HTTPStatus
        
        model = os.getenv("ALIBABA_TEXT_MODEL") or os.getenv("ALIBABA_MODEL", "qwen-plus")
        
        try:
            response = dashscope.Generation.call(
                model=model,
                messages=messages,
                result_format='message',
                top_p=0.8,
                temperature=0.5
            )
            
            if response.status_code == HTTPStatus.OK:
                return response.output.choices[0].message.content
            else:
                raise Exception(f"API调用失败: {response.code}, {response.message}")
                
        except Exception as e:
            raise Exception(f"阿里云API调用异常: {str(e)}")
    
    def _combine_evidence_and_hazards(self, 
                                    region_evidence: List[Dict[str, Any]], 
                                    hazards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        合并证据和风险信息
        """
        combined = []
        
        for evidence in region_evidence:
            region_name = evidence.get("region_label", "Unknown Region")
            region_desc = evidence.get("description", "")
            
            # 查找匹配的风险信息
            matching_hazards = next((h for h in hazards if h.get("region_name") == region_name), {})
            
            combined_entry = {
                "region_name": region_name,
                "description": region_desc,
                "general_hazards": matching_hazards.get("general_hazards", []),
                "specific_hazards": matching_hazards.get("specific_hazards", []),
            }
            
            combined.append(combined_entry)
        
        return combined
    
    def _format_user_attributes(self, attributes: Dict[str, Any]) -> str:
        """
        格式化用户属性为可读字符串
        """
        if not attributes:
            return "No special user groups."
        
        attribute_descriptions = {
            'isPregnant': "Pregnant",
            'isChildren': "Children",
            'isElderly': "Elderly",
            'isDisabled': "Disabled",
            'isAllergic': "Allergic",
            'isPets': "Pets"
        }
        
        # 过滤出值为True的属性
        active_attributes = [desc for key, desc in attribute_descriptions.items() 
                            if attributes.get(key, False)]
        
        if not active_attributes:
            return "No special user groups."
        
        return ", ".join(active_attributes) + "."
