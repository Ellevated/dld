# External Research — ARCH-161: Orchestrator Radical Rewrite

## Best Practices

### 1. Python Poll Loop with Signal-Driven Graceful Shutdown

**Source:** [Stopping a Python systemd service cleanly](https://alexandra-zaharia.github.io/posts/stopping-python-systemd-service-cleanly/)
**Source 2:** [Signal Handling in Python: Custom Handlers for Graceful Shutdowns](https://johal.in/signal-handling-in-python-custom-handlers-for-graceful-shutdowns/)

**Summary:** A long-running Python daemon should install `signal.signal(signal.SIGTERM, handler)` and `signal.signal(signal.SIGINT, handler)`. The handler sets a `threading.Event` (or a simple `bool` flag) that the main poll loop checks via `event.wait(timeout=POLL_INTERVAL)`. This lets `systemctl stop` wake the sleeping loop instantly rather than waiting for the full sleep to expire — median shutdown time drops from `POLL_INTERVAL/2` to under 1 second.

**Why relevant:** The new `orchestrator.py` runs as a systemd service with a 300-second poll interval. Without this pattern, `systemctl stop` blocks for up to 5 minutes.

**Minimal pattern:**
```python
import signal, threading

_stop = threading.Event()

def _handle_signal(signum, frame):
    _stop.set()

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)

while not _stop.is_set():
    run_cycle()
    _stop.wait(timeout=POLL_INTERVAL)
```

---

### 2. SQLite WAL + BEGIN IMMEDIATE for Single-Writer Concurrency

**Source:** [SQLite concurrent writes and "database is locked" errors](https://tenthousandmeters.com/blog/sqlite-concurrent-writes-and-database-is-locked-errors/)
**Source 2:** [SQLite Transactions: A Practical Guide](https://thelinuxcode.com/sqlite-transactions-a-practical-guide-to-autocommit-wal-savepoint-and-production-patterns/)

**Summary:** WAL mode allows concurrent readers during a write transaction (unlike the default DELETE journal which locks the whole file). `BEGIN IMMEDIATE` acquires the write lock upfront, eliminating "database is locked" errors when multiple processes compete for writes (orchestrator.py + callback.py run as separate processes). `PRAGMA busy_timeout=5000` adds automatic retry for 5 seconds before raising an error.

**Why relevant:** `orchestrator.py` (poll loop) and `callback.py` (fired by Pueue on task completion) both write to SQLite concurrently. The existing `db.py` already uses this pattern — it must be preserved verbatim in the clean rewrite.

**Key settings (already in db.py — do not change):**
```python
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=5000")
# BEGIN IMMEDIATE for slot acquisition:
conn.execute("BEGIN IMMEDIATE")
```

---

### 3. Pueue v4 Callback — Template Variables and Label Resolution

**Source:** [Pueue pueue-callback.sh (existing implementation)](../../../scripts/vps/pueue-callback.sh) — lines 6-14
**Source 2:** [Pueue Configuration Wiki](https://github.com/Nukesor/pueue/wiki/Configuration)
**Source 3:** [Pueue v4.0.0 release notes](https://www.heise.de/en/news/pueue-4-0-0-is-here-Task-management-tool-manages-tasks-without-delays-10311784.html)

**Summary:** Pueue v4.0.4 (current, latest as of 2026-03-02) exposes these template variables in `pueue.yml` callback:
- `{{ id }}` — numeric pueue task id
- `{{ group }}` — pueue group name (e.g. `claude-runner`)
- `{{ result }}` — result string: `Success`, `Failed(N)`, `Killed`, `Errored(N)`

**Critical finding:** `{{ label }}` is NOT available in callback template variables in v4.0.4. Label must be resolved at runtime via `pueue status --json | python3 -c "..."`. This is a known limitation documented in the existing `pueue-callback.sh` header comment.

**Why relevant:** `callback.py` must replicate the label-resolution logic from the existing bash script. The Python subprocess call pattern:
```python
import subprocess, json

result = subprocess.run(["pueue", "status", "--json"], capture_output=True, text=True)
data = json.loads(result.stdout)
label = data.get("tasks", {}).get(str(pueue_id), {}).get("label", "unknown")
```

---

### 4. Idempotent Callbacks — Deterministic IDs + Guarded Upserts

**Source:** [How to Build Idempotent Cloud Tasks Handlers in Python](https://dev.to/humzakt/how-to-build-idempotent-cloud-tasks-handlers-in-python-the-pattern-that-eliminated-our-duplicate-4gml)
**Source 2:** [Idempotency Patterns: Building Retry-Safe Distributed Systems](https://backendbytes.com/articles/idempotency-patterns-distributed-systems)

**Summary:** Pueue fires the callback exactly once per task completion, but if `callback.py` crashes mid-execution (e.g. during slot release) and is re-invoked manually (or the callback itself is retried), it must be safe to re-run. The proven pattern:
1. Use the pueue task ID as a natural idempotency key (it's stable and unique).
2. Use `INSERT OR IGNORE` / `ON CONFLICT DO NOTHING` for `task_log` entries.
3. Use `UPDATE ... WHERE status != 'done'` guards for phase transitions to avoid regressing a completed task.
4. The slot release (`DELETE FROM compute_slots WHERE pueue_id = ?`) is naturally idempotent (DELETE of a non-existent row is a no-op).

**Why relevant:** `callback.py` must be crash-safe. If it fails after releasing the slot but before writing `task_log`, re-invocation must not double-release or corrupt the phase.

---

### 5. Hot-Reload via mtime Check (Polling, Not inotify)

**Source:** [How to Build a Config System with Hot Reload in Python](https://oneuptime.com/blog/post/2026-01-22-config-hot-reload-python/view)
**Source 2:** [Keep Your Python Running: Reloading Configuration on the Fly with SIGHUP](https://medium.com/@snnapys-devops/keep-your-python-running-reloading-configuration-on-the-fly-with-sighup-8cac1179c24d)

**Summary:** Two approaches for hot-reload of `projects.json`:
- **Polling mtime** (simpler): each cycle compares `os.path.getmtime(PROJECTS_JSON)` to the last-seen value. If changed, reload + sync to SQLite. Zero dependencies, works across NFS/docker volumes.
- **SIGHUP handler** (classic): `signal.signal(signal.SIGHUP, reload_handler)`. Used by nginx, gunicorn. More explicit but requires operator action.

**Why relevant:** The existing orchestrator.sh hot-reloads `projects.json` every cycle (unconditionally). The Python rewrite should use **mtime-based polling** in the cycle (simpler, no inotify dependency, already the correct UX since the cycle is 300s). Example:

```python
_last_projects_mtime: float = 0.0

def maybe_reload_projects(path: Path) -> None:
    global _last_projects_mtime
    mtime = path.stat().st_mtime
    if mtime != _last_projects_mtime:
        projects = json.loads(path.read_text())
        db.seed_projects_from_json(projects)
        _last_projects_mtime = mtime
```

---

## Libraries/Tools

| Library | Version | Pros | Cons | Use Case | Source |
|---------|---------|------|------|----------|--------|
| `subprocess` (stdlib) | Python 3.10+ | No deps, `capture_output=True` idiom, `check=True` raises | Blocking; no async streaming | Calling `pueue add`, `pueue status --json`, `git pull` | [Python docs](https://docs.python.org/3.14/library/subprocess.html) |
| `watchdog` | 6.x | inotify-backed, event-driven, works cross-platform | Extra dependency; overkill for single-dir polling | File system events if polling latency matters | [watchdog docs](https://watchdog.readthedocs.io/en/stable) |
| `sqlite3` (stdlib) | Python 3.x | Already used, WAL+IMMEDIATE pattern established | Single-writer; not for high-concurrency writes | Orchestrator state (slots, tasks, projects) | [existing db.py](../../../scripts/vps/db.py) |
| `signal` (stdlib) | Python 3.x | SIGTERM/SIGINT handling, SIGHUP for reload | Cannot use in threads (only main thread) | Graceful shutdown, hot-reload trigger | [Python docs](https://docs.python.org/3/library/signal.html) |
| `threading.Event` (stdlib) | Python 3.x | Interruptible sleep (`event.wait(timeout)`) | Requires care with GIL | Replace `time.sleep()` in poll loops | [Python docs](https://docs.python.org/3/library/threading.html) |

**Recommendation:** Use only stdlib (`subprocess`, `sqlite3`, `signal`, `threading`, `json`, `pathlib`, `logging`). The rewrite target is ~450 LOC total across two files — external deps add more risk than value. The existing `db.py` dependency handles all database I/O.

---

## Production Patterns

### Pattern 1: Fail-Safe Callback with Structured Logging

**Source:** [Existing pueue-callback.sh](../../../scripts/vps/pueue-callback.sh) — lines 17-21, 84-109
**Description:** Every risky operation in the callback is wrapped in a try/except (Python equivalent of `|| true` in bash). The slot release and DB update happen in a single `BEGIN IMMEDIATE` transaction. If the transaction fails, a WARNING is logged but the script exits 0 — Pueue requires a 0 exit code to mark the task done. A non-zero exit causes Pueue to mark the task `Errored`, which triggers another callback firing (potential infinite loop).

**Real-world use:** The existing `pueue-callback.sh` already implements this; it has a `set -uo pipefail` but wraps every external call with `|| { log; }`. Python makes this cleaner with `try/except`.

**Fits us:** Yes — `callback.py` must never exit non-zero. The recommended structure:
```python
def main():
    try:
        release_slot_and_update_db(pueue_id, status, project_id)
    except Exception as e:
        log.error("db update failed: %s", e)
        # still continue — slot release failure must not prevent OpenClaw wake

    try:
        write_openclaw_event(project_id, skill, status, task_label)
    except Exception as e:
        log.error("openclaw event failed: %s", e)

    try:
        dispatch_qa_and_reflect(project_id, task_label, skill, status)
    except Exception as e:
        log.error("post-autopilot dispatch failed: %s", e)

    sys.exit(0)  # always
```

---

### Pattern 2: Duplicate-Dispatch Guard via Pueue Status Check

**Source:** [Existing pueue-callback.sh](../../../scripts/vps/pueue-callback.sh) — lines 371-393
**Description:** Before dispatching QA or Reflect after autopilot completion, the callback queries `pueue status --json` and checks whether a task with the same label is already `Running` or `Queued`. If yes, skip dispatch. This prevents double-dispatch when two autopilot tasks complete within the same callback window.

**Real-world use:** Already battle-tested in production. The Python port:
```python
def is_already_queued(label: str) -> bool:
    result = subprocess.run(["pueue", "status", "--json"], capture_output=True, text=True)
    data = json.loads(result.stdout)
    for task in data.get("tasks", {}).values():
        if task.get("label") == label:
            status = task.get("status", {})
            if isinstance(status, dict) and ("Running" in status or "Queued" in status):
                return True
    return False
```

**Fits us:** Yes — required for QA and Reflect dispatch idempotency.

---

### Pattern 3: Poll Loop with Project-Scoped Slot Check Before Dispatch

**Source:** [Existing orchestrator.sh](../../../scripts/vps/orchestrator.sh) — lines 97-157
**Description:** Before dispatching any task, check: (a) are there free compute slots globally? (b) is this project already running a task? Use `BEGIN IMMEDIATE` to atomically check-and-reserve. The SQL pattern:
```sql
-- try_acquire_slot: atomic reserve
BEGIN IMMEDIATE;
SELECT COUNT(*) FROM compute_slots WHERE project_id = ?;
-- if 0: INSERT INTO compute_slots ...
COMMIT;
```
If project already has a slot, skip all dispatch for that project and move to the next one.

**Real-world use:** SQLite `BEGIN IMMEDIATE` is used by production tools like Litestream, LiteFS, and the existing DLD orchestrator at scale.

**Fits us:** Yes — the existing `db.try_acquire_slot()` already implements this correctly. `orchestrator.py` must call it before `pueue add`.

---

### Pattern 4: Systemd Service with PID File and Restart Policy

**Source:** [Stopping a Python systemd service cleanly](https://alexandra-zaharia.github.io/posts/stopping-python-systemd-service-cleanly/)
**Source 2:** [Create Linux auto-restartable service on file change](https://piotrnowicki.com/posts/2024-07-25/create-linux-auto-restartable-service-on-file-change/)

**Description:** A well-formed systemd unit for a Python poll daemon:
```ini
[Unit]
Description=DLD Orchestrator
After=network.target

[Service]
Type=simple
ExecStart=/path/to/venv/bin/python3 /path/to/orchestrator.py
Restart=on-failure
RestartSec=10
WorkingDirectory=/path/to/scripts/vps
EnvironmentFile=/path/to/scripts/vps/.env
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Key choices:
- `Type=simple` (not `forking`) — Python daemon stays in foreground, systemd tracks it directly
- `Restart=on-failure` — auto-restart on crash, but not on clean `sys.exit(0)`
- No `PIDFile=` needed with `Type=simple`
- `StandardOutput=journal` — logs go to `journald`, accessible via `journalctl -u dld-orchestrator`

**Fits us:** Yes — the existing service uses this pattern (minus `Type=simple`, which should be explicit). `callback.py` is invoked by Pueue directly and does not need a systemd unit.

---

## Key Decisions Supported by Research

1. **Decision:** Keep `callback.py` as a standalone script (not a service), invoked by Pueue daemon via `pueue.yml callback:` setting.
   **Evidence:** Pueue's callback mechanism fires a subprocess per task completion. A long-running Python service would require IPC (Unix socket or HTTP) to receive completion events — significantly more complex. The existing bash callback pattern works; Python port is a direct translation.
   **Confidence:** High

2. **Decision:** Resolve pueue task label at runtime via `pueue status --json` in `callback.py`, not from template variables.
   **Evidence:** Pueue v4.0.4 confirmed: `{{ label }}` is NOT available in callback templates. This is documented in the existing `pueue-callback.sh` header (line 13) and verified by the codebase. The runtime resolution pattern is already battle-tested.
   **Confidence:** High

3. **Decision:** Use `threading.Event.wait(timeout)` instead of `time.sleep()` in the poll loop.
   **Evidence:** `threading.Event.wait(timeout)` is interruptible by `.set()` from a signal handler, enabling sub-second shutdown response. `time.sleep()` cannot be interrupted cleanly. This is the standard pattern for Python daemons with signal handling.
   **Confidence:** High

4. **Decision:** Use mtime-based `projects.json` hot-reload (check each cycle) instead of inotify/watchdog.
   **Evidence:** The existing orchestrator reloads every 300s unconditionally. mtime check adds negligible overhead and avoids a dependency. inotify requires `watchdog` library and is overkill for a config file that changes infrequently.
   **Confidence:** High

5. **Decision:** Keep `db.py` WAL + `BEGIN IMMEDIATE` + `busy_timeout=5000` pattern unchanged.
   **Evidence:** The existing pattern correctly handles the two-writer scenario (orchestrator + callback). Changing it risks introducing "database is locked" errors. SQLite WAL with a single writer at a time is production-proven for single-node orchestrators at this scale.
   **Confidence:** High

6. **Decision:** `callback.py` always exits 0, wrapping every operation in try/except.
   **Evidence:** Pueue marks a task `Errored` if the callback exits non-zero. An `Errored` state may trigger another callback invocation (depending on Pueue config), creating an infinite retry loop. The existing bash script uses `|| true` for the same reason. This is not optional.
   **Confidence:** High

---

## Pueue v4 Subprocess Patterns (Code Reference)

Based on the existing working implementation and Pueue v4.0.4 docs:

**Submit a task:**
```python
import subprocess

def pueue_add(group: str, label: str, cmd: list[str]) -> int:
    """Returns pueue task ID (int)."""
    result = subprocess.run(
        ["pueue", "add", "--group", group, "--label", label, "--print-task-id", "--"] + cmd,
        capture_output=True, text=True, check=True
    )
    return int(result.stdout.strip())
```

**Query running tasks:**
```python
def pueue_status() -> dict:
    result = subprocess.run(["pueue", "status", "--json"], capture_output=True, text=True)
    if result.returncode != 0:
        return {}
    return json.loads(result.stdout)
```

**Check if label already running/queued:**
```python
def label_is_active(label: str) -> bool:
    data = pueue_status()
    for task in data.get("tasks", {}).values():
        if task.get("label") == label:
            s = task.get("status", {})
            if isinstance(s, dict) and ("Running" in s or "Queued" in s):
                return True
    return False
```

**pueue.yml callback config (v4.x):**
```yaml
daemon:
  callback: "/path/to/scripts/vps/callback.py {{ id }} '{{ group }}' '{{ result }}'"
  callback_log_lines: 10
```

---

## Research Sources

- [Pueue GitHub (v4.0.4)](https://github.com/Nukesor/pueue/?tab=readme-ov-file) — latest release 2026-03-02, confirmed `{{ label }}` not in callback vars
- [Pueue Configuration Wiki](https://github.com/Nukesor/pueue/wiki/Configuration) — callback template variables, pueue.yml structure
- [Pueue Groups Wiki](https://github.com/Nukesor/pueue/wiki/Groups) — group parallelism, `pueue add -g`
- [Pueue Common Pitfalls Wiki](https://github.com/Nukesor/pueue/wiki/Common-Pitfalls-and-Debugging) — `sh -c` wrapping, label escaping
- [SQLite concurrent writes article](https://tenthousandmeters.com/blog/sqlite-concurrent-writes-and-database-is-locked-errors/) — WAL mode concurrency mechanics
- [SQLite Transactions production guide](https://thelinuxcode.com/sqlite-transactions-a-practical-guide-to-autocommit-wal-savepoint-and-production-patterns/) — BEGIN IMMEDIATE, busy_timeout patterns
- [SQLite production setup (2026)](https://oneuptime.com/blog/post/2026-02-02-sqlite-production-setup/view) — WAL configuration, single-server workloads
- [Python signal handling (graceful shutdown)](https://johal.in/signal-handling-in-python-custom-handlers-for-graceful-shutdowns/) — SIGTERM handler, threading.Event pattern
- [Stopping a Python systemd service cleanly](https://alexandra-zaharia.github.io/posts/stopping-python-systemd-service-cleanly/) — systemd unit file, PID tracking, signal handling
- [Python config hot-reload](https://oneuptime.com/blog/post/2026-01-22-config-hot-reload-python/view) — mtime polling vs SIGHUP approaches
- [Idempotent task handlers in Python](https://dev.to/humzakt/how-to-build-idempotent-cloud-tasks-handlers-in-python-the-pattern-that-eliminated-our-duplicate-4gml) — deterministic IDs, ON CONFLICT DO NOTHING, always-200 principle
- [Idempotency patterns distributed systems](https://backendbytes.com/articles/idempotency-patterns-distributed-systems) — at-least-once delivery, crash-safe design
- [Python subprocess docs](https://docs.python.org/3.14/library/subprocess.html) — `capture_output=True`, `check=True`, `text=True`
- [watchdog library](https://watchdog.readthedocs.io/en/stable) — inotify-based alternative (rejected: overkill)
- [Existing pueue-callback.sh](../../../scripts/vps/pueue-callback.sh) — production baseline, all patterns validated
- [Existing orchestrator.sh](../../../scripts/vps/orchestrator.sh) — poll loop, git pull, slot management baseline
- [Existing db.py](../../../scripts/vps/db.py) — WAL+IMMEDIATE pattern, context manager design
