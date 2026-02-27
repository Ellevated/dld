# Task 1/2: Create health endpoint with basic response

**Type:** code
**Files:**
  - Create: `src/api/health.py`
  - Modify: `src/api/main.py`
**Pattern:** FastAPI router pattern
**Acceptance:** GET /health returns `{"status": "ok"}`

## Context
- FastAPI application
- Existing routers are registered in `src/api/main.py` via `app.include_router()`
- Pattern: `APIRouter(prefix="/path", tags=["tag"])`
- Result pattern: all domain functions return `Result[T, E]`
- Async everywhere: all IO uses `async def`

## Existing main.py structure (excerpt)
```python
from fastapi import FastAPI
from src.api.users import router as users_router

app = FastAPI()
app.include_router(users_router)
```
