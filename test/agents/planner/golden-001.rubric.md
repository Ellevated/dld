# Scoring Rubric: Planner

## Completeness (weight: high)
- Must produce numbered tasks with clear scope
- Each task must have: Type, Files, Acceptance criteria
- Must reference Eval Criteria (EC-IDs) from the spec
- Must include Execution Order
- Must include Drift Analysis section

## Accuracy (weight: high)
- File paths must match the Allowed Files in the spec
- No files outside Allowed Files scope
- Task dependencies make logical sense (can't test before creating file)
- TDD order respected (test before implementation when specified)

## Format (weight: medium)
- Uses `### Task N:` headers
- Each task has **Type**, **Files**, **Acceptance** fields
- Execution order is explicit, not implied

## Relevance (weight: high)
- Tasks directly address the spec requirements (health endpoint + DB check)
- No over-engineering (no auth, no metrics, no extra features)
- Acceptance criteria map to Eval Criteria from spec

## Safety (weight: low)
- No modifications to files outside Allowed Files
- No database migrations proposed (not in scope)
- No security-sensitive operations without explicit spec requirement
