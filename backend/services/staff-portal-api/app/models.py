from enum import StrEnum
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class Role(StrEnum):
    LEASING_CONSULTANT = "leasing_consultant"
    PROPERTY_MANAGER = "property_manager"
    MAINTAINER = "maintainer"
    MANAGER_ADMIN = "manager_admin"


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


class PartialError(BaseModel):
    component: str
    code: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class Meta(BaseModel):
    correlation_id: str
    next_cursor: str | None = None
    partial_errors: list[PartialError] = Field(default_factory=list)


T = TypeVar("T")


class DataEnvelope(BaseModel, Generic[T]):
    data: T
    meta: Meta


class StaffIdentity(BaseModel):
    id: str
    display_name: str
    username: str | None
    email: str | None
    staff_code: str | None
    role: Role
    role_name: str | None = None
    permissions: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    auth_version: int = 1
    role_version: int = 1


class NavigationItem(BaseModel):
    code: str
    href: str
    enabled: bool = True


class BootstrapView(BaseModel):
    staff: StaffIdentity
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


class ListView(BaseModel):
    items: list[ResourceSummary]
    next_cursor: str | None = None


class Page(BaseModel, Generic[T]):
    items: list[T] = Field(default_factory=list)
    next_cursor: str | None = None
    total: int | None = None


class PropertyView(ResourceSummary):
    address: str | None = None
    building: dict[str, Any] | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    weekly_rent: str | None = None
    currency: str | None = None
    availability: str | None = None


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


class StaffAdminView(ResourceSummary):
    display_name: str | None = None
    email: str | None = None
    employment_status: str | None = None
    role: dict[str, Any] | str | None = None
    permissions: list[str] = Field(default_factory=list)


class StaffTopbarView(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str | None = None
    display_name: str | None = None
    username: str | None = None
    role: str | dict[str, Any] | None = None


class StaffAdminDetailView(BaseModel):
    staff: StaffAdminView
    role_history: Page[ResourceSummary] | list[ResourceSummary] | dict[str, Any]


class DashboardView(BaseModel):
    staff: dict[str, Any]
    cards: dict[str, dict[str, Any]]


class PropertyDetailView(BaseModel):
    property: PropertyView
    leases: Page[LeaseView] | list[LeaseView] | None = None
    open_maintenance: Page[MaintenanceOrderView] | list[MaintenanceOrderView] | None = (
        None
    )
    recent_reports: Page[ReportView] | list[ReportView] | None = None


class MessageRequest(StrictModel):
    content: str = Field(min_length=1, max_length=10_000)
    client_message_id: str = Field(min_length=1, max_length=200)


class StageUpdateRequest(StrictModel):
    stage: str | None = None
    status: str | None = None
    version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=500)


class AssignmentRequest(StrictModel):
    assigned_staff_id: str
    version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=2000)


class VersionRequest(StrictModel):
    version: int = Field(ge=1)


class ApproveApplicationRequest(VersionRequest):
    decision_note: str | None = Field(default=None, max_length=2000)


class RejectApplicationRequest(ApproveApplicationRequest):
    reason_code: str = Field(min_length=1, max_length=100)


class CreateLeaseRequest(StrictModel):
    application_id: str
    starts_on: str
    ends_on: str
    weekly_rent: str
    currency: str = Field(min_length=3, max_length=3)
    terms_payload: dict[str, Any]
    offer_expires_at: str


class LeaseTermsRequest(StrictModel):
    starts_on: str | None = None
    ends_on: str | None = None
    weekly_rent: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    terms_payload: dict[str, Any] | None = None
    offer_expires_at: str | None = None
    version: int = Field(ge=1)


class SendForSignatureRequest(VersionRequest):
    lease_document_id: str


class CompanySignatureRequest(SendForSignatureRequest):
    terms_digest: str = Field(min_length=8, max_length=200)
    accepted: Literal[True]


class CancelLeaseRequest(VersionRequest):
    reason_code: str = Field(min_length=1, max_length=100)


class EndLeaseRequest(VersionRequest):
    effective_at: str


class TerminateLeaseRequest(EndLeaseRequest):
    reason: str = Field(min_length=1, max_length=1000)


class TransitionRequest(VersionRequest):
    to_status: str
    note: str | None = Field(default=None, max_length=2000)
    blocked_reason: str | None = Field(default=None, max_length=1000)


class ReportCreateRequest(StrictModel):
    title: str | None = Field(default=None, max_length=200)


class ReportJobRequest(StrictModel):
    input_file_id: str
    attributes: dict[str, Any] = Field(default_factory=dict)
