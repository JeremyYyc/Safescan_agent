from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContactRequest(StrictModel):
    property_id: UUID
    content: str = Field(min_length=1, max_length=4000)
    client_message_id: UUID
    customer_name: str = Field(default="Customer", min_length=1, max_length=200)


class MessageCreate(StrictModel):
    content: str = Field(min_length=1, max_length=4000)
    client_message_id: UUID


class CaseUpdate(StrictModel):
    stage: Literal["new", "contacted", "viewing", "application", "negotiation", "converted", "lost"] | None = None
    status: Literal["open", "closed"] | None = None
    version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=500)


class CaseAssignment(StrictModel):
    consultant_staff_id: UUID
    version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


class ApplicationCreate(StrictModel):
    case_id: UUID
    property_id: UUID
    desired_start_on: date
    term_months: int = Field(ge=1, le=120)
    occupants: int = Field(ge=1, le=50)
    note: str | None = Field(default=None, max_length=4000)


class ApplicationUpdate(StrictModel):
    desired_start_on: date | None = None
    term_months: int | None = Field(default=None, ge=1, le=120)
    occupants: int | None = Field(default=None, ge=1, le=50)
    note: str | None = Field(default=None, max_length=4000)
    version: int = Field(ge=1)


class VersionCommand(StrictModel):
    version: int = Field(ge=1)


class SubmitApplication(VersionCommand):
    attestation: Literal[True]


class DecisionCommand(VersionCommand):
    decision_note: str | None = Field(default=None, max_length=2000)


class RejectCommand(DecisionCommand):
    reason_code: str = Field(min_length=1, max_length=100)


class WithdrawCommand(VersionCommand):
    reason: str | None = Field(default=None, max_length=500)


class LeaseCreate(StrictModel):
    application_id: UUID
    starts_on: date
    ends_on: date
    weekly_rent: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="AUD", min_length=3, max_length=3)
    terms_payload: dict[str, Any]
    offer_expires_at: datetime

    @model_validator(mode="after")
    def validate_period(self):
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on must be on or after starts_on")
        return self


class LeaseUpdate(StrictModel):
    starts_on: date | None = None
    ends_on: date | None = None
    weekly_rent: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    terms_payload: dict[str, Any] | None = None
    offer_expires_at: datetime | None = None
    version: int = Field(ge=1)


class SendForSignature(VersionCommand):
    lease_document_id: UUID


class SignatureCommand(VersionCommand):
    lease_document_id: UUID
    terms_digest: str = Field(min_length=8, max_length=200)
    accepted: Literal[True]
    ip_hash: str | None = Field(default=None, max_length=200)
    user_agent_hash: str | None = Field(default=None, max_length=200)


class CancelLease(VersionCommand):
    reason_code: str = Field(min_length=1, max_length=100)


class TimedLeaseCommand(VersionCommand):
    as_of: datetime


class AuthorizationCheck(StrictModel):
    subject_id: UUID
    property_id: UUID
    action: str = Field(min_length=1, max_length=100)
    lease_id: UUID | None = None


class LeaseAuthorizationCheck(StrictModel):
    subject_id: UUID
    lease_id: UUID
    property_id: UUID | None = None
    action: str = Field(min_length=1, max_length=100)


class BatchIds(StrictModel):
    ids: list[UUID] = Field(min_length=1, max_length=200)
