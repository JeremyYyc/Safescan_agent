from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReportCreate(StrictModel):
    title: str | None = Field(default=None, max_length=255)


class JobCreate(StrictModel):
    input_file_id: UUID
    attributes: dict[str, Any] = Field(default_factory=dict)


class CancelJob(StrictModel):
    reason: str = Field(min_length=1, max_length=500)


class ReportView(BaseModel):
    id: UUID
    property_id: UUID
    source_lease_id: UUID | None
    title: str
    source: str
    status: str
    version: int
    completed_at: Any | None = None
    validation_passed: bool | None = None
    report: dict[str, Any] | None = None
    region_info: list[Any] | None = None
    evidence_images: list[UUID] | None = None
    can_download: Literal[False] = False


class JobView(BaseModel):
    id: UUID
    type: str
    status: str
    stage: str
    progress_percent: float
    attempt: int
    max_attempts: int
    report_id: UUID
    error: dict[str, Any] | None
    created_at: Any
    updated_at: Any
