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

## Altitude (weight: high)
- Implementation is anchored, not authored: path + insertion point (`file.py:120-135`) +
  signature + invariants. No pasted function bodies, no reproduced existing code
- Tests are stated as contract, not as files: test name + the assertion that makes it red,
  one line per EC-ID. No imports, no fixtures, no boilerplate
- Existing code referenced as `file:line`, never quoted in full
- Plan is shorter than the spec it plans — a longer plan means code was written twice
