from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.agents.alibaba_base_agent import AlibabaBaseAgent
from app.prompts import report_prompts
from app.llm_registry import get_generation_params, get_model_name, get_max_concurrency
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
        
        return report_prompts.hazard_system_message(attributes_desc)
    
    def identify_hazards(
        self,
        region_evidence: List[Dict[str, Any]],
        user_attributes: Dict[str, Any],
        max_concurrency: int | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Identify hazards for each region in parallel.
        
        Args:
            region_evidence: Region evidence list
            user_attributes: User attributes for personalization
            max_concurrency: Max concurrency for LLM calls
            
        Returns:
            List of hazards per region
        """
        if max_concurrency is None:
            max_concurrency = get_max_concurrency()

        hazards_list: List[Dict[str, Any]] = [None] * len(region_evidence)

        if max_concurrency <= 1 or len(region_evidence) <= 1:
            for idx, region in enumerate(region_evidence):
                _, hazards = self._identify_region_hazards(idx, region, user_attributes)
                hazards_list[idx] = hazards
            return hazards_list

        with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
            future_to_idx = {
                executor.submit(self._identify_region_hazards, idx, region, user_attributes): idx
                for idx, region in enumerate(region_evidence)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    _, hazards = future.result()
                except Exception as exc:
                    hazards = {
                        "region_name": "unknown",
                        "general_hazards": [],
                        "specific_hazards": [],
                        "error": f"hazard_detection_failed: {str(exc)}",
                    }
                hazards_list[idx] = hazards

        return hazards_list

    def _identify_region_hazards(
        self,
        idx: int,
        region: Dict[str, Any],
        user_attributes: Dict[str, Any],
    ) -> tuple[int, Dict[str, Any]]:
        region_desc = region.get("description", "")
        region_name = region.get("region_label", "unknown")

        messages = [
            {
                "role": "system",
                "content": self._get_system_message(user_attributes),
            },
            {
                "role": "user",
                "content": report_prompts.hazard_user_prompt(region_desc),
            },
        ]

        try:
            response_content = self.call_alibaba_api(messages)
            parsed_hazards = self._parse_hazard_json(response_content)
            if not parsed_hazards:
                parsed_hazards = self._parse_hazard_response(response_content)
            hazards = {
                "region_name": region_name,
                "general_hazards": parsed_hazards.get("general_hazards", []),
                "specific_hazards": parsed_hazards.get("specific_hazards", []),
            }
        except Exception as exc:
            hazards = {
                "region_name": region_name,
                "general_hazards": [],
                "specific_hazards": [],
                "error": f"hazard_detection_failed: {str(exc)}",
            }

        return idx, hazards

    def call_alibaba_api(self, messages: List[Dict[str, Any]]) -> str:
        """
        调用阿里云通义千问API进行风险识别
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
    
    def _parse_hazard_json(self, response: str) -> Dict[str, List[str]] | None:
        try:
            parsed = self.parse_json_response(response)
        except Exception:
            return None
        if not isinstance(parsed, dict):
            return None
        if "general_hazards" in parsed or "specific_hazards" in parsed:
            return {
                "general_hazards": parsed.get("general_hazards", []) or [],
                "specific_hazards": parsed.get("specific_hazards", []) or [],
            }
        return None

    def _parse_hazard_response(self, response: str) -> Dict[str, List[str]]:
        general_hazards = []
        specific_hazards = []

        lower = response.lower()
        if "specific hazards" in lower or "special hazards" in lower:
            parts = lower.split("specific hazards", 1)
            if len(parts) == 1:
                parts = lower.split("special hazards", 1)
            general_part = parts[0]
            specific_part = parts[1] if len(parts) > 1 else ""
            general_hazards = [line.strip("-* \t") for line in general_part.split("\n") if line.strip()]
            specific_hazards = [line.strip("-* \t") for line in specific_part.split("\n") if line.strip()]
        else:
            general_hazards = [line.strip("-* \t") for line in response.split("\n") if line.strip()]

        return {
            "general_hazards": general_hazards,
            "specific_hazards": specific_hazards,
        }
    
    def _format_user_attributes(self, attributes: Dict[str, Any]) -> str:
        """Format user attributes for prompt context."""
        if not attributes:
            return "No special user groups."

        attribute_descriptions = {
            "isPregnant": "Pregnant",
            "isChildren": "Children",
            "isElderly": "Elderly",
            "isDisabled": "Disabled",
            "isAllergic": "Allergic",
            "isPets": "Pets",
        }

        active_attributes = [
            desc for key, desc in attribute_descriptions.items() if attributes.get(key, False)
        ]

        if not active_attributes:
            return "No special user groups."

        return ", ".join(active_attributes) + "."
