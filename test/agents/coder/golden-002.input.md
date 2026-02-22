# Task 1/4: Create rate counter storage

**Type:** code
**Files:**
  - Create: `src/infra/cache/rate_store.py`
**Pattern:** Redis INCR + EXPIRE for sliding window counter
**Acceptance:** `increment(key) -> count`, `is_limited(key, limit) -> bool`, automatic TTL reset

## Context
- FastAPI application with Redis already configured
- Existing `src/infra/cache/redis_client.py` provides `get_redis()` async connection
- Pattern: async everywhere, Result[T, E] for domain boundaries
- Rate limit: 100 requests/minute per authenticated user, 20/minute anonymous
- TTL: 60 seconds window

## Existing redis_client.py structure (excerpt)
```python
import redis.asyncio as redis
from src.shared.config import settings

_pool = None

async def get_redis() -> redis.Redis:
    global _pool
    if _pool is None:
        _pool = redis.from_url(settings.REDIS_URL)
    return _pool
```
