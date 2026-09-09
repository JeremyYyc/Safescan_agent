import hashlib
import json
from typing import Any, Protocol

from redis.exceptions import RedisError

from .auth import Principal


class Cache(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl: int) -> None: ...
    async def invalidate_subject(self, subject: str) -> None: ...
    async def ready(self) -> bool: ...


def private_cache_key(namespace: str, principal: Principal, vary: str = "") -> str:
    permissions = hashlib.sha256(
        "\n".join(sorted(principal.permissions)).encode()
    ).hexdigest()[:16]
    scopes = hashlib.sha256("\n".join(principal.scopes).encode()).hexdigest()[:16]
    vary_hash = hashlib.sha256(vary.encode()).hexdigest()[:16]
    return f"staff:v1:{namespace}:sub:{principal.subject}:av:{principal.auth_version}:rv:{principal.role_version}:role:{principal.role.value}:perm:{permissions}:scope:{scopes}:v:{vary_hash}"


class MemoryCache:
    def __init__(self):
        self.values: dict[str, Any] = {}

    async def get(self, key: str) -> Any | None:
        return self.values.get(key)

    async def set(self, key: str, value: Any, ttl: int) -> None:
        self.values[key] = value

    async def invalidate_subject(self, subject: str) -> None:
        marker = f":sub:{subject}:"
        for key in [key for key in self.values if marker in key]:
            self.values.pop(key, None)

    async def ready(self) -> bool:
        return True


class RedisCache:
    def __init__(self, url: str):
        from redis.asyncio import from_url

        self.redis = from_url(url, decode_responses=True)

    async def get(self, key: str) -> Any | None:
        value = await self.redis.get(key)
        return json.loads(value) if value else None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        await self.redis.set(key, json.dumps(value), ex=ttl)

    async def invalidate_subject(self, subject: str) -> None:
        async for key in self.redis.scan_iter(match=f"staff:v1:*:sub:{subject}:*"):
            await self.redis.delete(key)

    async def ready(self) -> bool:
        try:
            return bool(await self.redis.ping())
        except (RedisError, OSError):
            return False
