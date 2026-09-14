import secrets
import threading
import time
from collections.abc import Callable

import jwt

from app.core.config import Settings


SERVICE_CLIENT_CODE = "property-leasing"
SERVICE_SCOPES = ("identity:customer_status_write", "identity:subject_read")


class IdentityServiceTokenProvider:
    """Provide short-lived, least-privilege JWTs accepted by Identity's client allowlist."""

    def __init__(self, settings: Settings, *, clock: Callable[[], float] = time.time) -> None:
        self.settings = settings
        self.clock = clock
        self._lock = threading.Lock()
        self._token: str | None = None
        self._expires_at = 0

    @property
    def refreshable(self) -> bool:
        return bool(self.settings.identity_service_credential.get_secret_value())

    def invalidate(self) -> None:
        if self.refreshable:
            with self._lock:
                self._expires_at = 0

    def token(self) -> str:
        now = int(self.clock())
        if self.refreshable:
            with self._lock:
                if self._token and now < self._expires_at - self.settings.identity_token_refresh_skew_seconds:
                    return self._token
                self._token, self._expires_at = self._issue(now)
                return self._token

        static_token = self.settings.identity_service_token.get_secret_value()
        if not static_token:
            raise RuntimeError("Identity service credential is unavailable")
        self._validate_claims(static_token, now)
        return static_token

    def _issue(self, now: int) -> tuple[str, int]:
        expires_at = now + self.settings.identity_service_token_seconds
        payload = {
            "aud": self.settings.identity_internal_audience,
            "exp": expires_at,
            "iat": now,
            "iss": self.settings.jwt_issuer,
            "jti": secrets.token_hex(16),
            "nbf": now,
            "scopes": list(SERVICE_SCOPES),
            "sub": f"service:{SERVICE_CLIENT_CODE}",
        }
        return (
            jwt.encode(
                payload,
                self.settings.identity_service_credential.get_secret_value(),
                algorithm="HS256",
            ),
            expires_at,
        )

    def _validate_claims(self, token: str, now: int) -> None:
        try:
            claims = jwt.decode(
                token,
                options={"verify_signature": False, "verify_exp": False},
                algorithms=["HS256"],
            )
            expires_at = int(claims["exp"])
            scopes = claims["scopes"]
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Identity service token is malformed") from exc
        if claims.get("sub") != f"service:{SERVICE_CLIENT_CODE}":
            raise RuntimeError("Identity service token has the wrong subject")
        if claims.get("iss") != self.settings.jwt_issuer:
            raise RuntimeError("Identity service token has the wrong issuer")
        audience = claims.get("aud")
        if audience != self.settings.identity_internal_audience:
            raise RuntimeError("Identity service token has the wrong audience")
        if not isinstance(scopes, list) or not set(SERVICE_SCOPES).issubset(scopes):
            raise RuntimeError("Identity service token is missing required scopes")
        if expires_at <= now + self.settings.identity_token_refresh_skew_seconds:
            raise RuntimeError("Identity service token is expired or cannot be refreshed")
