# System Blueprint — callback / lifecycle / orchestrator Contour (TO-BE)

**Scope:** `scripts/vps/` — the multi-project orchestration daemon contour
**Mode:** Retrofit (brownfield) — Alternative C chosen
**Date:** 2026-05-23
**Status:** TO-BE specification. AS-IS is in `ai/audit/deep-audit-report.md`. Migration in `ai/architect/migration-path.md`.

This is a SINGLE-FILE blueprint (vs the 6-file Greenfield template) because retrofit of one contour does not need full system-wide design rewrite. Other domain blueprints (managed projects' business logic) are unaffected and not in scope.

---

## 1. Bounded Contexts (after Wave 5)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Event Reaction Context (Loop 1 — pueue-driven)                         │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │   callback.py    │───▶│   dispatcher.py  │───▶│ event_writer.py  │  │
│  │  (≤100 LOC)      │    │   (~150 LOC)     │    │   (~170 LOC)     │  │
│  │  pueue handler   │    │  QA/reflect      │    │  Hermes notify   │  │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘  │
│         │                                                                │
│         ▼                                                                │
│  ┌──────────────────┐                                                   │
│  │      db.py       │  (release_slot, finish_task — that's it)          │
│  │   SQLite WAL     │                                                   │
│  └──────────────────┘                                                   │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  Status Determination Context (Loop 2 — polling-driven)                 │
│  ┌──────────────────┐    ┌──────────────────┐                          │
│  │  gate-daemon.py  │───▶│   lifecycle.py   │  ──▶ git per-spec YAML   │
│  │   (~200 LOC)     │    │   (~300 LOC)     │      (multi-machine SoR)│
│  │  60s polling     │    │  atomic writer   │                          │
│  │  origin/develop  │    │  + state machine │                          │
│  └──────────────────┘    └──────────────────┘                          │
│         │                                                                │
│         ▼                                                                │
│  ┌──────────────────┐                                                   │
│  │    circuit.py    │  (alert-only, no pueue-pause — Bruce)             │
│  │   (~80 LOC)      │                                                   │
│  └──────────────────┘                                                   │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  Orchestration Context (continuous, daemon)                              │
│  ┌──────────────────┐                                                   │
│  │ orchestrator.py  │  ─── scans queued from git lifecycle yamls        │
│  │   (~400 LOC)     │  ─── manages compute slots in db.py               │
│  │  systemd daemon  │  ─── dispatches to pueue                          │
│  └──────────────────┘  ─── intake from ai/inbox/ via Hermes             │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  Audit & Render Context                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                          │
│  │    audit.py      │    │ render_backlog.py│  ──▶ backlog.md (render) │
│  │   (~100 LOC)     │    │   (~200 LOC)     │      (NEVER read as SoR) │
│  │  JSONL writer    │    │  cron-driven OR  │                          │
│  └──────────────────┘    │  post-gate hook  │                          │
│                          └──────────────────┘                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  Agent API Context (Erik's missing layer)                                │
│  ┌──────────────────┐                                                   │
│  │  vps_orch CLI    │  Single entry for agents to query/mutate state    │
│  │   (~200 LOC)     │  JSON output. NO bypassing of writers.            │
│  └──────────────────┘                                                   │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  Cross-Cutting (shared util)                                             │
│  ┌──────────────────┐                                                   │
│  │    common.py     │  SPEC_ID_PATTERN, _load_env, _setup_logging,      │
│  │   (~120 LOC)     │  _pueue_add, AuditPayload, GateResult dataclasses│
│  └──────────────────┘                                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

### Allowed inter-context calls

| From → To | Allowed? | Method |
|---|---|---|
| Event Reaction → SQLite | YES | direct (db.py functions) |
| Event Reaction → dispatcher | YES | direct call |
| Event Reaction → Status Determination | **NO** (key invariant — temporal decoupling) | FF-09 enforces zero imports |
| Status Determination → git plumbing (lifecycle.py) | YES | direct call |
| Status Determination → SQLite (read-only) | YES | for circuit state |
| Orchestration → SQLite | YES | direct |
| Orchestration → git read (lifecycle yamls) | YES | scan_queued |
| Orchestration → Status Determination | **NO** | orchestrator dispatches; daemon updates separately |
| Spec Authoring (Spark) → lifecycle.create_initial | YES | direct, from any of 3 machines |
| Anything → Audit | YES (write-only) | audit.write(payload) |
| Audit → Anything | **NO** | audit is sink, not source |
| Agent → vps-orch CLI | YES (preferred path) | subprocess call from agent context |
| Agent → SQLite | DISCOURAGED | use vps-orch instead |
| Agent → lifecycle YAML | DISCOURAGED | use vps-orch instead |

---

## 2. Ubiquitous Language (Resolved)

| Term | Definition (resolve language drift identified by Eric) |
|---|---|
| **status** | Single field in lifecycle yaml: one of `queued`, `in_progress`, `blocked`, `done`, `resumed`, `draft`. NO synonym in code. |
| **phase** | DIFFERENT from status. Project-level field in SQLite `project_state.phase`. Reflects orchestration state machine (idle, dispatched, qa_pending, etc.), NOT spec status. |
| **gate** | The single decision: "is spec done on origin/develop?". Lives in gate-daemon. NO "guard", "rule", "check", "verify" synonyms going forward (those were 6 names for the same thing). |
| **dispatch** | "Tell pueue to run a task". Lives in orchestrator + dispatcher. NOT "send", "submit", "enqueue" — only "dispatch". |
| **writer** | Code that calls `lifecycle.write_lifecycle`. Identified by `by=` field. Allowed writers: gate-daemon, orchestrator (for create_initial only), spec_operator. Pre-Wave-3 callback is a writer; post-Wave-3 it is NOT. |
| **verdict** | gate-daemon's structured output: `GateResult{verdict: done\|in_progress\|blocked, reason: GateReason, evidence: [commits]}`. Replaces `_emit_audit(12 positional args)`. |
| **decision** | Audit entry written to JSONL. Permanent record. Distinct from gate-daemon's in-memory `verdict`. |
| **bootstrap** | DELETED. Word should not appear in code post-Wave 4. Spec creation is "Spark writes lifecycle". |
| **lifecycle** | The state machine + its yaml representation. NOT "spec status", NOT "task state" — those are subsets. |

---

## 3. Data Architecture

### System of Record per entity

| Entity | SoR | Multi-machine? | Audit Trail |
|---|---|---|---|
| Spec lifecycle status | `ai/lifecycle/{spec_id}.yaml` HEAD in each project repo | YES — git push/pull replicates | git log per-file |
| Spec body + metadata | `ai/features/{spec_id}-{date}-{title}.md` HEAD | YES — git | git log per-file |
| Compute slot allocation | SQLite `compute_slots` table on VPS | NO — VPS-only operational state | task_log |
| Task execution log | SQLite `task_log` on VPS | NO | self |
| Callback decisions (circuit) | SQLite `callback_decisions` on VPS | NO | self |
| SDK errors telemetry | SQLite `sdk_post_result_errors` on VPS | NO | self |
| Gate decisions | `scripts/vps/gate-decisions.jsonl` (append-only) | NO | self |
| Project state (phase) | SQLite `project_state` on VPS | NO | task_log |
| Hermes events | `ai/openclaw/pending-events/*.json` | NO (consumed) | self (until consumed) |
| Audit log | `scripts/vps/callback-audit.jsonl` (renamed: `scripts/vps/audit.jsonl`) | NO | self |

**Key design choice:** lifecycle status is in git (preserves ADR-023 multi-machine). All operational state (slots, queues, telemetry) is in SQLite on the VPS only — these don't need multi-machine sync.

### Schema invariants (enforced)

- **VALID_TRANSITIONS** (in lifecycle.py):
  - `queued → in_progress` (allowed; sets dispatched_at)
  - `in_progress → done | blocked` (allowed)
  - `in_progress → resumed` (allowed)
  - `blocked → resumed | done` (allowed; done only from gate-daemon)
  - `done → *` REJECTED (terminal state)
  - `queued → done` REJECTED — must go through in_progress (closes Root 1's bug class structurally)
  - `* → draft` REJECTED (draft is initial-only)
- **dispatched_at** populated on `queued → in_progress` (replaces always-null `started_at`)
- **finished_at** populated on `in_progress → done | blocked`
- **allowed_files_hash** DELETED (dead field, 190+ nulls)
- **transitions[]** append-only (immutable history; never reset)
- **by** must be in `_ALLOWED_WRITERS` (process token enforces in Wave 6)
- **version** monotonic int (used for optimistic locking)

### SQLite schema additions (P0 + Wave 6)

```sql
-- P0
CREATE INDEX IF NOT EXISTS idx_task_log_pueue_id ON task_log(pueue_id);
CREATE INDEX IF NOT EXISTS idx_task_log_started_at ON task_log(started_at);
CREATE INDEX IF NOT EXISTS idx_night_findings_project_status ON night_findings(project_id, status);

-- Schema versioning (Wave 6)
PRAGMA user_version = 5;
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    description TEXT NOT NULL
);

-- Retention (Wave 6 cron)
-- DELETE FROM task_log WHERE started_at < datetime('now', '-90 days');
-- DELETE FROM callback_decisions WHERE ts < datetime('now', '-30 days');
-- DELETE FROM sdk_post_result_errors WHERE ts < datetime('now', '-90 days');
```

---

## 4. API Contracts

### vps-orch CLI (agent-facing, JSON output)

| Subcommand | Args | Output | Side effects |
|---|---|---|---|
| `vps-orch status SPEC-ID [--project P]` | spec_id, optional project | `{spec_id, status, blocked_reason, dispatched_at, ...}` | none (read) |
| `vps-orch health` | none | `{circuit: closed\|open, slots: {...}, queue_depth: N, gate_daemon: {last_poll_at, cycle_count}, heartbeat: {last_seen}}` | none |
| `vps-orch gate-check SPEC-ID --project P` | spec_id, project | `{verdict, evidence: [{sha, subject, date}], reason}` | none (dry-run) |
| `vps-orch audit SPEC-ID --since DURATION` | spec_id, duration | `[{ts, event, ...}]` (JSONL parsed) | none (read) |
| `vps-orch gate-history SPEC-ID` | spec_id | `[{ts, verdict, reason}]` | none |
| `vps-orch circuit-status` | none | `{state, demotes_last_10min, last_open_at, last_reset_at}` | none |
| `vps-orch dispatch SPEC-ID --project P` | spec_id, project | `{pueue_id, slot}` | dispatches pueue task (operator-confirmed) |
| `vps-orch lifecycle-set SPEC-ID --status S --reason R` | spec_id, status, reason | `{ok: bool, error?: str}` | writes lifecycle yaml (operator-only) |

All commands default to `--json` output. `--text` flag for human terminal viewing.

### Internal API (lifecycle.py)

```python
def read_lifecycle(repo_dir: str, spec_id: str) -> Optional[dict]
def write_lifecycle(repo_dir: str, spec_id: str, status: str, *, by: str, reason: str | None = None, pueue_id: int | None = None) -> None  # raises VALID_TRANSITIONS violation
def create_initial(repo_dir: str, spec_id: str, priority: str, kind: str, status: str = "queued") -> None  # callable from any machine
def list_by_status(repo_dir: str, status: set[str]) -> list[str]  # for orchestrator.scan_queued
```

### Internal API (gate-daemon.py)

Subprocess only. No imported module. Calls:
- `git -C {project_path} log origin/develop --grep="{spec_id}" --pretty=%h%x00%s -- {allowed_files}` (with timeout=15)
- `lifecycle.write_lifecycle(..., by="gate-daemon")` (via subprocess `python3 -c "from lifecycle import write_lifecycle; ..."` or via `vps-orch lifecycle-set`)

### Internal API (callback.py — post-Wave 6)

```python
def main():
    pueue_id, group, result = sys.argv[1:4]
    label = resolve_label(pueue_id)
    spec_id = extract_spec_id(label)
    project = resolve_project(label)
    db.release_slot(pueue_id)
    db.finish_task(pueue_id, result)
    if result == "Success":
        dispatcher.dispatch_qa_reflect(project, spec_id)
    event_writer.notify(project, spec_id)
    sys.exit(0)  # ALWAYS 0
```

That's it. ~30 LOC for the body. Total file ~80 LOC including imports + helpers.

---

## 5. Cross-Cutting Rules (as code, not prose)

### Identity enforcement (Wave 6)

```python
# common.py
ALLOWED_WRITERS = {"gate-daemon", "orchestrator", "spec_operator", "spark", "migration"}
# NOTE: "callback" REMOVED post-Wave 6 — callback is read-only for lifecycle

# lifecycle.py write_lifecycle:
ORCHESTRATOR_PROCESS_TOKEN = os.environ.get("ORCHESTRATOR_PROCESS_TOKEN")
def write_lifecycle(..., by: str):
    if by not in ALLOWED_WRITERS:
        raise ValueError(f"writer {by!r} not in {ALLOWED_WRITERS}")
    if by in {"gate-daemon", "orchestrator"} and not ORCHESTRATOR_PROCESS_TOKEN:
        raise PermissionError(f"writer {by!r} requires ORCHESTRATOR_PROCESS_TOKEN (systemd env)")
    # ... rest of write
```

Process token lives in systemd unit `Environment=ORCHESTRATOR_PROCESS_TOKEN=...`. Agents in pueue task environments don't have it → cannot impersonate gate-daemon or orchestrator. Spark/spec_operator are CLI-invoked (`by` checked separately). This closes Bruce's "honor system" gap.

### Error taxonomy (post-Wave 5)

```python
# common.py
class VPSOrchError(Exception): pass
class LifecycleWriteRaceError(VPSOrchError): ...
class InvalidTransitionError(VPSOrchError): ...
class GateNoMatchError(VPSOrchError): ...
class PueueIntegrationError(VPSOrchError): ...
class ProcessTokenMissingError(VPSOrchError): ...

# Per ADR-004: bare except only in hooks. Other code uses typed exceptions.
# Fitness function FF-10 (new): grep -E "except Exception" scripts/vps/*.py
#   → must match only inside `scripts/vps/audit.py` (audit is fail-silent by design)
```

### Money rule (already enforced by ADR-001)

- All money in cents (int)
- `cost_usd REAL` in `sdk_post_result_errors` → migrate to `cost_millicents INTEGER` in Wave 0 P0-equivalent OR explicit Wave 6 schema migration

### Logging

```python
# common.py _setup_logging
# All logs JSON-structured: {ts, level, module, msg, **context}
# Levels:
#   ERROR — incident class events (gate-daemon down, write failures)
#   WARNING — multi-machine push failures, BOOTSTRAP_ANOMALY, circuit trips
#   INFO — normal lifecycle events
#   DEBUG — diagnostic, off in prod by default

# Best-effort failures → WARNING + counter file increment (NOT debug)
```

### Fitness functions (FF-01..FF-09, Wave 6)

| FF | Check | CI gate |
|---|---|---|
| FF-01 | `wc -l scripts/vps/*.py` → all ≤400 (tests/* ≤600) | PR fails on violation |
| FF-02 | grep zombie validator imports (e.g., `spec_lint`) | PR fails if found |
| FF-03 | Sole writer per data store (analyze `lifecycle.write_lifecycle` callsites) | PR fails on new writer not in ALLOWED_WRITERS |
| FF-04 | All `tests/` dirs in `pyproject.toml: testpaths` | covered in P0 |
| FF-05 | Functions per module ≤25, public exports ≤7 | PR fails on violation |
| FF-06 | CHANGELOG.md entry for each incident-driven fix references test file | manual review enforced |
| FF-07 | `_subject_implements` / gate matches both canonical scope AND trailer conventions (golden dataset) | PR fails on regression |
| FF-08 | `_SPEC_ID_RE` defined in exactly one place (common.py) | PR fails on duplicates |
| FF-09 | `grep -E "(import callback\|from callback)" scripts/vps/gate-daemon.py` returns empty | PR fails on violation (temporal decoupling invariant) |

---

## 6. Integration Map (TO-BE)

### External dependencies (unchanged)

- pueue CLI (with `--print-task-id`, `--json` flags)
- git CLI (porcelain + plumbing; plumbing simplified in C — fewer subprocess calls)
- claude_agent_sdk
- openclaw/Hermes (notifications)
- SQLite (local)
- systemd (--user)

### Internal data flow

```
Spark (any machine)
    │
    ▼
git push → ai/features/SPEC.md + ai/lifecycle/SPEC.yaml + backlog row
    │
    ▼ (git pull on VPS)
orchestrator polls → sees `status: queued` → dispatches via pueue
    │
    ▼
pueue runs claude-runner.py → autopilot does work → commits to feature branch → merges to develop → pushes
    │
    ▼
pueue completion → callback.py → release slot, dispatch QA/reflect → exit 0
    │
    ▼ (independently, on 60s timer)
gate-daemon → git log origin/develop --grep SPEC → if match → lifecycle.write_lifecycle(by="gate-daemon", "done")
    │
    ▼
git push → other 2 machines git pull → see done status
```

### Failure modes (mapped)

| Failure | Detection | Mitigation |
|---|---|---|
| Pueue daemon down | callback never fires; ALERT-004 heartbeat | systemd auto-restart |
| Git push fails (network) | ALERT-002 lifecycle_push_failures >0 | retry on next gate cycle |
| Gate-daemon hung | ALERT-005 last_poll_at stale | systemd WatchdogSec=120 |
| Orchestrator hung | ALERT-004 heartbeat stale >10min | systemd Restart=always |
| Mass-bootstrap anomaly | ALERT-001 fires at threshold >3 in 5min | operator intervenes |
| Circuit breaker open | ALERT-006 informational | operator runs `vps-orch circuit-status` and decides |

---

## 7. Agent Architecture

### Agent-as-consumer pattern (Erik's contribution)

Agents (autopilot, QA, reflect, planner, debugger) interact with this contour ONLY through `vps-orch` CLI. Direct reads of SQLite or lifecycle YAML are discouraged (lint warning).

Why: changes inside the contour (decomposition, SQLite schema, gate logic) become opaque to agents. Agents only depend on CLI JSON contract. Context budget for an agent task drops from ~3000 tokens (reading callback + lifecycle + ADRs) to ~50 tokens (one tool call to `vps-orch status SPEC-ID`).

### Agent-as-threat-actor pattern (Bruce's contribution)

Defensive layers:
1. **Process token** in systemd env. Pueue task agents don't inherit it → cannot impersonate gate-daemon.
2. **Filesystem isolation:** `scripts/vps/` is writable only by `dld` user; agents run in worktrees with their own working directory. (Current state: same user, same FS. Defense relies on git as integrity layer.)
3. **Pre-commit guard** (deployed to all 10 managed projects in MP-016): any attempt to commit lifecycle yaml without process token → rejected.
4. **Git author tag:** `gate-daemon` commits attributed; suspicious authors flagged.
5. **`scan_queued` audit anti-recency:** reads recent audit JSONL to detect rapid-fire dispatch attempts.

Threats accepted:
- Adversarial agent with `dld` shell access can read process token (single-user VPS — not in threat model)
- Insider threat (founder is single operator)

### Agent reference doc (Wave 6)

`scripts/vps/AGENT_REFERENCE.md` (~1000 tokens, structured) — distilled API contract for agents. Contains:
- `vps-orch` CLI quickref
- Lifecycle state machine (VALID_TRANSITIONS table)
- "How to find spec status" (one CLI call)
- "How to add a new gate rule" (CANNOT — gate is single-rule; new conventions extend `_subject_implements` if needed, OR add to gate-daemon's `git log` invocation with golden dataset test)
- Error taxonomy (when to retry vs fail)

---

## 8. Operations (Charity's contribution)

### SLOs (measurable from Wave 6)

| SLO | Target | Measurement |
|---|---|---|
| SLO-1 | 95% of queued specs dispatched within 10 min | `task_log.started_at - lifecycle.created_at` |
| SLO-2 | 99% of callbacks reach definitive verdict (Success / Failed-with-reason) | callback exit code distribution |
| SLO-3 | Zero `lifecycle_push_failures` per 24h | ALERT-002 |
| SLO-4 | Zero fake-done flips per release (gate-daemon writes match git log evidence) | shadow vs real parity check (Wave 2 verification ongoing) |
| SLO-5 | Orchestrator + gate-daemon liveness ≥99.9% per 30 days | heartbeat + WatchdogSec |

### Counter-file metrics (Wave 6, NOT Prometheus)

`scripts/vps/metrics/*.txt` (one int per file). Updated by callback, gate-daemon, orchestrator. Read by `simple_alerts.py` cron.

- `bootstrap_done_total`
- `lifecycle_writes_total{by=gate-daemon|orchestrator|...}`
- `gate_decisions_total{verdict=done|in_progress|blocked}`
- `lifecycle_push_failures_total`
- `circuit_trips_total`
- `gate_cycle_total`
- `gate_demote_total`
- `bootstrap_anomaly_total` (>3 in 5min)

### Alerts (6, all wired to Hermes/Telegram)

ALERT-001 — bootstrap mass-done (BOOTSTRAP_ANOMALY, P0 in Wave 0)
ALERT-002 — multi-machine convergence broken (push failures)
ALERT-003 — gate demote rate >5/hour (convention drift)
ALERT-004 — orchestrator heartbeat stale
ALERT-005 — gate-daemon poll stale
ALERT-006 — circuit-breaker open (informational)

---

## 9. What's Explicitly Preserved (Not Changing)

- ADR-023 (lifecycle SoT = git per-spec YAML) — preserved for multi-machine
- pueue + systemd + SQLite stack
- Hermes/openclaw event mechanism
- claude_agent_sdk integration in claude-runner.py
- Multi-project orchestrator paradigm (10 managed projects)
- Cron-based night reviewer

---

## 10. What's Explicitly Deleted

- ADR-018 (markdown markers) — superseded; `## Kills` for spec_lint, DLD-CALLBACK-MARKER, marker_utils.py (Wave 0)
- 8-rule gate in callback (Wave 3) → replaced by 1-rule gate in gate-daemon
- `_subject_implements` regex (Wave 3) → replaced by `git log --grep`
- `bootstrap_new_specs` (Wave 4)
- `verify_status_sync` (Wave 3)
- `_emit_audit` 12-arg signature (Wave 5) → AuditPayload dataclass
- `_atomic_write_file` duplicate (Wave 2 simplification)
- `migrate_backlog_to_lifecycle.py` (Wave 0) — one-shot already ran
- `spec_operator._reset_circuit_cli` cross-import (Wave 5) — circuit.reset() is public
- `allowed_files_hash` field (Wave 2)
- `_load_env`, `_setup_logging`, `_pueue_add` duplicates (Wave 5)
- `_SPEC_ID_RE` divergence (Wave 0 + 5)
- DLD-CALLBACK-MARKER blocks in 23 spec files (Wave 0)
- `.worktrees/ARCH-186`, `.worktrees/ARCH-187` (Wave 0 cleanup)

---

## 11. ADR Updates (will be added to .claude/rules/architecture.md)

- **ADR-025: Alternative C — Decoupled Gate Daemon**
  - Decision: Status determination is asynchronous, polling-driven, in a separate process (`gate-daemon.py`).
  - Rationale: Eliminates temporal coupling (Neal's insight). Callback no longer infers status. Trade-off: 60s eventual consistency window, acceptable for autopilot, surfaced via `vps-orch status`.
  - **## Kills:** 8-rule gate in `verify_status_sync`, `_subject_implements`, `_is_done_on_develop`, `_fetch_develop`, `_emit_audit` 12-arg signature. Also kills `bootstrap_new_specs` (separate concern but same wave).

- **ADR-026: Spark Writes Lifecycle Directly**
  - Decision: Spec authoring (Spark) writes `lifecycle.create_initial` at end of spec creation. Works from any of 3 machines.
  - Rationale: Eliminates `bootstrap_new_specs` (Root 1 of 2026-05-23 incident). Single source of spec creation. No second writer.
  - **## Kills:** `orchestrator.bootstrap_new_specs`, WT read of `backlog.md`.

- **ADR-027: Agent API Contract Layer (`vps-orch` CLI)**
  - Decision: All agent interactions with this contour go through `vps-orch` CLI with JSON output. Direct SQLite/YAML reads discouraged.
  - Rationale: Erik's anti-corruption layer. Context budget per agent task drops 60x. Internal refactors don't break agents.

- **ADR-028: Process-Token Identity Enforcement**
  - Decision: `lifecycle.write_lifecycle` from `gate-daemon` or `orchestrator` requires `ORCHESTRATOR_PROCESS_TOKEN` env var (from systemd unit).
  - Rationale: Bruce's "honor system theater" fix. Agents in pueue tasks don't inherit the token; cannot impersonate writer.
  - **## Replaces:** ARCH-187's pre-commit-hook approach (was deployed nowhere).

---

## 12. ADR Governance (Neal's contribution — applies going forward)

Every new ADR in this codebase MUST include a `## Kills` section listing exact `file:line` artifacts deactivated. A new fitness function `test_adr_kills_complete.py` verifies the listed artifacts are actually removed within 1 release of the ADR being merged.

ADRs without `## Kills` (e.g., when truly additive) must include `## Kills: NONE — purely additive` with rationale.

---

## References

- Audit: `ai/audit/deep-audit-report.md`
- Architect synthesis: `ai/architect/architectures.md`
- Migration path: `ai/architect/migration-path.md`
- Persona research: `ai/architect/research-*.md` (8 files)
- Cross-critiques: `ai/architect/critique-*.md` (8 files)
- ADR chain: `.claude/rules/architecture.md`
