from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "maintenance"


class Base(DeclarativeBase):
    pass


class MaintenanceOrder(Base):
    __tablename__ = "maintenance_orders"
    __table_args__ = ({"schema": SCHEMA},)
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        unique=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    property_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    lease_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reference: Mapped[str] = mapped_column(Text, unique=True)
    summary: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(Text, default="normal")
    status: Mapped[str] = mapped_column(Text, default="open")
    reported_by_party_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reported_by_subject_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    assigned_staff_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    assigned_by_staff_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vendor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    next_event_sequence: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MaintenanceEvent(Base):
    __tablename__ = "maintenance_events"
    __table_args__ = (
        UniqueConstraint("order_id", "sequence_no"),
        UniqueConstraint("order_id", "client_message_id"),
        {"schema": SCHEMA},
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        unique=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    order_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.maintenance_orders.id"))
    sequence_no: Mapped[int] = mapped_column(BigInteger)
    actor_staff_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    actor_subject_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    actor_type: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str | None] = mapped_column(Text)
    client_message_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("actor_subject_id", "operation", "idempotency_key"),
        {"schema": SCHEMA},
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    actor_subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    operation: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    resource_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = ({"schema": SCHEMA},)
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), unique=True, default=uuid4
    )
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SubjectDeletionRecord(Base):
    __tablename__ = "subject_deletion_records"
    __table_args__ = ({"schema": SCHEMA},)
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(Text)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
