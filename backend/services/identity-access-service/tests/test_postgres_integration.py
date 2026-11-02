import sqlalchemy as sa
import pytest
from sqlalchemy.orm import Session
from datetime import timedelta
from uuid import uuid4

from safescan_common.http.errors import ApiError

from app.core.security import create_access_token, decode_access_token, token_hash, utcnow
from app.domain.principal import Principal
from app.services.auth_service import AuthService
from app.services.internal_service import InternalService


pytestmark = pytest.mark.postgres_integration


def test_staff_summaries_batch_actual_role_permissions_without_writes(session_factory, identity_settings, monkeypatch):
    from app.services.admin_service import AdminService
    monkeypatch.setattr('app.core.pagination.get_settings', lambda: identity_settings)
    marker = uuid4().hex
    with session_factory() as session:
        for index, role in enumerate(('maintainer', 'maintainer', 'property_manager', 'leasing_consultant')):
            person = _create_staff(session, role)
            session.execute(sa.text('UPDATE identity_access.staff SET staff_code=:code WHERE public_id=:id'),
                            {'code': f'SUMMARY-{marker}-{index}', 'id': person['staff_id']})
        service = AdminService(session, identity_settings)
        expected = {role: service.admin.role_permission_codes(role_id) for role, role_id in session.execute(
            sa.text('SELECT code,id FROM identity_access.roles'))}
        grants_before = session.execute(sa.text('SELECT role_id,permission_id FROM identity_access.role_permissions ORDER BY 1,2')).all()
        statements = []
        def capture(_connection, _cursor, statement, _params, _context, _many):
            statements.append(statement)
        engine = session.get_bind()
        sa.event.listen(engine, 'before_cursor_execute', capture)
        try:
            result = service.list_staff(role_code=None,employment_status=None,query=marker,cursor=None,limit=100)
        finally:
            sa.event.remove(engine, 'before_cursor_execute', capture)
        assert len(result['data']) == 4
        assert len(statements) == 2 and all(statement.lstrip().upper().startswith('SELECT') for statement in statements)
        for item in result['data']:
            assert item['permissions'] == expected[item['role']['code']]
            assert service.get_staff(item['id'])['permissions'] == item['permissions']
        assert session.execute(sa.text('SELECT role_id,permission_id FROM identity_access.role_permissions ORDER BY 1,2')).all() == grants_before


def test_staff_summary_distinguishes_empty_and_customized_role_permissions(session_factory, identity_settings):
    from app.services.admin_service import AdminService
    # All changes here are confined to the disposable test transaction.
    with session_factory() as session:
        person = _create_staff(session, 'maintainer')
        role_id = session.scalar(sa.text("SELECT id FROM identity_access.roles WHERE code='maintainer'"))
        session.execute(sa.text('DELETE FROM identity_access.role_permissions WHERE role_id=:id'), {'id': role_id})
        service = AdminService(session, identity_settings)
        assert service.get_staff(person['staff_id'])['permissions'] == []
        session.execute(sa.text("""INSERT INTO identity_access.role_permissions(role_id,permission_id,created_at)
            SELECT :id,id,now() FROM identity_access.permissions WHERE code='iam:audit:read'"""), {'id': role_id})
        assert service.get_staff(person['staff_id'])['permissions'] == ['iam:audit:read']


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
            "status": "active", "employment_status": "active", "city_id": None,
        }
        for staff_id in (inactive["staff_id"], non_maintainer["staff_id"],
                         active["subject_id"]):
            with pytest.raises(ApiError) as caught:
                service.active_maintainer(staff_id)
            assert caught.value.code == "maintainer_not_found"


def test_staff_city_change_revokes_sessions_updates_projection_and_checks_version(postgres_engine, identity_settings):
    from app.services.admin_service import AdminService
    # The service commits, so isolate those commits in savepoints. A normal
    # Session rollback at test end would leave an extra active staff account
    # behind and contaminate the later real-system seed verification.
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        before = connection.scalar(sa.text('SELECT count(*) FROM identity_access.staff'))
        try:
            with Session(bind=connection, join_transaction_mode='create_savepoint') as session:
                staff = _create_staff(session, 'property_manager')
                actor = Principal(subject=str(uuid4()), account_type='staff', scopes=frozenset(), claims={})
                service = AdminService(session, identity_settings)
                result = service.change_city(staff['staff_id'], city_id='sydney', reason='City allocation',
                                             version=1, actor=actor, correlation_id=uuid4())
                assert result['city_id'] == 'sydney'
                projection = InternalService(session, identity_settings).subject(staff['subject_id'])
                assert projection['city_id'] == 'sydney'
                assert session.scalar(sa.text('SELECT status FROM identity_access.auth_sessions WHERE public_id=:id'),
                                      {'id': staff['session_id']}) == 'revoked'
                with pytest.raises(ApiError) as exc:
                    service.change_city(staff['staff_id'], city_id='melbourne', reason='Stale update',
                                        version=1, actor=actor, correlation_id=uuid4())
                assert exc.value.code == 'version_conflict'
                session.rollback()
                assert service.get_staff(staff['staff_id'])['city_id'] == 'sydney'

        finally:
            transaction.rollback()
        assert connection.scalar(sa.text('SELECT count(*) FROM identity_access.staff')) == before
