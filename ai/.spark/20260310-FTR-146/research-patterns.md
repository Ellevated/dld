# Pattern Research — Multi-Project Orchestrator Phase 1

## Pattern 1: CCBot — Claude Code + Telegram Integration

**Source:** [RichardAtCT/claude-code-telegram](https://github.com/RichardAtCT/claude-code-telegram) (2K stars, Python, MIT)

### Description
Wrap Claude Code CLI in a Python subprocess, parse its JSON output (`--output-format json`), and persist the returned `session_id` to resume conversations. The Telegram bot acts as a thin routing layer: every message goes to `ClaudeIntegration.run_command()`, which invokes `claude -p "$prompt" --resume $session_id --output-format json`, then stores the new session_id for the next turn.

### How Session Continuity Works
```python
# Pattern from openclaw-prompts-and-skills/telegram-claude-poc.py
cmd = [
    "claude", "-p", message,
    "--output-format", "json",
    "--allowedTools", "Read,Write,Edit,Bash,Glob,Grep,WebFetch,WebSearch"
]
if session_id:
    cmd += ["--resume", session_id]

result = subprocess.run(cmd, capture_output=True, text=True, timeout=None)
response = json.loads(result.stdout)
result_text = response.get("result", "")
new_session_id = response.get("session_id", "")   # <- persist this
```

### Output Parsing
`claude --output-format json` returns a single JSON object on stdout:
```json
{
  "result": "text of final response",
  "session_id": "abc123def456",
  "is_error": false,
  "cost_usd": 0.0042
}
```
For streaming: `--output-format stream-json` emits newline-delimited JSON frames; parse each line individually.

### Pros
- Session IDs come from Claude itself — no custom UUID generation
- `--resume` handles multi-turn conversation natively; no need to replay history
- `subprocess.run()` with `capture_output=True` is dead simple; timeout is a single param
- `--allowedTools` restricts blast radius per invocation
- Already battle-tested: 2K-star production repo, 20 contributors

### Cons
- Blocking subprocess — must run in thread pool or async executor (not raw `asyncio.create_subprocess_exec`) to avoid blocking the event loop
- stdout buffer can grow large for long tasks (streaming mitigates this)
- `session_id` is opaque; if Claude process crashes, the session is orphaned (need cleanup job)
- No native progress reporting — user sees nothing until final response (typing indicator + periodic heartbeat helps)

### Complexity
**Estimate:** Easy — 4-8 hours for the bot-to-Claude bridge

**Why:** The pattern is fully solved. The only custom work is the routing layer (which message goes to which project's session) and the SQLite session store. The subprocess pattern is 10 lines.

### Real Implementation Reference
`src/claude/sdk_integration.py` in RichardAtCT/claude-code-telegram:
- `ClaudeSDKManager` wraps SDK (primary) with CLI subprocess fallback
- Session IDs stored per (user_id, project_dir) in SQLite
- `asyncio.get_event_loop().run_in_executor(None, subprocess.run, ...)` for non-blocking execution

---

## Pattern 2: Pueue — Group-Based Job Queue with JSON Status

**Source:** [Nukesor/pueue](https://github.com/Nukesor/pueue) (4.6K stars, Rust, MIT)

### Description
Pueue daemon (`pueued`) manages a persistent queue of shell commands. Tasks are organized into named groups, each with a configurable parallelism limit. `pueue status --json` emits structured JSON that Python can parse. Groups map 1:1 to projects in our architecture.

### Group Management
```bash
# Create groups at orchestrator startup (idempotent)
pueue group add saas-app   2>/dev/null || true
pueue group add dld        2>/dev/null || true
pueue group add side-proj  2>/dev/null || true

# Set parallelism: 1 task per project at a time
pueue parallel --group saas-app 1
pueue parallel --group dld 1

# Submit a task to a specific group
pueue add --group saas-app \
    --label "FTR-146-autopilot" \
    -- /home/ubuntu/scripts/vps/run-agent.sh /home/ubuntu/projects/saas-app "implement FTR-146" claude
```

### JSON Status Parsing in Python
```python
import subprocess
import json

def get_pueue_status() -> dict:
    result = subprocess.run(
        ["pueue", "status", "--json"],
        capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    # Schema: {"tasks": {id: {status, command, label, group, ...}}, "groups": {...}}
    return data

def get_project_tasks(project_id: str) -> list[dict]:
    data = get_pueue_status()
    return [
        task for task in data["tasks"].values()
        if task.get("group") == project_id
    ]

# Task status values: "Running" | "Queued" | "Paused" | "Success" | "Failed" | "Stashed"
def is_project_running(project_id: str) -> bool:
    tasks = get_project_tasks(project_id)
    return any(t["status"] == "Running" for t in tasks)
```

### Wait for Completion Pattern
```bash
# Pueue has a native wait command — no polling loop needed
pueue wait --group saas-app   # blocks until all tasks in group finish
# Or wait for specific task ID:
pueue wait 42
```

### Pause/Resume a Project
```bash
pueue pause --group saas-app    # pauses all tasks in group
pueue start --group saas-app    # resumes
pueue kill --group saas-app     # kills running task, clears queue
```

### Pros
- Handles concurrency limits, persistence through reboots, and restart-on-failure natively
- `pueue status --json` is the single source of truth — no custom state machine
- `pueue wait` eliminates polling loops
- Group pause/resume maps directly to Telegram `/pause saas-app` and `/run saas-app` commands
- Ships as a single binary; no language runtime dependency

### Cons
- `pueue status --json` schema can change between versions (pin `pueue` binary version)
- No native webhook/callback when a task completes — must poll or use Pueue's `callback` hook
- Pueue's callback is a shell command, not a Python callback — requires a small bridge script
- Groups must be pre-created; adding a new project at runtime requires calling `pueue group add`

### Completion Hook (Bridge to SQLite + Telegram)
```bash
# ~/.config/pueue/pueue.yml
callback: "/home/ubuntu/scripts/vps/pueue-callback.sh {{id}} {{name}} {{group}} {{result}}"
```
```bash
#!/usr/bin/env bash
# pueue-callback.sh — called by pueued on task completion
TASK_ID="$1"; LABEL="$2"; GROUP="$3"; RESULT="$4"

# Update SQLite
sqlite3 /var/orchestrator/orchestrator.db \
    "UPDATE project_state SET phase='idle', current_task=NULL
     WHERE project_id='$GROUP';"

# Notify via bot
python3 /home/ubuntu/scripts/vps/notify.py \
    --project "$GROUP" \
    --result "$RESULT" \
    --task-label "$LABEL"
```

### Complexity
**Estimate:** Easy — 2-4 hours for group setup + JSON parsing + callback hook

**Why:** All the hard parts (concurrency, persistence, restart) are solved. Custom work is the callback bridge and the Python status query functions.

---

## Pattern 3: Telegram Forum Topics — message_thread_id Routing

**Source:** [python-telegram-bot v22 docs](https://docs.python-telegram-bot.org/en/v22.1/) + [PR #4170 — reply to same thread by default](https://github.com/python-telegram-bot/python-telegram-bot/pull/4170)

### Description
Telegram Forum Supergroups expose `message_thread_id` on every incoming Update. This integer is the topic ID. A bot stores a mapping of `{topic_id: project_id}` and routes all messages accordingly. Replies back to the correct topic require passing `message_thread_id` to `send_message`. Since PTB v21 (PR #4170), `message.reply_text()` preserves `message_thread_id` automatically.

### Enable Topics
1. Convert group to supergroup (Settings → Manage group → Topics → Enable)
2. Bot must have `can_manage_topics` admin right to create topics programmatically

### Routing Pattern
```python
from telegram import Update
from telegram.ext import ContextTypes

# In-memory or SQLite: {topic_id (int): project_id (str)}
TOPIC_TO_PROJECT: dict[int, str] = {}

async def route_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thread_id = update.message.message_thread_id
    if thread_id is None:
        # Message in General topic — treat as global command
        await handle_general_command(update, context)
        return

    project_id = TOPIC_TO_PROJECT.get(thread_id)
    if project_id is None:
        await update.message.reply_text("Unknown topic. Use /addproject to register.")
        return

    await handle_project_message(update, context, project_id)
```

### Creating a Topic (for /addproject)
```python
async def create_project_topic(bot, chat_id: int, project_name: str) -> int:
    """Creates a forum topic and returns its message_thread_id."""
    forum_topic = await bot.create_forum_topic(
        chat_id=chat_id,
        name=project_name,
        # icon_color: one of 7322096, 16766590, 13338331, 9367192, 16749490, 16478047
    )
    return forum_topic.message_thread_id  # store this as the routing key

# Then send to that topic:
await bot.send_message(
    chat_id=chat_id,
    text="Project registered. Tasks will appear here.",
    message_thread_id=forum_topic.message_thread_id
)
```

### Sending Status Updates to the Right Topic
```python
async def notify_project(bot, chat_id: int, project_id: str, text: str):
    """Looks up topic_id and sends message there."""
    # topic_id loaded from SQLite: SELECT topic_id FROM project_state WHERE project_id=?
    topic_id = get_topic_id_from_db(project_id)
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        message_thread_id=topic_id,
        parse_mode="HTML"
    )
```

### Key Gotchas (from production issues)
1. **Rate limit is global, not per-topic**: 30 msg/sec for the entire bot. Burst across many topics hits 429.
2. **topic_id = 0 is the General topic** — never use 0 as a project routing key.
3. `create_forum_topic` requires bot to be admin with `can_manage_topics` right.
4. Topic IDs are stable: they survive bot restarts. Store them once in SQLite.
5. PTB v21+: `message.reply_text()` auto-passes `message_thread_id`. PTB v20: pass it manually.

### Pros
- Single Telegram supergroup = one chat_id to manage (no juggling multiple groups)
- Each project gets a visually isolated space in the Telegram UI
- `message_thread_id` is a durable, stable routing key
- `bot.create_forum_topic()` automates project setup from `/addproject` command

### Cons
- Bot must have admin rights (`can_manage_topics`) to create topics
- Cold start: need to rebuild `{topic_id: project_id}` map from SQLite on bot restart
- Max ~250 open topics before Telegram client UX degrades (not a constraint for 2-5 projects)
- No way to move a topic between groups after creation

### Complexity
**Estimate:** Medium — 6-10 hours (includes topic creation, routing table, PTB handler wiring)

**Why:** The Telegram API part is well-documented. Complexity is in the routing table + persistent storage sync + edge cases (bot removed from admin, topic manually deleted, etc.).

---

## Pattern 4: SQLite WAL — Daemon State + Slot Acquisition

**Source:** [Zylos Research: SQLite WAL Mode for AI Agent Systems](https://zylos.ai/research/2026-02-20-sqlite-wal-mode-ai-agent-systems) + [DOCSAID: SQLite WAL Busy Timeout](https://docsaid.org/en/blog/sqlite-wal-busy-timeout-for-workers)

### Description
SQLite in WAL mode allows concurrent readers without blocking writers. For an orchestrator with a Python bot process + bash daemon process + Pueue callbacks, all writing to the same `orchestrator.db`, the key primitives are:
1. `PRAGMA journal_mode = WAL` — set once at DB creation
2. `PRAGMA busy_timeout = 5000` — wait up to 5s before returning SQLITE_BUSY (not LOCKED)
3. `BEGIN IMMEDIATE` for slot acquisition — locks the write slot atomically

### Python Connection Setup
```python
import sqlite3
from contextlib import contextmanager

DB_PATH = "/var/orchestrator/orchestrator.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=5.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()

# Using aiosqlite for async bot process:
import aiosqlite

async def get_project_state(project_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=5000")
        async with db.execute(
            "SELECT * FROM project_state WHERE project_id = ?", (project_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
```

### Slot Acquisition (Atomic — replaces flock)
```python
def try_acquire_slot(conn, project_id: str, pid: int, provider: str = "claude") -> int | None:
    """
    Returns slot_number if acquired, None if no slot available.
    Uses BEGIN IMMEDIATE to lock out other writers during the check-then-update.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        cursor = conn.execute(
            """
            UPDATE compute_slots
            SET project_id = ?, acquired_at = strftime('%Y-%m-%dT%H:%M:%SZ','now'), pid = ?
            WHERE slot_number = (
                SELECT slot_number FROM compute_slots
                WHERE project_id IS NULL AND provider = ?
                ORDER BY slot_number LIMIT 1
            ) AND project_id IS NULL
            RETURNING slot_number
            """,
            (project_id, pid, provider)
        )
        row = cursor.fetchone()
        conn.execute("COMMIT")
        return row[0] if row else None
    except Exception:
        conn.execute("ROLLBACK")
        raise

def release_slot(conn, project_id: str):
    conn.execute(
        "UPDATE compute_slots SET project_id=NULL, acquired_at=NULL, pid=NULL WHERE project_id=?",
        (project_id,)
    )
    conn.commit()
```

### Key WAL Gotchas
- `SQLITE_BUSY` (can retry) vs `SQLITE_LOCKED` (same process, different connection — usually a bug)
- Never open two connections to the same WAL DB from the same process without `check_same_thread=False`
- `busy_timeout` only applies to `SQLITE_BUSY` — `SQLITE_LOCKED` raises immediately regardless
- WAL checkpoint can stall if a long-running read transaction holds open the WAL file. Set `wal_autocheckpoint = 1000` (default) and monitor WAL file size.

### Pros
- Concurrent reads during writes (bot reads status while daemon writes)
- `BEGIN IMMEDIATE` slot acquisition is ACID and race-free — no external locking (flock) needed
- `sqlite3` ships with every Linux/Python — zero new dependencies
- SQLite WAL is the most deployed DB in history; operationally boring
- `PRAGMA integrity_check` for nightly health verification

### Cons
- Single write lock: high-frequency concurrent writes (>100/sec) degrade. Not a concern at orchestrator frequency (write per task start/finish, ~once per minute).
- WAL files (`-wal`, `-shm`) must be included in backups
- `isolation_level=None` (autocommit) requires explicit `BEGIN`/`COMMIT` for transactions — easy to forget

### Complexity
**Estimate:** Easy — 2-4 hours for schema creation + connection helper + slot acquisition

**Why:** Schema already designed in architectures.md. The Python patterns above are directly adaptable. The main risk is misunderstanding BUSY vs LOCKED, which the `busy_timeout` pragma resolves.

---

## Pattern 5: Auto-Approve with Timeout (Countdown + Cancel Button)

**Source:** [python-telegram-bot timerbot example](https://docs.python-telegram-bot.org/en/v22.1/examples.timerbot.html) + [Stack Overflow: edit message after expiration](https://stackoverflow.com/questions/74125542/automatically-edit-last-telegram-bot-message-after-expiration-period)

### Description
When the orchestrator picks a task from the inbox, it sends a summary message with an inline "Cancel" button and starts a countdown. After N seconds with no cancel, it proceeds automatically. The countdown is implemented with PTB's `JobQueue.run_once()` — the job fires after timeout and executes the task. The cancel button removes the job.

### Implementation Pattern
```python
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

AUTO_APPROVE_TIMEOUT = 30  # seconds

async def propose_task(update: Update, context: ContextTypes.DEFAULT_TYPE,
                       project_id: str, task_summary: str):
    """
    Sends a task proposal with auto-proceed countdown.
    User can cancel within AUTO_APPROVE_TIMEOUT seconds.
    """
    keyboard = [[InlineKeyboardButton("Cancel", callback_data=f"cancel:{project_id}")]]
    msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        message_thread_id=get_topic_id(project_id),  # send to correct topic
        text=(
            f"<b>Queuing task for {project_id}:</b>\n"
            f"{task_summary}\n\n"
            f"Proceeding in {AUTO_APPROVE_TIMEOUT}s unless cancelled."
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

    # Store msg_id + project in job context so we can edit it on timeout
    context.job_queue.run_once(
        callback=_execute_task_job,
        when=AUTO_APPROVE_TIMEOUT,
        data={
            "project_id": project_id,
            "task_summary": task_summary,
            "chat_id": msg.chat_id,
            "message_id": msg.message_id,
            "thread_id": get_topic_id(project_id),
        },
        name=f"auto_approve:{project_id}",  # name allows cancellation by name
    )

async def _execute_task_job(context: ContextTypes.DEFAULT_TYPE):
    """Called by JobQueue after timeout — timeout means approved."""
    data = context.job.data
    # Edit the message to remove the cancel button and confirm execution
    await context.bot.edit_message_text(
        chat_id=data["chat_id"],
        message_id=data["message_id"],
        text=(
            f"<b>Starting task for {data['project_id']}:</b>\n"
            f"{data['task_summary']}"
        ),
        parse_mode="HTML"
    )
    # Actually submit to Pueue
    submit_to_pueue(data["project_id"], data["task_summary"])

async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline button handler — cancels the pending job."""
    query = update.callback_query
    await query.answer()
    _, project_id = query.data.split(":", 1)

    # Cancel the pending job
    jobs = context.job_queue.get_jobs_by_name(f"auto_approve:{project_id}")
    for job in jobs:
        job.schedule_removal()

    await query.edit_message_text(
        text=f"Task for <b>{project_id}</b> cancelled.",
        parse_mode="HTML"
    )
```

### Countdown Display Variant (optional)
If you want a live countdown in the message (cosmetic only):
```python
async def _tick_countdown(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    remaining = data["remaining"] - 1
    if remaining <= 0:
        # Let the main job handle execution
        return
    data["remaining"] = remaining
    await context.bot.edit_message_text(
        chat_id=data["chat_id"],
        message_id=data["message_id"],
        text=f"... proceeding in {remaining}s ...",
        reply_markup=data["keyboard"],
        parse_mode="HTML"
    )
```

Note: Live countdown requires editing the message every second — hits Telegram's edit rate limit (1 edit per second per message). Use sparingly. A static "proceeding in 30s" is sufficient.

### Pros
- Entirely within PTB's JobQueue — no threads, no asyncio.sleep loops
- `job.schedule_removal()` is the single cancel call — clean
- Works across bot restarts IF using `PTBPersistence` (persists job queue to disk)
- Inline button UX is familiar and clear (no slash commands needed)

### Cons
- Job queue is in-memory by default; bot restart cancels all pending jobs
- Telegram rate limits on message edits: max 1 edit/second per message (for live countdown)
- Can't use the same `name` for two concurrent jobs for the same project (blocks parallel proposals for same project — which is desired behavior here anyway)

### Complexity
**Estimate:** Easy — 2-4 hours including cancel handler and Pueue submission

**Why:** PTB JobQueue handles all the async scheduling. The pattern is 50 lines. Persistence of pending jobs across restarts is the only non-trivial addition (another 1-2 hours).

---

## Pattern 6: Structured Logging to journald from Python/Bash

**Source:** [Andy's Thoughts: Structured Logging with Python and systemd Journald](https://denner.co/2025/01/26/logging3.html) + [smhk.net: Using structlog and journald](https://smhk.net/note/2023/11/structlog-and-journald/)

### Description
Two approaches: (A) `systemd-python` with `JournalHandler` — emits structured key=value fields that `journalctl` can filter; (B) JSON to stdout with `StandardOutput=journal` in the systemd unit — `journalctl` stores it as `MESSAGE` but it's searchable as text. Approach A is richer (native structured fields). Approach B requires no extra dependency (bash-friendly).

### Approach A: Python JournalHandler (structured fields)
```python
import logging
from systemd.journal import JournalHandler

logger = logging.getLogger("orchestrator")
logger.setLevel(logging.DEBUG)
logger.addHandler(JournalHandler())

# Log with custom structured fields (journalctl -F PROJECT_ID to filter)
logger.info(
    "Task started",
    extra={
        "PROJECT_ID": "saas-app",       # journald field — UPPERCASE required
        "TASK_LABEL": "FTR-146",
        "PROVIDER": "claude",
        "SLOT_NUMBER": 1,
    }
)

# Now filterable via:
# journalctl -u orchestrator TASK_LABEL=FTR-146
# journalctl -u orchestrator PROJECT_ID=saas-app -f
```

### Approach B: JSON to stdout (bash-native, simpler)
```bash
# In orchestrator.sh — pure bash, no Python dependency
log_json() {
    local level="$1" service="$2" message="$3"
    # Extra fields as key=value pairs: log_json info orchestrator "msg" project=saas-app task=FTR-146
    local extra_json="{"
    shift 3
    for kv in "$@"; do
        key="${kv%%=*}"
        val="${kv#*=}"
        extra_json+="\"$key\":\"$val\","
    done
    extra_json="${extra_json%,}}"
    printf '{"ts":"%s","level":"%s","service":"%s","msg":"%s","meta":%s}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$level" "$service" "$message" "$extra_json"
}

# Usage:
log_json "info" "orchestrator" "Slot acquired" project=saas-app slot=1 pid=$$
log_json "error" "orchestrator" "OOM killed" project=saas-app free_ram_gb=1

# Because StandardOutput=journal in systemd unit, these go to journald as MESSAGE=<json>
# Query: journalctl -u orchestrator --output=cat | jq 'select(.meta.project=="saas-app")'
```

### systemd Unit Configuration
```ini
[Service]
StandardOutput=journal
StandardError=journal
SyslogIdentifier=orchestrator
# Enables: journalctl -u orchestrator
# Or by identifier: journalctl -t orchestrator
```

### journalctl Query Examples
```bash
# Follow orchestrator logs
journalctl -u orchestrator -f

# Last hour of errors only
journalctl -u orchestrator -p err --since "1 hour ago"

# Filter by project (only works with Approach A structured fields)
journalctl -u orchestrator PROJECT_ID=saas-app -f

# JSON output for programmatic processing
journalctl -u orchestrator -o json | jq '.MESSAGE | fromjson | select(.level=="error")'

# Since last boot
journalctl -u orchestrator -b

# Output as plain text (one line per entry — good for grep)
journalctl -u orchestrator --output=cat | grep '"project":"saas-app"'
```

### Pros
- Zero log file management (rotation, cleanup) — journald handles it
- `journalctl -u orchestrator -f` works from anywhere, even SSH sessions
- Approach A: fields are indexed by journald — fast filtering by PROJECT_ID, TASK_LABEL
- Approach B: zero extra Python dependencies — pure bash + JSON
- Both approaches: logs survive daemon restarts and are timestamped by journald

### Cons
- Approach A requires `systemd-python` package (`pip install systemd-python` or `apt install python3-systemd`) — not available on all distros without compilation
- Approach B: JSON in MESSAGE field is not natively structured — requires `jq` post-processing for filtering
- journald truncates messages >48KB (not a concern for typical log lines)
- Logs only accessible on the VPS — no centralized log aggregation unless Promtail/Loki is added

### Complexity
**Estimate:** Easy — 1-2 hours

**Why:** Approach B (bash log_json) is already written above. Approach A is 5 lines of Python setup. The systemd unit already has `StandardOutput=journal` in the architecture spec.

---

## Comparison Matrix

| Criteria | P1: CCBot Session | P2: Pueue Groups | P3: Forum Topics | P4: SQLite WAL | P5: Auto-Approve | P6: journald Logs |
|----------|------------------|-----------------|-----------------|----------------|-----------------|------------------|
| Complexity | Low | Low | Medium | Low | Low | Low |
| Existing Proof | High (2K stars) | High (4.6K stars) | Medium (PTB v21+) | High (industry std) | Medium (PTB JobQueue) | High (systemd std) |
| Dependencies | None new | Pueue binary | python-telegram-bot | sqlite3 (stdlib) | None new | systemd-python (opt) |
| Debuggability | Medium | High (pueue status) | Medium | High (sqlite3 CLI) | Medium | High (journalctl) |
| Failure Modes | Orphaned sessions | Stale Running tasks | Topic deleted | WAL checkpoint stall | Job lost on restart | None (journald owned) |
| Time to Implement | 4-8h | 2-4h | 6-10h | 2-4h | 2-4h | 1-2h |

---

## Recommendation

**All 6 patterns should be implemented** — they are complementary layers, not alternatives.

### Priority Order for Phase 1 (Days 1-3)

**Day 1:**
1. **P6 (journald logging)** — 1-2h. Do this first. Without logs, debugging everything else is blind.
2. **P4 (SQLite WAL)** — 2-4h. Schema from architectures.md is already written. Run it.
3. **P2 (Pueue groups)** — 2-4h. `pueue group add` per project, JSON status query.

**Day 2:**
4. **P3 (Forum topics routing)** — 6-10h. The biggest piece. topic_id → project_id map in SQLite. `create_forum_topic` on `/addproject`.
5. **P1 (CCBot subprocess)** — 4-8h. `claude -p ... --resume $session_id --output-format json` pattern. Store session_id per project in SQLite.

**Day 3:**
6. **P5 (Auto-approve timeout)** — 2-4h. PTB JobQueue countdown. Cancel button.

### Complexity Buckets
- **Easy (Day 1 done same day):** P6, P4, P2
- **Medium (Day 2 full focus):** P3, P1
- **Trivial add-on (Day 3 morning):** P5

### Key Risks to Mitigate
1. **P1 risk**: `claude --output-format json` sometimes returns partial JSON if Claude crashes mid-run. Wrap `json.loads` in try/except; log raw stdout on parse failure.
2. **P3 risk**: Bot loses admin rights (topic creation breaks). Add startup check: `bot.get_chat_member(chat_id, bot.id)` → verify `can_manage_topics`.
3. **P4 risk**: Two processes using `isolation_level=None` AND explicit transactions simultaneously — `SQLITE_LOCKED` (not BUSY). Use one connection per process with proper transaction scoping.
4. **P5 risk**: JobQueue not persisted. On bot restart, pending countdown jobs are lost silently. Acceptable for MVP — log when a job is created and monitor for orphaned pending tasks in SQLite.

---

## Research Sources

- [RichardAtCT/claude-code-telegram](https://github.com/RichardAtCT/claude-code-telegram) — P1: CCBot session management, subprocess pattern, SDK integration
- [openclaw-prompts-and-skills/telegram-claude-poc.py](https://github.com/seedprod/openclaw-prompts-and-skills/blob/main/telegram-claude-poc.py) — P1: minimal subprocess + session_id pattern (60 lines)
- [terranc/claude-telegram-bot-bridge](https://github.com/terranc/claude-telegram-bot-bridge) — P1: daemon mode with crash recovery, PTY alternative
- [Nukesor/pueue](https://github.com/Nukesor/pueue) — P2: group management, JSON status, wait command, callback hook
- [Pueue Groups wiki](https://github.com/Nukesor/pueue/wiki/Groups) — P2: group parallelism configuration
- [python-telegram-bot v22 Bot.create_forum_topic docs](https://docs.python-telegram-bot.org/en/v22.1/telegram.bot.html) — P3: forum topic creation API
- [PTB PR #4170: reply to same thread by default](https://github.com/python-telegram-bot/python-telegram-bot/pull/4170) — P3: message_thread_id auto-routing in reply_* methods
- [TelegramHPC: Best Practices for Telegram Topic Hubs](https://telegramhpc.com/news/1714023446/) — P3: rate limits, gotchas, bot wiring
- [Zylos Research: SQLite WAL Mode for AI Agent Systems](https://zylos.ai/research/2026-02-20-sqlite-wal-mode-ai-agent-systems) — P4: WAL internals, checkpoint starvation, production hardening
- [DOCSAID: SQLite WAL busy_timeout](https://docsaid.org/en/blog/sqlite-wal-busy-timeout-for-workers) — P4: BUSY vs LOCKED distinction, concurrent worker patterns
- [python-telegram-bot timerbot example](https://docs.python-telegram-bot.org/en/v22.1/examples.timerbot.html) — P5: JobQueue.run_once pattern
- [Stack Overflow: edit message after expiration](https://stackoverflow.com/questions/74125542/automatically-edit-last-telegram-bot-message-after-expiration-period) — P5: cleanup job pattern with message_id
- [Andy's Thoughts: Structured logging Python + journald](https://denner.co/2025/01/26/logging3.html) — P6: JournalHandler with structured fields
- [smhk.net: Using structlog and journald](https://smhk.net/note/2023/11/structlog-and-journald/) — P6: custom JournalHandler implementation
