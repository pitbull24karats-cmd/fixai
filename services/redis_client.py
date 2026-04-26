import redis.asyncio as aioredis
from typing import Optional

REDIS_URL = "redis://localhost:6379"

_pool: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _pool
