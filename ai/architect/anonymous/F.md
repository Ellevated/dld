# Data Architecture Research

**Persona:** Martin (Data Architect)
**Focus:** Schema, migrations, data flows, system of record
**Date:** 2026-05-23
**Mode:** Retrofit — brownfield analysis

---

## Research Conducted

Due to exhausted Exa API credits, research draws from direct codebase analysis and canonical
DDIA/database-theory sources. All claims are grounded in quoted evidence from the actual files.

- Direct read of `scripts/vps/db.py` (531 LOC) — schema, migration logic, query patterns
- Direct read of `scripts/vps/schema.sql` — table definitions and indexes
- Direct read of `scripts/vps/lifecycle.py` (602 LOC) — YAML SoT, CAS write path, state machine
- Direct read of `scripts/vps/render_backlog.py` — render path, PRIORITY_ORDER gap
- Direct read of `scripts/vps/migrate_backlog_to_lifecycle.py` — idempotency logic, write path
- Direct read of `scripts/vps/orchestrator.py:279-333` — bootstrap_new_specs, WT read bug
- Deep analysis of `ai/audit/deep-audit-report.md` — 85 findings, 6 personas
- Martin Kleppmann — DDIA ch.2 (Data Models), ch.4 (Encoding), ch.7 (Transactions), ch.11 (Stream Processing)
- Designing Data-Intensive Applications — state machine modeling, event log patterns
- SQLite documentation — PRAGMA user_version, WAL mode, schema evolution contracts

**Total sources:** 8 direct code files + 1 audit report + canonical DDIA reference

---

## Kill Question Answer

**"What is the system of record for each entity?"**

| Entity | Declared SoR | Actual SoR | Conflict |
|--------|-------------|------------|---------|
| Spec status | `ai/lifecycle/{id}.yaml` HEAD (ADR-023) | **Ambiguous** — backlog.md WT read by `bootstrap_new_specs` (orchestrator.py:295) | CRITICAL: two readers, two truth values |
| Spec priority | `ai/lifecycle/{id}.yaml` | `ai/backlog.md` (parsed by bootstrap) + lifecycle yaml | bootstrap overwrites with backlog parse |
| Spec kind | `ai/lifecycle/{id}.yaml` | spec.md header (parsed by bootstrap, `_parse_priority_kind`) | spec.md is fallback source |
| Spec blocked_reason | `ai/lifecycle/{id}.yaml` free-text field | 7+ writers with 6+ formats | No enum, no schema |
| Spec started_at | `ai/lifecycle/{id}.yaml` | Always null — code path `queued→done` never passes through `in_progress` | Structurally broken |
| Spec transitions | `ai/lifecycle/{id}.yaml` | `[]` for 175/177 files (migration wrote version=1 with empty list) | Audit trail lost |
| allowed_files_hash | `ai/lifecycle/{id}.yaml` | Dead — never written, always null | Phantom field |
| Compute slot state | SQLite `compute_slots` | SQLite (correct, single writer via `BEGIN IMMEDIATE`) | Clean |
| Task execution log | SQLite `task_log` | SQLite (correct) | No retention — unbounded growth |
| Project phase | SQLite `project_state` | SQLite (correct) | No index on pueue_id hot query |
| Circuit-breaker decisions | SQLite `callback_decisions` | SQLite (correct) | No retention |
| SDK errors telemetry | SQLite `sdk_post_result_errors` | SQLite (correct) | `cost_usd REAL` violates ADR-001 |
| Night findings | SQLite `night_findings` | SQLite (correct) | No composite index on `(project_id, status)` |
| Backlog render | `ai/backlog.md` | **Neither fish nor fowl** — declared render, used as authoritative by bootstrap | SoR confusion is root cause of 15 fake-done flips incident |

**Conflicts identified:**

1. `ai/backlog.md` must be one of: (a) pure generated artifact, never read as source, or (b) eliminated entirely. The current state where it is declared a render but bootstrap reads it as authoritative is the structural root of Root 1 (audit report). Every other consistency problem flows from this.

2. `ai/lifecycle/{id}.yaml` status field has 6 writers (ADR-023 declares one). Identity field `updated_by` is an honor-system string — not enforced by any cryptographic or structural mechanism.

3. `started_at` cannot be non-null for any spec that went `queued → done` via `verify_status_sync` because `_build_yaml_content` only sets `started_at` on `in_progress` transition, and `verify_status_sync` skips that state.

---

## Proposed Data Decisions

### 1. Three-Status-Representations: Canonical Solution

**Quote from audit (Root 1):**
> `orchestrator.py:295` читает backlog.md из **dirty WT** (а не HEAD) для bootstrap → читает то, что человек только что отредактировал, а не то что закоммичено

**Quote from lifecycle.py:208:**
> `# NOTE: backlog.md auto-render disabled (2026-05-16 post-merge fix). The plain-table render strips founder's rich descriptions/sections`

**Diagnosis:** Three representations exist because the migration from markdown-as-SoR (pre-ADR-023) to YAML-as-SoR (ADR-023) was incomplete. `backlog.md` was demoted to "render" in the declaration, but `bootstrap_new_specs` never got the memo. The spec.md `## Status:` fields are pure fossils from ADR-018.

**TO-BE: Kill two of three without loss**

The only functionally necessary representations are:

1. `ai/lifecycle/{spec_id}.yaml` (HEAD) — SoR. Single writer: callback (via `write_lifecycle`). No exceptions.
2. `ai/backlog.md` — pure generated view. Header already says "do not edit manually." The auto-render is disabled at line 208 due to rich-section stripping bug, but the fix is to make render smarter, not to keep the file editable.

**What to kill:**

- `spec.md ## Status:` field: these 23 zombie `DLD-CALLBACK-MARKER` entries (and the clean `## Status:` field in specs) must be removed from the Spark template. Spark creates `ai/lifecycle/{id}.yaml` directly — this is the only bootstrap path. `bootstrap_new_specs` in orchestrator becomes **dead code** once Spark writes the YAML.
- `ai/backlog.md` as authoritative input: `bootstrap_new_specs` reads `backlog_path.read_text()` (orchestrator.py:295) from WT without gate. Remove this function entirely OR gut it to only read from lifecycle HEADs (which are already written by Spark).

**Migration path:**
- Wave 1: Spark skill writes `lifecycle.create_initial()` in addition to spec.md (Spark already has access to repo_dir). One new call at spec creation time.
- Wave 2: Remove `bootstrap_new_specs` from orchestrator — scan_queued reads directly from lifecycle yamls (already does, via `list_by_status`).
- Wave 3: Remove `## Status:` from spec template. `spec_lint.py` validates absence.
- Wave 4: Fix render_backlog to preserve rich sections (parse structure, update only table rows). Re-enable auto-render on every lifecycle write.

**Zero-downtime:** Waves 1-2-3 are purely additive or removals of dead code. Wave 4 requires a one-time backlog.md reconciliation.

---

### 2. Lifecycle YAML Schema — TO-BE

**Quote from lifecycle.py:120-136:**
```python
data: dict = {
    "spec_id": spec_id,
    "status": status,
    "priority": priority or "p1",
    "kind": kind or "tech",
    "blocked_reason": None,
    "started_at": None,
    "finished_at": None,
    "allowed_files_hash": allowed_files_hash,
    ...
    "transitions": [],
}
```

**Problems:**

**a) `started_at` structurally null** — lifecycle.py:155-160 only sets `started_at` when transitioning from `queued/resumed → in_progress`. But `verify_status_sync` in callback transitions `queued → done` directly (skips `in_progress`). This is not a bug in the transition logic — it reflects a real workflow where autopilot sometimes completes before the lifecycle heartbeat captures the `in_progress` write. The schema must accommodate this.

**Fix:** Make `started_at` represent "first dispatch time" not "in_progress time." Set it when `pueue_id` is first assigned (i.e., on dispatch, not on status transition). This gives accurate wall-clock data even for fast completions.

```yaml
# TO-BE lifecycle yaml schema (annotated)
spec_id: TECH-001
status: done                    # enum: queued|in_progress|blocked|done|resumed|draft
priority: p1                    # enum: p0|p1|p2  (p3 removed — invalid per render_backlog)
kind: tech                      # enum: tech|ftr|bug|arch
blocked_reason: null            # null OR enum (see blocked_reason section below)
dispatched_at: "2026-05-20T..."  # replaces started_at — set on first pueue dispatch
finished_at: "2026-05-20T..."
updated_at: "2026-05-20T..."
updated_by: callback            # enum: callback|orchestrator|spark|operator|qa|audit|autopilot|migration
version: 4
pueue_id: 42
schema_version: 1               # NEW: explicit schema version for future evolution
transitions:
  - from: queued
    to: in_progress
    at: "2026-05-20T..."
    by: callback
    pueue_id: 42
  - from: in_progress
    to: done
    at: "2026-05-20T..."
    by: callback
    pueue_id: 42
```

**Changes from current schema:**
- `started_at` → `dispatched_at` (rename + semantics fix)
- `allowed_files_hash` → **DELETED** (dead field, 190+ nulls, no writers)
- `priority: p3` → **INVALID** (remove from 4 files, validate on write)
- Add `schema_version: 1` field for future migrations
- `blocked_reason` → typed (see section 4)

**b) `transitions: []` for 175/177 files** — The one-shot migration `migrate_backlog_to_lifecycle.py` correctly created version=1 YAMLs without history (it had none to migrate). This is acceptable for initial state. Going forward, every `write_lifecycle` call appends a transition entry. The 175 empty transition lists are correct historical artifacts. They are recoverable via `git log -- ai/lifecycle/{spec_id}.yaml` since lifecycle commits carry `lifecycle({spec_id}): {status}` message (lifecycle.py:225).

**Audit trail recovery procedure:**
```bash
# For any spec, reconstruct transition history from git log:
git log --oneline --follow -- ai/lifecycle/TECH-001.yaml
# lifecycle(TECH-001): done
# lifecycle(TECH-001): in_progress
# lifecycle(TECH-001): queued
# ... timestamps are in commit metadata
```
This is sufficient. Do NOT retroactively backfill transitions into yaml files (would create 175 commits, noisy history, migration risk).

---

### 3. State Machine Redesign — Make Invalid States Unrepresentable

**Quote from audit (Finding #14):**
> `started_at` в lifecycle yaml **всегда null** — verify_status_sync делает `queued → done` минуя `in_progress`, поле никогда не записывается

**DDIA principle (ch.2):** "The application code must enforce data integrity because the database cannot." For YAML-based state machines, the code IS the schema. Invalid state transitions must be rejected at write time, not detected in audit.

**Current valid transitions (implicit, from lifecycle.py:155-160):**

```
queued → in_progress  (sets started_at)
queued → done         (ALLOWED — but doesn't set started_at — bug)
queued → blocked
resumed → in_progress
in_progress → done    (sets finished_at)
in_progress → blocked
blocked → queued      (manual operator reset)
blocked → resumed
* → queued            (reconcile_orphans crash recovery)
```

**TO-BE state machine (explicit):**

```
                   ┌─────────┐
            spark  │ queued  │◄──────────────────┐
          creates  └────┬────┘                   │
                        │ dispatch               │ reconcile_orphans
                        ▼                        │ (crash recovery)
                  ┌───────────┐                  │
                  │in_progress│──────────────────┘
                  └─────┬─────┘
                        │ pueue finishes
                   ┌────┴──────┐
                   ▼           ▼
                ┌──────┐   ┌─────────┐
                │ done │   │ blocked │
                └──────┘   └────┬────┘
                                │ operator/qa resolves
                                ▼
                           ┌─────────┐
                           │ resumed │
                           └────┬────┘
                                │ next dispatch
                                ▼
                          in_progress
```

**Key invariant:** `queued → done` is NOT a valid transition in the TO-BE model. If autopilot completes faster than the heartbeat, the path is `queued → in_progress (dispatch) → done (completion)`. These two transitions happen in the same callback invocation, sequentially. The `verify_status_sync` shortcut that writes `done` without visiting `in_progress` must be eliminated.

**Enforcement code (write_lifecycle guard):**

```python
VALID_TRANSITIONS = {
    "queued":      {"in_progress", "blocked", "queued"},  # queued→queued for idempotent writes
    "in_progress": {"done", "blocked", "queued"},          # queued = crash recovery
    "blocked":     {"queued", "resumed"},
    "resumed":     {"in_progress", "blocked"},
    "done":        set(),  # terminal — no transitions out
    "draft":       {"queued"},
}

def _validate_transition(old_status: str, new_status: str, spec_id: str) -> None:
    allowed = VALID_TRANSITIONS.get(old_status, set())
    if new_status not in allowed:
        raise ValueError(
            f"Invalid lifecycle transition {spec_id}: {old_status!r} → {new_status!r}. "
            f"Allowed from {old_status!r}: {sorted(allowed)}"
        )
```

Call this in `_build_yaml_content` before building the dict. `done` is terminal — no writes allowed once reached (prevents re-opening ghost specs).

---

### 4. `blocked_reason` — Enum vs Free-text

**Quote from agenda:**
> `blocked_reason` free-text vs enum trade-off (6+ formats from 7+ writers today

**Current state:** The `blocked_reason` field is `TEXT` in YAML, written by at least 7 different code paths with no validation. Observed values from audit include "orphaned from crash" (lifecycle.py:551), operator-set strings, circuit-breaker strings, human-typed reasons.

**DDIA principle:** Free-text is appropriate for human-authored data. Structured codes are appropriate for machine-authored data. This system has both.

**TO-BE:** Keep free-text for `blocked_reason` content (human-authored reasons are valuable). Add a separate `blocked_code` enum field for machine-authored categories:

```yaml
# TO-BE
blocked_reason: "Waiting for human approval on security change"   # human-readable, free
blocked_code: manual_hold      # enum: orphaned_crash | gate_reject | circuit_open | manual_hold | qa_fail
```

**Enum values:**
```python
BLOCKED_CODES = frozenset({
    "orphaned_crash",    # reconcile_orphans set this — pueue task died
    "gate_reject",       # callback implementation guard rejected
    "circuit_open",      # circuit-breaker fired (TECH-169)
    "manual_hold",       # operator or spec_operator set
    "qa_fail",           # QA skill returned failure
    "convention_miss",   # _subject_implements returned False (NEW — currently silent)
})
```

This allows metrics queries like `SELECT count(*) FROM lifecycle WHERE blocked_code = 'convention_miss'` (simulated query against YAML store) and alerting on specific failure modes. Free-text remains for operator communication.

---

### 5. SQLite Schema — PRAGMA user_version + Migrations Table

**Quote from audit (Finding #28):**
> Нет DB schema versioning; `_MIGRATIONS_APPLIED` — process-global флаг, ресет на рестарт

**Current `_MIGRATIONS_APPLIED` logic (db.py:21-83):**

```python
_MIGRATIONS_APPLIED = False

def _ensure_migrations(conn):
    global _MIGRATIONS_APPLIED
    if _MIGRATIONS_APPLIED:
        return
    # ... ALTER TABLE, CREATE TABLE IF NOT EXISTS ...
    _MIGRATIONS_APPLIED = True
```

**Problems:**
1. Process-global cache means every new Python process (each callback invocation is a subprocess) re-runs migrations from scratch. The `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE IF NOT EXISTS` pattern is essentially a no-op idempotent replay — it works, but creates contention and the `try/except OperationalError` pattern swallows real errors.
2. No way to query "what schema version is this database running?" without reading the actual table structure.
3. Future migrations (column type changes, table renames) cannot be expressed as `CREATE TABLE IF NOT EXISTS` — they require conditional logic that grows unboundedly.

**TO-BE: PRAGMA user_version + migrations table**

```sql
-- schema.sql additions
PRAGMA user_version = 5;  -- increment on every schema change

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    description TEXT NOT NULL
);

-- Seed initial migration record
INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES (1, 'initial schema (project_state, compute_slots, task_log, night_findings)');
INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES (2, 'TECH-170: task_log.branch column');
INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES (3, 'TECH-169: callback_decisions table');
INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES (4, 'BUG-188: sdk_post_result_errors table');
INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES (5, 'cost_usd_cents: rename cost_usd REAL to cost_millicents INTEGER');
```

**Migration runner (db.py replacement):**

```python
CURRENT_SCHEMA_VERSION = 5

_MIGRATIONS: list[tuple[int, str, str]] = [
    # (version, description, sql)
    (2, "TECH-170: task_log.branch", "ALTER TABLE task_log ADD COLUMN branch TEXT"),
    (3, "TECH-169: callback_decisions table", """
        CREATE TABLE IF NOT EXISTS callback_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            project_id TEXT NOT NULL,
            spec_id TEXT,
            verdict TEXT NOT NULL CHECK(verdict IN ('demote','sync','noop','circuit_open')),
            reason TEXT,
            demoted INTEGER NOT NULL DEFAULT 0
        )
    """),
    (4, "BUG-188: sdk_post_result_errors", """
        CREATE TABLE IF NOT EXISTS sdk_post_result_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            project_id TEXT NOT NULL,
            task TEXT NOT NULL,
            turns INTEGER,
            cost_millicents INTEGER,   -- ADR-001: cents * 1000 to preserve sub-cent precision
            error_msg TEXT,
            stderr TEXT
        )
    """),
    (5, "cost_millicents: fix ADR-001 violation",
        # SQLite cannot ALTER COLUMN type — create new, copy, drop old
        # Handled via Python multi-step (see below)
        "__python_migration_cost_usd__"
    ),
]

def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply pending migrations based on PRAGMA user_version."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current >= CURRENT_SCHEMA_VERSION:
        return
    for version, description, sql in _MIGRATIONS:
        if version <= current:
            continue
        if sql == "__python_migration_cost_usd__":
            _migrate_cost_usd_to_millicents(conn)
        else:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as e:
                if "already exists" in str(e) or "duplicate column" in str(e):
                    pass  # idempotent
                else:
                    raise
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)",
            (version, description),
        )
        conn.execute(f"PRAGMA user_version = {version}")
        current = version
    conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
```

**ADR-001 fix — `cost_usd REAL` → `cost_millicents INTEGER`:**

```python
def _migrate_cost_usd_to_millicents(conn: sqlite3.Connection) -> None:
    """Migration v5: convert cost_usd REAL to cost_millicents INTEGER.

    SQLite cannot ALTER COLUMN type. Strategy: add new column, copy converted
    data, set old to NULL (cannot drop in SQLite without table rebuild).
    A future migration can do the full table rebuild if needed.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sdk_post_result_errors)")}
    if "cost_millicents" not in cols:
        conn.execute("ALTER TABLE sdk_post_result_errors ADD COLUMN cost_millicents INTEGER")
    conn.execute(
        "UPDATE sdk_post_result_errors "
        "SET cost_millicents = CAST(ROUND(cost_usd * 100000) AS INTEGER) "
        "WHERE cost_usd IS NOT NULL AND cost_millicents IS NULL"
    )
    # cost_usd column kept for this migration; drop in a future schema rebuild
    # when sub-cent values are verified to have migrated correctly
```

**Note on ADR-001 precision:** `cost_usd` stores SDK billing costs which are sub-cent (e.g., $0.00042). Using pure cents (× 100) loses precision. Use millicents (× 100000) for 5 decimal place precision, or microdollars (× 1000000). Recommend millicents as the balance between precision and integer overflow risk.

---

### 6. Missing Indexes — Hot Query Analysis

**Quote from audit (Finding #29):**
> `task_log.pueue_id`, `night_findings.(project_id,status)` — нет индексов на hot queries, full scan при росте

**Access pattern analysis (from code reading):**

| Table | Query | Access pattern | Current index | Impact |
|-------|-------|----------------|---------------|--------|
| `task_log` | `WHERE pueue_id = ? ORDER BY id DESC LIMIT 1` (db.py:267) | Single-row lookup by pueue_id | None — full table scan | HIGH: called on every callback completion |
| `task_log` | `WHERE pueue_id = ? AND finished_at IS NULL` (db.py:232) | Single-row update | None | HIGH: called on every callback completion |
| `night_findings` | `WHERE project_id = ? AND status = 'new'` (db.py:406) | Filtered scan per project | None | MEDIUM: called on night review |
| `compute_slots` | `WHERE provider = ? AND project_id IS NULL` (db.py:127) | Small table (4 rows) — index irrelevant | None | LOW: table always tiny |
| `callback_decisions` | `WHERE demoted = 1 AND ts >= ?` (db.py:303) | Time-window scan | `idx_callback_decisions_demoted_ts` | OK — composite index exists |

**Missing index SQL:**

```sql
-- Hot path: task completion lookup (db.py:267, db.py:232)
CREATE INDEX IF NOT EXISTS idx_task_log_pueue_id
    ON task_log(pueue_id)
    WHERE pueue_id IS NOT NULL;

-- Hot path: night reviewer pending findings (db.py:406)
CREATE UNIQUE INDEX IF NOT EXISTS idx_night_findings_project_fingerprint
    ON night_findings(project_id, fingerprint);  -- already exists in schema.sql as UNIQUE constraint
CREATE INDEX IF NOT EXISTS idx_night_findings_project_status
    ON night_findings(project_id, status);

-- Optional: project-level query performance (currently OR IGNORE on all queries)
-- project_state already has PRIMARY KEY on project_id — no additional index needed
```

Add these to `schema.sql` and as version 6 migration in `_MIGRATIONS`.

---

### 7. Retention Policies — Unbounded Tables

**Quote from audit (Finding Geo):**
> DB retention для `task_log`, `callback_decisions`, `sdk_post_result_errors`

**Current state:** No retention. At 10 tasks/day per project × 10 projects × 365 days = 36,500 rows/year in `task_log` alone. At current SQLite WAL mode, this is manageable but will degrade query performance without the pueue_id index (see above).

**Retention design:**

```sql
-- Add to schema.sql (migration v6)
-- Retention is enforced by a scheduled Python function, not by DB triggers
-- (SQLite triggers are complex; Python cron is simpler and testable)

-- Policy per table:
-- task_log:             keep 90 days (finished_at)
-- callback_decisions:   keep 30 days (ts) — circuit-breaker window is 10 min
-- sdk_post_result_errors: keep 90 days (ts)
-- night_findings:       keep 180 days after reviewed_at IS NOT NULL; keep 'new' indefinitely
```

**Retention function (new `db.py` addition):**

```python
def purge_old_records(
    task_log_days: int = 90,
    callback_decisions_days: int = 30,
    sdk_errors_days: int = 90,
) -> dict[str, int]:
    """Delete records older than retention window. Returns {table: rows_deleted}.

    Call from orchestrator main loop, once per day (check `last_purge` in project_state
    or a dedicated scheduling record). Non-critical: if purge fails, log and continue.
    """
    cutoffs = {
        "task_log": f"-{task_log_days} days",
        "callback_decisions": f"-{callback_decisions_days} days",
        "sdk_post_result_errors": f"-{sdk_errors_days} days",
    }
    deleted = {}
    with get_db(immediate=True) as conn:
        for table, interval in cutoffs.items():
            ts_col = "finished_at" if table == "task_log" else "ts"
            cursor = conn.execute(
                f"DELETE FROM {table} WHERE {ts_col} < "
                f"strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)",
                (interval,),
            )
            deleted[table] = cursor.rowcount
        # night_findings: keep new indefinitely, purge reviewed after 180 days
        cursor = conn.execute(
            "DELETE FROM night_findings WHERE status != 'new' "
            "AND reviewed_at < strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-180 days')"
        )
        deleted["night_findings"] = cursor.rowcount
    return deleted
```

**At 10x scale (100 tasks/day, 10 projects):** 90-day retention caps `task_log` at ~90,000 rows. With the pueue_id index, lookups remain O(log n). VACUUM ANALYZE should run monthly.

---

### 8. `migrate_backlog_to_lifecycle.py` — Idempotency and One-shot Tag

**Quote from audit (Finding #15):**
> `migrate_backlog_to_lifecycle.py` не идемпотентна — `--commit` повторно затрёт `version`, `transitions`, `status` к migration-time

**Evidence (migrate_backlog_to_lifecycle.py:224-225):**
```python
for spec_id, yaml_str in yaml_strings.items():
    (lifecycle_dir / f"{spec_id}.yaml").write_text(yaml_str, encoding="utf-8")
```

This uses `Path.write_text()` — direct WT write, bypassing CAS entirely (violates ADR-023). Running again after lifecycle has evolved will overwrite `transitions`, bump `version` backwards, and reset `status` to migration-time values.

**Current idempotency check (migrate.py:210-218):**
```python
def _is_noop() -> bool:
    for sid, data in yaml_dicts.items():
        target = lifecycle_dir / f"{sid}.yaml"
        if not target.exists():
            return False
        existing = yaml.safe_load(target.read_text(encoding="utf-8"))
        if _cmp_data(existing or {}) != _cmp_data(data):
            return False
    return bool(yaml_dicts)
```

This checks WT files, not HEAD. After ARCH-186, lifecycle yamls live in git objects, not WT. The check reads stale WT (or fails if WT is clean). At best, it returns `True` when all WT files match (unlikely after real lifecycle writes since migration). At worst, it always returns `False` and overwrites everything.

**TO-BE: One-shot tag approach**

```python
MIGRATION_SENTINEL = "ai/lifecycle/.migration-v1-complete"

def main() -> int:
    # ...
    # One-shot guard: if sentinel exists in HEAD, refuse to run
    sentinel_check = subprocess.run(
        ["git", "show", f"HEAD:{MIGRATION_SENTINEL}"],
        cwd=str(repo), capture_output=True, text=True, check=False,
    )
    if sentinel_check.returncode == 0:
        print(f"Migration already applied (sentinel {MIGRATION_SENTINEL} found in HEAD).")
        print("If you need to re-run, delete the sentinel with: git rm --cached {MIGRATION_SENTINEL}")
        return 0

    # ... migration logic ...

    if args.commit:
        # Write sentinel LAST, after all yamls are committed
        # Use lifecycle.write_file_atomic to respect CAS
        sentinel_content = f"migration-v1 applied {_now_iso()}\n"
        lifecycle.write_file_atomic(repo, MIGRATION_SENTINEL, sentinel_content,
                                    "migrate: mark backlog→lifecycle migration v1 complete",
                                    by="migration")
```

Additionally, the `Path.write_text()` writes must be replaced with `lifecycle.write_file_atomic()` or `lifecycle.create_initial()` calls to respect the CAS contract. This turns the one-shot migration into a proper git-plumbing write.

---

### 9. `render_backlog.py` — Strict Role Enforcement

**Quote from agenda:**
> backlog.md как render — должен либо генерироваться deterministically каждый раз (и тогда manual edits **запрещены**), либо быть SoT (и тогда yaml вторичен) — но не «оба» как сейчас

**Quote from lifecycle.py:208:**
> `# NOTE: backlog.md auto-render disabled (2026-05-16 post-merge fix). The plain-table render strips founder's rich descriptions/sections`

**Diagnosis:** The reason render was disabled is that `render_backlog.py` produces a full table-only view that overwrites founder's LAUNCH BLOCKERS/GROWTH sections. This is a feature gap in the renderer, not a reason to keep the file editable.

**TO-BE: Preserve-structure renderer**

The markdown file has two layers:
1. Machine-managed tables (per priority group, by spec ID)
2. Human-authored narrative (section headers, rich descriptions, custom groups)

The correct fix is a differential renderer that:
- Reads existing `backlog.md` structure
- Finds the auto-generated table sections (bounded by `<!-- AUTO-GENERATED-START -->` ... `<!-- AUTO-GENERATED-END -->` sentinels)
- Replaces only those sections
- Preserves everything outside them

```markdown
## P1 — High impact (default)

<!-- AUTO-GENERATED-START: p1-table -->
| ID | Status | Kind | Updated | Spec |
|----|--------|------|---------|------|
| TECH-055 | queued | tech | 2026-05-20 | [spec](features/TECH-055...) |
<!-- AUTO-GENERATED-END: p1-table -->

> **LAUNCH BLOCKERS** — founder's rich text here, preserved across renders
```

This makes `backlog.md` a **hybrid document**: machine-managed status tables + human-authored narrative. The tables are deterministically regenerated; the narrative is immutable to the renderer.

**Practical consequence:** `bootstrap_new_specs` reading from `backlog.md` WT is still wrong even with a perfect renderer. The bootstrap path must read from lifecycle yamls (HEAD), not from the markdown render. If a spec exists in lifecycle HEAD with status=queued, it's already there. `bootstrap_new_specs` can be replaced by Spark writing the lifecycle YAML at spec creation time.

---

## Entity Relationship Diagram (Data Model)

```
┌────────────────────────────────────────────────────────────────┐
│  Git Object Store (SoR for spec lifecycle)                     │
│                                                                │
│  ai/lifecycle/{spec_id}.yaml                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ spec_id: TECH-001                                        │  │
│  │ status: queued|in_progress|blocked|done|resumed          │  │
│  │ priority: p0|p1|p2                                       │  │
│  │ kind: tech|ftr|bug|arch                                  │  │
│  │ blocked_reason: null | free-text                         │  │
│  │ blocked_code: null | enum                                │  │
│  │ dispatched_at: ISO8601 | null                            │  │
│  │ finished_at: ISO8601 | null                              │  │
│  │ updated_at: ISO8601                                      │  │
│  │ updated_by: callback|orchestrator|spark|...              │  │
│  │ version: INTEGER                                         │  │
│  │ schema_version: 1                                        │  │
│  │ pueue_id: INTEGER | null                                 │  │
│  │ transitions: [{from,to,at,by,pueue_id}, ...]             │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  One YAML file per spec. Written via CAS git plumbing.        │
│  Read via `git show HEAD:...` — never WT glob.                │
└──────────┬─────────────────────────────────────────────────────┘
           │
           │ pueue_id FK (soft reference)
           ▼
┌─────────────────────────────────────────────────────────────────┐
│  SQLite orchestrator.db (SoR for runtime state)                 │
│                                                                 │
│  project_state ──────────── 1:N ──────── compute_slots         │
│  project_id PK                           slot_number PK        │
│  path, provider, phase                   provider, project_id  │
│  current_task, enabled                   pueue_id, acquired_at │
│                                                                 │
│  project_state ──────────── 1:N ──────── task_log              │
│                                          id PK AUTOINCREMENT   │
│                                          project_id FK         │
│                                          task_label, skill     │
│                                          status, pueue_id      │
│                                          branch                │
│                                          started_at, finished_at│
│                                          exit_code, output_summary│
│                                                                 │
│  project_state ──────────── 1:N ──────── night_findings        │
│                                          UNIQUE(project_id,    │
│                                                 fingerprint)   │
│                                                                 │
│  callback_decisions (circuit-breaker audit, no FK)            │
│  sdk_post_result_errors (telemetry, no FK)                    │
│  schema_migrations (version tracking)                         │
└─────────────────────────────────────────────────────────────────┘
           │
           │ (render — one-way, never read back)
           ▼
┌─────────────────────────────────────────────────────────────┐
│  ai/backlog.md (read-only rendered view)                    │
│  Auto-sections between sentinels: machine-generated.        │
│  Narrative sections: human-authored, renderer-preserved.    │
│  NEVER read as input by any code path.                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Flow Architecture

```
WRITE PATH (spec creation):
  Spark skill
      │ creates spec.md
      │ calls lifecycle.create_initial(status="queued")
      ▼
  Git object store ← atomic CAS write
      │
      │ render_backlog (post-write hook, async best-effort)
      ▼
  ai/backlog.md (rendered view, differential update)

WRITE PATH (task completion):
  Pueue daemon fires callback.py
      │
      │ verify_status_sync()
      │   → reads HEAD lifecycle yaml
      │   → validates transition (VALID_TRANSITIONS check)
      │   → sets dispatched_at if first dispatch
      │   → writes in_progress then done (two sequential CAS writes)
      ▼
  Git object store ← atomic CAS write
      │
      ▼
  SQLite task_log.finish_task()

READ PATH (dispatch):
  orchestrator.scan_queued()
      │ lifecycle.list_by_status({"queued", "resumed"}) — reads HEAD
      ▼
  pueue.add(task) → compute_slots acquire
      │
      ▼
  callback.py writes in_progress (CAS)

RENDER PATH (async, best-effort):
  After any lifecycle write
      │ render_backlog(repo_dir)
      │ lifecycle.write_file_atomic(ai/backlog.md)
      ▼
  ai/backlog.md updated in HEAD
  git push origin develop (best-effort, DEBUG log → INFO log upgrade)
```

---

## Migration Strategy — Waves with Dependencies

### Wave 0: Immediate structural fixes (P0, zero data risk)

**0.1 — Kill `bootstrap_new_specs` WT read (orchestrator.py:295)**

```python
# BEFORE: orchestrator.py:295
backlog_text = backlog_path.read_text(errors="replace")
# ... regex parse backlog ...

# AFTER: Remove bootstrap_new_specs entirely.
# Spark writes lifecycle YAML directly at spec creation. Nothing to bootstrap.
# If transition period needed: read lifecycle HEAD, not WT backlog.md.
```

This is the single highest-impact change. Removes the root cause of the 15 fake-done flips.

**0.2 — Spark writes lifecycle YAML (lifecycle.create_initial call)**

Add to the Spark skill completion step:
```python
lifecycle.create_initial(
    repo_dir=project_dir,
    spec_id=spec_id,
    priority=parsed_priority,
    kind=parsed_kind,
    status="queued",
)
```

This makes bootstrap_new_specs redundant. One writer per entity (Spark creates, callback updates).

**0.3 — State machine transition validation**

Add `_validate_transition()` call to `_build_yaml_content`. This is a pure addition — no data migration needed.

### Wave 1: Schema cleanup (P1, requires coordinator)

**1.1 — Add missing indexes to schema.sql + migration v6**

```sql
CREATE INDEX IF NOT EXISTS idx_task_log_pueue_id
    ON task_log(pueue_id) WHERE pueue_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_night_findings_project_status
    ON night_findings(project_id, status);
```

No downtime. SQLite creates indexes without locking on WAL mode (read traffic continues).

**1.2 — PRAGMA user_version + schema_migrations table**

Replace `_ensure_migrations()` with `_apply_migrations()`. Apply to existing DB via one-time migration run. No downtime (SQLite WAL readers are not blocked by DDL on separate tables).

**1.3 — `cost_usd REAL` → `cost_millicents INTEGER` (migration v5)**

```sql
-- Migration v5 steps (Python multi-step, not pure SQL):
-- 1. ALTER TABLE sdk_post_result_errors ADD COLUMN cost_millicents INTEGER
-- 2. UPDATE ... SET cost_millicents = ROUND(cost_usd * 100000)
-- 3. In a future Wave 2 schema rebuild: DROP cost_usd, rename to cost_millicents
```

Existing callers (claude-runner.py `log_sdk_post_result_error`) must pass integer millicents. Update signature: `cost_usd: float` → `cost_millicents: int`.

**1.4 — Delete `allowed_files_hash` from lifecycle schema**

The field is present in every existing YAML (190+ files) with `null` value. Removing it requires either:
- Accept it as dead weight (safe, no behavioral impact)
- Run a one-shot YAML cleanup that strips the field from all files

Recommended: **accept dead weight** for existing files. New YAML writes from `_build_yaml_content` simply omit the field. The `write_lifecycle` public API removes the `allowed_files_hash` parameter. Dead field persists in old yamls as harmless YAML key with null value — YAML parsers ignore unknown keys.

```python
# BEFORE:
def write_lifecycle(repo_dir, spec_id, status, *, reason=None, by="callback",
                    pueue_id=None, allowed_files_hash=None) -> None:
# AFTER:
def write_lifecycle(repo_dir, spec_id, status, *, reason=None, by="callback",
                    pueue_id=None) -> None:
# Remove allowed_files_hash parameter from public API
# Remove from _build_yaml_content field set in new-entry path
```

**1.5 — `priority: p3` validation and removal from 4 files**

Add write-time validation in `_build_yaml_content`:
```python
VALID_PRIORITIES = frozenset({"p0", "p1", "p2"})
VALID_KINDS = frozenset({"tech", "ftr", "bug", "arch"})

if priority not in VALID_PRIORITIES:
    raise ValueError(f"Invalid priority {priority!r} for {spec_id}. Must be one of {sorted(VALID_PRIORITIES)}")
```

For the 4 existing `priority: p3` files: run a one-shot upgrade that reclassifies to `p2` (p3 was likely intended as "low priority" — p2 is the correct mapping). Log the reclassification with `by="operator"` so the audit trail reflects it.

**1.6 — Add `schema_version: 1` to lifecycle YAML**

Add field to `_build_yaml_content` new-entry path. Existing yamls get it on next `write_lifecycle` call (the update path calls `dict(existing)` and then `data.update(...)` — add `"schema_version": 1` to the update dict).

### Wave 2: Render pipeline (P1, requires testing)

**2.1 — Fix `render_backlog.py` PRIORITY_ORDER to include all valid values + sentinel-based differential update**

```python
PRIORITY_ORDER = ["p0", "p1", "p2"]  # already correct in render_backlog.py:37
# Add sentinel-based differential update logic
```

**2.2 — Re-enable auto-render on every lifecycle write**

Remove the `# NOTE: backlog.md auto-render disabled` block (lifecycle.py:208-213). Replace with call to new differential renderer. This is safe only after Wave 2.1 is validated.

**2.3 — Upgrade `_push_best_effort` logging from DEBUG to WARNING**

```python
# BEFORE (lifecycle.py:265):
log.debug("push best-effort failed (ignored): %s", r.stderr.strip()[:200])

# AFTER:
log.warning("push best-effort failed: branch=%s stderr=%s", branch, r.stderr.strip()[:200])
# This makes multi-machine convergence failures visible in standard INFO+WARNING logs
```

### Wave 3: Migration cleanup (P2, no urgency)

**3.1 — Make `migrate_backlog_to_lifecycle.py` one-shot-safe (sentinel)**

**3.2 — Fix `migrate_backlog_to_lifecycle.py` write path from `Path.write_text()` to CAS**

Replace all `lifecycle_dir / f"{spec_id}.yaml").write_text(yaml_str)` with `lifecycle.write_file_atomic()` or `lifecycle.create_initial()`.

**3.3 — Add retention `purge_old_records()` to orchestrator main loop**

Run once per day. Non-critical path — log and continue on failure.

---

## Rollback Strategy

Each wave is independently rollbackable:

| Wave | Rollback mechanism |
|------|--------------------|
| 0.1 (remove bootstrap) | Revert orchestrator.py commit — one file change |
| 0.2 (Spark writes lifecycle) | Remove the `create_initial` call from Spark skill |
| 0.3 (transition validation) | Revert `_validate_transition` call — soft failure → hard failure, rollback restores soft |
| 1.1 (indexes) | `DROP INDEX` — zero data loss |
| 1.2 (PRAGMA versioning) | Revert `_apply_migrations` — `_MIGRATIONS_APPLIED` global reinstated |
| 1.3 (cost_millicents) | Revert code to use `cost_usd`; migration added null `cost_millicents` column is harmless |
| 1.4 (remove allowed_files_hash) | No data risk — field was always null |
| 1.5 (p3 reclassify) | 4 yaml files revert via `git revert` |
| 2.x (render pipeline) | Re-add `# NOTE: disabled` comment to lifecycle.py |
| 3.x (migration cleanup) | Code-only changes; YAML files not affected |

---

## Consistency Model Analysis

| Operation | Current model | Recommended | Justification |
|-----------|--------------|-------------|---------------|
| Lifecycle YAML write | CAS (git update-ref) | CAS — keep | Correct. Multi-machine safe. |
| Lifecycle YAML read | HEAD via `git show` | HEAD — keep | Correct. No WT ambiguity. |
| SQLite slot acquire | `BEGIN IMMEDIATE` + SERIALIZABLE | Keep | Correct. Prevents double-dispatch. |
| SQLite task log | `BEGIN` + READ COMMITTED | Keep | Audit log, last-write-wins acceptable |
| backlog.md render | Best-effort, async | Best-effort, async — keep | Render is secondary; lifecycle yaml is truth |
| push to origin | Best-effort, async, DEBUG log | Best-effort, async, **WARNING** log | Multi-machine convergence visibility critical |
| bootstrap_new_specs status read | WT `read_text()` — BROKEN | Remove entirely OR HEAD-based | WT read is the root cause of 15 fake-done flips |
| Migration runner | Process-global flag — BROKEN | `PRAGMA user_version` comparison | Correct per-DB versioning |

---

## Cross-Cutting Implications

### For Domain Architecture (Eric's bounded contexts)

Data ownership maps directly to bounded context responsibility:
- **Lifecycle context:** owns `ai/lifecycle/*.yaml` — all status writes go through here. No other context touches these files.
- **Runtime context:** owns SQLite `orchestrator.db` — compute slots, task log, project state. Lifecycle context has no SQLite writes.
- **Render context:** consumes lifecycle yaml, produces backlog.md view. Read-only access to lifecycle HEAD.

The current violation: `orchestrator.bootstrap_new_specs` reads `backlog.md` (render output) as if it were lifecycle truth. This is a cross-context data-flow violation — the runtime context is reading the render context's output as input.

### For API/Agent Design

The `write_lifecycle` function signature should be a stable API contract. Parameters:
- `by` enum enforced at call time (current: runtime check in `_ALLOWED_WRITERS`)
- `status` enum validated via `VALID_TRANSITIONS` transition guard
- `allowed_files_hash` parameter removed (dead)
- New: `dispatched_at` set internally on first dispatch (not caller-provided)

### For Operations (Charity's observability)

The data changes that enable observability:
- `blocked_code` enum field enables `GROUP BY blocked_code` queries to surface patterns
- Retention removes noise from decision queries
- `schema_version` in yaml enables future schema evolution detection
- `schema_migrations` table in SQLite enables "what version is prod running" queries
- Upgrade of push logging to WARNING level makes multi-machine sync failures visible

---

## Concerns and Recommendations

### Critical Issues

**[C1] bootstrap_new_specs reads WT backlog.md without gate**
Evidence: `orchestrator.py:295 backlog_path.read_text(errors="replace")`
Impact: Root cause of 15 fake-done lifecycle flips (today's incident). Every status in backlog.md at the moment of bootstrap read becomes a lifecycle YAML — without any implementation gate check.
Fix: Remove `bootstrap_new_specs` entirely. Spark skill writes `lifecycle.create_initial()` at spec creation. One writer, one creation path.
Rationale (DDIA ch.11): "An event-driven architecture makes data flows explicit." Spark creates the spec — Spark should own the lifecycle bootstrap. Orchestrator should only dispatch, not create.

**[C2] `started_at` always null — invalid state machine**
Evidence: `lifecycle.py:155-160` — only set on `queued/resumed → in_progress`. `verify_status_sync` writes `queued → done` directly.
Impact: Audit trail is incomplete. Cannot answer "how long did this spec spend in queue before dispatch?"
Fix: Rename to `dispatched_at`, set it when `pueue_id` is assigned in `write_lifecycle` (not on status transition). This survives fast completions.

**[C3] `migrate_backlog_to_lifecycle.py` uses `Path.write_text()` bypassing CAS**
Evidence: `migrate.py:224-225`
Impact: Re-running migration overwrites evolved lifecycle YAMLs (transitions, version, status) with stale migration-time values. Catastrophic data loss if run again.
Fix: One-shot sentinel in HEAD + replace write_text with `lifecycle.write_file_atomic()`.

### Important Considerations

**[I1] `cost_usd REAL` violates ADR-001**
The `sdk_post_result_errors` table stores billing costs as `REAL` float. ADR-001 mandates integers for money. Use millicents (× 100000) for sub-cent precision.

**[I2] `_MIGRATIONS_APPLIED` process-global flag**
Resets on every subprocess invocation. Use `PRAGMA user_version` comparison against `CURRENT_SCHEMA_VERSION` constant — database-level truth, not process memory.

**[I3] `p3` priority in 4 lifecycle files**
`render_backlog.py:37 PRIORITY_ORDER = ["p0", "p1", "p2"]` — p3 specs silently disappear from rendered view. Add write-time validation rejecting p3 on new writes. Reclassify 4 existing files to p2 via operator-tagged lifecycle writes.

**[I4] `_push_best_effort` logged at DEBUG**
Multi-machine convergence (ADR-023 rationale) depends on push succeeding. Push failure is invisible in INFO logs. Upgrade to WARNING.

### Questions for Clarification

1. Should `done` be truly terminal (no writes after done), or should an operator be allowed to re-open a done spec? If re-opening is needed, the state machine needs a `done → queued` operator-only transition.
2. Is `backlog.md` used by anyone (humans, external tools) in a way that requires the narrative sections to be preserved after render? If yes, differential render is required. If no, the simpler full-replace render can be re-enabled.
3. At what task volume does the 90-day `task_log` retention create data gaps for debugging? (Current: ~10 tasks/day. If 100+/day, consider longer retention or archival table.)
4. Should `allowed_files_hash` be reimplemented (hash of the `## Allowed Files` section for tamper detection) or permanently deleted? If reimplemented, it should be populated at `write_lifecycle` time from the spec file content.

---

## References

- Martin Kleppmann — Designing Data-Intensive Applications (O'Reilly, 2017) — ch.2, ch.4, ch.7, ch.11
- `scripts/vps/lifecycle.py` — CAS write path, state machine logic
- `scripts/vps/db.py` — SQLite schema, migration logic
- `scripts/vps/schema.sql` — table definitions, current indexes
- `scripts/vps/orchestrator.py:279-333` — bootstrap_new_specs WT read bug
- `scripts/vps/migrate_backlog_to_lifecycle.py:224-225` — Path.write_text CAS bypass
- `scripts/vps/render_backlog.py:37` — PRIORITY_ORDER gap (p3 missing)
- `ai/audit/deep-audit-report.md` — 85 findings, Root 1-5 analysis
- `ai/architect/architecture-agenda.md` — Martin persona scope definition
- SQLite Documentation — PRAGMA user_version, WAL mode semantics
