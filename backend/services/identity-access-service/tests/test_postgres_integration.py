import sqlalchemy as sa
import pytest
from uuid import uuid4

from app.core.security import token_hash
from app.services.auth_service import AuthService


pytestmark = pytest.mark.postgres_integration


def test_registration_commits_complete_customer_identity(postgres_engine, register_customer):
    result = register_customer()
    subject_id = result["user"]["id"]

    with postgres_engine.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT u.account_type,u.status,p.customer_status,c.algorithm,"
                "s.status AS session_status,t.status AS refresh_status "
                "FROM identity_access.users u "
                "JOIN identity_access.customer_profiles p ON p.user_id=u.id "
                "JOIN identity_access.user_credentials c ON c.user_id=u.id "
                "JOIN identity_access.auth_sessions s ON s.user_id=u.id "
                "JOIN identity_access.refresh_tokens t ON t.session_id=s.id "
                "WHERE u.public_id=CAST(:subject_id AS uuid)"
            ),
            {"subject_id": subject_id},
        ).mappings().one()

    assert dict(row) == {
        "account_type": "customer",
        "status": "active",
        "customer_status": "prospect",
        "algorithm": "argon2id",
        "session_status": "active",
        "refresh_status": "active",
    }


def test_refresh_rotation_commits_parent_child_chain(
    postgres_engine, session_factory, identity_settings, register_customer
):
    registered = register_customer()
    old_value = registered["refresh_token"]
    with session_factory() as session:
        rotated = AuthService(session, identity_settings).refresh(
            old_value, correlation_id=uuid4()
        )

    with postgres_engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT id,token_hash,status,parent_token_id,replaced_by_token_id "
                "FROM identity_access.refresh_tokens "
                "WHERE token_hash IN (:old_hash,:new_hash) ORDER BY id"
            ),
            {"old_hash": token_hash(old_value), "new_hash": token_hash(rotated["refresh_token"])},
        ).mappings().all()

    assert [row["status"] for row in rows] == ["rotated", "active"]
    assert rows[0]["replaced_by_token_id"] == rows[1]["id"]
    assert rows[1]["parent_token_id"] == rows[0]["id"]
