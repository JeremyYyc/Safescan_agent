import json
import os
import random
from functools import lru_cache

from fastapi.encoders import jsonable_encoder

try:
    import redis
except ImportError:  # pragma: no cover - permits minimal local tooling
    redis = None


class QueryCache:
    """Best-effort Redis cache; PostgreSQL remains the only business truth."""

    def __init__(self, url: str | None) -> None:
        self.client = redis.Redis.from_url(url, decode_responses=True,
                                           socket_connect_timeout=0.2,
                                           socket_timeout=0.2) if redis and url else None

    def get(self, key: str):
        if not self.client:
            return None
        try:
            value = self.client.get(key)
            return json.loads(value) if value else None
        except (redis.RedisError, ValueError):
            return None

    def set(self, key: str, value, ttl: int = 60) -> None:
        if not self.client:
            return
        try:
            self.client.setex(key, ttl + random.randint(0, max(1, ttl // 5)),
                              json.dumps(jsonable_encoder(value), separators=(",", ":")))
        except redis.RedisError:
            pass

    def market_epoch(self) -> str:
        if not self.client:
            return "0"
        try:
            return self.client.get("leasing:market:epoch") or "0"
        except redis.RedisError:
            return "0"

    def invalidate_market(self) -> None:
        if not self.client:
            return
        try:
            self.client.incr("leasing:market:epoch")
        except redis.RedisError:
            pass


@lru_cache(maxsize=1)
def get_query_cache() -> QueryCache:
    return QueryCache(os.getenv("REDIS_URL"))
