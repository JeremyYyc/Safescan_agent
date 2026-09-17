import sqlalchemy as sa
import pytest
from datetime import timedelta
from uuid import uuid4

from safescan_common.http.errors import ApiError

from app.core.security import create_access_token, decode_access_token, token_hash, utcnow
from app.domain.principal import Principal
from app.services.auth_service import AuthService
from app.services.internal_service import InternalService


pytestmark = pytest.mark.postgres_integration


def _create_staff(session, role_code: str, *, user_status: str = "active",
                  employment_status: str = "active") -> dict:
    now = utcnow()
    marker = uuid4()
    role = session.execute(
        sa.text("SELECT id,version FROM identity_access.roles WHERE code=:code"),
        {"code": role_code},
    ).mappings().one()
    user = session.execute(
        sa.text(
            "INSERT INTO identity_access.users "
            "(public_id,email,account_type,username,avatar,locale,status,auth_version,version,created_at,updated_at) "
            "VALUES (:public_id,:email,'staff',:username,'','zh-CN',:status,1,1,:now,:now) "
            "RETURNING id,public_id"
        ),
        {"public_id": marker, "email": f"identity-{marker.hex}@example.test",
         "username": f"identity-{marker.hex}", "status": user_status, "now": now},
    ).mappings().one()
    staff = session.execute(
        sa.text(
            "INSERT INTO identity_access.staff "
            "(public_id,user_id,role_id,staff_code,display_name,employment_status,hired_at,created_at,updated_at) "
            "VALUES (:public_id,:user_id,:role_id,:staff_code,'Identity Test Staff',:employment_status,:now,:now,:now) "
            "RETURNING public_id"
        ),
        {"public_id": uuid4(), "user_id": user["id"], "role_id": role["id"],
         "staff_code": f"T-{marker.hex[:10]}", "employment_status": employment_status,
         "now": now},
    ).mappings().one()
    session_id = uuid4()
    session.execute(
        sa.text(
            "INSERT INTO identity_access.auth_sessions "
            "(public_id,user_id,status,last_seen_at,expires_at,created_at,updated_at) "
            "VALUES (:public_id,:user_id,'active',:now,:expires_at,:now,:now)"
        ),
        {"public_id": session_id, "user_id": user["id"], "now": now,
         "expires_at": now + timedelta(minutes=10)},
    )
    return {"user_id": user["id"], "subject_id": user["public_id"],
            "staff_id": staff["public_id"], "session_id": session_id,
            "role_version": role["version"]}


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


def test_domain_service_delegation_allowlists_are_migrated(postgres_engine):
    with postgres_engine.connect() as connection:
        rows = {
            row["client_code"]: row
            for row in connection.execute(sa.text(
                "SELECT client_code,allowed_audiences,allowed_scopes "
                "FROM identity_access.service_clients "
                "WHERE client_code IN ('maintenance','inspection-report')"
            )).mappings()
        }
    assert {"property-leasing-service"}.issubset(
        rows["maintenance"]["allowed_audiences"]
    )
    assert {
        "identity:token_exchange", "maintenance:self:create",
        "maintenance:assign_assigned", "maintenance:update_assigned",
        "maintenance:manage_all", "work_order:read_assigned",
        "work_order:update_assigned", "work_order:evidence_write",
        "property:read_market", "property:manage_assigned", "property:read_all",
        "property:read_work_context",
    }.issubset(rows["maintenance"]["allowed_scopes"])
    assert {"property-leasing-service", "maintenance-service"}.issubset(
        rows["inspection-report"]["allowed_audiences"]
    )
    assert {"identity:token_exchange", "work_order:read_assigned",
            "report:read_work_context"}.issubset(rows["inspection-report"]["allowed_scopes"])


def test_delegated_actor_exchange_revalidates_database_session_and_versions(
    session_factory, identity_settings
):
    with session_factory() as session:
        staff = _create_staff(session, "maintainer")
        client = session.execute(sa.text(
            "SELECT allowed_scopes FROM identity_access.service_clients "
            "WHERE client_code='maintenance'"
        )).mappings().one()
        token, _ = create_access_token(
            identity_settings,
            subject=str(staff["subject_id"]),
            session_id=str(staff["session_id"]),
            account_type="staff",
            auth_version=1,
            scopes=["property:read_work_context"],
            audience="maintenance-service",
            extra={"rv": staff["role_version"]},
            actor={
                "sub": str(staff["subject_id"]), "client": "service:staff-portal",
                "account_type": "staff", "staff_id": str(staff["staff_id"]),
                "role": "maintainer",
            },
        )
        principal = Principal(
            subject="service:maintenance", user_id=None, session_internal_id=None,
            session_id=None, account_type=None,
            scopes=frozenset(client["allowed_scopes"]), claims={},
        )
        service = InternalService(session, identity_settings)
        result = service.exchange(
            principal, user_token=token, target_audience="property-leasing-service",
            requested_scopes=["property:read_work_context"],
        )
        claims = decode_access_token(
            identity_settings, result["access_token"], audience="property-leasing-service"
        )
        assert claims["scopes"] == ["property:read_work_context"]
        assert claims["act"]["staff_id"] == str(staff["staff_id"])

        session.execute(sa.text(
            "UPDATE identity_access.auth_sessions SET status='revoked' WHERE public_id=:sid"
        ), {"sid": staff["session_id"]})
        with pytest.raises(ApiError) as caught:
            service.exchange(
                principal, user_token=token, target_audience="property-leasing-service",
                requested_scopes=["property:read_work_context"],
            )
        assert caught.value.code == "session_inactive"

        session.execute(sa.text(
            "UPDATE identity_access.auth_sessions SET status='active' WHERE public_id=:sid"
        ), {"sid": staff["session_id"]})
        session.execute(sa.text(
            "UPDATE identity_access.users SET auth_version=auth_version+1 WHERE id=:user_id"
        ), {"user_id": staff["user_id"]})
        with pytest.raises(ApiError) as caught:
            service.exchange(
                principal, user_token=token, target_audience="property-leasing-service",
                requested_scopes=["property:read_work_context"],
            )
        assert caught.value.code == "token_stale"


def test_maintainer_lookup_uses_staff_public_id_and_fails_closed(
    session_factory, identity_settings
):
    with session_factory() as session:
        active = _create_staff(session, "maintainer")
        inactive = _create_staff(session, "maintainer", employment_status="pending")
        non_maintainer = _create_staff(session, "property_manager")
        service = InternalService(session, identity_settings)

        result = service.active_maintainer(active["staff_id"])
        assert result == {
            "id": str(active["staff_id"]), "staff_code": result["staff_code"],
            "display_name": "Identity Test Staff", "role": "maintainer",
            "status": "active", "employment_status": "active",
        }
        for staff_id in (inactive["staff_id"], non_maintainer["staff_id"],
                         active["subject_id"]):
            with pytest.raises(ApiError) as caught:
                service.active_maintainer(staff_id)
            assert caught.value.code == "maintainer_not_found"
