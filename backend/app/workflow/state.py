"""Shared graph state. Bytes, model clients, secrets and local paths stay outside."""
from typing import TypedDict,Any,Annotated
import operator

class WorkflowState(TypedDict,total=False):
    run_id:str
    user_id:int
    chat_id:int
    video_asset_id:str
    user_attributes:dict[str,Any]
    frames:list[str]
    filter_stats:dict[str,int]
    representative_images:list[str]
    yolo_summaries:dict[str,list[str]]
    region_evidence:list[dict]
    plan:list[str]
    hazards:list[dict]
    comfort:dict
    compliance:dict
    scoring:dict
    recommendations:dict
    draft_report:dict
    validation:dict
    iterations:int
    title:str
    report_id:int
    warning:str
    trace_log:Annotated[list[dict],operator.add]
