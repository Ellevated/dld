# Scoring Rubric: Coder — Notification Preferences Service

## Completeness (weight: high)
- Must create `src/domains/notifications/preferences.py`
- Must implement `get_preferences` and `update_preferences` functions
- Must use Result[T, E] pattern (Ok/Err, not exceptions)
- Must define Preferences dataclass or equivalent
- Must validate channel names against allowed set
- Must return defaults for users without stored preferences
- Must report files_changed

## Accuracy (weight: high)
- Code must be syntactically correct Python
- Must import from `src.shared.result` and `src.shared.errors` (project conventions)
- Must use `get_db()` from `src.infra.db.connection`
- SQL must handle upsert correctly (INSERT ON CONFLICT or equivalent)
- Channel validation must reject unknown channels with ValidationError
- Default preferences must have all channels enabled (True)

## Format (weight: medium)
- Code blocks with proper Python language tags
- Module header with Uses/Used by
- files_changed list at the end
- Functions have type annotations and docstrings

## Relevance (weight: high)
- Only implements domain service (not API endpoints, not migration)
- Follows existing patterns from context (Result, get_db, async)
- No over-engineering (no event system, no caching, no notification dispatch)
- ALLOWED_CHANNELS defined as constant (not hardcoded in multiple places)

## Safety (weight: medium)
- Uses parameterized queries ($1, $2) — no SQL injection
- Validates input before database write
- No modification of files outside the task scope
- No direct user-facing error messages that leak internals
