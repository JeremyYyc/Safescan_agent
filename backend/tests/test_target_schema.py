from collections import Counter

from app.persistence.target_schema import SERVICE_SCHEMAS, metadata


EXPECTED_TABLE_COUNTS = {
    "identity_access": 20,
    "property_leasing": 21,
    "maintenance": 6,
    "inspection_report": 16,
    "knowledge": 3,
    "staff_agent": 23,
}


def test_target_schema_has_only_the_owned_service_boundaries():
    assert set(SERVICE_SCHEMAS) == set(EXPECTED_TABLE_COUNTS)
    assert Counter(table.schema for table in metadata.tables.values()) == EXPECTED_TABLE_COUNTS
    assert "tenant_agent" not in SERVICE_SCHEMAS


def test_single_company_model_has_no_organization_column_or_join_layer():
    assert all("organization_id" not in table.c for table in metadata.tables.values())
    table_names = {table.name for table in metadata.tables.values()}
    assert "organizations" not in table_names
    assert "memberships" not in table_names
    assert "relationships" not in table_names


def test_cross_service_references_are_not_physical_foreign_keys():
    for table in metadata.tables.values():
        for constraint in table.foreign_key_constraints:
            referred_schema = next(iter(constraint.elements)).column.table.schema
            assert referred_schema == table.schema


def test_every_physical_foreign_key_has_a_leading_index():
    for table in metadata.tables.values():
        indexed_columns = [tuple(index.columns.keys()) for index in table.indexes]
        indexed_columns.extend(
            tuple(constraint.columns.keys())
            for constraint in table.constraints
            if constraint.__class__.__name__ in {"PrimaryKeyConstraint", "UniqueConstraint"}
        )
        for constraint in table.foreign_key_constraints:
            foreign_key_columns = tuple(element.parent.name for element in constraint.elements)
            assert any(
                columns[: len(foreign_key_columns)] == foreign_key_columns
                for columns in indexed_columns
            ), f"{table.fullname}{foreign_key_columns} has no leading index"


def test_unique_email_account_and_single_staff_role_are_schema_facts():
    users = metadata.tables["identity_access.users"]
    staff = metadata.tables["identity_access.staff"]

    assert {"email", "account_type", "auth_version", "version", "locale"} <= set(users.c.keys())
    assert any(index.name == "uq_identity_users_email" and index.unique for index in users.indexes)
    assert {"user_id", "role_id", "employment_status"} <= set(staff.c.keys())
    assert any(
        constraint.name == "uq_staff_user_id"
        for constraint in staff.constraints
    )


def test_identity_action_tokens_are_hashed_single_use_records():
    tokens = metadata.tables["identity_access.account_action_tokens"]
    assert {"user_id", "purpose", "token_hash", "expires_at", "used_at", "revoked_at"} <= set(tokens.c.keys())
    assert "token" not in tokens.c
    assert any(
        index.name == "uq_identity_action_one_active_purpose" and index.unique
        for index in tokens.indexes
    )


def test_identity_deletion_schema_keeps_only_non_identifying_tombstones():
    requests = metadata.tables["identity_access.subject_deletion_requests"]
    acknowledgements = metadata.tables["identity_access.subject_deletion_acknowledgements"]
    tombstones = metadata.tables["identity_access.subject_deletion_tombstones"]

    assert {"user_id", "subject_id", "status", "required_services"} <= set(requests.c.keys())
    assert requests.c.user_id.nullable
    assert requests.c.subject_id.nullable
    assert {"request_id", "service", "status", "attempt"} <= set(acknowledgements.c.keys())
    assert any(
        tuple(constraint.columns.keys()) == ("request_id", "service")
        for constraint in acknowledgements.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    )
    assert {
        "deletion_request_id",
        "subject_fingerprint",
        "fingerprint_version",
        "status",
        "completed_at",
    } == set(tombstones.c.keys())


def test_staff_agent_schema_covers_durable_chat_and_execution_state():
    required = {
        "staff_sessions",
        "staff_messages",
        "staff_message_attachments",
        "staff_message_streams",
        "staff_requests",
        "staff_request_events",
        "staff_clarifications",
        "workflow_checkpoints",
        "task_runs",
        "tool_calls",
        "audit_events",
    }
    staff_agent_tables = {
        table.name for table in metadata.tables.values() if table.schema == "staff_agent"
    }
    assert required <= staff_agent_tables

    messages = metadata.tables["staff_agent.staff_messages"]
    request_fk = next(
        constraint
        for constraint in messages.foreign_key_constraints
        if constraint.referred_table.name == "staff_requests"
    )
    assert request_fk.use_alter is True


def test_report_jobs_persist_input_result_and_prevent_parallel_workspace_runs():
    jobs = metadata.tables["inspection_report.report_jobs"]
    assert {"input_payload", "result_payload", "lease_until", "heartbeat_at"} <= set(
        jobs.c.keys()
    )
    assert any(
        index.name == "uq_report_jobs_one_active_workspace" and index.unique
        for index in jobs.indexes
    )
    items = metadata.tables["inspection_report.report_workspace_items"]
    source_fk_deletes = {
        next(iter(constraint.columns)).name: constraint.ondelete
        for constraint in items.foreign_key_constraints
    }
    assert source_fk_deletes["report_id"] == "CASCADE"
    assert source_fk_deletes["job_id"] == "CASCADE"
