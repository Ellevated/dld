# Reference Output (Coder)

## Created: src/api/health.py

```python
from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check():
    return {"status": "ok"}
```

## Modified: src/api/main.py

```python
from fastapi import FastAPI
from src.api.users import router as users_router
from src.api.health import router as health_router

app = FastAPI()
app.include_router(users_router)
app.include_router(health_router)
```

## files_changed
- src/api/health.py (created)
- src/api/main.py (modified)
