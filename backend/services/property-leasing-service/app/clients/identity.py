from uuid import UUID

import httpx

from app.core.config import Settings
from app.core.errors import error


class IdentityClient:
    """Fail-closed adapter for the Identity SubjectProjection contract."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get_subject(self, subject_id: UUID) -> dict:
        token = self.settings.identity_service_token.get_secret_value()
        if not token:
            raise error(503, "dependency_unavailable", "Identity validation is unavailable",
                        dependency="identity-access-service")
        try:
            response = httpx.get(
                f"{self.settings.identity_base_url.rstrip('/')}/internal/v1/subjects/{subject_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=self.settings.identity_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise error(504, "dependency_timeout", "Identity validation timed out",
                        dependency="identity-access-service") from exc
        except httpx.HTTPError as exc:
            raise error(503, "dependency_unavailable", "Identity validation is unavailable",
                        dependency="identity-access-service") from exc
        if response.status_code == 404:
            raise error(409, "account_unavailable", "Customer account is unavailable")
        if response.status_code >= 500:
            raise error(503, "dependency_unavailable", "Identity validation is unavailable",
                        dependency="identity-access-service")
        if response.status_code != 200:
            raise error(502, "dependency_invalid_response", "Identity returned an invalid response",
                        dependency="identity-access-service")
        try:
            return response.json()["data"]
        except (ValueError, KeyError, TypeError) as exc:
            raise error(502, "dependency_invalid_response", "Identity returned an invalid response",
                        dependency="identity-access-service") from exc

    def require_lease_eligible_customer(self, subject_id: UUID) -> dict:
        projection = self.get_subject(subject_id)
        if projection.get("account_type") != "customer" or projection.get("status") != "active":
            raise error(409, "account_unavailable", "Customer account is unavailable")
        status = projection.get("customer_status")
        if status not in {"prospect", "former_tenant"}:
            raise error(403, "customer_not_eligible_for_lease",
                        "Customer is not eligible for a new lease", customer_status=status,
                        allowed_statuses=["prospect", "former_tenant"])
        return projection

    def _leasing_consultant_response(self, path: str) -> dict:
        token = self.settings.identity_service_token.get_secret_value()
        if not token:
            raise error(503, "dependency_unavailable", "Identity validation is unavailable",
                        dependency="identity-access-service")
        try:
            response = httpx.get(
                f"{self.settings.identity_base_url.rstrip('/')}{path}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=self.settings.identity_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise error(504, "dependency_timeout", "Identity validation timed out",
                        dependency="identity-access-service") from exc
        except httpx.HTTPError as exc:
            raise error(503, "dependency_unavailable", "Identity validation is unavailable",
                        dependency="identity-access-service") from exc
        if response.status_code == 404:
            raise error(409, "leasing_consultant_unavailable",
                        "The Leasing Consultant is not active")
        if response.status_code >= 500:
            raise error(503, "dependency_unavailable", "Identity validation is unavailable",
                        dependency="identity-access-service")
        if response.status_code != 200:
            raise error(502, "dependency_invalid_response", "Identity returned an invalid response",
                        dependency="identity-access-service")
        try:
            return response.json()["data"]
        except (ValueError, KeyError, TypeError) as exc:
            raise error(502, "dependency_invalid_response", "Identity returned an invalid response",
                        dependency="identity-access-service") from exc

    def active_leasing_consultants(self) -> list[dict]:
        payload = self._leasing_consultant_response("/internal/v1/staff/leasing-consultants")
        items = payload.get("items")
        if not isinstance(items, list):
            raise error(502, "dependency_invalid_response", "Identity returned an invalid response",
                        dependency="identity-access-service")
        try:
            for item in items:
                UUID(item["id"])
                if item.get("role") != "leasing_consultant":
                    raise ValueError("unexpected role")
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise error(502, "dependency_invalid_response", "Identity returned an invalid response",
                        dependency="identity-access-service") from exc
        return items

    def require_active_leasing_consultant(self, staff_id: UUID) -> dict:
        return self._leasing_consultant_response(
            f"/internal/v1/staff/leasing-consultants/{staff_id}"
        )
