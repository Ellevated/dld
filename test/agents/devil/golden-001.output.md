# Reference Output (Devil's Advocate)

## Why NOT

1. **New dependency risk:** Redis adds operational complexity. If Redis goes down, the fallback logic must be tested. Most teams underestimate Redis failure modes.
2. **Cache invalidation is hard:** LLM prompts may include dynamic context (user data, timestamps). Identical prompt text != identical intent.
3. **30% repeat rate may not justify:** At 500 queries/day, only 150 are repeats. Saving 2-5 seconds on 150 calls = 5-12 minutes total. Is this worth Redis ops?

## Simpler Alternatives

1. **In-memory LRU cache:** `functools.lru_cache` or `cachetools` — zero infra, same benefit for single-instance deployments
2. **Prompt deduplication at API layer:** If same user sends identical query within 10 seconds, return previous response (debounce pattern)
3. **Skip entirely:** 2-5 seconds is acceptable for LLM calls. Users expect AI to "think"

## What Breaks

- `src/domains/seller/agent.py` — adding cache check changes the async flow
- `.env` — new required variable means deployment update
- Tests — mock Redis or add integration test dependency

## Eval Assertions

### Deterministic Assertions

| ID | Scenario | Input | Expected Behavior | Risk | Priority | Type |
|----|----------|-------|-------------------|------|----------|------|
| DA-1 | Cache miss | New prompt | Falls through to LLM | High | P0 | deterministic |
| DA-2 | Redis down | Any prompt | Graceful fallback to direct LLM | High | P0 | deterministic |
| DA-3 | Cache hit with stale data | Cached prompt with changed context | Returns stale response | Med | P1 | deterministic |

### Side-Effect Assertions

| ID | Affected Component | File:line | Regression Check | Priority |
|----|-------------------|-----------|------------------|----------|
| SA-1 | seller agent | agent.py:45 | Async flow unchanged without cache | P0 |
| SA-2 | deployment | .env | REDIS_URL optional, not required | P1 |

### Assertion Summary
- Deterministic: 3 | Side-effect: 2 | Total: 5
