# Migration Path: AS-IS → TO-BE (Alternative C — Decouple & Defer)

**Created:** 2026-05-23
**Source:** Architect retrofit synthesis from deep audit (85 findings, 8 personas, 8 critiques)
**Chosen alternative:** **C — Decouple & Defer**
**Multi-machine context (founder-confirmed):** 3 dev machines (VPS + 2 laptops); VPS runs orchestrator 24/7 as sole writer; all 3 machines pull/push git; Spark runs on any machine. ADR-023 git-as-distribution-channel is preserved.
**Total cost:** ~$150 compute, **6 waves**, 5-6 weeks wall-clock
**Universal exit criterion:** callback.py = ~80 LOC + gate runs as independent daemon + ZERO incidents in this contour for 4 weeks straight after Wave 6 ships.

---

## Core Architectural Decisions (Alt C)

1. **Temporal coupling устраняется структурно.** Gate physically lives in `gate-daemon.py`, separate systemd unit, separate process. Callback **cannot** call gate — they don't share imports.
2. **Two orthogonal loops** (Brooks: conceptual integrity through simplicity):
   - **Loop 1 (event-driven):** pueue completion → callback → release slot, dispatch QA/reflect, exit. ~80 LOC.
   - **Loop 2 (polling):** every 60s → gate-daemon → for each in_progress spec, check `git log origin/develop --grep SPEC-ID` → update lifecycle YAML if found.
3. **Git per-spec YAML remains SoT** (ADR-023 preserved — multi-machine requirement is real per founder).
4. **Single rule gate:** `git log origin/develop --grep "SPEC-ID"` (touching allowed_files). Replaces 8-rule + 202-LOC `_subject_implements` + 460/636 awardybot false-blocked.
5. **bootstrap_new_specs killed.** Spark writes `lifecycle.create_initial(...)` directly when creating spec (regardless of which of 3 machines Spark runs on).
6. **Eventual consistency window: 60s.** After merge → up to 60s before lifecycle yaml flips to `done`. Acceptable for autopilot; surfaced in `vps-orch status` CLI for humans.

---

## Universal Wave 0 — P0 Hardening Cluster

**Already specced** (`/spark` in flight as separate TECH-XXX). Must merge BEFORE Wave 1 begins.

- 10 P0 items (testpaths, conftest autouse, token rotation, zombie cleanup, BOOTSTRAP_ANOMALY, push WARNING, GROWTH regex, timeouts, heartbeat, identity fix)
- Cost: ~$15, 2-3 days
- Dependency: none
- Risk: R1
- Exit criterion: all 10 items shipped to develop; orchestrator restarts cleanly; testpaths picks up ~100 new tests in CI

**Wave 1 cannot start until Wave 0 ships** — testpaths fix and zombie cleanup must be in develop before refactoring lands.

---

## Wave 1: Foundations — Gate Daemon (Parallel, Shadow Mode)

**Purpose:** Build `gate-daemon.py` alongside existing callback. Shadow-write lifecycle decisions for parity verification. Do NOT switch authority yet.

### MP-001: gate-daemon.py shadow implementation
- **Type:** ARCH
- **Priority:** P0
- **Risk:** R1
- **Depends on:** Wave 0 (P0 cluster)
- **Description:** New file `scripts/vps/gate-daemon.py` (~150 LOC). Polls origin/develop every 60s. For each spec across all projects where `lifecycle.status in {in_progress, queued}`, runs `git log origin/develop --grep "SPEC-ID" -- <allowed_files>`. If matching commit found → writes shadow entry to `scripts/vps/gate-daemon-shadow.jsonl` (NOT lifecycle yaml). Emits cycle counter + last_poll_at via SQLite for `vps-orch gate-health`.
- **Files affected:**
  - NEW: `scripts/vps/gate-daemon.py`
  - NEW: `~/.config/systemd/user/dld-gate-daemon.service`
  - NEW: `scripts/vps/gate_logic.py` (extracted pure functions: `parse_allowed_files`, `find_implementation_commit`, `match_subject`)
- **Acceptance criteria:**
  - Daemon runs continuously as systemd `--user` unit (Restart=on-failure, WatchdogSec=120s)
  - Cycle counter increments every ~60s
  - Shadow JSONL grows with realistic decisions
  - `vps-orch gate-health` returns `{"last_poll_at": ISO, "cycle_count": N, "in_progress_specs": M}`
  - Zero writes to lifecycle yaml from gate-daemon (verified by git log filter)
- **Compute cost:** ~$15 (file creation + tests)
- **Wall-clock:** 1 week

### MP-002: Shadow JSONL format + reader
- **Type:** TECH
- **Priority:** P1
- **Risk:** R2
- **Depends on:** MP-001
- **Description:** Structured shadow log entry: `{ts, spec_id, project, gate_verdict: done|in_progress|blocked, gate_reason, matching_commit_sha, allowed_files_count}`. Reader function `audit.read_shadow_decisions(since_ts)` for parity comparison.
- **Files affected:**
  - `scripts/vps/gate-daemon.py` (writer)
  - NEW: `scripts/vps/audit.py` (reader; this will be extracted-from-callback in Wave 4 — bootstrap it now)
- **Acceptance criteria:** Shadow JSONL is valid JSONL, every line parseable; tests cover happy path + corrupt-line tolerance
- **Compute cost:** ~$3
- **Wall-clock:** 1-2 days (parallel with MP-001 finishing)

### Wave 1 Exit Criteria
- Gate-daemon runs for 48 hours minimum
- Shadow JSONL has ≥100 decisions logged
- `vps-orch gate-health` exposes daemon liveness
- No writes to lifecycle yaml from gate-daemon
- All P0 items from Wave 0 still passing CI

---

## Wave 2: Parity Verification (Observation Week)

**Purpose:** Compare every status decision made by old callback gate AND new gate-daemon. Confirm equivalence before cutover.

### MP-003: Parity comparator + daily report
- **Type:** TECH
- **Priority:** P0
- **Risk:** R2
- **Depends on:** MP-001, MP-002
- **Description:** Cron job at 08:00 UTC compares last 24h decisions between callback audit JSONL and gate-daemon shadow JSONL for the same spec_id. Output: `ai/architect/parity-reports/YYYY-MM-DD.md` with table {spec_id, callback_verdict, daemon_verdict, agreement (Y/N), divergence_reason}.
- **Files affected:**
  - NEW: `scripts/vps/parity_compare.py` (~80 LOC)
  - Cron entry (manual)
- **Acceptance criteria:**
  - Daily report generated for 7 consecutive days
  - Agreement rate ≥ 98% by day 7 (some divergence expected for edge cases — investigate each)
  - Divergence reasons documented (e.g., "callback uses regex, daemon uses git log --grep — daemon caught awardybot trailer convention callback missed" is expected)
- **Compute cost:** ~$5
- **Wall-clock:** 1 week (observation period dominates)

### MP-004: Fix divergence root causes
- **Type:** BUG
- **Priority:** P0
- **Risk:** R1
- **Depends on:** MP-003 daily reports
- **Description:** For each divergence reported, decide: callback was wrong (gate-daemon is the new truth — document) OR gate-daemon has a bug (fix gate-daemon). Update gate-daemon logic until agreement ≥99% on 7-day rolling window.
- **Acceptance criteria:** 99% agreement on 7 consecutive daily reports
- **Compute cost:** ~$5 (depending on bug count)
- **Wall-clock:** within observation week

### Wave 2 Exit Criteria
- 7 daily parity reports with ≥99% agreement
- All divergences classified and either fixed in gate-daemon OR documented as "callback was wrong, gate-daemon is correct"
- Founder confidence to proceed with cutover

---

## Wave 3: Cutover (Authority Transfer)

**Purpose:** Gate-daemon becomes sole status determiner. Remove gate logic from callback.

### MP-005: Gate-daemon writes lifecycle yaml
- **Type:** ARCH
- **Priority:** P0
- **Risk:** R0 (this is the irreversible commitment — but reversible via git revert)
- **Depends on:** Wave 2 (parity ≥99% for 7 days)
- **Description:** Gate-daemon switches from shadow-write to real `lifecycle.write_lifecycle(by="gate-daemon")`. Add "gate-daemon" to `_ALLOWED_WRITERS`. Callback's `verify_status_sync` keeps running for 1 week as final-check fallback (warning-only mode), then removed in MP-007.
- **Files affected:**
  - `scripts/vps/lifecycle.py` (add "gate-daemon" to _ALLOWED_WRITERS)
  - `scripts/vps/gate-daemon.py` (switch shadow→real write)
- **Acceptance criteria:**
  - Lifecycle yaml updates appear in git log with `by: gate-daemon` author tag
  - Parity reports continue ≥99% (callback gate still runs)
  - Eventual consistency window measurable: time-from-merge to lifecycle-yaml-update p95 < 90s
- **Compute cost:** ~$5
- **Wall-clock:** 1 day cutover + 1 week observation

### MP-006: Remove gate from callback hot path
- **Type:** ARCH
- **Priority:** P0
- **Risk:** R1
- **Depends on:** MP-005 (1 week of clean dual operation)
- **Description:** Delete `callback.verify_status_sync()` function (202 LOC). Delete `_subject_implements`, `_is_done_on_develop`, `_fetch_develop`, `_commit_stats`. Callback `main()` no longer calls any gate logic. Callback becomes pure dispatcher.
- **Files affected:**
  - `scripts/vps/callback.py` (delete ~400 LOC of gate code)
- **Acceptance criteria:**
  - `callback.py` LOC count < 600
  - All gate-related tests now run against gate-daemon, not callback
  - 1 week of operation with callback-as-dispatcher only
- **Compute cost:** ~$10
- **Wall-clock:** 1 week

### MP-007: Remove callback's lifecycle write path
- **Type:** ARCH
- **Priority:** P0
- **Risk:** R1
- **Depends on:** MP-006
- **Description:** Delete `callback._render_and_commit_backlog()`, `callback`'s lifecycle.write_lifecycle calls. Callback NO LONGER writes lifecycle. Backlog render moves to gate-daemon post-write hook (or render_backlog.py as cron).
- **Files affected:**
  - `scripts/vps/callback.py` (~150 more LOC removed)
  - `scripts/vps/render_backlog.py` (becomes cron-driven OR called by gate-daemon)
- **Acceptance criteria:**
  - Callback only writes: SQLite (release_slot, finish_task, record audit)
  - All lifecycle writes attributable to: gate-daemon, orchestrator (bootstrap), or spec_operator
- **Compute cost:** ~$10
- **Wall-clock:** 3-4 days

### Wave 3 Exit Criteria
- Callback < 200 LOC (target: 80-150)
- Gate-daemon is sole authority for status determination
- 0 lifecycle writes from callback in 1 week
- Parity test retired (no second source to compare against)

---

## Wave 4: Bootstrap Removal + Spark Integration

**Purpose:** Eliminate `bootstrap_new_specs` (Root 1 of today's incident). Spark writes lifecycle directly on spec creation.

### MP-008: Spark writes lifecycle.create_initial on spec creation
- **Type:** ARCH
- **Priority:** P0
- **Risk:** R1
- **Depends on:** Wave 3 (no more callback writes)
- **Description:** Update Spark facilitator agent (`.claude/agents/spark/facilitator.md` or wherever `lifecycle.create_initial` should be called) to write lifecycle yaml at end of spec creation. Update BOTH `template/.claude/skills/spark/` AND `.claude/skills/spark/` so changes propagate to managed projects via `/upgrade`. This must work from ANY of the 3 machines (founder runs Spark on laptops too).
- **Files affected:**
  - `template/.claude/skills/spark/completion.md` (instruction to write lifecycle)
  - `template/.claude/agents/spark/facilitator.md` (programmatic call to lifecycle.create_initial)
  - `.claude/skills/spark/*` (DLD-self)
  - `scripts/vps/lifecycle.py` (verify create_initial works from any cwd, given project_dir)
- **Acceptance criteria:**
  - New Spark spec → lifecycle yaml exists in `ai/lifecycle/SPEC-ID.yaml` immediately after Spark finishes
  - Test: invoke Spark from laptop (not VPS) → lifecycle yaml committed correctly
  - Test: invoke Spark from VPS → lifecycle yaml committed correctly
- **Compute cost:** ~$10
- **Wall-clock:** 3-4 days

### MP-009: Remove orchestrator.bootstrap_new_specs
- **Type:** ARCH
- **Priority:** P0
- **Risk:** R1
- **Depends on:** MP-008 (Spark writes lifecycle for 1 week minimum to prove all-projects cutover)
- **Description:** Delete `orchestrator.bootstrap_new_specs()` function entirely. Delete WT read of `backlog.md`. Orchestrator's `scan_queued` reads lifecycle yamls from HEAD via `git ls-tree HEAD ai/lifecycle/`.
- **Files affected:**
  - `scripts/vps/orchestrator.py` (delete bootstrap_new_specs ~50 LOC + WT-read logic)
- **Acceptance criteria:**
  - Orchestrator's main loop has zero references to `backlog.md`
  - Startup assertion: every spec in ai/features/*.md has corresponding ai/lifecycle/*.yaml; if not, log warning (NOT auto-create — Spark's responsibility)
  - Today's incident class (15 fake-done flips) is structurally impossible
- **Compute cost:** ~$5
- **Wall-clock:** 2-3 days

### Wave 4 Exit Criteria
- 0 calls to bootstrap_new_specs anywhere
- 0 reads of backlog.md by orchestrator
- All 3 machines successfully creating specs that write lifecycle
- 1 week zero-incident operation

---

## Wave 5: Decompose Callback (Final Slimming)

**Purpose:** Callback shrinks to its true scope. Extract dispatcher logic to dedicated module.

### MP-010: Extract dispatcher.py from callback
- **Type:** TECH
- **Priority:** P1
- **Risk:** R2
- **Depends on:** Wave 4
- **Description:** Extract `dispatch_qa`, `dispatch_reflect`, `write_event_for_skill` into `scripts/vps/dispatcher.py` (~150 LOC). Callback calls `dispatcher.dispatch_qa_reflect(project, spec_id)`.
- **Files affected:**
  - NEW: `scripts/vps/dispatcher.py`
  - `scripts/vps/callback.py` (remove dispatch functions)
- **Acceptance criteria:**
  - Callback's main() body is ≤30 LOC
  - dispatcher.py independently testable
- **Compute cost:** ~$5
- **Wall-clock:** 2-3 days

### MP-011: Extract common.py utilities
- **Type:** TECH
- **Priority:** P1
- **Risk:** R2
- **Depends on:** MP-010
- **Description:** Deduplicate `_load_env`, `_setup_logging`, `_pueue_add`, `_SPEC_ID_RE` (with GROWTH already added in Wave 0) into `scripts/vps/common.py`. Update 3 modules to import.
- **Files affected:**
  - NEW: `scripts/vps/common.py`
  - `scripts/vps/callback.py`, `orchestrator.py`, `claude-runner.py`, `gate-daemon.py`
- **Acceptance criteria:**
  - Zero duplicate function definitions across modules (grep + fitness function FF-09)
- **Compute cost:** ~$5
- **Wall-clock:** 2 days

### MP-012: Extract circuit.py (simplified)
- **Type:** TECH
- **Priority:** P1
- **Risk:** R2
- **Depends on:** MP-011
- **Description:** Extract circuit-breaker into `scripts/vps/circuit.py` (~80 LOC). Simplification: remove pueue-pause behavior (Bruce's concern: circuit can lock entire system). Circuit becomes alert-only: trips after 3 demotes/10min, sends Hermes event, but does NOT pause pueue. Operator can manually pause if needed. Reduces risk of self-DoS.
- **Files affected:**
  - NEW: `scripts/vps/circuit.py`
  - `scripts/vps/callback.py` (remove circuit code), `gate-daemon.py` (call circuit.record + check)
- **Acceptance criteria:**
  - Pueue group cannot be paused by circuit alone (audit trail check)
  - Hermes event fires on trip
  - `vps-orch circuit-status` exposes state
- **Compute cost:** ~$5
- **Wall-clock:** 2 days

### Wave 5 Exit Criteria
- callback.py < 100 LOC
- gate-daemon.py < 200 LOC
- common.py, dispatcher.py, circuit.py each < 150 LOC
- Zero function duplications across modules

---

## Wave 6: CI, Observability, Deployment (Permanent Defense)

**Purpose:** Lock in the architecture via fitness functions. Surface failures via metrics. Deploy hooks to managed projects.

### MP-013: Fitness function suite FF-01..FF-08
- **Type:** TECH
- **Priority:** P0
- **Risk:** R2
- **Depends on:** Wave 5
- **Description:** Implement 8 fitness functions as CI tests + pre-commit hooks. From Neal's research:
  - FF-01: LOC per file ≤400 (tests: 600)
  - FF-02: No zombie validators (e.g., spec_lint.py-class files validating removed formats)
  - FF-03: Sole writer per data store (gate-daemon for status, callback for slots, etc.)
  - FF-04: All tests/ in CI testpaths (already done in Wave 0)
  - FF-05: Module responsibility count ≤5 (heuristic: top-level functions grouped by domain)
  - FF-06: Regression test per incident (CHANGELOG entry must reference test file path)
  - FF-07: _subject_implements/git log --grep accepts both conventions (golden dataset test)
  - FF-08: _SPEC_ID_RE consistent across modules (extract-to-common check)
  - FF-09 (NEW): Zero callback↔gate-daemon imports (the temporal decoupling fitness)
- **Files affected:**
  - NEW: `tests/fitness/test_ff_*.py` (8-9 files)
  - `pyproject.toml` (add fitness/ to testpaths)
  - `.github/workflows/test.yml` (require fitness pass)
- **Acceptance criteria:**
  - All 9 FFs pass on develop
  - PR that violates any FF fails CI
- **Compute cost:** ~$15
- **Wall-clock:** 1 week

### MP-014: vps-orch CLI for agent ergonomics
- **Type:** FTR
- **Priority:** P1
- **Risk:** R2
- **Depends on:** Wave 5 (modules stable)
- **Description:** Erik's agent API contract layer. Single CLI `vps-orch` with subcommands returning JSON:
  - `vps-orch status SPEC-ID` → {spec_id, status, blocked_reason, ...}
  - `vps-orch health` → {circuit, slots, queue_depth, gate_last_poll_at}
  - `vps-orch gate-check SPEC-ID` → {verdict, evidence: [...commits], gate_reason}  ← DRY-RUN
  - `vps-orch audit SPEC-ID --since 7d` → [audit entries]
  - `vps-orch gate-history SPEC-ID` → [shadow + real decisions over time]
  - `vps-orch circuit-status` → {state, demotes_last_10min, ...}
  - `vps-orch dispatch SPEC-ID` → manually dispatch a spec (operator-only)
- **Files affected:**
  - NEW: `scripts/vps/vps_orch.py` (~200 LOC)
  - `~/.local/bin/vps-orch` (entry point script)
- **Acceptance criteria:**
  - All 7 subcommands return valid JSON
  - `--json` flag default ON (agent-friendly)
  - Coder agents demonstrably use this in autopilot runs (audit via diary entries)
- **Compute cost:** ~$10
- **Wall-clock:** 4-5 days

### MP-015: pre-commit framework migration
- **Type:** TECH
- **Priority:** P1
- **Risk:** R2
- **Depends on:** Wave 6 (no longer need hand-rolled hooks for active development)
- **Description:** Replace hand-rolled `.git-hooks/pre-commit` with `pre-commit` framework (Python). Hooks: lifecycle-write-guard, fitness function checks, LOC limit, no-zombie-import. Provides standard install: `pre-commit install`.
- **Files affected:**
  - NEW: `.pre-commit-config.yaml`
  - DELETE: `.git-hooks/pre-commit`
  - DELETE: `scripts/hooks/pre-commit`
  - `.claude/hooks/pre-commit-lifecycle-guard.mjs` → migrate to Python hook in pre-commit framework
- **Acceptance criteria:**
  - `pre-commit install` works clean-clone in DLD
  - All previous hook logic preserved
  - `core.hooksPath` set correctly during install
- **Compute cost:** ~$8
- **Wall-clock:** 3-4 days

### MP-016: register-project.sh for managed-project deployment
- **Type:** TECH
- **Priority:** P0
- **Risk:** R1
- **Depends on:** MP-015
- **Description:** Single-command provisioner for managed projects: `scripts/vps/register-project.sh <project_path>`. Installs `.pre-commit-config.yaml` from DLD template, runs `pre-commit install`, sets `core.hooksPath`, validates with smoke test. Run for all 10 managed projects.
- **Files affected:**
  - NEW: `scripts/vps/register-project.sh`
  - Manual: run for awardybot, wb, dowry, nexus, plpilot, gipotenuza, memyselfandi, mishkinlyap, dowry-mc
- **Acceptance criteria:**
  - All 10 managed projects have working pre-commit (verified by attempting bad commit → blocked)
  - DLD-self has same hooks (eat your own dogfood)
- **Compute cost:** ~$5 (script) + manual deployment
- **Wall-clock:** 2-3 days

### MP-017: Counter-file metrics + simple alerter
- **Type:** TECH
- **Priority:** P1
- **Risk:** R2
- **Depends on:** Wave 6
- **Description:** Charity's minimal-viable observability (NOT Prometheus). Counter files in `scripts/vps/metrics/*.txt` (one int per file). `simple_alerts.py` cron reads + fires Hermes events on thresholds. Specific alerts:
  - ALERT-001: bootstrap-mass-done (`bootstrap_done_total` delta >3 in 5min) — would have caught today's incident
  - ALERT-002: lifecycle_push_failures >0 per 24h (validates multi-machine convergence health)
  - ALERT-003: gate_demote_rate >5 per hour (early sign of convention drift)
  - ALERT-004: orchestrator heartbeat stale >10min
  - ALERT-005: gate-daemon last_poll_at stale >5min
  - ALERT-006: circuit-breaker open (informational)
- **Files affected:**
  - NEW: `scripts/vps/simple_alerts.py` (~80 LOC)
  - Cron entry every 1 minute
- **Acceptance criteria:**
  - All 6 alerts firing test successfully in isolated tests
  - Hermes events delivered to Telegram
- **Compute cost:** ~$8
- **Wall-clock:** 3 days

### Wave 6 Exit Criteria
- 9 fitness functions in CI, all passing
- vps-orch CLI used by ≥2 agents in production
- pre-commit framework installed in DLD + all 10 managed projects
- All 6 alerts wired and tested
- Wave 6 is the **permanent defense layer** — locks in the architecture

---

## Exit Criterion (Migration Complete)

All Wave 0-6 items merged. AS-IS converged with TO-BE:

- `callback.py` ≤ 100 LOC, single responsibility (pueue dispatcher)
- `gate-daemon.py` ≤ 200 LOC, single responsibility (status determination)
- `bootstrap_new_specs` deleted
- `_subject_implements` 202-LOC regex replaced by 5-LOC `git log --grep`
- `lifecycle.py` simplified (no `_atomic_write_file` dup, no CAS plumbing — but unchanged storage layer; this is C, not B)
- Multi-machine git sync confirmed working (push failures alerted via ALERT-002)
- 9 fitness functions defend against fix-train resumption
- vps-orch CLI is the canonical agent interface
- pre-commit deployed via framework to 10 managed projects
- Telegram token rotated, in Nexus, not in git

**Then:** normal flow (Spark → autopilot) resumes WITHIN the new architecture. Any new incident in this contour requires:
1. Regression test added (FF-06)
2. If fix requires a new principle → re-open architecture decision (don't accrete in callback/gate-daemon/lifecycle)

---

## Risk Summary (Per Wave)

| Wave | Highest Risk | Mitigation |
|---|---|---|
| 0 (P0) | Token rotation in flight while git history still has it | `git filter-repo` immediately; rotate before push |
| 1 (Gate daemon shadow) | Daemon dies between cycles silently | systemd WatchdogSec=120 + ALERT-005 |
| 2 (Parity verify) | Divergences indicate either is wrong | Daily report; founder reviews before cutover |
| 3 (Cutover) | Authority transfer leaves period with two writers | MP-005→MP-006→MP-007 are sequenced; 1-week observation between each |
| 4 (Bootstrap removal) | Spark on laptop doesn't write lifecycle correctly | MP-008 tests cross-machine; MP-009 has startup warning if drift |
| 5 (Decomposition) | New file count adds maintenance | FF-01 LOC limits; circuit simplification removes self-DoS risk |
| 6 (CI + ops + deploy) | Fitness functions fail in CI for legacy code | Each FF has bypass label `[FF-skip]` for explicit one-time exemption (audited) |

---

## Cost Summary

| Wave | Compute | Wall-clock |
|---|---|---|
| 0 (P0) | ~$15 | 2-3 days |
| 1 (Gate daemon shadow) | ~$18 | 1 week |
| 2 (Parity verify) | ~$10 | 1 week |
| 3 (Cutover, 3 steps) | ~$25 | 2 weeks |
| 4 (Bootstrap removal) | ~$15 | 1 week |
| 5 (Decompose callback) | ~$15 | 1 week |
| 6 (CI/ops/deploy) | ~$46 | 2 weeks |
| **Total** | **~$144** | **~6-8 weeks** |

(Estimate from architectures.md was $150 / 5-6 weeks; this detailed breakdown adds the parity verification week realistically.)

---

## What Stays Out of This Migration

- Managed-project business logic (awardybot/wb/dowry domain code) — not in scope
- claude_agent_sdk integration — keep as is
- pueue daemon configuration — keep as is
- Hermes/openclaw event mechanism — keep as is
- SQLite schema for compute_slots, task_log, callback_decisions, sdk_post_result_errors — keep, fix indexes as part of P0 if not done in Wave 0

---

## Conway's Law Note (Neal)

This migration creates **one new artifact**: `gate-daemon.py` as a separate process. The conway's-law side-effect: status-determination decisions are now **physically separable from event-handling**. In practice this means:
- If gate logic has a bug, it lives in one place. Cannot be "smuggled" into callback by mistake (FF-09 enforces).
- The next operator who joins (or the next Claude SDK agent that touches this code) sees TWO orthogonal concerns, not ONE god module. Cognitive load drops.

This is the structural mitigation against the fix-train pattern. Other waves (zombie cleanup, decomposition) reduce existing debt. This is the ONE wave that creates the structural separation that prevents future debt.

---

## References

- Audit: `ai/audit/deep-audit-report.md`
- Architect synthesis: `ai/architect/architectures.md`
- Persona research: `ai/architect/research-*.md` (8 files)
- Cross-critiques: `ai/architect/critique-*.md` (8 files)
- Agenda: `ai/architect/architecture-agenda.md`
- ADR chain: `.claude/rules/architecture.md` (ADR-018 → 023 → 024, and forthcoming ADR-025 for Alt C decoupling)
- Founder confirmation: multi-machine convergence operational (3 dev machines, VPS sole orchestrator)
