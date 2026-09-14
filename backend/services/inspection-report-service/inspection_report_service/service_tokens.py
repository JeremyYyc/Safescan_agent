import secrets
import threading
import time
from collections.abc import Callable

import jwt

from .config import Settings


class IdentityServiceTokenProvider:
    """Caches and refreshes Identity's short-lived service JWT."""

    required_scopes = (
        "identity:token_exchange",
        "report:read_work_context",
        "work_order:read_assigned",
    )

    def __init__(
        self,
        settings: Settings,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings
        self.clock = clock
        self._lock = threading.Lock()
        self._token: str | None = None
        self._expires_at = 0.0

    def token(self) -> str | None:
        now = self.clock()
        if self._fresh(now):
            return self._token
        with self._lock:
            now = self.clock()
            if self._fresh(now):
                return self._token
            configured = self.settings.identity_service_token.get_secret_value().strip()
            if configured and self._token is None:
                expires_at = self._configured_expiry(configured)
                if expires_at > now + self.settings.identity_service_token_refresh_skew_seconds:
                    self._token, self._expires_at = configured, expires_at
                    return configured
                if not expires_at and not self.settings.formal_runtime:
                    # Some local fixtures still use an opaque stand-in. It is
                    # never accepted as a production service credential.
                    self._token, self._expires_at = configured, float("inf")
                    return configured
            credential = self.settings.identity_service_credential.get_secret_value()
            if len(credential) < 24:
                return None
            issued_at = int(now)
            expires_at = issued_at + self.settings.identity_service_token_seconds
            self._token = jwt.encode(
                {
                    "aud": self.settings.identity_internal_audience,
                    "exp": expires_at,
                    "iat": issued_at,
                    "iss": self.settings.jwt_issuer,
                    "jti": secrets.token_hex(16),
                    "nbf": issued_at,
                    "scopes": list(self.required_scopes),
                    "sub": f"service:{self.settings.identity_service_client_code}",
                },
                credential,
                algorithm="HS256",
            )
            self._expires_at = float(expires_at)
            return self._token

    def require_token(self) -> str:
        token = self.token()
        if not token:
            raise RuntimeError("Identity service credential is unavailable")
        return token

    def _fresh(self, now: float) -> bool:
        return bool(
            self._token
            and self._expires_at
            > now + self.settings.identity_service_token_refresh_skew_seconds
        )

    def _configured_expiry(self, token: str) -> float:
        try:
            credential = self.settings.identity_service_credential.get_secret_value()
            if len(credential) >= 24:
                claims = jwt.decode(
                    token,
                    credential,
                    algorithms=["HS256"],
                    audience=self.settings.identity_internal_audience,
                    issuer=self.settings.jwt_issuer,
                    options={
                        "require": ["aud", "exp", "iat", "iss", "jti", "nbf", "sub"],
                    },
                )
                if claims.get("sub") != f"service:{self.settings.identity_service_client_code}":
                    return 0.0
                scopes = set(claims.get("scopes") or [])
                if not set(self.required_scopes).issubset(scopes):
                    return 0.0
            else:
                claims = jwt.decode(token, options={"verify_signature": False})
            return float(claims.get("exp") or 0)
        except (jwt.PyJWTError, TypeError, ValueError):
            return 0.0
