# External Research — Orphan Slot Watchdog (BUG-162)

## Best Practices (5 with sources)

### 1. Lease + Heartbeat: Turn Permanent Ownership into Borrowing
**Source:** [SQLite in Practice (3): Save Your Workers](https://docsaid.org/en/blog/sqlite-lease-heartbeat-recovery)
**Summary:** The canonical solution for stale locks in job queues is the lease model: a worker "borrows" a slot for a fixed period. If it stops renewing (heartbeat), the scheduler can reclaim it. The field `acquired_at` (already in `compute_slots`) is the simplest version of this — age-based expiry replaces heartbeat when workers don't support active renewal.
**Why relevant:** Our `compute_slots.acquired_at` column is already populated by `try_acquire_slot()`. The watchdog just needs to compare it against a threshold (e.g., max agent wall-clock time is 60 min per `claude-runner.py`). No schema change needed — this is a read-only check.

### 2. "Cross-reference External State" Over Timeout-Only Expiry
**Source:** [BullMQ Stalled Job Handling](https://oneuptime.com/blog/post/2026-01-21-bullmq-stalled-jobs/view) — `stalledInterval` + process check pattern
**Summary:** BullMQ combines lock-expiry with an active check: it queries the queue for tasks that hold a lock but haven't renewed, AND cross-references with the worker process list. Neither check alone is sufficient: timeout-only misses fast crashes; process-check alone misses the gap between task finish and DB update.
**Why relevant:** The race condition in BUG-162 is exactly this gap. The correct approach: collect `pueue_id`s from locked DB slots, then call `pueue status --json` once per cycle, and release only slots whose `pueue_id` is absent from pueue's task list (never Running or Queued). This is a cross-reference, not a timeout check.

### 3. BEGIN IMMEDIATE for Watchdog Cleanup Prevents TOCTOU
**Source:** [SQLite: understanding and fixing "database is locked"](https://zeroclarkthirty.com/2024-10-19-sqlite-database-is-locked) and [SQLite in Practice (2): Atomic Claims](https://docsaid.org/en/blog/sqlite-job-queue-atomic-claim)
**Summary:** The TOCTOU (time-of-check/time-of-use) race: you SELECT orphan slots, then another writer (callback.py) releases the same slot between your SELECT and your UPDATE. `BEGIN IMMEDIATE` acquires the write lock at transaction start, not at first write. This means the callback cannot slip in between.
**Why relevant:** `db.py` already uses `get_db(immediate=True)` for `try_acquire_slot` and `release_slot`. The watchdog cleanup function must use the same pattern: `BEGIN IMMEDIATE`, re-read slot state inside the transaction, only clear if `pueue_id` is still absent from pueue.

### 4. Poll-Start Watchdog Pattern: Run Cleanup Before Dispatch
**Source:** [How to Configure systemd Watchdog for Service Health Checks](https://oneuptime.com/blog/post/2026-03-02-how-to-configure-systemd-watchdog-for-service-health-checks-on-ubuntu/view)
**Summary:** Production daemons run health/cleanup checks at the start of each poll cycle, before any new work is dispatched. This ensures the system always starts a cycle from a known-clean state. The systemd watchdog model: "check liveness first, then do work."
**Why relevant:** The watchdog should be the very first call in `orchestrator.py`'s `main()` while-loop body — before `sync_projects()` and before `scan_backlog()`. This guarantees that slot counts are correct before `get_available_slots()` is ever consulted.

### 5. Idempotent Cleanup with Structured Logging for Forensics
**Source:** [Maintenance workflow cleanup stale queue tasks — Temporal](https://github.com/temporalio/temporal/issues/1021) and [SQLite Transactions Production Patterns](https://thelinuxcode.com/sqlite-transactions-a-practical-guide-to-autocommit-wal-savepoint-and-production-patterns/)
**Summary:** Temporal's approach to stale queue cleanup: log every reclamation with enough context to diagnose why it happened. Cleanup must be idempotent (running it twice must not cause harm). Log `project_id`, `slot_number`, `pueue_id`, `acquired_at` for every released orphan slot.
**Why relevant:** We need forensic visibility into how often this happens (which indicates upstream bugs) without causing secondary corruption if the watchdog runs more than once per cycle.

---

## Libraries/Tools

| Library/Tool | Version | Pros | Cons | Use Case | Source |
|---|---|---|---|---|---|
| `pueue status --json` | v4.0.4 | Already used in codebase (`is_agent_running`), no new dep | Subprocess call with 10s timeout per cycle | Cross-reference live task IDs | [pueue GitHub](https://github.com/nukesor/pueue) |
| `sqlite3` stdlib + `BEGIN IMMEDIATE` | Python stdlib | Already used, zero deps, atomic write-lock at tx start | Single writer; callback.py must also use IMMEDIATE | Atomic orphan cleanup in DB | [SQLite WAL + IMMEDIATE](https://zeroclarkthirty.com/2024-10-19-sqlite-database-is-locked) |
| `pueue_lib` Rust crate | latest | Structured Rust types for pueue state | Not usable from Python | N/A for this feature | [docs.rs/pueue-lib](https://docs.rs/pueue-lib/latest/pueue_lib/) |

**Recommendation:** No new library needed. Use the existing `pueue status --json` subprocess pattern (already in `is_agent_running()`) combined with the existing `get_db(immediate=True)` pattern from `db.py`. Everything required is already in the codebase.

---

## Production Patterns

### Pattern 1: Cross-Reference Watchdog (Orphan Detection by Absence)
**Source:** [BullMQ Stalled Job Handling](https://oneuptime.com/blog/post/2026-01-21-bullmq-stalled-jobs/view) + existing `orchestrator.py:is_agent_running()`
**Description:**
1. Query DB for all locked slots (WHERE `project_id IS NOT NULL`), collecting their `pueue_id` values.
2. Call `pueue status --json` once (already done in `is_agent_running`, factor it out).
3. Build a set of "live" pueue IDs: those with status `Running` or `Queued`.
4. Any DB slot whose `pueue_id` is NOT in the live set is orphaned.
5. Release each orphaned slot in a `BEGIN IMMEDIATE` transaction that re-checks the condition inside the transaction.

**Real-world use:** BullMQ (used by >500k npm projects), Temporal workflow engine, solid_queue (Rails).
**Fits us:** Yes — this is the minimal, safe approach. One pueue call per cycle, O(slots) DB operations (max 4 slots total). Race condition handled by re-checking inside IMMEDIATE transaction.

### Pattern 2: Age-Based Timeout Expiry (Fallback)
**Source:** [SQLite in Practice (3): Save Your Workers](https://docsaid.org/en/blog/sqlite-lease-heartbeat-recovery)
**Description:** Release slots where `acquired_at` is older than `MAX_AGENT_WALL_CLOCK` (e.g., 90 minutes — 60min timeout + 30min grace). Simpler, but can falsely release a legitimately long-running task if it approaches the limit.
**Real-world use:** Kubernetes TTL-after-finished controller, AWS SQS visibility timeout.
**Fits us:** Partially — use as a secondary safety net ONLY, not as the primary mechanism. The cross-reference pattern (Pattern 1) is more accurate. Age-based is a final backstop for when pueue is completely unreachable.

### Pattern 3: Idempotent Single-SQL Cleanup
**Source:** [SQLite in Practice (2): Atomic Claims](https://docsaid.org/en/blog/sqlite-job-queue-atomic-claim) — UPDATE...WHERE CAS pattern
**Description:** Collapse the SELECT + UPDATE into a single atomic statement inside IMMEDIATE transaction:
```sql
BEGIN IMMEDIATE;
UPDATE compute_slots
SET project_id = NULL, pid = NULL, pueue_id = NULL, acquired_at = NULL
WHERE pueue_id IN (?, ?, ...)   -- known-orphan IDs from pueue cross-reference
  AND project_id IS NOT NULL;   -- re-check: still locked (CAS guard)
COMMIT;
```
The `AND project_id IS NOT NULL` is the compare-and-swap guard. If `callback.py` released the slot between our pueue check and this UPDATE, rowcount will be 0 and no harm is done.
**Real-world use:** Standard pattern in PostgreSQL-based job queues using `FOR UPDATE SKIP LOCKED` equivalent logic.
**Fits us:** Yes — this is the exact implementation pattern to use inside `release_orphan_slots()`.

---

## Pueue JSON Status Format

From reading `orchestrator.py:is_agent_running()` and pueue v4.0.4 source:

```json
{
  "tasks": {
    "0": {
      "id": 0,
      "label": "dld:FTR-160",
      "status": {"Running": {"start": "2026-03-19T10:00:00Z", "children": []}},
      "command": "...",
      "group": "claude-runner"
    },
    "1": {
      "id": 1,
      "label": "awardybot:TECH-055",
      "status": "Queued",
      "command": "...",
      "group": "claude-runner"
    },
    "2": {
      "id": 2,
      "label": "dld:ARCH-161",
      "status": {"Done": {"result": {"Success": null}, "start": "...", "end": "..."}},
      "command": "...",
      "group": "claude-runner"
    }
  },
  "groups": {}
}
```

Key observations:
- `tasks` is a dict keyed by string integer task ID
- `status` is either a plain string (`"Queued"`, `"Stashed"`, `"Paused"`) or a dict (`{"Running": {...}}`, `{"Done": {...}}`, `{"Failed": {...}}`)
- `label` is our `project_id:spec_id` format
- A task is "live" if `isinstance(status, dict) and "Running" in status` OR `status == "Queued"`
- Task IDs are integers stored as `pueue_id` in `compute_slots`

**Source:** `orchestrator.py` lines 107-114 (live code that already parses this format correctly).

---

## Key Decisions Supported by Research

1. **Decision:** Cross-reference pueue task list vs. DB slots (not age-based timeout alone)
   **Evidence:** BullMQ and Temporal both use cross-reference; age-only causes false releases on slow-but-alive tasks. Our agents run up to 60 min (configured in claude-runner). Age-based would need 90+ min threshold = slow detection.
   **Confidence:** High

2. **Decision:** Single `pueue status --json` call per cycle, reusing parsed result
   **Evidence:** `is_agent_running()` already makes this call per-project (redundant). Refactoring to one call at cycle-start and passing the parsed data down is a cleanup that also enables the watchdog. This avoids N subprocess calls for N projects.
   **Confidence:** High

3. **Decision:** Use `BEGIN IMMEDIATE` with CAS guard inside cleanup transaction
   **Evidence:** `db.py` already uses this pattern for `try_acquire_slot`/`release_slot`. The watchdog must use it too. Without IMMEDIATE, callback.py can slip a release between our SELECT and UPDATE, causing double-release (idempotent but noisy).
   **Confidence:** High

4. **Decision:** Add watchdog as first step in poll cycle, before `sync_projects()`
   **Evidence:** Systemd watchdog pattern: check health before dispatching work. Ensures `get_available_slots()` returns accurate count. Position: `while not _stop.is_set()` → first line.
   **Confidence:** High

5. **Decision:** Add `release_orphan_slots()` to `db.py`, not inline in `orchestrator.py`
   **Evidence:** All DB operations are in `db.py` (ADR from `rules/dependencies.md`). The function takes a list of live pueue_ids (already fetched by orchestrator) and returns count of released slots for logging.
   **Confidence:** High

---

## Implementation Sketch (Pseudocode)

```python
# orchestrator.py — refactored poll cycle

def get_live_pueue_ids() -> set[int]:
    """Return set of pueue task IDs that are Running or Queued."""
    try:
        r = subprocess.run(["pueue", "status", "--json"],
                          capture_output=True, text=True, timeout=10)
        data = json.loads(r.stdout)
        live = set()
        for task_id_str, task in data.get("tasks", {}).items():
            status = task.get("status", "")
            is_running = isinstance(status, dict) and "Running" in status
            is_queued = status == "Queued"
            if is_running or is_queued:
                live.add(int(task_id_str))
        return live
    except Exception:
        return None  # None = pueue unreachable, skip watchdog this cycle


# db.py

def release_orphan_slots(live_pueue_ids: set[int]) -> int:
    """Release compute slots whose pueue_id is not in live_pueue_ids.

    Uses BEGIN IMMEDIATE to prevent race with callback.py.
    Returns number of slots released.
    """
    with get_db(immediate=True) as conn:
        locked = conn.execute(
            "SELECT slot_number, project_id, pueue_id, acquired_at "
            "FROM compute_slots WHERE project_id IS NOT NULL"
        ).fetchall()
        released = 0
        for row in locked:
            if row["pueue_id"] not in live_pueue_ids:
                conn.execute(
                    "UPDATE compute_slots "
                    "SET project_id = NULL, pid = NULL, pueue_id = NULL, acquired_at = NULL "
                    "WHERE slot_number = ? AND project_id IS NOT NULL",  # CAS guard
                    (row["slot_number"],),
                )
                released += 1
                # log: slot, project_id, pueue_id, acquired_at
        return released
```

---

## Research Sources

- [SQLite in Practice (3): Save Your Workers](https://docsaid.org/en/blog/sqlite-lease-heartbeat-recovery) — lease+heartbeat pattern for stale slot recovery
- [SQLite in Practice (2): Atomic Claims](https://docsaid.org/en/blog/sqlite-job-queue-atomic-claim) — BEGIN IMMEDIATE + CAS guard pattern, UPDATE...WHERE idempotency
- [SQLite in Practice (1): Database is Locked](https://docsaid.org/en/blog/sqlite-wal-busy-timeout-for-workers) — WAL + busy_timeout + IMMEDIATE transaction behavior
- [BullMQ Stalled Jobs](https://oneuptime.com/blog/post/2026-01-21-bullmq-stalled-jobs/view) — stalledInterval + cross-reference pattern, production at scale
- [SQLite: understanding and fixing "database is locked"](https://zeroclarkthirty.com/2024-10-19-sqlite-database-is-locked) — BEGIN IMMEDIATE vs DEFERRED, why TOCTOU happens with deferred
- [Temporal Maintenance workflow cleanup stale queue tasks](https://github.com/temporalio/temporal/issues/1021) — how Temporal handles stale task cleanup in production
- [pueue GitHub repo (v4.0.4)](https://github.com/nukesor/pueue) — JSON status format, task states, label conventions
- [SQLite Transactions Production Patterns](https://thelinuxcode.com/sqlite-transactions-a-practical-guide-to-autocommit-wal-savepoint-and-production-patterns/) — autocommit, WAL, SAVEPOINT, production patterns 2026
- [Exclusive scheduled jobs using DB locks](https://tkareine.org/articles/exclusive-scheduled-jobs-using-db-locks.html) — fault-tolerant exclusive job implementation with acquired_at
- [Background jobs without Redis: Postgres SKIP LOCKED in production](https://artur.bearblog.dev/background-jobs-without-redis-postgres-skip-locked-in-production/) — lease_until + heartbeat + stale reclaim query pattern (Postgres, but directly translates to SQLite IMMEDIATE)
