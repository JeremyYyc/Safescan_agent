from enum import StrEnum
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CustomerStatus(StrEnum):
    PROSPECT = "prospect"
    TENANT = "tenant"
    FORMER_TENANT = "former_tenant"


class FieldError(BaseModel):
    field: str
    reason: str


class ErrorBody(BaseModel):
    status: int
    code: str
    message: str
    correlation_id: str
    field_errors: list[FieldError] = Field(default_factory=list)
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Meta(BaseModel):
    correlation_id: str
    next_cursor: str | None = None
    partial_errors: list[dict[str, Any]] = Field(default_factory=list)


T = TypeVar("T")


class DataEnvelope(BaseModel, Generic[T]):
    data: T
    meta: Meta


class CustomerIdentity(BaseModel):
    id: str | None = None
    username: str | None = None
    status: CustomerStatus | None = None
    authenticated: bool
    auth_version: int = 0
    status_version: int = 0


class NavigationItem(BaseModel):
    code: str
    href: str


class BootstrapView(BaseModel):
    customer: CustomerIdentity
    menu: list[NavigationItem]
    capabilities: list[str]
    agent: dict[str, Any] = Field(
        default_factory=lambda: {"available": False, "placeholder": True}
    )


class ResourceSummary(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    reference: str | None = None
    status: str | None = None
    version: int | None = None


class Page(BaseModel, Generic[T]):
    items: list[T] = Field(default_factory=list)
    next_cursor: str | None = None
    total: int | None = None


class PropertyView(ResourceSummary):
    address: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    weekly_rent: str | None = None
    currency: str | None = None
    availability: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class ProspectCaseView(ResourceSummary):
    stage: str | None = None
    property: PropertyView | None = None
    assigned_consultant: dict[str, Any] | None = None


class ApplicationView(ResourceSummary):
    case_id: str | None = None
    property_id: str | None = None
    desired_start_on: str | None = None
    term_months: int | None = None
    occupants: int | None = None


class LeaseView(ResourceSummary):
    property: PropertyView | None = None
    starts_on: str | None = None
    ends_on: str | None = None
    weekly_rent: str | None = None
    currency: str | None = None
    document: dict[str, Any] | None = None
    tenant_signers: list[dict[str, Any]] = Field(default_factory=list)


class MaintenanceOrderView(ResourceSummary):
    priority: str | None = None
    summary: str | None = None
    description: str | None = None
    property: PropertyView | None = None
    lease_id: str | None = None
    timeline: list[dict[str, Any]] = Field(default_factory=list)


class ReportView(ResourceSummary):
    property_id: str | None = None
    source_lease_id: str | None = None
    title: str | None = None
    created_at: str | None = None


class ReportJobView(ResourceSummary):
    report_id: str | None = None
    stage: str | None = None
    progress_percent: int | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)


class MyPropertyView(BaseModel):
    lease: LeaseView
    property: PropertyView | None = None
    invoices: dict[str, Any] | Page[ResourceSummary] | None = None
    maintenance: Page[MaintenanceOrderView] | list[MaintenanceOrderView] | None = None
    reports: Page[ReportView] | list[ReportView] | None = None


class HomeView(BaseModel):
    applications: dict[str, Any] | None = None
    leases: dict[str, Any] | None = None
    maintenance: dict[str, Any] | None = None
    reports: dict[str, Any] | None = None


class TenantTopbarView(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str | None = None
    username: str | None = None
    customer_status: str | None = None


class LeaseDocumentView(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str | None = None
    version: int | None = None
    terms_digest: str | None = None
    content: str | dict[str, Any] | None = None


class ContactRequest(StrictModel):
    message: str = Field(min_length=1, max_length=4000)
    client_message_id: str = Field(min_length=1, max_length=200)


class MessageRequest(StrictModel):
    content: str = Field(min_length=1, max_length=4000)
    client_message_id: str = Field(min_length=1, max_length=200)


class CreateApplicationRequest(StrictModel):
    case_id: str
    property_id: str
    desired_start_on: str
    term_months: int = Field(ge=1, le=120)
    occupants: int = Field(ge=1, le=20)
    note: str | None = Field(default=None, max_length=4000)


class UpdateApplicationRequest(StrictModel):
    desired_start_on: str | None = None
    term_months: int | None = Field(default=None, ge=1, le=120)
    occupants: int | None = Field(default=None, ge=1, le=20)
    note: str | None = Field(default=None, max_length=4000)
    version: int = Field(ge=1)


class SubmitApplicationRequest(StrictModel):
    attestation: Literal[True]
    version: int = Field(ge=1)


class VersionReasonRequest(StrictModel):
    version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=1000)


class TenantSignatureRequest(StrictModel):
    lease_document_id: str
    terms_digest: str = Field(min_length=8, max_length=200)
    accepted: Literal[True]
    version: int = Field(ge=1)


class DeclineLeaseRequest(StrictModel):
    reason_code: str = Field(min_length=1, max_length=100)
    version: int = Field(ge=1)


class CreateMaintenanceRequest(StrictModel):
    summary: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    priority: str

    @model_validator(mode="before")
    @classmethod
    def reject_authority_fields(cls, value: Any):
        if isinstance(value, dict) and {
            "lease_id",
            "property_id",
            "subject_id",
        }.intersection(value):
            raise ValueError("lease_id, property_id and subject_id are server-derived")
        return value


class UpdateMaintenanceRequest(StrictModel):
    summary: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    priority: str | None = None
    version: int = Field(ge=1)


class ReportCreateRequest(StrictModel):
    title: str | None = Field(default=None, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def reject_authority_fields(cls, value: Any):
        if isinstance(value, dict) and {
            "lease_id",
            "property_id",
            "subject_id",
            "source_lease_id",
        }.intersection(value):
            raise ValueError("report authority fields are server-derived")
        return value


class ReportJobRequest(StrictModel):
    input_file_id: str
    attributes: dict[str, Any] = Field(default_factory=dict)
