from collections import Counter
from datetime import timedelta
import runpy
from uuid import UUID, uuid4

import jwt
import pytest
import httpx
from fastapi.testclient import TestClient
from safescan_common.http.errors import ApiError
from pydantic import SecretStr
from app.core.config import Settings, get_settings
from app.core.pagination import decode_cursor, encode_cursor, get_cursor_codec
from app.core.security import (create_access_token, decode_access_token, deletion_peppers,
                               hash_password, subject_fingerprint, utcnow, verify_password)
from app.domain.principal import Principal
from app.main import app
from app.mappers.user_mapper import UserMapper
from app.schemas.internal import CustomerStatusEventRequest
from app.seed_staff import STAFF_SEEDS, initial_password
from app.services.deletion_client import DeletionEligibilityClient
from app.services.deletion_client import DeletionBlockers
from app.services.deletion_service import DeletionService
from app.services.auth_service import AuthService
from app.services.internal_service import InternalService


pytestmark = pytest.mark.unit


def settings() -> Settings:
    return Settings(
        database_url=SecretStr("postgresql+psycopg://unused:unused@db/unused"),
        jwt_secret=SecretStr("identity-unit-test-secret-value"),
    )


def test_openapi_exposes_the_57_planned_operations():
    schema = app.openapi()
    operations = sum(
        method.lower() in {"get", "post", "put", "patch", "delete"}
        for path in schema["paths"].values()
        for method in path
    )
    assert operations == 57
    assert "/api/v1/auth/register" in schema["paths"]
    assert "/api/v1/me" in schema["paths"]
    assert "/internal/v1/tokens/exchange" in schema["paths"]
    assert "/internal/v1/subject-deletions/{request_id}/acknowledgements" in schema["paths"]
    assert "/internal/v1/subject-deletions/{request_id}" in schema["paths"]
    assert "/internal/v1/subject-tombstones:check" in schema["paths"]
    assert "/internal/v1/staff/leasing-consultants" in schema["paths"]
    assert "/internal/v1/staff/leasing-consultants/{staff_id}" in schema["paths"]
    assert "/internal/v1/staff/{staff_id}" in schema["paths"]


def test_leasing_consultant_projection_is_minimal_and_property_compatible():
    staff_id = uuid4()
    consultant = UserMapper.leasing_consultant_view({
        "public_id": staff_id,
        "staff_code": "LC-001",
        "display_name": "Alex Leasing",
        "role": "leasing_consultant",
        "email": "must-not-leak@example.test",
    })
    assert consultant == {
        "id": str(staff_id),
        "staff_code": "LC-001",
        "display_name": "Alex Leasing",
        "role": "leasing_consultant",
    }

    class ConsultantMapper:
        @staticmethod
        def list_active_leasing_consultants():
            return [consultant]

        @staticmethod
        def get_active_leasing_consultant(_staff_id):
            return consultant

    service = object.__new__(InternalService)
    service.users = ConsultantMapper()
    assert service.active_leasing_consultants() == {"items": [consultant]}
    assert service.active_leasing_consultant(staff_id) == consultant


def test_inactive_leasing_consultant_detail_uses_a_stable_not_found_error():
    class MissingConsultantMapper:
        @staticmethod
        def get_active_leasing_consultant(_staff_id):
            return None

    service = object.__new__(InternalService)
    service.users = MissingConsultantMapper()
    with pytest.raises(ApiError) as caught:
        service.active_leasing_consultant(uuid4())
    assert caught.value.status_code == 404
    assert caught.value.code == "leasing_consultant_not_found"


def _exchange_fixture(
    *,
    caller: str,
    input_audience: str,
    input_scopes: list[str],
    current_scopes: list[str] | None = None,
    include_actor: bool = True,
    current_auth_version: int = 3,
    current_role_version: int = 4,
    session_status: str = "active",
):
    config = settings()
    subject_id = uuid4()
    session_id = uuid4()
    staff_id = uuid4()
    actor = ({
        "sub": str(subject_id),
        "client": "service:staff-portal",
        "account_type": "staff",
        "staff_id": str(staff_id),
        "role": "maintainer",
    } if include_actor else None)
    token, _ = create_access_token(
        config,
        subject=str(subject_id),
        session_id=str(session_id),
        account_type="staff",
        auth_version=3,
        scopes=input_scopes,
        audience=input_audience,
        extra={"rv": 4},
        actor=actor,
    )

    class Users:
        @staticmethod
        def get_by_public_id(_public_id):
            return {"id": 7, "public_id": subject_id, "account_type": "staff",
                    "status": "active", "auth_version": current_auth_version}

        @staticmethod
        def scopes_for(_user):
            return current_scopes or input_scopes, {"rv": current_role_version}

    class Sessions:
        @staticmethod
        def get_session(_public_id, _user_id):
            return {"id": 9, "public_id": session_id, "status": session_status,
                    "expires_at": utcnow() + timedelta(minutes=5)}

    auth = object.__new__(AuthService)
    auth.settings = config
    auth.users = Users()
    auth.auth = Sessions()

    allowed = {
        "identity:token_exchange",
        "property:read_work_context",
        "report:read_work_context",
    }

    class Clients:
        @staticmethod
        def get_service_client(_code):
            return {
                "allowed_audiences": [
                    "property-leasing-service", "maintenance-service",
                    "inspection-report-service",
                ],
                "allowed_scopes": sorted(allowed),
            }

    service = object.__new__(InternalService)
    service.settings = config
    service.admin = Clients()
    service.auth_service = auth
    principal = Principal(
        subject=f"service:{caller}", user_id=None, session_internal_id=None,
        session_id=None, account_type=None, scopes=frozenset(allowed), claims={},
    )
    return service, principal, token, staff_id


def test_browser_exchange_remains_compatible_and_scope_bounded():
    service, principal, token, _ = _exchange_fixture(
        caller="staff-portal",
        input_audience=settings().jwt_audience,
        input_scopes=["property:read_work_context"],
    )
    result = service.exchange(
        principal, user_token=token, target_audience="property-leasing-service",
        requested_scopes=["property:read_work_context"],
    )
    claims = decode_access_token(
        settings(), result["access_token"], audience="property-leasing-service"
    )
    assert claims["scopes"] == ["property:read_work_context"]


def test_domain_exchange_requires_matching_caller_audience_and_preserves_actor():
    service, principal, token, staff_id = _exchange_fixture(
        caller="inspection-report",
        input_audience="inspection-report-service",
        input_scopes=["report:read_work_context"],
    )
    result = service.exchange(
        principal, user_token=token, target_audience="maintenance-service",
        requested_scopes=["report:read_work_context"],
    )
    claims = decode_access_token(
        settings(), result["access_token"], audience="maintenance-service"
    )
    assert claims["act"]["staff_id"] == str(staff_id)
    assert claims["act"]["role"] == "maintainer"
    assert claims["act"]["client"] == "service:inspection-report"

    mismatched, wrong_principal, wrong_token, _ = _exchange_fixture(
        caller="maintenance",
        input_audience="inspection-report-service",
        input_scopes=["report:read_work_context"],
    )
    with pytest.raises(ApiError) as caught:
        mismatched.exchange(
            wrong_principal, user_token=wrong_token,
            target_audience="property-leasing-service",
            requested_scopes=["report:read_work_context"],
        )
    assert caught.value.code == "delegated_token_audience_invalid"


def test_domain_exchange_rejects_missing_actor_and_any_scope_expansion():
    service, principal, token, _ = _exchange_fixture(
        caller="inspection-report",
        input_audience="inspection-report-service",
        input_scopes=["report:read_work_context"],
        include_actor=False,
    )
    with pytest.raises(ApiError) as caught:
        service.exchange(
            principal, user_token=token, target_audience="maintenance-service",
            requested_scopes=["report:read_work_context"],
        )
    assert caught.value.code == "delegated_token_actor_invalid"

    service, principal, token, _ = _exchange_fixture(
        caller="inspection-report",
        input_audience="inspection-report-service",
        input_scopes=["report:read_work_context"],
        current_scopes=["report:read_work_context", "property:read_work_context"],
    )
    with pytest.raises(ApiError) as caught:
        service.exchange(
            principal, user_token=token, target_audience="property-leasing-service",
            requested_scopes=["property:read_work_context"],
        )
    assert caught.value.code == "scope_not_delegable"


def test_domain_exchange_rejects_bad_signature_issuer_and_expiry():
    service, principal, token, _ = _exchange_fixture(
        caller="inspection-report",
        input_audience="inspection-report-service",
        input_scopes=["report:read_work_context"],
    )
    raw = jwt.decode(token, options={"verify_signature": False})
    foreign_issuer, _ = create_access_token(
        settings().model_copy(update={"jwt_issuer": "untrusted-issuer"}),
        subject=raw["sub"], session_id=raw["sid"], account_type="staff",
        auth_version=raw["av"], scopes=raw["scopes"], audience=raw["aud"],
        extra={"rv": raw["rv"]}, actor=raw["act"],
    )
    expired, _ = create_access_token(
        settings(), subject=raw["sub"], session_id=raw["sid"], account_type="staff",
        auth_version=raw["av"], scopes=raw["scopes"], audience=raw["aud"],
        extra={"rv": raw["rv"]}, actor=raw["act"], lifetime_seconds=-1,
    )
    tampered = f"{token.rsplit('.', 1)[0]}.invalid-signature"

    for invalid_token in (tampered, foreign_issuer, expired):
        with pytest.raises(ApiError) as caught:
            service.exchange(
                principal, user_token=invalid_token, target_audience="maintenance-service",
                requested_scopes=["report:read_work_context"],
            )
        assert caught.value.code == "invalid_token"


@pytest.mark.parametrize(
    ("fixture_overrides", "error_code"),
    [
        ({"current_auth_version": 4}, "token_stale"),
        ({"current_role_version": 5}, "token_stale"),
        ({"session_status": "revoked"}, "session_inactive"),
    ],
)
def test_domain_exchange_revalidates_versions_and_session(fixture_overrides, error_code):
    service, principal, token, _ = _exchange_fixture(
        caller="inspection-report",
        input_audience="inspection-report-service",
        input_scopes=["report:read_work_context"],
        **fixture_overrides,
    )
    with pytest.raises(ApiError) as caught:
        service.exchange(
            principal, user_token=token, target_audience="maintenance-service",
            requested_scopes=["report:read_work_context"],
        )
    assert caught.value.code == error_code


def test_maintainer_projection_contract_rejects_unavailable_staff():
    maintainer = {
        "id": str(uuid4()), "staff_code": "MT001", "display_name": "Maintainer",
        "role": "maintainer", "status": "active", "employment_status": "active",
    }

    class Maintainers:
        @staticmethod
        def get_active_maintainer(staff_id):
            return maintainer if str(staff_id) == maintainer["id"] else None

    service = object.__new__(InternalService)
    service.users = Maintainers()
    assert service.active_maintainer(UUID(maintainer["id"])) is maintainer
    with pytest.raises(ApiError) as caught:
        service.active_maintainer(uuid4())
    assert caught.value.status_code == 404
    assert caught.value.code == "maintainer_not_found"


def test_access_token_is_scoped_signed_and_audience_checked():
    config = settings()
    token, lifetime = create_access_token(
        config, subject="subject", session_id="session", account_type="customer",
        auth_version=3, scopes=["b", "a", "a"],
    )
    claims = decode_access_token(config, token)
    assert lifetime == config.access_token_seconds
    assert claims["scopes"] == ["a", "b"]
    assert claims["av"] == 3
    assert claims["aud"] == config.jwt_audience


def test_identity_errors_use_the_frozen_error_envelope(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unused:unused@db/unused")
    monkeypatch.setenv("AUTH_SECRET", "identity-unit-test-secret-value")
    get_settings.cache_clear()
    response = TestClient(app).get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["error"] == {
        "code": "authentication_required",
        "message": "Authentication required",
        "request_id": response.headers["x-request-id"],
        "retryable": False,
        "details": {},
    }
    get_settings.cache_clear()


def test_passwords_are_argon2id_hashes_and_cursors_are_opaque(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unused:unused@db/unused")
    monkeypatch.setenv("AUTH_SECRET", "identity-unit-test-secret-value")
    get_settings.cache_clear()
    get_cursor_codec.cache_clear()
    password_hash = hash_password("LongPassword123")
    assert password_hash.startswith("$argon2id$")
    assert verify_password(password_hash, "LongPassword123")
    assert not verify_password(password_hash, "incorrect")
    cursor = encode_cursor(42)
    assert cursor != "42"
    assert decode_cursor(cursor) == 42
    assert "." in cursor
    get_cursor_codec.cache_clear()
    get_settings.cache_clear()


def test_staff_seed_contains_the_twelve_approved_development_accounts():
    assert len(STAFF_SEEDS) == 12
    assert Counter(row[4] for row in STAFF_SEEDS) == {
        "leasing_consultant": 4,
        "property_manager": 4,
        "maintainer": 3,
        "manager_admin": 1,
    }
    assert len({row[2] for row in STAFF_SEEDS}) == 12
    assert len({row[3].lower() for row in STAFF_SEEDS}) == 12
    for _, display_name, username, email, _ in STAFF_SEEDS:
        assert "+" not in email
        assert email == f"{display_name.split()[0]}Safescan@outlook.com"
        generated_password = initial_password(username)
        assert generated_password.startswith("staff")
        assert generated_password.endswith("123456")
        assert verify_password(hash_password(generated_password), generated_password)


def test_migration_seeds_the_exact_frozen_staff_permission_matrix():
    matrix = runpy.run_path("/identity_p0_migration.py")["P0_ROLE_PERMISSIONS"]
    repair = runpy.run_path("/identity_p0_repair_migration.py")
    expected = {
        "leasing_consultant": {
            "property:read_market", "prospect:manage", "application:manage", "lease:prepare",
            "lease:execute", "agent:staff:use",
        },
        "property_manager": {
            "building:read_assigned", "property:manage_assigned", "lease:manage_active_assigned",
            "maintenance:assign_assigned", "maintenance:update_assigned", "report:read_assigned",
            "report:generate_assigned", "agent:staff:use",
        },
        "maintainer": {
            "work_order:read_assigned", "work_order:update_assigned", "work_order:evidence_write",
            "property:read_work_context", "report:read_work_context", "agent:staff:use",
        },
    }
    expected["manager_admin"] = {
        *(permission for permissions in expected.values() for permission in permissions),
        "building:read_all", "property:read_all", "prospect:manage_all", "application:manage_all",
        "lease:manage_all", "maintenance:manage_all", "report:read_all", "report:generate_all",
        "iam:user:read", "iam:user:status_manage", "iam:staff:create", "iam:staff:read",
        "iam:staff:employment_manage", "iam:staff:role_manage", "iam:audit:read", "rbac:read",
        "rbac:manage", "scope:manage",
    }
    assert matrix == expected
    assert repair["down_revision"] == "20260910_0005"
    assert repair["P0_ROLE_PERMISSIONS"] == expected


def test_domain_delegation_migration_covers_real_maintenance_requested_scopes():
    migration = runpy.run_path("/identity_domain_delegation_migration.py")
    maintenance = migration["DOMAIN_DELEGATION"]["maintenance"]
    assert maintenance["audiences"] == {"property-leasing-service"}
    assert maintenance["scopes"] == {
        "identity:token_exchange",
        "maintenance:self:create",
        "maintenance:assign_assigned",
        "maintenance:update_assigned",
        "maintenance:manage_all",
        "work_order:read_assigned",
        "work_order:update_assigned",
        "work_order:evidence_write",
        "property:read_market",
        "property:manage_assigned",
        "property:read_all",
        "property:read_work_context",
    }
    assert maintenance["scopes"].isdisjoint(
        migration["PREDECESSOR"]["maintenance"]["scopes"]
    )


@pytest.mark.parametrize(
    ("status", "expected_scopes", "forbidden_scopes"),
    [
        ("prospect", {"application:self:create", "application:self:submit"}, {"report:self:create"}),
        ("tenant", {"lease:self:read", "report:self:create"}, {"application:self:create"}),
        ("former_tenant", {"lease:self:read_history", "report:self:read_history", "application:self:create"}, {"report:self:create"}),
    ],
)
def test_customer_scopes_follow_the_three_tenancy_stages(status, expected_scopes, forbidden_scopes):
    mapper = UserMapper(None)
    mapper.get_customer_profile = lambda _user_id: {"customer_status": status, "status_version": 2}
    scopes, extra = mapper.scopes_for({"id": 7, "account_type": "customer"})
    assert expected_scopes.issubset(scopes)
    assert forbidden_scopes.isdisjoint(scopes)
    assert extra == {"customer_status": status, "cv": 2}


def test_tenancy_projection_event_uses_explicit_status_without_lease_count():
    common = {
        "event_id": uuid4(),
        "customer_subject_id": uuid4(),
        "lease_id": uuid4(),
        "event_type": "customer.tenancy_status_changed.v1",
        "aggregate_version": 1,
        "occurred_at": "2026-09-08T00:00:00Z",
    }
    event = CustomerStatusEventRequest(**common, to_status="tenant")
    assert event.to_status == "tenant"
    assert "active_lease_count" not in event.model_dump()


def test_tombstone_fingerprint_is_keyed_and_not_a_plain_subject_digest():
    subject = str(uuid4())
    first = subject_fingerprint(subject, "independent-deletion-pepper-one")
    second = subject_fingerprint(subject, "independent-deletion-pepper-two")
    assert first != second
    assert len(first) == 32


def test_tombstone_checks_keep_historical_peppers_during_rotation():
    config = settings().model_copy(update={
        "deletion_pepper": SecretStr("current-independent-deletion-pepper"),
        "deletion_pepper_version": 3,
        "deletion_previous_peppers": SecretStr(
            "1:first-independent-deletion-pepper,2:second-independent-deletion-pepper"
        ),
    })
    assert deletion_peppers(config) == [
        (3, "current-independent-deletion-pepper"),
        (1, "first-independent-deletion-pepper"),
        (2, "second-independent-deletion-pepper"),
    ]


def test_deletion_eligibility_client_combines_both_domain_blockers():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith("Bearer ")
        if request.url.host == "leasing.test":
            return httpx.Response(200, json={"data": {"lease_ids": ["lease-1"]}})
        return httpx.Response(200, json={"data": {"order_ids": ["order-1"]}})

    client = DeletionEligibilityClient(
        settings().model_copy(update={
            "property_leasing_url": "http://leasing.test",
            "maintenance_url": "http://maintenance.test",
        }),
        transport=httpx.MockTransport(handler),
    )
    blockers = client.check(str(uuid4()))
    assert blockers.leases == ("lease-1",)
    assert blockers.maintenance_orders == ("order-1",)


@pytest.mark.parametrize(
    ("blockers", "code"),
    [
        (DeletionBlockers(leases=("lease-1",)), "active_lease_blocks_deletion"),
        (DeletionBlockers(maintenance_orders=("order-1",)),
         "open_maintenance_orders_block_deletion"),
    ],
)
def test_account_deletion_blockers_use_frozen_409_codes(blockers, code):
    with pytest.raises(ApiError) as caught:
        DeletionService._raise_blocker(blockers)
    assert caught.value.status_code == 409
    assert caught.value.code == code


def test_production_rejects_the_known_development_staff_seed():
    config = Settings(
        app_env="production",
        database_url=SecretStr("postgresql+psycopg://unused:unused@db/unused"),
        jwt_secret=SecretStr("identity-unit-test-secret-value"),
        seed_staff=True,
    )
    with pytest.raises(RuntimeError, match="IDENTITY_SEED_STAFF"):
        config.validate_runtime()
