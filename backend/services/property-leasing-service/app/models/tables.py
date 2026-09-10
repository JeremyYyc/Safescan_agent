from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Identity, Integer,
                        Numeric, String, Text, UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


SCHEMA = "property_leasing"


class Base(DeclarativeBase):
    pass


class PublicMixin:
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True, default=uuid4,
                                            server_default=func.gen_random_uuid())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                  onupdate=func.now())


class Building(PublicMixin, Base):
    __tablename__ = "buildings"
    __table_args__ = ({"schema": SCHEMA},)
    reference: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    address: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text, default="Australia/Sydney")
    status: Mapped[str] = mapped_column(Text, default="active")
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Property(PublicMixin, Base):
    __tablename__ = "properties"
    __table_args__ = ({"schema": SCHEMA},)
    building_id: Mapped[int | None] = mapped_column(ForeignKey(f"{SCHEMA}.buildings.id"))
    reference: Mapped[str] = mapped_column(Text, unique=True)
    address: Mapped[str] = mapped_column(Text)
    bedrooms: Mapped[int] = mapped_column(Integer)
    bathrooms: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    parking_spaces: Mapped[int | None] = mapped_column(Integer)
    floor_area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    display_image_urls: Mapped[list[str]] = mapped_column(JSONB, default=list)
    floorplan_url: Mapped[str | None] = mapped_column(Text)
    weekly_rent: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="AUD")
    status: Mapped[str] = mapped_column(Text)
    listing_visibility: Mapped[str] = mapped_column(Text)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class StaffBuildingScope(Base):
    __tablename__ = "staff_building_scopes"
    __table_args__ = ({"schema": SCHEMA},)
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    staff_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    building_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.buildings.id"))
    scope_role: Mapped[str] = mapped_column(Text)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_by_subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StaffPropertyScope(Base):
    __tablename__ = "staff_property_scopes"
    __table_args__ = ({"schema": SCHEMA},)
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    staff_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    property_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.properties.id"))
    access_level: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_by_subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Party(PublicMixin, Base):
    __tablename__ = "parties"
    __table_args__ = ({"schema": SCHEMA},)
    party_type: Mapped[str] = mapped_column(Text, default="person")
    subject_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    contact: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(Text, default="active")


class ProspectCase(PublicMixin, Base):
    __tablename__ = "prospect_cases"
    __table_args__ = ({"schema": SCHEMA},)
    prospect_party_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.parties.id"))
    property_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.properties.id"))
    assigned_consultant_staff_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    stage: Mapped[str] = mapped_column(Text, default="new")
    status: Mapped[str] = mapped_column(Text, default="open")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    converted_lease_id: Mapped[int | None] = mapped_column(ForeignKey(f"{SCHEMA}.leases.id"))
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)


class ProspectCaseEvent(Base):
    __tablename__ = "prospect_case_events"
    __table_args__ = (UniqueConstraint("prospect_case_id", "sequence_no"), {"schema": SCHEMA})
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    prospect_case_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.prospect_cases.id"))
    sequence_no: Mapped[int] = mapped_column(BigInteger)
    event_type: Mapped[str] = mapped_column(Text)
    from_stage: Mapped[str | None] = mapped_column(Text)
    to_stage: Mapped[str | None] = mapped_column(Text)
    actor_subject_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    details_redacted: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContactThread(Base):
    __tablename__ = "prospect_contact_threads"
    __table_args__ = ({"schema": SCHEMA},)
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True, default=uuid4,
                                            server_default=func.gen_random_uuid())
    prospect_case_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.prospect_cases.id"))
    assigned_consultant_staff_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(Text, default="active")
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_sequence: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContactMessage(Base):
    __tablename__ = "prospect_contact_messages"
    __table_args__ = (UniqueConstraint("thread_id", "sequence_no"), {"schema": SCHEMA})
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.prospect_contact_threads.id"))
    sequence_no: Mapped[int] = mapped_column(BigInteger)
    sender_type: Mapped[str] = mapped_column(Text)
    sender_subject_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    sender_staff_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="sent")
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    client_message_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Application(PublicMixin, Base):
    __tablename__ = "tenancy_applications"
    __table_args__ = ({"schema": SCHEMA},)
    prospect_case_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.prospect_cases.id"))
    property_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.properties.id"))
    applicant_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.parties.id"))
    reference: Mapped[str] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(Text, default="draft")
    desired_start_on: Mapped[date] = mapped_column(Date)
    term_months: Mapped[int] = mapped_column(Integer)
    occupants: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_reason: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    winning_lease_id: Mapped[int | None] = mapped_column(ForeignKey(f"{SCHEMA}.leases.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)


class Lease(PublicMixin, Base):
    __tablename__ = "leases"
    __table_args__ = ({"schema": SCHEMA},)
    application_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.tenancy_applications.id"), unique=True)
    property_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.properties.id"))
    reference: Mapped[str] = mapped_column(Text, unique=True)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    weekly_rent: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(Text, default="draft")
    offer_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tenant_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    company_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)


class LeaseTenant(Base):
    __tablename__ = "lease_tenants"
    __table_args__ = (UniqueConstraint("lease_id"), {"schema": SCHEMA})
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    lease_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.leases.id"))
    party_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.parties.id"))
    signing_status: Mapped[str] = mapped_column(Text, default="pending")
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LeaseDocument(Base):
    __tablename__ = "lease_documents"
    __table_args__ = (UniqueConstraint("lease_id", "version"), {"schema": SCHEMA})
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True, default=uuid4)
    lease_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.leases.id"))
    version: Mapped[int] = mapped_column(Integer)
    terms_payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    terms_digest: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="issued")
    created_by_subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LeaseSignatureEvent(Base):
    __tablename__ = "lease_signature_events"
    __table_args__ = (UniqueConstraint("lease_id", "lease_document_id", "side"), {"schema": SCHEMA})
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    lease_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.leases.id"))
    lease_document_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.lease_documents.id"))
    signer_subject_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    signer_staff_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    side: Mapped[str] = mapped_column(Text)
    terms_digest: Mapped[str] = mapped_column(Text)
    ip_hash: Mapped[str | None] = mapped_column(Text)
    user_agent_hash: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CustomerLeaseSlot(Base):
    __tablename__ = "customer_lease_slots"
    __table_args__ = ({"schema": SCHEMA},)
    customer_subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    lease_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.leases.id"), unique=True)
    status: Mapped[str] = mapped_column(Text)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("actor_subject_id", "operation", "idempotency_key"),
                      {"schema": SCHEMA})
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    actor_subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    operation: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    resource_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CustomerEventVersion(Base):
    __tablename__ = "customer_event_versions"
    __table_args__ = ({"schema": SCHEMA},)
    customer_subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    aggregate_version: Mapped[int] = mapped_column(BigInteger, default=0)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = ({"schema": SCHEMA},)
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(Text)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    aggregate_type: Mapped[str] = mapped_column(Text)
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    aggregate_version: Mapped[int] = mapped_column(Integer)
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RentInvoice(Base):
    __tablename__ = "rent_invoices"
    __table_args__ = ({"schema": SCHEMA},)
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    lease_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.leases.id"))
    reference: Mapped[str] = mapped_column(Text)
    due_on: Mapped[date] = mapped_column(Date)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
