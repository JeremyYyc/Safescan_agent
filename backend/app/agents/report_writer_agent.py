from typing import Dict, Any, List, Optional

from app.agents.autogen_agent_base import AutoGenDashscopeAgent
from app.prompts import report_prompts


class ReportWriterAgent(AutoGenDashscopeAgent):
    """
    代理负责根据收集的证据和风险信息生成结构化的家居安全报告。
    """
    
    def __init__(self):
        super().__init__(name="ReportWriterAgent", model_tier="L3")
    
    def _get_system_message(self, user_attributes: Dict[str, Any]) -> str:
        attributes_desc = self._format_user_attributes(user_attributes)
        
        return report_prompts.report_writer_system_message(attributes_desc)
    
    def write_report(self, 
                    region_evidence: List[Dict[str, Any]], 
                    hazards: List[Dict[str, Any]], 
                    user_attributes: Dict[str, Any],
                    scoring_result: Dict[str, Any],
                    comfort_result: Dict[str, Any],
                    compliance_result: Dict[str, Any],
                    recommendations_result: Dict[str, Any],
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
            scoring_result,
            comfort_result,
            compliance_result,
            recommendations_result,
            repair_instructions=repair_instructions,
        )

        try:
            # 调用阿里云API
            response_content = self._call_llm(
                system_message=self._get_system_message(user_attributes),
                user_content=user_content,
                tier="L3",
            )
            
            # 尝试解析API返回的JSON
            try:
                report = self.parse_json_response(response_content)
                return self._normalize_report(report)
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
        user_content = messages[-1]["content"] if messages else ""
        return self._call_llm(
            system_message=self._get_system_message({}),
            user_content=user_content,
            tier="L3",
            name_suffix="compat",
        )
        """
        调用阿里云通义千问API进行报告生成
        """
        import dashscope
        from http import HTTPStatus
        
        model = get_model_name("L3")
        params = get_generation_params("L3")
        
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

    def _normalize_report(self, report: Any) -> Any:
        if not isinstance(report, dict):
            return report

        regions = report.get("regions")
        if not isinstance(regions, list):
            return report

        for region in regions:
            if not isinstance(region, dict):
                continue

            region_name = region.get("regionName")
            if isinstance(region_name, str):
                name = region_name.strip()
                region["regionName"] = [name] if name else ["Unknown Region"]
            elif isinstance(region_name, list):
                cleaned = [str(item).strip() for item in region_name if str(item).strip()]
                region["regionName"] = cleaned if cleaned else ["Unknown Region"]
            else:
                region["regionName"] = ["Unknown Region"]

            for field in ["potentialHazards", "colorAndLightingEvaluation", "suggestions"]:
                value = region.get(field)
                if isinstance(value, str):
                    entry = value.strip()
                    region[field] = [entry] if entry else []
                elif isinstance(value, list):
                    cleaned = [str(item).strip() for item in value if str(item).strip()]
                    region[field] = cleaned

            if not region.get("potentialHazards"):
                region["potentialHazards"] = ["No obvious hazards identified in this region."]

        return report

    def _combine_evidence_and_hazards(
        self,
        region_evidence: List[Dict[str, Any]],
        hazards: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Combine evidence and hazards with trimmed descriptions.
        """
        combined: List[Dict[str, Any]] = []

        for evidence in region_evidence:
            region_name = evidence.get("region_label", "Unknown Region")
            region_desc = evidence.get("description", "")
            if isinstance(region_desc, str) and len(region_desc) > 1200:
                region_desc = region_desc[:1200].rsplit(" ", 1)[0].rstrip()
                if region_desc:
                    region_desc += "..."

            matching_hazards = next(
                (h for h in hazards if h.get("region_name") == region_name), {}
            )

            combined_entry: Dict[str, Any] = {
                "region_name": region_name,
                "description": region_desc,
                "general_hazards": matching_hazards.get("general_hazards", []),
                "specific_hazards": matching_hazards.get("specific_hazards", []),
            }
            if "key_objects" in evidence:
                combined_entry["key_objects"] = evidence.get("key_objects", [])
            if "evidence_frames" in evidence:
                combined_entry["evidence_frames"] = evidence.get("evidence_frames", [])

            combined.append(combined_entry)

        return combined
