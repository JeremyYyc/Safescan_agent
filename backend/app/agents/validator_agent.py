from typing import Dict, Any
from app.agents.base_agent import BaseAgent
from app.tools.validation_tools import validate_report


class ValidatorAgent(BaseAgent):
    """
    Agent responsible for validating the home safety report against schema requirements.
    This agent performs deterministic validation without calling LLMs.
    """
    
    def __init__(self, llm_config: Dict[str, Any]):
        super().__init__(
            name="ValidatorAgent",
            llm_config=False,  # This agent doesn't use LLMs for validation
            human_input_mode="NEVER"
        )
    
    def validate_report(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate the home safety report structure and content.
        
        Args:
            report: The report to validate
            
        Returns:
            Validation result with validity, errors, and repair hints
        """
        return validate_report(report)
    
    def needs_repair(self, validation_result: Dict[str, Any]) -> bool:
        """
        Determine if the report needs repairs based on validation.
        
        Args:
            validation_result: Result from validation
            
        Returns:
            True if repairs are needed, False otherwise
        """
        return not validation_result.get("valid", False)