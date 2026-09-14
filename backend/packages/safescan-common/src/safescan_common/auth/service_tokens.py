import asyncio
import base64
import threading
import time
from collections.abc import Callable

import httpx


class ServiceTokenError(RuntimeError):
    """Credential exchange failed without retaining credential material."""

    def __init__(self, status_code: int | None = None) -> None:
        super().__init__("Identity service-token exchange failed")
        self.status_code = status_code


def _basic(client_id: str, client_secret: str) -> str:
    value = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    return f"Basic {value}"


def _lease(response: httpx.Response) -> tuple[str, int]:
    if response.status_code != 200:
        raise ServiceTokenError(response.status_code)
    try:
        payload = response.json()
        data = payload.get("data", payload)
        token = data["access_token"]
        expires_in = int(data["expires_in"])
    except (ValueError, KeyError, TypeError) as exc:
        raise ServiceTokenError(response.status_code) from exc
    if not isinstance(token, str) or len(token) < 20 or expires_in < 1:
        raise ServiceTokenError(response.status_code)
    return token, expires_in


class ServiceTokenProvider:
    """Thread-safe short-lived service-token cache with single-flight refresh."""

    def __init__(
        self, identity_url: str, client_id: str, client_secret: str,
        scopes: list[str] | tuple[str, ...], *, timeout: float = 2.0,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._authorization = _basic(client_id, client_secret)
        self._scopes = sorted(set(scopes))
        self._clock = clock
        self._lock = threading.Lock()
        self._token = ""
        self._refresh_at = 0.0
        self._http = httpx.Client(base_url=identity_url.rstrip("/"), timeout=timeout,
                                  transport=transport)

    def _valid(self) -> bool:
        return bool(self._token) and self._clock() < self._refresh_at

    def get(self) -> str:
        if self._valid():
            return self._token
        with self._lock:
            if self._valid():
                return self._token
            response = self._http.post(
                "/internal/v1/service-tokens",
                headers={"Authorization": self._authorization},
                json={"requested_scopes": self._scopes},
            )
            token, expires_in = _lease(response)
            self._token = token
            self._refresh_at = self._clock() + max(1, expires_in - min(30, expires_in // 5))
            return token

    def invalidate(self, rejected_token: str | None = None) -> None:
        with self._lock:
            if rejected_token is None or self._token == rejected_token:
                self._refresh_at = 0.0

    def close(self) -> None:
        self._http.close()


class AsyncServiceTokenProvider:
    """Async equivalent used by pooled Portal BFF clients."""

    def __init__(
        self, identity_url: str, client_id: str, client_secret: str,
        scopes: list[str] | tuple[str, ...], *, timeout: float = 2.0,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._authorization = _basic(client_id, client_secret)
        self._scopes = sorted(set(scopes))
        self._clock = clock
        self._lock = asyncio.Lock()
        self._token = ""
        self._refresh_at = 0.0
        self._http = httpx.AsyncClient(base_url=identity_url.rstrip("/"), timeout=timeout,
                                       transport=transport)

    def _valid(self) -> bool:
        return bool(self._token) and self._clock() < self._refresh_at

    async def get(self) -> str:
        if self._valid():
            return self._token
        async with self._lock:
            if self._valid():
                return self._token
            response = await self._http.post(
                "/internal/v1/service-tokens",
                headers={"Authorization": self._authorization},
                json={"requested_scopes": self._scopes},
            )
            token, expires_in = _lease(response)
            self._token = token
            self._refresh_at = self._clock() + max(1, expires_in - min(30, expires_in // 5))
            return token

    async def invalidate(self, rejected_token: str | None = None) -> None:
        async with self._lock:
            if rejected_token is None or self._token == rejected_token:
                self._refresh_at = 0.0

    async def close(self) -> None:
        await self._http.aclose()
