from datetime import datetime
from uuid import UUID

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
    event_type: str = Field(min_length=1, max_length=100)
    occurred_at: datetime
    details_redacted: dict = Field(default_factory=dict)
