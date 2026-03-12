# Feature: [FTR-146] Multi-Project Orchestrator Phase 1

**Status:** done | **Priority:** P0 | **Date:** 2026-03-10

## Why

Founder manages 2-5 DLD projects on one VPS. Without orchestration: manual SSH, manual Spark,
manual Autopilot per project. Goal: send idea from Telegram → full cycle runs unattended
(Spark → Autopilot → QA → notification). Mobile-first control via Telegram forum topics.

## Context

- Architecture decided: Alternative B — Pueue + Telegram Bot + SQLite + systemd
- Decision: `ai/architect/orchestrator/decision.md`
- Full architecture: `ai/architect/orchestrator/architectures.md` (Alternative B, lines 287-742)
- Original spec: `ai/architect/multi-project-orchestrator.md`
- Existing scripts in git history (commit `51e7788`) — NOT restored, building fresh from patterns
- Research: `ai/.spark/20260310-FTR-146/research-*.md` (4 files)

---

## Scope

**In scope:**
- SQLite WAL schema for runtime state (projects, slots, events)
- Telegram bot with forum topic routing (PTB v21.9+, Python 3.12)
- Pueue groups (claude-runner, codex-runner) with per-group parallelism
- `run-agent.sh` → `claude-runner.sh` / `codex-runner.sh` provider abstraction
- `orchestrator.sh` main loop: git pull → inbox scan → backlog scan → QA dispatch
- `inbox-processor.sh` with keyword-based skill routing (spark/architect/council/bughunt)
- Auto-approve with spark summary in Telegram + configurable timeout per project
- QA dispatch via `/qa` skill (not old qa-tester.md)
- `pueue-callback.sh` for slot release + Telegram notification on task completion
- `setup-vps.sh` one-command bootstrap with systemd units
- `/status`, `/run`, `/pause`, `/resume` bot commands
- Spark self-escalation fallback (writes back to inbox with new route if needed)

**Out of scope:**
- `/addproject` command (manual `projects.json` editing — Phase 3 per architecture)
- Docker containers for projects
- Voice inbox via whisper.cpp (Phase 3)
- Web dashboard
- Multi-VPS federation
- Task-level LLM routing (project-level only in v1)

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?

```bash
grep -rn "autopilot-loop\|inbox-processor\|orchestrator\|notify" . --include="*.sh" --include="*.py"
```

| File | Line | Usage |
|------|------|-------|
| `scripts/autopilot-loop.sh` | 15 | hardcodes `BACKLOG_FILE="ai/backlog.md"` — needs PROJECT_DIR |
| `.claude/hooks/pre-edit.mjs` | 84 | reads `CLAUDE_PROJECT_DIR` env — must set per project |

### Step 2: DOWN — dependencies

| Dependency | Notes |
|------------|-------|
| `claude` CLI | `claude -p --output-format json --max-turns 30` |
| `codex` CLI | `codex exec "task" --sandbox workspace-write --json` |
| `pueue` / `pueued` | v4.0.4+ for sync command execution |
| `sqlite3` | CLI for bash, stdlib for Python |
| `python-telegram-bot` | v21.9+ for forum topic support |
| `jq` | JSON parsing in bash scripts |
| `git` | pull in each project dir |
| `systemd` | process management |

### Step 3: BY TERM — grep

| File | Line | Context |
|------|------|---------|
| `scripts/autopilot-loop.sh` | 15 | `BACKLOG_FILE="ai/backlog.md"` hardcoded relative path |
| `.claude/hooks/pre-edit.mjs` | 84 | `CLAUDE_PROJECT_DIR` env var |

### Step 4: CHECKLIST

- [x] `scripts/autopilot-loop.sh` — needs PROJECT_DIR param
- [ ] `tests/` — no tests for VPS scripts (will create `tests/vps/`)
- [x] `ai/architect/orchestrator/` — architecture docs (read-only reference)

### Verification

- [x] All found files added to Allowed Files
- [x] `scripts/vps/` does not exist on disk — no collision

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `scripts/autopilot-loop.sh` — add PROJECT_DIR env var support

**New files allowed:**

1. `scripts/vps/telegram-bot.py` — Telegram bot with forum topic routing
2. `scripts/vps/run-agent.sh` — provider abstraction dispatcher
3. `scripts/vps/claude-runner.sh` — Claude Code CLI wrapper
4. `scripts/vps/codex-runner.sh` — ChatGPT Codex CLI wrapper
5. `scripts/vps/pueue-callback.sh` — post-task: slot release + notification
6. `scripts/vps/inbox-processor.sh` — inbox → skill routing (spark/architect/council)
7. `scripts/vps/qa-loop.sh` — dispatch /qa skill after autopilot completion
8. `scripts/vps/orchestrator.sh` — main daemon loop
9. `scripts/vps/setup-vps.sh` — one-command VPS bootstrap
10. `scripts/vps/notify.py` — Telegram notification helper (Python, for topic routing)
11. `scripts/vps/db.py` — SQLite WAL helpers (Python module)
12. `scripts/vps/schema.sql` — SQLite schema DDL
13. `scripts/vps/projects.json.example` — example project registry
14. `scripts/vps/.env.example` — environment config template
15. `scripts/vps/requirements.txt` — Python dependencies
16. `scripts/vps/db_exec.sh` — bash SQLite wrapper (prepends PRAGMAs)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: true (SQLite)

---

## Blueprint Reference

**Domain:** Application service (orchestrator), Inbox context, Pipeline context
**Cross-cutting:** Process isolation (systemd MemoryMax), provider abstraction
**Data model:** project_state, compute_slots, task_log (SQLite)

---

## Approaches

### Approach 1: Restore + Refactor

**Source:** Codebase scout — 6 files in git commit `51e7788`
**Summary:** Restore existing scripts, refactor from single-project to multi-project
**Pros:** ~1000 LOC battle-tested code
**Cons:** Refactoring ≈ rewriting (flock→Pueue, JSON→SQLite, Groq→whisper.cpp). Legacy single-project assumptions everywhere. Devil: "refactor friction multiplies estimates 2-3x"

### Approach 2: Clean Build from Patterns

**Source:** Pattern scout (6 patterns), External scout (PTB, Pueue, SQLite WAL research)
**Summary:** Build fresh using research patterns. Cherry-pick only proven snippets (auth, inbox format). Validate hardest unknown (Pueue+Claude) on Day 1 before UI.
**Pros:** No legacy debt, patterns give copy-paste code, architecture applied directly
**Cons:** ~200 LOC auth/inbox needs rewriting (patterns available)

### Approach 3: No-Topics MVP

**Source:** Devil Alternative 3
**Summary:** Same as Approach 2 but without forum topics. Explicit project arg in commands.
**Pros:** Simpler, faster
**Cons:** UX degradation, migration cost later, deviates from architecture

### Selected: 2

**Rationale:** Clean build eliminates refactoring overhead. All 6 research patterns provide ready code. Day 1 validates Pueue+Claude (hardest unknown) before investing in Telegram UI. Devil's 5 traps addressed in pre-flight checklist. Approach 3 rejected because user wants full scope in one phase.

---

## Design

### User Flow

**Flow A: Telegram Idea → Full Cycle**

1. Founder sends text message in project's Telegram topic
2. Bot receives message, routes by `message_thread_id` → project
3. Bot saves to `{project_path}/ai/inbox/{timestamp}-text.md` with metadata
4. Bot runs keyword routing on message text → determines skill (spark/architect/council)
5. Bot writes `**Route:** {skill}` in inbox file metadata
6. Bot sends spark summary to topic: "Spec ready: FTR-XXX. Summary: ..."
7. Bot starts auto-approve countdown (per-project timeout from projects.json)
8. If no cancel within timeout → bot submits to Pueue: `run-agent.sh` with autopilot
9. Pueue runs task → Claude/Codex executes → pueue-callback.sh fires
10. Callback releases SQLite slot + notifies Telegram topic: "Done/Failed"
11. Orchestrator triggers QA: `claude -p "/qa FTR-XXX"` → result in topic
12. QA PASS → done. QA FAIL → bugs written to `ai/inbox/` → cycle repeats

**Flow B: Local Spark → VDS Autopilot**

1. Founder runs `/spark` locally → spec created → `git push develop`
2. Orchestrator on VDS: `git pull --ff-only` every 5 min (or `/run` trigger)
3. Finds new `queued` spec in `ai/backlog.md`
4. Submits to Pueue → autopilot → QA → notification in Telegram topic

**Flow C: Architect Route**

1. Founder sends "спроектируй систему нотификаций" in topic
2. Keyword routing matches "спроектируй" → `route: architect`
3. `inbox-processor.sh` dispatches: `claude -p "/architect $idea"`
4. Architect creates specs → Spark refines → Autopilot executes → QA checks
5. Full chain notification in Telegram topic at each stage

**Flow D: Bot Commands**

- `/status` → query SQLite + Pueue JSON → per-project state table
- `/status project-name` → detailed status for one project
- `/run project-name` → trigger immediate orchestrator cycle
- `/run project-name "fix login bug"` → write to inbox + trigger
- `/pause project-name` → `pueue pause --group project-name`
- `/resume project-name` → `pueue start --group project-name`

### Architecture

```
Telegram Supergroup (Forum Mode)
├── General Topic: alerts, heartbeat
├── Topic "saas-app" (topic_id=5)
├── Topic "dld" (topic_id=7)
└── Topic "side-proj" (topic_id=9)
        │
        ▼
┌─────────────────────┐
│  telegram-bot.py    │  PTB v21.9+, polling mode
│  - route by topic   │  message_thread_id → project
│  - /status /run     │  SQLite for state queries
│  - auto-approve     │  JobQueue countdown + Cancel btn
│  - keyword routing  │  detect skill from Russian text
└────────┬────────────┘
         │ writes to ai/inbox/
         ▼
┌─────────────────────┐
│  orchestrator.sh    │  systemd service, main daemon
│  - git pull loop    │  every 5 min per project
│  - inbox scan       │  → inbox-processor.sh
│  - backlog scan     │  → pueue add (autopilot)
│  - QA dispatch      │  → qa-loop.sh after autopilot
└────────┬────────────┘
         │ submits tasks
         ▼
┌─────────────────────┐
│  Pueue daemon       │  Groups: claude-runner(2), codex-runner(1)
│  - run-agent.sh     │  dispatches to provider runners
│  - pueue-callback   │  on completion: SQLite + notify
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│  SQLite WAL         │  orchestrator.db
│  - project_state    │  phase, current_task, topic_id
│  - compute_slots    │  provider, pid, acquired_at
│  - task_log         │  history for /status
└─────────────────────┘
```

### Database Changes

**New file: `scripts/vps/schema.sql`**

```sql
-- orchestrator.db schema
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS project_state (
    project_id   TEXT PRIMARY KEY,
    path         TEXT NOT NULL,
    topic_id     INTEGER,
    provider     TEXT NOT NULL DEFAULT 'claude',
    phase        TEXT NOT NULL DEFAULT 'idle',
    current_task TEXT,
    auto_approve_timeout INTEGER NOT NULL DEFAULT 30,
    updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS compute_slots (
    slot_number  INTEGER PRIMARY KEY,
    provider     TEXT NOT NULL,
    project_id   TEXT REFERENCES project_state(project_id),
    pid          INTEGER,
    acquired_at  TEXT
);

CREATE TABLE IF NOT EXISTS task_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   TEXT NOT NULL REFERENCES project_state(project_id),
    task_label   TEXT NOT NULL,
    skill        TEXT NOT NULL DEFAULT 'autopilot',
    status       TEXT NOT NULL,
    pueue_id     INTEGER,
    started_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    finished_at  TEXT,
    exit_code    INTEGER,
    output_summary TEXT
);

-- Seed slots: 2 for claude, 1 for codex
INSERT OR IGNORE INTO compute_slots (slot_number, provider) VALUES (1, 'claude');
INSERT OR IGNORE INTO compute_slots (slot_number, provider) VALUES (2, 'claude');
INSERT OR IGNORE INTO compute_slots (slot_number, provider) VALUES (3, 'codex');
```

### Keyword Routing

```python
ROUTE_PATTERNS = {
    "architect": [
        "архитектура", "спроектируй", "система", "домены",
        "как устроить", "интеграция", "design system",
        "bounded context", "data flow", "инфраструктура",
        "схема данных", "миграция", "рефакторинг архитектуры"
    ],
    "council": [
        "консилиум", "сравни подходы", "что лучше",
        "trade-off", "выбери между", "стоит ли",
        "плюсы и минусы", "совет директоров"
    ],
    "spark_bug": [
        "баг", "ошибка", "не работает", "сломалось",
        "падает", "crash", "fix", "broken",
        "регрессия", "regression"
    ],
    "bughunt": [
        "баг хант", "охота на баги", "глубокий анализ багов",
        "много багов", "всё сломалось", "системные проблемы",
        "deep analysis", "bug hunt", "командный аудит багов"
    ],
    # default → spark (feature mode)
}

def detect_route(text: str) -> str:
    text_lower = text.lower()
    for route, keywords in ROUTE_PATTERNS.items():
        if any(kw in text_lower for kw in keywords):
            return route
    return "spark"
```

### Spark Self-Escalation Fallback

If Spark in headless mode determines a task needs architect/council:
1. Spark writes to `{project}/ai/inbox/{timestamp}-escalation.md`:
   ```markdown
   # Idea: {timestamp}
   **Source:** spark-escalation
   **Route:** architect
   **Original:** FTR-XXX
   ---
   {original idea text + spark's analysis of why architect is needed}
   ```
2. Spark sets its own spec status to `blocked` with reason "Needs architect review"
3. Next orchestrator cycle picks up the escalation file and dispatches to architect

---

## UI Event Completeness (Telegram Buttons)

| Producer | callback_data | Consumer (handler) | Handler File |
|----------|---------------|--------------------|-------------|
| Auto-approve message | `cancel:{project_id}:{task_id}` | `handle_cancel()` | `telegram-bot.py` ✓ |
| Auto-approve message | `approve:{project_id}:{task_id}` | `handle_approve()` | `telegram-bot.py` ✓ |

---

## Drift Log

**Checked:** 2026-03-10 UTC
**Result:** light_drift

### Changes Detected
| File | Change Type | Action Taken |
|------|-------------|--------------|
| `scripts/autopilot-loop.sh` | exists, unchanged (166 LOC) | No action needed |
| `scripts/vps/` | directory does not exist yet | Confirmed: all files are NEW creations, no collision |

### References Updated
- Task 3: Pueue callback variable `{{name}}` is NOT a valid Pueue template variable. Correct variable is `{{ label }}`. Updated in Detailed Implementation Plan.
- Task 4: PTB requirement pinned to `python-telegram-bot>=21.9,<22.0` (v22.0 has breaking changes to `message_thread_id` handling per PTB issue #4205). Updated in Detailed Implementation Plan.
- Task 9: `.env.example` missing `PUEUE_PATH` variable needed by `pueue-callback.sh`. Added in Detailed Implementation Plan.

### Solution Verification
- **Pueue callback**: Confirmed via GitHub issue #236 and wiki. Template vars: `{{ id }}`, `{{ command }}`, `{{ path }}`, `{{ result }}`, `{{ start }}`, `{{ end }}`, `{{ group }}`, `{{ label }}`, `{{ output }}`. Configured in `~/.config/pueue/pueue.yml` under `daemon.callback`.
- **PTB forum topics**: Confirmed `message_thread_id` works in all send methods since PTB v20.0+. Bug: `message_thread_id=1` (General topic) returns `BadRequest`. Fix: pass `None` instead. Spec already accounts for this (DA-4).
- **Pueue v4.0.4**: Confirmed latest stable. Breaking state format from v3.x. Groups API unchanged.
- **SQLite WAL**: Python 3.12 `sqlite3` module supports `autocommit` parameter. Two-phase init pattern confirmed.

---

## Detailed Implementation Plan

### Research Sources

- [CCBot subprocess pattern](https://github.com/RichardAtCT/claude-code-telegram) — `claude -p --output-format json --resume $session_id`
- [Pueue groups + callback](https://github.com/Nukesor/pueue/wiki/Groups) — per-group parallelism, `pueue status --json`
- [Pueue callback bug #236](https://github.com/Nukesor/pueue/issues/236) — confirmed template vars: `{{ id }}`, `{{ label }}`, `{{ group }}`, `{{ result }}`, `{{ command }}`, `{{ path }}`, `{{ output }}`
- [PTB Forum Topics API](https://docs.python-telegram-bot.org/en/stable/telegram.forumtopic.html) — `create_forum_topic`, `message_thread_id` routing
- [PTB issue #4739](https://github.com/python-telegram-bot/python-telegram-bot/issues/4739) — `message_thread_id=1` bug confirmed (General topic). Fix: pass `None`.
- [SQLite WAL concurrent access](https://sqlite.org/forum/forumpost/04ed1d235b) — `BEGIN IMMEDIATE` for slot acquisition
- [PTB JobQueue timer](https://docs.python-telegram-bot.org/en/v22.1/examples.timerbot.html) — auto-approve countdown pattern
- [systemd MemoryMax](https://oneuptime.com/blog/post/2026-03-02-setup-systemd-resource-control-memorymax-ubuntu/view) — cgroup resource limits
- [Python 3.12 WAL init](https://www.technetexperts.com/python-sqlite-wal-autocommit-false/) — two-phase connection pattern

### Task 1: SQLite Schema + Python DB Module

**Files:**
- Create: `scripts/vps/schema.sql`
- Create: `scripts/vps/db.py`
- Create: `scripts/vps/db_exec.sh`

**Context:**
Foundation layer. All other components depend on SQLite for state. schema.sql defines 3 tables (project_state, compute_slots, task_log). db.py provides Python helpers for the Telegram bot. db_exec.sh provides bash helpers for shell scripts.

**Step 1: Create schema.sql**

```sql
-- scripts/vps/schema.sql
-- Orchestrator runtime state (SQLite WAL mode)
-- Usage: sqlite3 orchestrator.db < schema.sql

PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS project_state (
    project_id   TEXT PRIMARY KEY,
    path         TEXT NOT NULL,
    topic_id     INTEGER,
    provider     TEXT NOT NULL DEFAULT 'claude',
    phase        TEXT NOT NULL DEFAULT 'idle',
    current_task TEXT,
    auto_approve_timeout INTEGER NOT NULL DEFAULT 30,
    enabled      INTEGER NOT NULL DEFAULT 1,
    updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS compute_slots (
    slot_number  INTEGER PRIMARY KEY,
    provider     TEXT NOT NULL,
    project_id   TEXT REFERENCES project_state(project_id),
    pid          INTEGER,
    pueue_id     INTEGER,
    acquired_at  TEXT
);

CREATE TABLE IF NOT EXISTS task_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   TEXT NOT NULL REFERENCES project_state(project_id),
    task_label   TEXT NOT NULL,
    skill        TEXT NOT NULL DEFAULT 'autopilot',
    status       TEXT NOT NULL DEFAULT 'queued',
    pueue_id     INTEGER,
    started_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    finished_at  TEXT,
    exit_code    INTEGER,
    output_summary TEXT
);

-- Seed slots: 2 for claude, 1 for codex
INSERT OR IGNORE INTO compute_slots (slot_number, provider) VALUES (1, 'claude');
INSERT OR IGNORE INTO compute_slots (slot_number, provider) VALUES (2, 'claude');
INSERT OR IGNORE INTO compute_slots (slot_number, provider) VALUES (3, 'codex');
```

**Step 2: Create db.py**

```python
#!/usr/bin/env python3
"""
Module: db
Role: SQLite WAL helpers for orchestrator state management.
Uses: sqlite3 (stdlib)
Used by: telegram-bot.py, notify.py
"""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).parent / "orchestrator.db"))


@contextmanager
def get_db():
    """Context manager for SQLite connection with WAL mode.

    Python 3.12 two-phase init:
    1. autocommit=True to set PRAGMAs
    2. Then autocommit=False for transactional work
    """
    conn = sqlite3.connect(DB_PATH, autocommit=True)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.autocommit = False
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def try_acquire_slot(project_id: str, provider: str, pueue_id: int) -> Optional[int]:
    """Acquire a compute slot for a project. Returns slot_number or None.

    Uses BEGIN IMMEDIATE to prevent race conditions between
    orchestrator and callback scripts.
    """
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT slot_number FROM compute_slots "
            "WHERE provider = ? AND project_id IS NULL "
            "ORDER BY slot_number LIMIT 1",
            (provider,),
        ).fetchone()
        if row is None:
            return None
        slot = row["slot_number"]
        conn.execute(
            "UPDATE compute_slots SET project_id = ?, pueue_id = ?, "
            "acquired_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
            "WHERE slot_number = ?",
            (project_id, pueue_id, slot),
        )
        return slot


def release_slot(pueue_id: int) -> Optional[str]:
    """Release a compute slot by pueue task id. Returns project_id or None."""
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT slot_number, project_id FROM compute_slots WHERE pueue_id = ?",
            (pueue_id,),
        ).fetchone()
        if row is None:
            return None
        project_id = row["project_id"]
        conn.execute(
            "UPDATE compute_slots SET project_id = NULL, pid = NULL, "
            "pueue_id = NULL, acquired_at = NULL WHERE pueue_id = ?",
            (pueue_id,),
        )
        return project_id


def get_project_state(project_id: str) -> Optional[dict]:
    """Get project state as dict. Returns None if not found."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM project_state WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return dict(row) if row else None


def get_project_by_topic(topic_id: int) -> Optional[dict]:
    """Look up project by Telegram topic_id. Returns None if not found."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM project_state WHERE topic_id = ?",
            (topic_id,),
        ).fetchone()
        return dict(row) if row else None


def get_all_projects() -> list[dict]:
    """Get all enabled projects."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM project_state WHERE enabled = 1 ORDER BY project_id"
        ).fetchall()
        return [dict(r) for r in rows]


def update_project_phase(project_id: str, phase: str, current_task: str = None) -> None:
    """Update project phase and optional current_task."""
    with get_db() as conn:
        conn.execute(
            "UPDATE project_state SET phase = ?, current_task = ?, "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
            "WHERE project_id = ?",
            (phase, current_task, project_id),
        )


def log_task(
    project_id: str,
    task_label: str,
    skill: str,
    status: str,
    pueue_id: int = None,
) -> int:
    """Create a task_log entry. Returns the row id."""
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, task_label, skill, status, pueue_id),
        )
        return cursor.lastrowid


def finish_task(pueue_id: int, status: str, exit_code: int, summary: str = None) -> None:
    """Mark a task as finished in task_log."""
    with get_db() as conn:
        conn.execute(
            "UPDATE task_log SET status = ?, exit_code = ?, output_summary = ?, "
            "finished_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
            "WHERE pueue_id = ? AND finished_at IS NULL",
            (status, exit_code, summary, pueue_id),
        )


def get_available_slots(provider: str) -> int:
    """Count available slots for a provider."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM compute_slots "
            "WHERE provider = ? AND project_id IS NULL",
            (provider,),
        ).fetchone()
        return row["cnt"]


def seed_projects_from_json(projects: list[dict]) -> None:
    """Upsert projects from projects.json into project_state table."""
    with get_db() as conn:
        for p in projects:
            conn.execute(
                "INSERT INTO project_state (project_id, path, topic_id, provider, auto_approve_timeout) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(project_id) DO UPDATE SET "
                "path = excluded.path, topic_id = excluded.topic_id, "
                "provider = excluded.provider, "
                "auto_approve_timeout = excluded.auto_approve_timeout",
                (
                    p["project_id"],
                    p["path"],
                    p.get("topic_id"),
                    p.get("provider", "claude"),
                    p.get("auto_approve_timeout", 30),
                ),
            )
```

**Step 3: Create db_exec.sh**

```bash
#!/usr/bin/env bash
# scripts/vps/db_exec.sh
# Bash SQLite wrapper — prepends WAL + busy_timeout PRAGMAs.
# Usage: ./db_exec.sh "SQL statement"
#   or:  echo "SQL" | ./db_exec.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_PATH="${DB_PATH:-${SCRIPT_DIR}/orchestrator.db}"

PRAGMAS="PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON;"

if [[ $# -gt 0 ]]; then
    sqlite3 "$DB_PATH" "${PRAGMAS} $1"
else
    # Read from stdin
    SQL=$(cat)
    sqlite3 "$DB_PATH" "${PRAGMAS} ${SQL}"
fi
```

**Step 4: Verify**

```bash
# Create DB from schema
mkdir -p scripts/vps
sqlite3 scripts/vps/orchestrator.db < scripts/vps/schema.sql

# Verify tables exist
sqlite3 scripts/vps/orchestrator.db ".tables"
# Expected: compute_slots  project_state  task_log

# Verify slots seeded
sqlite3 scripts/vps/orchestrator.db "SELECT * FROM compute_slots;"
# Expected: 3 rows (1|claude|, 2|claude|, 3|codex|)

# Verify db_exec.sh works
chmod +x scripts/vps/db_exec.sh
./scripts/vps/db_exec.sh "SELECT COUNT(*) FROM compute_slots;"
# Expected: 3

# Verify Python db.py imports
cd scripts/vps && python3 -c "import db; print('OK')" && cd ../..
# Expected: OK
```

**Acceptance Criteria:**
- [ ] `sqlite3 orchestrator.db < schema.sql` creates DB with 3 tables
- [ ] `db.py`: `get_db()` context manager with WAL + busy_timeout
- [ ] `db.py`: `try_acquire_slot()` with `BEGIN IMMEDIATE`
- [ ] `db.py`: `release_slot()` on task completion
- [ ] `db.py`: `get_project_state()`, `update_project_phase()`, `seed_projects_from_json()`
- [ ] `db_exec.sh`: bash wrapper prepending PRAGMAs
- [ ] All 3 files < 400 LOC

---

### Task 2: Provider Abstraction (run-agent.sh + runners)

**Files:**
- Create: `scripts/vps/run-agent.sh`
- Create: `scripts/vps/claude-runner.sh`
- Create: `scripts/vps/codex-runner.sh`

**Context:**
Provider abstraction layer. `run-agent.sh` is the single entrypoint that Pueue calls. It dispatches to `claude-runner.sh` or `codex-runner.sh` based on the provider argument. Includes RAM floor gate (3GB minimum) to prevent OOM.

**Step 1: Create run-agent.sh**

```bash
#!/usr/bin/env bash
# scripts/vps/run-agent.sh
# Provider abstraction dispatcher for Pueue tasks.
# Usage: run-agent.sh <project_dir> <task> <provider> [skill]
#   provider: claude | codex
#   skill: autopilot (default) | spark | architect | council | qa | bughunt
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_DIR="${1:?Usage: run-agent.sh <project_dir> <task> <provider> [skill]}"
TASK="${2:?Missing task argument}"
PROVIDER="${3:?Missing provider argument (claude|codex)}"
SKILL="${4:-autopilot}"

# Source environment if available
[[ -f "${SCRIPT_DIR}/.env" ]] && set -a && source "${SCRIPT_DIR}/.env" && set +a

# RAM floor gate: require 3GB free before launching an LLM agent
check_ram() {
    if [[ -f /proc/meminfo ]]; then
        local avail_kb
        avail_kb=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
        local avail_gb=$(( avail_kb / 1048576 ))
        if (( avail_gb < 3 )); then
            echo '{"error":"insufficient_ram","available_gb":'"${avail_gb}"',"required_gb":3}' >&2
            exit 78  # EX_CONFIG
        fi
    fi
    # Skip check on non-Linux (macOS dev)
}

check_ram

# Validate project directory exists
if [[ ! -d "$PROJECT_DIR" ]]; then
    echo '{"error":"project_dir_not_found","path":"'"${PROJECT_DIR}"'"}' >&2
    exit 1
fi

# Dispatch to provider-specific runner
case "$PROVIDER" in
    claude)
        exec "${SCRIPT_DIR}/claude-runner.sh" "$PROJECT_DIR" "$TASK" "$SKILL"
        ;;
    codex)
        exec "${SCRIPT_DIR}/codex-runner.sh" "$PROJECT_DIR" "$TASK" "$SKILL"
        ;;
    *)
        echo '{"error":"unknown_provider","provider":"'"${PROVIDER}"'"}' >&2
        exit 1
        ;;
esac
```

**Step 2: Create claude-runner.sh**

```bash
#!/usr/bin/env bash
# scripts/vps/claude-runner.sh
# Claude Code CLI wrapper with per-project isolation.
# Called by run-agent.sh, never directly.
set -euo pipefail

PROJECT_DIR="${1:?Missing project_dir}"
TASK="${2:?Missing task}"
SKILL="${3:-autopilot}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_BIN="${CLAUDE_PATH:-claude}"

# Per-project config dir (prevents cross-session contamination — DA-9)
CONFIG_DIR="${PROJECT_DIR}/.claude-config"
mkdir -p "$CONFIG_DIR"

# Export env vars for Claude and DLD hooks
export CLAUDE_CODE_CONFIG_DIR="$CONFIG_DIR"
export CLAUDE_PROJECT_DIR="$PROJECT_DIR"
export PROJECT_DIR="$PROJECT_DIR"

# Build command based on skill
PROMPT="/${SKILL} ${TASK}"

# Structured JSON output, bounded turns
timeout 900 "$CLAUDE_BIN" \
    --print \
    --output-format json \
    --max-turns 30 \
    --verbose \
    -p "$PROMPT" \
    2>&1

EXIT_CODE=$?

# Output structured result
echo '{"exit_code":'"${EXIT_CODE}"',"project":"'"$(basename "$PROJECT_DIR")"'","skill":"'"${SKILL}"'","task":"'"${TASK}"'"}'

exit "$EXIT_CODE"
```

**Step 3: Create codex-runner.sh**

```bash
#!/usr/bin/env bash
# scripts/vps/codex-runner.sh
# ChatGPT Codex CLI wrapper.
# Called by run-agent.sh, never directly.
set -euo pipefail

PROJECT_DIR="${1:?Missing project_dir}"
TASK="${2:?Missing task}"
SKILL="${3:-autopilot}"

CODEX_BIN="${CODEX_PATH:-codex}"

cd "$PROJECT_DIR"

# Codex uses sandbox mode for safety
timeout 900 "$CODEX_BIN" exec \
    "$TASK" \
    --sandbox workspace-write \
    --json \
    2>&1

EXIT_CODE=$?

echo '{"exit_code":'"${EXIT_CODE}"',"project":"'"$(basename "$PROJECT_DIR")"'","skill":"'"${SKILL}"'","task":"'"${TASK}"'"}'

exit "$EXIT_CODE"
```

**Step 4: Verify**

```bash
chmod +x scripts/vps/run-agent.sh scripts/vps/claude-runner.sh scripts/vps/codex-runner.sh

# Verify dispatch routes correctly (will fail at claude binary, but validates routing)
scripts/vps/run-agent.sh /tmp/test-project "test" claude 2>&1 || true
# Expected: error about claude not found or project not found, NOT "unknown_provider"

# Verify RAM check function (on Linux)
scripts/vps/run-agent.sh /tmp "test" claude 2>&1 || true
# Expected: runs (or insufficient_ram on low-RAM systems)

# Verify unknown provider rejection
scripts/vps/run-agent.sh /tmp "test" unknown 2>&1 || true
# Expected: {"error":"unknown_provider","provider":"unknown"}
```

**Acceptance Criteria:**
- [ ] `run-agent.sh <project_dir> <task> <provider>` dispatches to correct runner
- [ ] RAM floor gate checks `/proc/meminfo` MemAvailable >= 3GB
- [ ] `claude-runner.sh` sets `CLAUDE_CODE_CONFIG_DIR`, `CLAUDE_PROJECT_DIR`
- [ ] `claude-runner.sh` runs `mkdir -p "$config_dir"` before invocation (DA-9)
- [ ] `codex-runner.sh` uses `--sandbox workspace-write --json`
- [ ] Both runners: timeout 900s, structured JSON output, exit code propagation
- [ ] All 3 files < 400 LOC

---

### Task 3: Pueue Callback

**Files:**
- Create: `scripts/vps/pueue-callback.sh`

**Context:**
Pueue fires this callback script whenever a task finishes (success or failure). It releases the SQLite compute slot and sends a Telegram notification. Uses Pueue template variables `{{ id }}`, `{{ label }}`, `{{ group }}`, `{{ result }}`. Note: Pueue v4.0+ uses `{{ label }}` not `{{ name }}`.

**Step 1: Create pueue-callback.sh**

```bash
#!/usr/bin/env bash
# scripts/vps/pueue-callback.sh
# Pueue completion callback: release slot + notify Telegram.
#
# Called by Pueue daemon via pueue.yml callback config:
#   callback: "/path/to/pueue-callback.sh {{ id }} '{{ label }}' '{{ group }}' '{{ result }}'"
#
# Arguments:
#   $1 = pueue task id
#   $2 = task label (format: "project_id:SPEC-ID")
#   $3 = pueue group (claude-runner or codex-runner)
#   $4 = result status (Success, Failed, etc.)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PUEUE_ID="${1:?Missing pueue task id}"
LABEL="${2:-unknown}"
GROUP="${3:-unknown}"
RESULT="${4:-unknown}"

# Source environment
[[ -f "${SCRIPT_DIR}/.env" ]] && set -a && source "${SCRIPT_DIR}/.env" && set +a

DB_EXEC="${SCRIPT_DIR}/db_exec.sh"

# Parse project_id from label (format: "project_id:SPEC-ID")
PROJECT_ID="${LABEL%%:*}"
TASK_ID="${LABEL#*:}"

# Determine status from Pueue result
case "$RESULT" in
    *Success*) STATUS="done"; EXIT_CODE=0 ;;
    *)         STATUS="failed"; EXIT_CODE=1 ;;
esac

# 1. Release compute slot (ALWAYS — even on failure, DA-8/SA-2)
"$DB_EXEC" "UPDATE compute_slots SET project_id = NULL, pid = NULL, pueue_id = NULL, acquired_at = NULL WHERE pueue_id = ${PUEUE_ID};"

# 2. Update task_log
"$DB_EXEC" "UPDATE task_log SET status = '${STATUS}', exit_code = ${EXIT_CODE}, finished_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE pueue_id = ${PUEUE_ID} AND finished_at IS NULL;"

# 3. Update project phase
if [[ "$STATUS" == "done" ]]; then
    "$DB_EXEC" "UPDATE project_state SET phase = 'qa_pending', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE project_id = '${PROJECT_ID}';"
else
    "$DB_EXEC" "UPDATE project_state SET phase = 'failed', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE project_id = '${PROJECT_ID}';"
fi

# 4. Get last 5 lines of Pueue log for summary
SUMMARY=""
if command -v pueue &>/dev/null; then
    SUMMARY=$(pueue log "$PUEUE_ID" --lines 5 2>/dev/null | tail -5 || echo "")
fi

# 5. Send Telegram notification
if [[ "$STATUS" == "done" ]]; then
    MSG="Task ${TASK_ID} completed successfully for ${PROJECT_ID}."
else
    MSG="Task ${TASK_ID} FAILED for ${PROJECT_ID}. Check logs: pueue log ${PUEUE_ID}"
fi

# Notify via Python helper (has topic routing)
python3 "${SCRIPT_DIR}/notify.py" "$PROJECT_ID" "$MSG" 2>/dev/null || true

echo "[callback] pueue_id=${PUEUE_ID} project=${PROJECT_ID} task=${TASK_ID} status=${STATUS}"
```

**Step 2: Verify**

```bash
chmod +x scripts/vps/pueue-callback.sh

# Verify script parses args correctly (will fail at DB, but validates parsing)
scripts/vps/pueue-callback.sh 42 "saas-app:FTR-100" "claude-runner" "Success" 2>&1 || true
# Expected: attempts DB operations (may fail if DB not init'd yet)

# Verify label parsing
bash -c 'LABEL="saas-app:FTR-100"; echo "${LABEL%%:*}"; echo "${LABEL#*:}"'
# Expected: saas-app \n FTR-100
```

**Acceptance Criteria:**
- [ ] `pueue-callback.sh` receives `{{ id }}` `{{ label }}` `{{ group }}` `{{ result }}`
- [ ] Releases SQLite slot regardless of exit code (DA-8, SA-2)
- [ ] Updates task_log with status + exit_code + finished_at
- [ ] Updates project_state phase to `qa_pending` (success) or `failed`
- [ ] Calls `notify.py` to send Telegram notification
- [ ] File < 400 LOC

---

### Task 4: Telegram Bot Core + Notify Helper

**Files:**
- Create: `scripts/vps/telegram-bot.py`
- Create: `scripts/vps/notify.py`
- Create: `scripts/vps/requirements.txt`

**Context:**
Telegram bot with PTB v21.9+ (NOT v22 -- breaking changes). Routes messages by `message_thread_id` to projects. Handles `/status`, `/run`, `/pause`, `/resume` commands. Text messages in project topics are saved to inbox with keyword routing. `notify.py` is a standalone script for sending notifications from bash callbacks.

**Step 1: Create requirements.txt**

```
# scripts/vps/requirements.txt
python-telegram-bot>=21.9,<22.0
python-dotenv>=1.0.0
```

**Step 2: Create notify.py**

```python
#!/usr/bin/env python3
"""
Module: notify
Role: Standalone Telegram notification helper for bash scripts.
Uses: db.py, python-telegram-bot
Used by: pueue-callback.sh, orchestrator.sh, qa-loop.sh

Usage: python3 notify.py <project_id> <message>
"""
import asyncio
import os
import sys
from pathlib import Path

# Add script dir to path for db import
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import db


async def send_to_project(project_id: str, text: str) -> bool:
    """Send a message to a project's Telegram topic.

    Looks up topic_id from SQLite, sends via Bot API.
    Falls back to General topic (no thread_id) if topic_id is None.
    """
    from telegram import Bot

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        print("[notify] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID", file=sys.stderr)
        return False

    project = db.get_project_state(project_id)
    if project is None:
        print(f"[notify] Project not found: {project_id}", file=sys.stderr)
        return False

    topic_id = project.get("topic_id")

    bot = Bot(token=token)
    try:
        # DA-4: message_thread_id=1 is General topic bug.
        # Pass None instead of 1 to send to General.
        thread_id = topic_id if topic_id and topic_id != 1 else None

        await bot.send_message(
            chat_id=int(chat_id),
            message_thread_id=thread_id,
            text=text,
            parse_mode="Markdown",
        )
        return True
    except Exception as e:
        print(f"[notify] Failed to send: {e}", file=sys.stderr)
        return False
    finally:
        await bot.shutdown()


async def send_to_general(text: str) -> bool:
    """Send a message to the General topic (no thread_id)."""
    from telegram import Bot

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        return False

    bot = Bot(token=token)
    try:
        await bot.send_message(
            chat_id=int(chat_id),
            text=text,
            parse_mode="Markdown",
        )
        return True
    except Exception as e:
        print(f"[notify] Failed to send to general: {e}", file=sys.stderr)
        return False
    finally:
        await bot.shutdown()


def main() -> None:
    """CLI entrypoint: notify.py <project_id> <message>"""
    if len(sys.argv) < 3:
        print("Usage: notify.py <project_id> <message>", file=sys.stderr)
        sys.exit(1)

    project_id = sys.argv[1]
    message = sys.argv[2]

    success = asyncio.run(send_to_project(project_id, message))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
```

**Step 3: Create telegram-bot.py (core -- auto-approve added in Task 7)**

```python
#!/usr/bin/env python3
"""
Module: telegram-bot
Role: Telegram bot with forum topic routing for multi-project orchestration.
Uses: db.py, notify.py, python-telegram-bot v21.9+
Used by: systemd (dld-telegram-bot.service)
"""
import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Add script dir for db import
sys.path.insert(0, str(Path(__file__).parent))
import db

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("dld-bot")

# Config from env
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
ALLOWED_USERS = set(
    int(uid.strip())
    for uid in os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",")
    if uid.strip()
)
SCRIPT_DIR = Path(__file__).parent

# Keyword routing patterns (Russian + English)
ROUTE_PATTERNS: dict[str, list[str]] = {
    "architect": [
        "архитектура", "спроектируй", "система", "домены",
        "как устроить", "интеграция", "design system",
        "bounded context", "data flow", "инфраструктура",
        "схема данных", "миграция", "рефакторинг архитектуры",
    ],
    "council": [
        "консилиум", "сравни подходы", "что лучше",
        "trade-off", "выбери между", "стоит ли",
        "плюсы и минусы", "совет директоров",
    ],
    "spark_bug": [
        "баг", "ошибка", "не работает", "сломалось",
        "падает", "crash", "fix", "broken",
        "регрессия", "regression",
    ],
    "bughunt": [
        "баг хант", "охота на баги", "глубокий анализ багов",
        "много багов", "всё сломалось", "системные проблемы",
        "deep analysis", "bug hunt", "командный аудит багов",
    ],
}


def detect_route(text: str) -> str:
    """Detect skill route from message text via keyword matching."""
    text_lower = text.lower()
    for route, keywords in ROUTE_PATTERNS.items():
        if any(kw in text_lower for kw in keywords):
            return route
    return "spark"


def is_authorized(user_id: int) -> bool:
    """Check if user is in allowed list."""
    if not ALLOWED_USERS:
        return True  # No whitelist = allow all (dev mode)
    return user_id in ALLOWED_USERS


def get_topic_id(update: Update) -> int | None:
    """Extract message_thread_id, handling General topic bug (DA-4)."""
    thread_id = getattr(update.effective_message, "message_thread_id", None)
    # DA-4: thread_id=1 is General topic, returns BadRequest if used
    if thread_id == 1:
        return None
    return thread_id


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command. Shows project state from SQLite + Pueue."""
    if not is_authorized(update.effective_user.id):
        return

    # Check if project-specific or global
    args = context.args or []
    topic_id = get_topic_id(update)

    if args:
        # /status <project_id>
        project = db.get_project_state(args[0])
        if not project:
            await update.message.reply_text(f"Project `{args[0]}` not found.", parse_mode="Markdown")
            return
        await _send_project_status(update, project)
    elif topic_id:
        # In project topic — show this project
        project = db.get_project_by_topic(topic_id)
        if project:
            await _send_project_status(update, project)
        else:
            await update.message.reply_text("This topic is not linked to a project.")
    else:
        # General topic — show all projects
        projects = db.get_all_projects()
        if not projects:
            await update.message.reply_text("No projects configured.")
            return
        lines = ["*All Projects:*\n"]
        for p in projects:
            status_icon = {"idle": "⚪", "running": "🟢", "qa_pending": "🟡", "failed": "🔴"}.get(p["phase"], "⚫")
            task_info = f" ({p['current_task']})" if p.get("current_task") else ""
            lines.append(f"{status_icon} `{p['project_id']}` — {p['phase']}{task_info}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def _send_project_status(update: Update, project: dict) -> None:
    """Format and send detailed project status."""
    # Get Pueue status for this project
    pueue_info = ""
    try:
        result = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            pueue_data = json.loads(result.stdout)
            tasks = pueue_data.get("tasks", {})
            project_tasks = [
                t for t in tasks.values()
                if t.get("label", "").startswith(project["project_id"] + ":")
            ]
            if project_tasks:
                pueue_lines = []
                for t in project_tasks[-3:]:  # Last 3 tasks
                    pueue_lines.append(f"  #{t['id']} {t.get('label','')} — {t.get('status','?')}")
                pueue_info = "\n*Pueue tasks:*\n" + "\n".join(pueue_lines)
    except Exception:
        pass

    slots = db.get_available_slots(project.get("provider", "claude"))
    msg = (
        f"*{project['project_id']}*\n"
        f"Phase: `{project['phase']}`\n"
        f"Provider: `{project.get('provider', 'claude')}`\n"
        f"Current task: `{project.get('current_task', 'none')}`\n"
        f"Auto-approve: `{project.get('auto_approve_timeout', 30)}s`\n"
        f"Available slots: `{slots}`\n"
        f"Path: `{project['path']}`"
        f"{pueue_info}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /run command. Triggers orchestrator cycle or writes to inbox."""
    if not is_authorized(update.effective_user.id):
        return

    args = context.args or []
    topic_id = get_topic_id(update)

    # Determine target project
    project = None
    task_text = None

    if args:
        project = db.get_project_state(args[0])
        if not project:
            await update.message.reply_text(f"Project `{args[0]}` not found.", parse_mode="Markdown")
            return
        task_text = " ".join(args[1:]) if len(args) > 1 else None
    elif topic_id:
        project = db.get_project_by_topic(topic_id)

    if not project:
        await update.message.reply_text("Specify project: `/run <project>` or use in project topic.", parse_mode="Markdown")
        return

    if task_text:
        # Write task to inbox
        _save_to_inbox(project, task_text)
        await update.message.reply_text(
            f"Saved to inbox: `{task_text}`\nTriggering cycle...",
            parse_mode="Markdown",
        )

    # Touch trigger file for orchestrator
    trigger_file = SCRIPT_DIR / f".run-now-{project['project_id']}"
    trigger_file.touch()
    if not task_text:
        await update.message.reply_text(
            f"Triggered immediate cycle for `{project['project_id']}`.",
            parse_mode="Markdown",
        )


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /pause command. Pauses project's Pueue group."""
    if not is_authorized(update.effective_user.id):
        return

    project = _resolve_project(update, context)
    if not project:
        await update.message.reply_text("Specify project: `/pause <project>`", parse_mode="Markdown")
        return

    try:
        subprocess.run(["pueue", "pause", "--group", project["project_id"]], timeout=5)
        db.update_project_phase(project["project_id"], "paused")
        await update.message.reply_text(f"Paused `{project['project_id']}`.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Pause failed: {e}")


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /resume command. Resumes project's Pueue group."""
    if not is_authorized(update.effective_user.id):
        return

    project = _resolve_project(update, context)
    if not project:
        await update.message.reply_text("Specify project: `/resume <project>`", parse_mode="Markdown")
        return

    try:
        subprocess.run(["pueue", "start", "--group", project["project_id"]], timeout=5)
        db.update_project_phase(project["project_id"], "idle")
        await update.message.reply_text(f"Resumed `{project['project_id']}`.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Resume failed: {e}")


def _resolve_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    """Resolve project from command args or topic_id."""
    args = context.args or []
    if args:
        return db.get_project_state(args[0])
    topic_id = get_topic_id(update)
    if topic_id:
        return db.get_project_by_topic(topic_id)
    return None


def _save_to_inbox(project: dict, text: str) -> Path:
    """Save a text message to project's ai/inbox/ directory."""
    inbox_dir = Path(project["path"]) / "ai" / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    route = detect_route(text)

    filename = f"{timestamp}-telegram.md"
    filepath = inbox_dir / filename

    content = (
        f"# Idea: {timestamp}\n"
        f"**Source:** telegram\n"
        f"**Route:** {route}\n"
        f"**Status:** new\n"
        f"---\n"
        f"{text}\n"
    )
    filepath.write_text(content, encoding="utf-8")
    logger.info("Saved to inbox: %s (route=%s)", filepath, route)
    return filepath


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plain text messages in project topics -> save to inbox."""
    if not is_authorized(update.effective_user.id):
        return

    topic_id = get_topic_id(update)
    if not topic_id:
        return  # Ignore messages in General topic

    project = db.get_project_by_topic(topic_id)
    if not project:
        return  # Topic not linked to a project

    text = update.message.text
    if not text or text.startswith("/"):
        return

    filepath = _save_to_inbox(project, text)
    route = detect_route(text)

    await update.message.reply_text(
        f"Saved to inbox (route: `{route}`).\n"
        f"Orchestrator will process on next cycle.",
        parse_mode="Markdown",
    )


def main() -> None:
    """Start the Telegram bot."""
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # Command handlers
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("run", cmd_run))
    application.add_handler(CommandHandler("pause", cmd_pause))
    application.add_handler(CommandHandler("resume", cmd_resume))

    # Text message handler (must be after commands)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

    logger.info("Starting DLD Telegram bot (PTB v21.9+)")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
```

**Step 4: Verify**

```bash
# Check syntax
python3 -c "import ast; ast.parse(open('scripts/vps/telegram-bot.py').read()); print('OK')"
python3 -c "import ast; ast.parse(open('scripts/vps/notify.py').read()); print('OK')"

# Verify requirements install
pip install -r scripts/vps/requirements.txt --dry-run
# Expected: python-telegram-bot>=21.9,<22.0 resolves

# Verify detect_route function
python3 -c "
import sys; sys.path.insert(0, 'scripts/vps')
from importlib.machinery import SourceFileLoader
bot = SourceFileLoader('bot', 'scripts/vps/telegram-bot.py').load_module()
assert bot.detect_route('спроектируй систему нотификаций') == 'architect'
assert bot.detect_route('добавь кнопку логина') == 'spark'
assert bot.detect_route('не работает авторизация') == 'spark_bug'
assert bot.detect_route('много багов, всё сломалось после обновления') == 'bughunt'
print('All routing tests passed')
"
```

**Acceptance Criteria:**
- [ ] `telegram-bot.py`: PTB v21.9+ with `drop_pending_updates=True`
- [ ] Auth: `is_authorized()` checks `TELEGRAM_ALLOWED_USERS`
- [ ] Topic routing: `message_thread_id` -> `project_id` via SQLite
- [ ] Guard: `message_thread_id=1` -> treat as General (DA-4)
- [ ] Commands: `/status`, `/run`, `/pause`, `/resume` all working
- [ ] Text messages in topics -> `save_to_inbox()` with keyword routing
- [ ] `notify.py`: standalone CLI + async `send_to_project()`
- [ ] `requirements.txt`: pinned `python-telegram-bot>=21.9,<22.0`
- [ ] `telegram-bot.py` < 400 LOC, `notify.py` < 400 LOC

---

### Task 5: Inbox Processor with Keyword Routing

**Files:**
- Create: `scripts/vps/inbox-processor.sh`

**Context:**
Called by orchestrator for each new file in `ai/inbox/`. Reads the `**Route:**` metadata from the inbox file and dispatches to the correct Claude skill. Submits the task through Pueue (via run-agent.sh) so it respects slot limits.

**Step 1: Create inbox-processor.sh**

```bash
#!/usr/bin/env bash
# scripts/vps/inbox-processor.sh
# Process inbox files: read route metadata, dispatch to skill via Pueue.
# Usage: inbox-processor.sh <project_id> <project_dir> <inbox_file>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ID="${1:?Usage: inbox-processor.sh <project_id> <project_dir> <inbox_file>}"
PROJECT_DIR="${2:?Missing project_dir}"
INBOX_FILE="${3:?Missing inbox_file}"

# Source environment
[[ -f "${SCRIPT_DIR}/.env" ]] && set -a && source "${SCRIPT_DIR}/.env" && set +a

DB_EXEC="${SCRIPT_DIR}/db_exec.sh"

# Validate file exists and has new status
if [[ ! -f "$INBOX_FILE" ]]; then
    echo "[inbox] File not found: $INBOX_FILE" >&2
    exit 1
fi

# Check if already processed
if ! grep -q '^\*\*Status:\*\* new' "$INBOX_FILE" 2>/dev/null; then
    echo "[inbox] Skipping (not new): $INBOX_FILE"
    exit 0
fi

# Extract route from metadata
ROUTE=$(grep -oP '^\*\*Route:\*\* \K\S+' "$INBOX_FILE" 2>/dev/null || echo "spark")

# Extract idea text (everything after --- separator)
IDEA_TEXT=$(sed -n '/^---$/,$ { /^---$/d; p; }' "$INBOX_FILE" | head -50)

# Map route to Claude skill and command
case "$ROUTE" in
    spark)
        SKILL="spark"
        TASK_CMD="/spark ${IDEA_TEXT}"
        ;;
    architect)
        SKILL="architect"
        TASK_CMD="/architect ${IDEA_TEXT}"
        ;;
    council)
        SKILL="council"
        TASK_CMD="/council ${IDEA_TEXT}"
        ;;
    spark_bug)
        SKILL="spark"
        TASK_CMD="/spark ${IDEA_TEXT}"
        ;;
    bughunt)
        SKILL="spark"
        TASK_CMD="/spark bug hunt ${IDEA_TEXT}"
        ;;
    *)
        SKILL="spark"
        TASK_CMD="/spark ${IDEA_TEXT}"
        ;;
esac

# Get provider from project state
PROVIDER=$("$DB_EXEC" "SELECT provider FROM project_state WHERE project_id = '${PROJECT_ID}';" 2>/dev/null || echo "claude")
PROVIDER="${PROVIDER:-claude}"

# Generate task label
TIMESTAMP=$(date '+%Y%m%d-%H%M%S')
TASK_LABEL="${PROJECT_ID}:inbox-${TIMESTAMP}"

# Submit to Pueue
PUEUE_GROUP="${PROVIDER}-runner"

echo "[inbox] Dispatching: route=${ROUTE} skill=${SKILL} project=${PROJECT_ID}"

PUEUE_ID=$(pueue add \
    --group "$PUEUE_GROUP" \
    --label "$TASK_LABEL" \
    --print-task-id \
    -- "${SCRIPT_DIR}/run-agent.sh" "$PROJECT_DIR" "$TASK_CMD" "$PROVIDER" "$SKILL")

# Log task in SQLite
"$DB_EXEC" "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) VALUES ('${PROJECT_ID}', '${TASK_LABEL}', '${SKILL}', 'queued', ${PUEUE_ID});"

# Update project phase
"$DB_EXEC" "UPDATE project_state SET phase = 'processing_inbox', current_task = '${TASK_LABEL}', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE project_id = '${PROJECT_ID}';"

# Mark inbox file as processed
sed -i 's/^\*\*Status:\*\* new/\*\*Status:\*\* processing/' "$INBOX_FILE"

# Move to done directory
DONE_DIR="$(dirname "$INBOX_FILE")/done"
mkdir -p "$DONE_DIR"
mv "$INBOX_FILE" "$DONE_DIR/"

echo "[inbox] Submitted pueue_id=${PUEUE_ID} label=${TASK_LABEL}"
```

**Step 2: Verify**

```bash
chmod +x scripts/vps/inbox-processor.sh

# Create test inbox file
mkdir -p /tmp/test-project/ai/inbox
cat > /tmp/test-project/ai/inbox/test.md << 'EOF'
# Idea: test
**Source:** telegram
**Route:** spark
**Status:** new
---
Add a login button to the main page
EOF

# Verify route extraction
grep -oP '^\*\*Route:\*\* \K\S+' /tmp/test-project/ai/inbox/test.md
# Expected: spark

# Verify idea text extraction
sed -n '/^---$/,$ { /^---$/d; p; }' /tmp/test-project/ai/inbox/test.md
# Expected: Add a login button to the main page
```

**Acceptance Criteria:**
- [ ] Reads `**Route:**` from inbox file metadata
- [ ] Dispatches to correct skill (spark/architect/council/spark_bug/bughunt)
- [ ] Submits task to Pueue via `run-agent.sh`
- [ ] Moves processed files to `ai/inbox/done/`
- [ ] Logs task in SQLite task_log
- [ ] Updates project phase
- [ ] File < 400 LOC

---

### Task 6: Orchestrator Main Loop

**Files:**
- Create: `scripts/vps/orchestrator.sh`

**Context:**
Main daemon loop. Runs as systemd service. Each cycle: reads projects.json, hot-reloads config, iterates over projects: git pull, scan inbox, scan backlog for queued specs, dispatch QA after autopilot completes.

**Step 1: Create orchestrator.sh**

```bash
#!/usr/bin/env bash
# scripts/vps/orchestrator.sh
# Main daemon loop for multi-project orchestration.
# Runs as systemd service (dld-orchestrator.service).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source environment
[[ -f "${SCRIPT_DIR}/.env" ]] && set -a && source "${SCRIPT_DIR}/.env" && set +a

DB_EXEC="${SCRIPT_DIR}/db_exec.sh"
POLL_INTERVAL="${POLL_INTERVAL:-300}"
PROJECTS_JSON="${PROJECTS_JSON:-${SCRIPT_DIR}/projects.json}"

# PID file for health checks
PID_FILE="${SCRIPT_DIR}/.orchestrator.pid"
echo $$ > "$PID_FILE"
trap 'rm -f "$PID_FILE"' EXIT

log_json() {
    local level="$1" msg="$2"
    echo "{\"ts\":\"$(date -u '+%Y-%m-%dT%H:%M:%SZ')\",\"level\":\"${level}\",\"msg\":\"${msg}\"}"
}

# Seed/sync projects from JSON to SQLite
sync_projects() {
    if [[ ! -f "$PROJECTS_JSON" ]]; then
        log_json "warn" "projects.json not found: ${PROJECTS_JSON}"
        return
    fi
    python3 -c "
import json, sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
with open('${PROJECTS_JSON}') as f:
    projects = json.load(f)
db.seed_projects_from_json(projects)
print(f'Synced {len(projects)} projects')
"
}

# Git pull for a project
git_pull() {
    local project_dir="$1"
    if [[ ! -d "${project_dir}/.git" ]]; then
        log_json "warn" "Not a git repo: ${project_dir}"
        return 1
    fi
    cd "$project_dir"
    if ! git pull --ff-only origin develop 2>&1; then
        log_json "warn" "git pull failed for ${project_dir}"
        return 1
    fi
    cd "$SCRIPT_DIR"
    return 0
}

# Scan inbox for new files
scan_inbox() {
    local project_id="$1" project_dir="$2"
    local inbox_dir="${project_dir}/ai/inbox"

    [[ ! -d "$inbox_dir" ]] && return

    local count=0
    for inbox_file in "${inbox_dir}"/*.md; do
        [[ ! -f "$inbox_file" ]] && continue
        # Only process files with Status: new
        if grep -q '^\*\*Status:\*\* new' "$inbox_file" 2>/dev/null; then
            log_json "info" "Processing inbox: ${inbox_file}"
            "${SCRIPT_DIR}/inbox-processor.sh" "$project_id" "$project_dir" "$inbox_file" || \
                log_json "error" "inbox-processor failed for ${inbox_file}"
            count=$((count + 1))
        fi
    done

    if (( count > 0 )); then
        log_json "info" "Processed ${count} inbox files for ${project_id}"
    fi
}

# Scan backlog for queued specs
scan_backlog() {
    local project_id="$1" project_dir="$2"
    local backlog="${project_dir}/ai/backlog.md"

    [[ ! -f "$backlog" ]] && return

    # Find first queued spec
    local spec_id
    spec_id=$(grep -E '\|\s*queued\s*\|' "$backlog" 2>/dev/null | head -1 | \
              grep -oE '(TECH|FTR|BUG|ARCH)-[0-9]+' | head -1 || echo "")

    [[ -z "$spec_id" ]] && return

    # Check if slot available
    local provider
    provider=$("$DB_EXEC" "SELECT provider FROM project_state WHERE project_id = '${project_id}';" 2>/dev/null || echo "claude")
    provider="${provider:-claude}"

    local available
    available=$(python3 -c "
import sys; sys.path.insert(0, '${SCRIPT_DIR}')
import db; print(db.get_available_slots('${provider}'))
")

    if (( available < 1 )); then
        log_json "info" "No slots for ${project_id} (provider=${provider})"
        return
    fi

    # Find spec file
    local spec_file
    spec_file=$(find "${project_dir}/ai/features/" -name "${spec_id}*" -type f 2>/dev/null | head -1 || echo "")

    if [[ -z "$spec_file" ]]; then
        log_json "warn" "Spec file not found for ${spec_id} in ${project_dir}/ai/features/"
        return
    fi

    # Submit autopilot to Pueue
    local task_label="${project_id}:${spec_id}"
    local pueue_group="${provider}-runner"

    log_json "info" "Submitting autopilot: ${task_label}"

    local pueue_id
    pueue_id=$(pueue add \
        --group "$pueue_group" \
        --label "$task_label" \
        --print-task-id \
        -- "${SCRIPT_DIR}/run-agent.sh" "$project_dir" "autopilot ${spec_id}" "$provider" "autopilot")

    # Acquire slot
    python3 -c "
import sys; sys.path.insert(0, '${SCRIPT_DIR}')
import db; db.try_acquire_slot('${project_id}', '${provider}', ${pueue_id})
"

    # Log task
    "$DB_EXEC" "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) VALUES ('${project_id}', '${task_label}', 'autopilot', 'running', ${pueue_id});"

    # Update project phase
    "$DB_EXEC" "UPDATE project_state SET phase = 'autopilot', current_task = '${spec_id}', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE project_id = '${project_id}';"

    log_json "info" "Submitted pueue_id=${pueue_id} for ${task_label}"
}

# Check for QA-pending projects and dispatch QA
dispatch_qa() {
    local project_id="$1" project_dir="$2"

    local phase
    phase=$("$DB_EXEC" "SELECT phase FROM project_state WHERE project_id = '${project_id}';" 2>/dev/null || echo "")

    [[ "$phase" != "qa_pending" ]] && return

    local current_task
    current_task=$("$DB_EXEC" "SELECT current_task FROM project_state WHERE project_id = '${project_id}';" 2>/dev/null || echo "")

    [[ -z "$current_task" ]] && return

    log_json "info" "Dispatching QA for ${project_id}:${current_task}"
    "${SCRIPT_DIR}/qa-loop.sh" "$project_id" "$project_dir" "$current_task" &
}

# Main loop
log_json "info" "Orchestrator starting (pid=$$, poll=${POLL_INTERVAL}s)"

while true; do
    # Hot-reload projects
    sync_projects

    # Get all enabled projects
    PROJECTS=$(python3 -c "
import json, sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
for p in db.get_all_projects():
    print(f\"{p['project_id']}|{p['path']}\")
" 2>/dev/null || echo "")

    while IFS='|' read -r project_id project_dir; do
        [[ -z "$project_id" ]] && continue

        # Check for /run trigger
        TRIGGER_FILE="${SCRIPT_DIR}/.run-now-${project_id}"
        if [[ -f "$TRIGGER_FILE" ]]; then
            rm -f "$TRIGGER_FILE"
            log_json "info" "Triggered immediate cycle for ${project_id}"
        fi

        log_json "info" "Processing: ${project_id}"

        # 1. Git pull
        git_pull "$project_dir" || true

        # 2. Scan inbox
        scan_inbox "$project_id" "$project_dir"

        # 3. Scan backlog
        scan_backlog "$project_id" "$project_dir"

        # 4. Check QA pending
        dispatch_qa "$project_id" "$project_dir"

    done <<< "$PROJECTS"

    log_json "info" "Cycle complete. Sleeping ${POLL_INTERVAL}s..."
    sleep "$POLL_INTERVAL"
done
```

**Step 2: Verify**

```bash
chmod +x scripts/vps/orchestrator.sh

# Verify syntax
bash -n scripts/vps/orchestrator.sh
# Expected: no output (syntax OK)

# Verify log_json output format
bash -c 'source scripts/vps/orchestrator.sh; log_json "info" "test"' 2>/dev/null || true
# Not directly testable (runs main loop), but syntax check covers it
```

**Acceptance Criteria:**
- [ ] Reads `projects.json` each cycle (hot-reload via `sync_projects`)
- [ ] Per project: git pull, inbox scan, backlog scan, QA dispatch
- [ ] Slot acquisition before Pueue submission
- [ ] `POLL_INTERVAL` configurable (default 300s)
- [ ] `.run-now-{project}` trigger file for immediate cycle
- [ ] Structured JSON logging to stdout
- [ ] PID file for health checks
- [ ] File < 400 LOC

---

### Task 7: Auto-Approve with Spark Summary

**Files:**
- Modify: `scripts/vps/telegram-bot.py` (add auto-approve flow + CallbackQueryHandler)

**Context:**
After inbox-processor creates a spec, the bot displays a summary with Approve/Cancel buttons and starts a countdown timer. If no cancel within timeout, auto-submits to Pueue. Uses PTB JobQueue for the timer.

**Step 1: Add auto-approve imports and handler to telegram-bot.py**

Add after the existing `CallbackQueryHandler` import (already present):

Add these functions before the `main()` function in telegram-bot.py:

```python
# --- Auto-approve flow ---

async def send_auto_approve(
    application: Application,
    project: dict,
    spec_id: str,
    summary: str,
) -> None:
    """Send auto-approve message with countdown to project's Telegram topic."""
    timeout = project.get("auto_approve_timeout", 30)
    topic_id = project.get("topic_id")
    thread_id = topic_id if topic_id and topic_id != 1 else None

    text = (
        f"Spec ready: *{spec_id}*\n"
        f"Summary: {summary}\n\n"
    )

    if timeout == 0:
        text += "Auto-approve disabled. Press Approve to start."
    else:
        text += f"Auto-starting in {timeout}s..."

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Approve", callback_data=f"approve:{project['project_id']}:{spec_id}"),
            InlineKeyboardButton("Cancel", callback_data=f"cancel:{project['project_id']}:{spec_id}"),
        ]
    ])

    msg = await application.bot.send_message(
        chat_id=CHAT_ID,
        message_thread_id=thread_id,
        text=text,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )

    if timeout > 0:
        # Schedule auto-approve timer
        application.job_queue.run_once(
            _auto_approve_callback,
            when=timeout,
            data={
                "project": project,
                "spec_id": spec_id,
                "message_id": msg.message_id,
                "chat_id": CHAT_ID,
            },
            name=f"auto_approve:{project['project_id']}:{spec_id}",
        )


async def _auto_approve_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Timer fired — auto-approve the spec."""
    data = context.job.data
    project = data["project"]
    spec_id = data["spec_id"]

    # Submit to orchestrator (touch trigger file)
    trigger = SCRIPT_DIR / f".run-now-{project['project_id']}"
    trigger.touch()

    # Edit original message
    try:
        await context.bot.edit_message_text(
            chat_id=data["chat_id"],
            message_id=data["message_id"],
            text=f"Spec *{spec_id}* auto-approved. Starting...",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning("Failed to edit auto-approve message: %s", e)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Approve/Cancel button presses."""
    query = update.callback_query
    await query.answer()

    if not is_authorized(query.from_user.id):
        return

    data = query.data  # format: "approve:project_id:spec_id" or "cancel:project_id:spec_id"
    parts = data.split(":", 2)
    if len(parts) != 3:
        return

    action, project_id, spec_id = parts

    # Cancel any existing timer
    job_name = f"auto_approve:{project_id}:{spec_id}"
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()

    if action == "approve":
        # Immediate trigger
        trigger = SCRIPT_DIR / f".run-now-{project_id}"
        trigger.touch()

        await query.edit_message_text(
            text=f"Spec *{spec_id}* approved. Starting...",
            parse_mode="Markdown",
        )

    elif action == "cancel":
        await query.edit_message_text(
            text=f"Spec *{spec_id}* cancelled.",
            parse_mode="Markdown",
        )
```

Then in `main()`, add the CallbackQueryHandler:

```python
    # Add after command handlers, before MessageHandler
    application.add_handler(CallbackQueryHandler(handle_callback))
```

**Step 2: Verify**

```bash
# Verify syntax still valid after modifications
python3 -c "import ast; ast.parse(open('scripts/vps/telegram-bot.py').read()); print('OK')"
# Expected: OK
```

**Acceptance Criteria:**
- [ ] `send_auto_approve()` sends message with Approve/Cancel buttons
- [ ] `auto_approve_timeout` read from project state (per-project)
- [ ] `0` = never auto-approve (no timer scheduled)
- [ ] Timer fires -> triggers orchestrator cycle, edits message
- [ ] Cancel button -> removes timer job, edits message to "Cancelled"
- [ ] Approve button -> immediate trigger, cancels timer
- [ ] `telegram-bot.py` still < 400 LOC after additions

---

### Task 8: QA Dispatch

**Files:**
- Create: `scripts/vps/qa-loop.sh`

**Context:**
Called by orchestrator when a project reaches `qa_pending` phase. Runs `/qa` skill on the completed spec. Reports results via Telegram notification. On failure, writes bugs back to inbox for the cycle to repeat.

**Step 1: Create qa-loop.sh**

```bash
#!/usr/bin/env bash
# scripts/vps/qa-loop.sh
# QA dispatch: run /qa skill after autopilot completion.
# Usage: qa-loop.sh <project_id> <project_dir> <spec_id>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ID="${1:?Usage: qa-loop.sh <project_id> <project_dir> <spec_id>}"
PROJECT_DIR="${2:?Missing project_dir}"
SPEC_ID="${3:?Missing spec_id}"

# Source environment
[[ -f "${SCRIPT_DIR}/.env" ]] && set -a && source "${SCRIPT_DIR}/.env" && set +a

DB_EXEC="${SCRIPT_DIR}/db_exec.sh"
CLAUDE_BIN="${CLAUDE_PATH:-claude}"
QA_TIMEOUT="${QA_TIMEOUT:-600}"

# Update phase
"$DB_EXEC" "UPDATE project_state SET phase = 'qa_running', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE project_id = '${PROJECT_ID}';"

# Find spec file
SPEC_FILE=$(find "${PROJECT_DIR}/ai/features/" -name "${SPEC_ID}*" -type f 2>/dev/null | head -1 || echo "")

if [[ -z "$SPEC_FILE" ]]; then
    echo "[qa] Spec file not found: ${SPEC_ID}" >&2
    python3 "${SCRIPT_DIR}/notify.py" "$PROJECT_ID" "QA skipped: spec file not found for ${SPEC_ID}" 2>/dev/null || true
    "$DB_EXEC" "UPDATE project_state SET phase = 'idle', current_task = NULL, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE project_id = '${PROJECT_ID}';"
    exit 1
fi

# Run QA via Claude
export CLAUDE_PROJECT_DIR="$PROJECT_DIR"
export PROJECT_DIR="$PROJECT_DIR"

CONFIG_DIR="${PROJECT_DIR}/.claude-config"
mkdir -p "$CONFIG_DIR"
export CLAUDE_CODE_CONFIG_DIR="$CONFIG_DIR"

echo "[qa] Running QA for ${SPEC_ID} in ${PROJECT_DIR}"

set +e
QA_OUTPUT=$(timeout "$QA_TIMEOUT" "$CLAUDE_BIN" \
    --print \
    --output-format json \
    --max-turns 15 \
    -p "/qa ${SPEC_ID}" \
    2>&1)
QA_EXIT=$?
set -e

# Determine result
if (( QA_EXIT == 0 )); then
    # QA passed
    "$DB_EXEC" "UPDATE project_state SET phase = 'idle', current_task = NULL, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE project_id = '${PROJECT_ID}';"
    python3 "${SCRIPT_DIR}/notify.py" "$PROJECT_ID" "QA PASSED for ${SPEC_ID}" 2>/dev/null || true
    echo "[qa] PASSED: ${SPEC_ID}"
else
    # QA failed — write bugs to inbox for cycle to repeat
    "$DB_EXEC" "UPDATE project_state SET phase = 'qa_failed', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE project_id = '${PROJECT_ID}';"

    TIMESTAMP=$(date '+%Y%m%d-%H%M%S')
    INBOX_DIR="${PROJECT_DIR}/ai/inbox"
    mkdir -p "$INBOX_DIR"

    # Write QA failure as new inbox item
    cat > "${INBOX_DIR}/${TIMESTAMP}-qa-fail.md" << EOF
# Idea: ${TIMESTAMP}
**Source:** qa-dispatch
**Route:** spark_bug
**Status:** new
---
QA failed for ${SPEC_ID}. Exit code: ${QA_EXIT}.

Please investigate and fix the issues found during QA.
Spec: ${SPEC_FILE}
EOF

    python3 "${SCRIPT_DIR}/notify.py" "$PROJECT_ID" "QA FAILED for ${SPEC_ID}. Bugs written to inbox." 2>/dev/null || true
    echo "[qa] FAILED: ${SPEC_ID} (exit=${QA_EXIT})"
fi
```

**Step 2: Verify**

```bash
chmod +x scripts/vps/qa-loop.sh

# Verify syntax
bash -n scripts/vps/qa-loop.sh
# Expected: no output (syntax OK)
```

**Acceptance Criteria:**
- [ ] Dispatches `/qa SPEC_ID` via Claude CLI
- [ ] QA PASS -> update phase to idle, notify topic
- [ ] QA FAIL -> write bug to inbox, notify topic, phase = qa_failed
- [ ] QA timeout: 600s (configurable via `QA_TIMEOUT`)
- [ ] Sets proper env vars (CLAUDE_PROJECT_DIR, CONFIG_DIR)
- [ ] File < 400 LOC

---

### Task 9: Setup + systemd + Config Templates

**Files:**
- Create: `scripts/vps/setup-vps.sh`
- Create: `scripts/vps/projects.json.example`
- Create: `scripts/vps/.env.example`

**Context:**
One-command VPS bootstrap. Validates all prerequisites (Devil traps), initializes SQLite, creates Pueue groups, configures callback, installs systemd units. Config templates for user customization.

**Step 1: Create .env.example**

```bash
# scripts/vps/.env.example
# DLD Multi-Project Orchestrator environment config
# Copy to .env and fill in values: cp .env.example .env

# Telegram Bot
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ALLOWED_USERS=123456789

# Paths
DB_PATH=/home/ubuntu/scripts/vps/orchestrator.db
PROJECTS_JSON=/home/ubuntu/scripts/vps/projects.json

# Orchestrator
POLL_INTERVAL=300
QA_TIMEOUT=600

# Provider binaries
CLAUDE_PATH=/home/ubuntu/.claude/local/claude
CODEX_PATH=/usr/local/bin/codex
```

**Step 2: Create projects.json.example**

```json
[
  {
    "project_id": "saas-app",
    "path": "/home/ubuntu/projects/saas-app",
    "topic_id": 5,
    "provider": "claude",
    "auto_approve_timeout": 30
  },
  {
    "project_id": "side-project",
    "path": "/home/ubuntu/projects/side-project",
    "topic_id": 8,
    "provider": "claude",
    "auto_approve_timeout": 0
  }
]
```

**Step 3: Create setup-vps.sh**

```bash
#!/usr/bin/env bash
# scripts/vps/setup-vps.sh
# One-command VPS bootstrap for DLD Multi-Project Orchestrator.
# Usage: bash setup-vps.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

echo "=== DLD Multi-Project Orchestrator Setup ==="
echo ""

# ── Pre-flight checks ──────────────────────────────────
echo "--- Pre-flight checks ---"

# DA-1: loginctl enable-linger (pueued survives SSH disconnect)
if command -v loginctl &>/dev/null; then
    loginctl enable-linger "$(whoami)" 2>/dev/null && ok "loginctl enable-linger" || warn "loginctl enable-linger failed (may need sudo)"
else
    warn "loginctl not found (non-systemd system?)"
fi

# Python 3.12+
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if python3 -c "import sys; assert sys.version_info >= (3, 12)"; then
        ok "Python ${PY_VERSION}"
    else
        fail "Python 3.12+ required, found ${PY_VERSION}"
    fi
else
    fail "python3 not found"
fi

# sqlite3
if command -v sqlite3 &>/dev/null; then
    ok "sqlite3 $(sqlite3 --version | head -1)"
else
    fail "sqlite3 not found. Install: apt install sqlite3"
fi

# jq
if command -v jq &>/dev/null; then
    ok "jq $(jq --version)"
else
    fail "jq not found. Install: apt install jq"
fi

# git
if command -v git &>/dev/null; then
    ok "git $(git --version)"
else
    fail "git not found"
fi

echo ""
echo "--- Python dependencies ---"

# Create venv if not exists
if [[ ! -d "${SCRIPT_DIR}/venv" ]]; then
    python3 -m venv "${SCRIPT_DIR}/venv"
    ok "Created Python venv"
fi

# DA-2: Install PTB v21.9+ (NOT v22.0 — breaking changes)
"${SCRIPT_DIR}/venv/bin/pip" install -r "${SCRIPT_DIR}/requirements.txt" --quiet
ok "Python requirements installed"

echo ""
echo "--- Pueue setup ---"

# DA-6: Install Pueue if not present
if ! command -v pueue &>/dev/null; then
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64)  PUEUE_ARCH="x86_64-unknown-linux-musl" ;;
        aarch64) PUEUE_ARCH="aarch64-unknown-linux-musl" ;;
        *)       fail "Unsupported architecture: ${ARCH}" ;;
    esac
    PUEUE_VERSION="4.0.4"
    PUEUE_URL="https://github.com/Nukesor/pueue/releases/download/v${PUEUE_VERSION}/pueue-${PUEUE_ARCH}"
    PUEUED_URL="https://github.com/Nukesor/pueue/releases/download/v${PUEUE_VERSION}/pueued-${PUEUE_ARCH}"

    echo "Downloading Pueue v${PUEUE_VERSION} for ${ARCH}..."
    curl -fsSL "$PUEUE_URL" -o /usr/local/bin/pueue || curl -fsSL "$PUEUE_URL" -o "${HOME}/.local/bin/pueue"
    curl -fsSL "$PUEUED_URL" -o /usr/local/bin/pueued || curl -fsSL "$PUEUED_URL" -o "${HOME}/.local/bin/pueued"
    chmod +x /usr/local/bin/pueue /usr/local/bin/pueued 2>/dev/null || chmod +x "${HOME}/.local/bin/pueue" "${HOME}/.local/bin/pueued"
    ok "Pueue v${PUEUE_VERSION} installed"
else
    ok "pueue found: $(pueue --version 2>/dev/null || echo 'unknown')"
fi

# Start pueued if not running
if ! pueue status &>/dev/null; then
    pueued --daemonize 2>/dev/null || true
    sleep 1
    ok "pueued started"
else
    ok "pueued already running"
fi

# Create groups
pueue group add claude-runner 2>/dev/null || true
pueue group add codex-runner 2>/dev/null || true
pueue parallel 2 --group claude-runner 2>/dev/null || true
pueue parallel 1 --group codex-runner 2>/dev/null || true
ok "Pueue groups configured (claude-runner=2, codex-runner=1)"

# Configure callback
PUEUE_CONFIG_DIR="${HOME}/.config/pueue"
mkdir -p "$PUEUE_CONFIG_DIR"
PUEUE_CONFIG="${PUEUE_CONFIG_DIR}/pueue.yml"

# Write callback config (preserves existing settings)
if [[ -f "$PUEUE_CONFIG" ]]; then
    # Update callback line
    if grep -q "callback:" "$PUEUE_CONFIG"; then
        sed -i "s|callback:.*|callback: \"${SCRIPT_DIR}/pueue-callback.sh {{ id }} '{{ label }}' '{{ group }}' '{{ result }}'\"|" "$PUEUE_CONFIG"
    else
        echo "  callback: \"${SCRIPT_DIR}/pueue-callback.sh {{ id }} '{{ label }}' '{{ group }}' '{{ result }}'\"" >> "$PUEUE_CONFIG"
    fi
else
    cat > "$PUEUE_CONFIG" << EOF
---
client:
  restart_in_place: false
  read_local_logs: true
  show_confirmation_questions: false
  show_expanded_aliases: false
  dark_mode: false
  max_status_lines: null
  status_time_format: "%H:%M:%S"
  status_datetime_format: "%Y-%m-%d\n%H:%M:%S"
daemon:
  default_parallel_tasks: 1
  pause_group_on_failure: false
  pause_all_on_failure: false
  callback: "${SCRIPT_DIR}/pueue-callback.sh {{ id }} '{{ label }}' '{{ group }}' '{{ result }}'"
  callback_log_lines: 10
shared:
  use_unix_socket: true
  host: "127.0.0.1"
  port: "6924"
EOF
fi
ok "Pueue callback configured"

echo ""
echo "--- SQLite setup ---"

# Initialize database
DB_PATH="${DB_PATH:-${SCRIPT_DIR}/orchestrator.db}"
sqlite3 "$DB_PATH" < "${SCRIPT_DIR}/schema.sql"
ok "SQLite database initialized: ${DB_PATH}"

echo ""
echo "--- Make scripts executable ---"
chmod +x "${SCRIPT_DIR}"/*.sh "${SCRIPT_DIR}"/*.py 2>/dev/null || true
ok "Scripts made executable"

echo ""
echo "--- Environment check ---"
if [[ ! -f "${SCRIPT_DIR}/.env" ]]; then
    warn ".env not found. Copy from template:"
    echo "  cp ${SCRIPT_DIR}/.env.example ${SCRIPT_DIR}/.env"
    echo "  # Then edit and fill in TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID"
else
    ok ".env exists"
fi

if [[ ! -f "${SCRIPT_DIR}/projects.json" ]]; then
    warn "projects.json not found. Copy from template:"
    echo "  cp ${SCRIPT_DIR}/projects.json.example ${SCRIPT_DIR}/projects.json"
    echo "  # Then edit with your project paths and topic IDs"
else
    ok "projects.json exists"
fi

# DA-9: Verify Claude CLI
if command -v claude &>/dev/null || [[ -f "${CLAUDE_PATH:-}" ]]; then
    ok "Claude CLI found"
else
    warn "Claude CLI not found. Set CLAUDE_PATH in .env"
fi

echo ""
echo "--- systemd units ---"

# Install systemd user units
SYSTEMD_DIR="${HOME}/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"

cat > "${SYSTEMD_DIR}/dld-orchestrator.service" << EOF
[Unit]
Description=DLD Multi-Project Orchestrator
After=network.target

[Service]
Type=simple
ExecStart=${SCRIPT_DIR}/orchestrator.sh
WorkingDirectory=${SCRIPT_DIR}
EnvironmentFile=${SCRIPT_DIR}/.env
MemoryMax=27G
MemorySwapMax=0
KillMode=control-group
Restart=on-failure
RestartSec=30
StartLimitIntervalSec=300
StartLimitBurst=3
StandardOutput=journal
StandardError=journal
SyslogIdentifier=dld-orchestrator

[Install]
WantedBy=default.target
EOF

cat > "${SYSTEMD_DIR}/dld-telegram-bot.service" << EOF
[Unit]
Description=DLD Telegram Bot
After=network.target

[Service]
Type=simple
ExecStart=${SCRIPT_DIR}/venv/bin/python ${SCRIPT_DIR}/telegram-bot.py
WorkingDirectory=${SCRIPT_DIR}
EnvironmentFile=${SCRIPT_DIR}/.env
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=dld-bot

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
ok "systemd units installed"

echo ""
echo "--- Enable services ---"
echo "  systemctl --user enable --now dld-orchestrator"
echo "  systemctl --user enable --now dld-telegram-bot"
echo ""
echo "--- Check status ---"
echo "  systemctl --user status dld-orchestrator"
echo "  systemctl --user status dld-telegram-bot"
echo "  journalctl --user -u dld-orchestrator -f"
echo ""
echo -e "${GREEN}=== Setup complete ===${NC}"
```

**Step 4: Verify**

```bash
chmod +x scripts/vps/setup-vps.sh

# Verify syntax
bash -n scripts/vps/setup-vps.sh
# Expected: no output (syntax OK)

# Verify JSON example is valid
python3 -c "import json; json.load(open('scripts/vps/projects.json.example')); print('OK')"
# Expected: OK
```

**Acceptance Criteria:**
- [ ] Pre-flight checks: loginctl, Python 3.12, sqlite3, jq, git
- [ ] PTB v21.9+ installed (not v22.0)
- [ ] Pueue v4.0.4 installed with arch detection (x86_64/aarch64)
- [ ] Pueue groups + parallelism + callback configured
- [ ] SQLite schema initialized
- [ ] systemd user units installed (orchestrator + bot)
- [ ] `.env.example` and `projects.json.example` created
- [ ] File < 400 LOC

---

### Task 10: autopilot-loop.sh PROJECT_DIR Support

**Files:**
- Modify: `scripts/autopilot-loop.sh` (lines 14-15, 51)

**Context:**
Minimal change to existing script. Adds `PROJECT_DIR` env var support so the orchestrator can run autopilot-loop.sh for any project directory, not just the current working directory. Must maintain backward compatibility.

**Step 1: Modify path variables to support PROJECT_DIR**

In `scripts/autopilot-loop.sh`, change the hardcoded paths at lines 14-15:

Replace:
```bash
BACKLOG_FILE="ai/backlog.md"
PROGRESS_FILE="ai/diary/autopilot-progress.md"
```

With:
```bash
# Support PROJECT_DIR env var for multi-project orchestration
# Falls back to relative paths for backward compatibility
BASE_DIR="${PROJECT_DIR:-.}"
BACKLOG_FILE="${BASE_DIR}/ai/backlog.md"
PROGRESS_FILE="${BASE_DIR}/ai/diary/autopilot-progress.md"
```

**Step 2: Verify**

```bash
# Verify backward compat (no PROJECT_DIR set)
unset PROJECT_DIR
bash -n scripts/autopilot-loop.sh
scripts/autopilot-loop.sh --check 2>/dev/null || true
# Expected: works as before (looks at ./ai/backlog.md)

# Verify with PROJECT_DIR
export PROJECT_DIR=/tmp/test-project
mkdir -p /tmp/test-project/ai
echo "| FTR-001 | test | queued |" > /tmp/test-project/ai/backlog.md
scripts/autopilot-loop.sh --check 2>/dev/null || true
# Expected: finds FTR-001 in /tmp/test-project/ai/backlog.md
```

**Acceptance Criteria:**
- [ ] Reads `PROJECT_DIR` env var; if set, uses `$PROJECT_DIR/ai/backlog.md`
- [ ] Falls back to relative `ai/backlog.md` if `PROJECT_DIR` not set
- [ ] Same for `ai/diary/` path
- [ ] `--check` mode still works
- [ ] No behavior change when `PROJECT_DIR` is unset

---

### Execution Order

```
Task 1 (schema+db) → Task 2 (runners) → Task 3 (pueue callback)
                                            ↓
                    Task 10 (autopilot-loop) → Task 6 (orchestrator)
                                                     ↓
                              Task 4 (bot core) → Task 5 (inbox processor)
                                                     ↓
                                              Task 7 (auto-approve)
                                                     ↓
                                              Task 8 (QA dispatch)
                                                     ↓
                                              Task 9 (setup + systemd)
```

**Day 1 gate:** Tasks 1-3 + 10: `pueue add -- run-agent.sh ~/project "test task" claude` works
**Day 2 gate:** Tasks 4-5 + 6: `/status` responds in Telegram with project state
**Day 3 gate:** Tasks 7-9: auto-approve timer fires, QA dispatches after autopilot

### Dependencies

- Task 2 depends on Task 1 (runners call db_exec.sh indirectly via callback)
- Task 3 depends on Task 1 (callback uses db_exec.sh) and Task 2 (callback references run-agent.sh label format)
- Task 5 depends on Task 1 (inbox-processor uses db_exec.sh) and Task 2 (submits to Pueue via run-agent.sh)
- Task 6 depends on Tasks 1, 2, 5 (orchestrator calls inbox-processor, submits to Pueue, queries DB)
- Task 4 depends on Task 1 (bot queries SQLite via db.py)
- Task 7 depends on Task 4 (adds to telegram-bot.py)
- Task 8 depends on Tasks 1, 4 (QA uses db_exec.sh, notify.py)
- Task 9 depends on ALL previous tasks (setup script references all files)
- Task 10 is independent (modifies existing file, no VPS dependencies)
- Task 11 depends on Task 10 (syncs the autopilot-loop.sh change to template)

---

### Task 11: Sync autopilot-loop.sh to template (AUTO-GENERATED)

**Type:** sync
**Files:**
- sync: `template/scripts/autopilot-loop.sh` <-- `scripts/autopilot-loop.sh`

**Context:**
`scripts/autopilot-loop.sh` is in a sync zone (`scripts/`). The `PROJECT_DIR` support from Task 10 is a universal improvement (benefits all DLD users, not DLD-specific). Per template-sync rule, changes must be synced to template.

**Steps:**

```bash
cp scripts/autopilot-loop.sh template/scripts/autopilot-loop.sh
```

**Acceptance:**
- [ ] `diff scripts/autopilot-loop.sh template/scripts/autopilot-loop.sh` = empty

---

## Flow Coverage Matrix

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | Founder sends text in project topic | Task 4 | ✓ |
| 2 | Bot routes message by topic_id → project | Task 4 | ✓ |
| 3 | Bot saves to ai/inbox/ with metadata | Task 4 | ✓ |
| 4 | Keyword routing determines skill | Task 5 | ✓ |
| 5 | Inbox processor dispatches to skill | Task 5 | ✓ |
| 6 | Spark summary displayed in topic | Task 7 | ✓ |
| 7 | Auto-approve countdown with Cancel/Approve | Task 7 | ✓ |
| 8 | Task submitted to Pueue | Task 6 | ✓ |
| 9 | run-agent.sh dispatches to provider | Task 2 | ✓ |
| 10 | Claude/Codex executes task | Task 2 | ✓ |
| 11 | pueue-callback releases slot + notifies | Task 3 | ✓ |
| 12 | QA dispatched after autopilot | Task 8 | ✓ |
| 13 | QA fail → bugs to inbox → cycle repeats | Task 8 | ✓ |
| 14 | Local spark → git push → VDS picks up | Task 6 (git pull) | ✓ |
| 15 | /status shows project state | Task 4 | ✓ |
| 16 | /run triggers immediate cycle | Task 4, 6 | ✓ |
| 17 | /pause stops project queue | Task 4 | ✓ |
| 18 | /resume resumes project queue | Task 4 | ✓ |
| 19 | Spark self-escalation to architect | Task 5 (fallback) | ✓ |
| 20 | Architect route from inbox | Task 5 | ✓ |

**GAPS:** None

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | pueued survives SSH disconnect | Start pueued, close SSH, reopen | `pueue status` returns OK | deterministic | devil DA-1 | P0 |
| EC-2 | PTB installs correctly | `pip install -r requirements.txt` | No "no matching distribution" error | deterministic | devil DA-2 | P0 |
| EC-3 | SQLite busy_timeout prevents lock errors | Two processes write simultaneously via db_exec.sh | No "database is locked" — waits up to 5s | deterministic | devil DA-3 | P0 |
| EC-4 | General topic routing safe | Bot receives msg in General (thread_id=1) | Routes to general handler, no crash | deterministic | devil DA-4 | P0 |
| EC-5 | Bot handles 409 on restart | Kill bot, restart within 10s | Bot starts, no silent command drops | deterministic | devil DA-5 | P1 |
| EC-6 | /status with empty DB | Bot starts, no projects in SQLite | Returns "No projects configured" | deterministic | devil DA-7 | P1 |
| EC-7 | Stale slot recovery on Claude crash | Claude exits code 1, Pueue marks Failed | pueue-callback releases slot in SQLite | deterministic | devil DA-8 | P0 |
| EC-8 | CONFIG_DIR created before Claude | run-agent.sh invoked for new project | `$config_dir` exists before claude command | deterministic | devil DA-9 | P1 |
| EC-9 | Keyword routing: architect | "спроектируй систему нотификаций" | `detect_route()` returns "architect" | deterministic | user requirement | P0 |
| EC-10 | Keyword routing: default spark | "добавь кнопку логина" | `detect_route()` returns "spark" | deterministic | user requirement | P0 |
| EC-11 | Keyword routing: bug | "не работает авторизация" | `detect_route()` returns "spark_bug" | deterministic | user requirement | P0 |
| EC-12 | Keyword routing: bughunt | "много багов, всё сломалось после обновления" | `detect_route()` returns "bughunt" | deterministic | user requirement | P0 |
| EC-13 | git pull picks up new spec | Spec pushed to develop, orchestrator runs | Spec found in backlog, task created | deterministic | user requirement | P0 |
| EC-14 | Auto-approve timer fires | Spec ready, no cancel within timeout | Task submitted to Pueue after timeout | deterministic | user requirement | P0 |
| EC-15 | Cancel stops auto-approve | Press Cancel button within timeout | Job removed, message updated "Cancelled" | deterministic | user requirement | P0 |
| EC-16 | QA dispatched after autopilot | Pueue task completes with Success | `/qa` skill invoked for spec | deterministic | user requirement | P1 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-17 | Pueue group claude-runner parallel=2 | Add 3 tasks | Only 2 run, 1 queued | integration | devil SA-1 | P0 |
| EC-18 | Bot + SQLite + Pueue running | `/status saas-app` in Telegram | Formatted response with phase, current_task, slot info | integration | user requirement | P0 |
| EC-19 | Full pipeline | Send text in topic → wait | Spec created, autopilot ran, QA checked, notification received | integration | user requirement | P0 |
| EC-20 | systemd restart | `kill -9 <orchestrator_pid>` | Service restarts within 30s | integration | devil SA-3 | P1 |
| EC-21 | Auth whitelist | Message from non-allowed user_id | Silently ignored, no error sent | integration | devil SA-4 | P0 |

### Coverage Summary

- Deterministic: 16 | Integration: 5 | LLM-Judge: 0 | Total: 21

### TDD Order

1. EC-1 (pueued survives) → EC-2 (pip install) → EC-3 (SQLite) — pre-flight
2. EC-9, EC-10, EC-11 (keyword routing) — pure function, easy to test first
3. EC-6, EC-4 (empty DB, General topic) — bot edge cases
4. EC-7 (stale slot) → EC-16 (parallelism) — Pueue integration
5. EC-12, EC-13, EC-14 (git pull, auto-approve) — orchestrator flow
6. EC-17, EC-18 (full pipeline) — end-to-end last

---

## Acceptance Verification (MANDATORY)

### Smoke Checks (process alive)

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | pueued running | `pueue status` | Shows groups: claude-runner, codex-runner | 5s |
| AV-S2 | SQLite schema valid | `sqlite3 orchestrator.db ".tables"` | project_state, compute_slots, task_log | 5s |
| AV-S3 | Telegram bot responds | Send `/status` in Telegram | Bot replies within 10s | 15s |
| AV-S4 | Orchestrator service running | `systemctl is-active dld-orchestrator` | active | 5s |
| AV-S5 | Bot service running | `systemctl is-active dld-telegram-bot` | active | 5s |

### Functional Checks (business logic)

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | /status shows project | Seed 1 project in DB | `/status` in Telegram | Shows project with phase=idle |
| AV-F2 | Message routes to inbox | Send text in project topic | File appears in `{project}/ai/inbox/` | File with metadata + keyword route |
| AV-F3 | Pueue task submission | Write queued spec to backlog | Trigger orchestrator cycle | Task visible in `pueue status` |
| AV-F4 | Slot released on completion | Let Pueue task finish | Check SQLite slots | Slot has project_id=NULL |

### Verify Command (copy-paste ready)

```bash
# Smoke
pueue status
sqlite3 /home/ubuntu/scripts/vps/orchestrator.db ".tables"
systemctl is-active dld-orchestrator
systemctl is-active dld-telegram-bot
# Send /status in Telegram and verify response

# Functional — seed a test project
sqlite3 /home/ubuntu/scripts/vps/orchestrator.db \
  "INSERT OR REPLACE INTO project_state (project_id, path, topic_id, provider) \
   VALUES ('test-project', '/home/ubuntu/projects/test', NULL, 'claude');"
# Send /status in Telegram → should show test-project

# Verify pueue callback
pueue add --group claude-runner --label "test:EC-TEST" -- echo "hello world"
sleep 2
sqlite3 /home/ubuntu/scripts/vps/orchestrator.db \
  "SELECT * FROM task_log WHERE task_label='test:EC-TEST';"
# Should show status=Success
```

### Post-Deploy URL

```
DEPLOY_URL=local-only (VPS SSH access required)
```

---

## Definition of Done

### Functional
- [ ] All 11 tasks from Implementation Plan completed
- [ ] Telegram bot responds to /status with project state from SQLite
- [ ] Message in project topic → saved to ai/inbox/ with keyword route
- [ ] Orchestrator git pull picks up specs pushed from local machine
- [ ] Auto-approve timer fires and submits to Pueue
- [ ] QA dispatched via /qa skill after autopilot completion
- [ ] Keyword routing correctly dispatches spark/architect/council/bughunt

### Tests
- [ ] All 21 eval criteria pass
- [ ] Pre-flight checklist (EC-1, EC-2, EC-3) all green

### Acceptance Verification
- [ ] All Smoke checks (AV-S1 through AV-S5) pass
- [ ] All Functional checks (AV-F1 through AV-F4) pass
- [ ] Verify Command runs without errors

### Technical
- [ ] All scripts < 400 LOC
- [ ] systemd services start and survive reboot
- [ ] pueued survives SSH disconnect (loginctl enable-linger)

---

## Autopilot Log

[Auto-populated by autopilot during execution]
