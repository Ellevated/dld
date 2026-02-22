# Scoring Rubric: Planner — Notification Preferences Spec

## Completeness (weight: high)
- Must produce numbered tasks covering all 5 allowed files
- Each task must have: Type, Files, Acceptance criteria
- Must reference EC-IDs from the spec (EC-1 through EC-3)
- Must include Execution Order with layer-based reasoning (migration -> domain -> api -> test)
- Must include Drift Analysis
- Migration task must note "git-first only"

## Accuracy (weight: high)
- File paths must match Allowed Files exactly
- No files outside Allowed Files scope
- Domain service must use Result[T, E] pattern (project convention)
- Migration must be SQL, not ORM-generated
- PATCH semantics correct (partial update, not full replace)

## Format (weight: medium)
- Uses `### Task N:` headers
- Each task has **Type**, **Files**, **Acceptance** fields
- Execution order is explicit
- Drift Analysis is a separate section

## Relevance (weight: high)
- Tasks directly address preferences CRUD (get defaults, update, validate)
- No over-engineering (no notification dispatch, no scheduling, no templates)
- Acceptance criteria map to EC-1 through EC-3
- Correctly identifies this is a new domain (no existing notifications code)

## Safety (weight: medium)
- Migration marked as git-first only (never apply directly)
- No modifications to files outside Allowed Files
- Auth requirement mentioned for endpoints
- Channel validation prevents injection of unsupported channels
