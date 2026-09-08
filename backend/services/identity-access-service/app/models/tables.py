"""Runtime table mappings owned by identity-access-service.

Schema creation remains in the platform Alembic chain during the service-split
migration. These mappings deliberately include only identity_access objects.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


SCHEMA = "identity_access"
metadata = sa.MetaData(schema=SCHEMA)


def timestamps(*, updated: bool = True):
    columns = [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)]
    if updated:
        columns.append(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    return columns


users = sa.Table(
    "users", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("public_id", UUID(as_uuid=True), nullable=False),
    sa.Column("email", sa.Text, nullable=False),
    sa.Column("account_type", sa.Text, nullable=False),
    sa.Column("username", sa.Text, nullable=False),
    sa.Column("avatar", sa.Text, nullable=False),
    sa.Column("locale", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("email_verified_at", sa.DateTime(timezone=True)),
    sa.Column("auth_version", sa.Integer, nullable=False),
    sa.Column("version", sa.Integer, nullable=False),
    *timestamps(),
)

user_credentials = sa.Table(
    "user_credentials", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("user_id", sa.BigInteger, nullable=False),
    sa.Column("credential_type", sa.Text, nullable=False),
    sa.Column("secret_hash", sa.Text, nullable=False),
    sa.Column("algorithm", sa.Text, nullable=False),
    sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("failed_attempts", sa.Integer, nullable=False),
    sa.Column("locked_until", sa.DateTime(timezone=True)),
    sa.Column("status", sa.Text, nullable=False),
    *timestamps(),
)

roles = sa.Table(
    "roles", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("public_id", UUID(as_uuid=True), nullable=False),
    sa.Column("code", sa.Text, nullable=False),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("version", sa.Integer, nullable=False),
    *timestamps(),
)

permissions = sa.Table(
    "permissions", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("code", sa.Text, nullable=False),
    sa.Column("description", sa.Text, nullable=False),
    sa.Column("risk_level", sa.Text, nullable=False),
    *timestamps(updated=False),
)

role_permissions = sa.Table(
    "role_permissions", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("role_id", sa.BigInteger, nullable=False),
    sa.Column("permission_id", sa.BigInteger, nullable=False),
    *timestamps(updated=False),
)

staff = sa.Table(
    "staff", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("public_id", UUID(as_uuid=True), nullable=False),
    sa.Column("user_id", sa.BigInteger, nullable=False),
    sa.Column("role_id", sa.BigInteger, nullable=False),
    sa.Column("staff_code", sa.Text, nullable=False),
    sa.Column("display_name", sa.Text, nullable=False),
    sa.Column("employment_status", sa.Text, nullable=False),
    sa.Column("hired_at", sa.DateTime(timezone=True)),
    sa.Column("ended_at", sa.DateTime(timezone=True)),
    *timestamps(),
)

staff_role_history = sa.Table(
    "staff_role_history", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("staff_id", sa.BigInteger, nullable=False),
    sa.Column("from_role_id", sa.BigInteger),
    sa.Column("to_role_id", sa.BigInteger, nullable=False),
    sa.Column("changed_by_staff_id", sa.BigInteger, nullable=False),
    sa.Column("reason", sa.Text),
    sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
    *timestamps(updated=False),
)

customer_profiles = sa.Table(
    "customer_profiles", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("user_id", sa.BigInteger, nullable=False),
    sa.Column("customer_status", sa.Text, nullable=False),
    sa.Column("status_version", sa.Integer, nullable=False),
    sa.Column("first_prospect_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("tenant_since", sa.DateTime(timezone=True)),
    sa.Column("former_tenant_at", sa.DateTime(timezone=True)),
    *timestamps(),
)

customer_status_events = sa.Table(
    "customer_status_events", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("customer_id", sa.BigInteger, nullable=False),
    sa.Column("from_status", sa.Text),
    sa.Column("to_status", sa.Text, nullable=False),
    sa.Column("reason_code", sa.Text, nullable=False),
    sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("source_event_id", UUID(as_uuid=True)),
    sa.Column("actor_subject_id", UUID(as_uuid=True)),
    sa.Column("details_redacted", JSONB, nullable=False),
    *timestamps(updated=False),
)

auth_sessions = sa.Table(
    "auth_sessions", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("public_id", UUID(as_uuid=True), nullable=False),
    sa.Column("user_id", sa.BigInteger, nullable=False),
    sa.Column("device_label", sa.Text),
    sa.Column("user_agent_hash", sa.Text),
    sa.Column("ip_hash", sa.Text),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("revoked_at", sa.DateTime(timezone=True)),
    sa.Column("revoke_reason", sa.Text),
    *timestamps(),
)

refresh_tokens = sa.Table(
    "refresh_tokens", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("session_id", sa.BigInteger, nullable=False),
    sa.Column("family_id", UUID(as_uuid=True), nullable=False),
    sa.Column("token_hash", sa.Text, nullable=False),
    sa.Column("parent_token_id", sa.BigInteger),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("used_at", sa.DateTime(timezone=True)),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("replaced_by_token_id", sa.BigInteger),
    *timestamps(updated=False),
)

account_action_tokens = sa.Table(
    "account_action_tokens", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("public_id", UUID(as_uuid=True), nullable=False),
    sa.Column("user_id", sa.BigInteger, nullable=False),
    sa.Column("purpose", sa.Text, nullable=False),
    sa.Column("token_hash", sa.Text, nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("used_at", sa.DateTime(timezone=True)),
    sa.Column("revoked_at", sa.DateTime(timezone=True)),
    sa.Column("requested_ip_hash", sa.Text),
    *timestamps(updated=False),
)

guest_sessions = sa.Table(
    "guest_sessions", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("public_id", UUID(as_uuid=True), nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("claimed_by_user_id", sa.BigInteger),
    sa.Column("claimed_at", sa.DateTime(timezone=True)),
    *timestamps(),
)

service_clients = sa.Table(
    "service_clients", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("client_code", sa.Text, nullable=False),
    sa.Column("credential_ref", sa.Text, nullable=False),
    sa.Column("allowed_audiences", JSONB, nullable=False),
    sa.Column("allowed_scopes", JSONB, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("key_id", sa.Text),
    sa.Column("version", sa.Integer, nullable=False),
    *timestamps(),
)

auth_events = sa.Table(
    "auth_events", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("user_id", sa.BigInteger),
    sa.Column("session_id", sa.BigInteger),
    sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("ip_hash", sa.Text),
    sa.Column("user_agent_hash", sa.Text),
    sa.Column("correlation_id", UUID(as_uuid=True), nullable=False),
    sa.Column("details_redacted", JSONB, nullable=False),
    *timestamps(updated=False),
)

outbox_events = sa.Table(
    "outbox_events", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("event_id", UUID(as_uuid=True), nullable=False),
    sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("schema_version", sa.Integer, nullable=False),
    sa.Column("aggregate_type", sa.Text, nullable=False),
    sa.Column("aggregate_id", UUID(as_uuid=True), nullable=False),
    sa.Column("aggregate_version", sa.Integer, nullable=False),
    sa.Column("correlation_id", UUID(as_uuid=True), nullable=False),
    sa.Column("payload", JSONB, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("attempts", sa.Integer, nullable=False),
    sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("delivered_at", sa.DateTime(timezone=True)),
    *timestamps(),
)

inbox_events = sa.Table(
    "inbox_events", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("event_id", UUID(as_uuid=True), nullable=False),
    sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("consumer", sa.Text, nullable=False),
    sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("processed_at", sa.DateTime(timezone=True)),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("error_code", sa.Text),
    *timestamps(),
)
