from dataclasses import dataclass

import httpx
from safescan_common.http.errors import ApiError

from app.core.config import Settings
from app.core.security import create_access_token


@dataclass(frozen=True)
class DeletionBlockers:
    leases: tuple[str, ...] = ()
    maintenance_orders: tuple[str, ...] = ()

    @property
    def any(self) -> bool:
        return bool(self.leases or self.maintenance_orders)


class DeletionEligibilityClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport

    def _token(self, audience: str) -> str:
        token, _ = create_access_token(
            self.settings, subject="service:identity-access", session_id=None,
            account_type=None, auth_version=None, scopes=["privacy:subject_deletion_check"],
            audience=audience, lifetime_seconds=300,
        )
        return token

    def _check(self, base_url: str, audience: str, subject_id: str, dependency: str) -> tuple[str, ...]:
        try:
            with httpx.Client(timeout=self.settings.deletion_dependency_timeout_seconds,
                              transport=self.transport) as client:
                response = client.post(
                    f"{base_url.rstrip('/')}/internal/v1/privacy/subject-deletions:check",
                    json={"subject_id": subject_id},
                    headers={"Authorization": f"Bearer {self._token(audience)}"},
                )
        except httpx.TimeoutException as exc:
            raise ApiError(504, "dependency_timeout", "Deletion dependency timed out",
                           details={"dependency": dependency}) from exc
        except httpx.HTTPError as exc:
            raise ApiError(503, "dependency_unavailable", "Deletion dependency is unavailable",
                           details={"dependency": dependency}) from exc
        if response.status_code >= 500:
            raise ApiError(503, "dependency_unavailable", "Deletion dependency is unavailable",
                           details={"dependency": dependency})
        try:
            body = response.json()
        except ValueError as exc:
            raise ApiError(502, "dependency_invalid_response", "Deletion dependency returned invalid data",
                           details={"dependency": dependency}) from exc
        if response.status_code == 409:
            error = body.get("error", {})
            expected_code = (
                "active_lease_blocks_deletion" if dependency == "property-leasing"
                else "open_maintenance_orders_block_deletion"
            )
            if not isinstance(error, dict) or error.get("code") != expected_code:
                raise ApiError(502, "dependency_invalid_response",
                               "Deletion dependency returned invalid data",
                               details={"dependency": dependency})
            details = error.get("details") if isinstance(error.get("details"), dict) else {}
            safe_details = {key: details[key] for key in ("blocker_count", "lease_ids", "order_ids")
                            if key in details}
            raise ApiError(409, expected_code, error.get("message") or "Account deletion is blocked",
                           details=safe_details)
        payload = body.get("data", body)
        if response.status_code != 200 or not isinstance(payload, dict):
            raise ApiError(502, "dependency_invalid_response", "Deletion dependency returned invalid data",
                           details={"dependency": dependency})
        values = payload.get("blocker_ids") or payload.get("lease_ids") or payload.get("order_ids") or []
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ApiError(502, "dependency_invalid_response", "Deletion dependency returned invalid data",
                           details={"dependency": dependency})
        return tuple(values)

    def check(self, subject_id: str) -> DeletionBlockers:
        leases = self._check(self.settings.property_leasing_url, "property-leasing-service",
                             subject_id, "property-leasing")
        orders = self._check(self.settings.maintenance_url, "maintenance-service",
                             subject_id, "maintenance")
        return DeletionBlockers(leases=leases, maintenance_orders=orders)
