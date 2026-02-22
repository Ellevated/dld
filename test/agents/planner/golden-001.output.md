# Reference Output (Planner)

## Implementation Plan

### Task 1: Create health endpoint with basic response
**Type:** code
**Files:**
  - Create: `src/api/health.py`
  - Modify: `src/api/main.py`
**Pattern:** FastAPI router pattern (existing in main.py)
**Acceptance:** GET /health returns `{"status": "ok"}`
**Test first:** Write test for EC-1, verify it fails, then implement

### Task 2: Add database connectivity check
**Type:** code
**Files:**
  - Modify: `src/api/health.py`
**Pattern:** Try DB query, catch exception, return status
**Acceptance:** Response includes `db_connected: true` when DB is up, `false` when down
**Test first:** Write test for EC-2, verify it fails, then implement

### Task 3: Write test file
**Type:** test
**Files:**
  - Create: `tests/test_health.py`
**Pattern:** pytest + httpx async client
**Acceptance:** Both EC-1 and EC-2 covered, tests pass

### Execution Order
1 -> 3 -> 2 (TDD: test first)

## Drift Analysis
- No conflicts with existing codebase
- `src/api/main.py` exists and has router registration pattern
- No deleted files or API changes detected
