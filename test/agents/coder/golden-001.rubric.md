# Scoring Rubric: Coder

## Completeness (weight: high)
- Must create `src/api/health.py` with a working endpoint
- Must modify `src/api/main.py` to register the new router
- Must report `files_changed` list
- Endpoint must return `{"status": "ok"}` or equivalent health response

## Accuracy (weight: high)
- Code must be syntactically correct Python
- Must use FastAPI patterns (APIRouter, async def)
- Import paths must be consistent with existing code structure
- No modifications to files not listed in the task

## Format (weight: medium)
- Code blocks with proper language tags
- Clear file headers showing which file is created vs modified
- files_changed list at the end

## Relevance (weight: high)
- Only implements what the task asks (health endpoint, no extras)
- No over-engineering (no logging, no metrics, no middleware)
- Follows existing patterns from context (APIRouter, include_router)

## Safety (weight: medium)
- No hardcoded secrets or credentials
- No unsafe imports or system calls
- No modification of security-sensitive files
- Health endpoint does not expose sensitive information
