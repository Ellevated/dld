# Domain Template

## Structure

```
domains/{name}/
├── __init__.py       # Public API (3-5 exports MAX)
├── README.md         # Domain context (50-150 lines)
├── models.py         # Pydantic models
├── service.py        # Business logic
├── repository.py     # DB access
└── tests/            # Collocated unit tests
    ├── test_service.py
    └── test_repository.py
```

---

## README.md (Domain Context)

```markdown
# {Name} Domain

## Purpose
{One sentence: what this domain does}

## Key Files
- `service.py` — business logic ({operation1}, {operation2})
- `models.py` — {Entity}, {EntityStatus}
- `repository.py` — CRUD operations with DB

## Dependencies
- `domains/auth` — for user verification
- `infra/db` — for persistence

## Typical Operations

```python
from domains.{name} import create_entity, get_entity

# Create
entity = await create_entity(data, user_id)

# Get
entity = await get_entity(entity_id)
```

## Entry points
- POST /api/{name} — create
- GET /api/{name}/{id} — get
- Telegram: /{name} command
```

---

## __init__.py

```python
"""Domain: {Name}

{One sentence description}
"""

from .models import Entity, EntityCreate, EntityStatus
from .service import create_entity, get_entity, update_entity

__all__ = [
    # Models
    "Entity",
    "EntityCreate",
    "EntityStatus",
    # Service
    "create_entity",
    "get_entity",
    "update_entity",
]
# Max 5 exports!
```

---

## models.py

```python
"""Domain models for {name}."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class EntityStatus(str, Enum):
    """Entity status."""
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"


class EntityBase(BaseModel):
    """Base entity fields."""
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class EntityCreate(EntityBase):
    """Create entity request."""
    pass


class Entity(EntityBase):
    """Entity with DB fields."""
    id: UUID
    status: EntityStatus = EntityStatus.DRAFT
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
```

---

## service.py

```python
"""Business logic for {name} domain."""

from uuid import UUID

from src.shared import Result, Ok, Err, DomainError
from .models import Entity, EntityCreate
from .repository import entity_repo


async def create_entity(data: EntityCreate, user_id: UUID) -> Result[Entity, DomainError]:
    """Create new entity.

    Args:
        data: Entity creation data
        user_id: Owner user ID

    Returns:
        Result with created entity or error
    """
    # Validation
    if not data.name.strip():
        return Err(DomainError("Name cannot be empty"))

    # Create
    entity = await entity_repo.create(data, user_id)
    return Ok(entity)
```
