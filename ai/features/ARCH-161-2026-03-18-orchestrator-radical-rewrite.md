# Arch: [ARCH-161] Orchestrator Radical Rewrite — Python + North Star
**Status:** queued | **Priority:** P1 | **Date:** 2026-03-18

## Why
Текущий оркестратор — 20 файлов, 4422 строки, смесь bash и Python. Legacy Telegram UI, draft approval flows, shell SQL injection (ADR-017), системная хрупкость bash (6 багфиксов за один день 2026-03-18). Нужно переписать на чистый Python, следуя North Star (`ai/architect/orchestrator-final-state.md`): линейный пайплайн inbox → Spark → Autopilot → QA → Reflect → STOP. Telegram заменён OpenClaw.

## Context
North Star определяет: OpenClaw — единственный intake writer и наблюдатель. Внутренний пайплайн DLD — чистая машина: файл появляется в inbox → обрабатывается → артефакты пишутся в файловую систему → OpenClaw читает результаты. Telegram UI больше не нужен.

---

## Scope
**In scope:**
- Новый orchestrator.py (заменяет orchestrator.sh + inbox-processor.sh)
- Новый callback.py (заменяет pueue-callback.sh + qa-loop.sh + db_exec.sh)
- Рефакторинг notify.py → event_writer.py (Telegram → OpenClaw pending-events)
- Чистка db.py (удаление Telegram-специфичных функций)
- Обновление setup-vps.sh (systemd units, pueue callback path)
- Удаление Telegram UI файлов (telegram-bot.py, handlers)
- Удаление старых тестов + обновление docs

**Out of scope:**
- night-reviewer.sh (откладываем, но он вызывает event_writer.py вместо notify.py)
- openclaw-artifact-scan.py (внешний слой)
- run-agent.sh, claude-runner.py, codex-runner.sh, gemini-runner.sh (работают)

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
| File | Usage | Action |
|------|-------|--------|
| systemd dld-orchestrator.service | ExecStart → orchestrator.sh | update to orchestrator.py |
| systemd dld-telegram-bot.service | ExecStart → telegram-bot.py | delete unit |
| pueue.yml | callback → pueue-callback.sh | update to callback.py |
| night-reviewer.sh:215 | python3 notify.py | update to event_writer.py |
| setup-vps.sh:226,367,394 | hardcoded paths to old scripts | update all 3 |
| .claude/rules/dependencies.md | 15 component docs | rewrite |
| .claude/skills/spark/completion.md:190 | references pueue-callback.sh | update |

### Step 2: DOWN — what depends on?
- db.py core functions (keep): try_acquire_slot, release_slot, get_project_state, update_project_phase, log_task, finish_task, seed_projects_from_json, get_all_projects, get_available_slots
- db.py night functions (keep): save_finding, get_new_findings, update_finding_status, get_finding_by_id, get_all_findings
- Pueue label format: `{project_id}:{spec_id}` — preserve exactly
- OpenClaw pending-events JSON format: preserve exactly
- CLAUDE_CURRENT_SPEC_PATH env var 3-hop contract: preserve

### Step 3: BY TERM — grep entire project
| Term | Files Found | Action |
|------|-------------|--------|
| `pueue-callback.sh` | dependencies.md, completion.md:190 | update refs |
| `orchestrator.sh` | dependencies.md, setup-vps.sh | update refs |
| `telegram-bot.py` | dependencies.md, setup-vps.sh, test_cycle_smoke.py | delete refs |
| `notify.py` | dependencies.md, night-reviewer.sh:215, night-mode.md:91 | update to event_writer.py |
| `inbox-processor.sh` | dependencies.md, orchestrator.sh | delete refs |
| `qa-loop.sh` | dependencies.md | delete refs |
| `db_exec.sh` | qa-loop.sh | delete both |
| `approve_handler` | dependencies.md, telegram-bot.py, test_approve_handler.py | delete all |

### Step 4: CHECKLIST — mandatory folders
- [x] `scripts/vps/tests/` — delete: test_cycle_smoke.py, test_notify.py, test_approve_handler.py, test_artifact_scan.py (references deleted files)
- [x] `db/migrations/` — N/A (no schema changes)
- [x] `ai/glossary/` — N/A

### Verification
- [x] All found files added to Allowed Files
- [x] grep for old terms after changes → 0 results (except night-reviewer.sh which uses event_writer.py)

---

## Allowed Files
**ONLY these files may be modified during implementation:**

**New files allowed:**
1. `scripts/vps/orchestrator.py` — new main daemon
2. `scripts/vps/callback.py` — new pueue callback
3. `scripts/vps/event_writer.py` — OpenClaw pending-event writer (replaces notify.py Telegram layer)

**Modify:**
4. `scripts/vps/db.py` — remove Telegram-specific functions
5. `scripts/vps/setup-vps.sh` — update systemd units + pueue callback path
6. `scripts/vps/night-reviewer.sh` — update notify.py → event_writer.py call
7. `.claude/rules/dependencies.md` — rewrite for new architecture
8. `.claude/skills/spark/completion.md` — remove pueue-callback.sh reference
9. `.claude/skills/audit/night-mode.md` — update notify.py reference
10. `scripts/vps/.env.example` — remove TELEGRAM_* vars
11. `CLAUDE.md` — update if needed

**Delete:**
12. `scripts/vps/telegram-bot.py` (560 LOC)
13. `scripts/vps/admin_handler.py` (284 LOC)
14. `scripts/vps/approve_handler.py` (156 LOC)
15. `scripts/vps/photo_handler.py` (96 LOC)
16. `scripts/vps/voice_handler.py` (113 LOC)
17. `scripts/vps/notify.py` (256 LOC) — replaced by event_writer.py
18. `scripts/vps/orchestrator.sh` (425 LOC) — replaced by orchestrator.py
19. `scripts/vps/pueue-callback.sh` (428 LOC) — replaced by callback.py
20. `scripts/vps/inbox-processor.sh` (245 LOC) — absorbed into orchestrator.py
21. `scripts/vps/qa-loop.sh` (114 LOC) — absorbed into callback.py
22. `scripts/vps/db_exec.sh` (19 LOC) — legacy, ADR-017 violation
23. `scripts/vps/tests/test_cycle_smoke.py` — references deleted files
24. `scripts/vps/tests/test_notify.py` — imports deleted notify module
25. `scripts/vps/tests/test_approve_handler.py` — imports deleted module
26. `scripts/vps/tests/test_artifact_scan.py` — references deleted callback

**FORBIDDEN:** All other files.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** scripts/vps (orchestrator infrastructure)
**Cross-cutting:** N/A
**Data model:** project_state, compute_slots, task_log (SQLite, no schema changes)

---

## Approaches

### Approach 1: Thin sync Python, all-in-one (based on Patterns + External scouts)
**Source:** [Python subprocess docs](https://docs.python.org/3/library/subprocess.html), [Signal handling for graceful shutdowns](https://johal.in/signal-handling-in-python-custom-handlers-for-graceful-shutdowns/)
**Summary:** `subprocess.run()` для pueue, `threading.Event` для shutdown, sequential scan. Механический перевод bash→Python. notify.py → event_writer.py (pending-events JSON + openclaw wake).
**Pros:** Минимальный концептуальный overhead, сохраняет проверенную логику, stdlib only
**Cons:** Нет параллельного сканирования проектов (не нужно при 3-5 проектах)

### Approach 2: Asyncio daemon (based on Patterns scout Approach 2)
**Source:** [roguelynn.com asyncio graceful shutdowns](https://roguelynn.com/words/asyncio-graceful-shutdowns/)
**Summary:** Full asyncio с `asyncio.gather()` для параллельного сканирования
**Pros:** Parallel scan, consistent с claude-runner.py
**Cons:** CPython bug #103847, asyncio overhead для 300s loop, callback всё равно sync

### Selected: 1
**Rationale:** Orchestrator — это 300s poll loop с 3-5 проектами. Asyncio не даёт реального выигрыша, но добавляет CPython subprocess bug и conceptual overhead (External scout, Patterns scout). Sync Python — прямой перевод проверенной логики.

---

## Design

### User Flow
1. Файл появляется в `ai/inbox/*.md` с `Status: new` (OpenClaw кладёт извне)
2. orchestrator.py scan_inbox() находит файл → извлекает Route/Provider → dispatch Spark через pueue
3. Spark создаёт спеку в `ai/features/` + запись в `ai/backlog.md` (status: queued)
4. orchestrator.py scan_backlog() находит queued → dispatch Autopilot через pueue
5. Autopilot завершается → pueue вызывает callback.py
6. callback.py: release_slot + finish_task + phase transition + dispatch QA + Reflect
7. callback.py: write OpenClaw pending-event via event_writer.py
8. QA/Reflect завершаются → callback.py: write pending-events → STOP
9. OpenClaw читает pending-events и артефакты (извне)

### Architecture

```
                    ┌─────────────────────┐
                    │   orchestrator.py    │  systemd service
                    │   (poll loop 300s)   │
                    └────────┬────────────┘
                             │ pueue add
                    ┌────────▼────────────┐
                    │       Pueue         │  task queue
                    │  (claude/codex/     │
                    │   gemini runners)   │
                    └────────┬────────────┘
                             │ on completion
                    ┌────────▼────────────┐
                    │    callback.py       │  pueue callback
                    │  (slot, phase, QA,  │
                    │   reflect, events)  │
                    └────────┬────────────┘
                             │
                    ┌────────▼────────────┐
                    │  event_writer.py     │  pending-events + wake
                    └─────────────────────┘
```

**Key interfaces:**
- Pueue label format: `{project_id}:{spec_id}` (preserve exactly)
- callback.py CLI: `callback.py <pueue_id> '<group>' '<result>'` (matches pueue.yml template)
- OpenClaw pending-events: `ai/openclaw/pending-events/{ts}-{skill}.json`
- db.py: import directly (no CLI wrappers needed from Python)

---

## Detailed Implementation Plan

### Research Sources
- [Python signal handling for graceful shutdowns](https://johal.in/signal-handling-in-python-custom-handlers-for-graceful-shutdowns/) — threading.Event pattern
- [SQLite concurrent writes](https://tenthousandmeters.com/blog/sqlite-concurrent-writes-and-database-is-locked-errors/) — WAL + BEGIN IMMEDIATE
- [Pueue v4 Configuration](https://github.com/Nukesor/pueue/wiki/Configuration) — callback template variables
- [Idempotent task handlers](https://dev.to/humzakt/how-to-build-idempotent-cloud-tasks-handlers-in-python-the-pattern-that-eliminated-our-duplicate-4gml) — crash-safe callbacks

### Task 1: Create event_writer.py (replaces notify.py Telegram layer)

**Files:**
  - Create: `scripts/vps/event_writer.py`

**Context:** notify.py sends Telegram messages. We replace it with a module that writes OpenClaw pending-events JSON and wakes OpenClaw via CLI. Used by callback.py and night-reviewer.sh.

**Design:**
```python
#!/usr/bin/env python3
"""Write OpenClaw pending-events and wake OpenClaw.

Replaces notify.py Telegram layer (ARCH-161).
Called by: callback.py (import), night-reviewer.sh (CLI).

CLI: python3 event_writer.py <project_id> <skill> <status> <message> [--artifact <path>]
"""
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

def write_event(project_path: str, skill: str, status: str,
                message: str, artifact_rel: str = "") -> Path:
    """Write pending-event JSON to ai/openclaw/pending-events/."""
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    events_dir = Path(project_path) / "ai" / "openclaw" / "pending-events"
    events_dir.mkdir(parents=True, exist_ok=True)

    event = {
        "project_id": Path(project_path).name,
        "skill": skill,
        "status": status,
        "message": message,
        "artifact_rel": artifact_rel,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    event_file = events_dir / f"{ts}-{skill}.json"
    event_file.write_text(json.dumps(event, ensure_ascii=False, indent=2))
    return event_file


def wake_openclaw() -> bool:
    """Wake OpenClaw via CLI. Returns True on success."""
    openclaw_bin = os.path.expanduser("~/.npm-global/bin/openclaw")
    if not os.path.isfile(openclaw_bin):
        return False
    try:
        subprocess.run(
            [openclaw_bin, "system", "event", "--mode", "now", "--text", "pipeline event"],
            timeout=10, capture_output=True
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def notify(project_path: str, skill: str, status: str,
           message: str, artifact_rel: str = "") -> None:
    """Write event + wake OpenClaw. Main entry point."""
    write_event(project_path, skill, status, message, artifact_rel)
    wake_openclaw()


if __name__ == "__main__":
    # CLI: python3 event_writer.py <project_path> <skill> <status> <message> [--artifact <path>]
    # For night-reviewer.sh compatibility
    ...
```

**Acceptance:**
- [ ] `python3 -c "import event_writer; print('ok')"` works
- [ ] CLI writes valid JSON to ai/openclaw/pending-events/
- [ ] wake_openclaw() handles missing binary gracefully

---

### Task 2: Create orchestrator.py (replaces orchestrator.sh + inbox-processor.sh)

**Files:**
  - Create: `scripts/vps/orchestrator.py`

**Context:** Main daemon. Poll loop: hot-reload projects, git pull, scan inbox, scan backlog, dispatch tasks via pueue.

**Design:**
```python
#!/usr/bin/env python3
"""DLD Orchestrator — main poll loop.

Replaces orchestrator.sh + inbox-processor.sh (ARCH-161).
Runs as systemd service. Poll interval configurable via POLL_INTERVAL env var.

Flow per project per cycle:
  1. git pull --rebase (safe, skip if agent running)
  2. scan ai/inbox/ for Status:new → dispatch Spark via pueue
  3. scan ai/backlog.md for first queued spec → dispatch Autopilot via pueue
"""
import json, logging, os, re, signal, subprocess, sys, threading
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import db

_stop = threading.Event()
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "300"))
PROJECTS_JSON = Path(os.environ.get("PROJECTS_JSON", str(SCRIPT_DIR / "projects.json")))
LOG_DIR = Path(os.environ.get("LOG_DIR", "/var/log/dld-orchestrator"))

log = logging.getLogger("orchestrator")

# --- Functions ---
# sync_projects(): mtime-based hot-reload of projects.json
# git_pull(project_dir): safe git pull --rebase, skip if agent running
# scan_inbox(project_id, project_dir): find Status:new → extract Route/Provider → pueue add
# scan_backlog(project_id, project_dir): find first queued → resolve provider → pueue add
# pueue_add(group, label, cmd): subprocess.run(["pueue", "add", ...])
# process_project(project_id, project_dir): git_pull + scan_inbox + scan_backlog
# main(): signal handlers + poll loop

# Key implementation details:
# - threading.Event.wait(timeout=POLL_INTERVAL) for interruptible sleep
# - signal.signal(SIGTERM/SIGINT, lambda: _stop.set())
# - db.try_acquire_slot() before pueue add
# - db.log_task() + db.update_project_phase() after pueue add
# - Inbox file lifecycle: Status:new → processing → move to done/
# - Headless prefix: [headless] Source: <source>. Context: <context>. <idea>
# - CLAUDE_CURRENT_SPEC_PATH set via pueue env for inbox tasks
# - PID file at SCRIPT_DIR/.orchestrator.pid
# - JSON structured logging (daily rotation)
```

**Key contracts to preserve (from codebase scout):**
- Pueue label: `{project_id}:{spec_id}` for autopilot, `{project_id}:inbox-{YYYYMMDD-HHMMSS}` for inbox
- Provider resolution: project default from db, override from inbox file `**Provider:**` field
- Route extraction: `**Route:**` field → skill mapping (spark, architect, council, etc.)
- Slot acquisition: `db.try_acquire_slot(project_id, provider, pueue_id)` before submit
- Git pull: skip if compute_slots has entry for this project_id
- .run-now-{project_id} trigger files (immediate cycle)
- .review-trigger file (night review dispatch)

**Acceptance:**
- [ ] `python3 -c "import orchestrator"` — no syntax errors
- [ ] `python3 orchestrator.py --help` or `--dry-run` shows usage
- [ ] Signal handling: SIGTERM sets _stop, loop exits cleanly
- [ ] scan_inbox correctly parses Route/Provider/Source from inbox files
- [ ] scan_backlog correctly finds first queued spec

---

### Task 3: Create callback.py (replaces pueue-callback.sh + qa-loop.sh)

**Files:**
  - Create: `scripts/vps/callback.py`

**Context:** Pueue callback script. Called on every task completion. Must always exit 0.

**Design:**
```python
#!/usr/bin/env python3
"""DLD Pueue Callback — task completion handler.

Replaces pueue-callback.sh (ARCH-161).
Called by pueue daemon: callback.py <pueue_id> '<group>' '<result>'

Steps:
  1. Resolve label via pueue status --json (v4 doesn't expose {{ label }})
  2. Parse PROJECT_ID and SPEC_ID from label
  3. Release slot (db.release_slot)
  4. Finish task (db.finish_task)
  5. Phase transition based on skill + result
  6. Parse agent JSON output (skill, result_preview, exit_code)
  7. Write OpenClaw pending-event (event_writer.py)
  8. If autopilot success: dispatch QA + Reflect (idempotent)
  9. Exit 0 always
"""

# Key implementation details:
# - Every step in try/except — NEVER raise, NEVER exit non-zero
# - Label resolution: pueue status --json → tasks[pueue_id].label
# - Phase transitions:
#   autopilot success (non-inbox) → qa_pending
#   autopilot success (inbox-*) → idle
#   any failure → failed
# - QA dispatch: check is_already_queued(label) before pueue add
# - Reflect dispatch: same idempotent check
# - QA label: {project_id}:qa-{original_label}
# - Reflect label: {project_id}:reflect-{original_label}
# - Skip night-reviewer group entirely
# - Agent JSON parsing: last line of pueue log --lines 10
# - OpenClaw event: event_writer.notify(project_path, skill, status, message, artifact)
```

**Key contracts to preserve:**
- CLI signature: `callback.py <pueue_id> '<group>' '<result>'`
- Result parsing: Success → done, Failed/Killed/Errored → failed
- Pueue label format parsing: `project_id:spec_id` via `label.split(":", 1)`
- Idempotent dispatch: `is_already_queued(label)` via pueue status --json
- Agent JSON output format: `{"skill", "result_preview", "exit_code", ...}` from claude-runner.py
- OpenClaw pending-events JSON format (preserve exactly for openclaw-artifact-scan.py)

**Acceptance:**
- [ ] `python3 callback.py --help` shows usage
- [ ] `bash -c 'python3 callback.py 999 "test-group" "Success"'` exits 0 (even with invalid pueue_id)
- [ ] Never exits non-zero under any circumstances

---

### Task 4: Clean db.py — remove Telegram-specific functions

**Files:**
  - Modify: `scripts/vps/db.py`

**Context:** Remove functions only used by deleted Telegram files. Keep core orchestrator + night-reviewer functions.

**Delete these functions:**
- `get_project_by_topic()` — only used by telegram-bot.py, photo/voice/approve handlers
- `add_project()` — only used by admin_handler.py
- `set_project_topic()` — only used by Telegram wizard
- `get_nexus_cache()` / `save_nexus_cache()` — only used by admin_handler.py

**Delete from CLI __main__:**
- Remove Telegram-related CLI commands if any

**Keep everything else** — especially:
- All core functions (try_acquire_slot, release_slot, etc.)
- Night findings functions (save_finding, get_new_findings, etc.)
- CLI commands used by night-reviewer.sh (save-finding, get-new-findings, update-phase, etc.)
- `callback` CLI command (until new callback.py imports db.py directly — then can remove)

**Also clean:**
- Remove `DEFAULT_CHAT_ID` constant (reads TELEGRAM_CHAT_ID env)
- Remove `_ensure_runtime_schema()` if it only handles chat_id migration
- Remove topic_id from seed_projects_from_json() INSERT if possible (or keep for compat)

**Acceptance:**
- [ ] `grep -c "get_project_by_topic\|add_project\|set_project_topic\|get_nexus_cache" scripts/vps/db.py` returns 0
- [ ] `python3 -c "import db; db.get_all_projects()"` still works
- [ ] All CLI commands used by night-reviewer.sh still work

---

### Task 5: Update night-reviewer.sh — notify.py → event_writer.py

**Files:**
  - Modify: `scripts/vps/night-reviewer.sh`

**Context:** night-reviewer.sh calls `python3 notify.py <project_id> <msg>` at line ~215. Replace with `python3 event_writer.py <project_path> night-review done <msg>`.

**Changes:**
- Replace all `python3 "${SCRIPT_DIR}/notify.py" "${PROJECT_ID}" "${msg}"` calls with:
  `python3 "${SCRIPT_DIR}/event_writer.py" "${PROJECT_PATH}" "night-review" "done" "${msg}" || true`
- Need to resolve PROJECT_PATH from PROJECT_ID (via db.py get_project_state)

**Acceptance:**
- [ ] `grep -c "notify.py" scripts/vps/night-reviewer.sh` returns 0
- [ ] `grep -c "event_writer.py" scripts/vps/night-reviewer.sh` returns >= 1
- [ ] `bash -n scripts/vps/night-reviewer.sh` exits 0

---

### Task 6: Delete old files + tests

**Files:**
  - Delete: `scripts/vps/telegram-bot.py`
  - Delete: `scripts/vps/admin_handler.py`
  - Delete: `scripts/vps/approve_handler.py`
  - Delete: `scripts/vps/photo_handler.py`
  - Delete: `scripts/vps/voice_handler.py`
  - Delete: `scripts/vps/notify.py`
  - Delete: `scripts/vps/orchestrator.sh`
  - Delete: `scripts/vps/pueue-callback.sh`
  - Delete: `scripts/vps/inbox-processor.sh`
  - Delete: `scripts/vps/qa-loop.sh`
  - Delete: `scripts/vps/db_exec.sh`
  - Delete: `scripts/vps/tests/test_cycle_smoke.py`
  - Delete: `scripts/vps/tests/test_notify.py`
  - Delete: `scripts/vps/tests/test_approve_handler.py`
  - Delete: `scripts/vps/tests/test_artifact_scan.py`

**Total:** 11 script files (~2800 LOC) + 4 test files

**Acceptance:**
- [ ] None of the deleted files exist on disk
- [ ] `grep -rn "telegram-bot.py\|approve_handler\|photo_handler\|voice_handler" scripts/vps/*.py scripts/vps/*.sh` returns 0 (no dangling imports)

---

### Task 7: Update setup-vps.sh

**Files:**
  - Modify: `scripts/vps/setup-vps.sh`

**Changes:**
1. **Pueue callback:** Replace `CALLBACK_LINE` pointing to `pueue-callback.sh` with `callback.py`
   ```
   callback: "${SCRIPT_DIR}/venv/bin/python3 ${SCRIPT_DIR}/callback.py {{ id }} '{{ group }}' '{{ result }}'"
   ```
2. **Orchestrator systemd unit:** Replace `ExecStart=...orchestrator.sh` with:
   ```
   ExecStart=${SCRIPT_DIR}/venv/bin/python3 ${SCRIPT_DIR}/orchestrator.py
   ```
3. **Delete Telegram bot systemd unit:** Remove the `dld-telegram-bot.service` creation block entirely
4. **Update .env.example:** Remove TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ALLOWED_USERS, OPS_TOPIC_ID, GROQ_API_KEY

**Acceptance:**
- [ ] `grep -c "orchestrator.sh" scripts/vps/setup-vps.sh` returns 0
- [ ] `grep -c "pueue-callback.sh" scripts/vps/setup-vps.sh` returns 0
- [ ] `grep -c "telegram-bot.py" scripts/vps/setup-vps.sh` returns 0
- [ ] `grep -c "orchestrator.py" scripts/vps/setup-vps.sh` returns >= 1
- [ ] `grep -c "callback.py" scripts/vps/setup-vps.sh` returns >= 1
- [ ] `bash -n scripts/vps/setup-vps.sh` exits 0

---

### Task 8: Update docs — dependencies.md, completion.md, CLAUDE.md

**Files:**
  - Modify: `.claude/rules/dependencies.md` — rewrite for new architecture
  - Modify: `.claude/skills/spark/completion.md` — remove pueue-callback.sh reference at line ~190
  - Modify: `.claude/skills/audit/night-mode.md` — update notify.py → event_writer.py
  - Modify: `scripts/vps/.env.example` — remove Telegram vars

**dependencies.md rewrite scope:**
- Remove sections: telegram-bot.py, notify.py, approve_handler.py, photo_handler.py, voice_handler.py, admin_handler.py, orchestrator.sh, pueue-callback.sh, inbox-processor.sh, qa-loop.sh
- Add sections: orchestrator.py, callback.py, event_writer.py
- Update: db.py (remove Telegram callers), night-reviewer.sh (event_writer.py), setup-vps.sh (new paths)

**Acceptance:**
- [ ] `grep -c "telegram-bot.py\|pueue-callback.sh\|orchestrator.sh\|inbox-processor.sh\|qa-loop.sh" .claude/rules/dependencies.md` returns 0
- [ ] `grep -c "orchestrator.py\|callback.py\|event_writer.py" .claude/rules/dependencies.md` returns >= 3
- [ ] `grep -c "pueue-callback.sh" .claude/skills/spark/completion.md` returns 0

---

### Execution Order

1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

Task 1 (event_writer.py) first — used by Task 3 (callback.py) and Task 5 (night-reviewer.sh).
Task 2 (orchestrator.py) and Task 3 (callback.py) can run in parallel but sequential is safer.
Task 6 (delete) MUST be after Tasks 1-5 (new files exist before old deleted).
Task 7 (setup-vps.sh) after Task 6.
Task 8 (docs) LAST.

### Dependencies
- Task 3 depends on Task 1 (imports event_writer)
- Task 5 depends on Task 1 (calls event_writer.py CLI)
- Task 6 depends on Tasks 1-5 (new replacements ready)
- Task 7 depends on Task 6 (old files deleted)
- Task 8 depends on Task 7 (all changes done)

---

## Flow Coverage Matrix (REQUIRED)

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | File appears in ai/inbox/ with Status:new | - | existing (OpenClaw writes) |
| 2 | orchestrator.py detects new inbox file | Task 2 | new |
| 3 | orchestrator.py extracts Route/Provider, dispatches Spark | Task 2 | new |
| 4 | Spark creates queued spec + backlog entry | - | existing (TECH-151) |
| 5 | orchestrator.py detects queued spec in backlog | Task 2 | new |
| 6 | orchestrator.py dispatches Autopilot via pueue | Task 2 | new |
| 7 | Autopilot completes → pueue fires callback.py | Task 3 | new |
| 8 | callback.py releases slot, finishes task, updates phase | Task 3 | new |
| 9 | callback.py dispatches QA + Reflect | Task 3 | new |
| 10 | callback.py writes OpenClaw pending-event | Task 1, 3 | new |
| 11 | QA/Reflect complete → callback.py writes events → STOP | Task 3 | new |
| 12 | OpenClaw reads pending-events and artifacts | - | existing (external) |
| 13 | night-reviewer.sh writes events via event_writer.py | Task 5 | updated |
| 14 | Old files deleted, tests cleaned | Task 6 | cleanup |
| 15 | setup-vps.sh creates correct systemd units | Task 7 | updated |
| 16 | Docs reflect new architecture | Task 8 | updated |

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | orchestrator.py syntax valid | `python3 -c "import orchestrator"` | exit 0 | deterministic | codebase | P0 |
| EC-2 | callback.py syntax valid | `python3 -c "import callback"` | exit 0 | deterministic | codebase | P0 |
| EC-3 | event_writer.py syntax valid | `python3 -c "import event_writer"` | exit 0 | deterministic | codebase | P0 |
| EC-4 | callback.py always exits 0 | `python3 callback.py 999 "test" "Success"` | exit 0 | deterministic | external | P0 |
| EC-5 | No deleted files remain | `ls telegram-bot.py orchestrator.sh pueue-callback.sh` | all missing | deterministic | devil | P0 |
| EC-6 | No dangling references to deleted files | `grep -rn "telegram-bot.py\|pueue-callback.sh\|orchestrator.sh\|inbox-processor.sh\|qa-loop.sh\|notify.py" scripts/vps/*.py scripts/vps/*.sh .claude/rules/dependencies.md` | 0 results | deterministic | devil | P0 |
| EC-7 | db.py Telegram functions removed | `grep -c "get_project_by_topic\|add_project\|set_project_topic\|get_nexus_cache" scripts/vps/db.py` | 0 | deterministic | codebase | P1 |
| EC-8 | setup-vps.sh references new files | `grep -c "orchestrator.py" scripts/vps/setup-vps.sh` | >= 1 | deterministic | devil | P0 |
| EC-9 | setup-vps.sh no old references | `grep -c "orchestrator.sh\|pueue-callback.sh\|telegram-bot.py" scripts/vps/setup-vps.sh` | 0 | deterministic | devil | P0 |
| EC-10 | night-reviewer.sh uses event_writer | `grep -c "event_writer" scripts/vps/night-reviewer.sh` | >= 1 | deterministic | devil | P0 |
| EC-11 | dependencies.md updated | `grep -c "orchestrator.py\|callback.py" .claude/rules/dependencies.md` | >= 2 | deterministic | codebase | P1 |
| EC-12 | Old tests deleted | `ls test_cycle_smoke.py test_notify.py test_approve_handler.py 2>&1` | all missing | deterministic | devil | P0 |

### Coverage Summary
- Deterministic: 12 | Integration: 0 | LLM-Judge: 0 | Total: 12 (min 3 met)

### TDD Order
1. EC-3 (event_writer) → Task 1
2. EC-1 (orchestrator.py) → Task 2
3. EC-2, EC-4 (callback.py) → Task 3
4. EC-7 (db.py clean) → Task 4
5. EC-10 (night-reviewer) → Task 5
6. EC-5, EC-12 (deletions) → Task 6
7. EC-8, EC-9 (setup-vps) → Task 7
8. EC-6, EC-11 (docs + no dangling refs) → Task 8

---

## Acceptance Verification (MANDATORY)

### Smoke Checks (process alive)

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Python modules importable | `python3 -c "import orchestrator; import callback; import event_writer"` | exit 0 | 5s |
| AV-S2 | Bash syntax valid for remaining scripts | `bash -n scripts/vps/run-agent.sh && bash -n scripts/vps/night-reviewer.sh && bash -n scripts/vps/setup-vps.sh` | exit 0 | 5s |

### Functional Checks (business logic)

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | callback.py fail-safe | N/A | `python3 scripts/vps/callback.py 999 "fake" "Success"` | Exit 0, logs error about invalid pueue_id |
| AV-F2 | No deleted files | After Task 6 | `ls scripts/vps/telegram-bot.py 2>&1` | "No such file" |
| AV-F3 | No dangling refs | After Task 8 | `grep -rn "telegram-bot\|pueue-callback.sh\|orchestrator.sh" scripts/vps/*.py scripts/vps/*.sh .claude/rules/ .claude/skills/` | 0 results (excluding this spec and historical docs) |

### Verify Command (copy-paste ready)

```bash
cd /home/dld/projects/dld
# Smoke
python3 -c "
import sys; sys.path.insert(0, 'scripts/vps')
import orchestrator; import callback; import event_writer
print('imports OK')
"
bash -n scripts/vps/run-agent.sh && bash -n scripts/vps/night-reviewer.sh && echo "bash OK"

# Functional — deletions
for f in telegram-bot.py admin_handler.py approve_handler.py photo_handler.py voice_handler.py notify.py orchestrator.sh pueue-callback.sh inbox-processor.sh qa-loop.sh db_exec.sh; do
  [ -f "scripts/vps/$f" ] && echo "FAIL: $f still exists" || echo "PASS: $f deleted"
done

# Functional — no dangling refs
echo "--- Dangling refs ---"
grep -rn "telegram-bot.py\|pueue-callback.sh\|orchestrator\.sh\|inbox-processor.sh\|qa-loop.sh" scripts/vps/*.py scripts/vps/*.sh .claude/rules/dependencies.md 2>/dev/null | grep -v "ARCH-161\|\.md:" || echo "PASS: no dangling refs"

# Functional — new refs in setup-vps.sh
echo "--- setup-vps.sh ---"
grep -c "orchestrator.py" scripts/vps/setup-vps.sh | grep -q "0" && echo "FAIL" || echo "PASS: orchestrator.py found"
grep -c "callback.py" scripts/vps/setup-vps.sh | grep -q "0" && echo "FAIL" || echo "PASS: callback.py found"

# Functional — db.py clean
echo "--- db.py ---"
grep -c "get_project_by_topic\|add_project\|set_project_topic\|get_nexus_cache" scripts/vps/db.py | grep -q "0" && echo "PASS" || echo "FAIL: Telegram functions remain"

# Functional — night-reviewer
echo "--- night-reviewer ---"
grep -c "event_writer" scripts/vps/night-reviewer.sh | grep -q "0" && echo "FAIL" || echo "PASS: event_writer found"
grep -c "notify.py" scripts/vps/night-reviewer.sh | grep -q "0" && echo "PASS" || echo "FAIL: notify.py still referenced"
```

---

## Migration Procedure (MANDATORY for VPS deployment)

After autopilot completes, deploy to VPS:

```bash
# 1. Wait for empty pueue slots
pueue status  # verify no Running tasks

# 2. Stop services
sudo systemctl stop dld-orchestrator
sudo systemctl stop dld-telegram-bot  # will be removed

# 3. Pull new code
cd /home/dld/projects/dld && git pull origin develop

# 4. Update pueue callback
# Edit ~/.config/pueue/pueue.yml:
#   callback: "/path/to/venv/bin/python3 /path/to/callback.py {{ id }} '{{ group }}' '{{ result }}'"
# Then restart pueue daemon:
pueue kill --all  # clean slate
pueued -d  # restart daemon

# 5. Update systemd
sudo systemctl daemon-reload
sudo systemctl restart dld-orchestrator
sudo systemctl disable dld-telegram-bot
sudo systemctl stop dld-telegram-bot

# 6. Verify
sudo systemctl status dld-orchestrator  # should be active
pueue status  # groups should be visible
```

---

## Definition of Done

### Functional
- [x] orchestrator.py runs as systemd daemon, polls projects, dispatches Spark + Autopilot
- [x] callback.py handles task completion, dispatches QA + Reflect, writes OpenClaw events
- [x] event_writer.py writes pending-events JSON, wakes OpenClaw
- [x] db.py cleaned of Telegram functions
- [x] night-reviewer.sh uses event_writer.py
- [x] All 11 old files deleted
- [x] All 4 old tests deleted
- [x] setup-vps.sh updated for new architecture
- [x] docs updated (dependencies.md, completion.md, night-mode.md)

### Tests
- [x] All 12 eval criteria pass
- [x] AV-S1, AV-S2 smoke checks pass
- [x] AV-F1, AV-F2, AV-F3 functional checks pass

### Acceptance Verification
- [x] Verify Command runs without errors

### Technical
- [x] No regressions in orchestrator flow
- [x] Pueue label format preserved
- [x] OpenClaw pending-events format preserved
- [x] North Star invariants maintained

---

## Autopilot Log
[Auto-populated by autopilot during execution]
