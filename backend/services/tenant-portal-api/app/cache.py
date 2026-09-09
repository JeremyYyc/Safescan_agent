import hashlib
import json
from typing import Any

from redis.exceptions import RedisError

from .auth import Principal


def cache_key(namespace: str, principal: Principal, vary: str = "") -> str:
    subject = principal.subject or "guest"
    permissions = hashlib.sha256(
        "\n".join(sorted(principal.permissions)).encode()
    ).hexdigest()[:16]
    vary_hash = hashlib.sha256(vary.encode()).hexdigest()[:16]
    return f"tenant:v1:{namespace}:sub:{subject}:av:{principal.auth_version}:sv:{principal.status_version}:status:{principal.status.value if principal.status else 'guest'}:perm:{permissions}:v:{vary_hash}"


class MemoryCache:
    def __init__(self):
        self.values: dict[str, Any] = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ttl):
        self.values[key] = value

    async def invalidate_subject(self, subject):
        marker = f":sub:{subject}:"
        for key in [k for k in self.values if marker in k]:
            self.values.pop(key, None)

    async def ready(self):
        return True


class RedisCache:
    def __init__(self, url):
        from redis.asyncio import from_url

        self.redis = from_url(url, decode_responses=True)

    async def get(self, key):
        value = await self.redis.get(key)
        return json.loads(value) if value else None

    async def set(self, key, value, ttl):
        await self.redis.set(key, json.dumps(value), ex=ttl)

    async def invalidate_subject(self, subject):
        async for key in self.redis.scan_iter(match=f"tenant:v1:*:sub:{subject}:*"):
            await self.redis.delete(key)

    async def ready(self):
        try:
            return bool(await self.redis.ping())
        except (RedisError, OSError):
            return False
