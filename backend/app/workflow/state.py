from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
import json


@dataclass
class WorkflowState:
    """
    Represents the state of the home safety analysis workflow.
    """
    # Input data
    video_path: Optional[str] = None
    user_attributes: Optional[Dict[str, Any]] = None
    
    # Video processing results
    frames: List[str] = field(default_factory=list)
    filter_stats: Dict[str, int] = field(default_factory=dict)
    
    # Image selection results
    representative_images: List[str] = field(default_factory=list)
    yolo_summaries: Dict[str, List[str]] = field(default_factory=dict)
    
    # Analysis results
    region_evidence: List[Dict[str, Any]] = field(default_factory=list)
    hazards: List[Dict[str, Any]] = field(default_factory=list)
    
    # Draft report
    draft_report: Optional[Dict[str, Any]] = None
    
    # Validation results
    validation: Optional[Dict[str, Any]] = None
    
    # Trace log for debugging
    trace_log: List[Dict[str, Any]] = field(default_factory=list)
    trace_listeners: List[Callable[[Dict[str, Any]], None]] = field(default_factory=list, repr=False)
    
    def add_trace(self, step: str, details: Dict[str, Any]):
        """Add a trace entry to the log."""
        entry = {
            "step": step,
            "timestamp": self._get_timestamp(),
            "details": details
        }
        self.trace_log.append(entry)
        for listener in list(self.trace_listeners):
            try:
                listener(entry)
            except Exception:
                continue

    def add_trace_listener(self, listener: Callable[[Dict[str, Any]], None]):
        """Register a trace listener callback."""
        if callable(listener):
            self.trace_listeners.append(listener)
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for serialization."""
        return {
            "video_path": self.video_path,
            "user_attributes": self.user_attributes,
            "frames": self.frames,
            "filter_stats": self.filter_stats,
            "representative_images": self.representative_images,
            "yolo_summaries": self.yolo_summaries,
            "region_evidence": self.region_evidence,
            "hazards": self.hazards,
            "draft_report": self.draft_report,
            "validation": self.validation,
            "trace_log": self.trace_log
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowState':
        """Create state from dictionary."""
        state = cls()
        state.video_path = data.get('video_path')
        state.user_attributes = data.get('user_attributes')
        state.frames = data.get('frames', [])
        state.filter_stats = data.get('filter_stats', {})
        state.representative_images = data.get('representative_images', [])
        state.yolo_summaries = data.get('yolo_summaries', {})
        state.region_evidence = data.get('region_evidence', [])
        state.hazards = data.get('hazards', [])
        state.draft_report = data.get('draft_report')
        state.validation = data.get('validation')
        state.trace_log = data.get('trace_log', [])
        return state
