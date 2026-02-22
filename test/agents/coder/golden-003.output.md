# Reference Output (Coder)

## Created: src/domains/notifications/preferences.py

```python
"""
Module: preferences
Role: Notification preference management for users
Uses: db/connection (get_db), shared/result, shared/errors
Used by: api/notifications
Glossary: ai/glossary/notifications.md
"""

from dataclasses import dataclass

from src.shared.result import Result, Ok, Err
from src.shared.errors import NotFoundError, ValidationError
from src.infra.db.connection import get_db

ALLOWED_CHANNELS = {"email", "push", "in_app"}
DEFAULTS = {ch: True for ch in ALLOWED_CHANNELS}


@dataclass
class Preferences:
    user_id: int
    email: bool
    push: bool
    in_app: bool


async def get_preferences(user_id: int) -> Result[Preferences, NotFoundError]:
    """Get notification preferences for user. Returns defaults if none set."""
    db = await get_db()
    row = await db.fetchone(
        "SELECT * FROM notification_preferences WHERE user_id = $1",
        user_id,
    )
    if not row:
        return Ok(Preferences(user_id=user_id, **DEFAULTS))
    return Ok(Preferences(**row))


async def update_preferences(
    user_id: int, changes: dict
) -> Result[Preferences, ValidationError]:
    """Update specific notification channels. Validates channel names."""
    invalid = set(changes.keys()) - ALLOWED_CHANNELS
    if invalid:
        return Err(ValidationError(f"Invalid channels: {', '.join(invalid)}"))

    db = await get_db()
    current = await get_preferences(user_id)
    prefs = current.unwrap()

    for channel, enabled in changes.items():
        setattr(prefs, channel, enabled)

    await db.execute(
        """INSERT INTO notification_preferences (user_id, email, push, in_app)
           VALUES ($1, $2, $3, $4)
           ON CONFLICT (user_id)
           DO UPDATE SET email = $2, push = $3, in_app = $4""",
        prefs.user_id, prefs.email, prefs.push, prefs.in_app,
    )
    return Ok(prefs)
```

## files_changed
- src/domains/notifications/preferences.py (created)
