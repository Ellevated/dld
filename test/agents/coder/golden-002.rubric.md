# Scoring Rubric: Coder — Rate Counter Storage

## Completeness (weight: high)
- Must create `src/infra/cache/rate_store.py` with `increment` and `is_limited` functions
- Must use Redis pipeline for atomic INCR + EXPIRE
- Must report `files_changed` list
- Must include module header with Uses/Used by

## Accuracy (weight: high)
- Code must be syntactically correct Python
- Must use `redis.asyncio` via existing `get_redis()` helper
- Redis INCR + EXPIRE pipeline is the correct pattern for rate limiting
- `is_limited` must return True when count > limit (not >=)
- Window seconds must be configurable with sensible default (60)

## Format (weight: medium)
- Code blocks with proper Python language tags
- Module header comment present
- files_changed list at the end
- Functions have docstrings

## Relevance (weight: high)
- Only implements storage layer (not middleware, not endpoint)
- Uses existing redis_client.py (no new Redis connection)
- No over-engineering (no Lua scripts, no token bucket, no distributed consensus)
- Follows project patterns (async, imports from infra)

## Safety (weight: medium)
- No hardcoded connection strings
- Uses pipeline for atomicity (no race condition between INCR and EXPIRE)
- No global mutable state beyond what redis_client already manages
