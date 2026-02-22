# Task 2/4: Create notification preferences service

**Type:** code
**Files:**
  - Create: `src/domains/notifications/preferences.py`
**Pattern:** Domain service with Result[T, E] pattern
**Acceptance:**
  - `get_preferences(user_id) -> Result[Preferences, NotFoundError]`
  - `update_preferences(user_id, changes) -> Result[Preferences, ValidationError]`
  - Default preferences: all channels enabled
  - Validate channel names against allowed set

## Context
- FastAPI application with PostgreSQL
- Domain layer uses Result[T, E] pattern (no exceptions at boundaries)
- Existing `src/shared/result.py` provides `Result`, `Ok`, `Err`
- Existing `src/shared/errors.py` provides `NotFoundError`, `ValidationError`
- Database access via `src/infra/db/connection.py` → `get_db()` returns async session
- Allowed channels: email, push, in_app

## Existing patterns (excerpt from another domain)
```python
from src.shared.result import Result, Ok, Err
from src.shared.errors import NotFoundError, ValidationError
from src.infra.db.connection import get_db

async def get_user(user_id: int) -> Result[User, NotFoundError]:
    db = await get_db()
    row = await db.fetchone("SELECT * FROM users WHERE id = $1", user_id)
    if not row:
        return Err(NotFoundError(f"User {user_id} not found"))
    return Ok(User(**row))
```
