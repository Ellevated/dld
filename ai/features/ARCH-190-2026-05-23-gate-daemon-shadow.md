# Feature: [ARCH-190] gate-daemon shadow implementation (Alt C Wave 1 — MP-001)

**Priority:** P0 | **Date:** 2026-05-23

> **Lifecycle state** is tracked in `ai/lifecycle/ARCH-190.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

Callback bears two responsibilities today: pueue completion dispatcher AND status determination gate (`verify_status_sync` + `_is_done_on_develop` + `_subject_implements`). This temporal coupling caused the fix-train: ADR-018 → BUG-185 → ARCH-186 → ADR-023 → BUG-188 → ADR-024 → TECH-189. Each "fix" surfaced a new edge case.

Alt C (chosen 2026-05-23 in `/architect` Cycle #2 — 3 reject / 1 approve convergence) structurally separates gate logic into a polling daemon. Wave 1 builds this daemon in **shadow mode** — observation only, no authority. Wave 2 verifies parity. Wave 3 cuts over. This spec implements MP-001 (the daemon itself) per `ai/architect/migration-path.md:39-80`.

## Context

- **TECH-189 (Wave 0 P0 cluster) merged 2026-05-23** — all 9 hardening fixes shipped. Develop is stable.
- **Blueprint reference:** `ai/blueprint/system-blueprint/callback-lifecycle-contour.md` — "Status Determination Context (Loop 2)" is gate-daemon's bounded context. FF-09 key invariant: zero callback↔gate-daemon imports.
- **Multi-machine:** founder runs on 3 machines (VPS sole orchestrator/gate-daemon host; 2 laptops run Spark). Gate-daemon reads `origin/develop` after `git fetch` — distribution via git (ADR-023 preserved).
- **Function-naming drift caught:** `_spec_has_merged_implementation` was renamed to `_is_done_on_develop` in commit `cefaa55` (8-rule redesign 2026-05-21). This spec uses the current name everywhere.

---

## Scope

**In scope (Wave 1 MP-001):**
- `scripts/vps/gate_logic.py` — extracted pure functions (parse_allowed_files v1+legacy, match_subject, find_implementation_commit, fetch_develop, _SPEC_ID_RE). Zero I/O on import, pure-functional core.
- `scripts/vps/gate-daemon.py` — polling daemon (60s cycle, multi-project iteration, JSONL shadow writer, SQLite health metrics, file-based heartbeat). Hard runtime invariant `assert SHADOW_ONLY_MODE`.
- `scripts/vps/schema.sql` + `scripts/vps/db.py` — `gate_health` table + helpers (`log_gate_cycle`, `get_gate_health`).
- `scripts/vps/setup-vps.sh` — install `dld-gate-daemon.service` user-unit (Restart=on-failure, WatchdogSec=120, MemoryMax=2G, file-based heartbeat) + `systemctl --user enable --now`.
- `scripts/vps/tests/test_gate_logic.py` + `scripts/vps/tests/test_gate_daemon.py` — pure-function tests + daemon loop integration tests with real tmp git fixtures.
- `.claude/rules/dependencies.md` — new section per context-updater protocol.

**Out of scope (deferred to other waves — explicitly):**
- Parity comparator + `audit.py` reader → MP-002, MP-003 (Wave 2).
- Gate-daemon writes lifecycle yaml → MP-005 (Wave 3, adds `"gate-daemon"` to `_ALLOWED_WRITERS`).
- Removing `verify_status_sync` from callback hot-path → MP-006 (Wave 3).
- `vps-orch` CLI — but `gate_health` SQLite schema is designed so MP-014 can read it without migration.
- `heartbeat_monitor.py` watching gate-daemon heartbeat → Wave 6 ALERT-005 (this spec writes the heartbeat file; monitor consumes it later).
- Concurrent git fetches via `ThreadPoolExecutor` — mitigation chosen is **aggressive per-fetch timeout=15s** instead (KISS, matches orchestrator's sequential pattern).
- Logrotate config for shadow JSONL — deferred to MP-002. This spec uses Python's `RotatingFileHandler` (100MB cap, 5 files) to prevent disk exhaustion during Wave 2 observation week.

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
- N/A — new files; no callers yet. Wave 3 (MP-005) will add gate-daemon as lifecycle writer; Wave 6 (MP-014) will read `gate_health` via `vps-orch`.
- Verified: `grep -rn 'gate.daemon\|gate_logic\|gate-health' --include="*.py" --include="*.sh" --include="*.sql" .` → 0 hits in source code (only in `ai/architect/`, `ai/blueprint/`, `ai/features/` design docs).

### Step 2: DOWN — what depends on?
| Dependency | File | Functions used |
|---|---|---|
| `lifecycle` | `scripts/vps/lifecycle.py:333,411` | `read_lifecycle()`, `list_by_status()` — both accept `repo_dir` (multi-project ready) |
| `db` | `scripts/vps/db.py` | `get_all_projects()`, NEW `log_gate_cycle()`, NEW `get_gate_health()` |
| `gate_logic` | NEW `scripts/vps/gate_logic.py` | `parse_allowed_files()`, `find_implementation_commit()`, `match_subject()`, `fetch_develop()` |
| stdlib | — | `subprocess`, `json`, `pathlib`, `logging`, `signal`, `time`, `os`, `threading` |
| `.env` | `scripts/vps/.env` | `DB_PATH`, `POLL_INTERVAL` (default 60), `GATE_DAEMON_SHADOW_LOG` |

**FF-09 invariant (this spec asserts):** `grep -E "^import callback\|^from callback" scripts/vps/gate-daemon.py scripts/vps/gate_logic.py` returns 0. `gate_logic.py` imports only stdlib (`re`, `subprocess`, `dataclasses`, `pathlib`, `logging`).

### Step 3: BY TERM — grep entire project

| Term | Pre-spec result | Post-spec expected |
|---|---|---|
| `gate-daemon`, `gate_daemon` | 0 in source code | present in 4 NEW files + dependencies.md row |
| `gate_logic` | 0 | present in `gate_logic.py` (definition) + `gate-daemon.py` (import) + 2 tests |
| `gate_health` | 0 | present in `schema.sql`, `db.py` (2 helpers), tests |
| `_spec_has_merged_implementation` | 0 (renamed to `_is_done_on_develop`) | stays 0 — this spec uses current name everywhere |
| `SHADOW_ONLY_MODE` | 0 | present in `gate-daemon.py` (constant + assert) + 1 test |

### Step 4: CHECKLIST — mandatory folders
- [x] `scripts/vps/tests/**` — NEW `test_gate_daemon.py` + `test_gate_logic.py`
- [x] `scripts/vps/schema.sql` — add `gate_health` table (idempotent `CREATE TABLE IF NOT EXISTS`)
- [x] `scripts/vps/db.py` — add `_ensure_migrations` row + 2 helpers (mirror `log_sdk_post_result_error` pattern from BUG-188)
- [x] `scripts/vps/setup-vps.sh` — install user-unit via HEREDOC + `systemctl --user enable --now`
- [x] `.claude/rules/dependencies.md` — new section "scripts/vps/gate-daemon.py" + "scripts/vps/gate_logic.py"

### Step 5: DUAL SYSTEM (gate-daemon coexists with callback)

| System | Reads lifecycle YAML | Writes lifecycle YAML | Writes JSONL |
|---|---|---|---|
| callback | yes (`read_lifecycle`) | yes (`write_lifecycle(by="callback")`) | yes (`callback-audit.jsonl`) |
| gate-daemon (Wave 1) | yes (`list_by_status`, `read_lifecycle`) | **NO** (FF-09 + `SHADOW_ONLY_MODE` assert + `_ALLOWED_WRITERS` doesn't include "gate-daemon") | yes (`gate-daemon-shadow.jsonl`) |

Both read same git HEAD — pure HEAD query, no race. The two JSONL files are SEPARATE (different filenames) — Wave 2 MP-003 will read both for parity comparison.

**Invariant after Wave 1 ships:** `grep "updated_by: gate-daemon" ai/lifecycle/*.yaml` = 0 (across all projects). Test SA-3 verifies via `git log --grep='by: gate-daemon' --all ai/lifecycle/ -- | wc -l` = 0.

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/gate-daemon.py` — daemon loop (NEW, ~180 LOC)
- `scripts/vps/gate_logic.py` — pure-function extract (NEW, ~200 LOC)
- `scripts/vps/schema.sql` — add `gate_health` table (modify)
- `scripts/vps/db.py` — add `log_gate_cycle` + `get_gate_health` + migration (modify)
- `scripts/vps/setup-vps.sh` — install `dld-gate-daemon.service` user-unit + enable (modify)
- `scripts/vps/tests/test_gate_logic.py` — pure-function tests (NEW, ~180 LOC)
- `scripts/vps/tests/test_gate_daemon.py` — daemon loop integration tests (NEW, ~200 LOC)
- `.claude/rules/dependencies.md` — add gate-daemon + gate_logic sections (modify, context-updater protocol)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list. Explicit non-targets (already-stable code that this spec must NOT touch): callback.py (Wave 3), lifecycle.py (Wave 3 MP-005 will add "gate-daemon" to _ALLOWED_WRITERS), orchestrator.py (unaffected), event_writer.py (Wave 6 ALERT-005 hook).

---

## Environment

<!-- DLD orchestrator: VPS Linux, Python 3.12+, systemd --user units, sqlite3 stdlib -->
nodejs: false
docker: false
database: true  (existing SQLite; new `gate_health` table)

---

## Blueprint Reference

**Domain:** `scripts/vps` — Status Determination Context (Loop 2) per `ai/blueprint/system-blueprint/callback-lifecycle-contour.md:30-44`.
**Cross-cutting:** Multi-machine git-as-distribution-channel (ADR-023). FF-09 temporal decoupling enforcement.
**Data model:** Reads `ai/lifecycle/{spec_id}.yaml` from git HEAD via `lifecycle.list_by_status`. Writes `scripts/vps/gate-daemon-shadow.jsonl` (append) + `gate_health` SQLite row per cycle. Does NOT write lifecycle yaml (Wave 1 invariant).

---

## Historical Risks

<!-- lessons-binding v1 -->

`ai/lessons/` exists but is unseeded (`.gitkeep` only). Derived from git history (TECH-189, BUG-188, TECH-177, ARCH-186 commits):

| ID | Class | Rule | Sources |
|---|---|---|---|
| L-derived-1 | function-naming-drift | Always re-verify function names via `grep -n "^def"` before citing. `_spec_has_merged_implementation` was renamed to `_is_done_on_develop` (cefaa55) — this spec uses current names. | commit cefaa55 |
| L-derived-2 | regex-duplication | `_SPEC_ID_RE` lives in callback.py:43 AND orchestrator.py:308. GROWTH had to be added twice (TECH-189 Task 6). Wave 1 adds a THIRD copy in `gate_logic.py`; Wave 5 MP-011 consolidates to `common.py`. | TECH-189 Task 6 (1151eb1) |
| L-derived-3 | --grep-false-positive | Bare `git log --grep "SPEC-ID"` matches body/trailer mentions (TECH-177 incident). Must use path-filter-first + subject-only matching via `match_subject`. This spec's `find_implementation_commit` does NOT use bare `--grep`. | TECH-177 (2026-05-04) |
| L-derived-4 | silent-cycle-failure | Cycle counter alone is insufficient liveness signal — daemon can have healthy counter but `last_cycle_evaluated=0` (all fetches timing out). `gate_health` records both metrics. | derived (Devil Attack 9) |
| L-derived-5 | bootstrap-mass-done | 15 lifecycle yamls auto-flipped in one cycle burned $258 (BOOTSTRAP_ANOMALY_THRESHOLD root cause). Gate-daemon writes shadow JSONL, never lifecycle in Wave 1 — same mass-anomaly class structurally impossible. | BUG-188, TECH-189 Task 4 |

---

## Approaches

### Approach 1: "Minimal Shadow" (rejected)

**Source:** Patterns scout "Approach A" combined with Devil Attack 1+9 partial mitigation
**Summary:** Pure 60s polling, `time.sleep(60)` (drifting cadence), sequential fetches with default 30s timeout, JSONL only (no SQLite metrics), no SHA cache, no heartbeat. ~120 LOC.
**Pros:** smallest review surface.
**Cons (blockers):** 30s timeout × 10 projects = worst-case 300s cycle (5x WatchdogSec). No SHA cache → replays git log every cycle. No `last_cycle_evaluated` → Devil Attack 9 silent-failure mode goes undetected. **Rejected.**

### Approach 2: "Defensive Shadow" (SELECTED)

**Source:** Patterns scout "Approach B" + ALL Devil P0 mitigations + Codebase scout's DLD-pattern alignment (file heartbeat, sequential fetch, SQLite metrics in same db.py style)
**Summary:** Sequential per-project iteration with aggressive `timeout=15s` per `git fetch` (worst case 150s; still beats default 30s × 10 = 300s and avoids ThreadPoolExecutor complexity). SHA cache for `origin/develop` HEAD (skip git log if HEAD unchanged). Fixed cadence via `cycle_start = time.monotonic()` + `_stop.wait(max(0, CYCLE_SLEEP - elapsed))`. Shadow JSONL with full schema (`cycle_start_ts`, `as_of_ts`, `spec_id`, `project`, `gate_verdict`, `gate_reason`, `matching_commit_sha`, `allowed_files_count`). RotatingFileHandler 100MB cap × 5 files. SQLite `gate_health` per-cycle row (cycle_count, last_poll_at, in_progress_specs, decisions_this_cycle, error_msg). File-based heartbeat `.gate-daemon-heartbeat` (mirrors orchestrator pattern). `assert SHADOW_ONLY_MODE` runtime guard. ~380 LOC total (180 daemon + 200 logic, both well under 400-LOC limit).
**Pros:** Addresses every Devil P0 mitigation. Reuses proven DLD patterns (sequential fetch, file heartbeat, JSONL append, SQLite migration). gate_logic.py is pure-functional → trivially testable without subprocess mocks. FF-09 structurally enforced (no callback import).
**Cons:** More code than Approach 1, but each piece justified by a Devil attack or scout finding.

### Approach 3: "Hardened Concurrent" (rejected)

**Source:** Approach 2 + Devil Attack 3 mitigation via `ThreadPoolExecutor(max_workers=5)` for git fetches.
**Pros:** Bounds total fetch time to 15s worst-case across 10 projects.
**Cons:** Breaks consistency with orchestrator's sequential pattern. Adds thread-safety concerns for SQLite writes (WAL handles concurrent readers but daemon is single-process; thread pool inside one process needs explicit `check_same_thread=False` or per-thread connections). Codebase scout cites this as anti-pattern departure. Aggressive `timeout=15s` (Approach 2) achieves 90% of the benefit at 0% of the complexity cost. **Rejected.**

### Selected: 2

**Rationale:** Approach 2 = "boring tech" (Dan the DX Architect's principle from `/architect`): mirrors orchestrator's main-loop structure, mirrors callback's JSONL writer, mirrors db.py's migration helper. Every component traceable to existing DLD pattern. Addresses every P0 mitigation Devil flagged. Concurrent fetches are real value-add but explicit non-goal of Wave 1 ("simple shadow daemon", per migration-path.md).

---

## Design

### User Flow

(This is a daemon, not a UI feature — "user" = operator + future agents.)

1. **Operator runs setup:** `bash scripts/vps/setup-vps.sh` on VPS → user-unit installed and started.
2. **Daemon starts:** loads .env, opens SQLite, writes initial heartbeat, enters main loop.
3. **Every 60s cycle:**
   - For each enabled project (sequential):
     - `git fetch origin develop --quiet` (timeout=15s, `check=False`).
     - Read current `origin/develop` HEAD via `git rev-parse`. Compare to cached HEAD. If unchanged, skip git log for this project (SHA cache hit).
     - `lifecycle.list_by_status(project_path, {"in_progress", "queued"})` → list of spec dicts.
     - For each spec: read `## Allowed Files` via `gate_logic.parse_allowed_files`. If parse fails → shadow record `gate_verdict="blocked", gate_reason="missing_allowed_files"`. Else call `gate_logic.find_implementation_commit(project_path, spec_id, allowed)` → sha or None. Record shadow JSONL entry.
   - Write `gate_health` row to SQLite (cycle_count, last_poll_at, in_progress_specs_total, decisions_this_cycle, error_msg).
   - Touch heartbeat file `.gate-daemon-heartbeat`.
   - Sleep `max(0, 60s - elapsed)` (fixed cadence).
4. **Future operator query (Wave 6):** `vps-orch gate-health` reads latest `gate_health` row.

### Architecture

```
gate-daemon.py (main loop, I/O)
    │
    ├── gate_logic.py (pure functions, stdlib only)
    │       ├── parse_allowed_files(spec_path) -> list[str] | None
    │       ├── match_subject(subject, spec_id) -> bool       # extracted from _subject_implements
    │       ├── fetch_develop(project_path, timeout=15) -> bool
    │       └── find_implementation_commit(project_path, spec_id, allowed) -> str | None
    │
    ├── lifecycle.py (read-only API: list_by_status, read_lifecycle)
    │       │
    │       └── git show HEAD:ai/lifecycle/*.yaml (per project)
    │
    └── db.py (SQLite WAL)
            ├── get_all_projects()           # existing
            ├── log_gate_cycle(...)          # NEW
            └── get_gate_health()            # NEW

Output sinks:
  - gate-daemon-shadow.jsonl       (RotatingFileHandler 100MB × 5)
  - SQLite gate_health table       (one row per cycle)
  - .gate-daemon-heartbeat         (file touched per cycle)

Reads (NEVER writes):
  - ai/lifecycle/{spec_id}.yaml    (via lifecycle.list_by_status)
  - ai/features/{spec_id}.md       (via gate_logic.parse_allowed_files)
  - origin/develop git refs        (via subprocess)
```

### Database Changes

`scripts/vps/schema.sql` — append (idempotent `CREATE TABLE IF NOT EXISTS`):

```sql
-- ARCH-190: gate-daemon per-cycle health metrics
CREATE TABLE IF NOT EXISTS gate_health (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    cycle_count           INTEGER NOT NULL,
    last_poll_at          TEXT NOT NULL,
    in_progress_specs     INTEGER NOT NULL DEFAULT 0,
    decisions_this_cycle  INTEGER NOT NULL DEFAULT 0,
    error_msg             TEXT
);

CREATE INDEX IF NOT EXISTS idx_gate_health_ts ON gate_health(ts);
```

`scripts/vps/db.py:_ensure_migrations` — add row mirroring `sdk_post_result_errors` style (BUG-188).

### Shadow JSONL Entry Schema

Each line is one JSON object. Fields (Devil Attack 1 mitigation — timestamp alignment for MP-003):

```json
{
  "cycle_start_ts": "2026-05-24T12:34:00Z",   // when this cycle started (for parity join)
  "as_of_ts": "2026-05-24T12:34:18Z",          // when this decision was written (for Wave 2 alignment)
  "project": "dld",
  "spec_id": "TECH-200",
  "gate_verdict": "done",                       // "done" | "in_progress" | "blocked"
  "gate_reason": "subject_matched: feat(TECH-200): ...",
  "matching_commit_sha": "abc1234",             // null if verdict != "done"
  "allowed_files_count": 3,
  "shadow_only": true                           // explicit marker, never absent
}
```

### Systemd Unit Template

Installed by `setup-vps.sh` to `~/.config/systemd/user/dld-gate-daemon.service`:

```ini
[Unit]
Description=DLD Gate Daemon (Alt C Wave 1 — shadow mode)
After=network.target

[Service]
Type=simple
ExecStart=${SCRIPT_DIR}/venv/bin/python3 ${SCRIPT_DIR}/gate-daemon.py
WorkingDirectory=${SCRIPT_DIR}
EnvironmentFile=${SCRIPT_DIR}/.env
MemoryMax=2G
MemorySwapMax=0
KillMode=control-group
Restart=on-failure
RestartSec=2s
RestartMaxDelaySec=60s
RestartSteps=5
StartLimitBurst=10
StartLimitIntervalSec=300s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=dld-gate-daemon

[Install]
WantedBy=default.target
```

**NOTE:** `WatchdogSec` is intentionally OMITTED. Devil Attack 9 + Codebase scout consensus: DLD's proven liveness pattern is file-based heartbeat (`.orchestrator-heartbeat` + `heartbeat_monitor.py` cron). Gate-daemon writes `.gate-daemon-heartbeat`; Wave 6 MP-017 extends the cron to watch both files. No `sd_notify` Python dep needed.

---

## UI Event Completeness

N/A — daemon, no UI.

---

## Implementation Plan

### Research Sources

- [migration-path.md MP-001](../architect/migration-path.md) — Wave 1 spec source
- [callback-lifecycle-contour.md](../blueprint/system-blueprint/callback-lifecycle-contour.md) — TO-BE blueprint, FF-09 invariant
- [research-external.md](../.spark/20260523-ARCH-190/research-external.md) — systemd unit best practices, JSONL atomicity, git log perf
- [research-codebase.md](../.spark/20260523-ARCH-190/research-codebase.md) — extract candidates, lifecycle API, Verified References
- [research-patterns.md](../.spark/20260523-ARCH-190/research-patterns.md) — 7-axis trade-off analysis
- [research-devil.md](../.spark/20260523-ARCH-190/research-devil.md) — 11 attacks, P0 mitigations IN this spec

### Task 1: Extract `gate_logic.py` from callback functions

**Type:** code
**Files:**
- create: `scripts/vps/gate_logic.py`
**Acceptance:**
- File contains ONLY pure functions + dataclasses + module-level regex constants. NO subprocess in import path (only inside function bodies).
- Imports = `re`, `subprocess`, `pathlib`, `logging`, `dataclasses` (stdlib only). `grep -E "^import callback\|^from callback" scripts/vps/gate_logic.py` = 0.
- Public API: `parse_allowed_files(spec_path: Path) -> list[str] | None`, `match_subject(subject: str, spec_id: str) -> bool`, `fetch_develop(project_path: str, timeout: int = 15) -> bool`, `find_implementation_commit(project_path: str, spec_id: str, allowed_files: list[str]) -> str | None` (returns sha or None — NOT bare bool).
- `find_implementation_commit` uses two-step approach IDENTICAL to `callback._is_done_on_develop`: `git log origin/develop --pretty=%H%x00%s -- <allowed_files>` first (path filter), then Python loop `match_subject(subject, spec_id)` (subject-only — Devil Attack 2/10 mitigation). **NOT bare `--grep SPEC-ID`.**
- `_SPEC_ID_RE` copied verbatim including GROWTH: `re.compile(r"(TECH|FTR|BUG|ARCH|GROWTH)-\d+[a-z]*")` (L-derived-2).

### Task 2: Add `gate_health` table to schema + db.py helpers

**Type:** migrate + code
**Files:**
- modify: `scripts/vps/schema.sql`
- modify: `scripts/vps/db.py`
**Acceptance:**
- `gate_health` table created via idempotent `CREATE TABLE IF NOT EXISTS` (appears in both `schema.sql` AND `db._ensure_migrations`).
- `db.log_gate_cycle(cycle_count, last_poll_at, in_progress_specs, decisions_this_cycle, error_msg=None) -> int` (mirror `log_sdk_post_result_error` signature).
- `db.get_gate_health() -> dict | None` returns latest row by `id DESC LIMIT 1`.
- Migration order in `_ensure_migrations` is idempotent; running twice does not error.

### Task 3: Implement `gate-daemon.py` daemon loop

**Type:** code
**Files:**
- create: `scripts/vps/gate-daemon.py`
**Acceptance:**
- Mirrors `orchestrator.py:main()` structure: `_load_env() → _setup_logging() → _write_pid() → signal handlers (SIGTERM/SIGINT via threading.Event) → main loop`.
- `SHADOW_ONLY_MODE = True` constant. `assert SHADOW_ONLY_MODE, "Wave 3 cutover not yet authorized"` at process start AND immediately before any code path that might write lifecycle. (Defense-in-depth even though `_ALLOWED_WRITERS` doesn't include "gate-daemon".)
- `grep -n "lifecycle.write_lifecycle\|write_lifecycle(" scripts/vps/gate-daemon.py` = 0.
- Main loop: fixed cadence (`cycle_start = time.monotonic()` → work → `_stop.wait(max(0, 60 - elapsed))`).
- SHA cache: dict `_origin_develop_sha: dict[project_id, str]`. Skip per-spec git log if `git rev-parse origin/develop` returns same sha as last cycle.
- Sequential per-project iteration with **per-project try/except** (Devil Attack 7 / patterns A7b): one project's git error logs warning and continues with next project. Cycle counter still increments.
- `gate_logic.fetch_develop(project_path, timeout=15)` — aggressive 15s timeout per project (Devil Attack 3 mitigation without ThreadPoolExecutor).
- Shadow writer: `RotatingFileHandler` on `GATE_DAEMON_SHADOW_LOG` path (default `scripts/vps/gate-daemon-shadow.jsonl`), `maxBytes=100*1024*1024`, `backupCount=5`. Each line = JSON with full schema (cycle_start_ts, as_of_ts, project, spec_id, gate_verdict, gate_reason, matching_commit_sha, allowed_files_count, shadow_only=True).
- After each cycle: `db.log_gate_cycle(...)` writes `gate_health` row. Write `.gate-daemon-heartbeat` file with ISO ts.
- Log every cycle at INFO: `cycle=N evaluated=K projects=P duration=Xs`.
- Daemon survives ALL exceptions in cycle body (top-level `try/except Exception: log.exception(...)` — never propagates), per orchestrator pattern.

### Task 4: Install user-unit via `setup-vps.sh`

**Type:** code
**Files:**
- modify: `scripts/vps/setup-vps.sh`
**Acceptance:**
- HEREDOC block writes `~/.config/systemd/user/dld-gate-daemon.service` with template above (NO `WatchdogSec`).
- `systemctl --user daemon-reload && systemctl --user enable --now dld-gate-daemon.service` invoked.
- Idempotent: re-running setup does not duplicate the unit file (uses `cat > ... <<EOF`, overwrites). Service handles re-enable cleanly.
- Pre-flight: `loginctl enable-linger ${USER}` invoked (External scout: required for `--user` units to survive SSH logout).

### Task 5: Pure-function tests `test_gate_logic.py`

**Type:** test
**Files:**
- create: `scripts/vps/tests/test_gate_logic.py`
**Acceptance:**
- Real `tmp_path` git repos (NO mocks for git — mirror `test_callback.py:git_repo` fixture style, callback test_callback.py:67-78).
- `isolated_db` fixture from conftest.py reused for DB-touching tests.
- Test coverage (≥10 tests, all P0 from Devil's DA-series):
  - DA-1: commit body mentions SPEC-A but subject is for SPEC-B → `find_implementation_commit("SPEC-A", ...)` returns None
  - DA-4: `GROWTH-042` spec_id matched by `_SPEC_ID_RE` and `match_subject`
  - DA-5: spec without `## Allowed Files` → `parse_allowed_files` returns None
  - DA-6: golden oracle — commit `feat(SPEC-A): work` touching allowed file → `find_implementation_commit` returns sha
  - DA-9: commit `feat(TECH-189): work, refs ARCH-191` touching ARCH-191's allowed file → `find_implementation_commit("ARCH-191", ...)` returns None
  - `parse_allowed_files_v1` happy path + edge case (marker present, multiple paths)
  - `parse_allowed_files_legacy` happy path (heading variants)
  - `match_subject`: 3 forms (conventional `feat(SPEC-A):`, merge `Merge ... SPEC-A`, bare prefix `SPEC-A: ...`)
  - `fetch_develop` returns False on bad remote (timeout case)
  - Negative: `match_subject("feat(BUG-200): work", "TECH-189")` returns False

### Task 6: Daemon integration tests `test_gate_daemon.py`

**Type:** test
**Files:**
- create: `scripts/vps/tests/test_gate_daemon.py`
**Acceptance:**
- Coverage (≥8 tests):
  - SA-3: After 3 cycles, `git log --grep='by: gate-daemon' --all ai/lifecycle/` = 0 (lifecycle never touched by daemon).
  - SHADOW_ONLY_MODE assert fires if someone monkey-patches `SHADOW_ONLY_MODE = False`.
  - One cycle writes one row to `gate_health` table.
  - Shadow JSONL grows by exactly N lines per cycle where N = total in_progress specs across all projects.
  - Per-project error isolation: project A's git fetch fails → cycle continues, project B's specs still evaluated, error logged to `gate_health.error_msg`.
  - SHA cache: 2nd cycle with no new commits → `find_implementation_commit` not called (assert via spy/counter).
  - Heartbeat file `.gate-daemon-heartbeat` mtime updated after each cycle.
  - Daemon graceful SIGTERM: receives SIGTERM mid-cycle → `_stop.is_set()` true → exits cleanly within 2s.

### Task 7: Dependency map update `.claude/rules/dependencies.md`

**Type:** docs
**Files:**
- modify: `.claude/rules/dependencies.md`
**Acceptance:**
- New section `## scripts/vps/gate-daemon.py` with Uses/Used-by tables.
- New section `## scripts/vps/gate_logic.py` with Uses/Used-by tables.
- New changelog entry in "Last Update" table referencing ARCH-190.
- Per context-updater protocol (CLAUDE.md project rules system).

### Execution Order

1 (gate_logic) → 2 (schema+db) → 3 (gate-daemon) → 4 (setup-vps) → 5+6 (tests in parallel — different files) → 7 (docs)

Task 1 has no deps. Task 2 has no deps on Task 1 (independent change to schema). Task 3 depends on Tasks 1+2 (imports gate_logic, calls db.log_gate_cycle). Task 4 depends on Task 3 (unit references gate-daemon.py). Tasks 5+6 depend on Tasks 1+3. Task 7 depends on Tasks 1+3 being final.

---

## Flow Coverage Matrix

| # | Flow Step | Covered by Task | Status |
|---|---|---|---|
| 1 | Operator runs setup-vps.sh | Task 4 | ✓ |
| 2 | Daemon starts via systemd | Task 4 (unit file) + Task 3 (main) | ✓ |
| 3 | Per-cycle: git fetch projects | Task 3 (loop) + Task 1 (fetch_develop) | ✓ |
| 4 | Per-cycle: read in_progress specs | Task 3 (lifecycle.list_by_status call) | ✓ |
| 5 | Per-spec: parse Allowed Files | Task 1 (parse_allowed_files) | ✓ |
| 6 | Per-spec: gate check | Task 1 (find_implementation_commit, subject-only) | ✓ |
| 7 | Write shadow JSONL line | Task 3 (writer with rotation) | ✓ |
| 8 | Write gate_health row | Task 2 (log_gate_cycle) + Task 3 (call) | ✓ |
| 9 | Touch heartbeat file | Task 3 | ✓ |
| 10 | SIGTERM handling | Task 3 (signal handlers) | ✓ |
| 11 | Per-project error isolation | Task 3 (try/except per project) | ✓ |
| 12 | NEVER write lifecycle | Task 3 (SHADOW_ONLY_MODE) + Task 6 (SA-3 test) | ✓ |

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|---|---|---|---|---|---|---|
| EC-1 | Body mention does NOT mark done (DA-1) | commit `feat(BUG-200): work\n\nSee also TECH-189 for context`, touches TECH-189 allowed file | `find_implementation_commit("TECH-189", ...)` returns None | deterministic | devil | P0 |
| EC-2 | Subject match marks done (DA-6) | commit `feat(TECH-189): task 7 — timeout` touching allowed file | returns commit sha (truthy) | deterministic | devil | P0 |
| EC-3 | Cross-spec reference does NOT match (DA-9) | commit `feat(TECH-189): work, refs ARCH-191` touching ARCH-191's allowed file | `find_implementation_commit("ARCH-191", ...)` returns None | deterministic | devil | P0 |
| EC-4 | GROWTH spec_id matched (DA-4) | spec_id `GROWTH-042`, commit `feat(GROWTH-042): work` touching allowed | returns sha | deterministic | devil/L-derived-2 | P1 |
| EC-5 | Missing Allowed Files → blocked verdict (DA-5) | spec file without `## Allowed Files` section | shadow record `gate_verdict="blocked", gate_reason="missing_allowed_files"` | deterministic | devil | P1 |
| EC-6 | Shadow JSONL schema completeness | one cycle run with 2 in_progress specs across 1 project | JSONL has exactly 2 lines; each line has all 9 schema fields including `shadow_only:true` | deterministic | devil A1 | P0 |
| EC-7 | Per-project error isolation (DA-3 partial) | project A's git fetch raises CalledProcessError; project B has 1 spec | cycle completes; B's spec gets shadow record; `gate_health.error_msg` references A | deterministic | devil A7 | P0 |
| EC-8 | SHA cache short-circuits git log | 2 cycles with same `origin/develop` HEAD | `find_implementation_commit` call count after cycle 2 == call count after cycle 1 | deterministic | patterns A1b | P1 |
| EC-9 | `SHADOW_ONLY_MODE` assert fires (Wave 1 invariant) | runtime: `import gate_daemon; gate_daemon.SHADOW_ONLY_MODE = False`, then call main loop body | `AssertionError` raised | deterministic | spec invariant | P0 |
| EC-10 | Zero `write_lifecycle` references in daemon source (SA-3 static) | static grep | `grep -n "write_lifecycle" scripts/vps/gate-daemon.py` returns 0 | deterministic | FF-09 / blueprint | P0 |
| EC-11 | FF-09: no callback import in daemon (FF-09 static) | static grep | `grep -E "^import callback\|^from callback" scripts/vps/gate-daemon.py scripts/vps/gate_logic.py` returns 0 | deterministic | FF-09 / blueprint | P0 |
| EC-12 | `gate_health` table writable + readable | call `db.log_gate_cycle(1, ts, 0, 0)` then `db.get_gate_health()` | returns dict with id=1, cycle_count=1 | deterministic | task 2 acceptance | P1 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|---|---|---|---|---|---|---|
| EC-13 | Real tmp git repo + lifecycle yaml for SPEC-A status=in_progress + commit `feat(SPEC-A): work` touching allowed file | Run one cycle of gate-daemon main loop | Shadow JSONL has 1 line: `spec_id=SPEC-A, gate_verdict="done", matching_commit_sha=<sha>` | integration | full path | P0 |
| EC-14 | 2 tmp git repos as 2 projects; project A throws CalledProcessError on fetch; project B has 1 in_progress spec | Run one cycle | Shadow JSONL has 1 line (for B); `gate_health.error_msg` mentions project A; `decisions_this_cycle=1`; cycle_count incremented | integration | EC-7 in full daemon | P0 |
| EC-15 | Heartbeat file freshness | Run 2 cycles back-to-back | `.gate-daemon-heartbeat` mtime within last 60s | integration | task 3 acceptance | P1 |

### Coverage Summary
- Deterministic: 12 | Integration: 3 | LLM-Judge: 0 | Total: 15 (min 3 — met)

### TDD Order
1. EC-1, EC-3 (subject-only matching — highest risk, Devil A2/A10) → FAIL → implement `match_subject` correctly → PASS
2. EC-2, EC-4, EC-6 — full gate logic
3. EC-9, EC-10, EC-11 — Wave 1 invariants (structural)
4. EC-12 — db layer
5. EC-13, EC-14, EC-15 — integration

---

## Acceptance Verification

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|---|---|---|---|---|
| AV-S1 | gate-daemon imports cleanly | `python3 -c "import sys; sys.path.insert(0, 'scripts/vps'); import gate_daemon"` (renamed to avoid hyphen — alias via `importlib.util` if needed; test imports the module) | exit 0 | 5s |
| AV-S2 | gate_logic is pure (no I/O on import) | `python3 -c "import sys; sys.path.insert(0, 'scripts/vps'); import gate_logic; print('OK')"` | prints OK, no errors, no side effects | 5s |
| AV-S3 | schema.sql applies cleanly | `python3 -c "import sqlite3; c=sqlite3.connect(':memory:'); c.executescript(open('scripts/vps/schema.sql').read()); print('OK')"` | prints OK | 5s |
| AV-S4 | systemd unit syntax | `systemd-analyze --user verify ~/.config/systemd/user/dld-gate-daemon.service` (after setup-vps.sh ran) | no errors | 10s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|---|---|---|---|---|
| AV-F1 | Pure-function tests pass | venv | `cd scripts/vps && python -m pytest tests/test_gate_logic.py -v` | all green, ≥10 tests |
| AV-F2 | Daemon integration tests pass | venv | `cd scripts/vps && python -m pytest tests/test_gate_daemon.py -v` | all green, ≥8 tests |
| AV-F3 | FF-09 invariant (static grep — Wave 1 fitness function preview) | clean repo | `grep -E "^import callback\|^from callback" scripts/vps/gate-daemon.py scripts/vps/gate_logic.py; grep "write_lifecycle" scripts/vps/gate-daemon.py` | both grep returns no matches (exit 1) |
| AV-F4 | Manual smoke after deploy | VPS, post-setup-vps.sh | `systemctl --user status dld-gate-daemon` + tail journal for 65s | unit active; 1+ cycle logs visible |

### Verify Command

```bash
# Smoke (run from repo root)
python3 -c "import sys; sys.path.insert(0, 'scripts/vps'); import gate_logic; print('gate_logic OK')"
python3 -c "import sqlite3; c=sqlite3.connect(':memory:'); c.executescript(open('scripts/vps/schema.sql').read()); print('schema OK')"

# Functional
cd scripts/vps && python -m pytest tests/test_gate_logic.py tests/test_gate_daemon.py -v

# FF-09 static check (must return 0 matches)
grep -E "^import callback|^from callback" scripts/vps/gate-daemon.py scripts/vps/gate_logic.py && echo "FAIL: callback import" || echo "OK: FF-09 holds"
grep "write_lifecycle" scripts/vps/gate-daemon.py && echo "FAIL: lifecycle write" || echo "OK: daemon read-only"
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

(Daemon runs on VPS, no HTTP endpoint. Wave 6 MP-014 will add `vps-orch gate-health` CLI — out of scope.)

---

## Definition of Done

### Functional
- [ ] Feature works as specified (gate-daemon polls, writes shadow JSONL, never touches lifecycle)
- [ ] All 7 tasks from Implementation Plan completed

### Tests
- [ ] All EC-1..EC-15 pass
- [ ] Coverage not decreased on `scripts/vps/`

### E2E (this is a daemon — operator manual verification)
- [ ] On VPS: `systemctl --user status dld-gate-daemon` shows `active (running)`
- [ ] On VPS: `tail -f /home/dld/projects/dld/scripts/vps/gate-daemon-shadow.jsonl` shows new lines every ~60s
- [ ] On VPS: `sqlite3 scripts/vps/orchestrator.db "SELECT * FROM gate_health ORDER BY id DESC LIMIT 3"` shows recent cycles
- [ ] On VPS: `stat scripts/vps/.gate-daemon-heartbeat` mtime within last 90s

### Acceptance Verification
- [ ] AV-S1..S4 all pass
- [ ] AV-F1..F4 all pass
- [ ] Verify Command runs without FAIL output

### Wave 1 Exit Criteria (from migration-path.md, enforced manually post-merge)
- [ ] Daemon runs for ≥48h on VPS without crash (operator check)
- [ ] Shadow JSONL has ≥100 decisions logged after 48h (acceptance from migration-path.md)
- [ ] `grep "updated_by: gate-daemon" ai/lifecycle/*.yaml` = 0 across all 10 projects (SA-3 in production)

### Technical
- [ ] `./test fast` passes (or `cd scripts/vps && python -m pytest -q` if no top-level harness)
- [ ] No regressions in `test_callback.py`, `test_lifecycle.py`, `test_orchestrator.py`
- [ ] `scripts/vps/gate-daemon.py` ≤ 400 LOC; `scripts/vps/gate_logic.py` ≤ 400 LOC

---

## Autopilot Log
[Auto-populated by autopilot during execution]
