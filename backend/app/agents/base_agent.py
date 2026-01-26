from typing import Dict, Any, List
import json
from autogen import ConversableAgent


class BaseAgent(ConversableAgent):
    """
    Base class for all agents in the home safety analysis system.
    """
    
    def __init__(self, name: str, llm_config: Dict[str, Any], **kwargs):
        super().__init__(
            name=name,
            llm_config=llm_config,
            **kwargs
        )
    
    def parse_json_response(self, response: str) -> Dict[str, Any]:
        """
        Parse JSON response from LLM, handling common formatting issues.
        
        Args:
            response: Raw response string from LLM
            
        Returns:
            Parsed JSON as dictionary
        """
        # Clean the response string
        cleaned_response = response.strip()
        
        # Remove markdown code block markers if present
        if cleaned_response.startswith("```json"):
            cleaned_response = cleaned_response[7:]  # Remove ```json
        if cleaned_response.startswith("```"):
            cleaned_response = cleaned_response[3:]   # Remove ```
        if cleaned_response.endswith("```"):
            cleaned_response = cleaned_response[:-3]  # Remove ```
        
        cleaned_response = cleaned_response.strip()
        
        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            # Try to find JSON within the response
            import re
            json_match = re.search(r'\{.*\}', cleaned_response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    raise ValueError(f"Could not parse JSON from response: {response}")
            else:
                raise ValueError(f"Could not parse JSON from response: {response}")