from uuid import UUID

import httpx
from safescan_common.auth import ServiceTokenError, ServiceTokenProvider

from app.core.config import Settings
from app.core.errors import error
from app.domain.principal import Principal


class DependencyClient:
    _IDENTITY_SCOPES = (
        "identity:subject_read",
        "identity:subject_deletion_ack",
        "identity:token_exchange",
    )

    def __init__(
        self,
        settings: Settings,
        service_tokens: ServiceTokenProvider | None = None,
    ) -> None:
        self.settings = settings
        secret = settings.identity_client_secret.get_secret_value()
        self._service_tokens = service_tokens or (
            ServiceTokenProvider(
                settings.identity_base_url,
                settings.identity_client_id,
                secret,
                self._IDENTITY_SCOPES,
                timeout=settings.dependency_timeout_seconds,
            )
            if secret
            else None
        )

    def _service_token(self) -> str:
        if self._service_tokens is None:
            raise error(
                503,
                "dependency_unavailable",
                "Identity credentials are unavailable",
                dependency="identity-access-service",
            )
        try:
            return self._service_tokens.get()
        except (ServiceTokenError, httpx.HTTPError) as exc:
            raise error(
                503,
                "dependency_unavailable",
                "Identity credentials are unavailable",
                dependency="identity-access-service",
            ) from exc

    def identity_ready(self) -> None:
        self._service_token()

    def _identity_request(self, method: str, path: str, **kwargs) -> dict:
        for attempt in range(2):
            token = self._service_token()
            try:
                response = httpx.request(
                    method,
                    f"{self.settings.identity_base_url.rstrip('/')}{path}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=self.settings.dependency_timeout_seconds,
                    **kwargs,
                )
            except httpx.TimeoutException as exc:
                raise error(
                    504,
                    "dependency_timeout",
                    "identity-access-service validation timed out",
                    dependency="identity-access-service",
                ) from exc
            except httpx.HTTPError as exc:
                raise error(
                    503,
                    "dependency_unavailable",
                    "identity-access-service validation is unavailable",
                    dependency="identity-access-service",
                ) from exc
            if response.status_code != 401 or attempt == 1:
                return self._response_payload("identity-access-service", response)
            # Only invalidate the token this request actually used. Another
            # thread may already have refreshed the provider after our request
            # left the process.
            self._service_tokens.invalidate(token)
        raise AssertionError("identity retry loop must return")

    @staticmethod
    def _response_payload(name: str, response: httpx.Response) -> dict:
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
        return self._response_payload(name, response)

    def _property_actor_token(self, actor: Principal) -> str:
        if not actor.bearer:
            raise error(
                503,
                "dependency_unavailable",
                "Identity delegation is unavailable",
                dependency="identity-access-service",
            )
        result = self._identity_request(
            "POST",
            "/internal/v1/tokens/exchange",
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
        return self._identity_request(
            "GET",
            f"/internal/v1/staff/{staff_id}",
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
        return self._identity_request(
            "POST",
            "/internal/v1/subject-deletions/"
            f"{request_id}/acknowledgements",
            json={
                "service": "maintenance",
                "status": status,
                "details_redacted": details,
            },
        )
