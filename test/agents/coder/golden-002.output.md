# Reference Output (Coder)

## Created: src/infra/cache/rate_store.py

```python
"""
Module: rate_store
Role: Redis-based rate limiting counter with sliding window
Uses: redis_client (get_redis)
Used by: rate_limit middleware
"""

from src.infra.cache.redis_client import get_redis


async def increment(key: str, window_seconds: int = 60) -> int:
    """Increment counter for key, return current count. Auto-expires after window."""
    r = await get_redis()
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, window_seconds)
    results = await pipe.execute()
    return results[0]


async def is_limited(key: str, limit: int, window_seconds: int = 60) -> bool:
    """Check if key has exceeded rate limit within window."""
    count = await increment(key, window_seconds)
    return count > limit
```

## files_changed
- src/infra/cache/rate_store.py (created)
