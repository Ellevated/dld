# Reference Output (Planner)

## Implementation Plan

### Task 1: Create rate counter storage
**Type:** code
**Files:**
  - Create: `src/infra/cache/rate_store.py`
**Pattern:** Redis INCR + EXPIRE for sliding window counter
**Acceptance:** `increment(key) -> count`, `is_limited(key, limit) -> bool`, automatic TTL reset
**Test first:** Unit test for counter logic with mock Redis

### Task 2: Create rate limiting middleware
**Type:** code
**Files:**
  - Create: `src/api/middleware/rate_limit.py`
  - Modify: `src/api/main.py`
**Pattern:** FastAPI middleware pattern (`@app.middleware("http")`)
**Acceptance:**
  - Extract user ID from auth header (or IP for anonymous)
  - Check rate_store.is_limited()
  - If limited: return 429 with `Retry-After` header
  - If not: increment counter and pass through
**Test first:** Write test for EC-2 (over limit returns 429), verify it fails, then implement

### Task 3: Differentiate authenticated vs anonymous limits
**Type:** code
**Files:**
  - Modify: `src/api/middleware/rate_limit.py`
**Pattern:** Check auth header presence → select limit (100 vs 20)
**Acceptance:** EC-3 — anonymous users limited at 20/min, authenticated at 100/min
**Test first:** Write test for EC-3, verify it fails, then implement

### Task 4: Write comprehensive test file
**Type:** test
**Files:**
  - Create: `tests/test_rate_limit.py`
**Pattern:** pytest + httpx async client + Redis mock (fakeredis)
**Acceptance:** EC-1 through EC-4 all covered, all pass
**Dependencies:** fakeredis or test Redis instance

### Execution Order
1 -> 2 -> 4 -> 3 (infra first, then middleware, then tests, then refinement)

## Drift Analysis
- No conflicts with existing codebase
- `src/api/main.py` exists, middleware registration pattern available
- Redis connection available via existing `src/infra/cache/redis_client.py`
- No middleware directory exists — will create `src/api/middleware/`
