from typing import Dict, Any, List
from app.agents.base_agent import BaseAgent


class OrchestratorAgent(BaseAgent):
    """
    Agent that coordinates the workflow between other agents.
    """
    
    def __init__(self, llm_config: Dict[str, Any]):
        super().__init__(
            name="OrchestratorAgent",
            llm_config=llm_config,
            system_message=self._get_system_message(),
            human_input_mode="NEVER"
        )
    
    def _get_system_message(self) -> str:
        return """You are an orchestrator agent coordinating the home safety analysis workflow. Your responsibilities include:
        1. Coordinating between the Scene Understanding Agent, Safety Hazard Agent, Report Writer Agent, and Validator Agent
        2. Managing the flow of information between agents
        3. Ensuring each step is completed before proceeding to the next
        4. Handling any coordination logic needed between agents"""
    
    def coordinate_analysis(self, 
                          representative_images: List[str], 
                          user_attributes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Coordinate the complete analysis workflow between agents.
        
        Args:
            representative_images: List of image paths to analyze
            user_attributes: User-specific attributes for analysis
            
        Returns:
            Complete analysis result
        """
        # This would coordinate the actual agent interactions
        # For now, returning a template
        return {
            "representative_images": representative_images,
            "user_attributes": user_attributes,
            "status": "coordination_template"
        }