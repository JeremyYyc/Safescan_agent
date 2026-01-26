from typing import Dict, Any, List, Callable
from app.workflow.state import WorkflowState
from app.tools.video_tools import extract_frames, filter_frames_with_stats, batch_images, get_representative_images, yolo_detect_and_draw
from app.tools.evidence_tools import merge_region_evidence
from app.tools.validation_tools import validate_report
from pathlib import Path
from ultralytics import YOLO
import os


class WorkflowOrchestrator:
    """
    Orchestrates the home safety analysis workflow.
    """
    
    def __init__(self):
        model_path = Path(__file__).resolve().parent.parent / "yolov8m.pt"
        self.yolo_model = YOLO(str(model_path))
        self.steps = []
    
    def execute_workflow(self, 
                        video_path: str, 
                        user_attributes: Dict[str, Any], 
                        extract_dir: str = './extracted_frames/',
                        trace_cb: Callable[[Dict[str, Any]], None] = None) -> WorkflowState:
        """
        Execute the complete workflow from video to report.
        
        Args:
            video_path: Path to input video
            user_attributes: User-specific attributes for analysis
            extract_dir: Directory to store extracted frames
        
        Returns:
            Completed workflow state
        """
        state = WorkflowState()
        if trace_cb:
            state.add_trace_listener(trace_cb)
        state.video_path = video_path
        state.user_attributes = user_attributes
        
        # Create extraction directory if it doesn't exist
        os.makedirs(extract_dir, exist_ok=True)
        
        # Step 1: Extract frames
        state.add_trace("extract_frames_start", {"video_path": video_path})
        frame_paths = extract_frames(video_path, extract_dir, frame_rate=1)
        state.frames = frame_paths
        state.add_trace("extract_frames_complete", {"frame_count": len(frame_paths)})
        
        # Step 2: Filter frames
        if len(state.frames) > 0:
            state.add_trace("filter_frames_start", {"frame_count_before": len(state.frames)})
            filtered_frames, stats = filter_frames_with_stats(state.frames)
            state.frames = filtered_frames
            state.filter_stats = stats
            state.add_trace("filter_frames_complete", {
                "frame_count_after": len(filtered_frames),
                "deletion_stats": stats
            })
        
        # Check if we have frames after filtering
        if len(state.frames) == 0:
            state.add_trace("workflow_early_exit", {"reason": "no_valid_frames_after_filtering"})
            return state
        
        # Step 3: Get representative images
        state.add_trace("select_representative_images_start", {"frame_count": len(state.frames)})
        batch_size = self._calculate_dynamic_batch_size(len(state.frames))
        frame_batches = batch_images(state.frames, batch_size)
        representative_images = get_representative_images(frame_batches)
        state.representative_images = representative_images
        state.add_trace("select_representative_images_complete", {
            "representative_image_count": len(representative_images),
            "batch_size": batch_size,
            "batch_count": len(frame_batches)
        })
        
        # Step 4: Apply YOLO detection to representative images
        state.add_trace("yolo_detection_start", {"representative_image_count": len(representative_images)})
        processed_images = yolo_detect_and_draw(state.representative_images, self.yolo_model)
        state.representative_images = processed_images
        state.add_trace("yolo_detection_complete", {"processed_image_count": len(processed_images)})
        
        # At this point, we would normally continue with agent-based analysis
        # But since this requires LLM integration, we'll add a placeholder
        # The actual agent-based analysis would happen here
        
        return state
    
    def _calculate_dynamic_batch_size(self, total_frames: int) -> int:
        """
        Calculate optimal batch size based on total number of frames.
        
        Args:
            total_frames: Total number of frames to process
        
        Returns:
            Optimal batch size
        """
        if total_frames <= 12:
            return 5
        elif total_frames <= 30:
            return 6
        elif total_frames <= 45:
            return 7
        elif total_frames <= 75:
            return 9
        elif total_frames <= 105:
            return 11
        elif total_frames <= 165:
            return 15
        else:
            return 20
