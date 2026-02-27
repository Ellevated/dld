# Reference Output (Planner)

## Implementation Plan

### Task 1: Create database migration for preferences table
**Type:** migration
**Files:**
  - Create: `db/migrations/005_notification_preferences.sql`
**Pattern:** SQL migration with `IF NOT EXISTS`
**Acceptance:** Table `notification_preferences` with columns: user_id (FK), email (bool), push (bool), in_app (bool), created_at, updated_at
**Note:** Migration is git-first only — do NOT apply directly

### Task 2: Create preference model and service
**Type:** code
**Files:**
  - Create: `src/domains/notifications/preferences.py`
**Pattern:** Domain service with Result[T, E] pattern
**Acceptance:**
  - `get_preferences(user_id) -> Result[Preferences, NotFoundError]`
  - `update_preferences(user_id, changes) -> Result[Preferences, ValidationError]`
  - Default preferences: all channels enabled
  - Validate channel names against allowed set
**Test first:** Write test for EC-1 (default preferences), verify it fails

### Task 3: Create REST endpoints
**Type:** code
**Files:**
  - Create: `src/api/notifications.py`
  - Modify: `src/api/main.py`
**Pattern:** FastAPI router with Pydantic models
**Acceptance:**
  - `GET /notifications/preferences` -> current preferences
  - `PATCH /notifications/preferences` -> partial update
  - Auth required (user from token)
**Test first:** Write test for EC-2 (update returns updated prefs)

### Task 4: Write test file
**Type:** test
**Files:**
  - Create: `tests/test_notification_preferences.py`
**Pattern:** pytest + httpx async client
**Acceptance:** EC-1 (defaults), EC-2 (update), EC-3 (invalid channel) all pass

### Execution Order
1 -> 2 -> 3 -> 4 (migration first, domain layer, API layer, tests)

## Drift Analysis
- No notifications domain exists — creating new
- `src/api/main.py` has router registration pattern
- Migration numbered 005 — verified no conflict with existing migrations
- No circular dependency risk (notifications depends on users via FK only)
