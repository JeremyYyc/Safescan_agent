from uuid import UUID

import httpx
from safescan_common.auth import ServiceTokenError, ServiceTokenProvider

from app.core.config import Settings
from app.core.errors import error
from app.domain.principal import Principal


class DependencyClient:
    def __init__(self, settings: Settings, service_tokens=None) -> None:
        self.settings = settings
        self.service_tokens = service_tokens or ServiceTokenProvider(
            settings.identity_base_url, settings.identity_client_id,
            settings.identity_client_secret.get_secret_value(),
            ["identity:token_exchange", "identity:subject_read",
             "identity:subject_deletion_ack"],
            timeout=settings.dependency_timeout_seconds,
        )

    def _identity_token(self) -> str:
        try:
            return self.service_tokens.get()
        except (ServiceTokenError, httpx.HTTPError) as exc:
            raise error(503, "dependency_unavailable", "Identity credentials are unavailable",
                        dependency="identity-access-service") from exc

    def _request(self, name: str, method: str, url: str, token: str, **kwargs) -> dict:
        if not token:
            raise error(
                503,
                "dependency_unavailable",
                f"{name} validation is unavailable",
                dependency=name,
            )
        try:
            response = httpx.request(
                method,
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=self.settings.dependency_timeout_seconds,
                **kwargs,
            )
        except httpx.TimeoutException as exc:
            raise error(
                504,
                "dependency_timeout",
                f"{name} validation timed out",
                dependency=name,
            ) from exc
        except httpx.HTTPError as exc:
            raise error(
                503,
                "dependency_unavailable",
                f"{name} validation is unavailable",
                dependency=name,
            ) from exc
        if response.status_code >= 500:
            raise error(
                503,
                "dependency_unavailable",
                f"{name} validation is unavailable",
                dependency=name,
            )
        if response.status_code >= 400:
            if response.status_code == 404:
                return {"allowed": False}
            raise error(
                502,
                "dependency_invalid_response",
                f"{name} returned an invalid response",
                dependency=name,
            )
        try:
            payload = response.json()
            return payload.get("data", payload)
        except (ValueError, TypeError, AttributeError) as exc:
            raise error(
                502,
                "dependency_invalid_response",
                f"{name} returned an invalid response",
                dependency=name,
            ) from exc

    def _property_actor_token(self, actor: Principal) -> str:
        service_token = self._identity_token()
        if not actor.bearer:
            raise error(
                503,
                "dependency_unavailable",
                "Identity delegation is unavailable",
                dependency="identity-access-service",
            )
        result = self._request(
            "identity-access-service",
            "POST",
            f"{self.settings.identity_base_url.rstrip('/')}/internal/v1/tokens/exchange",
            service_token,
            json={
                "user_token": actor.bearer,
                "target_audience": "property-leasing-service",
                # Property Leasing's authorization projections decide from the
                # authenticated actor/resource relation. No domain permission is
                # delegated, which prevents a Maintenance hop from widening scope.
                "requested_scopes": [],
            },
        )
        token = result.get("access_token")
        if not isinstance(token, str) or len(token) < 20:
            raise error(
                502,
                "dependency_invalid_response",
                "Identity returned an invalid delegation",
                dependency="identity-access-service",
            )
        return token

    def lease_access(self, actor: Principal, lease_id: UUID, property_id: UUID) -> dict:
        token = self._property_actor_token(actor)
        result = self._request(
            "property-leasing-service",
            "POST",
            f"{self.settings.property_base_url.rstrip('/')}/internal/v1/authorizations/lease-action:check",
            token,
            json={
                "subject_id": str(actor.subject_id),
                "lease_id": str(lease_id),
                "property_id": str(property_id),
                "action": "maintenance:create",
            },
        )
        required = {
            "allowed",
            "lease_id",
            "property_id",
            "status",
            "lease_version",
            "relationship_version",
        }
        if not required.issubset(result):
            if result.get("allowed") is False:
                return result
            raise error(
                502,
                "dependency_invalid_response",
                "Property Leasing returned an invalid response",
                dependency="property-leasing-service",
            )
        if (
            str(result["lease_id"]) != str(lease_id)
            or str(result["property_id"]) != str(property_id)
            or not isinstance(result["allowed"], bool)
            or not isinstance(result["lease_version"], int)
            or not isinstance(result["relationship_version"], int)
        ):
            raise error(
                502,
                "dependency_invalid_response",
                "Property Leasing returned a mismatched authorization",
                dependency="property-leasing-service",
            )
        return result

    def property_access(self, actor: Principal, property_id: UUID, action: str) -> bool:
        token = self._property_actor_token(actor)
        result = self._request(
            "property-leasing-service",
            "POST",
            f"{self.settings.property_base_url.rstrip('/')}/internal/v1/authorizations/property-access:check",
            token,
            json={
                "subject_id": str(actor.subject_id),
                "property_id": str(property_id),
                "action": action,
            },
        )
        if str(result.get("property_id")) != str(property_id) or not isinstance(
            result.get("allowed"), bool
        ):
            raise error(
                502,
                "dependency_invalid_response",
                "Property Leasing returned a mismatched authorization",
                dependency="property-leasing-service",
            )
        return result.get("allowed") is True

    def staff(self, staff_id: UUID) -> dict:
        return self._request(
            "identity-access-service",
            "GET",
            f"{self.settings.identity_base_url.rstrip('/')}/internal/v1/staff/{staff_id}",
            self._identity_token(),
        )

    def require_active_maintainer(self, staff_id: UUID) -> dict:
        projection = self.staff(staff_id)
        if (
            str(projection.get("id")) != str(staff_id)
            or projection.get("status", "active") != "active"
            or projection.get("employment_status") != "active"
            or projection.get("role") != "maintainer"
        ):
            raise error(
                409,
                "assignee_inactive",
                "Assignee is not an active maintainer",
                assignee_id=str(staff_id),
            )
        return projection

    def acknowledge_deletion(
        self, request_id: UUID, status: str, details: dict
    ) -> dict:
        return self._request(
            "identity-access-service",
            "POST",
            f"{self.settings.identity_base_url.rstrip('/')}/internal/v1/subject-deletions/"
            f"{request_id}/acknowledgements",
            self._identity_token(),
            json={
                "service": "maintenance",
                "status": status,
                "details_redacted": details,
            },
        )
