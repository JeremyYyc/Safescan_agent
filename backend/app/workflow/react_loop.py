from typing import Dict, Any, Tuple, List, Optional, Callable
from app.agents.validator_agent import ValidatorAgent
from app.agents.report_writer_agent import ReportWriterAgent


class ReactRepairLoop:
    """
    Implements the ReAct (Reason-Act-Observe) loop for report validation and repair.
    """
    
    def __init__(self, validator_agent: ValidatorAgent, report_writer_agent: ReportWriterAgent):
        self.validator_agent = validator_agent
        self.report_writer_agent = report_writer_agent
    
    def execute_repair_loop(self, 
                           initial_report: Dict[str, Any], 
                           region_evidence: List[Dict[str, Any]], 
                           hazards: List[Dict[str, Any]], 
                           user_attributes: Dict[str, Any], 
                           max_iterations: int = 3,
                           trace_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None
                           ) -> Tuple[Dict[str, Any], bool, int]:
        """
        Execute the ReAct repair loop to fix validation errors in the report.
        
        Args:
            initial_report: The initial report to validate and repair
            region_evidence: Evidence about regions
            hazards: Identified hazards
            user_attributes: User attributes
            max_iterations: Maximum number of repair attempts
            
        Returns:
            Tuple of (final_report, success_flag, iteration_count)
        """
        current_report = initial_report
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            if trace_cb:
                trace_cb("react_loop_iteration_start", {"iteration": iteration})

            # Step 1: Reason (Validate the report)
            validation_result = self.validator_agent.validate_report(current_report)
            if trace_cb:
                trace_cb("react_loop_validation", {
                    "iteration": iteration,
                    "valid": validation_result.get("valid", False),
                    "error_count": len(validation_result.get("errors", []))
                })
            
            if validation_result["valid"]:
                # Report is valid, exit the loop
                if trace_cb:
                    trace_cb("react_loop_success", {"iteration": iteration})
                return current_report, True, iteration
            
            # Step 2: Act (Attempt to repair based on validation errors)
            repair_instructions = self._generate_repair_instructions(validation_result)
            if trace_cb:
                trace_cb("react_loop_repair_instructions", {
                    "iteration": iteration,
                    "repair_hint_count": len(validation_result.get("repair_hints", []))
                })
            
            # For repair, we regenerate the report with focus on problematic areas
            repaired_report = self.report_writer_agent.write_report(
                region_evidence, 
                hazards, 
                user_attributes,
                repair_instructions=repair_instructions
            )
            
            # Update current report for next iteration
            current_report = repaired_report
        
        # If we've reached max iterations without success
        if trace_cb:
            trace_cb("react_loop_max_iterations", {"iterations": iteration})
        return current_report, False, iteration
    
    def _generate_repair_instructions(self, validation_result: Dict[str, Any]) -> str:
        """
        Generate repair instructions based on validation errors.
        
        Args:
            validation_result: Result from validation
            
        Returns:
            Repair instructions as a string
        """
        errors = validation_result.get("errors", [])
        repair_hints = validation_result.get("repair_hints", [])
        
        instructions = "The report has validation errors. Please fix the following:\n"
        
        for error in errors:
            instructions += f"- {error}\n"
        
        instructions += "\nRepair hints:\n"
        for hint in repair_hints:
            instructions += f"- {hint}\n"
        
        return instructions
