from uuid import UUID

import httpx

from .auth import Principal
from .config import Settings
from .errors import dependency_error
from .service_tokens import IdentityServiceTokenProvider


def _payload(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError as exc:
        raise dependency_error("dependency_invalid_response", "property-leasing") from exc
    return body.get("data", body) if isinstance(body, dict) else {}


class PropertyLeasingClient:
    """Controlled HTTP boundary; never reads the property_leasing schema."""

    def __init__(
        self,
        settings: Settings,
        token_provider: IdentityServiceTokenProvider | None = None,
    ) -> None:
        self.settings = settings
        self.token_provider = token_provider or IdentityServiceTokenProvider(settings)

    def require_identity_service_token(self) -> str:
        return self.token_provider.require_token()

    def _delegated_token(self, principal: Principal) -> str:
        service_token = self.token_provider.token()
        if not service_token:
            if self.settings.formal_runtime:
                raise dependency_error("dependency_unavailable", "identity-access")
            # Local compatibility only. Formal runtimes always use a separately
            # authenticated, short-lived Identity service token.
            return principal.token
        try:
            response = httpx.post(
                f"{self.settings.identity_base_url}/internal/v1/tokens/exchange",
                headers={"Authorization": f"Bearer {service_token}"},
                json={
                    "user_token": principal.token,
                    "target_audience": "property-leasing-service",
                    # Property Leasing decides from the authenticated actor and
                    # authoritative resource scope. No report permission needs
                    # to cross this service boundary.
                    "requested_scopes": [],
                },
                timeout=self.settings.dependency_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise dependency_error("dependency_timeout", "identity-access") from exc
        except httpx.HTTPError as exc:
            raise dependency_error("dependency_unavailable", "identity-access") from exc
        if response.status_code >= 500:
            raise dependency_error("dependency_unavailable", "identity-access")
        if response.status_code != 200:
            raise dependency_error("dependency_invalid_response", "identity-access")
        token = _payload(response).get("access_token")
        if not token:
            raise dependency_error("dependency_invalid_response", "identity-access")
        return str(token)

    def _request(self, principal: Principal, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = httpx.request(
                method,
                f"{self.settings.property_leasing_base_url}{path}",
                headers={"Authorization": f"Bearer {self._delegated_token(principal)}"},
                timeout=self.settings.dependency_timeout_seconds,
                **kwargs,
            )
        except httpx.TimeoutException as exc:
            raise dependency_error("dependency_timeout", "property-leasing") from exc
        except httpx.HTTPError as exc:
            raise dependency_error("dependency_unavailable", "property-leasing") from exc
        if response.status_code >= 500:
            raise dependency_error("dependency_unavailable", "property-leasing")
        return response

    def property_access(self, principal: Principal, property_id: UUID, action: str) -> dict:
        response = self._request(
            principal, "POST", "/internal/v1/authorizations/property-access:check",
            json={"subject_id": str(principal.subject_id), "property_id": str(property_id), "action": action},
        )
        if response.status_code != 200:
            return {"allowed": False}
        result = _payload(response)
        # The frozen contract requires active_lease_id for staff report generation.
        # Baseline Leasing omits it for staff, so use its authorized list API as a
        # compatibility fallback without reading another schema.
        if principal.account_type == "staff" and result.get("allowed") and not result.get("active_lease_id"):
            leases = self._request(
                principal, "GET", "/internal/v1/leases",
                params={"property_id": str(property_id), "status": "active", "limit": 2},
            )
            if leases.status_code == 200:
                items = _payload(leases).get("items", [])
                if len(items) == 1:
                    result["active_lease_id"] = items[0].get("id")
        return result

    def lease_access(self, principal: Principal, lease_id: UUID, property_id: UUID, action: str) -> dict:
        response = self._request(
            principal, "POST", "/internal/v1/authorizations/lease-action:check",
            json={
                "subject_id": str(principal.subject_id), "lease_id": str(lease_id),
                "property_id": str(property_id), "action": action,
            },
        )
        return _payload(response) if response.status_code == 200 else {"allowed": False}


class MaintenanceClient:
    """Validates a maintainer's assigned work order over the owned HTTP API."""

    def __init__(
        self,
        settings: Settings,
        token_provider: IdentityServiceTokenProvider | None = None,
    ) -> None:
        self.settings = settings
        self.token_provider = token_provider or IdentityServiceTokenProvider(settings)

    def order_access(self, principal: Principal, order_id: UUID, report_id: UUID) -> dict:
        service_token = self.token_provider.token()
        if not service_token:
            if self.settings.formal_runtime:
                raise dependency_error("dependency_unavailable", "identity-access")
            token = principal.token
        else:
            try:
                exchange = httpx.post(
                    f"{self.settings.identity_base_url}/internal/v1/tokens/exchange",
                    headers={"Authorization": f"Bearer {service_token}"},
                    json={
                        "user_token": principal.token,
                        "target_audience": "maintenance-service",
                        "requested_scopes": ["work_order:read_assigned", "report:read_work_context"],
                    },
                    timeout=self.settings.dependency_timeout_seconds,
                )
            except httpx.HTTPError as exc:
                raise dependency_error("dependency_unavailable", "identity-access") from exc
            if exchange.status_code != 200:
                raise dependency_error("dependency_invalid_response", "identity-access")
            token = _payload(exchange).get("access_token")
            if not token:
                raise dependency_error("dependency_invalid_response", "identity-access")
        try:
            response = httpx.post(
                f"{self.settings.maintenance_base_url}/internal/v1/authorizations/order-access:check",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "subject_id": str(principal.subject_id), "order_id": str(order_id),
                    "action": "report:read_work_context", "report_id": str(report_id),
                },
                timeout=self.settings.dependency_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise dependency_error("dependency_timeout", "maintenance") from exc
        except httpx.HTTPError as exc:
            raise dependency_error("dependency_unavailable", "maintenance") from exc
        if response.status_code >= 500:
            raise dependency_error("dependency_unavailable", "maintenance")
        return _payload(response) if response.status_code == 200 else {"allowed": False}
