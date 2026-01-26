from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class RegionScore(BaseModel):
    """Scores for a region"""
    personal_safety: float = Field(..., ge=0, le=5, description="Personal safety score (0-5)")
    special_safety: float = Field(..., ge=0, le=5, description="Special safety score (0-5)")
    color_lighting: float = Field(..., ge=0, le=5, description="Color and lighting score (0-5)")
    psychological_impact: float = Field(..., ge=0, le=5, description="Psychological impact score (0-5)")
    final_score: float = Field(..., ge=0, le=5, description="Final region score (0-5)")


class RegionInfo(BaseModel):
    """Information about a specific region in the home"""
    regionName: List[str] = Field(..., description="Names of the region")
    potentialHazards: List[str] = Field(..., description="Potential safety hazards in the region")
    specialHazards: Optional[List[str]] = Field(None, description="Hazards specific to user attributes")
    colorAndLightingEvaluation: List[str] = Field(..., description="Evaluation of color and lighting")
    suggestions: List[str] = Field(..., description="Suggestions for improvements")
    scores: List[float] = Field(..., min_items=5, max_items=5, description="List of 5 scores [personal_safety, special_safety, color_lighting, psychological_impact, final_score]")


class HomeSafetyReport(BaseModel):
    """Complete home safety report"""
    regions: List[RegionInfo] = Field(..., description="List of regions with safety information")
    overall_summary: Optional[str] = Field(None, description="Overall summary of the report")
    recommendations: Optional[List[str]] = Field(None, description="General recommendations")