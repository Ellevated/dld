# Scoring Rubric: Planner — Rate Limiting Spec

## Completeness (weight: high)
- Must produce numbered tasks covering all 4 allowed files
- Each task must have: Type, Files, Acceptance criteria
- Must reference EC-IDs from the spec (EC-1 through EC-4)
- Must include Execution Order with dependency reasoning
- Must include Drift Analysis checking existing codebase state

## Accuracy (weight: high)
- File paths must match Allowed Files (rate_limit.py, rate_store.py, main.py, test file)
- No files outside Allowed Files scope
- Redis sliding window is correct approach for rate limiting
- Middleware pattern must match FastAPI conventions
- 429 status code is correct for rate limiting (not 403 or 503)

## Format (weight: medium)
- Uses `### Task N:` headers
- Each task has **Type**, **Files**, **Acceptance** fields
- Execution order is explicit with reasoning
- Drift Analysis is a separate section

## Relevance (weight: high)
- Tasks directly address rate limiting requirements (per-user, anonymous, reset)
- No over-engineering (no distributed rate limiting, no token bucket unless needed)
- Acceptance criteria map to EC-1 through EC-4
- TDD order from spec respected in task sequencing

## Safety (weight: low)
- No modifications to files outside Allowed Files
- No database changes proposed
- Rate store uses Redis TTL (no manual cleanup needed)
