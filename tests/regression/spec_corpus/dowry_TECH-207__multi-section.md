# TECH-207: TG Group Activity Module

**Status:** done
**Priority:** P1
**Effort:** 6-8h
**Created:** 2026-02-20
**Depends on:** ~~TECH-200 (ACTIVITY purpose)~~ DONE, TECH-202 (warmed accounts)
**Related:** FTR-128 (KB news monitoring — content source)
**Corrected:** 2026-03-02 — spec review identified 7 issues, all fixed below

---

## Problem

TG accounts used only for DM outreach get banned faster. Telegram expects "normal" account behavior:

1. **No group presence** — accounts that only send DMs look like bots
2. **No brand visibility** — we're not present in target communities
3. **No organic leads** — helpful comments in groups attract inbound DMs
4. **Warming gap** — after warming, accounts go straight to aggressive DM, no gradual transition

---

## Solution

Group Activity module that automatically performs human-like actions in configured groups:

1. **Our channels** — post content from KB, reply to subscribers
2. **Target groups** — helpful comments (NOT ads), reactions
3. **Background presence** — continuous low-level activity to maintain account health

### Architecture

```
GroupActivityService
    │
    ├── GroupTargetManager
    │   ├── Our channels (support accounts, content from KB)
    │   └── Target groups (expendable accounts, comments + reactions)
    │
    ├── ContentProvider
    │   ├── KB articles → post summaries
    │   ├── Comment templates → group replies
    │   └── Reaction picker → appropriate emoji
    │
    └── ActivityScheduler
        ├── Per-account schedule (vary times daily)
        ├── Rate limiting (not too much, not too little)
        └── Integration with warming phases
```

---

## Specification

### GroupActivityService

```python
# src/domains/agents/workers/outreach/activity/service.py

class GroupActivityService:
    """Automated group activity for TG account health and visibility.

    Performs human-like actions in configured groups:
    - Reactions in channels
    - Comments in discussion groups
    - Content posts in our channels (from KB)
    """

    def __init__(
        self,
        pool: TGAccountPool,
        config: GroupActivityConfig,
        content_provider: ActivityContentProvider | None = None,
    ) -> None: ...

    async def run(self) -> ActivityRunResult:
        """Execute activity cycle for all eligible accounts.

        Eligible: status=active, purpose in (outreach, activity)
        Skips: accounts at >80% daily_limit utilization
        """

    async def perform_activity(
        self,
        account: TGAccount,
        target: GroupTarget,
    ) -> ActivityResult:
        """Perform a single activity action for account in target group."""
```

### GroupActivityConfig

```python
# src/domains/agents/workers/outreach/activity/config.py

@dataclass
class GroupTarget:
    """A Telegram group/channel for activity."""
    username: str                   # e.g. "wb_sellers_chat"
    target_type: str                # "our_channel" | "target_group"
    allowed_actions: list[str]      # ["react", "comment", "post"]
    max_actions_per_day: int = 5
    comment_templates: list[str] | None = None  # Override default templates

@dataclass
class GroupActivityConfig:
    """Configuration for group activity."""

    # Groups and channels
    targets: list[GroupTarget] = field(default_factory=list)

    # Per-account limits
    max_reactions_per_day: int = 10
    max_comments_per_day: int = 3
    max_posts_per_day: int = 2       # Only for our channels

    # Timing
    min_delay_between_actions: int = 300     # 5 min
    max_delay_between_actions: int = 1800    # 30 min
    activity_window_start_hour: int = 9      # MSK
    activity_window_end_hour: int = 21       # MSK

    # Content
    reaction_emojis: list[str] = field(default_factory=lambda: [
        "\U0001f44d",  # thumbs up
        "\u2764\ufe0f",  # heart
        "\U0001f525",  # fire
        "\U0001f4af",  # 100
        "\U0001f440",  # eyes
    ])
```

### ActivityContentProvider

```python
# src/domains/agents/workers/outreach/activity/content.py

class ActivityContentProvider:
    """Provides content for group activity.

    Sources:
    - Comment templates (hardcoded + configurable)
    - KB articles (via search service)
    - News digests (from FTR-128 monitoring)
    """

    async def get_comment(
        self,
        group_context: str | None = None,
    ) -> str:
        """Get a comment appropriate for the group context.

        Uses templates with light variation to avoid repetition.
        """

    async def get_post_content(
        self,
        topic: str | None = None,
    ) -> str | None:
        """Get content for posting in our channels.

        Sources from KB if available, returns None if no content.
        """

    def get_reaction(self) -> str:
        """Get random appropriate reaction emoji."""
```

### GroupTarget Type Semantics

| `target_type` | Telethon Reply | Use Case |
|---------------|---------------|----------|
| `our_channel` | `comment_to=msg.id` | Channel with linked discussion (we own it) |
| `target_group` | `reply_to=msg.id` | Group chat (target community) |

The `is_channel` flag in `action_comment()` is derived from `target.target_type == "our_channel"`.

### Default Comment Templates

```python
COMMENT_TEMPLATES = {
    "general": [
        "Спасибо за информацию!",
        "Полезно, сохраню себе",
        "Интересный подход, надо попробовать",
        "А это для всех категорий работает или есть ограничения?",
        "Кто-нибудь уже пробовал? Какие результаты?",
        "Подскажите, а где можно подробнее почитать?",
        "+, тоже интересует",
        "Хороший совет, спасибо что поделились",
    ],
    "wb_specific": [
        "А на WB это тоже актуально?",
        "Какая категория лучше всего зашла?",
        "Интересная статистика по выкупам",
        "А с кэшбеком как сейчас ситуация?",
        "Спасибо, особенно за часть про рекламу",
    ],
    "question_response": [
        "Хороший вопрос, тоже хотел бы узнать",
        "У нас похожая ситуация была, {variation}",
        "Попробуйте через личный кабинет, там должно быть",
    ],
}
```

### Activity Actions

```python
async def action_react(
    client: TelegramClient,
    group: str,
    emoji: str,
    reacted_ids: set[int] | None = None,
) -> bool:
    """Set reaction on a recent message in group.

    1. Get last 20 messages
    2. Filter: skip service messages, skip already-reacted (dedup)
    3. Pick random text message (not our own)
    4. Mark chat as read (ReadHistoryRequest) — human pattern
    5. Set reaction
    """

async def action_comment(
    client: TelegramClient,
    group: str,
    text: str,
    is_channel: bool = False,
    commented_ids: set[int] | None = None,
) -> bool:
    """Post comment/reply in group or channel.

    1. Get last 10 messages
    2. Filter: skip media-only, stickers, service messages, skip already-commented (dedup)
    3. Prefer messages with questions or discussion topics (has '?' or len > 50)
    4. For groups (is_channel=False): use reply_to=msg.id
    5. For channels (is_channel=True): use comment_to=msg.id (linked discussion)
    """

async def action_post(
    client: TelegramClient,
    channel: str,
    text: str,
) -> bool:
    """Post content in our channel.

    Only for target_type='our_channel'.
    Content from KB or news monitoring.
    """
```

### DB Schema (Activity Log)

```sql
-- migrate:up
-- TECH-207: Group activity log

CREATE TABLE dowry.tg_group_activity_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      UUID NOT NULL REFERENCES dowry.tg_accounts(id),
    group_username   TEXT NOT NULL,
    action_type     TEXT NOT NULL,       -- 'react', 'comment', 'post'
    success         BOOLEAN NOT NULL,
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_tg_activity_log_account_date
    ON dowry.tg_group_activity_log(account_id, created_at);

-- migrate:down
DROP TABLE IF EXISTS dowry.tg_group_activity_log;
```

### Scheduler Integration

3 daily runs at different MSK times for natural activity spread:

```python
# src/api/worker.py — 3 daily runs

# Morning:  06:00 UTC = 09:00 MSK
# Afternoon: 11:00 UTC = 14:00 MSK (existing)
# Evening:  16:00 UTC = 19:00 MSK

async def run_group_activity() -> None:
    """Run group activity cycle. Called 3x/day."""
    from src.infra.telegram.activity.service import GroupActivityService

    config = load_activity_config()
    service = GroupActivityService(pool=TGAccountPool(), config=config)
    result = await service.run()
    logger.info(
        "Group activity: %d actions, %d success, %d failed",
        result.total_actions,
        result.successful,
        result.failed,
    )
```

---

## Impact Tree

### UP — who uses this?
- Worker scheduler — runs activity cycle
- Warming service (TECH-202) — shares channel list, can delegate phase 2-3 actions

### DOWN — what does this depend on?
- `src/infra/telegram/pool.py` — TGAccountPool.get_client()
- `src/infra/telegram/models.py` — TGAccountPurpose.ACTIVITY (TECH-200)
- `src/domains/kb/` — KB search for content (optional, graceful fallback)

### Checklist
- [x] src/domains/agents/workers/outreach/activity/ — new module
- [x] supabase/migrations/ — activity log table
- [x] src/api/worker.py — add cron job
- [x] tests/ — activity service tests

---

## Allowed Files

> **NOTE:** Superseded by "Updated Allowed Files" section below (drift correction moved module to `src/infra/telegram/activity/`). See Drift Log for rationale.

~~**Modify:**~~
~~1. `src/api/worker.py` — add activity cycle to scheduler~~

~~**Create:**~~
~~- `src/domains/agents/workers/outreach/activity/*`~~

**See "Updated Allowed Files" section below for current paths.**

---

## Environment

nodejs: false
docker: false
database: true

---

## Edge Cases

1. **Group is private / not found** — skip, log warning, don't crash
2. **Account already at 80% daily_limit** — skip activity, preserve capacity for outreach
3. **KB not available** — use comment templates only, no posts
4. **Reaction already set on message** — skip, try next message
5. **Account gets FloodWait during activity** — mark cooldown, stop activity for this account
6. **All messages in group are from us** — skip commenting (would look weird)
7. **Activity outside window (22:00-08:00 MSK)** — don't execute, defer to next window
8. **Account not a member of group** — auto-join before performing actions; if join fails, skip group
9. **Message is media-only / sticker / service** — skip for commenting, OK for reactions
10. **Same message reacted/commented twice** — dedup via in-memory `reacted_ids` / `commented_ids` sets per run
11. **Channel vs group distinction** — channels use `comment_to` (linked discussion), groups use `reply_to`
12. **Multiple runs per day hit same messages** — `created_at` offset by last run timestamp (future improvement)

---

## Definition of Done

### Functional
- [ ] Activity service processes active accounts (both `outreach` and `activity` purpose)
- [ ] Reactions set in configured channels with read-before-react pattern
- [ ] Comments posted in configured groups (from templates) with message filtering
- [ ] `reply_to` used for groups, `comment_to` used for channels
- [ ] Content posted in our channels (from KB, if available)
- [ ] Activity logged in dowry.tg_group_activity_log
- [ ] Respects activity window (09:00-21:00 MSK)
- [ ] Per-account daily limits respected
- [ ] 3 daily runs (09:00, 14:00, 19:00 MSK) for natural activity spread
- [ ] Auto-join groups before first activity if not member
- [ ] Dedup: same message not reacted/commented twice in one run

### Technical
- [ ] `./test fast` passes
- [ ] Migration applies cleanly
- [ ] Config-driven (channels, limits, templates)
- [ ] Individual failures don't crash batch
- [ ] Type hints 100%
- [ ] Message filtering: skip service messages, media-only, stickers for comments

---

## Drift Log

**Checked:** 2026-02-20 UTC
**Result:** light_drift

### Changes Detected
| File | Change Type | Action Taken |
|------|-------------|--------------|
| `src/domains/agents/workers/outreach/activity/` | architecture_mismatch | AUTO-FIX: relocated to `src/infra/telegram/activity/` |
| `src/infra/telegram/warming_actions.py` | overlap_detected | AUTO-FIX: activity reuses existing reaction/comment primitives |
| `supabase/migrations/` | deferred | AUTO-FIX: DB log table moved to follow-up, not MVP |
| `src/api/worker.py:710` | lines_shifted | AUTO-FIX: updated — file is 710 lines, new job goes after line 676 |

### References Updated
- Module path: `src/domains/agents/workers/outreach/activity/` -> `src/infra/telegram/activity/`
- Removed migration task from MVP (logging via Python logger sufficient)
- Worker integration point: after line 676 (tg_pool_health_check block)

### Architecture Decisions Made During Planning

**1. Module Location: `src/infra/telegram/activity/` (NOT `domains/agents/workers/outreach/activity/`)**

The spec proposed placing this under `domains/agents`, but this is infra-level functionality:
- It performs raw Telethon operations on TG accounts (same as warming)
- Import direction `shared -> infra -> domains -> api` means infra cannot import from domains
- The warming module lives at `src/infra/telegram/warming.py` -- activity is the same abstraction
- No Agent Protocol compliance needed (this is not an agent, it is an infrastructure service)
- Consistent with `warming.py`, `warming_actions.py`, `warming_config.py`, `health.py` in same package

**2. Reuse Telethon Primitives from warming_actions.py**

`warming_actions.py` already has:
- `execute_set_reactions()` -- get history, pick message, send ReactionEmoji (lines 86-161)
- `execute_post_comments()` -- get history, pick message, send_message with comment_to (lines 164-229)

Activity needs the same operations but with different config (custom groups, richer templates, custom emoji lists). Instead of duplicating 200+ lines of Telethon code, we extract shared primitives into `src/infra/telegram/tg_actions.py` that both warming_actions and activity_actions can call.

However, to keep this task scoped and avoid touching warming_actions.py (not in Allowed Files), activity_actions.py will have its own Telethon functions that follow the same pattern but are independent. The shared extraction can be a follow-up refactor.

**3. DB Migration Deferred**

The `tg_group_activity_log` table is nice-to-have for analytics. The warming service has no DB log table either -- it logs via Python logger. For MVP, activity results are logged via structured Python logging. DB table can be added as TECH-207b follow-up.

**4. Scheduler: 3 Daily Runs (09:00, 14:00, 19:00 MSK)**

~~The Scheduler only supports `add_daily_job()` (no 2-4 hour intervals). One daily run at 11:00 UTC.~~
**CORRECTED (2026-03-02):** The Scheduler supports multiple `add_daily_job()` calls with different names. Register 3 jobs: `tg_group_activity_morning` (06:00 UTC), `tg_group_activity_afternoon` (11:00 UTC), `tg_group_activity_evening` (16:00 UTC). This creates natural activity spread throughout the MSK day. Daily budget is split across 3 runs (service tracks per-account daily usage).

**5. Corrections from Spec Review (2026-03-02)**

Seven issues identified and fixed:
1. **Read-before-react** — `action_react()` now calls `ReadHistoryRequest` before setting reaction (human pattern)
2. **`reply_to` vs `comment_to`** — Groups use `reply_to=msg.id` (direct reply), channels use `comment_to=msg.id` (linked discussion). Was using `comment_to` everywhere.
3. **Message filtering** — Actions now skip `MessageService` (joins/leaves/pins), media-only messages, stickers. Comments prefer messages with questions (`?`) or longer text (`len > 50`).
4. **Dedup protection** — `reacted_ids` and `commented_ids` sets passed through action calls, preventing same message being interacted with twice in one run.
5. **Group membership check** — `ensure_group_joined()` called before first action on each target. If join fails, target is skipped.
6. **Multiple daily runs** — 3 scheduler jobs instead of 1 for natural activity spread.
7. **TECH-200 is DONE** — Updated dependency status. Both `outreach` and `activity` purpose accounts eligible.

---

## Updated Allowed Files

**Modify:**
1. `src/api/worker.py` -- update existing activity job (line ~709) to 3 daily runs

**Create:**
- `src/infra/telegram/activity/__init__.py`
- `src/infra/telegram/activity/service.py`
- `src/infra/telegram/activity/config.py`
- `src/infra/telegram/activity/actions.py`
- `tests/unit/infra/telegram/activity/__init__.py`
- `tests/unit/infra/telegram/activity/test_config.py`
- `tests/unit/infra/telegram/activity/test_service.py`

**Deferred (follow-up):**
- `src/infra/telegram/activity/content.py` -- KB integration for channel posts
- `supabase/migrations/YYYYMMDDHHMMSS_tg_group_activity_log.sql` -- DB logging
- Refactor warming_actions.py + activity_actions.py to share Telethon primitives

**FORBIDDEN:** All other files.

---

## Detailed Implementation Plan

> **Re-planned 2026-03-02** by planner agent. Files already exist from initial coding
> but are MISSING the 7 corrections from spec review. This plan describes the DELTA
> (modifications to existing code), not creation from scratch.

### Task 1: Fix actions.py -- add all 7 corrections

**Files:**
- Modify: `src/infra/telegram/activity/actions.py` (FULL rewrite -- 230 lines -> ~290 lines)
- Test: `tests/unit/infra/telegram/activity/test_config.py` (already exists, no changes needed)

**Context:**
The `actions.py` file exists but was coded before the spec review. It is missing:
1. `reacted_ids` dedup parameter on `action_react()`
2. `ReadHistoryRequest` before reaction (read-before-react human pattern)
3. `MessageService` filtering in `action_react()`
4. `is_channel` parameter on `action_comment()`
5. `reply_to` vs `comment_to` distinction in `action_comment()`
6. Message filtering (skip media-only, service msgs, prefer questions) in `action_comment()`
7. `commented_ids` dedup parameter on `action_comment()`
8. `ensure_group_joined()` function entirely missing

**Step 1: Write failing tests for action corrections**

```python
# tests/unit/infra/telegram/activity/__init__.py
```

```python
# tests/unit/infra/telegram/activity/test_config.py
"""
Module: tests.unit.infra.telegram.activity.test_config
Role: Unit tests for GroupActivityConfig, GroupTarget, and comment templates.
"""

from __future__ import annotations

import pytest

from src.infra.telegram.activity.config import (
    COMMENT_TEMPLATES,
    GroupActivityConfig,
    GroupTarget,
)


class TestGroupTarget:
    """Tests for GroupTarget dataclass."""

    def test_default_max_actions_per_day_is_five(self) -> None:
        target = GroupTarget(
            username="test_group",
            target_type="target_group",
            allowed_actions=["react", "comment"],
        )
        assert target.max_actions_per_day == 5

    def test_custom_values_are_stored(self) -> None:
        target = GroupTarget(
            username="our_channel",
            target_type="our_channel",
            allowed_actions=["react", "comment", "post"],
            max_actions_per_day=10,
            comment_templates=["Custom comment"],
        )
        assert target.username == "our_channel"
        assert target.target_type == "our_channel"
        assert "post" in target.allowed_actions
        assert target.max_actions_per_day == 10
        assert target.comment_templates == ["Custom comment"]

    def test_comment_templates_default_is_none(self) -> None:
        target = GroupTarget(
            username="group",
            target_type="target_group",
            allowed_actions=["react"],
        )
        assert target.comment_templates is None


class TestGroupActivityConfig:
    """Tests for GroupActivityConfig dataclass."""

    def test_default_limits(self) -> None:
        config = GroupActivityConfig()
        assert config.max_reactions_per_day == 10
        assert config.max_comments_per_day == 3
        assert config.max_posts_per_day == 2

    def test_default_timing(self) -> None:
        config = GroupActivityConfig()
        assert config.min_delay_between_actions == 300
        assert config.max_delay_between_actions == 1800
        assert config.activity_window_start_hour == 9
        assert config.activity_window_end_hour == 21

    def test_default_targets_list_is_empty(self) -> None:
        config = GroupActivityConfig()
        assert config.targets == []

    def test_default_reaction_emojis_not_empty(self) -> None:
        config = GroupActivityConfig()
        assert len(config.reaction_emojis) > 0

    def test_custom_targets_are_stored(self) -> None:
        target = GroupTarget(
            username="wb_chat",
            target_type="target_group",
            allowed_actions=["react"],
        )
        config = GroupActivityConfig(targets=[target])
        assert len(config.targets) == 1
        assert config.targets[0].username == "wb_chat"

    def test_is_within_activity_window_returns_true_for_midday(self) -> None:
        config = GroupActivityConfig(
            activity_window_start_hour=9,
            activity_window_end_hour=21,
        )
        assert config.is_within_activity_window(14) is True

    def test_is_within_activity_window_returns_false_for_night(self) -> None:
        config = GroupActivityConfig(
            activity_window_start_hour=9,
            activity_window_end_hour=21,
        )
        assert config.is_within_activity_window(3) is False

    def test_is_within_activity_window_boundary_start(self) -> None:
        config = GroupActivityConfig(
            activity_window_start_hour=9,
            activity_window_end_hour=21,
        )
        assert config.is_within_activity_window(9) is True

    def test_is_within_activity_window_boundary_end(self) -> None:
        config = GroupActivityConfig(
            activity_window_start_hour=9,
            activity_window_end_hour=21,
        )
        assert config.is_within_activity_window(21) is False

    def test_get_targets_by_type_filters_correctly(self) -> None:
        targets = [
            GroupTarget(username="our", target_type="our_channel", allowed_actions=["post"]),
            GroupTarget(username="target", target_type="target_group", allowed_actions=["react"]),
        ]
        config = GroupActivityConfig(targets=targets)
        our = config.get_targets_by_type("our_channel")
        assert len(our) == 1
        assert our[0].username == "our"

    def test_get_targets_by_type_returns_empty_for_unknown(self) -> None:
        config = GroupActivityConfig()
        assert config.get_targets_by_type("nonexistent") == []


class TestCommentTemplates:
    """Tests for COMMENT_TEMPLATES constant."""

    def test_general_templates_not_empty(self) -> None:
        assert len(COMMENT_TEMPLATES["general"]) > 0

    def test_wb_specific_templates_not_empty(self) -> None:
        assert len(COMMENT_TEMPLATES["wb_specific"]) > 0

    def test_all_templates_are_strings(self) -> None:
        for category, templates in COMMENT_TEMPLATES.items():
            for template in templates:
                assert isinstance(template, str), f"Non-string template in {category}"
```

**Step 2: Verify tests fail**

```bash
cd C:\Projects\Dowry\.worktrees\TECH-207
python -m pytest tests/unit/infra/telegram/activity/test_config.py -v
```

Expected:
```
FAILED - ModuleNotFoundError: No module named 'src.infra.telegram.activity'
```

**Step 3: Write implementation**

```python
# src/infra/telegram/activity/__init__.py
"""TG group activity module for account health and visibility."""
```

```python
# src/infra/telegram/activity/config.py
"""
Module: infra.telegram.activity.config
Role: Configuration dataclasses for TG group activity — targets, limits, templates.

Uses:
  - dataclasses: dataclass, field

Used by:
  - infra.telegram.activity.service: GroupActivityService
  - infra.telegram.activity.actions: action functions

Glossary: ai/integration/tg-account-pool.md
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GroupTarget:
    """A Telegram group or channel for automated activity.

    Attributes:
        username: Telegram group/channel username (without @).
        target_type: Either "our_channel" or "target_group".
        allowed_actions: List of allowed actions: "react", "comment", "post".
        max_actions_per_day: Maximum actions per account per day in this target.
        comment_templates: Override default templates for this target. None = use defaults.
    """

    username: str
    target_type: str  # "our_channel" | "target_group"
    allowed_actions: list[str]
    max_actions_per_day: int = 5
    comment_templates: list[str] | None = None


@dataclass
class GroupActivityConfig:
    """Configuration for the group activity service.

    Attributes:
        targets: List of group/channel targets for activity.
        max_reactions_per_day: Max reactions across all targets per account.
        max_comments_per_day: Max comments across all targets per account.
        max_posts_per_day: Max posts in our channels per account.
        min_delay_between_actions: Minimum seconds between actions.
        max_delay_between_actions: Maximum seconds between actions.
        activity_window_start_hour: Start of activity window (MSK hour, 0-23).
        activity_window_end_hour: End of activity window (MSK hour, 0-23).
        reaction_emojis: List of emoji strings for reactions.
    """

    targets: list[GroupTarget] = field(default_factory=list)

    # Per-account daily limits
    max_reactions_per_day: int = 10
    max_comments_per_day: int = 3
    max_posts_per_day: int = 2

    # Timing
    min_delay_between_actions: int = 300   # 5 min
    max_delay_between_actions: int = 1800  # 30 min
    activity_window_start_hour: int = 9    # MSK
    activity_window_end_hour: int = 21     # MSK

    # Content
    reaction_emojis: list[str] = field(
        default_factory=lambda: [
            "\U0001f44d",   # thumbs up
            "\u2764\ufe0f",  # heart
            "\U0001f525",   # fire
            "\U0001f4af",   # 100
            "\U0001f440",   # eyes
        ]
    )

    def is_within_activity_window(self, current_msk_hour: int) -> bool:
        """Check if the current MSK hour is within the activity window.

        Args:
            current_msk_hour: Current hour in Moscow timezone (0-23).

        Returns:
            True if within [start, end) window.
        """
        return self.activity_window_start_hour <= current_msk_hour < self.activity_window_end_hour

    def get_targets_by_type(self, target_type: str) -> list[GroupTarget]:
        """Filter targets by type.

        Args:
            target_type: "our_channel" or "target_group".

        Returns:
            List of matching GroupTarget objects.
        """
        return [t for t in self.targets if t.target_type == target_type]


COMMENT_TEMPLATES: dict[str, list[str]] = {
    "general": [
        "\u0421\u043f\u0430\u0441\u0438\u0431\u043e \u0437\u0430 \u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u044e!",
        "\u041f\u043e\u043b\u0435\u0437\u043d\u043e, \u0441\u043e\u0445\u0440\u0430\u043d\u044e \u0441\u0435\u0431\u0435",
        "\u0418\u043d\u0442\u0435\u0440\u0435\u0441\u043d\u044b\u0439 \u043f\u043e\u0434\u0445\u043e\u0434, \u043d\u0430\u0434\u043e \u043f\u043e\u043f\u0440\u043e\u0431\u043e\u0432\u0430\u0442\u044c",
        "\u0410 \u044d\u0442\u043e \u0434\u043b\u044f \u0432\u0441\u0435\u0445 \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u0439 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u0438\u043b\u0438 \u0435\u0441\u0442\u044c \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u044f?",
        "\u041a\u0442\u043e-\u043d\u0438\u0431\u0443\u0434\u044c \u0443\u0436\u0435 \u043f\u0440\u043e\u0431\u043e\u0432\u0430\u043b? \u041a\u0430\u043a\u0438\u0435 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u044b?",
        "\u041f\u043e\u0434\u0441\u043a\u0430\u0436\u0438\u0442\u0435, \u0430 \u0433\u0434\u0435 \u043c\u043e\u0436\u043d\u043e \u043f\u043e\u0434\u0440\u043e\u0431\u043d\u0435\u0435 \u043f\u043e\u0447\u0438\u0442\u0430\u0442\u044c?",
        "+, \u0442\u043e\u0436\u0435 \u0438\u043d\u0442\u0435\u0440\u0435\u0441\u0443\u0435\u0442",
        "\u0425\u043e\u0440\u043e\u0448\u0438\u0439 \u0441\u043e\u0432\u0435\u0442, \u0441\u043f\u0430\u0441\u0438\u0431\u043e \u0447\u0442\u043e \u043f\u043e\u0434\u0435\u043b\u0438\u043b\u0438\u0441\u044c",
    ],
    "wb_specific": [
        "\u0410 \u043d\u0430 WB \u044d\u0442\u043e \u0442\u043e\u0436\u0435 \u0430\u043a\u0442\u0443\u0430\u043b\u044c\u043d\u043e?",
        "\u041a\u0430\u043a\u0430\u044f \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f \u043b\u0443\u0447\u0448\u0435 \u0432\u0441\u0435\u0433\u043e \u0437\u0430\u0448\u043b\u0430?",
        "\u0418\u043d\u0442\u0435\u0440\u0435\u0441\u043d\u0430\u044f \u0441\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430 \u043f\u043e \u0432\u044b\u043a\u0443\u043f\u0430\u043c",
        "\u0410 \u0441 \u043a\u044d\u0448\u0431\u044d\u043a\u043e\u043c \u043a\u0430\u043a \u0441\u0435\u0439\u0447\u0430\u0441 \u0441\u0438\u0442\u0443\u0430\u0446\u0438\u044f?",
        "\u0421\u043f\u0430\u0441\u0438\u0431\u043e, \u043e\u0441\u043e\u0431\u0435\u043d\u043d\u043e \u0437\u0430 \u0447\u0430\u0441\u0442\u044c \u043f\u0440\u043e \u0440\u0435\u043a\u043b\u0430\u043c\u0443",
    ],
}


__all__ = [
    "COMMENT_TEMPLATES",
    "GroupActivityConfig",
    "GroupTarget",
]
```

```python
# src/infra/telegram/activity/actions.py
"""
Module: infra.telegram.activity.actions
Role: Telethon action executors for group activity (react, comment, post).

Uses:
  - telethon: errors, GetHistoryRequest, SendReactionRequest, ReactionEmoji
  - infra.telegram.activity.config: GroupTarget, COMMENT_TEMPLATES
  - infra.telegram.pool: TGAccountPool (injected for flood/ban)

Used by:
  - infra.telegram.activity.service: GroupActivityService._perform_account_activity

Glossary: ai/integration/tg-account-pool.md
"""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from src.infra.telegram.pool import TGAccountPool

logger = logging.getLogger(__name__)


class ActivityActionError(Exception):
    """Error during activity action execution."""

    pass


async def action_react(
    tg_client: Any,
    pool: "TGAccountPool",
    account_id: UUID,
    group_username: str,
    emoji: str,
    reacted_ids: set[int] | None = None,
) -> bool:
    """Set reaction on a recent message in group.

    Steps:
    1. Resolve group entity
    2. Get last 20 messages
    3. Filter: skip service messages, skip already-reacted (dedup via reacted_ids)
    4. Pick random message from filtered list
    5. Mark chat as read (ReadHistoryRequest) — human-like pattern
    6. Set reaction

    Args:
        tg_client: Connected Telethon TelegramClient.
        pool: TGAccountPool for marking flood/ban events.
        account_id: Account UUID performing the action.
        group_username: Telegram group/channel username.
        emoji: Emoji string to react with.
        reacted_ids: Set of message IDs already reacted to (dedup). Updated in-place.

    Returns:
        True if reaction was set successfully.

    Raises:
        ActivityActionError: On FloodWait or ban.
    """
    from telethon import errors as tg_errors  # type: ignore[import]
    from telethon.tl.functions.messages import (  # type: ignore[import]
        GetHistoryRequest,
        ReadHistoryRequest,
        SendReactionRequest,
    )
    from telethon.tl.types import (  # type: ignore[import]
        MessageService,
        ReactionEmoji,
    )

    try:
        entity = await tg_client.get_entity(group_username)
        history = await tg_client(
            GetHistoryRequest(
                peer=entity,
                limit=20,
                offset_date=None,
                offset_id=0,
                max_id=0,
                min_id=0,
                add_offset=0,
                hash=0,
            )
        )

        if not history.messages:
            logger.debug("No messages in %s, skipping reaction", group_username)
            return False

        # Filter: skip service messages and already-reacted
        candidates = [
            msg for msg in history.messages
            if not isinstance(msg, MessageService)
            and (reacted_ids is None or msg.id not in reacted_ids)
        ]
        if not candidates:
            logger.debug("No eligible messages in %s after filtering", group_username)
            return False

        message = random.choice(candidates)

        # Read-before-react: mark messages as read (human pattern)
        try:
            await tg_client(ReadHistoryRequest(peer=entity, max_id=message.id))
        except Exception:
            pass  # Non-critical, proceed with reaction

        await tg_client(
            SendReactionRequest(
                peer=entity,
                msg_id=message.id,
                reaction=[ReactionEmoji(emoticon=emoji)],
            )
        )

        # Track for dedup
        if reacted_ids is not None:
            reacted_ids.add(message.id)

        logger.info("Reaction %s set in %s on msg %d", emoji, group_username, message.id)
        return True

    except tg_errors.FloodWaitError as flood_error:
        await pool.mark_flood_wait(account_id, flood_error.seconds)
        raise ActivityActionError(f"FloodWait {flood_error.seconds}s") from flood_error
    except tg_errors.UserBannedInChannelError:
        await pool.mark_banned(account_id)
        raise ActivityActionError("Account banned in channel") from None
    except Exception as action_error:
        logger.warning("Failed to react in %s: %s", group_username, action_error)
        return False


async def action_comment(
    tg_client: Any,
    pool: "TGAccountPool",
    account_id: UUID,
    group_username: str,
    comment_text: str,
    is_channel: bool = False,
    commented_ids: set[int] | None = None,
) -> bool:
    """Post comment/reply to a recent message in group or channel.

    Groups use reply_to (direct reply in chat).
    Channels use comment_to (post in linked discussion).

    Steps:
    1. Resolve group entity
    2. Get last 10 messages
    3. Filter: skip media-only, stickers, service messages, already-commented (dedup)
    4. Prefer messages with text content, especially questions ('?') or longer posts
    5. Reply using reply_to (groups) or comment_to (channels)

    Args:
        tg_client: Connected Telethon TelegramClient.
        pool: TGAccountPool for marking flood/ban events.
        account_id: Account UUID performing the action.
        group_username: Telegram group/channel username.
        comment_text: Text to post as comment.
        is_channel: True for channels (use comment_to), False for groups (use reply_to).
        commented_ids: Set of message IDs already commented on (dedup). Updated in-place.

    Returns:
        True if comment was posted successfully.

    Raises:
        ActivityActionError: On FloodWait or ban.
    """
    from telethon import errors as tg_errors  # type: ignore[import]
    from telethon.tl.functions.messages import GetHistoryRequest  # type: ignore[import]
    from telethon.tl.types import MessageService  # type: ignore[import]

    try:
        entity = await tg_client.get_entity(group_username)
        history = await tg_client(
            GetHistoryRequest(
                peer=entity,
                limit=10,
                offset_date=None,
                offset_id=0,
                max_id=0,
                min_id=0,
                add_offset=0,
                hash=0,
            )
        )

        if not history.messages:
            logger.debug("No messages in %s, skipping comment", group_username)
            return False

        # Filter: skip service messages, media-only (no text), already-commented
        candidates = [
            msg for msg in history.messages
            if not isinstance(msg, MessageService)
            and getattr(msg, "message", None)  # has text content
            and (commented_ids is None or msg.id not in commented_ids)
        ]
        if not candidates:
            logger.debug("No commentable messages in %s after filtering", group_username)
            return False

        # Prefer messages with questions or discussion (longer text)
        discussion_msgs = [
            msg for msg in candidates
            if "?" in (msg.message or "") or len(msg.message or "") > 50
        ]
        message = random.choice(discussion_msgs if discussion_msgs else candidates)

        # Groups: reply_to (direct reply in chat)
        # Channels: comment_to (linked discussion)
        if is_channel:
            await tg_client.send_message(
                entity=entity,
                message=comment_text,
                comment_to=message.id,
            )
        else:
            await tg_client.send_message(
                entity=entity,
                message=comment_text,
                reply_to=message.id,
            )

        # Track for dedup
        if commented_ids is not None:
            commented_ids.add(message.id)

        logger.info("Comment posted in %s on msg %d (channel=%s)", group_username, message.id, is_channel)
        return True

    except tg_errors.FloodWaitError as flood_error:
        await pool.mark_flood_wait(account_id, flood_error.seconds)
        raise ActivityActionError(f"FloodWait {flood_error.seconds}s") from flood_error
    except tg_errors.UserBannedInChannelError:
        await pool.mark_banned(account_id)
        raise ActivityActionError("Account banned in channel") from None
    except Exception as action_error:
        logger.warning("Failed to comment in %s: %s", group_username, action_error)
        return False


async def action_post(
    tg_client: Any,
    pool: "TGAccountPool",
    account_id: UUID,
    channel_username: str,
    text: str,
) -> bool:
    """Post content in our channel.

    Only for target_type='our_channel'. Posts as a new message (not reply).

    Args:
        tg_client: Connected Telethon TelegramClient.
        pool: TGAccountPool for marking flood/ban events.
        account_id: Account UUID performing the action.
        channel_username: Our channel username.
        text: Text content to post.

    Returns:
        True if post was sent successfully.

    Raises:
        ActivityActionError: On FloodWait or ban.
    """
    from telethon import errors as tg_errors  # type: ignore[import]

    try:
        entity = await tg_client.get_entity(channel_username)
        await tg_client.send_message(entity=entity, message=text)
        logger.info("Posted in channel %s", channel_username)
        return True

    except tg_errors.FloodWaitError as flood_error:
        await pool.mark_flood_wait(account_id, flood_error.seconds)
        raise ActivityActionError(f"FloodWait {flood_error.seconds}s") from flood_error
    except tg_errors.UserBannedInChannelError:
        await pool.mark_banned(account_id)
        raise ActivityActionError("Account banned in channel") from None
    except Exception as action_error:
        logger.warning("Failed to post in %s: %s", channel_username, action_error)
        return False


async def ensure_group_joined(
    tg_client: Any,
    pool: "TGAccountPool",
    account_id: UUID,
    group_username: str,
) -> bool:
    """Ensure account is a member of the group. Join if not.

    Args:
        tg_client: Connected Telethon TelegramClient.
        pool: TGAccountPool for marking flood/ban events.
        account_id: Account UUID.
        group_username: Telegram group/channel username.

    Returns:
        True if account is a member (already or just joined).
    """
    from telethon import errors as tg_errors  # type: ignore[import]
    from telethon.tl.functions.channels import JoinChannelRequest  # type: ignore[import]

    try:
        entity = await tg_client.get_entity(group_username)
        # Check if already a member by trying to get participant info
        # If get_entity succeeds for a group, we can usually interact
        # But to be safe, try joining — if already member, it's a no-op
        await tg_client(JoinChannelRequest(entity))
        return True
    except tg_errors.FloodWaitError as flood_error:
        await pool.mark_flood_wait(account_id, flood_error.seconds)
        raise ActivityActionError(f"FloodWait {flood_error.seconds}s on join") from flood_error
    except tg_errors.UserBannedInChannelError:
        await pool.mark_banned(account_id)
        raise ActivityActionError("Account banned, cannot join") from None
    except Exception as join_error:
        logger.warning("Failed to join %s: %s", group_username, join_error)
        return False


__all__ = [
    "ActivityActionError",
    "action_comment",
    "action_post",
    "action_react",
    "ensure_group_joined",
]
```

**Step 4: Verify tests pass**

```bash
cd C:\Projects\Dowry\.worktrees\TECH-207
python -m pytest tests/unit/infra/telegram/activity/test_config.py -v
```

Expected:
```
PASSED test_default_max_actions_per_day_is_five
PASSED test_custom_values_are_stored
PASSED test_comment_templates_default_is_none
PASSED test_default_limits
PASSED test_default_timing
PASSED test_default_targets_list_is_empty
PASSED test_default_reaction_emojis_not_empty
PASSED test_custom_targets_are_stored
PASSED test_is_within_activity_window_returns_true_for_midday
PASSED test_is_within_activity_window_returns_false_for_night
PASSED test_is_within_activity_window_boundary_start
PASSED test_is_within_activity_window_boundary_end
PASSED test_get_targets_by_type_filters_correctly
PASSED test_get_targets_by_type_returns_empty_for_unknown
PASSED test_general_templates_not_empty
PASSED test_wb_specific_templates_not_empty
PASSED test_all_templates_are_strings
```

**Acceptance Criteria:**
- [ ] All 17 config tests pass
- [ ] `GroupActivityConfig` has `is_within_activity_window()` and `get_targets_by_type()` methods
- [ ] `COMMENT_TEMPLATES` dict has "general" and "wb_specific" categories
- [ ] `actions.py` has `action_react`, `action_comment`, `action_post`, `ensure_group_joined` functions
- [ ] `action_react` sends `ReadHistoryRequest` before reaction (read-before-react pattern)
- [ ] `action_react` filters `MessageService` and uses `reacted_ids` dedup set
- [ ] `action_comment` uses `reply_to` for groups, `comment_to` for channels
- [ ] `action_comment` filters media-only/service messages, prefers questions/discussions
- [ ] `action_comment` uses `commented_ids` dedup set
- [ ] All functions have type hints, docstrings, and proper error handling
- [ ] `ActivityActionError` raised on FloodWait/ban (propagated to service)

---

### Task 2: GroupActivityService (orchestrator + scheduler integration)

**Files:**
- Create: `src/infra/telegram/activity/service.py`
- Create: `tests/unit/infra/telegram/activity/test_service.py`
- Modify: `src/api/worker.py:676-677` (add activity cycle job)

**Context:**
The service orchestrates activity across all eligible accounts and configured targets.
It fetches active/activity-purpose accounts from DB, checks daily limits and activity window,
then performs randomized actions per account. Integrated into worker.py as a daily cron job.

**Step 1: Write failing tests for service**

```python
# tests/unit/infra/telegram/activity/test_service.py
"""
Module: tests.unit.infra.telegram.activity.test_service
Role: Unit tests for GroupActivityService — cycle orchestration,
      account filtering, error isolation, and activity window checks.

Uses:
  - src.infra.telegram.activity.service: GroupActivityService, ActivityRunResult
  - src.infra.telegram.activity.config: GroupActivityConfig, GroupTarget
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.infra.telegram.activity.config import GroupActivityConfig, GroupTarget
from src.infra.telegram.activity.service import (
    ActivityRunResult,
    GroupActivityService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_pool() -> MagicMock:
    """Create mock TGAccountPool."""
    pool = MagicMock()
    pool.mark_flood_wait = AsyncMock()
    pool.mark_banned = AsyncMock()
    return pool


@pytest.fixture
def sample_config() -> GroupActivityConfig:
    """Create config with one target group."""
    return GroupActivityConfig(
        targets=[
            GroupTarget(
                username="test_group",
                target_type="target_group",
                allowed_actions=["react", "comment"],
                max_actions_per_day=3,
            ),
        ],
        max_reactions_per_day=5,
        max_comments_per_day=2,
        activity_window_start_hour=0,   # Always in window for tests
        activity_window_end_hour=24,
    )


@pytest.fixture
def activity_service(
    mock_pool: MagicMock,
    sample_config: GroupActivityConfig,
) -> GroupActivityService:
    """Create GroupActivityService with mocked pool."""
    return GroupActivityService(pool=mock_pool, config=sample_config)


def _make_active_account_dict(
    name: str = "activity-test-1",
    purpose: str = "activity",
    used_today: int = 0,
    daily_limit: int = 50,
) -> dict[str, object]:
    """Create a raw active account dict mimicking a Supabase row."""
    now = datetime.now(timezone.utc)
    return {
        "id": str(uuid4()),
        "name": name,
        "purpose": purpose,
        "risk_level": "expendable",
        "session_data": "encrypted_session",
        "phone_encrypted": "encrypted_phone",
        "status": "active",
        "daily_limit": daily_limit,
        "used_today": used_today,
        "ban_count": 0,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


def _build_mock_db_client(data: list[dict[str, object]]) -> MagicMock:
    """Build mock Supabase client returning data for select queries."""
    client = MagicMock()
    # Chain: table().select().in_().eq().or_().order().execute()
    chain = client.table.return_value.select.return_value
    chain.in_.return_value.eq.return_value.or_.return_value.order.return_value.execute = (
        AsyncMock(return_value=MagicMock(data=data))
    )
    return client


# ---------------------------------------------------------------------------
# ActivityRunResult dataclass
# ---------------------------------------------------------------------------


class TestActivityRunResult:
    """Tests for ActivityRunResult dataclass defaults."""

    def test_default_values_are_zero(self) -> None:
        result = ActivityRunResult()
        assert result.accounts_processed == 0
        assert result.total_actions == 0
        assert result.successful == 0
        assert result.failed == 0
        assert result.skipped_window == 0
        assert result.skipped_limit == 0


# ---------------------------------------------------------------------------
# run() — empty scenarios
# ---------------------------------------------------------------------------


class TestRunEmpty:
    """Tests for run() when no accounts or targets exist."""

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_accounts(
        self,
        activity_service: GroupActivityService,
    ) -> None:
        mock_db = _build_mock_db_client([])

        async def _get() -> MagicMock:
            return mock_db

        with patch("src.infra.telegram.activity.service.get_dowry_client", _get):
            result = await activity_service.run()

        assert result.accounts_processed == 0
        assert result.total_actions == 0

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_targets_configured(
        self,
        mock_pool: MagicMock,
    ) -> None:
        empty_config = GroupActivityConfig(
            targets=[],
            activity_window_start_hour=0,
            activity_window_end_hour=24,
        )
        service = GroupActivityService(pool=mock_pool, config=empty_config)
        mock_db = _build_mock_db_client([_make_active_account_dict()])

        async def _get() -> MagicMock:
            return mock_db

        with patch("src.infra.telegram.activity.service.get_dowry_client", _get):
            result = await service.run()

        assert result.accounts_processed == 0
        assert result.total_actions == 0


# ---------------------------------------------------------------------------
# run() — activity window check
# ---------------------------------------------------------------------------


class TestRunActivityWindow:
    """Tests for activity window enforcement."""

    @pytest.mark.asyncio
    async def test_skips_when_outside_activity_window(
        self,
        mock_pool: MagicMock,
    ) -> None:
        config = GroupActivityConfig(
            targets=[
                GroupTarget(
                    username="test",
                    target_type="target_group",
                    allowed_actions=["react"],
                ),
            ],
            activity_window_start_hour=9,
            activity_window_end_hour=10,  # Very narrow window
        )
        service = GroupActivityService(pool=mock_pool, config=config)

        # Force current MSK hour to 3 AM (outside window)
        with patch(
            "src.infra.telegram.activity.service.get_current_msk_hour",
            return_value=3,
        ):
            mock_db = _build_mock_db_client([_make_active_account_dict()])

            async def _get() -> MagicMock:
                return mock_db

            with patch("src.infra.telegram.activity.service.get_dowry_client", _get):
                result = await service.run()

        assert result.skipped_window == 1


# ---------------------------------------------------------------------------
# run() — daily limit skip
# ---------------------------------------------------------------------------


class TestRunDailyLimit:
    """Tests for daily limit enforcement."""

    @pytest.mark.asyncio
    async def test_skips_account_at_80_percent_utilization(
        self,
        activity_service: GroupActivityService,
    ) -> None:
        account = _make_active_account_dict(
            used_today=42,
            daily_limit=50,  # 84% utilization
        )
        mock_db = _build_mock_db_client([account])

        async def _get() -> MagicMock:
            return mock_db

        with patch(
            "src.infra.telegram.activity.service.get_current_msk_hour",
            return_value=14,
        ):
            with patch("src.infra.telegram.activity.service.get_dowry_client", _get):
                result = await activity_service.run()

        assert result.skipped_limit == 1
        assert result.total_actions == 0


# ---------------------------------------------------------------------------
# run() — error isolation
# ---------------------------------------------------------------------------


class TestRunErrorIsolation:
    """Tests for error isolation between accounts."""

    @pytest.mark.asyncio
    async def test_db_fetch_error_returns_empty_result(
        self,
        activity_service: GroupActivityService,
    ) -> None:
        mock_db = MagicMock()
        chain = mock_db.table.return_value.select.return_value
        chain.in_.return_value.eq.return_value.or_.return_value.order.return_value.execute = (
            AsyncMock(side_effect=Exception("DB down"))
        )

        async def _get() -> MagicMock:
            return mock_db

        with patch(
            "src.infra.telegram.activity.service.get_current_msk_hour",
            return_value=14,
        ):
            with patch("src.infra.telegram.activity.service.get_dowry_client", _get):
                result = await activity_service.run()

        assert result.accounts_processed == 0
```

**Step 2: Verify tests fail**

```bash
cd C:\Projects\Dowry\.worktrees\TECH-207
python -m pytest tests/unit/infra/telegram/activity/test_service.py -v
```

Expected:
```
FAILED - ModuleNotFoundError: No module named 'src.infra.telegram.activity.service'
```

**Step 3: Write implementation**

```python
# src/infra/telegram/activity/service.py
"""
Module: infra.telegram.activity.service
Role: Orchestrates automated group activity for TG accounts.
      Performs human-like reactions, comments, and posts in configured groups
      to maintain account health and visibility.

Uses:
  - infra.db: get_dowry_client
  - infra.telegram.models: TGAccountPurpose, TGAccountStatus, TGRiskLevel
  - infra.telegram.activity.config: GroupActivityConfig, GroupTarget, COMMENT_TEMPLATES
  - infra.telegram.activity.actions: action_react, action_comment, action_post,
      ActivityActionError
  - infra.telegram.pool: TGAccountPool (injected)

Used by:
  - api.worker: run_group_activity_job (daily cron)

Glossary: ai/integration/tg-account-pool.md
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID

from src.infra.db import get_dowry_client
from src.infra.telegram.activity.actions import (
    ActivityActionError,
    action_comment,
    action_post,
    action_react,
    ensure_group_joined,
)
from src.infra.telegram.activity.config import (
    COMMENT_TEMPLATES,
    GroupActivityConfig,
    GroupTarget,
)
from src.infra.telegram.models import TGAccountPurpose, TGAccountStatus

if TYPE_CHECKING:
    from src.infra.telegram.pool import TGAccountPool

logger = logging.getLogger(__name__)

# Utilization threshold: skip accounts above this percentage
_UTILIZATION_THRESHOLD = 0.80


def get_current_msk_hour() -> int:
    """Get current hour in Moscow timezone (UTC+3).

    Returns:
        Current hour (0-23) in MSK.
    """
    utc_now = datetime.now(timezone.utc)
    msk_hour = (utc_now.hour + 3) % 24
    return msk_hour


@dataclass
class ActivityRunResult:
    """Result of a group activity run cycle.

    Attributes:
        accounts_processed: Number of accounts that performed actions.
        total_actions: Total action attempts.
        successful: Successful actions.
        failed: Failed actions.
        skipped_window: Accounts skipped due to activity window.
        skipped_limit: Accounts skipped due to daily limit.
    """

    accounts_processed: int = 0
    total_actions: int = 0
    successful: int = 0
    failed: int = 0
    skipped_window: int = 0
    skipped_limit: int = 0


class GroupActivityService:
    """Automated group activity for TG account health and visibility.

    Performs human-like actions in configured groups:
    - Reactions in channels and groups
    - Comments in discussion groups (from templates)
    - Content posts in our channels

    Usage:
        config = GroupActivityConfig(targets=[...])
        service = GroupActivityService(pool=pool, config=config)
        result = await service.run()
    """

    def __init__(
        self,
        pool: "TGAccountPool",
        config: GroupActivityConfig,
    ) -> None:
        """Initialize group activity service.

        Args:
            pool: TGAccountPool for getting TG clients and status updates.
            config: Activity configuration with targets and limits.
        """
        self._pool = pool
        self._config = config

    async def run(self) -> ActivityRunResult:
        """Execute activity cycle for all eligible accounts.

        Eligible: status=active, purpose in (outreach, activity)
        Skips: accounts at >80% daily_limit utilization
        Skips: if outside activity window (MSK hours)

        Returns:
            ActivityRunResult with cycle statistics.
        """
        result = ActivityRunResult()

        if not self._config.targets:
            logger.info("No activity targets configured, skipping")
            return result

        accounts = await self._fetch_eligible_accounts()
        if not accounts:
            logger.info("No eligible accounts for group activity")
            return result

        current_msk_hour = get_current_msk_hour()

        for account_data in accounts:
            account_name = account_data.get("name", "unknown")

            # Check activity window
            if not self._config.is_within_activity_window(current_msk_hour):
                result.skipped_window += 1
                logger.debug(
                    "Account %s: outside activity window (MSK hour=%d)",
                    account_name,
                    current_msk_hour,
                )
                continue

            # Check daily limit utilization
            used_today = account_data.get("used_today", 0)
            daily_limit = account_data.get("daily_limit", 50)
            if daily_limit > 0 and (used_today / daily_limit) >= _UTILIZATION_THRESHOLD:
                result.skipped_limit += 1
                logger.debug(
                    "Account %s: at %.0f%% utilization, skipping",
                    account_name,
                    (used_today / daily_limit) * 100,
                )
                continue

            # Perform activity for this account
            account_result = await self._perform_account_activity(account_data)
            result.accounts_processed += 1
            result.total_actions += account_result["total"]
            result.successful += account_result["success"]
            result.failed += account_result["failed"]

        logger.info(
            "Group activity cycle: %d accounts, %d actions (%d ok, %d fail), "
            "%d skipped_window, %d skipped_limit",
            result.accounts_processed,
            result.total_actions,
            result.successful,
            result.failed,
            result.skipped_window,
            result.skipped_limit,
        )
        return result

    async def _fetch_eligible_accounts(self) -> list[dict[str, Any]]:
        """Fetch active accounts eligible for activity.

        Eligible: status=active, purpose in (outreach, activity),
        not in cooldown.

        Returns:
            List of raw account dicts from Supabase.
        """
        try:
            client = await get_dowry_client()
            now = datetime.now(timezone.utc).isoformat()

            result = await (
                client.table("tg_accounts")
                .select("*")
                .in_(
                    "purpose",
                    [
                        TGAccountPurpose.OUTREACH.value,
                        TGAccountPurpose.ACTIVITY.value,
                    ],
                )
                .eq("status", TGAccountStatus.ACTIVE.value)
                .or_(f"cooldown_until.is.null,cooldown_until.lt.{now}")
                .order("last_used_at", desc=False, nullsfirst=True)
                .execute()
            )
            return result.data or []
        except Exception as fetch_error:
            logger.error("Failed to fetch eligible accounts: %s", fetch_error)
            return []

    async def _perform_account_activity(
        self,
        account_data: dict[str, Any],
    ) -> dict[str, int]:
        """Perform activity actions for a single account across targets.

        Catches all exceptions per-action to prevent one failure from
        stopping the account's remaining actions.

        Args:
            account_data: Raw account dict from Supabase.

        Returns:
            Dict with "total", "success", "failed" counts.
        """
        from src.infra.telegram.models import TGAccountPurpose, TGRiskLevel

        account_id = UUID(account_data["id"])
        account_name = account_data.get("name", str(account_id))
        counts = {"total": 0, "success": 0, "failed": 0}

        reactions_done = 0
        comments_done = 0
        posts_done = 0

        # Dedup sets: track which messages we've already interacted with
        reacted_ids: set[int] = set()
        commented_ids: set[int] = set()

        try:
            async with self._pool.get_client(
                purpose=TGAccountPurpose.ACTIVITY,
                max_risk_level=TGRiskLevel.EXPENDABLE,
            ) as (tg_client, _tg_account):
                # Shuffle targets for natural-looking order
                targets = list(self._config.targets)
                random.shuffle(targets)

                for target in targets:
                    # Ensure account is a member of the group before acting
                    is_member = await ensure_group_joined(
                        tg_client, self._pool, account_id, target.username,
                    )
                    if not is_member:
                        logger.debug("Skipping %s: could not join", target.username)
                        continue

                    is_channel = target.target_type == "our_channel"
                    actions_for_target = list(target.allowed_actions)
                    random.shuffle(actions_for_target)

                    for action_type in actions_for_target:
                        if action_type == "react" and reactions_done < self._config.max_reactions_per_day:
                            counts["total"] += 1
                            emoji = random.choice(self._config.reaction_emojis)
                            success = await action_react(
                                tg_client, self._pool, account_id,
                                target.username, emoji,
                                reacted_ids=reacted_ids,
                            )
                            if success:
                                counts["success"] += 1
                                reactions_done += 1
                            else:
                                counts["failed"] += 1

                        elif action_type == "comment" and comments_done < self._config.max_comments_per_day:
                            counts["total"] += 1
                            templates = target.comment_templates or COMMENT_TEMPLATES.get("general", [])
                            if templates:
                                comment_text = random.choice(templates)
                                success = await action_comment(
                                    tg_client, self._pool, account_id,
                                    target.username, comment_text,
                                    is_channel=is_channel,
                                    commented_ids=commented_ids,
                                )
                                if success:
                                    counts["success"] += 1
                                    comments_done += 1
                                else:
                                    counts["failed"] += 1

                        elif (
                            action_type == "post"
                            and target.target_type == "our_channel"
                            and posts_done < self._config.max_posts_per_day
                        ):
                            # Posts require content provider (deferred to follow-up)
                            logger.debug(
                                "Post action for %s skipped (content provider not yet implemented)",
                                target.username,
                            )

                        # Delay between actions
                        delay = random.randint(
                            self._config.min_delay_between_actions,
                            self._config.max_delay_between_actions,
                        )
                        await asyncio.sleep(delay)

        except ActivityActionError as action_err:
            # FloodWait or ban — stop all activity for this account
            logger.warning(
                "Activity stopped for %s: %s",
                account_name,
                action_err,
            )
        except Exception as client_error:
            logger.error(
                "Activity failed for %s: %s",
                account_name,
                client_error,
            )
            counts["failed"] += 1

        logger.info(
            "Account %s: %d reactions, %d comments, %d posts",
            account_name,
            reactions_done,
            comments_done,
            posts_done,
        )
        return counts


__all__ = [
    "ActivityRunResult",
    "GroupActivityService",
    "get_current_msk_hour",
]
```

**Step 4: Add scheduler job to worker.py**

In `src/api/worker.py`, after the TG pool health check block (after line 676), add:

```python
    # TG group activity cycle (TECH-207)
    async def run_group_activity_job() -> None:
        """Run TG group activity cycle."""
        try:
            from src.infra.telegram.activity.config import (
                GroupActivityConfig,
                GroupTarget,
            )
            from src.infra.telegram.activity.service import GroupActivityService
            from src.infra.telegram.pool import TGAccountPool

            config = GroupActivityConfig(
                targets=[
                    # Configure target groups here
                    # GroupTarget(
                    #     username="wb_sellers_chat",
                    #     target_type="target_group",
                    #     allowed_actions=["react", "comment"],
                    # ),
                ],
            )
            pool = TGAccountPool()
            service = GroupActivityService(pool=pool, config=config)
            result = await service.run()
            logger.info(
                "Group activity: %d accounts, %d actions (%d ok, %d fail)",
                result.accounts_processed,
                result.total_actions,
                result.successful,
                result.failed,
            )
        except Exception as exc:
            logger.error("TG group activity cycle failed: %s", exc)

    # 3 daily runs for natural activity spread
    for job_name, run_hour, msk_label in [
        ("tg_group_activity_morning", 6, "09:00 MSK"),
        ("tg_group_activity_afternoon", 11, "14:00 MSK"),
        ("tg_group_activity_evening", 16, "19:00 MSK"),
    ]:
        digest_scheduler.add_daily_job(
            name=job_name,
            run_at=dt_time(run_hour, 0),
            func=run_group_activity_job,
        )
        logger.info("TG group activity scheduled: %02d:00 UTC (%s)", run_hour, msk_label)
```

**Step 5: Verify all tests pass**

```bash
cd C:\Projects\Dowry\.worktrees\TECH-207
python -m pytest tests/unit/infra/telegram/activity/ -v
```

Expected:
```
PASSED tests/unit/infra/telegram/activity/test_config.py::TestGroupTarget::test_default_max_actions_per_day_is_five
PASSED tests/unit/infra/telegram/activity/test_config.py::TestGroupTarget::test_custom_values_are_stored
... (all 17 config tests)
PASSED tests/unit/infra/telegram/activity/test_service.py::TestActivityRunResult::test_default_values_are_zero
PASSED tests/unit/infra/telegram/activity/test_service.py::TestRunEmpty::test_returns_zero_when_no_accounts
PASSED tests/unit/infra/telegram/activity/test_service.py::TestRunEmpty::test_returns_zero_when_no_targets_configured
PASSED tests/unit/infra/telegram/activity/test_service.py::TestRunActivityWindow::test_skips_when_outside_activity_window
PASSED tests/unit/infra/telegram/activity/test_service.py::TestRunDailyLimit::test_skips_account_at_80_percent_utilization
PASSED tests/unit/infra/telegram/activity/test_service.py::TestRunErrorIsolation::test_db_fetch_error_returns_empty_result
```

**Acceptance Criteria:**
- [ ] `GroupActivityService.run()` fetches eligible accounts and performs actions
- [ ] Activity window check skips accounts outside 09:00-21:00 MSK
- [ ] 80% utilization threshold skips accounts to preserve outreach capacity
- [ ] Error isolation: one account failure does not crash the cycle
- [ ] Worker.py has 3 daily jobs (06:00, 11:00, 16:00 UTC)
- [ ] `ensure_group_joined()` called before actions on each target
- [ ] Dedup sets (`reacted_ids`, `commented_ids`) prevent duplicate interactions per run
- [ ] `is_channel` flag correctly routes `reply_to` vs `comment_to`
- [ ] All tests pass including existing baseline tests
- [ ] `./test fast` passes

---

### Task 3: DB Migration for Activity Log

**Files:**
- Create: `supabase/migrations/20260220300000_tg_group_activity_log.sql`

**Context:**
Activity log table for tracking group actions per account. Enables analytics on
which groups generate the most engagement, which accounts are most active, and
failure rate tracking. This is the persistence layer for the activity module.

**Step 1: Write migration file**

```sql
-- migrate:up
-- Migration: TG group activity log table
-- Feature: TECH-207
--
-- Tracks all group activity actions (reactions, comments, posts) per account.
-- Used for analytics, rate limiting verification, and debugging.

CREATE TABLE dowry.tg_group_activity_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      UUID NOT NULL REFERENCES dowry.tg_accounts(id),
    group_username  TEXT NOT NULL,
    action_type     TEXT NOT NULL CHECK (action_type IN ('react', 'comment', 'post')),
    success         BOOLEAN NOT NULL,
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_tg_activity_log_account_date
    ON dowry.tg_group_activity_log(account_id, created_at);

CREATE INDEX idx_tg_activity_log_group
    ON dowry.tg_group_activity_log(group_username, created_at);

-- migrate:down
DROP INDEX IF EXISTS dowry.idx_tg_activity_log_group;
DROP INDEX IF EXISTS dowry.idx_tg_activity_log_account_date;
DROP TABLE IF EXISTS dowry.tg_group_activity_log;
```

**Step 2: Verify migration format**

```bash
cd C:\Projects\Dowry\.worktrees\TECH-207
grep -c "migrate:up" supabase/migrations/20260220300000_tg_group_activity_log.sql
grep -c "migrate:down" supabase/migrations/20260220300000_tg_group_activity_log.sql
grep -c "dowry\." supabase/migrations/20260220300000_tg_group_activity_log.sql
```

Expected:
```
1
1
5   (all CREATE/DROP statements use dowry. prefix)
```

**Step 3: Validate no public schema leaks**

```bash
# Verify every CREATE statement has dowry. prefix
grep "CREATE" supabase/migrations/20260220300000_tg_group_activity_log.sql | grep -v "dowry\."
```

Expected: empty output (no lines without dowry. prefix)

**Acceptance Criteria:**
- [ ] Migration has `-- migrate:up` and `-- migrate:down` markers (dbmate format)
- [ ] All tables and indexes use `dowry.` schema prefix
- [ ] `account_id` references `dowry.tg_accounts(id)`
- [ ] `action_type` has CHECK constraint for valid values
- [ ] Two indexes: by account+date and by group+date
- [ ] Down migration drops in reverse order (indexes first, then table)

---

### Execution Order

Task 1 (config + actions) -> Task 2 (service + worker.py) -> Task 3 (migration)

### Dependencies

- Task 2 depends on Task 1 (imports config.py and actions.py)
- Task 3 is independent but ordered last (migration is additive, no code depends on it yet)
- Task 1 and Task 3 could technically run in parallel

### Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Telethon import errors in unit tests | Actions use lazy imports inside functions (same pattern as warming_actions.py) |
| asyncio.sleep delays make tests slow | Tests only cover service orchestration (mock pool.get_client), not actions themselves |
| Worker.py gets too large (already 710 LOC) | New code is only ~30 lines (job definition + 3 scheduler calls) — acceptable |
| Activity targets not configured on first deploy | Config defaults to empty targets list — service safely exits with 0 actions |
| Overlap with warming_actions.py | Documented as follow-up refactor — both work independently for now |
| JoinChannelRequest triggers FloodWait | `ensure_group_joined` handles FloodWait → raises ActivityActionError → stops account |
| `ReadHistoryRequest` fails | Non-critical, wrapped in try/except pass — reaction proceeds anyway |
| Channel has no linked discussion | `comment_to` will fail silently → caught by except block → returns False |
| 3 daily runs exceed daily budget | Service checks `used_today / daily_limit` before each run — self-limiting |
