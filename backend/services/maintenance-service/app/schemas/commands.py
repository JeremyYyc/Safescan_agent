from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OrderCreate(StrictModel):
    property_id: UUID
    lease_id: UUID | None = None
    summary: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=8000)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"


class OrderUpdate(StrictModel):
    summary: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=8000)
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    version: int = Field(ge=1)

    @model_validator(mode="after")
    def has_change(self):
        if self.summary is None and self.description is None and self.priority is None:
            raise ValueError("at least one field must be updated")
        return self


class AssignmentCreate(StrictModel):
    assigned_staff_id: UUID
    version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=2000)


class TransitionCreate(StrictModel):
    to_status: Literal["assigned", "in_progress", "blocked", "completed", "cancelled"]
    version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=4000)
    blocked_reason: str | None = Field(default=None, max_length=2000)


class CommentCreate(StrictModel):
    content: str = Field(min_length=1, max_length=4000)
    visibility: Literal["public", "internal"] = "public"
    client_message_id: UUID


class DeletionCheck(StrictModel):
    subject_id: UUID


class DeletionProcess(StrictModel):
    subject_id: UUID


class OrderAccessCheck(StrictModel):
    subject_id: UUID
    order_id: UUID
    action: Literal["report:read_work_context"]
    report_id: UUID


class OrderBatchProjection(StrictModel):
    ids: list[UUID] = Field(min_length=1, max_length=200)
