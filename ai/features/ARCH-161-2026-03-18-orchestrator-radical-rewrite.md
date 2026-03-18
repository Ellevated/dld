# Arch: [ARCH-161] Orchestrator Radical Rewrite — Python + North Star
**Status:** done | **Priority:** P1 | **Date:** 2026-03-18

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

## Drift Log

**Checked:** 2026-03-18 UTC
**Result:** light_drift

### Changes Detected
| File | Change Type | Action Taken |
|------|-------------|--------------|
| `scripts/vps/db_exec.sh` | MISSING — file does not exist in worktree or develop | AUTO-FIX: removed from delete list (already absent) |
| `scripts/vps/tests/` | directory not in worktree (Glob empty), but files exist on develop via git | AUTO-FIX: test files exist, git rm will work |
| `scripts/vps/setup-vps.sh:226` | uses `{{ label }}` in callback — stale, Pueue v4.0.4 has no `{{ label }}` | AUTO-FIX: new callback.py uses `{{ id }} '{{ group }}' '{{ result }}'` only |
| `scripts/vps/db.py` | `save_nexus_cache` does not exist — spec said to delete it | AUTO-FIX: removed from delete list, only `get_nexus_cache` exists (line 285) |
| `scripts/vps/db.py:24-46` | `_ensure_runtime_schema` handles chat_id migration + unique index | AUTO-FIX: keep unique index creation, remove chat_id migration |

### References Updated
- Task 4: `save_nexus_cache()` removed from delete list (function does not exist)
- Task 6: `db_exec.sh` removed from delete list (file does not exist)
- Task 4: `_ensure_runtime_schema` cleanup clarified (keep index, remove chat_id migration)
- Task 4: `callback` CLI command removal clarified (new callback.py imports db directly)

---

## Detailed Implementation Plan

### Research Sources
- [Python signal handling for graceful shutdowns](https://johal.in/signal-handling-in-python-custom-handlers-for-graceful-shutdowns/) — threading.Event pattern
- [SQLite concurrent writes](https://tenthousandmeters.com/blog/sqlite-concurrent-writes-and-database-is-locked-errors/) — WAL + BEGIN IMMEDIATE
- [Pueue v4 Configuration](https://github.com/Nukesor/pueue/wiki/Configuration) — callback template variables: `{{ id }}`, `{{ group }}`, `{{ result }}` (NO `{{ label }}`)
- [Idempotent task handlers](https://dev.to/humzakt/how-to-build-idempotent-cloud-tasks-handlers-in-python-the-pattern-that-eliminated-our-duplicate-4gml) — crash-safe callbacks

---

### Task 1: Create event_writer.py (replaces notify.py Telegram layer)

**Files:**
  - Create: `scripts/vps/event_writer.py`

**Context:** notify.py sends Telegram messages. We replace it with a module that writes OpenClaw pending-events JSON and wakes OpenClaw via CLI. Used by callback.py (import) and night-reviewer.sh (CLI).

**Step 1: Create `scripts/vps/event_writer.py`**

```python
#!/usr/bin/env python3
"""
Module: event_writer
Role: Write OpenClaw pending-events JSON and wake OpenClaw CLI.
Uses: json, subprocess (stdlib)
Used by: callback.py (import), night-reviewer.sh (CLI)

Replaces notify.py Telegram layer (ARCH-161).

CLI: python3 event_writer.py <project_path> <skill> <status> <message> [--artifact <path>]
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("event_writer")


def write_event(
    project_path: str,
    skill: str,
    status: str,
    message: str,
    artifact_rel: str = "",
) -> Path:
    """Write pending-event JSON to ai/openclaw/pending-events/.

    Args:
        project_path: Absolute path to project root.
        skill: Skill name (autopilot, qa, reflect, spark, night-review).
        status: Outcome status (done, failed).
        message: Human-readable description.
        artifact_rel: Relative path to artifact file (optional).

    Returns:
        Path to the written event JSON file.
    """
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
    log.info("event written: %s", event_file.name)
    return event_file


def wake_openclaw() -> bool:
    """Wake OpenClaw via CLI. Returns True on success.

    Looks for openclaw binary at ~/.npm-global/bin/openclaw.
    Timeout 30s to match BUG-160 fix. Fails silently if binary missing.
    """
    openclaw_bin = os.path.expanduser("~/.npm-global/bin/openclaw")
    if not os.path.isfile(openclaw_bin):
        log.debug("openclaw binary not found at %s", openclaw_bin)
        return False
    try:
        subprocess.run(
            [openclaw_bin, "system", "event", "--mode", "now",
             "--text", "pipeline event"],
            timeout=30,
            capture_output=True,
        )
        log.info("openclaw wake sent")
        return True
    except subprocess.TimeoutExpired:
        log.warning("openclaw wake timed out")
        return False
    except (FileNotFoundError, OSError) as exc:
        log.warning("openclaw wake failed: %s", exc)
        return False


def notify(
    project_path: str,
    skill: str,
    status: str,
    message: str,
    artifact_rel: str = "",
) -> None:
    """Write event + wake OpenClaw. Main entry point for imports."""
    write_event(project_path, skill, status, message, artifact_rel)
    wake_openclaw()


def main() -> None:
    """CLI entrypoint for bash callers (night-reviewer.sh).

    Usage: python3 event_writer.py <project_path> <skill> <status> <message> [--artifact <path>]
    """
    if len(sys.argv) < 5:
        print(
            "Usage: event_writer.py <project_path> <skill> <status> <message> "
            "[--artifact <path>]",
            file=sys.stderr,
        )
        sys.exit(1)

    project_path = sys.argv[1]
    skill = sys.argv[2]
    status = sys.argv[3]
    message = sys.argv[4]
    artifact_rel = ""

    if "--artifact" in sys.argv:
        idx = sys.argv.index("--artifact")
        if idx + 1 < len(sys.argv):
            artifact_rel = sys.argv[idx + 1]

    notify(project_path, skill, status, message, artifact_rel)


if __name__ == "__main__":
    main()
```

**Step 2: Verify**

```bash
cd scripts/vps && python3 -c "import event_writer; print('ok')"
```

Expected: `ok`

**Acceptance:**
- [ ] `python3 -c "import event_writer; print('ok')"` works (EC-3)
- [ ] CLI `python3 event_writer.py /tmp test done "hello"` writes JSON to `/tmp/ai/openclaw/pending-events/`
- [ ] `wake_openclaw()` returns False gracefully when binary missing
- [ ] LOC < 130

---

### Task 2: Create orchestrator.py (replaces orchestrator.sh + inbox-processor.sh)

**Files:**
  - Create: `scripts/vps/orchestrator.py`

**Context:** Main daemon. Poll loop: hot-reload projects, git pull, scan inbox, scan backlog, dispatch tasks via pueue. Absorbs all logic from orchestrator.sh (426 LOC) and inbox-processor.sh (246 LOC). Must stay under 400 LOC.

**Step 1: Create `scripts/vps/orchestrator.py`**

The coder must implement ALL of the following functions with COMPLETE code (not pseudocode). The function list and behavioral contracts are specified here; the coder writes the actual implementation.

```python
#!/usr/bin/env python3
"""
Module: orchestrator
Role: Main poll loop daemon — scan inbox, scan backlog, dispatch via pueue.
Uses: db (import), subprocess (pueue CLI), signal, threading
Used by: systemd (dld-orchestrator.service)

Replaces orchestrator.sh + inbox-processor.sh (ARCH-161).
"""
```

**Functions to implement (with exact signatures):**

1. `_load_env() -> None` — Load .env file from SCRIPT_DIR (manual parser, no dotenv dependency). Sets env vars.

2. `_setup_logging() -> None` — Configure JSON structured logging to LOG_DIR with daily rotation (7 day retention). Use `logging.handlers.TimedRotatingFileHandler`.

3. `_signal_handler(signum: int, frame) -> None` — Set `_stop` threading.Event. Registered for SIGTERM and SIGINT.

4. `_write_pid() -> None` — Write PID to `SCRIPT_DIR/.orchestrator.pid`. Cleanup on exit via atexit.

5. `sync_projects() -> None` — Read PROJECTS_JSON if mtime changed. Call `db.seed_projects_from_json(projects)`. Log count.

6. `is_agent_running(project_id: str) -> bool` — `pueue status --json` → check if any task with label starting `{project_id}:` has status Running. Return False on any error.

7. `git_pull(project_id: str, project_dir: str) -> bool` — Skip if `is_agent_running`. If clean: `git pull --rebase origin develop`. If dirty: `git fetch origin develop` then `git rebase --autostash origin/develop` (abort on failure). Return True on success.

8. `_parse_inbox_file(filepath: Path) -> dict` — Extract from markdown: Route (default "spark"), Source (default "openclaw"), Provider (optional override), Context (optional), idea_text (body after `---` separator, max 50 lines, joined with spaces). Return dict with keys: route, source, provider, context, idea_text.

9. `_route_to_skill(route: str) -> str` — Map route string to skill: spark, architect, council, spark_bug->spark, bughunt, qa, reflect, scout. Default: spark.

10. `_pueue_add(group: str, label: str, cmd: list[str], env: dict[str,str] | None = None) -> int | None` — `subprocess.run(["pueue", "add", "--group", group, "--label", label, "--print-task-id", "--"] + cmd, ...)`. Parse stdout for task ID (integer). Return None on failure.

11. `scan_inbox(project_id: str, project_dir: str) -> int` — Scan `ai/inbox/*.md` for `**Status:** new`. For each: parse metadata, mark as processing, move to done/, resolve provider (db default, file override), build headless command prefix `[headless] Source: {source}. Context: {context}. {idea_text}`, write task-cmd to temp file, `_pueue_add` to `{provider}-runner` group with label `{project_id}:inbox-{YYYYMMDD-HHMMSS}`, set env CLAUDE_PROJECT_DIR and CLAUDE_CURRENT_SPEC_PATH, acquire slot, log_task, update_project_phase to "processing_inbox". Return count processed.

12. `scan_backlog(project_id: str, project_dir: str) -> bool` — Read `ai/backlog.md`, grep for first `| queued |` line, extract spec_id (TECH|FTR|BUG|ARCH-NNN). Find spec file in `ai/features/`. Resolve provider (db default, spec frontmatter `provider:` override). Check `db.get_available_slots(provider)`. `_pueue_add` with label `{project_id}:{spec_id}`, `db.try_acquire_slot`, `db.log_task`, `db.update_project_phase("autopilot", spec_id)`. Return True if dispatched.

13. `dispatch_night_review() -> None` — Check `.review-trigger` file. If exists, read project IDs, delete file, `_pueue_add` to night-reviewer group.

14. `process_project(project_id: str, project_dir: str) -> None` — Call git_pull, scan_inbox, scan_backlog, dispatch_qa_invariant (check qa_pending with empty current_task -> reset to idle).

15. `main() -> None` — Setup logging, load env, write PID, register signal handlers, enter poll loop: sync_projects, dispatch_night_review, get_all_projects, process each, check .run-now trigger files, `_stop.wait(POLL_INTERVAL)`.

**Key behavioral contracts from orchestrator.sh + inbox-processor.sh:**

- `scan_inbox` MUST mark files `**Status:** processing` and move to `done/` directory BEFORE dispatching to pueue (prevents double-submission).
- `scan_inbox` MUST write the task command to a temp file `SCRIPT_DIR/.task-cmd-{ts}.txt` because task text may contain shell metacharacters. run-agent.sh reads and deletes this file.
- `scan_inbox` MUST set env vars `CLAUDE_PROJECT_DIR` and `CLAUDE_CURRENT_SPEC_PATH` for the pueue task (3-hop contract for Spark to write SpecID back).
- `scan_backlog` MUST check `db.get_available_slots(provider) >= 1` before submission.
- `scan_backlog` MUST handle task-level provider override from spec frontmatter `provider: <name>`.
- `git_pull` MUST skip when agent is running (check pueue status for running tasks with matching project_id label prefix).
- `git_pull` MUST handle dirty working tree with `--autostash` and abort failed rebase.
- `.run-now-{project_id}` trigger files force immediate processing (delete trigger, log, process).
- `.review-trigger` file contains space-separated project IDs for night review dispatch.
- Inbox task pueue invocation: `run-agent.sh <project_dir> <provider> <skill> <task_file>`.
- Backlog autopilot invocation: `run-agent.sh <project_dir> <provider> autopilot "/autopilot {spec_id}"`.
- Route mapping: spark, architect, council, spark_bug->spark, bughunt, qa, reflect, scout. Unknown -> spark.
- Headless prefix: `[headless] Source: {source}. Context: {context}. {idea_text}`.
- The `_pueue_add` for inbox tasks must pass env vars. Use pueue's mechanism or export before call. Note: pueue v4 does NOT have `--env` flag. Use `os.environ` before subprocess call (child inherits parent env).

**Step 2: Verify**

```bash
cd scripts/vps && python3 -c "import orchestrator; print('ok')"
```

Expected: `ok`

**Acceptance:**
- [ ] `python3 -c "import orchestrator"` — no syntax errors (EC-1)
- [ ] Signal handling: SIGTERM sets `_stop`, loop exits cleanly
- [ ] `scan_inbox` correctly parses Route/Provider/Source/Context from inbox files
- [ ] `scan_backlog` correctly finds first queued spec
- [ ] `git_pull` skips when agent running, handles dirty worktree
- [ ] LOC <= 400 (split if needed)

---

### Task 3: Create callback.py (replaces pueue-callback.sh + qa-loop.sh)

**Files:**
  - Create: `scripts/vps/callback.py`

**Context:** Pueue callback script. Called on EVERY task completion/failure. MUST always exit 0 regardless of internal errors. Replaces pueue-callback.sh (478 LOC) and absorbs QA dispatch logic from qa-loop.sh (115 LOC).

**Step 1: Create `scripts/vps/callback.py`**

The coder must implement ALL functions with COMPLETE code. The critical invariant is: **every operation wrapped in try/except, script NEVER exits non-zero**.

```python
#!/usr/bin/env python3
"""
Module: callback
Role: Pueue completion callback — release slot, update phase, dispatch QA/Reflect, write events.
Uses: db (import), event_writer (import), subprocess (pueue CLI)
Used by: Pueue daemon (via pueue.yml callback config)

Replaces pueue-callback.sh + qa-loop.sh (ARCH-161).

CLI: python3 callback.py <pueue_id> '<group>' '<result>'
Pueue v4.0.4 callback template: callback.py {{ id }} '{{ group }}' '{{ result }}'

INVARIANT: Always exit 0. Every step in try/except.
"""
```

**Functions to implement (with exact signatures):**

1. `_load_env() -> None` — Same as orchestrator.py: manual .env parser from SCRIPT_DIR.

2. `_setup_logging() -> None` — Append-mode file logging to `SCRIPT_DIR/callback-debug.log`. Also log to stderr for pueue capture.

3. `resolve_label(pueue_id: str) -> str` — `pueue status --json` -> parse `tasks[pueue_id].label`. Return "unknown" on any error. Pueue v4 status JSON structure: `{"tasks": {"<id>": {"label": "...", "status": {...}, ...}}}`.

4. `parse_label(label: str) -> tuple[str, str]` — `label.split(":", 1)` -> (project_id, task_label). Guard: if no colon, return (label, label) and log warning.

5. `map_result(result: str) -> tuple[str, int]` — Parse pueue result string. "Success" -> ("done", 0). Anything else -> ("failed", 1). Return (status, exit_code).

6. `extract_agent_output(pueue_id: str) -> tuple[str, str]` — `pueue log {pueue_id} --json` -> parse for last JSON line containing "skill" key. Extract skill and result_preview (truncated to 500 chars). Return ("", "") on failure.

7. `resolve_spec_id(task_label: str, preview: str, project_path: str) -> str | None` — Multi-layer resolution (from pueue-callback.sh:89-123):
   - Layer 1: regex `(TECH|FTR|BUG|ARCH)-[0-9]+` in task_label
   - Layer 2: same regex in preview text
   - Layer 3: if task_label starts with "inbox-", grep `**SpecID:**` in `{project_path}/ai/inbox/done/*.md`
   - Return None if all layers fail.

8. `is_already_queued(label: str) -> bool` — `pueue status --json` -> check if any task with this exact label has status Running or Queued. Return False on error.

9. `dispatch_qa(project_id: str, project_path: str, spec_id: str, provider: str) -> None` — Build label `{project_id}:qa-{spec_id}`. Check `is_already_queued`. If not queued: `_pueue_add(group="{provider}-runner", label=qa_label, cmd=["run-agent.sh", project_path, provider, "qa", "/qa {spec_id}"])`.

10. `dispatch_reflect(project_id: str, project_path: str, task_label: str, provider: str) -> None` — Label `{project_id}:reflect-{task_label}`. Same pattern as dispatch_qa but with `/reflect`.

11. `write_event(project_path: str, skill: str, status: str, task_label: str) -> None` — Resolve artifact_rel (for qa: latest file in ai/qa/; for reflect: latest findings-*.md in ai/reflect/). Call `event_writer.notify(project_path, skill, status, message, artifact_rel)`. Only for skills: autopilot, qa, reflect.

12. `_pueue_add(group: str, label: str, cmd: list[str]) -> int | None` — Same pattern as orchestrator.py.

13. `main() -> None` — Parse sys.argv (pueue_id, group, result). Wrap entire body in try/except with sys.exit(0). Steps:
    - Skip night-reviewer group early
    - resolve_label -> parse_label -> map_result
    - db.release_slot(pueue_id)
    - db.finish_task(pueue_id, status, exit_code)
    - Determine new_phase: done + non-inbox -> qa_pending; done + inbox -> idle; failed -> failed
    - db.update_project_phase(project_id, new_phase, current_task)
    - extract_agent_output -> skill, preview
    - write_event (if applicable skill)
    - If skill == "autopilot" and status == "done": resolve_spec_id, dispatch_qa, dispatch_reflect
    - Exit 0

**Key behavioral contracts from pueue-callback.sh:**

- Label resolution: `pueue status --json` -> `data["tasks"][pueue_id]["label"]`. In Pueue v4 JSON, task IDs are string keys.
- Phase transition logic (lines 130-149): done + non-inbox label = qa_pending, done + inbox label = idle, failed = failed.
- QA dispatch (lines 390-443): only after `skill == "autopilot"` and `status == "done"`. Resolve spec_id via 3-layer resolution. Skip if no spec_id resolved for inbox tasks.
- Reflect dispatch (lines 446-471): unconditional after autopilot success (agents own diary writes). Idempotent check.
- QA label: `{project_id}:qa-{spec_id}` (NOT `qa-{task_label}`).
- Reflect label: `{project_id}:reflect-{task_label}`.
- OpenClaw events (lines 345-383): write for autopilot/qa/reflect on success, and for qa on failure. Artifact resolution: qa -> latest `ai/qa/{ts}-{spec}.md`, reflect -> latest `ai/reflect/findings-*.md`.
- Agent JSON output (lines 162-189): `pueue log {id} --json` -> look for JSON object with "skill" key. Fallback: grep for result_preview.
- Night-reviewer group skip (lines 75-79): early exit 0.

**Step 2: Verify**

```bash
cd scripts/vps && python3 -c "import callback; print('ok')"
python3 scripts/vps/callback.py 999 "test-group" "Success"; echo "exit: $?"
```

Expected: `ok`, then `exit: 0` (with logged error about invalid pueue_id).

**Acceptance:**
- [ ] `python3 -c "import callback"` — no syntax errors (EC-2)
- [ ] `python3 callback.py 999 "test-group" "Success"` exits 0 (EC-4)
- [ ] Never exits non-zero under any circumstances — wrap main() in try/except
- [ ] Correctly resolves label from pueue status JSON
- [ ] Dispatches QA + Reflect only after autopilot success
- [ ] LOC <= 400

---

### Task 4: Clean db.py — remove Telegram-specific functions

**Files:**
  - Modify: `scripts/vps/db.py`

**Context:** Remove functions and constants only used by deleted Telegram files. Keep core orchestrator + night-reviewer functions and CLI commands.

**Step 1: Remove Telegram-specific code from db.py**

Delete the following items by their EXACT line ranges (verified against current file):

1. **Line 19:** `DEFAULT_CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "0") or "0")` — Remove entirely.

2. **Lines 24-46:** `_ensure_runtime_schema()` function — Remove entirely. The chat_id column and unique index are already in schema.sql (lines 12, 22-24). The runtime migration was for old VPS DBs that pre-date schema.sql; after this rewrite, schema.sql re-apply is required anyway.

3. **Line 66:** `_ensure_runtime_schema(conn)` call inside `get_db()` — Remove this line.

4. **Lines 132-146:** `get_project_by_topic()` function — Remove entirely. Only used by telegram-bot.py and handlers.

5. **Lines 249-271:** `add_project()` function — Remove entirely. Only used by admin_handler.py.

6. **Lines 274-282:** `set_project_topic()` function — Remove entirely. Only used by Telegram /bindtopic command.

7. **Lines 285-293:** `get_nexus_cache()` function — Remove entirely. Only used by admin_handler.py.

8. **Lines 221-246:** In `seed_projects_from_json()` — Remove `chat_id` references:
   - Remove `DEFAULT_CHAT_ID or None` from INSERT
   - Remove `COALESCE(excluded.chat_id, project_state.chat_id)` from ON CONFLICT
   - Keep: project_id, path, topic_id, provider, auto_approve_timeout (topic_id stays for potential future use and schema compat)

9. **Lines 391-410:** `callback` CLI command in `__main__` — Remove entirely. New callback.py imports db functions directly. No bash caller needs this anymore.

10. **Module docstring (lines 6-9):** Update `Used by:` to reference orchestrator.py, callback.py, night-reviewer.sh (CLI).

11. **Update `__main__` usage message** to remove `callback` from the options string.

**Step 2: Verify**

```bash
cd scripts/vps
python3 -c "import db; print(db.get_all_projects()); print('ok')"
python3 db.py save-finding test fp1 medium high test.py 1-5 "test summary" "test suggestion"
python3 db.py update-phase test idle
```

**Acceptance:**
- [ ] `grep -c "get_project_by_topic\|add_project\|set_project_topic\|get_nexus_cache" scripts/vps/db.py` returns 0 (EC-7)
- [ ] `grep -c "DEFAULT_CHAT_ID\|TELEGRAM_CHAT_ID\|_ensure_runtime_schema" scripts/vps/db.py` returns 0
- [ ] `grep -c "callback" scripts/vps/db.py` returns 0 (no CLI callback command)
- [ ] `python3 -c "import db; db.get_all_projects()"` still works
- [ ] CLI commands `save-finding`, `get-new-findings`, `update-finding-status`, `update-phase`, `seed` still work
- [ ] File stays under 300 LOC after cleanup

---

### Task 5: Update night-reviewer.sh — notify.py → event_writer.py

**Files:**
  - Modify: `scripts/vps/night-reviewer.sh`

**Context:** night-reviewer.sh calls `python3 notify.py <project_id> <msg>` at line 215. Replace with event_writer.py CLI. Also update module docstring at line 11.

**Step 1: Update module docstring (line 11)**

Change:
```
# Uses: db.py (update-phase, save-finding, get-new-findings), notify.py, claude CLI, flock
```
To:
```
# Uses: db.py (update-phase, save-finding, get-new-findings), event_writer.py, claude CLI, flock
```

**Step 2: Replace notify.py call (line 215)**

The current code at line 215:
```bash
            python3 "${SCRIPT_DIR}/notify.py" "${PROJECT_ID}" "${msg}" 2>/dev/null
```

The variable `PROJECT_PATH` is already available in the `process_project` function (set at line 88-94 via db lookup). Replace with:
```bash
            python3 "${SCRIPT_DIR}/event_writer.py" "${PROJECT_PATH}" "night-review" "done" "${msg}" 2>/dev/null
```

Note: `PROJECT_PATH` is already resolved at line 88-94 of the process_project function as a local variable. The notify.py call is inside this same function, so PROJECT_PATH is in scope.

**Step 3: Verify**

```bash
bash -n scripts/vps/night-reviewer.sh
grep -c "notify.py" scripts/vps/night-reviewer.sh
grep -c "event_writer.py" scripts/vps/night-reviewer.sh
```

Expected: exit 0, `0`, `>= 1`

**Acceptance:**
- [ ] `grep -c "notify.py" scripts/vps/night-reviewer.sh` returns 0 (EC-10 partial)
- [ ] `grep -c "event_writer.py" scripts/vps/night-reviewer.sh` returns >= 1 (EC-10)
- [ ] `bash -n scripts/vps/night-reviewer.sh` exits 0 (syntax valid)
- [ ] `PROJECT_PATH` variable is in scope at the call site

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
  - Delete: `scripts/vps/tests/test_cycle_smoke.py`
  - Delete: `scripts/vps/tests/test_notify.py`
  - Delete: `scripts/vps/tests/test_approve_handler.py`
  - Delete: `scripts/vps/tests/test_artifact_scan.py`

**Note:** `db_exec.sh` is NOT in this list -- it does not exist in the worktree (already absent). Do not attempt to delete it.

**Total:** 10 script files + 4 test files = 14 file deletions

**Step 1: Delete via git rm**

```bash
cd /home/dld/projects/dld/.worktrees/ARCH-161
git rm scripts/vps/telegram-bot.py
git rm scripts/vps/admin_handler.py
git rm scripts/vps/approve_handler.py
git rm scripts/vps/photo_handler.py
git rm scripts/vps/voice_handler.py
git rm scripts/vps/notify.py
git rm scripts/vps/orchestrator.sh
git rm scripts/vps/pueue-callback.sh
git rm scripts/vps/inbox-processor.sh
git rm scripts/vps/qa-loop.sh
git rm scripts/vps/tests/test_cycle_smoke.py
git rm scripts/vps/tests/test_notify.py
git rm scripts/vps/tests/test_approve_handler.py
git rm scripts/vps/tests/test_artifact_scan.py
```

**Step 2: Verify no dangling imports in remaining files**

```bash
grep -rn "telegram-bot\|approve_handler\|photo_handler\|voice_handler\|admin_handler" \
  scripts/vps/*.py scripts/vps/*.sh 2>/dev/null || echo "PASS"
```

**Acceptance:**
- [ ] None of the 14 deleted files exist on disk (EC-5)
- [ ] Old tests deleted (EC-12)
- [ ] No dangling imports to deleted modules in remaining .py/.sh files

---

### Task 7: Update setup-vps.sh

**Files:**
  - Modify: `scripts/vps/setup-vps.sh`
  - Modify: `scripts/vps/.env.example`

**Context:** Update pueue callback path, orchestrator systemd unit, remove Telegram bot service, clean .env.example.

**Step 1: Update pueue callback line (line 226)**

Change:
```bash
CALLBACK_LINE="${SCRIPT_DIR}/pueue-callback.sh {{ id }} '{{ label }}' '{{ group }}' '{{ result }}'"
```
To:
```bash
CALLBACK_LINE="${SCRIPT_DIR}/venv/bin/python3 ${SCRIPT_DIR}/callback.py {{ id }} '{{ group }}' '{{ result }}'"
```

Note: `{{ label }}` is intentionally removed -- Pueue v4.0.4 does NOT support `{{ label }}` in callback templates. The new callback.py resolves labels via `pueue status --json`.

**Step 2: Update orchestrator systemd unit (line 367)**

Change:
```
ExecStart=${SCRIPT_DIR}/orchestrator.sh
```
To:
```
ExecStart=${SCRIPT_DIR}/venv/bin/python3 ${SCRIPT_DIR}/orchestrator.py
```

**Step 3: Remove Telegram bot systemd unit (lines 387-409)**

Delete the entire block:
```bash
cat > "${SYSTEMD_DIR}/dld-telegram-bot.service" << EOF
...
EOF
```

**Step 4: Update post-setup messages (lines 416-429)**

Remove references to `dld-telegram-bot`:
- Line 424: `echo "  systemctl --user enable --now dld-telegram-bot"` — delete
- Line 428: `echo "  systemctl --user status dld-telegram-bot"` — delete
- Line 286: `echo "  # Then fill in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"` — change to `echo "  # Then fill in your API keys and project paths"`

**Step 5: Update .env.example**

Remove these lines (lines 5-14 of .env.example):
```
# Telegram Bot
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ALLOWED_USERS=123456789

# Operations fallback topic (for projects without /bindtopic)
OPS_TOPIC_ID=

# Groq (Voice Transcription)
GROQ_API_KEY=
```

Also remove `QA_TIMEOUT=600` (line 22) -- qa-loop.sh is deleted, QA is now dispatched by callback.py via pueue.

**Step 6: Verify**

```bash
bash -n scripts/vps/setup-vps.sh
grep -c "orchestrator.sh" scripts/vps/setup-vps.sh
grep -c "pueue-callback.sh" scripts/vps/setup-vps.sh
grep -c "telegram-bot.py" scripts/vps/setup-vps.sh
grep -c "orchestrator.py" scripts/vps/setup-vps.sh
grep -c "callback.py" scripts/vps/setup-vps.sh
```

Expected: exit 0, 0, 0, 0, >= 1, >= 1

**Acceptance:**
- [ ] `bash -n scripts/vps/setup-vps.sh` exits 0
- [ ] `grep -c "orchestrator.sh" scripts/vps/setup-vps.sh` returns 0 (EC-9)
- [ ] `grep -c "pueue-callback.sh" scripts/vps/setup-vps.sh` returns 0 (EC-9)
- [ ] `grep -c "telegram-bot.py" scripts/vps/setup-vps.sh` returns 0 (EC-9)
- [ ] `grep -c "orchestrator.py" scripts/vps/setup-vps.sh` returns >= 1 (EC-8)
- [ ] `grep -c "callback.py" scripts/vps/setup-vps.sh` returns >= 1
- [ ] .env.example has no TELEGRAM_* vars
- [ ] dld-telegram-bot.service block removed entirely

---

### Task 8: Update docs — dependencies.md, completion.md, night-mode.md

**Files:**
  - Modify: `.claude/rules/dependencies.md`
  - Modify: `.claude/skills/spark/completion.md` (line 190)
  - Modify: `.claude/skills/audit/night-mode.md` (line 91)

**Step 1: Update completion.md (line 190)**

Change:
```
   - This enables pueue-callback.sh to resolve real spec_id for QA dispatch
```
To:
```
   - This enables callback.py to resolve real spec_id for QA dispatch
```

**Step 2: Update night-mode.md (line 91)**

Change:
```
  └─ New findings → Telegram via notify.py
```
To:
```
  └─ New findings → OpenClaw via event_writer.py
```

**Step 3: Rewrite dependencies.md**

Remove ALL sections for deleted files:
- `scripts/vps/telegram-bot.py`
- `scripts/vps/notify.py`
- `scripts/vps/approve_handler.py`
- `scripts/vps/photo_handler.py`
- `scripts/vps/voice_handler.py`
- `scripts/vps/admin_handler.py`
- `scripts/vps/orchestrator.sh`
- `scripts/vps/pueue-callback.sh`
- `scripts/vps/inbox-processor.sh`
- `scripts/vps/qa-loop.sh`

Add NEW sections for:

**scripts/vps/orchestrator.py:**
- Uses: db.py (seed_projects_from_json, get_all_projects, get_project_state, get_available_slots, try_acquire_slot, log_task, update_project_phase), run-agent.sh (pueue add dispatch), night-reviewer.sh (pueue add --group night-reviewer), pueue CLI, git CLI, projects.json
- Used by: systemd (dld-orchestrator.service)
- When changing: check callback.py (label format), run-agent.sh (arg order), db.py signatures

**scripts/vps/callback.py:**
- Uses: db.py (release_slot, finish_task, update_project_phase, get_project_state), event_writer.py (notify), run-agent.sh (pueue add for QA/Reflect), pueue CLI (status --json, log --json, add)
- Used by: Pueue daemon (pueue.yml callback config)
- When changing: check pueue.yml (arg order: id group result), run-agent.sh (arg order), event_writer.py (notify signature), schema.sql column names

**scripts/vps/event_writer.py:**
- Uses: openclaw CLI (~/.npm-global/bin/openclaw)
- Used by: callback.py (import: notify), night-reviewer.sh (CLI: python3 event_writer.py)
- When changing: check callback.py (notify import), night-reviewer.sh (CLI arg order)

Update EXISTING sections:
- **db.py**: Remove telegram-bot.py, notify.py, approve_handler.py, admin_handler.py from "Used by". Add orchestrator.py, callback.py. Remove CLI callback from "Used by".
- **run-agent.sh**: Remove orchestrate.sh, pueue-callback.sh from "Used by". Add orchestrator.py (pueue add), callback.py (QA/Reflect dispatch).
- **night-reviewer.sh**: Replace notify.py with event_writer.py in "Uses". Replace orchestrator.sh with orchestrator.py in "Used by".
- **setup-vps.sh**: Replace pueue-callback.sh with callback.py, orchestrator.sh with orchestrator.py, remove telegram-bot.py references.
- **nexus-cache-refresh.sh**: Remove admin_handler.py from "Used by" (admin_handler deleted).

Update **Last Update** table: add entry for ARCH-161 rewrite.

**Step 4: Verify**

```bash
grep -c "telegram-bot.py\|pueue-callback.sh\|orchestrator\.sh\|inbox-processor.sh\|qa-loop.sh\|notify\.py" .claude/rules/dependencies.md
grep -c "orchestrator.py\|callback.py\|event_writer.py" .claude/rules/dependencies.md
grep -c "pueue-callback.sh" .claude/skills/spark/completion.md
grep -c "notify.py" .claude/skills/audit/night-mode.md
```

Expected: 0, >= 3, 0, 0

**Acceptance:**
- [ ] `grep -c "telegram-bot.py\|pueue-callback.sh\|orchestrator\.sh\|inbox-processor.sh\|qa-loop.sh" .claude/rules/dependencies.md` returns 0 (EC-6, EC-11)
- [ ] `grep -c "orchestrator.py\|callback.py\|event_writer.py" .claude/rules/dependencies.md` returns >= 3 (EC-11)
- [ ] `grep -c "pueue-callback.sh" .claude/skills/spark/completion.md` returns 0
- [ ] `grep -c "notify.py" .claude/skills/audit/night-mode.md` returns 0
- [ ] No dangling references to deleted files across all docs

---

### Execution Order

```
Task 1 (event_writer.py)
  ↓
Task 2 (orchestrator.py)
  ↓
Task 3 (callback.py)        ← imports event_writer from Task 1
  ↓
Task 4 (db.py cleanup)
  ↓
Task 5 (night-reviewer.sh)  ← calls event_writer.py CLI from Task 1
  ↓
Task 6 (delete old files)   ← all replacements ready from Tasks 1-5
  ↓
Task 7 (setup-vps.sh)       ← references new files, old files deleted
  ↓
Task 8 (docs)               ← all changes finalized, update references
```

Task 1 (event_writer.py) FIRST — dependency for Task 3 (import) and Task 5 (CLI).
Tasks 2, 3 are strictly sequential (both create new files, no conflict, but callback tests need orchestrator patterns).
Task 4 (db.py) after Tasks 2-3 because they import db — must verify db cleanup doesn't break imports.
Task 5 (night-reviewer.sh) after Task 1 (needs event_writer.py to exist).
Task 6 (delete) MUST be after Tasks 1-5 (new replacements exist before old deleted).
Task 7 (setup-vps.sh) after Task 6 (old files deleted, verifications clean).
Task 8 (docs) LAST — references final state of all files.

### Dependencies
- Task 3 depends on Task 1 (imports event_writer)
- Task 5 depends on Task 1 (calls event_writer.py CLI)
- Task 6 depends on Tasks 1-5 (new replacements ready)
- Task 7 depends on Task 6 (old files deleted, grep checks clean)
- Task 8 depends on Task 7 (all file changes done)

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
| EC-1 | orchestrator.py syntax valid | `cd scripts/vps && python3 -c "import orchestrator"` | exit 0 | deterministic | codebase | P0 |
| EC-2 | callback.py syntax valid | `cd scripts/vps && python3 -c "import callback"` | exit 0 | deterministic | codebase | P0 |
| EC-3 | event_writer.py syntax valid | `cd scripts/vps && python3 -c "import event_writer"` | exit 0 | deterministic | codebase | P0 |
| EC-4 | callback.py always exits 0 | `cd scripts/vps && python3 callback.py 999 "test" "Success"; echo $?` | 0 | deterministic | external | P0 |
| EC-5 | No deleted files remain | `ls scripts/vps/telegram-bot.py scripts/vps/orchestrator.sh scripts/vps/pueue-callback.sh 2>&1` | all "No such file" | deterministic | devil | P0 |
| EC-6 | No dangling references to deleted files | `grep -rn "telegram-bot.py\|pueue-callback.sh\|orchestrator\.sh\|inbox-processor.sh\|qa-loop.sh" scripts/vps/*.py scripts/vps/*.sh .claude/rules/dependencies.md 2>/dev/null` | 0 results | deterministic | devil | P0 |
| EC-7 | db.py Telegram functions removed | `grep -c "get_project_by_topic\|add_project\|set_project_topic\|get_nexus_cache" scripts/vps/db.py` | 0 | deterministic | codebase | P1 |
| EC-8 | setup-vps.sh references new files | `grep -c "orchestrator.py" scripts/vps/setup-vps.sh` | >= 1 | deterministic | devil | P0 |
| EC-9 | setup-vps.sh no old references | `grep -c "orchestrator\.sh\|pueue-callback.sh\|telegram-bot.py" scripts/vps/setup-vps.sh` | 0 | deterministic | devil | P0 |
| EC-10 | night-reviewer.sh uses event_writer | `grep -c "event_writer" scripts/vps/night-reviewer.sh` | >= 1 | deterministic | devil | P0 |
| EC-11 | dependencies.md updated | `grep -c "orchestrator.py\|callback.py\|event_writer.py" .claude/rules/dependencies.md` | >= 3 | deterministic | codebase | P1 |
| EC-12 | Old tests deleted | `ls scripts/vps/tests/test_cycle_smoke.py scripts/vps/tests/test_notify.py scripts/vps/tests/test_approve_handler.py 2>&1` | all "No such file" | deterministic | devil | P0 |

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
