# Architecture Alternatives — callback / lifecycle / orchestrator Retrofit

**Synthesizer:** Oracle (Chairman)
**Date:** 2026-05-23
**Mode:** Retrofit (brownfield)
**Inputs:** Deep audit (85 findings, 6 personas) + 8 persona research reports + 8 cross-critiques + facilitator agenda
**Status:** 3 distinct alternatives + P0 set + Devil's questions surfaced. Human picks.

---

## Executive Summary

Eight independent personas converged on the same five symptoms — `callback.py` is a 1374-LOC god module with 7 responsibilities, `bootstrap_new_specs` reads `backlog.md` from a dirty working tree (root cause of today's 15 fake-done flips), `scripts/vps/tests/` is excluded from CI, `_push_best_effort` swallows multi-machine convergence failures at DEBUG level, and `_subject_implements` rejects 72% of awardybot's commit subjects. Five P0 fixes are agreed on regardless of architectural choice.

The architectural divergence is real and exclusive: it is the **central conflict** below. Three alternatives flow from how the conflict is resolved. **No alternative is a "best of both worlds" hybrid.** Each is internally coherent. Each has honest trade-offs. Human must choose based on five questions Devil raised that founder must answer first.

### Convergence — what all 8 personas agree on

| # | Finding | Evidence | All 8 agree? |
|---|---|---|---|
| 1 | `callback.py` (1374 LOC, 7 responsibilities) must be decomposed | callback.py file structure; deep audit Finding 1; every research+critique cites it | YES — even E (pragmatist) and G (devil) |
| 2 | `bootstrap_new_specs` reading WT `backlog.md` is the structural root of today's incident | orchestrator.py:295; deep audit Root 1 | YES |
| 3 | `pyproject.toml: testpaths = ["tests"]` is the cheapest highest-ROI fix | pyproject.toml:19; deep audit Finding 8 | YES — 1 line, 100 tests in CI |
| 4 | `_push_best_effort` at DEBUG is a silent production safety defect | lifecycle.py:266; deep audit Coroner #3 | YES |
| 5 | `_subject_implements` rejects 460/636 awardybot commits (Root 3) | callback.py:699-711; deep audit Cartographer #11 | YES |
| 6 | `spec_lint.py` is a zombie validator after ARCH-186 deleted DLD-CALLBACK-MARKER | spec_lint.py:25-26; deep audit Finding 22 | YES (B, D, E, G explicit; rest by implication) |
| 7 | `lifecycle._run()` has no timeout on 8 git plumbing calls (DoS under `_write_lock`) | lifecycle.py:77-88; deep audit Finding 12 | YES (A, D, H explicit) |
| 8 | TELEGRAM_BOT_TOKEN committed plaintext to `scripts/vps/.env` is a P0 credential exposure | architecture-agenda.md:69; deep audit Scout #7 | YES (D, H explicit; independent of architecture) |
| 9 | `pre-commit-lifecycle-guard.mjs` is dead in every repo (`core.hooksPath` mismatch) | deep audit Finding 4; Scout audit | YES — identity enforcement from ADR-024 is "decorative" (G's word) |
| 10 | The "fix train" pattern (5 incident-driven fixes/month on one file) is the mechanism of decay | git log; B's check_fix_train.py | YES — B's framing, all others agree on the symptom |

### The Central Conflict — Evaporating Cloud (per Devil)

```
              [A: Goal — stop the fix train, restore conceptual integrity]
                                        |
                ┌───────────────────────┴────────────────────────┐
                │                                                │
         [B: Need — preserve                          [C: Need — eliminate
          ARCH-186's design intent                    the bug class generated
          (lifecycle audit trail in                   by git-as-DB CAS plumbing]
          git, multi-machine sync)]                           │
                │                                             │
                │                                             │
         [D: Want — KEEP git-per-spec YAML                [E: Want — REVOKE
          as SoT; patch the                               git-as-DB; migrate
          implementation bugs                             lifecycle to SQLite]
          (WT-sync race, push-DEBUG)]
                │                                             │
                └────────────conflict────────────────────────┘
```

**Hidden assumption to challenge:** That multi-machine convergence is an operational requirement TODAY. ARCH-186 was justified by "multiple machines can sync via git push" as a design goal. If that is theoretical, E's position wins (revoke the token). If it is operational (e.g., laptop + VPS, or future multi-VPS), D's position wins (patch the implementation).

**Cloud evaporates when:** Founder answers one binary question — "is multi-machine git sync currently operational, or aspirational?"

### The Devil's 5 Questions — Founder Must Answer Before Synthesis Can Resolve

These are not rhetorical. The answers determine which alternative below is correct.

1. **Is multi-machine convergence a current operational requirement, or theoretical?**
   - If operational: ADR-023 git-as-DB design holds. Choose **Alternative A**.
   - If theoretical: ARCH-186 was overengineering. Choose **Alternative B**.
   - If undecided: start with **P0 + Wave 1 of Alternative A**, defer the storage decision until evidence accumulates.

2. **Who is solely responsible for architectural integrity of `scripts/vps/`?**
   - If "no one — whoever fixes the next incident": the fix train will resume regardless of choice. Pick the alternative that requires fewest follow-up decisions (Alternative A wave 1-2 + automated fitness functions).
   - If a named owner (you, founder): any alternative becomes viable because principles can be defended.

3. **Does anyone actually use `spec_operator.py` in a real workflow today?**
   - The QA logs (`ai/qa/2026-05-15-tech-973-hermes-intake.md:48`, `ai/qa/2026-05-16-arch-186.md:123`) reference it. Was that real usage or one-time post-incident cleanup?
   - If unused: remove (E, G, all alternatives agree on removal).
   - If used: each alternative below specifies replacement.

4. **What is the acceptable downtime for migrating 190+ lifecycle YAMLs to SQLite (if Alternative B)?**
   - If zero (orchestrator runs continuously): need expand-contract migration with dual-write window (Martin's critique-data.md proposal).
   - If a few hours (planned maintenance): one-shot migration script is acceptable.

5. **Are the commit conventions across managed projects (DLD canonical scope vs awardybot trailer) a DLD standard that managed projects must adopt, or are managed projects sovereign?**
   - If DLD-standard: educate managed projects, gate accepts only canonical. Operational cost: project-by-project migration.
   - If managed-project sovereign: gate must accept BOTH conventions. Code cost: extend `_subject_implements` regex OR replace with `git log --grep` (1-rule gate).

---

## Alternative A — "Patch & Harden" (Conservative)

**Philosophy:** ARCH-186 was directionally correct. The CAS git-as-DB concept is sound. Bugs are implementation bugs, not design bugs. Decompose callback.py, fix the WT-sync race, add fitness functions and observability, deploy hooks to managed projects via Strangler Fig.

**Best for:**
- Founder believes multi-machine convergence is real or imminent (laptop ↔ VPS sync, future multi-VPS).
- Founder values "no big-bang migration of 190+ YAMLs" risk avoidance.
- Founder accepts that conceptual integrity comes from automated CI fitness functions, not unifying redesign.
- "I trust ARCH-186's Council decision; we executed it badly, not chose wrong."

---

### 1. Module Decomposition Target

`callback.py` (1374 LOC, 7 responsibilities) → 5 modules + shared utility:

```
scripts/vps/
├── common.py            ~120 LOC  NEW
│   Responsibility: shared utilities (deduplicated from 3 modules)
│   Exports: SPEC_ID_PATTERN (frozenset of TECH/FTR/BUG/ARCH/GROWTH),
│            _load_env, _setup_logging, _pueue_add, AuditPayload dataclass
│
├── callback.py          ~250 LOC  (was 1374)
│   Responsibility: pueue completion handler — process boundary that always exit 0
│   Calls: resolve_label, dispatch_qa, dispatch_reflect, gate.evaluate, lifecycle_writer.update
│   No git logic, no parser internals — pure orchestration of the other modules
│
├── gate.py              ~200 LOC  NEW (extracted from verify_status_sync)
│   Responsibility: ONE — given (project_path, spec_id, allowed_files), return GateResult
│   Pure function. No writes. No side effects. Testable with real git repos.
│   Exports: evaluate(project, spec_id) -> GateResult; GateReason enum
│
├── circuit.py           ~80 LOC   NEW (extracted from callback)
│   Responsibility: circuit breaker state + decisions (TECH-169)
│   Exports: is_open(), trip(), reset(), record_decision()
│
├── audit.py             ~100 LOC  NEW (extracted from callback)
│   Responsibility: structured audit JSONL writer + reader
│   Exports: write(payload: AuditPayload), recent(since_ts) -> list[AuditEntry]
│
├── lifecycle.py         ~400 LOC  (was 602)
│   Responsibility: SoT writer + reader. Single change: simpler atomic write.
│   Replace `_atomic_write` (private GIT_INDEX_FILE + 8-step CAS) with:
│     write_text → git add → git commit → git push (with timeout=30 each)
│   Lose: zero-WT-touch property (slight). Gain: 200 LOC removed, race eliminated.
│   Add: VALID_TRANSITIONS guard (F's proposal — make queued→done structurally invalid)
│   Add: dispatched_at field (replaces always-null started_at)
│   Remove: allowed_files_hash (dead field, 190+ nulls)
│
├── orchestrator.py      ~400 LOC  (was 667)
│   Remove: bootstrap_new_specs entirely (Spark writes lifecycle.create_initial at spec creation)
│   Remove: WT read of backlog.md
│   Keep: slot management, scan_queued, hot-reload, Hermes intake, night reviewer dispatch
│
├── db.py                ~550 LOC  (was 531)
│   Add: PRAGMA user_version + schema_migrations table (F's proposal)
│   Add: indices on hot queries (task_log.pueue_id, night_findings.(project_id,status))
│   Add: purge_old_records (90-day retention on task_log, callback_decisions, sdk_errors)
│   Fix: cost_usd REAL → cost_millicents INTEGER (ADR-001 compliance)
│
├── render_backlog.py    ~200 LOC  (was ~150)
│   Add: sentinel-based differential render (preserves founder's narrative)
│   Re-enable auto-render after every lifecycle write (replaces NOTE-disabled block at lifecycle.py:208)
│
└── spec_operator.py     ~50 LOC   (was 166)
    Slim wrapper over lifecycle.write_lifecycle with TTY check + audit log
    Remove cross-import of callback._reset_circuit_cli; expose circuit.reset() as public API
```

**Net LOC delta:** ~3144 → ~2350 (about **-800 LOC**), 1 god module → 8 single-purpose modules.

---

### 2. What Dies (Zombies)

| What | Where | Why |
|---|---|---|
| `spec_lint.py` | scripts/vps/spec_lint.py | Validates removed DLD-CALLBACK-MARKER (ARCH-186) — inverted fitness function |
| `DLD-CALLBACK-MARKER` references | template/.claude/skills/spark/completion.md:46 | Blocks every new Spark spec against dead format |
| `DLD-CALLBACK-MARKER` regex check | .claude/agents/spark/facilitator.md:218-221 | Dead enforcer in agent prompt |
| `bootstrap_new_specs` | orchestrator.py:280-333 | Root 1 of today's incident; replaced by Spark writing lifecycle.create_initial |
| `migrate_backlog_to_lifecycle.py` | scripts/vps/migrate_backlog_to_lifecycle.py | One-shot migration already ran; keeping it is liability (CAS bypass via Path.write_text) |
| `_atomic_write_file` duplicate | lifecycle.py:469 | DRY violation with `_atomic_write` — same stale-index bug in both |
| `allowed_files_hash` field | lifecycle YAML schema | Always null in 190+ files; no writers; dead |
| DLD-CALLBACK-MARKER blocks in 23 spec files | ai/features/*.md | Fossils from pre-ARCH-186; can be batch-removed via sed |
| `.worktrees/ARCH-186`, `.worktrees/ARCH-187` | stale worktrees | Completed specs |

**Total net removal:** ~6 files deleted, ~200 LOC of zombie validation removed, ~23 spec files cleaned.

---

### 3. What's Added

| What | Where | Purpose |
|---|---|---|
| Common module | scripts/vps/common.py | Deduplicates _load_env, _setup_logging, _pueue_add, SPEC_ID_PATTERN |
| gate.py | scripts/vps/gate.py | Single-responsibility gate (extracted from verify_status_sync 202 LOC) |
| circuit.py | scripts/vps/circuit.py | Circuit breaker as separate concern |
| audit.py | scripts/vps/audit.py | Structured audit log with typed AuditPayload (replaces 12-arg _emit_audit) |
| `vps-orch` CLI | scripts/vps/vps_orch.py (NEW) | Agent-friendly JSON-output CLI: `status`, `health`, `gate-check`, `audit`, `dispatch` (Erik's missing API contract layer) |
| GateResult dataclass + GateReason enum | gate.py | Replaces None-return + side-effects pattern |
| VALID_TRANSITIONS state machine guard | lifecycle.py | Rejects `queued → done` shortcut (Martin's proposal) |
| `dispatched_at` field | lifecycle YAML | Replaces always-null started_at |
| Sentinel-based differential renderer | render_backlog.py | Preserves founder's narrative; re-enables auto-render |
| Pre-commit framework setup | `.pre-commit-config.yaml` | Replaces hand-rolled `.git-hooks/` (Dan's boring choice) |
| `register-project.sh` | scripts/vps/register-project.sh | Deploys hooks to managed projects (closes Layer 3 gap) |
| Fitness function suite (FF-01..FF-08) | tests/unit/, scripts/vps/tests/ | Executable architectural invariants (Neal's proposal) |
| Heartbeat file + monitor | scripts/vps/.orchestrator-heartbeat | ALERT-004 hang detection (Charity) |
| Counter-file metrics + cron alerter | scripts/vps/metrics/, scripts/vps/simple_alerts.py | ALERT-001..006 (Charity Tier 1 only) |
| Bootstrap audit JSONL | scripts/vps/bootstrap-audit.jsonl | Forensic data for create_initial calls |
| `_validate_transition` invariant | lifecycle.py | Enforce state machine at write time |
| AGENT_REFERENCE.md | scripts/vps/AGENT_REFERENCE.md | ~1000-token compressed reference (Erik) |

---

### 4. What's NOT Addressed (Honest Limits)

- **Conceptual integrity from one mind:** Decomposition alone does not create a unifying principle. If founder remains unwilling to name a sole architectural owner, the fix train can resume in `gate.py` or `lifecycle.py` instead of `callback.py`. Fitness functions raise the cost of new accretion but do not eliminate it.
- **Multi-repo topology:** SQLite tables would still be DLD-owned. Lifecycle YAMLs live in each managed project's git history; this remains true under A. The multi-machine convergence question (Devil Q1) is **answered "yes, it works as designed"** under Alternative A — without an explicit test that proves convergence happens correctly today.
- **`_subject_implements` improved but still inferring:** A keeps the regex-based gate and extends it to both canonical and trailer conventions (golden dataset + FF-07). It does NOT replace the inference with `git log --grep` (which is Alternative B's move). If a third convention appears in a future managed project, regex extension is required again.
- **CAS implementation simplified, not eliminated:** A replaces the private GIT_INDEX_FILE plumbing with `git add + git commit`, accepting a brief WT touch. This is faster and simpler but loses ARCH-186's "never touches WT" invariant. The WT-sync race is eliminated by removing WT-sync entirely (no `checkout-index` after commit).
- **Agent-as-threat-actor (Bruce's addition):** Alternative A does not move `scripts/vps/` to a filesystem path isolated from agent sandboxes. If an autopilot agent in `awardybot` writes to `/home/dld/projects/dld/scripts/vps/callback.py`, no control prevents this.

---

### 5. Migration Cost (LLM-Native)

**Total: ~$55-65 compute, 3-4 weeks wall-clock (parallel autopilot)**

| Wave | Items | Cost | Wall-clock |
|---|---|---|---|
| Wave 0 (P0, do regardless) | testpaths fix, conftest autouse, GROWTH regex, identity fixes, zombie cleanup, TELEGRAM rotation, push-WARNING, heartbeat | ~$10 | 2-3 days |
| Wave 1 (decomposition) | Extract gate.py/circuit.py/audit.py/common.py from callback; kill bootstrap_new_specs; Spark writes lifecycle.create_initial | ~$20 | 1 week |
| Wave 2 (lifecycle hardening) | Simplify _atomic_write (remove private GIT_INDEX_FILE); add VALID_TRANSITIONS; add dispatched_at; remove allowed_files_hash; fix render_backlog sentinels | ~$15 | 1 week |
| Wave 3 (CI + ops) | pyproject.toml extension; FF-01..FF-08 fitness functions; vps-orch CLI; counter-file metrics + alerts | ~$15 | 1 week |
| Wave 4 (deployment) | pre-commit framework setup; register-project.sh; deploy hooks to 10 managed projects | ~$5 | 2-3 days |

**Each wave is independently shippable and reversible.** Each is one Spark spec → autopilot execution.

---

### 6. Risk Per Devil/Security

| Risk | Likelihood | Impact | Mitigation in Alt A |
|---|---|---|---|
| **Fix train resumes inside gate.py** (G's prediction) | MEDIUM | HIGH | FF-01 (LOC limit per file) + FF-05 (responsibility count); pre-commit hook enforces both |
| **WT touch in simplified _atomic_write causes new race** | LOW | MEDIUM | `git add` is local + atomic; `_write_lock` still serializes; no `checkout-index` step |
| **Spark fails to write lifecycle.create_initial in 1 of 10 projects** | MEDIUM | HIGH | Cutover requires Spark skill update first; orchestrator startup check (`assert all queued specs have lifecycle YAML`) catches drift |
| **Pre-commit hook still not enforced for adversarial agents** | HIGH | MEDIUM | Bruce's note: agents can write directly to `ai/lifecycle/*.yaml` bypassing git commit. Mitigation: process-token in systemd env required by `lifecycle.write_lifecycle()` (H's Layer 1) |
| **Multi-machine convergence remains theoretical, never tested** | UNKNOWN | UNKNOWN | Add `lifecycle_push_failures_total` counter (M-03); ALERT-002 fires on any failure |
| **190+ lifecycle YAMLs not migrated to new schema (`dispatched_at`, no `allowed_files_hash`)** | LOW | LOW | Field rename is forward-compatible; old yamls have null `dispatched_at`, code tolerates |

---

### 7. When This Is the Right Choice

- Multi-machine git sync is operational (or imminently planned) — ADR-023 rationale still holds.
- Founder accepts incremental risk avoidance over clean redesign.
- "I want today's bugs fixed and next month's prevented; I don't want to bet on a 4-week rewrite."
- The cryptographic audit trail of `git log -- ai/lifecycle/` is operationally valuable (e.g., post-incident forensics).

---

## Alternative B — "SQLite Reset" (Pragmatic Rewrite)

**Philosophy:** ARCH-186 was the inflection point of the fix train. Git-as-DB is the innovation token whose cost (WT-sync race, 8 subprocess calls without timeout, push-at-DEBUG, CAS retry exhaustion) exceeded its benefit (theoretical multi-machine convergence). Revoke the token. SQLite is the boring choice that was always available. Lifecycle YAML continues as a read-only git artifact for audit trail; SoR moves to SQLite.

**Best for:**
- Founder believes multi-machine convergence is aspirational, not operational.
- Founder values "fewer moving parts" over "preserve existing architecture decisions."
- Founder accepts 4-6 hours of orchestrator downtime for migration (or expand-contract dual-write).
- "I should not have to know about private GIT_INDEX_FILE semantics to debug a status bug."

---

### 1. Module Decomposition Target

`callback.py` (1374 LOC) + `lifecycle.py` (602 LOC) → 5 modules with SQLite as SoR:

```
scripts/vps/
├── common.py            ~120 LOC  NEW (same as Alt A)
│   Responsibility: shared utilities, SPEC_ID_PATTERN, dataclasses
│
├── callback.py          ~200 LOC  (was 1374)
│   Responsibility: pueue completion handler → release slot, dispatch QA/reflect, exit
│   Calls: gate.evaluate, db.update_spec_status
│   No git plumbing. No YAML. No CAS retry loops.
│
├── gate.py              ~150 LOC  NEW
│   Responsibility: single-rule gate — `git log origin/develop --grep SPEC-ID`
│   Returns GateResult with structured reason
│   No regex on commit subjects. The git log search is the gate.
│
├── db.py                ~700 LOC  (was 531; +spec_lifecycle, +spec_transitions, +migrations)
│   New tables:
│     spec_lifecycle: spec_id PK, status, priority, kind, blocked_reason, blocked_code,
│                     dispatched_at, finished_at, updated_at, updated_by, version, pueue_id, project_id
│     spec_transitions: id PK, spec_id FK, from_status, to_status, at, by, pueue_id
│     schema_migrations: version PK, applied_at, description
│   New functions:
│     get_spec_status(spec_id), set_spec_status(spec_id, status, by, reason),
│     list_specs_by_status(status_set), insert_transition(spec_id, ...)
│   PRAGMA user_version + ordered migration list (E's proposal)
│
├── orchestrator.py      ~400 LOC  (was 667)
│   Remove: bootstrap_new_specs entirely
│   Remove: WT read of backlog.md
│   Change: scan_queued reads `SELECT spec_id FROM spec_lifecycle WHERE status='queued'`
│   Keep: slot management, hot-reload, Hermes intake
│
├── render_backlog.py    ~200 LOC  (was ~150)
│   Read source: SQLite (was: lifecycle YAML files)
│   Output: backlog.md (sentinel-based differential, preserves narrative)
│
├── lifecycle_archive.py ~80 LOC   NEW
│   Responsibility: write lifecycle YAML to git on every spec_lifecycle UPDATE (read-only audit)
│   Async, best-effort, non-blocking, logged at WARNING on failure
│   Purpose: preserve git history of status changes for forensics; not used as SoR
│
└── spec_operator.py     ~50 LOC   (was 166)
    Slim wrapper: argparse → db.set_spec_status with audit + TTY check
```

**Net LOC delta:** ~3144 → ~1900 (about **-1200 LOC**) — largest reduction across alternatives.

**lifecycle.py is GONE.** Its 602 LOC of CAS plumbing is replaced by ~30 LOC of SQLite calls in db.py.

---

### 2. SoR Migration Plan (YAML → SQLite)

**Strategy: Expand-Contract (Martin's recommendation in critique-data.md)**

| Phase | Step | Risk |
|---|---|---|
| **Expand** | Add spec_lifecycle table; migrate 190 YAMLs → SQLite rows (one-shot script with idempotent sentinel); START dual-write (every write_lifecycle call → both YAML AND SQLite) | LOW: additive, no readers switched |
| **Verify** | Run for 48-72 hours; FF: SQLite row count == YAML file count for every project; reconciliation cron daily | LOW: read-only verification |
| **Switch reads** | scan_queued, render_backlog, callback gate all read from SQLite; YAML reads removed | MEDIUM: any code path that reads YAML must be updated atomically |
| **Contract** | Stop writing YAML (callback writes only SQLite); lifecycle_archive.py becomes async-only (writes git for audit, never blocks) | LOW: writes are additive, can be reverted |
| **Cleanup** | After 1 week of SQLite-only operation: delete lifecycle.py (602 LOC), delete CAS code, archive YAML directory to ai/lifecycle.archive/ | NONE — pure deletion |

**Total migration:** ~10-14 days wall-clock with daily verification windows.

**Downtime:** Zero (if dual-write is implemented correctly). 4-6 hours (if one-shot cutover).

---

### 3. What Dies (Zombies + Architecture)

Beyond Alt A's zombie list:

| What | Where | Why Dies in B |
|---|---|---|
| `lifecycle.py` entire module | scripts/vps/lifecycle.py (602 LOC) | Replaced by db.py functions + SQLite transactions |
| `_atomic_write`, `_atomic_write_file` | lifecycle.py | CAS git plumbing — no longer needed |
| Private GIT_INDEX_FILE dance | lifecycle.py:171-260 | SQLite WAL transactions replace |
| `_ALLOWED_WRITERS` frozenset | lifecycle.py:49-51 | Honor-system theater — process-token in systemd replaces |
| `LifecycleWriteRaceError` | lifecycle.py | SQLite serializable transactions eliminate the race class |
| `_write_lock` (threading.Lock) | lifecycle.py | SQLite BEGIN IMMEDIATE provides serialization |
| `_push_best_effort` | lifecycle.py:263-266 | No git push for lifecycle SoR; archive push is separate async path |
| `migrate_backlog_to_lifecycle.py` | scripts/vps/migrate_backlog_to_lifecycle.py | Migration target gone |
| `assert_clean_lifecycle_tree` | orchestrator.py:363 | No more lifecycle WT to be dirty |
| `reconcile_orphans` (lifecycle-yaml path) | orchestrator.py:364 | Replaced by `UPDATE spec_lifecycle SET status='queued' WHERE status='in_progress' AND pueue_id NOT IN (SELECT pueue_id FROM live_tasks)` |
| `_subject_implements` regex (3+ formats) | callback.py:699-711 | Replaced by `git log --grep` (Dan's proposal) |
| 8-rule gate logic in verify_status_sync | callback.py:1001-1200 | Replaced by 5-line gate function in gate.py |
| `bootstrap_new_specs` | orchestrator.py | Replaced by Spark writing `db.create_spec(...)` directly |

**Net architectural removal:** lifecycle.py (602) + bootstrap (50) + 8-rule gate (202) + CAS plumbing (~200 across files) = **~1050 LOC permanently deleted**, on top of Alt A's zombie cleanup.

---

### 4. What's Added

| What | Where | Purpose |
|---|---|---|
| `spec_lifecycle` table | db.py schema.sql | SoR for spec status |
| `spec_transitions` table | db.py schema.sql | Audit trail (replaces YAML transitions array) |
| `schema_migrations` table | db.py schema.sql | PRAGMA user_version tracking |
| `lifecycle_archive.py` | scripts/vps/lifecycle_archive.py | Async best-effort YAML export to git for audit (~80 LOC) |
| 1-rule gate (`git log --grep`) | gate.py | Replaces 202-LOC verify_status_sync |
| GateResult + GateReason | gate.py + common.py | Typed return value (Erik's proposal) |
| VALID_TRANSITIONS guard | db.set_spec_status() | Enforced at write time |
| `vps-orch` CLI | scripts/vps/vps_orch.py | Agent-friendly JSON output (same as Alt A) |
| Process token in systemd | dld-orchestrator.service + db.set_spec_status() | ORCHESTRATOR_PROCESS_TOKEN required for writes (Bruce's Layer 1) |
| `register-project.sh` | scripts/vps/register-project.sh | Deploys hooks (same as Alt A) |
| Fitness functions FF-01..FF-08 | tests/ + scripts/vps/tests/ | Same suite as Alt A, adapted for SQLite |
| `purge_old_records()` | db.py | 90-day retention (same as Alt A) |
| Heartbeat + counter metrics | scripts/vps/ | Same as Alt A |

---

### 5. Migration Cost (LLM-Native)

**Total: ~$80-100 compute, 4-5 weeks wall-clock**

| Wave | Items | Cost | Wall-clock |
|---|---|---|---|
| Wave 0 (P0, do regardless) | Same as Alt A | ~$10 | 2-3 days |
| Wave 1 (SQLite expand) | Add spec_lifecycle + spec_transitions tables; migrate 190 YAMLs (idempotent); start dual-write in callback | ~$15 | 1 week |
| Wave 2 (verify + switch reads) | Reconciliation cron; FF for YAML==SQLite parity; switch scan_queued + render_backlog + gate reads to SQLite | ~$15 | 1 week |
| Wave 3 (contract + decompose) | Stop YAML writes; extract gate.py + callback.py to 200 LOC; replace 8-rule with `git log --grep` | ~$20 | 1 week |
| Wave 4 (cleanup) | Delete lifecycle.py + CAS code + migration script; lifecycle_archive.py as async audit | ~$10 | 3-4 days |
| Wave 5 (CI + ops) | Fitness functions, vps-orch CLI, metrics, hooks deployment | ~$15 | 1 week |

**Each wave includes parity verification before proceeding.** Rollback at each phase via dual-write keeping YAML as backup.

---

### 6. Risk Per Devil / Security / Martin

| Risk | Likelihood | Impact | Mitigation in Alt B |
|---|---|---|---|
| **SQLite cross-process serialization** (Devil's note: orchestrator + callback are two processes; WAL handles readers + 1 writer per process) | MEDIUM | HIGH | All status writes go through callback subprocess (single writer per logical operation); orchestrator only reads via SELECT; BEGIN IMMEDIATE on writes |
| **Multi-repo topology** (Devil: lifecycle YAMLs live in EACH project's git history; SQLite is single file) | MEDIUM | MEDIUM | SQLite owns operational state for ALL projects (already true today for compute_slots, task_log); lifecycle_archive.py preserves per-project git history for audit |
| **Migration data loss** (Ops critique: half-migrated state) | LOW | HIGH | Expand-contract pattern: dual-write window of 1 week minimum; daily parity verification; YAML kept as backup until Wave 4 |
| **Loss of cryptographic audit trail** (Security: git commits = tamper-evident; SQLite rows = mutable) | MEDIUM | MEDIUM | lifecycle_archive.py writes YAML to git on every status change (async, best-effort) — preserves git audit trail without depending on it as SoR |
| **Multi-machine convergence permanently lost** | HIGH | LOW (if Devil Q1 answered "theoretical") | Acknowledged trade-off; if multi-machine becomes real later, restoration path: re-introduce git-archive as SoR, SQLite as cache (reverse of current direction). Reversible at $50-100. |
| **`bootstrap_new_specs` removal requires Spark cutover in 10 projects atomically** | MEDIUM | HIGH | Same as Alt A: orchestrator startup check; Spark skill update is single source; cutover scripted |
| **Fix train moves to db.py** (Devil's prediction) | LOW | MEDIUM | db.py is structurally simpler than callback.py; FF-01 LOC limit applies; SQL invariants enforce themselves |
| **`git log --grep` false positives** (Martin's critique: matches body references like "See FTR-123 for context") | LOW | LOW | Anchored regex `--grep="\(${SPEC_ID}\b\|^[a-z]\+([^)]*${SPEC_ID}"`; tests cover both real conventions; trailer convention is more permissive (which is what we want for awardybot) |

---

### 7. When This Is the Right Choice

- Multi-machine convergence is aspirational (laptop dev only, single VPS prod, no immediate multi-VPS plan).
- Founder values "I can debug status by running one SQL query" over "git log is the cryptographic SoR."
- Founder is willing to invest 4-5 weeks in a structurally cleaner system with -1200 LOC delta.
- "ARCH-186's CAS plumbing was clever but generated 5 bugs in 1 month — clever is the wrong word for that."

---

## Alternative C — "Decouple & Defer" (Devil's Path)

**Philosophy:** The real disease is **temporal coupling** between status determination and event completion (Neal's hidden insight). Callback should not infer status; it should only react to pueue events. Status determination is a separate, independent concern — make it a separate daemon. callback shrinks to ~80 LOC; lifecycle writes go through a gate daemon that polls `origin/develop` every 60s. Strangler Fig everything else.

**Best for:**
- Founder is willing to invest 4-6 weeks for the cleanest possible rewrite.
- Founder accepts 60-second eventual consistency window for status updates.
- Founder values "every component does one thing" over "every operation is synchronous."
- "I want the simplest possible mental model: pueue fires → callback dispatches; git changes → gate updates status. Two independent loops."

---

### 1. Module Split

```
scripts/vps/
├── common.py            ~120 LOC  NEW (same as A, B)
│
├── callback.py          ~80 LOC   (was 1374) — most aggressive reduction
│   Responsibility: ONE — receive pueue signal, release slot, log task, dispatch QA/reflect, exit 0
│   Does NOT call gate. Does NOT write lifecycle. Does NOT know about git log.
│   def main(pueue_id, group, result):
│       label = resolve_label(pueue_id)              # 5 LOC
│       spec_id = extract_spec_id(label)             # 3 LOC
│       project = resolve_project(label)             # 3 LOC
│       db.release_slot(pueue_id)                    # 1 LOC
│       db.finish_task(pueue_id, result)             # 1 LOC
│       if result == "Success":
│           dispatch_qa(project, spec_id)            # 5 LOC
│           dispatch_reflect(project, spec_id)       # 5 LOC
│       event_writer.notify(project, spec_id)        # 3 LOC
│       sys.exit(0)
│
├── gate-daemon.py       ~150 LOC  NEW
│   Responsibility: ONE — every 60s, for each in_progress spec across all projects,
│                   run `git log origin/develop --grep SPEC-ID` and update status if found
│   Runs as separate systemd unit (dld-gate-daemon.service)
│   Has health check endpoint (`vps-orch gate-health`)
│   Emits structured log + counter on every cycle
│
├── lifecycle.py         ~200 LOC  (was 602) OR replaced by db.py SQLite tables
│   Decision: keep git-YAML (simpler CAS using `git add + git commit`)
│            OR SQLite (B's path)
│   The decoupling works with either storage choice
│
├── orchestrator.py      ~400 LOC  (was 667)
│   Remove: bootstrap_new_specs
│   Remove: WT read of backlog.md
│   Change: scan_queued + reconcile_orphans logic
│
├── db.py                ~550 LOC  (same as A)
│
├── render_backlog.py    ~200 LOC  (same as A or B)
│
└── spec_operator.py     ~50 LOC   (same as A)
```

**Net LOC delta:** ~3144 → ~1750 (about **-1400 LOC** — largest reduction).

---

### 2. What Dies (Most of Callback's Current Responsibilities)

Beyond Alt A's zombies:

| What | Where | Why Dies in C |
|---|---|---|
| `verify_status_sync` 202-LOC function | callback.py | Gate is separate daemon, not callback function |
| 8-rule gate (cefaa55) | callback.py | Gate daemon uses 1 rule (`git log --grep`) |
| `_subject_implements` regex | callback.py | `git log --grep` searches entire commit message body |
| `_emit_audit` 12-arg function | callback.py | Replaced by structured logger in gate-daemon |
| `_render_and_commit_backlog` from callback hot path | callback.py:1187 | Render becomes async post-write hook, not gate path |
| Circuit breaker as gate rule | callback.py | Becomes optional safety net in gate-daemon (simplified to log+alert, not pueue pause) |
| `bootstrap_new_specs` | orchestrator.py | Same as A, B — Spark writes lifecycle directly |

---

### 3. New Components

| What | Where | Purpose |
|---|---|---|
| `gate-daemon.py` | scripts/vps/gate-daemon.py | Standalone process: poll origin/develop, update lifecycle for in_progress specs |
| `dld-gate-daemon.service` | systemd unit | Manages gate daemon (Restart=on-failure, WatchdogSec=60) |
| Gate health endpoint | gate-daemon.py | Used by `vps-orch gate-health` for monitoring |
| Cycle counter + last_poll_at | gate-daemon.py + SQLite | Observability for the new daemon |
| Structured gate decision log | callback-gate-decisions.jsonl | Per-cycle, per-spec decision record |

---

### 4. Migration Cost (LLM-Native)

**Total: ~$100-150 compute, 5-6 weeks wall-clock** (most expensive of the 3)

| Wave | Items | Cost | Wall-clock |
|---|---|---|---|
| Wave 0 (P0, do regardless) | Same as A, B | ~$10 | 2-3 days |
| Wave 1 (write gate-daemon alongside existing callback) | New file gate-daemon.py + systemd unit; runs in parallel; writes shadow lifecycle entries with `by="gate-daemon-shadow"` | ~$20 | 1 week |
| Wave 2 (verify parity) | For 1 week, every status decision is made by BOTH old callback gate AND new gate-daemon; structured comparison log; agreement % tracked daily | ~$10 (mostly observation) | 1 week |
| Wave 3 (cutover) | Remove gate logic from callback.py; callback shrinks to 80 LOC; gate-daemon becomes sole status determiner | ~$25 | 1 week |
| Wave 4 (orchestrator + bootstrap) | Same as A, B: kill bootstrap_new_specs; Spark writes lifecycle directly | ~$15 | 1 week |
| Wave 5 (decompose callback dispatcher) | Extract dispatch_qa, dispatch_reflect to dispatcher.py; clean callback.py | ~$15 | 3-4 days |
| Wave 6 (CI + ops + hooks) | Fitness functions, vps-orch CLI, register-project.sh, observability | ~$15 | 1 week |

**Why most expensive:** parallel operation period (Wave 1-2) requires running two implementations and comparing outputs; this is observation-heavy, not just code-write.

---

### 5. Risk Per Martin / Devil / Operations

| Risk | Likelihood | Impact | Mitigation in Alt C |
|---|---|---|---|
| **Eventual consistency window: QA dispatches before gate updates status** (Martin's critique) | MEDIUM | MEDIUM | QA dispatch reads spec status from db; if status==in_progress at dispatch time, QA can either: (a) trigger immediate gate poll OR (b) accept that QA validates against git state, not lifecycle state |
| **Gate daemon dies silently between polls** (Ops critique) | LOW | HIGH | systemd WatchdogSec=60s + heartbeat counter; ALERT-008 fires if no gate cycle in 5 min; `vps-orch gate-health` returns last_poll_at |
| **60-second status detection latency** vs current ~instant | HIGH (by design) | LOW | Acknowledged trade-off; current synchronous gate is ~instant when working, ~5 hours when broken (today's incident). 60s consistent > 0s/5h variable. |
| **Two writers to lifecycle: gate-daemon + orchestrator.bootstrap** | MEDIUM | MEDIUM | Bootstrap is removed in Wave 4; until then, both write, gate-daemon only updates in_progress→done |
| **Fix train moves to gate-daemon** (Devil's prediction) | LOW | LOW | gate-daemon is structurally single-purpose; FF-01 LOC limit; the "rule accumulation" problem requires reading git log differently — gate logic stays at 5 lines |
| **Migration risk during parallel period (Wave 1-2)** | LOW | MEDIUM | Shadow writes only, no behavioral change; if parity fails, gate-daemon is just turned off |
| **Spark cutover (lifecycle.create_initial in Spark)** | SAME AS A/B | SAME | Same mitigation: orchestrator startup check |
| **Need to run gate-daemon as separate systemd unit** | LOW | LOW | One new systemd unit file; operational overhead minimal |
| **Agent ergonomics: gate decisions visible via separate log** | LOW | LOW | `vps-orch gate-history SPEC-ID` exposes structured decisions; better than current "grep callback-debug.log" |

---

### 6. When This Is the Right Choice

- Founder accepts "60-second eventual consistency" as preferable to "synchronous coupling that breaks subtly."
- Founder believes the architecture-as-orthogonal-loops mental model ("pueue fires → callback dispatches" + "git changes → gate updates") is fundamentally cleaner.
- Founder is willing to operate 2 parallel implementations for a week before cutover (highest verification confidence).
- "I want a system where each component fits in my head on one read. Not 'one mind owns it' — 'one mind can hold each component in working memory.'"
- Multi-machine convergence question is irrelevant (gate-daemon reads origin/develop regardless of where the write happened; works on 1 or N machines).

---

## Cross-Alternative Trade-offs Table

| Aspect | Alt A (Patch & Harden) | Alt B (SQLite Reset) | Alt C (Decouple & Defer) |
|---|---|---|---|
| **Innovation tokens used** | 0 new (preserves ADR-023's existing token spend) | -1 (revokes git-as-DB token) | -1 (revokes synchronous-callback token) |
| **Net LOC delta from current 3144** | **-800** (to ~2350) | **-1200** (to ~1900) | **-1400** (to ~1750) |
| **New failure modes introduced** | WT-touch in simplified CAS (low); fitness function false negatives (low) | SQLite cross-process write contention (medium); multi-repo SoR ownership (medium) | Eventual consistency (designed-in); gate-daemon hang (mitigated by systemd watchdog) |
| **Number of future fix-train risks** | 4 surfaces (gate.py, lifecycle.py, callback.py, render_backlog.py) | 2 surfaces (gate.py, db.py) — fewer because lifecycle.py is gone | 2 surfaces (gate-daemon.py, callback.py) — clearest separation |
| **Multi-machine convergence support** | YES (preserved by design) | NO (deliberate trade-off) | YES (gate-daemon reads origin regardless) |
| **Agent ergonomics (context budget per task)** | ~3K tokens per module (with AGENT_REFERENCE.md) | ~2K tokens (SQLite schema is self-describing; no CAS plumbing to understand) | ~2K tokens (each component fits in one context shot) |
| **Time to first risk-reduction (today's incident class becomes impossible)** | Wave 0+1 = ~10 days | Wave 0+1 = ~10 days | Wave 0+1 = ~10 days |
| **Wall-clock to fully migrated** | 3-4 weeks | 4-5 weeks | 5-6 weeks |
| **Compute cost (LLM-native)** | ~$55-65 | ~$80-100 | ~$100-150 |
| **Reversibility if wrong** | HIGH (each wave reversible; no SoR migration) | MEDIUM (SQLite migration is irreversible but lifecycle_archive.py preserves git history) | HIGH (Strangler Fig — gate-daemon can be turned off at any point in Waves 1-3) |
| **Conceptual integrity (Brooks)** | C (decomposed but still 5 ideas: gate, writer, dispatcher, audit, circuit) | B (3 ideas: gate, dispatcher, db) | A (2 loops: completion-reaction + git-state-monitor) |
| **Risk of fix train resumption** | MEDIUM (4 surfaces, accumulation possible) | LOW (2 surfaces, SQL invariants self-enforce) | LOW (2 surfaces, polling daemon is naturally simple) |
| **Founder decisions required** | 1 (approve Wave 1-4 sequence) | 3 (storage cutover dates, dual-write duration, downtime window) | 2 (parallel duration, cutover date) |
| **Devil's "one mind responsible" answer** | NOT addressed — relies on fitness functions | NOT addressed — relies on SQL constraints | NOT addressed — but architecture is simple enough that "one mind" requirement is easier to satisfy |
| **Honest verdict on the fix train** | Slows it down via FF + decomposition; does not stop it structurally | Stops the git-as-DB bug class; new class possible in SQLite | Stops the synchronous-coupling bug class; new class possible in polling daemon |

---

## Recommended P0 (Independent of A/B/C — Ship Immediately)

These items are pure wins regardless of which alternative wins. Every persona converged on them. They are P0 because they have measurable impact on incidents that have already occurred. **Estimated total: ~$10 compute, 2-3 days wall-clock. Spark spec per item.**

| # | Item | File:Line | Cost | Incidents Prevented |
|---|---|---|---|---|
| **P0-1** | `pyproject.toml: testpaths = ["tests", "scripts/vps/tests"]` | pyproject.toml:19 | $1, 5 min | All future regressions in lifecycle/orchestrator (currently invisible to CI) |
| **P0-2** | `tests/conftest.py: autouse fixture` for DB_PATH isolation (every test uses tmp_db) | tests/conftest.py | $1, 30 min | Local tests poisoning prod-DB (today's bug 5) |
| **P0-3** | Rotate TELEGRAM_BOT_TOKEN; remove from git-tracked .env; add to .gitignore; move to Nexus; `git filter-repo` history cleanup | scripts/vps/.env | $1 + manual token rotation, 1 hour | Confirmed credential exposure (P0 security incident — independent of architecture debate) |
| **P0-4** | Zombie cleanup: delete spec_lint.py; remove DLD-CALLBACK-MARKER from template/.claude/skills/spark/completion.md:46 + .claude/agents/spark/facilitator.md:218-221 | spec_lint.py, completion.md, facilitator.md | $2, 30 min | Spark spec malformed-blocker (current state); FF-02 zombie validator inverted signal |
| **P0-5** | BOOTSTRAP_ANOMALY threshold log: `if created_count > 3 in bootstrap_new_specs: log.warning(...) + counter` | orchestrator.py:280-333 | $1, 30 min | Today's incident class (15 fake-done flips) detected at 11:19 instead of 16:00 |

**Bonus P0+1 items** (still independent of A/B/C, can be done same week):

| # | Item | File:Line | Cost |
|---|---|---|---|
| P0-6 | `_push_best_effort`: DEBUG → WARNING + counter emission | lifecycle.py:266 | $1, 15 min |
| P0-7 | Add `GROWTH` to `_SPEC_ID_RE` in callback.py (or extract to common.py) | callback.py:43 | $1, 15 min |
| P0-8 | `lifecycle._run()`: add `timeout=30` to all 8 git plumbing calls | lifecycle.py:77-88 | $1, 30 min |
| P0-9 | Heartbeat file write at end of orchestrator main loop + cron monitor (Hermes event if stale >10min) | orchestrator.py + new heartbeat_monitor.py | $3, 1 hour |
| P0-10 | Fix `reconcile_orphans` identity attribution: `by="orchestrator"` not `by="callback"` | lifecycle.py:551 | $1, 15 min |

**Total P0 + P0+1: ~$15 compute, 1 week wall-clock if shipped serially, 2-3 days if parallel.**

**Critically:** These P0 items do NOT commit founder to any alternative. They are reversible, independent, and high-ROI regardless of architectural direction. **Recommendation: ship P0 in the next 5 days while founder decides A vs B vs C.**

---

## Decision Framework — Which Alternative for Which Founder Answer

The choice depends on founder's answers to Devil's questions. Use this table:

| Founder's answer to Devil Q1 (multi-machine?) | Founder's answer to Devil Q4 (downtime tolerance?) | Founder's risk appetite | Recommended Alternative |
|---|---|---|---|
| "Operational today (laptop ↔ VPS sync working)" | Any | Any | **Alternative A** — preserves ADR-023 |
| "Aspirational only (no multi-machine today)" | "Zero downtime acceptable; willing to do dual-write" | Medium-high | **Alternative B** — clean revoke |
| "Aspirational only" | "Some downtime OK; just want it cleanest" | High | **Alternative B** OR **Alternative C** |
| "Don't know / undecided" | Any | Low (incident-fatigued) | **Start with P0 + Alt A Wave 1-2**, defer A vs B vs C until 2-4 weeks of data |
| "Theoretical but I'm planning multi-VPS in 3-6 months" | Any | Any | **Alternative A** — don't paint into a corner |
| "Operational AND I want clean separation of concerns" | Any | High | **Alternative C** — git-YAML SoR + decoupled gate works for any topology |

**Universal recommendation (if founder is unsure):**

1. **Ship P0 this week.** All 10 items, $15 compute, 2-3 days. These are reversible and high-ROI.
2. **Wait 2-4 weeks.** Measure incident rate post-P0. Track:
   - Did `_push_best_effort` WARNING reveal any push failures? (Answers Q1 multi-machine question)
   - Did BOOTSTRAP_ANOMALY fire? (Validates the alert design)
   - Did `pyproject.toml` testpaths catch any regressions?
3. **Reconvene synthesis.** With 2-4 weeks of post-P0 evidence, the storage/coupling question becomes data-driven, not theoretical.
4. **Then choose A, B, or C.** With evidence in hand, the choice is mechanical.

---

## Net-Add-Only Disease — Honest Accounting

Devil's critique observed: **only Alternative E (Dan's pragmatist) had net-removal larger than additions**. Every other persona proposed structural additions without removing equivalents.

Re-verified against the three alternatives:

| Alternative | LOC removed | LOC added | Net delta | Files removed | Files added | Net file count |
|---|---|---|---|---|---|---|
| **A (Patch & Harden)** | ~1000 (CAS plumbing simplified, zombies deleted, callback decomposed) | ~200 (common.py, gate.py, circuit.py, audit.py, render_backlog enhanced) | **-800** | 4 (spec_lint, migrate_backlog, atomic_write_file dup, bootstrap_new_specs path) | 5 (common, gate, circuit, audit, register-project.sh, vps_orch.py) | +1 net file |
| **B (SQLite Reset)** | ~1700 (lifecycle.py entire 602 + 8-rule gate 202 + bootstrap 50 + CAS 200 + zombies 200 + verify_status_sync 200) | ~500 (SQLite tables + gate.py + lifecycle_archive.py + vps_orch.py + common.py) | **-1200** | 5 (spec_lint, migrate_backlog, lifecycle.py, bootstrap, atomic_write_file) | 5 (gate.py, lifecycle_archive.py, vps_orch.py, common.py, register-project.sh) | 0 net file |
| **C (Decouple & Defer)** | ~1850 (verify_status_sync 202 + 8-rule gate + circuit-in-callback + audit-in-callback + bootstrap 50 + most of callback 1100) | ~450 (callback shrunk to 80, gate-daemon 150, lifecycle preserved 200-400, vps_orch, common) | **-1400** | 4 (spec_lint, migrate_backlog, bootstrap, _emit_audit-as-function) | 6 (gate-daemon, dld-gate-daemon.service, common, vps_orch, register-project.sh, dispatcher.py extracted) | +2 net file |

**Alt B has the cleanest net removal accounting.** Alt C removes the most LOC but adds the most files (each small). Alt A removes least but adds least new infrastructure.

**No alternative is net-add-only.** Each pays Devil's removal tax.

---

## What the Devil Said That No Alternative Fully Addresses

> "The conceptual integrity of this system was lost at ARCH-186, not in the implementation bugs. A simple design maintained by one person for one purpose is more reliable than an elegant design maintained by committee through five incident cycles."

**The honest gap in all three alternatives:** None of them name a sole architectural owner. Each alternative makes the architecture *more amenable* to a sole owner (decomposition, fewer ideas, cleaner separation) — but if founder remains the implicit committee-of-one-incident-at-a-time, the fix train can resume in any alternative.

**Mitigation across all three:** Fitness functions (FF-01..FF-08) raise the cost of accretion. The fix-train detector (B's check_fix_train.py) makes the accretion visible. These do not replace conceptual integrity; they bound its erosion.

**The decision founder must make explicitly:**

> "Going forward, every architectural decision in scripts/vps/ goes through [Founder | named architect agent | architecture council]. No exceptions. Incidents are fixed within the existing architecture; if the fix requires a new principle, it requires re-opening the architecture decision."

Without this, the next ARCH or BUG-XXX spec will reproduce today's pattern in 4-8 weeks regardless of which alternative wins.

---

## Migration Path Outline (To Be Filled After Human Chooses)

Once founder selects A, B, or C, the next step is **`/spark` to produce wave-by-wave specs**. Each wave is one Spark spec → autopilot execution. Below is the dependency graph each alternative will inherit.

**Universal Wave 0 (regardless of choice):** Ship P0 set above.

**Then per alternative:**

- **A path:** P0 → A.Wave1 (decompose callback) → A.Wave2 (lifecycle hardening) → A.Wave3 (CI) → A.Wave4 (deployment)
- **B path:** P0 → B.Wave1 (SQLite expand) → B.Wave2 (verify+switch reads) → B.Wave3 (contract+decompose) → B.Wave4 (cleanup) → B.Wave5 (CI)
- **C path:** P0 → C.Wave1 (gate-daemon parallel) → C.Wave2 (parity verify) → C.Wave3 (cutover) → C.Wave4 (bootstrap removal) → C.Wave5 (dispatcher extract) → C.Wave6 (CI)

Each wave is one Spark spec. Each spec gets autopilot execution. Each is independently reviewable + reversible.

**Cost summary (assuming founder picks one and proceeds):**

| Alternative | Total compute | Wall-clock | Risk-adjusted ROI (vs current incident rate $258/week false-retries + ~2 hr/incident human debug) |
|---|---|---|---|
| A | ~$65 | 3-4 weeks | Payback in 4-5 weeks at current incident rate |
| B | ~$100 | 4-5 weeks | Payback in 6-7 weeks; eliminates entire git-as-DB bug class |
| C | ~$150 | 5-6 weeks | Payback in 8-9 weeks; cleanest structural separation |

All three pay back. The choice is about **what is eliminated permanently** (Devil's net-removal question), not about cost.

---

## Final Synthesizer Note

The peer consensus on symptoms is real and grounded in 85 audit findings. The peer divergence on architecture is also real and reflects a single binary question (multi-machine: operational or aspirational?) that only founder can answer.

The five P0 items are **non-negotiable and independent of architecture choice**. Ship them this week.

The three alternatives are **distinct, exclusive, and internally coherent**. Each is implementable by Spark + autopilot. Each addresses today's 5 bugs by structurally different mechanisms.

The Devil's 5 questions are **load-bearing**. Founder's answers determine the alternative.

**Synthesizer does not pick.** Founder picks. Then we Spark the chosen path.

---

## References

- Deep Audit Report: `/home/dld/projects/dld/ai/audit/deep-audit-report.md` (85 findings)
- Architecture Agenda: `/home/dld/projects/dld/ai/architect/architecture-agenda.md`
- Persona research: `research-{domain,data,ops,security,evolutionary,dx,llm,devil}.md`
- Cross-critiques: `critique-{domain,data,ops,security,evolutionary,dx,llm,devil}.md`
- ADR chain: `.claude/rules/architecture.md` (ADR-018 → 023 → 024)
- Primary code under review: `scripts/vps/callback.py` (1374 LOC), `lifecycle.py` (602 LOC), `orchestrator.py` (667 LOC), `db.py` (531 LOC), `render_backlog.py`, `spec_operator.py`, `migrate_backlog_to_lifecycle.py`
