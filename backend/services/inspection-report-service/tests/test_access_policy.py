from uuid import uuid4

import pytest
from pydantic import SecretStr
from safescan_common.http.errors import ApiError

from inspection_report_service.auth import Principal
from inspection_report_service.config import Settings
from inspection_report_service.service import ReportService


class FakeLeasing:
    def __init__(self, *, property_result=None, leases=None):
        self.property_result = property_result or {"allowed": False}
        self.leases = leases or {}

    def property_access(self, actor, property_id, action):
        return self.property_result

    def lease_access(self, actor, lease_id, property_id, action):
        return self.leases.get(lease_id, {"allowed": False})


class FakeRepo:
    def __init__(self, report=None):
        self.saved = report
        self.created = None

    def create_report(self, actor, account_type, property_id, source_lease_id, title, key,
                      correlation_id, pipeline_version):
        self.created = {
            "created_by_subject_id": actor, "created_by_account_type": account_type,
            "property_id": property_id, "source_lease_id": source_lease_id,
            "title": title, "public_id": uuid4(), "id": 1, "status": "draft",
        }
        return self.created

    def get_report(self, report_id):
        return self.saved

    def list_reports(self, property_id, source_lease_id=None):
        if self.saved and self.saved["property_id"] == property_id:
            if source_lease_id is None or self.saved["source_lease_id"] == source_lease_id:
                return [self.saved]
        return []


class FakeMaintenance:
    def __init__(self, result):
        self.result = result

    def order_access(self, actor, order_id, report_id):
        return self.result


def settings() -> Settings:
    return Settings(
        database_url=SecretStr("postgresql+psycopg://x:x@localhost/test"),
        jwt_secret=SecretStr("report-test-secret-that-is-long-enough"),
        minio_access_key=SecretStr("x"), minio_secret_key=SecretStr("x"),
    )


def actor(account_type, scopes, *, status=None, subject=None, role=None):
    return Principal(subject or uuid4(), account_type, frozenset(scopes), "token",
                     staff_id=uuid4() if account_type == "staff" else None,
                     role=role, customer_status=status)


def service(leasing, report=None):
    value = ReportService(object(), leasing, settings())
    value.repo = FakeRepo(report)
    return value


def report(property_id, lease_id, creator=None):
    return {"id": 1, "public_id": uuid4(), "property_id": property_id,
            "source_lease_id": lease_id, "created_by_subject_id": creator or uuid4(),
            "created_by_account_type": "customer", "status": "active"}


def assert_hidden(callable_):
    with pytest.raises(ApiError) as caught:
        callable_()
    assert caught.value.status_code == 404
    assert caught.value.code == "resource_not_found"


def test_property_manager_creates_only_in_scope_and_binds_active_lease() -> None:
    property_id, lease_id = uuid4(), uuid4()
    manager = actor("staff", {"report:generate_assigned"}, role="property_manager")
    svc = service(FakeLeasing(property_result={"allowed": True, "active_lease_id": str(lease_id)}))
    saved = svc.create_report(manager, property_id, None, uuid4(), uuid4())
    assert saved["property_id"] == property_id
    assert saved["source_lease_id"] == lease_id

    denied = service(FakeLeasing(property_result={"allowed": False}))
    assert_hidden(lambda: denied.create_report(manager, uuid4(), None, uuid4(), uuid4()))


def test_manager_admin_still_uses_property_authorization() -> None:
    admin = actor("staff", {"report:generate_all"}, role="manager_admin")
    assert_hidden(lambda: service(FakeLeasing()).create_report(admin, uuid4(), None, uuid4(), uuid4()))


def test_tenant_creation_requires_matching_active_lease() -> None:
    property_id, lease_id, tenant_id = uuid4(), uuid4(), uuid4()
    tenant = actor("customer", {"report:self:create", "report:self:read"},
                   status="tenant", subject=tenant_id)
    svc = service(FakeLeasing(property_result={"allowed": True, "active_lease_id": str(lease_id)}))
    saved = svc.create_report(tenant, property_id, "Tenant report", uuid4(), uuid4())
    assert saved["source_lease_id"] == lease_id
    assert saved["created_by_subject_id"] == tenant_id

    assert_hidden(lambda: service(FakeLeasing()).create_report(tenant, property_id, None, uuid4(), uuid4()))


def test_historical_lease_is_read_only_and_exactly_partitioned() -> None:
    property_id, old_lease, other_lease = uuid4(), uuid4(), uuid4()
    former = actor("customer", {"report:self:read"}, status="former_tenant")
    saved = report(property_id, old_lease)
    leasing = FakeLeasing(leases={old_lease: {"allowed": True, "status": "ended"}})
    svc = service(leasing, saved)
    assert svc.report(former, saved["public_id"], lease_context=old_lease) == saved
    assert svc.reports(former, property_id, old_lease) == [saved]
    assert_hidden(lambda: svc.report(former, saved["public_id"], lease_context=other_lease))
    assert_hidden(lambda: svc.report(former, saved["public_id"], lease_context=old_lease, write=True))


def test_different_current_lease_and_maintainer_full_read_are_hidden() -> None:
    property_id, report_lease = uuid4(), uuid4()
    saved = report(property_id, report_lease)
    future_tenant = actor("customer", {"report:self:read"}, status="tenant")
    svc = service(FakeLeasing(property_result={"allowed": True, "active_lease_id": str(uuid4())}), saved)
    assert_hidden(lambda: svc.report(future_tenant, saved["public_id"]))

    maintainer = actor("staff", {"report:read_work_context"}, role="maintainer")
    assert_hidden(lambda: service(FakeLeasing(property_result={"allowed": True}), saved).report(
        maintainer, saved["public_id"]
    ))


def test_maintainer_gets_only_assigned_work_context_fragments() -> None:
    property_id = uuid4()
    saved = report(property_id, uuid4())
    saved.update({
        "title": "Repair context",
        "report_payload": {"regions": [{
            "regionName": ["Kitchen"], "generalHazards": ["wet floor"],
            "recommendations": ["dry floor"], "evidenceImages": ["/api/assets/one"],
            "model": "must-not-leak", "comfort": "must-not-leak",
        }]},
    })
    maintainer = actor("staff", {"report:read_work_context"}, role="maintainer")
    svc = service(FakeLeasing(), saved)
    svc.maintenance = FakeMaintenance({"allowed": True, "property_id": str(property_id)})
    value = svc.work_context(maintainer, saved["public_id"], uuid4())
    assert value["regions"][0]["generalHazards"] == ["wet floor"]
    assert "model" not in value["regions"][0]
    assert "comfort" not in value["regions"][0]
