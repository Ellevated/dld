# Spec: TECH-042 Add API rate limiting

## Scope
Implement per-user rate limiting on all API endpoints. Limit: 100 requests/minute per authenticated user, 20/minute for anonymous.

## Allowed Files
1. `src/api/middleware/rate_limit.py` — NEW: rate limiting middleware
2. `src/infra/cache/rate_store.py` — NEW: rate counter storage (Redis)
3. `src/api/main.py` — MODIFY: register middleware
4. `tests/test_rate_limit.py` — NEW: rate limiting tests

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Under limit | 50 requests in 1 min | All return 200 | deterministic | user | P0 |
| EC-2 | Over limit | 101 requests in 1 min | 101st returns 429 | deterministic | user | P0 |
| EC-3 | Anonymous lower limit | 21 anon requests in 1 min | 21st returns 429 | deterministic | design | P1 |
| EC-4 | Rate reset | Wait 60 seconds after limit | Next request returns 200 | deterministic | design | P1 |

### Coverage Summary
- Deterministic: 4 | Total: 4

### TDD Order
1. EC-1 -> basic middleware passes requests
2. EC-2 -> enforce limit
3. EC-3 -> anonymous vs authenticated
4. EC-4 -> window reset
