"""Target PostgreSQL metadata for the single-company microservice database split.

Local development may host these service-owned schemas in one PostgreSQL database.
Cross-service references are UUID values without database foreign keys.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)
SERVICE_SCHEMAS = (
    "identity_access",
    "property_leasing",
    "maintenance",
    "inspection_report",
    "knowledge",
    "staff_agent",
)


def pk() -> sa.Column:
    return sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True)


def public_id() -> sa.Column:
    return sa.Column(
        "public_id",
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )


def updated_at() -> sa.Column:
    return sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )


def json_object(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        JSONB,
        nullable=nullable,
        server_default=None if nullable else sa.text("'{}'::jsonb"),
    )


def fk(
    name: str,
    target: str,
    *,
    nullable: bool = False,
    ondelete: str = "CASCADE",
) -> sa.Column:
    return sa.Column(
        name,
        sa.BigInteger,
        sa.ForeignKey(target, ondelete=ondelete),
        nullable=nullable,
        index=True,
    )


# identity_access: a unique email account is either staff or customer.
users = sa.Table(
    "users",
    metadata,
    pk(),
    public_id(),
    sa.Column("email", sa.Text, nullable=False),
    sa.Column("account_type", sa.Text, nullable=False),
    sa.Column("username", sa.Text, nullable=False),
    sa.Column("avatar", sa.Text, nullable=False, server_default=""),
    sa.Column("locale", sa.Text, nullable=False, server_default="zh-CN"),
    sa.Column("status", sa.Text, nullable=False, server_default="pending"),
    sa.Column("email_verified_at", sa.DateTime(timezone=True)),
    sa.Column("auth_version", sa.Integer, nullable=False, server_default="1"),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    created_at(),
    updated_at(),
    sa.CheckConstraint("email = lower(btrim(email))", name="email_normalized"),
    sa.CheckConstraint("account_type IN ('staff','customer')", name="account_type_valid"),
    sa.CheckConstraint("status IN ('pending','active','suspended','deleted')", name="status_valid"),
    sa.CheckConstraint("auth_version > 0", name="auth_version_positive"),
    sa.CheckConstraint("version > 0", name="version_positive"),
    sa.CheckConstraint("length(locale) BETWEEN 2 AND 20", name="locale_length_valid"),
    schema="identity_access",
)
sa.Index("uq_identity_users_email", sa.func.lower(sa.func.btrim(users.c.email)), unique=True)

roles = sa.Table(
    "roles",
    metadata,
    pk(),
    public_id(),
    sa.Column("code", sa.Text, nullable=False, unique=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="active"),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    created_at(),
    updated_at(),
    sa.CheckConstraint("status IN ('active','disabled')", name="status_valid"),
    sa.CheckConstraint("version > 0", name="version_positive"),
    schema="identity_access",
)

permissions = sa.Table(
    "permissions",
    metadata,
    pk(),
    sa.Column("code", sa.Text, nullable=False, unique=True),
    sa.Column("description", sa.Text, nullable=False),
    sa.Column("risk_level", sa.Text, nullable=False, server_default="normal"),
    created_at(),
    sa.CheckConstraint("risk_level IN ('low','normal','high')", name="risk_level_valid"),
    schema="identity_access",
)

role_permissions = sa.Table(
    "role_permissions",
    metadata,
    pk(),
    fk("role_id", "identity_access.roles.id"),
    fk("permission_id", "identity_access.permissions.id"),
    created_at(),
    sa.UniqueConstraint("role_id", "permission_id"),
    schema="identity_access",
)

staff = sa.Table(
    "staff",
    metadata,
    pk(),
    public_id(),
    fk("user_id", "identity_access.users.id", ondelete="RESTRICT"),
    fk("role_id", "identity_access.roles.id", ondelete="RESTRICT"),
    sa.Column("staff_code", sa.Text, nullable=False, unique=True),
    sa.Column("display_name", sa.Text, nullable=False),
    sa.Column("employment_status", sa.Text, nullable=False, server_default="pending"),
    sa.Column("hired_at", sa.DateTime(timezone=True)),
    sa.Column("ended_at", sa.DateTime(timezone=True)),
    created_at(),
    updated_at(),
    sa.UniqueConstraint("user_id"),
    sa.CheckConstraint(
        "employment_status IN ('pending','active','on_leave','ended')",
        name="employment_status_valid",
    ),
    sa.CheckConstraint(
        "employment_status <> 'ended' OR ended_at IS NOT NULL",
        name="ended_has_timestamp",
    ),
    schema="identity_access",
)
sa.Index("ix_identity_staff_role_status", staff.c.role_id, staff.c.employment_status, staff.c.id)

staff_role_history = sa.Table(
    "staff_role_history",
    metadata,
    pk(),
    fk("staff_id", "identity_access.staff.id", ondelete="RESTRICT"),
    fk("from_role_id", "identity_access.roles.id", nullable=True, ondelete="RESTRICT"),
    fk("to_role_id", "identity_access.roles.id", ondelete="RESTRICT"),
    fk("changed_by_staff_id", "identity_access.staff.id", ondelete="RESTRICT"),
    sa.Column("reason", sa.Text),
    sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
    created_at(),
    schema="identity_access",
)
sa.Index(
    "ix_identity_staff_role_history_recent",
    staff_role_history.c.staff_id,
    staff_role_history.c.effective_at.desc(),
    staff_role_history.c.id.desc(),
)

customer_profiles = sa.Table(
    "customer_profiles",
    metadata,
    pk(),
    fk("user_id", "identity_access.users.id", ondelete="RESTRICT"),
    sa.Column("customer_status", sa.Text, nullable=False, server_default="prospect"),
    sa.Column("status_version", sa.Integer, nullable=False, server_default="1"),
    sa.Column(
        "first_prospect_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    ),
    sa.Column("tenant_since", sa.DateTime(timezone=True)),
    sa.Column("former_tenant_at", sa.DateTime(timezone=True)),
    created_at(),
    updated_at(),
    sa.UniqueConstraint("user_id"),
    sa.CheckConstraint(
        "customer_status IN ('prospect','tenant','former_tenant')",
        name="customer_status_valid",
    ),
    sa.CheckConstraint("status_version > 0", name="status_version_positive"),
    schema="identity_access",
)
sa.Index(
    "ix_identity_customer_status_recent",
    customer_profiles.c.customer_status,
    customer_profiles.c.updated_at.desc(),
    customer_profiles.c.id.desc(),
)

customer_status_events = sa.Table(
    "customer_status_events",
    metadata,
    pk(),
    fk("customer_id", "identity_access.customer_profiles.id", ondelete="RESTRICT"),
    sa.Column("from_status", sa.Text),
    sa.Column("to_status", sa.Text, nullable=False),
    sa.Column("reason_code", sa.Text, nullable=False),
    sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("source_event_id", UUID(as_uuid=True)),
    sa.Column("actor_subject_id", UUID(as_uuid=True)),
    json_object("details_redacted"),
    created_at(),
    sa.CheckConstraint(
        "to_status IN ('prospect','tenant','former_tenant')",
        name="to_status_valid",
    ),
    schema="identity_access",
)
sa.Index(
    "uq_identity_customer_status_source_event",
    customer_status_events.c.source_event_id,
    unique=True,
    postgresql_where=customer_status_events.c.source_event_id.is_not(None),
)
sa.Index(
    "ix_identity_customer_status_timeline",
    customer_status_events.c.customer_id,
    customer_status_events.c.effective_at,
    customer_status_events.c.id,
)

user_credentials = sa.Table(
    "user_credentials",
    metadata,
    pk(),
    fk("user_id", "identity_access.users.id", ondelete="CASCADE"),
    sa.Column("credential_type", sa.Text, nullable=False, server_default="password"),
    sa.Column("secret_hash", sa.Text, nullable=False),
    sa.Column("algorithm", sa.Text, nullable=False),
    sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("failed_attempts", sa.Integer, nullable=False, server_default="0"),
    sa.Column("locked_until", sa.DateTime(timezone=True)),
    sa.Column("status", sa.Text, nullable=False, server_default="active"),
    created_at(),
    updated_at(),
    sa.UniqueConstraint("user_id", "credential_type"),
    sa.CheckConstraint("credential_type IN ('password')", name="credential_type_valid"),
    sa.CheckConstraint("status IN ('active','revoked')", name="status_valid"),
    sa.CheckConstraint("failed_attempts >= 0", name="failed_attempts_nonnegative"),
    schema="identity_access",
)

auth_sessions = sa.Table(
    "auth_sessions",
    metadata,
    pk(),
    public_id(),
    fk("user_id", "identity_access.users.id", ondelete="CASCADE"),
    sa.Column("device_label", sa.Text),
    sa.Column("user_agent_hash", sa.Text),
    sa.Column("ip_hash", sa.Text),
    sa.Column("status", sa.Text, nullable=False, server_default="active"),
    sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("revoked_at", sa.DateTime(timezone=True)),
    sa.Column("revoke_reason", sa.Text),
    created_at(),
    updated_at(),
    sa.CheckConstraint("status IN ('active','revoked','expired')", name="status_valid"),
    sa.CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
    schema="identity_access",
)
sa.Index(
    "ix_identity_auth_sessions_user_status_expiry",
    auth_sessions.c.user_id,
    auth_sessions.c.status,
    auth_sessions.c.expires_at,
    auth_sessions.c.id,
)

refresh_tokens = sa.Table(
    "refresh_tokens",
    metadata,
    pk(),
    fk("session_id", "identity_access.auth_sessions.id"),
    sa.Column("family_id", UUID(as_uuid=True), nullable=False),
    sa.Column("token_hash", sa.Text, nullable=False, unique=True),
    fk("parent_token_id", "identity_access.refresh_tokens.id", nullable=True, ondelete="SET NULL"),
    sa.Column("status", sa.Text, nullable=False, server_default="active"),
    sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("used_at", sa.DateTime(timezone=True)),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    fk("replaced_by_token_id", "identity_access.refresh_tokens.id", nullable=True, ondelete="SET NULL"),
    created_at(),
    sa.CheckConstraint(
        "status IN ('active','rotated','revoked','reused','expired')",
        name="status_valid",
    ),
    sa.CheckConstraint("expires_at > issued_at", name="expiry_after_issue"),
    schema="identity_access",
)
sa.Index(
    "uq_identity_refresh_one_active_per_session",
    refresh_tokens.c.session_id,
    unique=True,
    postgresql_where=refresh_tokens.c.status == "active",
)
sa.Index(
    "ix_identity_refresh_family",
    refresh_tokens.c.session_id,
    refresh_tokens.c.family_id,
    refresh_tokens.c.status,
    refresh_tokens.c.expires_at,
)

account_action_tokens = sa.Table(
    "account_action_tokens",
    metadata,
    pk(),
    public_id(),
    fk("user_id", "identity_access.users.id", ondelete="CASCADE"),
    sa.Column("purpose", sa.Text, nullable=False),
    sa.Column("token_hash", sa.Text, nullable=False, unique=True),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("used_at", sa.DateTime(timezone=True)),
    sa.Column("revoked_at", sa.DateTime(timezone=True)),
    sa.Column("requested_ip_hash", sa.Text),
    created_at(),
    sa.CheckConstraint(
        "purpose IN ('email_verify','password_reset','staff_activate')",
        name="purpose_valid",
    ),
    sa.CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
    schema="identity_access",
)
sa.Index(
    "uq_identity_action_one_active_purpose",
    account_action_tokens.c.user_id,
    account_action_tokens.c.purpose,
    unique=True,
    postgresql_where=sa.and_(
        account_action_tokens.c.used_at.is_(None),
        account_action_tokens.c.revoked_at.is_(None),
    ),
)
sa.Index(
    "ix_identity_action_expiry",
    account_action_tokens.c.expires_at,
    account_action_tokens.c.id,
    postgresql_where=sa.and_(
        account_action_tokens.c.used_at.is_(None),
        account_action_tokens.c.revoked_at.is_(None),
    ),
)

guest_sessions = sa.Table(
    "guest_sessions",
    metadata,
    pk(),
    public_id(),
    sa.Column("status", sa.Text, nullable=False, server_default="active"),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    fk("claimed_by_user_id", "identity_access.users.id", nullable=True, ondelete="SET NULL"),
    sa.Column("claimed_at", sa.DateTime(timezone=True)),
    created_at(),
    updated_at(),
    sa.CheckConstraint("status IN ('active','claimed','expired','revoked')", name="status_valid"),
    schema="identity_access",
)
sa.Index(
    "ix_identity_guest_active_expiry",
    guest_sessions.c.expires_at,
    guest_sessions.c.id,
    postgresql_where=guest_sessions.c.status == "active",
)

service_clients = sa.Table(
    "service_clients",
    metadata,
    pk(),
    sa.Column("client_code", sa.Text, nullable=False, unique=True),
    sa.Column("credential_ref", sa.Text, nullable=False),
    sa.Column("allowed_audiences", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    sa.Column("allowed_scopes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    sa.Column("status", sa.Text, nullable=False, server_default="active"),
    sa.Column("key_id", sa.Text),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    created_at(),
    updated_at(),
    sa.CheckConstraint("status IN ('active','disabled')", name="status_valid"),
    sa.CheckConstraint("version > 0", name="version_positive"),
    schema="identity_access",
)

auth_events = sa.Table(
    "auth_events",
    metadata,
    pk(),
    fk("user_id", "identity_access.users.id", nullable=True, ondelete="SET NULL"),
    fk("session_id", "identity_access.auth_sessions.id", nullable=True, ondelete="SET NULL"),
    sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("ip_hash", sa.Text),
    sa.Column("user_agent_hash", sa.Text),
    sa.Column("correlation_id", UUID(as_uuid=True), nullable=False),
    json_object("details_redacted"),
    created_at(),
    schema="identity_access",
)
sa.Index("ix_identity_auth_events_recent", auth_events.c.user_id, auth_events.c.occurred_at.desc(), auth_events.c.id.desc())


# property_leasing: service-local FKs, cross-service subjects/staff as UUID refs.
buildings = sa.Table(
    "buildings", metadata, pk(), public_id(),
    sa.Column("reference", sa.Text, nullable=False, unique=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("address", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="active"),
    json_object("attributes"), created_at(), updated_at(),
    sa.CheckConstraint("status IN ('active','inactive')", name="status_valid"),
    schema="property_leasing",
)

properties = sa.Table(
    "properties", metadata, pk(), public_id(),
    fk("building_id", "property_leasing.buildings.id", nullable=True, ondelete="SET NULL"),
    sa.Column("reference", sa.Text, nullable=False, unique=True),
    sa.Column("address", sa.Text, nullable=False),
    sa.Column("bedrooms", sa.Integer, nullable=False, server_default="0"),
    sa.Column("bathrooms", sa.Numeric(5, 1), nullable=False, server_default="0"),
    sa.Column("weekly_rent", sa.Numeric(14, 2), nullable=False),
    sa.Column("currency", sa.String(3), nullable=False, server_default="AUD"),
    sa.Column("status", sa.Text, nullable=False, server_default="draft"),
    sa.Column("listing_visibility", sa.Text, nullable=False, server_default="private"),
    json_object("attributes"), created_at(), updated_at(),
    sa.CheckConstraint("bedrooms >= 0 AND bathrooms >= 0 AND weekly_rent >= 0", name="values_nonnegative"),
    sa.CheckConstraint("status IN ('draft','vacant','marketing','under_offer','occupied','maintenance','inactive')", name="status_valid"),
    sa.CheckConstraint("listing_visibility IN ('private','staff','public')", name="visibility_valid"),
    schema="property_leasing",
)
sa.Index("ix_property_listing", properties.c.listing_visibility, properties.c.status, properties.c.id)

staff_building_scopes = sa.Table(
    "staff_building_scopes", metadata, pk(),
    sa.Column("staff_id", UUID(as_uuid=True), nullable=False),
    fk("building_id", "property_leasing.buildings.id", ondelete="RESTRICT"),
    sa.Column("scope_role", sa.Text, nullable=False),
    sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
    sa.Column("valid_until", sa.DateTime(timezone=True)),
    sa.Column("assigned_by_subject_id", UUID(as_uuid=True), nullable=False),
    created_at(), updated_at(),
    sa.UniqueConstraint("staff_id", "building_id", "scope_role", "valid_from"),
    sa.CheckConstraint("scope_role IN ('primary_manager','support_manager','maintenance_support')", name="scope_role_valid"),
    sa.CheckConstraint("valid_until IS NULL OR valid_until > valid_from", name="valid_period"),
    schema="property_leasing",
)
sa.Index("ix_property_staff_building_scope", staff_building_scopes.c.staff_id, staff_building_scopes.c.building_id, staff_building_scopes.c.valid_from, staff_building_scopes.c.valid_until)

staff_property_scopes = sa.Table(
    "staff_property_scopes", metadata, pk(),
    sa.Column("staff_id", UUID(as_uuid=True), nullable=False),
    fk("property_id", "property_leasing.properties.id", ondelete="RESTRICT"),
    sa.Column("access_level", sa.Text, nullable=False),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
    sa.Column("valid_until", sa.DateTime(timezone=True)),
    sa.Column("assigned_by_subject_id", UUID(as_uuid=True), nullable=False),
    created_at(), updated_at(),
    sa.CheckConstraint("access_level IN ('read','manage')", name="access_level_valid"),
    sa.CheckConstraint("valid_until IS NULL OR valid_until > valid_from", name="valid_period"),
    schema="property_leasing",
)
sa.Index("ix_property_staff_property_scope", staff_property_scopes.c.staff_id, staff_property_scopes.c.property_id, staff_property_scopes.c.valid_from, staff_property_scopes.c.valid_until)

parties = sa.Table(
    "parties", metadata, pk(), public_id(),
    sa.Column("party_type", sa.Text, nullable=False),
    sa.Column("subject_id", UUID(as_uuid=True)),
    sa.Column("name", sa.Text, nullable=False),
    json_object("contact"),
    sa.Column("status", sa.Text, nullable=False, server_default="active"),
    created_at(), updated_at(),
    sa.CheckConstraint("party_type IN ('person','company')", name="party_type_valid"),
    sa.CheckConstraint("status IN ('active','inactive')", name="status_valid"),
    schema="property_leasing",
)
sa.Index("uq_property_parties_subject", parties.c.subject_id, unique=True, postgresql_where=parties.c.subject_id.is_not(None))

property_owners = sa.Table(
    "property_owners", metadata, pk(),
    fk("property_id", "property_leasing.properties.id", ondelete="RESTRICT"),
    fk("party_id", "property_leasing.parties.id", ondelete="RESTRICT"),
    sa.Column("share", sa.Numeric(7, 6), nullable=False), created_at(), updated_at(),
    sa.UniqueConstraint("property_id", "party_id"),
    sa.CheckConstraint("share > 0 AND share <= 1", name="share_valid"),
    schema="property_leasing",
)

leases = sa.Table(
    "leases", metadata, pk(), public_id(),
    fk("property_id", "property_leasing.properties.id", ondelete="RESTRICT"),
    sa.Column("reference", sa.Text, nullable=False, unique=True),
    sa.Column("starts_on", sa.Date, nullable=False),
    sa.Column("ends_on", sa.Date, nullable=False),
    sa.Column("weekly_rent", sa.Numeric(14, 2), nullable=False),
    sa.Column("currency", sa.String(3), nullable=False, server_default="AUD"),
    sa.Column("status", sa.Text, nullable=False, server_default="draft"),
    sa.Column("tenant_signed_at", sa.DateTime(timezone=True)),
    sa.Column("company_signed_at", sa.DateTime(timezone=True)),
    sa.Column("executed_at", sa.DateTime(timezone=True)),
    sa.Column("ended_at", sa.DateTime(timezone=True)),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    created_at(), updated_at(),
    sa.CheckConstraint("ends_on >= starts_on", name="date_range_valid"),
    sa.CheckConstraint("weekly_rent >= 0", name="rent_nonnegative"),
    sa.CheckConstraint("status IN ('draft','pending_signature','executed','active','ended','terminated','cancelled')", name="status_valid"),
    sa.CheckConstraint("version > 0", name="version_positive"),
    sa.CheckConstraint("executed_at IS NULL OR (tenant_signed_at IS NOT NULL AND company_signed_at IS NOT NULL AND executed_at >= tenant_signed_at AND executed_at >= company_signed_at)", name="execution_after_signatures"),
    schema="property_leasing",
)
sa.Index("ix_property_leases_property_status_end", leases.c.property_id, leases.c.status, leases.c.ends_on, leases.c.id)

prospect_cases = sa.Table(
    "prospect_cases", metadata, pk(), public_id(),
    fk("prospect_party_id", "property_leasing.parties.id", ondelete="RESTRICT"),
    sa.Column("assigned_consultant_staff_id", UUID(as_uuid=True)),
    sa.Column("stage", sa.Text, nullable=False, server_default="new"),
    sa.Column("status", sa.Text, nullable=False, server_default="open"),
    sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
    fk("converted_lease_id", "property_leasing.leases.id", nullable=True, ondelete="SET NULL"),
    sa.Column("converted_at", sa.DateTime(timezone=True)),
    sa.Column("closed_at", sa.DateTime(timezone=True)),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    created_at(), updated_at(),
    sa.CheckConstraint("stage IN ('new','contacted','viewing','application','negotiation','converted','lost')", name="stage_valid"),
    sa.CheckConstraint("status IN ('open','closed')", name="status_valid"),
    sa.CheckConstraint("version > 0", name="version_positive"),
    schema="property_leasing",
)
sa.Index("ix_property_prospect_work_queue", prospect_cases.c.assigned_consultant_staff_id, prospect_cases.c.status, prospect_cases.c.stage, prospect_cases.c.updated_at.desc(), prospect_cases.c.id.desc())

prospect_case_events = sa.Table(
    "prospect_case_events", metadata, pk(),
    fk("prospect_case_id", "property_leasing.prospect_cases.id", ondelete="RESTRICT"),
    sa.Column("sequence_no", sa.BigInteger, nullable=False),
    sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("from_stage", sa.Text), sa.Column("to_stage", sa.Text),
    sa.Column("actor_subject_id", UUID(as_uuid=True)),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    json_object("details_redacted"), created_at(),
    sa.UniqueConstraint("prospect_case_id", "sequence_no"),
    schema="property_leasing",
)

prospect_contact_threads = sa.Table(
    "prospect_contact_threads", metadata, pk(),
    fk("prospect_case_id", "property_leasing.prospect_cases.id", ondelete="RESTRICT"),
    sa.Column("assigned_consultant_staff_id", UUID(as_uuid=True), nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="active"),
    sa.Column("last_message_at", sa.DateTime(timezone=True)),
    sa.Column("next_sequence", sa.BigInteger, nullable=False, server_default="1"),
    created_at(), updated_at(),
    sa.CheckConstraint("status IN ('active','closed')", name="status_valid"),
    sa.CheckConstraint("next_sequence > 0", name="next_sequence_positive"),
    schema="property_leasing",
)
sa.Index("uq_property_one_active_contact_thread", prospect_contact_threads.c.prospect_case_id, unique=True, postgresql_where=prospect_contact_threads.c.status == "active")

prospect_contact_messages = sa.Table(
    "prospect_contact_messages", metadata, pk(),
    fk("thread_id", "property_leasing.prospect_contact_threads.id", ondelete="RESTRICT"),
    sa.Column("sequence_no", sa.BigInteger, nullable=False),
    sa.Column("sender_type", sa.Text, nullable=False),
    sa.Column("sender_subject_id", UUID(as_uuid=True)),
    sa.Column("sender_staff_id", UUID(as_uuid=True)),
    sa.Column("content", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="sent"),
    sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("client_message_id", UUID(as_uuid=True)),
    created_at(),
    sa.UniqueConstraint("thread_id", "sequence_no"),
    sa.CheckConstraint("sender_type IN ('prospect','staff','system')", name="sender_type_valid"),
    sa.CheckConstraint("(sender_type='prospect' AND sender_subject_id IS NOT NULL AND sender_staff_id IS NULL) OR (sender_type='staff' AND sender_subject_id IS NULL AND sender_staff_id IS NOT NULL) OR (sender_type='system' AND sender_subject_id IS NULL AND sender_staff_id IS NULL)", name="sender_matches_type"),
    sa.CheckConstraint("status IN ('sent','failed','deleted')", name="status_valid"),
    schema="property_leasing",
)
sa.Index("uq_property_contact_client_message", prospect_contact_messages.c.thread_id, prospect_contact_messages.c.client_message_id, unique=True, postgresql_where=prospect_contact_messages.c.client_message_id.is_not(None))

lease_tenants = sa.Table(
    "lease_tenants", metadata, pk(),
    fk("lease_id", "property_leasing.leases.id", ondelete="RESTRICT"),
    fk("party_id", "property_leasing.parties.id", ondelete="RESTRICT"),
    sa.Column("signing_status", sa.Text, nullable=False, server_default="pending"),
    sa.Column("signed_at", sa.DateTime(timezone=True)), created_at(), updated_at(),
    sa.UniqueConstraint("lease_id", "party_id"),
    sa.CheckConstraint("signing_status IN ('pending','signed','declined','waived')", name="signing_status_valid"),
    sa.CheckConstraint("(signing_status='signed' AND signed_at IS NOT NULL) OR (signing_status<>'signed' AND signed_at IS NULL)", name="signed_time_matches_status"),
    schema="property_leasing",
)

lease_access_grants = sa.Table(
    "lease_access_grants", metadata, pk(),
    fk("lease_id", "property_leasing.leases.id", ondelete="RESTRICT"),
    fk("party_id", "property_leasing.parties.id", ondelete="RESTRICT"),
    sa.Column("subject_id", UUID(as_uuid=True), nullable=False),
    sa.Column("access_mode", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
    sa.Column("effective_until", sa.DateTime(timezone=True)),
    sa.Column("source_event_id", UUID(as_uuid=True), nullable=False, unique=True),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    created_at(), updated_at(),
    sa.UniqueConstraint("lease_id", "subject_id"),
    sa.CheckConstraint("access_mode IN ('full','read_only')", name="access_mode_valid"),
    sa.CheckConstraint("status IN ('active','expired','revoked')", name="status_valid"),
    sa.CheckConstraint("effective_until IS NULL OR effective_until > effective_from", name="effective_period"),
    sa.CheckConstraint("version > 0", name="version_positive"),
    schema="property_leasing",
)
sa.Index("ix_property_lease_grants_subject", lease_access_grants.c.subject_id, lease_access_grants.c.status, lease_access_grants.c.effective_from, lease_access_grants.c.effective_until, lease_access_grants.c.lease_id)

rent_invoices = sa.Table(
    "rent_invoices", metadata, pk(),
    fk("lease_id", "property_leasing.leases.id", ondelete="RESTRICT"),
    sa.Column("reference", sa.Text, nullable=False, unique=True),
    sa.Column("due_on", sa.Date, nullable=False),
    sa.Column("period_start", sa.Date, nullable=False),
    sa.Column("period_end", sa.Date, nullable=False),
    sa.Column("amount", sa.Numeric(14, 2), nullable=False),
    sa.Column("currency", sa.String(3), nullable=False, server_default="AUD"),
    sa.Column("status", sa.Text, nullable=False, server_default="open"),
    created_at(), updated_at(),
    sa.CheckConstraint("period_end >= period_start AND amount >= 0", name="values_valid"),
    sa.CheckConstraint("status IN ('open','part_paid','paid','void')", name="status_valid"),
    schema="property_leasing",
)
sa.Index("ix_property_invoices_lease_due", rent_invoices.c.lease_id, rent_invoices.c.due_on, rent_invoices.c.id)

payments = sa.Table(
    "payments", metadata, pk(),
    sa.Column("reference", sa.Text, nullable=False, unique=True),
    sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("amount", sa.Numeric(14, 2), nullable=False),
    sa.Column("currency", sa.String(3), nullable=False),
    sa.Column("provider_reference", sa.Text),
    created_at(),
    sa.CheckConstraint("amount > 0", name="amount_positive"),
    schema="property_leasing",
)

payment_allocations = sa.Table(
    "payment_allocations", metadata, pk(),
    fk("payment_id", "property_leasing.payments.id", ondelete="RESTRICT"),
    fk("invoice_id", "property_leasing.rent_invoices.id", ondelete="RESTRICT"),
    sa.Column("amount", sa.Numeric(14, 2), nullable=False), created_at(),
    sa.UniqueConstraint("payment_id", "invoice_id"),
    sa.CheckConstraint("amount > 0", name="amount_positive"),
    schema="property_leasing",
)

tenancy_applications = sa.Table(
    "tenancy_applications", metadata, pk(), public_id(),
    fk("prospect_case_id", "property_leasing.prospect_cases.id", ondelete="RESTRICT"),
    fk("property_id", "property_leasing.properties.id", ondelete="RESTRICT"),
    fk("applicant_id", "property_leasing.parties.id", ondelete="RESTRICT"),
    sa.Column("reference", sa.Text, nullable=False, unique=True),
    sa.Column("status", sa.Text, nullable=False, server_default="draft"),
    sa.Column("submitted_at", sa.DateTime(timezone=True)),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    created_at(), updated_at(),
    sa.CheckConstraint("status IN ('draft','submitted','reviewing','approved','rejected','withdrawn')", name="status_valid"),
    sa.CheckConstraint("version > 0", name="version_positive"),
    schema="property_leasing",
)

viewing_appointments = sa.Table(
    "viewing_appointments", metadata, pk(), public_id(),
    fk("property_id", "property_leasing.properties.id", ondelete="RESTRICT"),
    fk("prospect_id", "property_leasing.parties.id", ondelete="RESTRICT"),
    sa.Column("host_staff_id", UUID(as_uuid=True)),
    sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="scheduled"),
    sa.Column("idempotency_key", UUID(as_uuid=True), nullable=False, unique=True),
    created_at(), updated_at(),
    sa.CheckConstraint("ends_at > starts_at", name="time_range_valid"),
    sa.CheckConstraint("status IN ('scheduled','completed','cancelled','no_show')", name="status_valid"),
    schema="property_leasing",
)

property_favorites = sa.Table(
    "property_favorites", metadata, pk(),
    fk("party_id", "property_leasing.parties.id", ondelete="CASCADE"),
    fk("property_id", "property_leasing.properties.id", ondelete="CASCADE"),
    created_at(), sa.UniqueConstraint("party_id", "property_id"),
    schema="property_leasing",
)


def add_event_tables(schema: str) -> tuple[sa.Table, sa.Table]:
    outbox = sa.Table(
        "outbox_events", metadata, pk(),
        sa.Column("event_id", UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("aggregate_type", sa.Text, nullable=False),
        sa.Column("aggregate_id", UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_version", sa.Integer, nullable=False),
        sa.Column("correlation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        created_at(), updated_at(),
        sa.CheckConstraint("schema_version > 0 AND aggregate_version > 0", name="versions_positive"),
        sa.CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        sa.CheckConstraint("status IN ('pending','delivering','delivered','failed')", name="status_valid"),
        schema=schema,
    )
    sa.Index(
        f"ix_{schema}_outbox_pending".replace("_access", ""),
        outbox.c.available_at,
        outbox.c.id,
        postgresql_where=outbox.c.status == "pending",
    )
    inbox = sa.Table(
        "inbox_events", metadata, pk(),
        sa.Column("event_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("consumer", sa.Text, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Text, nullable=False, server_default="received"),
        sa.Column("error_code", sa.Text),
        created_at(), updated_at(),
        sa.UniqueConstraint("consumer", "event_id"),
        sa.CheckConstraint("status IN ('received','processed','failed')", name="status_valid"),
        schema=schema,
    )
    return outbox, inbox


identity_outbox, identity_inbox = add_event_tables("identity_access")
property_outbox, property_inbox = add_event_tables("property_leasing")


# maintenance
maintenance_orders = sa.Table(
    "maintenance_orders", metadata, pk(), public_id(),
    sa.Column("property_id", UUID(as_uuid=True), nullable=False),
    sa.Column("reference", sa.Text, nullable=False, unique=True),
    sa.Column("summary", sa.Text, nullable=False),
    sa.Column("priority", sa.Text, nullable=False, server_default="normal"),
    sa.Column("status", sa.Text, nullable=False, server_default="open"),
    sa.Column("reported_by_party_id", UUID(as_uuid=True)),
    sa.Column("assigned_staff_id", UUID(as_uuid=True)),
    sa.Column("assigned_by_staff_id", UUID(as_uuid=True)),
    sa.Column("assigned_at", sa.DateTime(timezone=True)),
    sa.Column("vendor_id", UUID(as_uuid=True)),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    created_at(), updated_at(),
    sa.CheckConstraint("priority IN ('low','normal','high','urgent')", name="priority_valid"),
    sa.CheckConstraint("status IN ('open','assigned','in_progress','blocked','completed','cancelled')", name="status_valid"),
    sa.CheckConstraint("version > 0", name="version_positive"),
    schema="maintenance",
)
sa.Index("ix_maintenance_property_status", maintenance_orders.c.property_id, maintenance_orders.c.status, maintenance_orders.c.created_at, maintenance_orders.c.id)
sa.Index("ix_maintenance_assignee_queue", maintenance_orders.c.assigned_staff_id, maintenance_orders.c.status, maintenance_orders.c.priority, maintenance_orders.c.created_at, maintenance_orders.c.id, postgresql_where=maintenance_orders.c.assigned_staff_id.is_not(None))

maintenance_events = sa.Table(
    "maintenance_events", metadata, pk(),
    fk("order_id", "maintenance.maintenance_orders.id", ondelete="RESTRICT"),
    sa.Column("actor_staff_id", UUID(as_uuid=True)),
    sa.Column("event_type", sa.Text, nullable=False),
    json_object("details"), created_at(),
    schema="maintenance",
)

maintenance_drafts = sa.Table(
    "maintenance_drafts", metadata, pk(), public_id(),
    sa.Column("task_id", UUID(as_uuid=True)),
    sa.Column("property_id", UUID(as_uuid=True), nullable=False),
    sa.Column("created_by", UUID(as_uuid=True), nullable=False),
    sa.Column("summary", sa.Text, nullable=False),
    sa.Column("priority", sa.Text, nullable=False, server_default="normal"),
    sa.Column("mode", sa.Text, nullable=False, server_default="mock"),
    sa.Column("status", sa.Text, nullable=False, server_default="simulated"),
    sa.Column("idempotency_key", UUID(as_uuid=True), nullable=False, unique=True),
    created_at(), updated_at(),
    sa.CheckConstraint("priority IN ('low','normal','high','urgent')", name="priority_valid"),
    sa.CheckConstraint("mode IN ('mock','live')", name="mode_valid"),
    sa.CheckConstraint("status IN ('simulated','discarded','draft','submitted','approved','rejected','converted')", name="status_valid"),
    sa.CheckConstraint("mode <> 'mock' OR status IN ('simulated','discarded')", name="mock_status_valid"),
    schema="maintenance",
)

approval_requests = sa.Table(
    "approval_requests", metadata, pk(), public_id(),
    fk("draft_id", "maintenance.maintenance_drafts.id", ondelete="RESTRICT"),
    sa.Column("requested_by", UUID(as_uuid=True), nullable=False),
    sa.Column("reviewer_id", UUID(as_uuid=True)),
    sa.Column("status", sa.Text, nullable=False, server_default="pending"),
    sa.Column("decision_at", sa.DateTime(timezone=True)),
    sa.Column("decision_note", sa.Text),
    created_at(), updated_at(),
    sa.CheckConstraint("status IN ('pending','approved','rejected','cancelled')", name="status_valid"),
    sa.CheckConstraint("status NOT IN ('approved','rejected') OR (reviewer_id IS NOT NULL AND decision_at IS NOT NULL)", name="decision_complete"),
    schema="maintenance",
)

maintenance_outbox, maintenance_inbox = add_event_tables("maintenance")


# inspection_report
report_workspaces = sa.Table(
    "report_workspaces", metadata, pk(), public_id(),
    sa.Column("created_by_subject_id", UUID(as_uuid=True), nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="active"),
    sa.Column("pinned", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("next_sequence", sa.BigInteger, nullable=False, server_default="1"),
    created_at(), updated_at(),
    sa.CheckConstraint("status IN ('active','archived','deleted')", name="status_valid"),
    sa.CheckConstraint("next_sequence > 0", name="next_sequence_positive"),
    schema="inspection_report",
)
sa.Index("ix_report_workspaces_owner_recent", report_workspaces.c.created_by_subject_id, report_workspaces.c.status, report_workspaces.c.last_activity_at.desc(), report_workspaces.c.id.desc())

report_workspace_messages = sa.Table(
    "report_workspace_messages", metadata, pk(),
    fk("workspace_id", "inspection_report.report_workspaces.id", ondelete="RESTRICT"),
    sa.Column("role", sa.Text, nullable=False),
    sa.Column("kind", sa.Text, nullable=False, server_default="text"),
    sa.Column("content", sa.Text, nullable=False),
    json_object("metadata_redacted"), created_at(),
    sa.CheckConstraint("role IN ('user','assistant','system')", name="role_valid"),
    sa.CheckConstraint("kind IN ('text','notice','error')", name="kind_valid"),
    schema="inspection_report",
)

files = sa.Table(
    "files", metadata, pk(), public_id(),
    sa.Column("created_by_subject_id", UUID(as_uuid=True), nullable=False),
    sa.Column("purpose", sa.Text, nullable=False),
    sa.Column("bucket", sa.Text, nullable=False),
    sa.Column("object_key", sa.Text, nullable=False),
    sa.Column("original_name", sa.Text, nullable=False, server_default=""),
    sa.Column("mime_type", sa.Text),
    sa.Column("file_size", sa.BigInteger),
    sa.Column("sha256", sa.Text),
    sa.Column("status", sa.Text, nullable=False, server_default="uploading"),
    sa.Column("scan_status", sa.Text, nullable=False, server_default="pending"),
    created_at(), updated_at(),
    sa.UniqueConstraint("bucket", "object_key"),
    sa.CheckConstraint("purpose IN ('input_video','evidence_image','uploaded_pdf','exported_pdf','other')", name="purpose_valid"),
    sa.CheckConstraint("status IN ('uploading','ready','deleted','orphaned')", name="status_valid"),
    sa.CheckConstraint("scan_status IN ('pending','clean','rejected','quarantined')", name="scan_status_valid"),
    sa.CheckConstraint("file_size IS NULL OR file_size >= 0", name="file_size_nonnegative"),
    schema="inspection_report",
)
sa.Index("ix_report_files_owner_purpose", files.c.created_by_subject_id, files.c.purpose, files.c.created_at.desc(), files.c.id.desc())

reports = sa.Table(
    "reports", metadata, pk(), public_id(),
    sa.Column("created_by_subject_id", UUID(as_uuid=True), nullable=False),
    fk("origin_workspace_id", "inspection_report.report_workspaces.id", nullable=True, ondelete="SET NULL"),
    sa.Column("report_kind", sa.Text, nullable=False),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="active"),
    sa.Column("schema_version", sa.Integer, nullable=False, server_default="1"),
    sa.Column("pipeline_version", sa.Text, nullable=False),
    sa.Column("completed_at", sa.DateTime(timezone=True)),
    created_at(), updated_at(),
    sa.CheckConstraint("report_kind IN ('analysis','pdf')", name="report_kind_valid"),
    sa.CheckConstraint("source IN ('video_analysis','uploaded_pdf','exported_pdf')", name="source_valid"),
    sa.CheckConstraint("status IN ('active','deleted')", name="status_valid"),
    sa.CheckConstraint("schema_version > 0", name="schema_version_positive"),
    schema="inspection_report",
)
sa.Index("ix_reports_owner_recent", reports.c.created_by_subject_id, reports.c.created_at.desc(), reports.c.id.desc())

report_analysis = sa.Table(
    "report_analysis", metadata,
    sa.Column("report_id", sa.BigInteger, sa.ForeignKey("inspection_report.reports.id", ondelete="CASCADE"), primary_key=True),
    fk("video_file_id", "inspection_report.files.id", nullable=True, ondelete="RESTRICT"),
    sa.Column("region_info", JSONB), sa.Column("report_payload", JSONB),
    sa.Column("validation_passed", sa.Boolean), sa.Column("validation_errors", JSONB),
    schema="inspection_report",
)

report_pdf = sa.Table(
    "report_pdf", metadata,
    sa.Column("report_id", sa.BigInteger, sa.ForeignKey("inspection_report.reports.id", ondelete="CASCADE"), primary_key=True),
    fk("file_id", "inspection_report.files.id", ondelete="RESTRICT"),
    sa.Column("pdf_kind", sa.Text, nullable=False),
    fk("derived_from_report_id", "inspection_report.reports.id", nullable=True, ondelete="SET NULL"),
    sa.Column("content_preview", sa.Text),
    sa.CheckConstraint("pdf_kind IN ('uploaded','exported')", name="pdf_kind_valid"),
    schema="inspection_report",
)

report_assets = sa.Table(
    "report_assets", metadata, pk(),
    fk("report_id", "inspection_report.reports.id", ondelete="CASCADE"),
    fk("file_id", "inspection_report.files.id", ondelete="RESTRICT"),
    sa.Column("asset_kind", sa.Text, nullable=False),
    sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
    created_at(), sa.UniqueConstraint("report_id", "file_id", "asset_kind"),
    sa.CheckConstraint("asset_kind IN ('input_video','evidence_image','exported_pdf')", name="asset_kind_valid"),
    schema="inspection_report",
)

inspections = sa.Table(
    "inspections", metadata, pk(), public_id(),
    sa.Column("property_id", UUID(as_uuid=True), nullable=False),
    sa.Column("inspector_subject_id", UUID(as_uuid=True)),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("inspected_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="planned"),
    sa.Column("summary", sa.Text), created_at(), updated_at(),
    sa.CheckConstraint("kind IN ('routine','move_in','move_out','video')", name="kind_valid"),
    sa.CheckConstraint("status IN ('planned','in_progress','completed','cancelled')", name="status_valid"),
    schema="inspection_report",
)
sa.Index("ix_inspections_property_recent", inspections.c.property_id, inspections.c.inspected_at.desc(), inspections.c.id.desc())

inspection_findings = sa.Table(
    "inspection_findings", metadata, pk(),
    fk("inspection_id", "inspection_report.inspections.id", ondelete="CASCADE"),
    sa.Column("area", sa.Text, nullable=False),
    sa.Column("description", sa.Text, nullable=False),
    sa.Column("severity", sa.Text, nullable=False),
    json_object("evidence"), created_at(),
    sa.CheckConstraint("severity IN ('info','low','medium','high','critical')", name="severity_valid"),
    schema="inspection_report",
)

inspection_reports = sa.Table(
    "inspection_reports", metadata, pk(),
    fk("inspection_id", "inspection_report.inspections.id", ondelete="CASCADE"),
    fk("report_id", "inspection_report.reports.id", ondelete="CASCADE"),
    created_at(), sa.UniqueConstraint("inspection_id", "report_id"),
    schema="inspection_report",
)

report_jobs = sa.Table(
    "report_jobs", metadata, pk(), public_id(),
    sa.Column("requested_by_subject_id", UUID(as_uuid=True), nullable=False),
    fk("workspace_id", "inspection_report.report_workspaces.id", nullable=True, ondelete="SET NULL"),
    sa.Column("source_service", sa.Text), sa.Column("source_session_id", UUID(as_uuid=True)),
    sa.Column("job_type", sa.Text, nullable=False),
    fk("input_file_id", "inspection_report.files.id", nullable=True, ondelete="RESTRICT"),
    fk("report_id", "inspection_report.reports.id", nullable=True, ondelete="SET NULL"),
    fk("inspection_id", "inspection_report.inspections.id", nullable=True, ondelete="SET NULL"),
    sa.Column("queue", sa.Text, nullable=False), sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
    sa.Column("status", sa.Text, nullable=False, server_default="queued"),
    sa.Column("attempt", sa.Integer, nullable=False, server_default="0"),
    sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
    sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("lease_until", sa.DateTime(timezone=True)), sa.Column("worker_id", sa.Text),
    sa.Column("heartbeat_at", sa.DateTime(timezone=True)), sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
    sa.Column("progress_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
    sa.Column("validation_passed", sa.Boolean),
    sa.Column("idempotency_key", UUID(as_uuid=True), nullable=False),
    sa.Column("pipeline_version", sa.Text, nullable=False),
    json_object("input_payload"),
    json_object("result_payload", nullable=True),
    sa.Column("error_code", sa.Text), sa.Column("finished_at", sa.DateTime(timezone=True)),
    created_at(), updated_at(),
    sa.UniqueConstraint("requested_by_subject_id", "idempotency_key"),
    sa.UniqueConstraint("report_id"),
    sa.CheckConstraint("job_type IN ('video_analysis','pdf_render','object_cleanup')", name="job_type_valid"),
    sa.CheckConstraint("status IN ('queued','retry_wait','running','completed','failed','cancelled')", name="status_valid"),
    sa.CheckConstraint("attempt >= 0 AND max_attempts > 0 AND progress_percent >= 0 AND progress_percent <= 100", name="counters_valid"),
    schema="inspection_report",
)
sa.Index("ix_report_jobs_available", report_jobs.c.queue, report_jobs.c.priority.desc(), report_jobs.c.available_at, report_jobs.c.id, postgresql_where=report_jobs.c.status.in_(("queued", "retry_wait")))
sa.Index("ix_report_jobs_running_lease", report_jobs.c.lease_until, report_jobs.c.id, postgresql_where=report_jobs.c.status == "running")
sa.Index(
    "uq_report_jobs_one_active_workspace",
    report_jobs.c.workspace_id,
    unique=True,
    postgresql_where=sa.and_(
        report_jobs.c.workspace_id.is_not(None),
        report_jobs.c.status.in_(("queued", "retry_wait", "running")),
    ),
)

report_job_steps = sa.Table(
    "report_job_steps", metadata, pk(),
    fk("job_id", "inspection_report.report_jobs.id", ondelete="CASCADE"),
    sa.Column("step_name", sa.Text, nullable=False), sa.Column("attempt", sa.Integer, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)),
    json_object("metrics"), sa.Column("error_code", sa.Text), created_at(), updated_at(),
    sa.UniqueConstraint("job_id", "step_name", "attempt"),
    sa.CheckConstraint("attempt > 0", name="attempt_positive"),
    schema="inspection_report",
)

report_job_events = sa.Table(
    "report_job_events", metadata, pk(),
    fk("job_id", "inspection_report.report_jobs.id", ondelete="CASCADE"),
    sa.Column("sequence_no", sa.BigInteger, nullable=False),
    sa.Column("event_type", sa.Text, nullable=False), sa.Column("stage", sa.Text, nullable=False),
    sa.Column("progress_percent", sa.Numeric(5, 2)), sa.Column("message", sa.Text),
    json_object("payload_redacted"), created_at(),
    sa.UniqueConstraint("job_id", "sequence_no"),
    sa.CheckConstraint("progress_percent IS NULL OR (progress_percent >= 0 AND progress_percent <= 100)", name="progress_valid"),
    schema="inspection_report",
)

report_workspace_items = sa.Table(
    "report_workspace_items", metadata, pk(),
    fk("workspace_id", "inspection_report.report_workspaces.id", ondelete="CASCADE"),
    sa.Column("sequence_no", sa.BigInteger, nullable=False),
    sa.Column("item_type", sa.Text, nullable=False),
    fk("message_id", "inspection_report.report_workspace_messages.id", nullable=True, ondelete="CASCADE"),
    fk("report_id", "inspection_report.reports.id", nullable=True, ondelete="CASCADE"),
    fk("job_id", "inspection_report.report_jobs.id", nullable=True, ondelete="CASCADE"),
    created_at(), sa.UniqueConstraint("workspace_id", "sequence_no"),
    sa.CheckConstraint("item_type IN ('message','report','job')", name="item_type_valid"),
    sa.CheckConstraint("num_nonnulls(message_id,report_id,job_id)=1", name="exactly_one_source"),
    schema="inspection_report",
)

inspection_outbox, inspection_inbox = add_event_tables("inspection_report")


# knowledge
knowledge_bases = sa.Table(
    "knowledge_bases", metadata, pk(), public_id(),
    sa.Column("code", sa.Text, nullable=False, unique=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("audience", sa.Text, nullable=False),
    sa.Column("retrieval_provider", sa.Text, nullable=False),
    sa.Column("external_dataset_id", sa.Text), created_at(), updated_at(),
    sa.CheckConstraint("audience IN ('staff','tenant','public')", name="audience_valid"),
    schema="knowledge",
)

knowledge_role_access = sa.Table(
    "knowledge_role_access", metadata, pk(),
    fk("knowledge_base_id", "knowledge.knowledge_bases.id", ondelete="CASCADE"),
    sa.Column("role_id", UUID(as_uuid=True), nullable=False),
    created_at(), sa.UniqueConstraint("knowledge_base_id", "role_id"),
    schema="knowledge",
)

knowledge_documents = sa.Table(
    "knowledge_documents", metadata, pk(), public_id(),
    fk("knowledge_base_id", "knowledge.knowledge_bases.id", ondelete="CASCADE"),
    sa.Column("document_key", sa.Text, nullable=False),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("file_id", UUID(as_uuid=True)), sa.Column("external_document_id", sa.Text),
    sa.Column("status", sa.Text, nullable=False, server_default="draft"),
    created_at(), updated_at(),
    sa.UniqueConstraint("knowledge_base_id", "document_key", "version"),
    sa.CheckConstraint("version > 0", name="version_positive"),
    sa.CheckConstraint("status IN ('draft','published','archived')", name="status_valid"),
    schema="knowledge",
)
sa.Index("ix_knowledge_documents_lookup", knowledge_documents.c.knowledge_base_id, knowledge_documents.c.status, knowledge_documents.c.document_key, knowledge_documents.c.version.desc())


# staff_agent: complete durable employee chat and task execution state.
agent_definitions = sa.Table(
    "agent_definitions", metadata, pk(), public_id(),
    sa.Column("code", sa.Text, nullable=False),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("transport", sa.Text, nullable=False, server_default="local"),
    sa.Column("endpoint", sa.Text), sa.Column("credential_ref", sa.Text),
    json_object("capabilities"),
    sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
    created_at(), updated_at(),
    sa.UniqueConstraint("code", "version"),
    sa.CheckConstraint("version > 0", name="version_positive"),
    sa.CheckConstraint("transport IN ('local','a2a')", name="transport_valid"),
    sa.CheckConstraint("transport <> 'a2a' OR endpoint IS NOT NULL", name="a2a_has_endpoint"),
    schema="staff_agent",
)

prompt_versions = sa.Table(
    "prompt_versions", metadata, pk(),
    fk("agent_id", "staff_agent.agent_definitions.id", ondelete="RESTRICT"),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("content", sa.Text, nullable=False),
    sa.Column("sha256", sa.Text, nullable=False), created_at(),
    sa.UniqueConstraint("agent_id", "version"),
    sa.CheckConstraint("version > 0", name="version_positive"),
    schema="staff_agent",
)

staff_sessions = sa.Table(
    "staff_sessions", metadata, pk(), public_id(),
    sa.Column("staff_id", UUID(as_uuid=True), nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="active"),
    sa.Column("pinned", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("locale", sa.Text, nullable=False, server_default="zh-CN"),
    sa.Column("last_message_at", sa.DateTime(timezone=True)),
    sa.Column("next_sequence", sa.BigInteger, nullable=False, server_default="1"),
    sa.Column("context_version", sa.Integer, nullable=False, server_default="1"),
    created_at(), updated_at(),
    sa.CheckConstraint("status IN ('active','archived','deleted')", name="status_valid"),
    sa.CheckConstraint("next_sequence > 0 AND context_version > 0", name="versions_positive"),
    schema="staff_agent",
)
sa.Index("ix_staff_sessions_recent", staff_sessions.c.staff_id, staff_sessions.c.status, staff_sessions.c.last_message_at.desc(), staff_sessions.c.id.desc())

staff_messages = sa.Table(
    "staff_messages", metadata, pk(), public_id(),
    fk("session_id", "staff_agent.staff_sessions.id", ondelete="CASCADE"),
    sa.Column("request_id", sa.BigInteger),
    sa.Column("parent_message_id", sa.BigInteger),
    sa.Column("sequence_no", sa.BigInteger, nullable=False),
    sa.Column("role", sa.Text, nullable=False),
    sa.Column("kind", sa.Text, nullable=False, server_default="text"),
    sa.Column("content", sa.Text, nullable=False, server_default=""),
    sa.Column("status", sa.Text, nullable=False, server_default="queued"),
    sa.Column("client_message_id", UUID(as_uuid=True)),
    sa.Column("content_version", sa.Integer, nullable=False, server_default="1"),
    json_object("metadata_redacted"), created_at(), updated_at(),
    sa.UniqueConstraint("session_id", "sequence_no"),
    sa.ForeignKeyConstraint(["parent_message_id"], ["staff_agent.staff_messages.id"], ondelete="SET NULL"),
    sa.CheckConstraint("role IN ('user','assistant','system')", name="role_valid"),
    sa.CheckConstraint("kind IN ('text','clarification','notice','error')", name="kind_valid"),
    sa.CheckConstraint("status IN ('queued','streaming','completed','failed','cancelled')", name="status_valid"),
    sa.CheckConstraint("content_version > 0", name="content_version_positive"),
    schema="staff_agent",
)
sa.Index("uq_staff_messages_client", staff_messages.c.session_id, staff_messages.c.client_message_id, unique=True, postgresql_where=staff_messages.c.client_message_id.is_not(None))
sa.Index("ix_staff_messages_parent", staff_messages.c.parent_message_id)

staff_requests = sa.Table(
    "staff_requests", metadata, pk(), public_id(),
    fk("session_id", "staff_agent.staff_sessions.id", ondelete="CASCADE"),
    fk("trigger_message_id", "staff_agent.staff_messages.id", ondelete="RESTRICT"),
    fk("final_message_id", "staff_agent.staff_messages.id", nullable=True, ondelete="SET NULL"),
    sa.Column("original_text", sa.Text, nullable=False),
    sa.Column("idempotency_key", UUID(as_uuid=True), nullable=False),
    sa.Column("route", sa.Text, nullable=False, server_default="pending"),
    sa.Column("status", sa.Text, nullable=False, server_default="received"),
    sa.Column("policy_version", sa.Text, nullable=False),
    sa.Column("route_reason", sa.Text), created_at(), updated_at(),
    sa.UniqueConstraint("session_id", "idempotency_key"),
    sa.UniqueConstraint("trigger_message_id"),
    sa.CheckConstraint("route IN ('pending','execute','human','clarify')", name="route_valid"),
    sa.CheckConstraint("status IN ('received','planned','needs_input','needs_review','running','responding','completed','partial','failed','cancelled')", name="status_valid"),
    schema="staff_agent",
)
sa.Index("ix_staff_requests_session_recent", staff_requests.c.session_id, staff_requests.c.created_at.desc(), staff_requests.c.id.desc())
staff_messages.append_constraint(
    sa.ForeignKeyConstraint(
        [staff_messages.c.request_id],
        [staff_requests.c.id],
        name="fk_staff_messages_request_id_staff_requests",
        ondelete="SET NULL",
        use_alter=True,
    )
)
sa.Index("ix_staff_messages_request_sequence", staff_messages.c.request_id, staff_messages.c.sequence_no, postgresql_where=staff_messages.c.request_id.is_not(None))

staff_message_attachments = sa.Table(
    "staff_message_attachments", metadata, pk(),
    fk("message_id", "staff_agent.staff_messages.id", ondelete="CASCADE"),
    sa.Column("file_id", UUID(as_uuid=True), nullable=False),
    sa.Column("purpose", sa.Text, nullable=False),
    sa.Column("display_name", sa.Text, nullable=False),
    sa.Column("mime_type", sa.Text), sa.Column("file_size", sa.BigInteger),
    sa.Column("status", sa.Text, nullable=False, server_default="pending"),
    sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
    created_at(), updated_at(),
    sa.UniqueConstraint("message_id", "file_id", "purpose"),
    sa.CheckConstraint("status IN ('pending','ready','rejected','quarantined','deleted')", name="status_valid"),
    sa.CheckConstraint("file_size IS NULL OR file_size >= 0", name="file_size_nonnegative"),
    schema="staff_agent",
)
sa.Index("ix_staff_attachments_message_order", staff_message_attachments.c.message_id, staff_message_attachments.c.sort_order, staff_message_attachments.c.id)

staff_message_streams = sa.Table(
    "staff_message_streams", metadata, pk(),
    fk("message_id", "staff_agent.staff_messages.id", ondelete="CASCADE"),
    fk("request_id", "staff_agent.staff_requests.id", ondelete="CASCADE"),
    sa.Column("stream_key", UUID(as_uuid=True), nullable=False, unique=True),
    sa.Column("transport", sa.Text, nullable=False, server_default="sse"),
    sa.Column("status", sa.Text, nullable=False, server_default="open"),
    sa.Column("last_event_seq", sa.BigInteger, nullable=False, server_default="0"),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_checkpoint_at", sa.DateTime(timezone=True)),
    sa.Column("finished_at", sa.DateTime(timezone=True)), sa.Column("error_code", sa.Text),
    created_at(), updated_at(), sa.UniqueConstraint("message_id"),
    sa.CheckConstraint("transport IN ('sse','websocket')", name="transport_valid"),
    sa.CheckConstraint("status IN ('open','completed','failed','cancelled')", name="status_valid"),
    sa.CheckConstraint("last_event_seq >= 0", name="event_seq_nonnegative"),
    schema="staff_agent",
)
sa.Index("ix_staff_streams_open_heartbeat", staff_message_streams.c.heartbeat_at, staff_message_streams.c.id, postgresql_where=staff_message_streams.c.status == "open")

staff_request_events = sa.Table(
    "staff_request_events", metadata, pk(),
    fk("request_id", "staff_agent.staff_requests.id", ondelete="CASCADE"),
    sa.Column("sequence_no", sa.BigInteger, nullable=False),
    sa.Column("event_type", sa.Text, nullable=False), sa.Column("stage", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False), sa.Column("display_text", sa.Text),
    sa.Column("progress_percent", sa.Numeric(5, 2)),
    sa.Column("visibility", sa.Text, nullable=False, server_default="user"),
    json_object("details_redacted"), created_at(),
    sa.UniqueConstraint("request_id", "sequence_no"),
    sa.CheckConstraint("progress_percent IS NULL OR (progress_percent >= 0 AND progress_percent <= 100)", name="progress_valid"),
    sa.CheckConstraint("visibility IN ('user','internal')", name="visibility_valid"),
    schema="staff_agent",
)

staff_clarifications = sa.Table(
    "staff_clarifications", metadata, pk(),
    fk("request_id", "staff_agent.staff_requests.id", ondelete="CASCADE"),
    sa.Column("ordinal", sa.Integer, nullable=False),
    fk("question_message_id", "staff_agent.staff_messages.id", ondelete="RESTRICT"),
    fk("answer_message_id", "staff_agent.staff_messages.id", nullable=True, ondelete="SET NULL"),
    sa.Column("status", sa.Text, nullable=False, server_default="open"),
    sa.Column("expected_input_schema", JSONB),
    sa.Column("expires_at", sa.DateTime(timezone=True)),
    sa.Column("answered_at", sa.DateTime(timezone=True)),
    created_at(), updated_at(),
    sa.UniqueConstraint("request_id", "ordinal"),
    sa.CheckConstraint("status IN ('open','answered','expired','cancelled')", name="status_valid"),
    schema="staff_agent",
)
sa.Index("uq_staff_one_open_clarification", staff_clarifications.c.request_id, unique=True, postgresql_where=staff_clarifications.c.status == "open")

staff_session_resources = sa.Table(
    "staff_session_resources", metadata, pk(),
    fk("session_id", "staff_agent.staff_sessions.id", ondelete="CASCADE"),
    fk("added_by_message_id", "staff_agent.staff_messages.id", nullable=True, ondelete="SET NULL"),
    sa.Column("resource_type", sa.Text, nullable=False),
    sa.Column("resource_id", UUID(as_uuid=True), nullable=False),
    sa.Column("purpose", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="active"),
    json_object("metadata_redacted"), created_at(), updated_at(),
    sa.UniqueConstraint("session_id", "resource_type", "resource_id", "purpose"),
    sa.CheckConstraint("status IN ('active','removed')", name="status_valid"),
    schema="staff_agent",
)
sa.Index("ix_staff_session_active_resources", staff_session_resources.c.session_id, staff_session_resources.c.resource_type, staff_session_resources.c.resource_id, postgresql_where=staff_session_resources.c.status == "active")

staff_context_summaries = sa.Table(
    "staff_context_summaries", metadata, pk(),
    fk("session_id", "staff_agent.staff_sessions.id", ondelete="CASCADE"),
    sa.Column("through_sequence_no", sa.BigInteger, nullable=False),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("summary", sa.Text, nullable=False), sa.Column("model", sa.Text, nullable=False),
    fk("prompt_id", "staff_agent.prompt_versions.id", nullable=True, ondelete="SET NULL"),
    sa.Column("token_estimate", sa.Integer), sa.Column("status", sa.Text, nullable=False, server_default="active"),
    created_at(), sa.UniqueConstraint("session_id", "version"),
    sa.CheckConstraint("version > 0 AND through_sequence_no >= 0", name="versions_valid"),
    sa.CheckConstraint("status IN ('active','superseded','invalid')", name="status_valid"),
    schema="staff_agent",
)

intent_runs = sa.Table(
    "intent_runs", metadata, pk(),
    fk("request_id", "staff_agent.staff_requests.id", ondelete="CASCADE"),
    fk("prompt_id", "staff_agent.prompt_versions.id", ondelete="RESTRICT"),
    sa.Column("model", sa.Text, nullable=False), sa.Column("attempt", sa.Integer, nullable=False),
    sa.Column("status", sa.Text, nullable=False), sa.Column("raw_output", JSONB),
    sa.Column("validation_errors", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    sa.Column("latency_ms", sa.Integer), created_at(),
    sa.UniqueConstraint("request_id", "attempt"),
    sa.CheckConstraint("attempt > 0", name="attempt_positive"),
    sa.CheckConstraint("status IN ('running','valid','invalid','failed')", name="status_valid"),
    schema="staff_agent",
)

staff_tasks = sa.Table(
    "staff_tasks", metadata, pk(), public_id(),
    fk("request_id", "staff_agent.staff_requests.id", ondelete="CASCADE"),
    fk("intent_run_id", "staff_agent.intent_runs.id", ondelete="RESTRICT"),
    sa.Column("task_key", sa.Text, nullable=False), sa.Column("ordinal", sa.Integer, nullable=False),
    sa.Column("source_text", sa.Text, nullable=False),
    sa.Column("span_start", sa.Integer, nullable=False), sa.Column("span_end", sa.Integer, nullable=False),
    sa.Column("intent", sa.Text, nullable=False), sa.Column("business_domain", sa.Text, nullable=False),
    sa.Column("condition_text", sa.Text), sa.Column("status", sa.Text, nullable=False, server_default="planned"),
    json_object("parameters"), created_at(), updated_at(),
    sa.UniqueConstraint("request_id", "ordinal"),
    sa.CheckConstraint("ordinal >= 0 AND span_start >= 0 AND span_end >= span_start", name="positions_valid"),
    sa.CheckConstraint("intent IN ('knowledge_question','record_query','action_request','unclear')", name="intent_valid"),
    schema="staff_agent",
)

task_dependencies = sa.Table(
    "task_dependencies", metadata, pk(),
    fk("request_id", "staff_agent.staff_requests.id", ondelete="CASCADE"),
    fk("task_id", "staff_agent.staff_tasks.id", ondelete="CASCADE"),
    fk("depends_on_id", "staff_agent.staff_tasks.id", ondelete="CASCADE"),
    created_at(), sa.UniqueConstraint("task_id", "depends_on_id"),
    sa.CheckConstraint("task_id <> depends_on_id", name="not_self_dependency"),
    schema="staff_agent",
)

workflow_checkpoints = sa.Table(
    "workflow_checkpoints", metadata, pk(),
    fk("request_id", "staff_agent.staff_requests.id", ondelete="CASCADE"),
    fk("task_id", "staff_agent.staff_tasks.id", nullable=True, ondelete="SET NULL"),
    sa.Column("checkpoint_no", sa.Integer, nullable=False),
    json_object("state_redacted"), sa.Column("next_action", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True)),
    created_at(), sa.UniqueConstraint("request_id", "checkpoint_no"),
    sa.CheckConstraint("checkpoint_no >= 0", name="checkpoint_nonnegative"),
    schema="staff_agent",
)

task_runs = sa.Table(
    "task_runs", metadata, pk(), public_id(),
    fk("task_id", "staff_agent.staff_tasks.id", ondelete="CASCADE"),
    fk("agent_id", "staff_agent.agent_definitions.id", nullable=True, ondelete="SET NULL"),
    sa.Column("queue", sa.Text, nullable=False), sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
    sa.Column("attempt", sa.Integer, nullable=False), sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
    sa.Column("status", sa.Text, nullable=False, server_default="queued"),
    sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)),
    sa.Column("lease_until", sa.DateTime(timezone=True)), sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
    sa.Column("worker_id", sa.Text), sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
    sa.Column("error_code", sa.Text), created_at(), updated_at(),
    sa.UniqueConstraint("task_id", "attempt"),
    sa.CheckConstraint("attempt > 0 AND max_attempts > 0", name="attempts_positive"),
    sa.CheckConstraint("status IN ('queued','retry_wait','running','input_required','completed','failed','cancelled')", name="status_valid"),
    schema="staff_agent",
)
sa.Index("uq_staff_one_running_task", task_runs.c.task_id, unique=True, postgresql_where=task_runs.c.status == "running")
sa.Index("ix_staff_task_runs_available", task_runs.c.queue, task_runs.c.priority.desc(), task_runs.c.available_at, task_runs.c.id, postgresql_where=task_runs.c.status.in_(("queued", "retry_wait")))
sa.Index("ix_staff_task_runs_lease", task_runs.c.lease_until, task_runs.c.id, postgresql_where=task_runs.c.status == "running")

tool_calls = sa.Table(
    "tool_calls", metadata, pk(),
    fk("run_id", "staff_agent.task_runs.id", ondelete="CASCADE"),
    sa.Column("call_key", sa.Text, nullable=False), sa.Column("tool_name", sa.Text, nullable=False),
    sa.Column("effect", sa.Text, nullable=False), sa.Column("authorization_decision", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False), json_object("arguments_redacted"),
    json_object("result_summary"), sa.Column("duration_ms", sa.Integer), created_at(),
    sa.UniqueConstraint("run_id", "call_key"),
    sa.CheckConstraint("effect IN ('read','draft','write')", name="effect_valid"),
    sa.CheckConstraint("authorization_decision IN ('allowed','denied')", name="authorization_valid"),
    sa.CheckConstraint("authorization_decision <> 'denied' OR status='denied'", name="denied_status"),
    schema="staff_agent",
)

task_results = sa.Table(
    "task_results", metadata, pk(),
    fk("run_id", "staff_agent.task_runs.id", ondelete="CASCADE"),
    sa.Column("answer", sa.Text, nullable=False), json_object("data"),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("business_persisted", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("approval_submitted", sa.Boolean, nullable=False, server_default=sa.false()),
    created_at(), sa.UniqueConstraint("run_id"),
    sa.CheckConstraint("source IN ('live','mock')", name="source_valid"),
    sa.CheckConstraint("source <> 'mock' OR (business_persisted=false AND approval_submitted=false)", name="mock_not_persisted"),
    schema="staff_agent",
)

human_cases = sa.Table(
    "human_cases", metadata, pk(), public_id(),
    fk("request_id", "staff_agent.staff_requests.id", ondelete="RESTRICT"),
    sa.Column("assigned_staff_id", UUID(as_uuid=True)), sa.Column("reason", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="open"),
    sa.Column("submission_status", sa.Text, nullable=False, server_default="not_submitted"),
    sa.Column("external_reference", sa.Text), sa.Column("submitted_at", sa.DateTime(timezone=True)),
    created_at(), updated_at(), sa.UniqueConstraint("request_id"),
    sa.CheckConstraint("status IN ('open','assigned','resolved','cancelled')", name="status_valid"),
    sa.CheckConstraint("submission_status IN ('not_submitted','submitted','failed')", name="submission_status_valid"),
    sa.CheckConstraint("submission_status <> 'submitted' OR (external_reference IS NOT NULL AND submitted_at IS NOT NULL)", name="submission_complete"),
    schema="staff_agent",
)
sa.Index("ix_staff_human_cases_queue", human_cases.c.status, human_cases.c.created_at, human_cases.c.id)

a2a_delegations = sa.Table(
    "a2a_delegations", metadata, pk(), public_id(),
    fk("run_id", "staff_agent.task_runs.id", ondelete="CASCADE"),
    fk("agent_id", "staff_agent.agent_definitions.id", ondelete="RESTRICT"),
    sa.Column("remote_task_id", sa.Text), sa.Column("remote_context_id", sa.Text),
    sa.Column("protocol_version", sa.Text, nullable=False),
    sa.Column("idempotency_key", UUID(as_uuid=True), nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="pending"),
    sa.Column("last_event_id", sa.Text), json_object("artifacts"),
    created_at(), updated_at(),
    sa.UniqueConstraint("agent_id", "idempotency_key"),
    sa.CheckConstraint("status IN ('pending','working','input_required','completed','failed','cancelled','unknown')", name="status_valid"),
    schema="staff_agent",
)
sa.Index("uq_staff_a2a_remote_task", a2a_delegations.c.agent_id, a2a_delegations.c.remote_task_id, unique=True, postgresql_where=a2a_delegations.c.remote_task_id.is_not(None))

audit_events = sa.Table(
    "audit_events", metadata, pk(),
    sa.Column("actor_staff_id", UUID(as_uuid=True)),
    fk("request_id", "staff_agent.staff_requests.id", nullable=True, ondelete="SET NULL"),
    sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("resource_type", sa.Text, nullable=False),
    sa.Column("resource_id", UUID(as_uuid=True)), json_object("details_redacted"),
    created_at(), schema="staff_agent",
)
sa.Index("ix_staff_audit_request_recent", audit_events.c.request_id, audit_events.c.created_at, audit_events.c.id)

staff_outbox, staff_inbox = add_event_tables("staff_agent")
