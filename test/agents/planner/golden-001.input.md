# Spec: TECH-999 Add health check endpoint

## Scope
Add `/health` endpoint to FastAPI application that returns service status.

## Allowed Files
1. `src/api/health.py` — NEW: health endpoint
2. `src/api/main.py` — MODIFY: register health router
3. `tests/test_health.py` — NEW: health endpoint tests

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Health endpoint responds | GET /health | 200 OK with status | deterministic | user | P0 |
| EC-2 | Health includes DB check | GET /health | db_connected: true/false | deterministic | design | P1 |

### Coverage Summary
- Deterministic: 2 | Total: 2

### TDD Order
1. EC-1 -> basic endpoint
2. EC-2 -> DB check
