---
paths:
  - "scripts/**"
  - ".claude/scripts/**"
  - "packages/**"
  - "tests/**"
---

# Project Dependencies

Dependency map between project components.

## How to Read

- `A → B` means "A uses B"
- `A ← B` means "A is used by B"

---

## {domain_name}

**Path:** `src/domains/{domain_name}/`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| {dependency} | {path} | {function}() |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| {caller} | {file}:{line} | {function}() |

### When changing API, check

- [ ] {dependent_1}
- [ ] {dependent_2}

---

## Example: billing

**Path:** `src/domains/billing/`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| users | infra/db | get_user() |
| database | infra/db | transactions table |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| campaigns | services.py:45 | get_balance() |
| campaigns | services.py:78 | check_can_spend() |
| seller | actions.py:23 | deduct_balance() |

### When changing API, check

- [ ] campaigns
- [ ] seller

---

## scripts/vps/db (orchestrator SQLite)

**Path:** `scripts/vps/db.py` (373 LOC — was 602, TECH-212 split)

`db.py` keeps `get_db`/`_ensure_migrations`/slots/`projects`/`task_log`/`seed_projects_from_json`
plus a `_delegate` factory that binds 12 names from the two leaves below back onto the `db`
module, so `db.<name>` and `from db import get_db` are unchanged for every consumer.

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| sqlite3 | stdlib | connection, Row, contextmanager |
| schema.sql | scripts/vps/schema.sql | project_state, compute_slots, task_log, night_findings, callback_decisions, classifier_refusals |
| db_decisions.py | scripts/vps/db_decisions.py | record_decision, count_demotes_since, clear_decisions, log_sdk_post_result_error, log_gate_cycle, get_gate_health — delegated, `immediate=True` preserved for `clear_decisions` |
| db_findings.py | scripts/vps/db_findings.py | save_finding, get_new_findings, update_finding_status, get_finding_by_id, get_all_findings, get_projects_for_night_scan — delegated, `immediate=True` preserved for save_finding/update_finding_status |
| db_cli.py | scripts/vps/db_cli.py | `main(sys.argv, sys.modules[__name__])` — argv dispatcher, deliberately does NOT `import db` (avoids a second module object with its own `DB_PATH` under `python3 db.py`) |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| orchestrator.py | scripts/vps/orchestrator.py | seed_projects_from_json(), get_all_projects(), get_project_state(), try_acquire_slot(), log_task(), update_project_phase() |
| callback.py | scripts/vps/callback.py | release_slot(), finish_task(), update_project_phase(), get_project_state() |
| callback.py | scripts/vps/callback.py | record_decision(), count_demotes_since(), clear_decisions() (TECH-169) |
| night-reviewer.sh | scripts/vps/night-reviewer.sh (FTR-147 Task 4) | CLI: save-finding, get-new-findings, update-phase |
| claude-runner.py | scripts/vps/claude-runner.py | log_sdk_post_result_error() (BUG-188 Layer 4, lazy import) |
| claude-runner.py | scripts/vps/claude-runner.py | log_classifier_refusal() — classifier decline telemetry (lazy import; failure logs WARNING and never fails the run) |
| gate-daemon.py | scripts/vps/gate-daemon.py | log_gate_cycle(), get_all_projects() (ARCH-190) |

### When changing API, check

- [ ] orchestrator.py
- [ ] callback.py
- [ ] night-reviewer.sh (CLI: save-finding / get-new-findings / update-phase)
- [ ] claude-runner.py (log_sdk_post_result_error signature — BUG-188)
- [ ] claude-runner.py (log_classifier_refusal signature — refusal detect; exit 4 = `classifier_refusal`)
- [ ] gate-daemon.py (log_gate_cycle signature — ARCH-190)
- [ ] db_decisions.py / db_findings.py (pure leaves, first param is the sqlite connection — no `import db`; keep it that way)
- [ ] db_cli.py (`main(argv, api)` — api param must stay the db module, not a fresh import)

---

## scripts/vps/run-agent.sh (provider dispatcher)

**Path:** `scripts/vps/run-agent.sh`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| claude-runner.py | scripts/vps/claude-runner.py | exec dispatch |
| codex-runner.sh | scripts/vps/codex-runner.sh | exec dispatch |
| /proc/meminfo | Linux kernel | RAM floor gate (3GB check) |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| Pueue daemon | pueue.yml callback config | task execution |
| orchestrator.py | scripts/vps/orchestrator.py | pueue add invocation |
| callback.py | scripts/vps/callback.py | pueue add for QA/Reflect dispatch |

### When changing API, check

- [ ] orchestrator.py (pueue add arg order)
- [ ] callback.py (label format)

---

## scripts/vps/claude-runner.py

**Path:** `scripts/vps/claude-runner.py` (329 LOC — was 912, TECH-213 split)

Entry point only: pinned config (`MODEL`/`AUTOPILOT_EFFORT`/`TIMEOUT_SECONDS`/`MAX_TURNS`
and the measurements behind them), `_salvage_if_needed`, `run_task`, `main` — plus a
re-export block, because the runner's tests reach the moved names as `runner.<name>`.

| Module | LOC | Holds |
|---|---|---|
| `runner_env.py` | 31 | `load_env` — `.env` next to the script into `os.environ` |
| `runner_cli.py` | 129 | `_MIN_CLI_VERSION`, `_SYSTEM_CLI_FALLBACK`, `_cli_version`, `_resolve_cli_path` (newest CLI, not first on PATH), `warn_if_stale`, `ALLOWED_TOOLS` |
| `runner_heartbeat.py` | 42 | `_write_heartbeat` — atomic per-turn heartbeat (TECH-198) |
| `runner_refusal.py` | 113 | `_refusal_from_message`, `_refusal_summary`, `_REFUSAL_*` — classifier declines; owns the exit-4 decision (ADR-029). stdlib only, duck-typed, never imports the SDK |
| `runner_result.py` | 367 | `new_run_state` + `apply_*`, `_session_totals`, `build_log_data`, `write_run_log`, `_EXIT_REASONS`, `log_post_result_error`, `log_refusal_telemetry`. Also SDK-free — the caller does the isinstance checks |
| `runner_loop.py` | 220 | `build_options`, `consume` (the `async for` over `query`), `handle_sdk_exception` (ADR-024 BUG-188 branch, SDK-init-timeout → 124) |

**The split line is the SDK.** `runner_loop` is the only sibling that imports
`claude_agent_sdk`, and that is not a style choice: the runner's tests load
`claude-runner.py` from source with a fake SDK in `sys.modules`, so any module that binds
SDK names at import time must be reloaded with it. The three fixtures do
`sys.modules.pop("runner_loop", None)` before `exec_module` for exactly that reason, and
`test_claude_runner_refusal.py` patches `mod.runner_loop.query`, not `mod.query`.
Moving `consume` back into a module the fixtures do not reload silently returns the real
(absent) SDK — 16 tests failed that way during TECH-213 before the fixtures were fixed.

**Telemetry takes `db` as a parameter**, never a self-import: the tests substitute
`runner._orch_db` to assert what a run records, and an import inside `runner_result`
would make that substitution a no-op.


### Uses (→)

| What | Where | Function |
|------|-------|----------|
| claude CLI | `CLAUDE_CLI_PATH` env, else newest of PATH / `~/.local/bin/claude` / `/usr/local/bin/claude` | `--version` probe then SDK `cli_path=`. Resolution is **by version, not PATH order** — see `_resolve_cli_path` |
| claude_agent_sdk | pip dep 0.1.63 | query(), ClaudeAgentOptions(stderr=callback) (BUG-188 Layer 2) |
| db.py | scripts/vps/db.py | log_sdk_post_result_error() — telemetry on post-result SDK exception (BUG-188 Layer 4, lazy import) |
| db.py | scripts/vps/db.py | log_classifier_refusal() — telemetry on `stop_reason: "refusal"`; the only counter an HTTP-200 decline lands in (it is not billed and raises no exception) |
| salvage.py | scripts/vps/salvage.py | spec_id_from_path(), salvage_run() — push the worktree on non-zero exit and on SIGTERM (optional import) |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| run-agent.sh | scripts/vps/run-agent.sh:47 | exec dispatch (provider=claude) |
| heartbeat_reaper.py | scripts/vps/heartbeat_reaper.py | reads logs/*.heartbeat.json files written by _write_heartbeat (TECH-198) |

---

## scripts/vps/salvage.py

**Path:** `scripts/vps/salvage.py`

Pushes what a dead autopilot run built. Autopilot commits per task into a worktree
branch and pushes once, at the end of PHASE 3 (TECH-085), so every abnormal exit
strands finished commits on a local branch nothing else reads. Runs only on failure,
so the one-push-per-spec rule is untouched.

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| lifecycle.py | scripts/vps/lifecycle.py | `run_git` — byte-level git I/O (never `text=True`) |
| git CLI | PATH | worktree list, plumbing snapshot (private `GIT_INDEX_FILE` + CAS `update-ref`), push |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| claude-runner.py | scripts/vps/claude-runner.py `_salvage_if_needed` | non-zero exit + SIGTERM handler |

### When changing API, check

- [ ] claude-runner.py (`_salvage_if_needed` — return dict lands in the run log as `salvage`)
- [ ] callback.py (`_parse_log_file` if `salvage` ever becomes a decision input; today it is telemetry only)
- [ ] worktree-setup.md §0a sweep (a pushed branch makes the worktree sweepable — that is intended)

---

## scripts/vps/codex-runner.sh

**Path:** `scripts/vps/codex-runner.sh`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| codex CLI | $CODEX_PATH or PATH | exec --sandbox workspace-write --json |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| run-agent.sh | scripts/vps/run-agent.sh:50 | exec dispatch (provider=codex) |

---

## scripts/vps/orchestrator.py

**Path:** `scripts/vps/orchestrator.py` (391 LOC — was 1078, TECH-215 split)

Split into four flat siblings; `orchestrator.py` keeps bootstrap (`_load_env`,
`_setup_logging`, `_write_pid`), `git_pull`, `startup_reconcile`, `scan_queued`,
`process_project`/`main`, and re-exports every moved name.

| Module | LOC | Holds |
|---|---|---|
| `orchestrator_slots.py` | 209 | `sync_projects`, `get_live_pueue_ids`, `pueue_has_active_label/_spec`, `release_orphan_slots`, `is_agent_running`, `_pueue_add` |
| `orchestrator_backlog.py` | 303 | `_parse_backlog` (ADR-026), `_bump_unparsable_counter`, `bootstrap_new_specs`, `_parse_priority_kind`, `cleanup_stale_stashes` |
| `orchestrator_inbox.py` | 136 | `_parse_inbox_file`, `scan_inbox` (ADR-021/022) |
| `orchestrator_queue.py` | 400 | `_backlog_deps` (deprecated fallback), `_spec_deps` (TECH-222 — lifecycle `depends_on` ∪ backlog `AFTER`, logs `DEP_VIA`/`DEP_SHAPE`), `_unmet_dependencies`, the decomposed `scan_queued` steps, `dispatch_night_review` |

**Two contracts that look stylistic and are not:**

1. **Re-export direction.** Names patched as `orchestrator.<name>` are imported into
   `orchestrator.py` with `from X import Y` and called by BARE NAME; the
   `orchestrator_queue` steps are called as MODULE ATTRIBUTES
   (`orchestrator_queue.record_dispatch(...)`). Inverting either direction makes a
   `patch()` silently miss its target — tests still pass, production is unpatched.
2. **`SCRIPT_DIR` is per-module.** `scan_inbox` and `dispatch_night_review` read their
   own module's `SCRIPT_DIR`, so `patch("orchestrator.SCRIPT_DIR", tmp_path)` does not
   reach them. Patch the owning module or the test shells out to the real pueue daemon.

No sibling imports `orchestrator` (enforced by a test). Edges: `orchestrator` →
{queue, slots, backlog, inbox}; queue/inbox → slots.

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| db.py | scripts/vps/db.py | seed_projects_from_json(), get_all_projects(), get_project_state(), get_available_slots(), get_provider_capacity(), try_acquire_slot(), log_task(), update_project_phase() |
| run-agent.sh | scripts/vps/run-agent.sh | pueue add autopilot + inbox dispatch (CLAUDE_CURRENT_SPEC_PATH env for both, BUG-199) |
| night-reviewer.sh | scripts/vps/night-reviewer.sh | pueue add --group night-reviewer (dispatch_night_review) |
| pueue CLI | PATH | pueue add --group --label --print-task-id |
| git CLI | PATH | git -C <dir> pull --ff-only origin develop |
| projects.json | PROJECTS_JSON env | hot-reload project list each cycle |
| lifecycle.py | scripts/vps/lifecycle.py | list_by_status(), read_lifecycle(), create_initial(), write_lifecycle() — reconciliation gate marks done by="orchestrator"; dispatch in scan_queued marks in_progress with pueue_id right after pueue add succeeds (BUG-218) |
| gate_logic.py | scripts/vps/gate_logic.py | parse_allowed_files(), fetch_develop() — scan_queued reconciliation gate (pre-dispatch "already on develop" check), delegated to `orchestrator_queue.reconcile_if_implemented` |
| gate_ancestry.py | scripts/vps/gate_ancestry.py | fetch_branch(), find_implementation(), branch_state() (TECH-221) — THE gate as of TECH-220 (ancestry primary, `gate_logic.find_implementation_commit` subject fallback); called from `orchestrator_queue.reconcile` (bool facade `reconcile_if_implemented`, which also sets/clears `CLAUDE_CONTINUE_BRANCH` in `os.environ`) / `record_dispatch` |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| systemd | dld-orchestrator.service | main daemon loop |

### When changing API, check

- [ ] callback.py (label format "project_id:SPEC-ID" must stay consistent)
- [ ] run-agent.sh (arg order: project_dir task provider skill)
- [ ] db.py (get_all_projects, try_acquire_slot, log_task, update_project_phase signatures)

---

## scripts/vps/callback.py

**Path:** `scripts/vps/callback.py` (371 LOC — was 1438, TECH-216 split, 2026-08-30; the dead
`_render_and_commit_backlog` and its `import lifecycle` were deleted in TECH-222)

Split into five flat siblings; `callback.py` keeps bootstrap, `resolve_label`/`parse_label`/
`map_result`, `write_event_for_skill`, `main`, and **re-exports every moved name** — root
`tests/` and `spec_operator.py` reach them as `callback.<name>`.

| Module | LOC | Holds |
|---|---|---|
| `callback_logs.py` | 227 | `_find_log_file`, `_skill_from_pueue_command`, `_parse_log_file`, `extract_agent_output` |
| `callback_dispatch.py` | 260 | `resolve_spec_id`, `is_already_queued`, `_pueue_add`, `dispatch_qa`, `dispatch_reflect`, `_merge_confirmed`, `_step6_dispatch_qa_reflect` (TECH-194 E / TECH-207) |
| `callback_scope.py` | 241 | `_get_started_at`, `_commit_stats`, `_is_test_path`, `_detect_out_of_scope_files` (BUG-199), `_audit_log_path`/`_write_audit`/`_emit_audit` (TECH-171) |
| `callback_circuit.py` | 202 | `CIRCUIT_*`, `is_circuit_open`, `_pueue_pause/_resume`, `_trip_circuit`, `_reset_circuit_cli`, `_record`, `note_demote` (TECH-169) |
| `callback_sync.py` | 349 | `verify_status_sync` as six named steps (`_read_existing_status` → `_collect_scope` → `_push_local_develop` → `_decide_status` → `_write_status` → `_Audit.emit`) |

**Same two contracts as the orchestrator split:** `main()` calls the re-exports by bare name,
so `monkeypatch.setattr(callback, "extract_agent_output", …)` still intercepts; the siblings
call each other as MODULE ATTRIBUTES (`callback_scope._commit_stats(...)`), so a test that
wants to reach `verify_status_sync` patches `callback_scope`/`callback_circuit`/`callback_sync`,
not `callback`. `SCRIPT_DIR` and `db` are per-module — patch the owning module.
CI coverage gate lists all six modules (`--cov` is keyed by module name).

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| db.py | scripts/vps/db.py | release_slot(), finish_task(), update_project_phase(), get_project_state(), try_acquire_slot(), log_task(), get_task_by_pueue_id() |
| db.py | scripts/vps/db.py | record_decision(), count_demotes_since(), clear_decisions() (TECH-169) |
| lifecycle.py | scripts/vps/lifecycle.py | write_lifecycle() — atomic plumbing commit of status (ARCH-186) |
| event_writer.py | scripts/vps/event_writer.py | notify() — send Hermes event |
| event_writer.py | scripts/vps/event_writer.py | notify_circuit_event() (TECH-169) |
| run-agent.sh | scripts/vps/run-agent.sh | pueue add for QA/Reflect dispatch |
| pueue CLI | PATH | pueue status --json, pueue log --json, pueue add |
| pueue CLI | PATH | pueue pause/start --group claude-runner (TECH-169 circuit) |
| spec files | ai/features/{SPEC_ID}*.md | _parse_allowed_files() reads `## Allowed Files` for implementation guard + _detect_out_of_scope_files() warning (BUG-199) |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| Pueue daemon | pueue.yml callback config | fires on task completion/failure |

### When changing API, check

- [ ] pueue.yml (arg order: id group result)
- [ ] run-agent.sh (arg order: project_dir task provider skill)
- [ ] event_writer.py (notify signature)
- [ ] schema.sql (compute_slots, task_log, project_state column names)
- [ ] lifecycle.py (write_lifecycle signature — ARCH-186 SoT)
- [ ] ai/features/ spec files (`## Allowed Files` format parsed by _parse_allowed_files)

---

## scripts/vps/lifecycle.py (ARCH-186)

**Path:** `scripts/vps/lifecycle.py`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| pyyaml | pip dep | yaml.safe_load / safe_dump |
| git CLI | PATH | atomic plumbing: hash-object, write-tree, commit-tree, update-ref (CAS form) |
| pathlib | stdlib | path manipulation |
| tempfile | stdlib | private GIT_INDEX_FILE for index isolation |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| callback.py | scripts/vps/callback.py | write_lifecycle() — sole writer of status |
| salvage.py | scripts/vps/salvage.py | run_git() — public alias of `_run`; do not re-derive its byte-level I/O rules |
| orchestrator.py | scripts/vps/orchestrator.py | list_by_status(), create_initial() (bootstrap), assert_clean_lifecycle_tree() (startup), reconcile_orphans() |
| render_backlog.py | scripts/vps/render_backlog.py | read_lifecycle() + list_all() for view generation |
| migrate_backlog_to_lifecycle.py | scripts/vps/migrate_backlog_to_lifecycle.py | initial migration one-shot |
| gate-daemon.py | scripts/vps/gate-daemon.py | list_by_status() — read-only, shadow mode (ARCH-190) |
| lifecycle_audit.py | scripts/vps/lifecycle_audit.py | read_lifecycle() — READ-ONLY drift detection (TECH-195) |
| recover_bootstrap_as_done.py | scripts/vps/recover_bootstrap_as_done.py | list_by_status(), recover_bootstrap_artifact() (TECH-195) |

### When changing API, check

- [ ] callback.py (write_lifecycle caller)
- [ ] orchestrator.py (4 callsites: list_by_status, create_initial, assert_clean, reconcile_orphans)
- [ ] render_backlog.py (read_lifecycle for view)
- [ ] tests/integration/test_callback_*.py (use write_lifecycle for setup)
- [ ] gate-daemon.py (list_by_status caller — ARCH-190 read-only)
- [ ] lifecycle_audit.py (read_lifecycle, LIFECYCLE_DIR — TECH-195)
- [ ] recover_bootstrap_as_done.py (recover_bootstrap_artifact, NotBootstrapArtifactError — TECH-195)

---

## scripts/vps/event_writer.py

**Path:** `scripts/vps/event_writer.py`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| openclaw CLI | ~/.npm-global/bin/openclaw | system event --mode now (immediate wake) |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| callback.py | scripts/vps/callback.py | import: notify() |
| callback.py | scripts/vps/callback.py | import: notify_circuit_event() (TECH-169) |
| night-reviewer.sh | scripts/vps/night-reviewer.sh | CLI: python3 event_writer.py <project_id> <msg> |
| heartbeat_reaper.py | scripts/vps/heartbeat_reaper.py | import: notify() — reap alert (TECH-198) |

### When changing API, check

- [ ] callback.py (notify import)
- [ ] night-reviewer.sh (CLI arg order)
- [ ] heartbeat_reaper.py (notify 5-arg signature — TECH-198)

---

## scripts/vps/night-reviewer.sh

**Path:** `scripts/vps/night-reviewer.sh`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| db.py | scripts/vps/db.py | get_project_state() (inline python3 -c), update-phase, save-finding, get-new-findings (CLI) |
| event_writer.py | scripts/vps/event_writer.py | python3 event_writer.py <project_id> <msg> |
| claude CLI | $CLAUDE_PATH or PATH | `cd <path> && flock --timeout 120 /tmp/claude-oauth.lock claude --print --output-format json --max-turns 30 -p "/audit night"`. **There is no `--cwd` flag** (checked against CLI 2.1.220); the script uses `cd`, and this row said otherwise until 2026-08-01 |
| flock | util-linux | serialize claude OAuth token access |
| jq | PATH | parse claude JSON output (.result field + findings array) |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| orchestrator.py | scripts/vps/orchestrator.py | dispatch_night_review() — pueue add --group night-reviewer |
| pueue daemon | night-reviewer group | task execution |

### When changing API, check

- [ ] orchestrator.py dispatch_night_review() (arg order: space-separated project IDs)
- [ ] db.py (save_finding, get_new_findings, update_project_phase signatures)
- [ ] event_writer.py (CLI: python3 event_writer.py <project_id> <msg>)

---

## scripts/vps/gemini-runner.sh

**Path:** `scripts/vps/gemini-runner.sh`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| gemini CLI | $GEMINI_PATH or PATH | gemini "$PROMPT" (headless, GEMINI_API_KEY auth) |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| run-agent.sh | scripts/vps/run-agent.sh:51 | exec dispatch (provider=gemini) |

### When changing API, check

- [ ] run-agent.sh (gemini case branch args)

---

## scripts/vps/orchestrator_monitor.py

**Path:** `scripts/vps/orchestrator_monitor.py`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| systemctl --user | stdlib subprocess | is-active dld-orchestrator.service |
| pueue status --json | PATH | claude-runner group paused check + running/queued counts |
| db.py | scripts/vps/db.py | callback_decisions — recent demotes in last 35 min |
| event_writer | scripts/vps/event_writer.py | notify() on anomaly |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| cron | */30 * * * * | full-status monitor (installed by setup-vps.sh section 8c) |

### When changing API, check

- [ ] setup-vps.sh (cron line for orchestrator_monitor.py — section 8c)
- [ ] event_writer.notify signature
- [ ] db.py callback_decisions schema

---

## scripts/vps/heartbeat_monitor.py (TECH-189 Task 8)

**Path:** `scripts/vps/heartbeat_monitor.py`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| .orchestrator-heartbeat | scripts/vps/.orchestrator-heartbeat | read ISO timestamp |
| event_writer | scripts/vps/event_writer.py | notify("dld", "ORCHESTRATOR_STALE: ...") |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| cron | */5 * * * * | liveness check (installed by setup-vps.sh) |
| orchestrator.py | scripts/vps/orchestrator.py:main loop | writes .orchestrator-heartbeat at end of each cycle |

### When changing API, check

- [ ] orchestrator.py (heartbeat file path must match) — SCRIPT_DIR/.orchestrator-heartbeat
- [ ] setup-vps.sh (cron line for heartbeat_monitor.py)

---

## scripts/vps/nexus-cache-refresh.sh

**Path:** `scripts/vps/nexus-cache-refresh.sh`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| nexus/bootstrap CLI | PATH | list-projects --ids, get-project-context |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| cron | */5 * * * * | periodic cache refresh |
| setup-vps.sh | scripts/vps/setup-vps.sh (--phase3) | cron installation |

### When changing API, check

- [ ] setup-vps.sh --phase3 (cron line)

---

## scripts/vps/setup-vps.sh

**Path:** `scripts/vps/setup-vps.sh`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| pueued | PATH or ~/.local/bin | daemon start, group creation, parallelism |
| pueue | PATH or ~/.local/bin | group add, parallel, status |
| sqlite3 | PATH | schema.sql init |
| schema.sql | scripts/vps/schema.sql | database initialization |
| requirements.txt | scripts/vps/requirements.txt | pip install into venv |
| callback.py | scripts/vps/callback.py | registered in pueue.yml callback |
| orchestrator.py | scripts/vps/orchestrator.py | ExecStart in dld-orchestrator.service |
| gate-daemon.py | scripts/vps/gate-daemon.py | ExecStart in dld-gate-daemon.service (ARCH-190) |
| heartbeat_reaper.py | scripts/vps/heartbeat_reaper.py | cron install section 8d (TECH-198) |
| .env | scripts/vps/.env | EnvironmentFile in systemd unit |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| operator | manual | one-command VPS bootstrap |
| systemd | generated units | ExecStart paths reference SCRIPT_DIR |

### When changing API, check

- [ ] callback.py (callback arg order must match pueue.yml template)
- [ ] orchestrator.py (ExecStart path in dld-orchestrator.service)
- [ ] gate-daemon.py (ExecStart path in dld-gate-daemon.service — ARCH-190)

---

## scripts/vps/gate-daemon.py (ARCH-190 Wave 1)

**Path:** `scripts/vps/gate-daemon.py`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| gate_logic | scripts/vps/gate_logic.py | fetch_develop(), parse_allowed_files() |
| gate_ancestry | scripts/vps/gate_ancestry.py | fetch_branch(), find_implementation() — THE gate (TECH-220); `_evaluate_project` writes `gate_via` into the shadow JSONL |
| lifecycle | scripts/vps/lifecycle.py | list_by_status() |
| db | scripts/vps/db.py | log_gate_cycle(), get_all_projects() |
| subprocess | stdlib | git rev-parse origin/develop (SHA cache) |
| logging.handlers | stdlib | RotatingFileHandler (shadow JSONL writer, 100MiB/5 backups) |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| systemd | dld-gate-daemon.service (Wave 2) | main daemon loop |

### When changing API, check

- [ ] setup-vps.sh (Wave 2 service install)
- [ ] gate_logic.py (fetch_develop / parse_allowed_files signatures)
- [ ] gate_ancestry.py (find_implementation / fetch_branch signatures — TECH-220)
- [ ] db.py (log_gate_cycle signature)

---

## scripts/vps/gate_logic.py (ARCH-190 Wave 1)

**Path:** `scripts/vps/gate_logic.py`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| subprocess | stdlib | git fetch origin develop, git log origin/develop |
| re | stdlib | _SPEC_ID_RE, match_subject patterns |
| pathlib | stdlib | Path type for parse_allowed_files |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| gate-daemon.py | scripts/vps/gate-daemon.py | fetch_develop(), parse_allowed_files() directly; find_implementation_commit() only reached indirectly, as gate_ancestry's deprecated subject fallback |
| orchestrator.py | scripts/vps/orchestrator.py | scan_queued reconciliation gate — parse_allowed_files(), fetch_develop() directly; find_implementation_commit() only reached indirectly, as gate_ancestry's deprecated subject fallback |
| gate_ancestry.py | scripts/vps/gate_ancestry.py | strip_bookkeeping_paths() (ancestry diff-intersect) + find_implementation_commit() as the deprecated module-attribute subject fallback (TECH-220) — the sole caller of both now. `callback.py` (TECH-216 split into `callback_sync.py`) does not call `gate_logic` directly any more; it goes through `gate_ancestry.find_implementation`, which tries ancestry first |
| .claude/scripts/validate-allowlist.mjs | `.claude/scripts/validate-allowlist.mjs` | **Not an import — a reimplementation in JS.** Spark's Phase 5.5 pre-flight check must accept exactly what this module accepts, or it rejects specs the pipeline would run. Enforced by `tests/test_allowlist_parity.py` |

### When changing API, check

- [ ] gate-daemon.py (_evaluate_project — fetch_develop/parse_allowed_files call sites)
- [ ] orchestrator.py (scan_queued reconciliation gate — same two functions)
- [ ] gate_ancestry.py (`find_implementation` calls `gate_logic.find_implementation_commit` as a module ATTRIBUTE, positionally, with exactly three args — see that module's docstring; renaming/reordering breaks the subject fallback silently)
- [ ] tests/test_gate_logic.py (pure-function tests, Wave 1 Task 2)
- [ ] `.claude/scripts/validate-allowlist.mjs` + `template/.claude/scripts/` copy — the allowlist regexes are duplicated there in JS; `tests/test_allowlist_parity.py` is the tripwire

---

## scripts/vps/gate_ancestry.py (TECH-220)

**Path:** `scripts/vps/gate_ancestry.py`

THE implementation gate as of TECH-220: `find_implementation(project_path, spec_id, allowed_files)`
returns `(sha, "ancestry")` when `origin/<type>/<ID>` is an ancestor of `origin/develop` and carried
≥1 non-bookkeeping allowed file (`find_merged_branch`), else falls back to the deprecated subject
regex and returns `(sha, "subject")` or `(None, "none")`. Every caller records that `gate_via` on
its audit line — the field that decides when the subject fallback (and `gate_logic.match_subject`/
`find_implementation_commit`) can be deleted.

`branch_state(project_path, spec_id)` (TECH-221) is the second public surface: a read-only,
fail-closed `BranchState(ref, exists, merged, ahead, behind)` verdict on `origin/<type>/<ID>`,
called when `find_implementation` comes back empty to tell "nothing was ever pushed" apart from
"pushed, just not merged yet" (a session salvaged its worktree and died before merge). It never
fetches — every caller already ran `fetch_branch` a few lines earlier — and only ever reads
`refs/remotes/origin/<ref>`, never a local branch (a stale local left by a swept worktree is
exactly the false-positive this exists to avoid).

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| gate_logic.py | scripts/vps/gate_logic.py | `strip_bookkeeping_paths()` (diff-intersect filter) + `find_implementation_commit()` (deprecated subject fallback, called as a module ATTRIBUTE — see module docstring) |
| subprocess | stdlib | every git call funneled through the private `_git` helper, fail-closed (any error/non-zero → `None`) |
| pathlib | stdlib | `SCRIPT_DIR` resolution for the local `sys.path` insert |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| callback_sync.py | scripts/vps/callback_sync.py `_decide_status` | fetch_branch(), find_implementation() — Rule 1 gate + grace-retry loop; branch_state() (TECH-221) — after grace-retry exhausts, turns a no-merge verdict into `blocked:branch_pushed_not_merged:<N> ahead` instead of `no_merged_implementation` when origin carries unmerged commits — demote-to-queued is the right operator response here, force-done is not |
| callback_dispatch.py | scripts/vps/callback_dispatch.py `_merge_confirmed` | fetch_branch(), find_implementation() — gates the QA/Reflect dispatch, same verdict as the status gate |
| orchestrator_queue.py | scripts/vps/orchestrator_queue.py `reconcile` (TECH-221; bool facade `reconcile_if_implemented`, the only name `scan_queued` calls) | fetch_branch(), find_implementation() — pre-dispatch "already on develop" check; branch_state() when nothing is found — distinguishes verdict `"continue"` (origin branch ahead of develop) from `"fresh"` (nothing pushed). `reconcile_if_implemented` sets/clears `CLAUDE_CONTINUE_BRANCH` in `os.environ` as a side effect, ALWAYS written (never only set). Telemetry only — `worktree-setup.md`/`autopilot-git.md` do NOT read this var; they detect continuation independently via `git ls-remote --heads origin <type>/<ID>` |
| orchestrator_queue.py | scripts/vps/orchestrator_queue.py `record_dispatch` | branch_ref_for() — writes the real `<type>/<ID>` branch prefix into `task_log.branch` instead of a hardcoded `feature/` |
| gate-daemon.py | scripts/vps/gate-daemon.py `_evaluate_project` | fetch_branch(), find_implementation() — shadow verdict, same gate as the enforcing callers |

### When changing API, check

- [ ] callback_sync.py, callback_dispatch.py, orchestrator_queue.py, gate-daemon.py (all four `find_implementation` call sites — same 3-arg signature, same `(sha, via)` return shape)
- [ ] `BranchState` field names (TECH-221) — `callback_sync._decide_status` and `orchestrator_queue.reconcile` both read `.exists`/`.ahead`/`.ref` by attribute, not positionally, but the dataclass is frozen and has no version marker; renaming a field breaks both silently until the next dispatch
- [ ] `CLAUDE_CONTINUE_BRANCH` env var (TECH-221) — written/popped in `orchestrator_queue.reconcile_if_implemented`, lands in the pueue dispatch env. NOT currently read by either `worktree-setup.md` or `autopilot-git.md` in either tree — both detect an existing pushed branch independently via `git ls-remote --heads origin <type>/<ID>` and reuse `origin/<type>/<ID>` on that basis alone. If a future change makes the prompts read the flag (or drops the independent git check), this row and the "when changing API" story go stale together — keep them in sync
- [ ] `_BRANCH_PREFIX` map — two prose copies exist and already disagree: `.claude/skills/autopilot/worktree-setup.md` (Type mapping table) and `autopilot-git.md` (bash `case`, falls through to `task/` and has no GROWTH row)
- [ ] `gate_logic.find_implementation_commit` (called positionally, as a module attribute — tests monkeypatch that attribute directly)
- [ ] scripts/vps/tests/test_gate_ancestry.py, scripts/vps/tests/test_orchestrator_in_progress.py (branch_state / reconcile three-way EC-1..EC-6, TECH-221)

---

## scripts/vps/cleanup-lifecycle-drift.sh (TECH-194)

**Path:** `scripts/vps/cleanup-lifecycle-drift.sh`

One-shot operator helper to recover from dirty `ai/lifecycle/` state in a project
(staged/modified/deleted files left over from pre-TECH-194 `env=env` bug in
`lifecycle.py`). HEAD is the canonical SoT — restores WT and unstages.

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| git CLI | PATH | `git status --porcelain ai/lifecycle/`, `git restore --staged`, `git checkout HEAD --` |
| jq | PATH | parse projects.json `.[].path` (iteration mode) |
| projects.json | $PROJECTS_JSON or scripts/vps/projects.json | list of project paths to clean |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| operator | manual | post-TECH-194 cleanup (one-shot or per-project) |

### When changing API, check

- [ ] projects.json schema (jq path stays `.[].path`)
- [ ] lifecycle.py (if SoT layout changes, cleanup paths must update)

---

## scripts/vps/install-lifecycle-guard.sh (2026-07-27)

**Path:** `scripts/vps/install-lifecycle-guard.sh`

**The only hook installer.** Supersedes `install-hooks-all-worktrees.sh` (deleted
2026-07-27), which only rewrote `core.hooksPath` and skipped any repo without a
checked-in `.git-hooks/` — six of the ten orchestrated repos. `setup-vps.sh
--phase4-hooks` now delegates here, so a full setup run cannot undo the install.

Installs one shared wrapper outside the repos, resolves the guard from the repo
first and DLD's copy second, and chains to the repo's own pre-commit when that
hook is executable.

Idempotent. `--dry-run` shows the plan; `--verify` reports effective state only.

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| git CLI | PATH | `config core.hooksPath`, `config dld.previousHooksPath` (rollback breadcrumb) |
| jq | PATH | parse projects.json `.[].path` |
| .claude/hooks/pre-commit-lifecycle-guard.mjs | DLD repo | central guard, baked into the wrapper as an absolute path |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| operator | manual | fleet-wide guard install / re-verify |
| setup-vps.sh | `--phase4-hooks` | delegates entirely — no second installation path exists |

### When changing API, check

- [ ] `.claude/hooks/pre-commit-lifecycle-guard.mjs` (moving it invalidates the baked path — re-run the installer)
- [ ] setup-vps.sh --phase4-hooks (delegates here; keep it a delegation, not a copy)
- [ ] tests/integration/test_worktree_hook_blocks.py (C4 asserts the guard blocks, not that a config value looks right)
- [ ] salvage.py (its plumbing snapshot bypasses this guard by construction — the `ai/lifecycle` exclusion lives there)

---

## scripts/vps/recover_bootstrap_as_done.py (TECH-195)

**Path:** `scripts/vps/recover_bootstrap_as_done.py`

One-shot operator helper that demotes "bootstrap-as-done" lifecycle artifacts
(status=done with empty signature — the silent fingerprint of the pre-TECH-195
positional-regex fall-through). Dry-run by default; `--confirm` executes.
Uses the narrow Rule 7 escape `lifecycle.recover_bootstrap_artifact`.

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| lifecycle | scripts/vps/lifecycle.py | list_by_status(), read_lifecycle(), recover_bootstrap_artifact(), NotBootstrapArtifactError, LifecycleWriteRaceError |
| projects.json | $PROJECTS_JSON or scripts/vps/projects.json | iterate projects |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| operator | manual | post-TECH-195 deploy cleanup (one-shot per VPS) |

### When changing API, check

- [ ] lifecycle.recover_bootstrap_artifact signature (reason/by kwargs)
- [ ] lifecycle.NotBootstrapArtifactError stays exported

---

## scripts/vps/lifecycle_audit.py (TECH-195)

**Path:** `scripts/vps/lifecycle_audit.py`

READ-ONLY multi-project drift detector. 14 categories cover the divergence
surface between lifecycle yaml / spec.md / backlog row / WT / counters.
Used as operator visibility tool and CI smoke gate.

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| lifecycle | scripts/vps/lifecycle.py | read_lifecycle(), LIFECYCLE_DIR (constant) |
| git CLI | PATH | ls-tree (HEAD inventory), status --porcelain (WT dirty), rev-list (divergence) |
| projects.json | $PROJECTS_JSON or scripts/vps/projects.json | iterate projects |
| spec.md files | ai/features/*.md | regex `**Status:**` extraction |
| backlog.md | ai/backlog.md | embedded column-aware parser (mirrors orchestrator._parse_backlog) |
| counter files | ai/.bootstrap-unparsable-count, .bootstrap-anomaly-count, .lifecycle-push-failures | drift signal |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| operator | manual | weekly drift check + post-deploy verification |

### When changing API, check

- [ ] lifecycle.read_lifecycle (signature, return shape)
- [ ] lifecycle.LIFECYCLE_DIR (constant name/value)
- [ ] orchestrator._parse_backlog (keep audit's _parse_backlog_columns in sync if behaviour diverges)

---

## scripts/vps/heartbeat_reaper.py (TECH-198)

**Path:** `scripts/vps/heartbeat_reaper.py`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| subprocess | stdlib | `pueue status --json`, `pueue kill`, `pgrep`, `/proc/*/stat` (CPU sample) |
| event_writer | scripts/vps/event_writer.py | notify() — Hermes alert on reap |
| heartbeat files | scripts/vps/logs/*.heartbeat.json | read `updated_at`, `started_at` for staleness/cross-check |
| json, datetime, pathlib | stdlib | parse heartbeat, ISO timestamps, file paths |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| cron | */5 * * * * | session liveness reaper (installed by setup-vps.sh section 8d) |

### When changing API, check

- [ ] setup-vps.sh (cron line for heartbeat_reaper.py — section 8d)
- [ ] event_writer.notify signature (5-arg: project_path, skill, status, message, artifact_rel)
- [ ] claude-runner.py heartbeat file format (fields: turn, elapsed_s, last_tool, started_at, model, updated_at)

---

## .claude/scripts/ (skill-invoked gates)

**Path:** `.claude/scripts/*.mjs`

Called from skill prompts by a running agent, not imported by any Python module — so a
missing file surfaces as an agent improvising around a shell error, and nothing fails
loudly. Six of these existed only in `template/` while root prompts referenced them
(ported 2026-07-31). The reverse pointers below are the check: **before deleting or
renaming one, grep the skill that calls it.**

| Script | Called from | Contract |
|---|---|---|
| `validate-audit-report.mjs` | `skills/audit/deep-mode.md`, `skills/retrofit/SKILL.md` | argv: report path. 0 = pass, 1 = fail, 2 = usage |
| `validate-audit-coverage.mjs` | `skills/audit/deep-mode.md` | argv: inventory.json + reports dir. 0 = ≥80% covered, 1 = below, 2 = usage |
| `codebase-inventory.mjs` | `skills/audit/deep-mode.md` | argv: target dir. JSON inventory to stdout, feeds the coverage gate |
| `validate-blueprint-compliance.mjs` | `skills/autopilot/task-loop.md` | argv: spec file [+ blueprint dir]. 0 = pass, 1 = fail, 2 = skip/usage |
| `validate-allowlist.mjs` | `skills/spark/feature-mode.md` Phase 5.5 | argv: spec file. 0 = pass, 1 = fix required, 2 = unreadable. Prints one JSON object. **Its regexes must equal `callback._parse_allowed_files_v1` + `gate_logic.strip_bookkeeping_paths`** — `scripts/vps/tests/test_allowlist_parity.py` fails if they diverge. Editing the parser without editing this script is the drift that test exists to catch |
| `run-eval.mjs` | `skills/skill-creator/SKILL.md` | shells out to `claude --print --setting-sources=project -p "/<skill> …"`. Drops `--setting-sources` and every eval silently measures nothing |
| `aggregate-benchmark.mjs` | `skills/skill-creator/SKILL.md`, `skills/skill-creator/references/schemas.md` | argv: workspace. Consumes `iteration-N/run-summary.json` written by `run-eval.mjs` — the two share that filename as a contract |
| `eval-agents.mjs` | `skills/eval` | Root-only. Scans `test/agents/` golden datasets; unrelated to `run-eval.mjs` despite the name |
| `check-prompt-integrity.mjs` | CI (`.github/workflows/ci.yml` → `prompt-integrity`), manual | argv: `--tree <dir> [--root <dir>] [--json]`. 0 = clean, 1 = findings, 2 = usage. Finds agents nothing dispatches, scripts a prompt tells an agent to *run* that do not exist, unresolved `@`-includes, and agents whose `model:`/`effort:` is unstated. Suppressions live in `prompt-integrity-baseline.json` **with a reason** — the whole point is that a green run means something. Reporting, not blocking |

### When changing API, check

- [ ] The calling skill prompt (both `.claude/` and `template/.claude/` copies — they are identical today)
- [ ] `run-eval.mjs` ↔ `aggregate-benchmark.mjs` workspace layout (`iteration-N/run-summary.json`, `eval-N-timing.json`)
- [ ] `codebase-inventory.mjs` ↔ `validate-audit-coverage.mjs` (the latter parses the former's `files[].path`)

---

## scripts/ (agent-invoked quality gates)

Plain `scripts/*.py`, run by an agent from a prompt — same failure mode as
`.claude/scripts/`: a missing file surfaces as the agent improvising around a shell
error, never as a loud failure. Two of these were referenced by prompts for months
before they existed (found 2026-08-01 by `check-prompt-integrity.mjs`), which is why
this section exists at all. **Before renaming or deleting one, grep the prompt that
calls it.** Each ships in `template/scripts/` too.

| Script | Called from | Contract |
|---|---|---|
| `pre-review-check.py` | `skills/autopilot/task-loop.md` Step 3a | argv: changed files (or stdin). 0 = pass, 1 = issues. TODO/FIXME, bare `except`, LOC limits |
| `check_domain_imports.py` | `agents/review.md` §6, `agents/architect/evolutionary.md`, `agents/architect/synthesizer.md` | argv: files, or whole `src/`. `--src`, `--json`. 0 = pass **or no source root**, 1 = violations, 2 = usage. Enforces `shared → infra → domains → api` + no cross-domain imports, via ast |
| `check_docs_sync.py` | `agents/review.md` §5 | argv: files, or whole tree. `--env`, `--all`, `--json`. 0 = pass **or no env template**, 1 = env vars read by code but absent from `.env.example` |
| `check-tree-sync.py` | manual; `rules/template-sync.md` | no argv. 0 = clean **or unavailable**, 1 = drift, 2 = graph unreadable. Reads function spans from the `codebase-memory` graph and compares the bodies across `.claude/` and `template/.claude/`. Root-only — needs two trees. Depends on `.cbmignore` un-skipping them; without it the check reports UNAVAILABLE rather than a false clean |

Both new checks exit 0 when they do not apply — DLD itself has no `src/` and no
`.env.example`. A gate that fails where it is inapplicable gets switched off everywhere,
which is worse than not having it.

### When changing API, check

- [ ] The calling prompt in **both** trees (`.claude/agents/…` and `template/.claude/agents/…`)
- [ ] `tests/unit/test_check_domain_imports.py`, `tests/unit/test_check_docs_sync.py`
- [ ] `template/scripts/` copy stays in sync — the prompts in both trees name the same path

---

## Last Update

История изменений (changelog) вынесена в `docs/dependencies-changelog.md` — этот путь
не попадает под `paths:` выше и не грузится автоматически в контекст сессии. Ничего не
потеряно, только перенесено. Новые записи дописывать туда, а не сюда.
