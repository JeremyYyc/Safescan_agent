from datetime import datetime
from uuid import UUID

from typing import Literal

from pydantic import BaseModel, Field


class TokenExchangeRequest(BaseModel):
    user_token: str = Field(min_length=20)
    target_audience: str = Field(min_length=1, max_length=200)
    requested_scopes: list[str] = Field(max_length=500)


class TokenIntrospectionRequest(BaseModel):
    token: str = Field(min_length=20)
    required_audience: str | None = Field(default=None, max_length=200)


class SubjectBatchRequest(BaseModel):
    subject_ids: list[UUID] = Field(min_length=1, max_length=200)


class CustomerStatusEventRequest(BaseModel):
    event_id: UUID
    customer_subject_id: UUID
    lease_id: UUID
    event_type: Literal["customer.tenancy_status_changed.v1"]
    to_status: Literal["tenant", "former_tenant"]
    aggregate_version: int = Field(gt=0)
    occurred_at: datetime
    details_redacted: dict = Field(default_factory=dict)


class SubjectDeletionAcknowledgementRequest(BaseModel):
    service: Literal["property-leasing", "maintenance", "inspection-report"]
    status: Literal["completed", "failed"]
    details_redacted: dict = Field(default_factory=dict)


class SubjectTombstoneCheckRequest(BaseModel):
    subject_id: UUID
