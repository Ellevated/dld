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

**Path:** `scripts/vps/db.py`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| sqlite3 | stdlib | connection, Row, contextmanager |
| schema.sql | scripts/vps/schema.sql | project_state, compute_slots, task_log, night_findings, callback_decisions |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| orchestrator.py | scripts/vps/orchestrator.py | seed_projects_from_json(), get_all_projects(), get_project_state(), try_acquire_slot(), log_task(), update_project_phase() |
| callback.py | scripts/vps/callback.py | release_slot(), finish_task(), update_project_phase(), get_project_state() |
| callback.py | scripts/vps/callback.py | record_decision(), count_demotes_since(), clear_decisions() (TECH-169) |
| night-reviewer.sh | scripts/vps/night-reviewer.sh (FTR-147 Task 4) | CLI: save-finding, get-new-findings, update-phase |
| claude-runner.py | scripts/vps/claude-runner.py | log_sdk_post_result_error() (BUG-188 Layer 4, lazy import) |
| gate-daemon.py | scripts/vps/gate-daemon.py | log_gate_cycle(), get_all_projects() (ARCH-190) |

### When changing API, check

- [ ] orchestrator.py
- [ ] callback.py
- [ ] night-reviewer.sh (CLI: save-finding / get-new-findings / update-phase)
- [ ] claude-runner.py (log_sdk_post_result_error signature — BUG-188)
- [ ] gate-daemon.py (log_gate_cycle signature — ARCH-190)

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

**Path:** `scripts/vps/claude-runner.py`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| claude CLI | $CLAUDE_PATH or PATH | --print --output-format json --max-turns 30 |
| claude_agent_sdk | pip dep 0.1.63 | query(), ClaudeAgentOptions(stderr=callback) (BUG-188 Layer 2) |
| db.py | scripts/vps/db.py | log_sdk_post_result_error() — telemetry on post-result SDK exception (BUG-188 Layer 4, lazy import) |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| run-agent.sh | scripts/vps/run-agent.sh:47 | exec dispatch (provider=claude) |
| heartbeat_reaper.py | scripts/vps/heartbeat_reaper.py | reads logs/*.heartbeat.json files written by _write_heartbeat (TECH-198) |

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

**Path:** `scripts/vps/orchestrator.py`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| db.py | scripts/vps/db.py | seed_projects_from_json(), get_all_projects(), get_project_state(), get_available_slots(), try_acquire_slot(), log_task(), update_project_phase() |
| run-agent.sh | scripts/vps/run-agent.sh | pueue add autopilot + inbox dispatch (CLAUDE_CURRENT_SPEC_PATH env for both, BUG-199) |
| night-reviewer.sh | scripts/vps/night-reviewer.sh | pueue add --group night-reviewer (dispatch_night_review) |
| pueue CLI | PATH | pueue add --group --label --print-task-id |
| git CLI | PATH | git -C <dir> pull --ff-only origin develop |
| projects.json | PROJECTS_JSON env | hot-reload project list each cycle |
| lifecycle.py | scripts/vps/lifecycle.py | list_by_status(), read_lifecycle(), create_initial(), write_lifecycle() — reconciliation gate marks done by="orchestrator" |
| gate_logic.py | scripts/vps/gate_logic.py | parse_allowed_files(), fetch_develop(), find_implementation_commit() — scan_queued reconciliation gate (pre-dispatch "already on develop" check) |

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

**Path:** `scripts/vps/callback.py`

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
| claude CLI | $CLAUDE_PATH or PATH | flock --timeout 120 /tmp/claude-oauth.lock claude --print --output-format json --max-turns 30 --cwd <path> -p "/audit night" |
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
| gate_logic | scripts/vps/gate_logic.py | fetch_develop(), parse_allowed_files(), find_implementation_commit() |
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
- [ ] gate_logic.py (fetch_develop / parse_allowed_files / find_implementation_commit signatures)
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
| gate-daemon.py | scripts/vps/gate-daemon.py | fetch_develop(), parse_allowed_files(), find_implementation_commit() |
| orchestrator.py | scripts/vps/orchestrator.py | scan_queued reconciliation gate — parse_allowed_files(), fetch_develop(), find_implementation_commit() before dispatch |

### When changing API, check

- [ ] gate-daemon.py (_evaluate_project — all three call sites)
- [ ] orchestrator.py (scan_queued reconciliation gate — same three functions)
- [ ] tests/test_gate_logic.py (pure-function tests, Wave 1 Task 2)

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

## scripts/vps/install-hooks-all-worktrees.sh (TECH-194 Layer C migration)

**Path:** `scripts/vps/install-hooks-all-worktrees.sh`

Migration helper that converts relative `core.hooksPath = .git-hooks` (broken in
worktrees — resolves relative to `.git/worktrees/<name>/` instead of repo root)
to absolute paths per project. Idempotent.

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| git CLI | PATH | `git -C <path> config core.hooksPath <absolute>` |
| jq | PATH | parse projects.json `.[].path` |
| projects.json | $PROJECTS_JSON or scripts/vps/projects.json | iterate project paths |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| operator | manual | one-shot Layer C migration on existing VPS deployments |
| setup-vps.sh | new VPS setup (--phase4-hooks) | covers new projects natively; this helper covers backfill |

### When changing API, check

- [ ] setup-vps.sh --phase4-hooks (must produce identical absolute hooksPath value)
- [ ] .git-hooks/pre-commit (GIT_COMMON_DIR resolution depends on absolute hooksPath)

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

## Last Update

| Date | What | Who |
|------|------|-----|
| 2026-03-10 | Added scripts/vps/db module (FTR-146 Task 1) | coder |
| 2026-03-10 | Added run-agent.sh, codex-runner.sh (FTR-146 Task 2) | coder |
| 2026-03-10 | Added setup-vps.sh, .env.example, projects.json.example (FTR-146 Task 9) | coder |
| 2026-03-10 | Extended db.py + schema.sql: night_findings table + 6 CRUD functions (FTR-147 Task 1) | coder |
| 2026-03-10 | Added night-reviewer.sh (FTR-147 Task 4) | coder |
| 2026-03-10 | Added gemini-runner.sh, nexus-cache-refresh.sh (FTR-148) | coder |
| 2026-03-18 | Radical rewrite: orchestrator.py, callback.py, event_writer.py replace bash scripts (ARCH-161) | coder |
| 2026-03-19 | Orphan slot watchdog: get_occupied_slots (db.py), get_live_pueue_ids + release_orphan_slots (orchestrator.py) (BUG-162) | coder |
| 2026-03-28 | callback.py: QA/Reflect slot+log, phase fix, spark events, resolve_label dedup | manual |
| 2026-03-28 | callback.py: verify_status_sync — auto-fix spec+backlog status after autopilot | manual |
| 2026-05-02 | callback circuit-breaker (TECH-169): callback_decisions table, record_decision/count_demotes_since/clear_decisions (db.py), notify_circuit_event (event_writer.py), --reset-circuit CLI (callback.py) | autopilot |
| 2026-05-04 | Spark spec template: DLD-CALLBACK-MARKER-START/END wraps Status + Allowed Files; Phase 5.5 SSOT extended with DLD_START_RE/DLD_END_RE + E007/E008 (TECH-175 Task 3) | coder |
| 2026-05-15 | marker_utils.py shared regex/extractor; orchestrator autostash recovery restores callback Status from HEAD post-pop (BUG-185, formerly BUG-974) | autopilot |
| 2026-05-16 | **ARCH-186 lifecycle SoT migration:** lifecycle.py (new, ~280 LOC) atomic git plumbing; callback.verify_status_sync upgraded to lifecycle.write_lifecycle (no markdown editing); orchestrator scan_queued + bootstrap_new_specs + assert_clean_lifecycle_tree + reconcile_orphans; render_backlog.py (new) markdown view; migrate_backlog_to_lifecycle.py (new, one-shot). DELETED: marker_utils.py (117), _restore_callback_markers_from_head (54), autostash dance (81), DLD-CALLBACK-MARKER blocks in spec template + Phase 5.5 E007/E008 rules. Supersedes ADR-018. Closes BUG-185. | autopilot (interactive) |
| 2026-05-23 | **TECH-189 P0 hardening cluster (9 tasks):** Task 1 pyproject testpaths += scripts/vps/tests; Task 2 tests/conftest.py autouse _db_isolation; Task 3 DELETED spec_lint.py + tests/unit/test_spec_lint.py + removed DLD-CALLBACK-MARKER refs across completion.md ×2, facilitator.md, .git-hooks/pre-commit, feature-mode.md ×2; Task 4 BOOTSTRAP_ANOMALY_THRESHOLD constant + warning + ai/.bootstrap-anomaly-count counter + Hermes event; Task 5 lifecycle._push_best_effort DEBUG→WARNING + ai/.lifecycle-push-failures counter + TimeoutExpired path; Task 6 GROWTH in _SPEC_ID_RE (callback) + bootstrap_new_specs regex (orchestrator:308); Task 7 lifecycle._run timeout=30 + _cas_loop TimeoutExpired catch; Task 8 NEW scripts/vps/heartbeat_monitor.py + orchestrator main-loop heartbeat write + setup-vps.sh cron (*/5 min); Task 9 reconcile_orphans by="orchestrator" (was "callback"). | autopilot |
| 2026-05-20 | **BUG-188:** claude-runner result_received/result_is_error tracking — post-result Exception no longer overrides exit_code=0 (Layer 1); public ClaudeAgentOptions.stderr callback captures subprocess CLI stderr (Layer 2); sdk_post_result_errors table + log_sdk_post_result_error helper (schema.sql + db.py, Layer 4); claude-runner wires telemetry inside post-result branch; autopilot SKILL.md adds early-exit detection step (Layer 3, both .claude/ and template/.claude/); ADR-024 documents exit_code contract. | autopilot |
| 2026-05-24 | **ARCH-190 Task 3:** NEW gate-daemon.py (391 LOC) shadow polling daemon; NEW gate_logic.py dependency sections added to dependencies.md. | coder |
| 2026-05-24 | **ARCH-190 Task 4:** setup-vps.sh — install dld-gate-daemon.service user-unit (HEREDOC + loginctl enable-linger + systemctl --user enable --now); setup-vps.sh Uses updated with gate-daemon.py entry. | coder |
| 2026-05-24 | **ARCH-190 Task 5:** NEW tests/test_gate_logic.py (410 LOC) — 24 pure-function tests covering DA-1, DA-4, DA-5, DA-6, DA-9 + parse_allowed_files v1/legacy + match_subject 3 forms + fetch_develop timeout. Real git repos via subprocess + tmp_path (ADR-013). | coder |
| 2026-05-24 | **ARCH-190 Task 6:** NEW tests/test_gate_daemon.py (515 LOC) — 8 integration tests covering SA-3 lifecycle-never-touched, SHADOW_ONLY_MODE guard, gate_health row, JSONL line count, per-project error isolation, SHA cache spy, heartbeat mtime, SIGTERM graceful exit. | coder |
| 2026-05-24 | **ARCH-190 Task 7 (Wave 1 complete):** dependency map consolidated — gate-daemon.py + gate_logic.py sections; reverse-pointer rows added to db.py, lifecycle.py, setup-vps.sh sections. Shadow daemon ready for VPS deploy (Wave 2 parity check next). | autopilot |
| 2026-05-26 | **TECH-195:** orchestrator._parse_backlog column-aware parser + safe default=queued (was: positional regex falling through to done); lifecycle.recover_bootstrap_artifact narrow Rule 7 escape + NotBootstrapArtifactError; NEW scripts/vps/recover_bootstrap_as_done.py operator helper (dry-run default); NEW scripts/vps/lifecycle_audit.py READ-ONLY 14-category drift detector; ADR-026 architecture.md; lifecycle.py reverse-pointers extended. +12 tests (recovery) + 12 tests (audit) in scripts/vps/tests/test_orchestrator_bootstrap.py (39 in file, 212 total). | autopilot |
| 2026-05-28 | NEW scripts/vps/orchestrator_monitor.py — 30-min cron: service alive + CB state + active tasks + demote burst; setup-vps.sh section 8c. | manual |
| 2026-05-26 | **TECH-194 (ARCH-193 follow-up):** Layer C — setup-vps.sh `core.hooksPath` absolute + `install-hooks-all-worktrees.sh` migration + `.git-hooks/pre-commit` uses `git rev-parse --git-common-dir` + `pre-commit-lifecycle-guard.mjs` resolves `event_writer.py` via `import.meta.url`; Layer D — `lifecycle._atomic_write` + `_atomic_write_file` use `git checkout HEAD --` (was `checkout-index --force` losing `env=env`); Layer E — callback Step 6 gates qa+reflect dispatch on `task_status not in ('blocked','needs_review')`; NEW `cleanup-lifecycle-drift.sh` operator helper; 11 new regression tests across 3 files. | autopilot |
| 2026-06-13 | **TECH-198:** Layer A: claude-runner heartbeat on every SDK message (was AssistantMessage-only). Layer B: NEW heartbeat_reaper.py (cron */5, kills wedged sessions: stale >25min + process idle + fail-open). setup-vps.sh section 8d cron install. 27 tests (5 Layer A + 22 Layer B). dependencies.md reaper section + reverse-pointers (claude-runner, event_writer, setup-vps). | autopilot |
| 2026-06-19 | **TECH-203:** claude-runner.py: AUTOPILOT_EFFORT env (default high, enum-validated) + ClaudeAgentOptions(effort=...). model-capabilities.md table synced to frontmatter SSOT. ADR-028 added. 9 template agent files synced to ADR-019 frontmatter. | autopilot |
| 2026-06-19 | **BUG-205:** scan_queued authoritative lifecycle re-read before _pueue_add (TOCTOU close). 5 regression tests in test_orchestrator.py (stale-block, happy-path, read-None, stale-done, resumed). | autopilot |
| 2026-06-26 | **scan_queued reconciliation gate:** orchestrator.py imports gate_logic; before _pueue_add checks `find_implementation_commit` on origin/develop and, if already implemented, writes done by="orchestrator" (no session). Closes single-writer hole (ADR-023) for out-of-band completion (other dev/window/node, callback never fired). 3 regression tests (TestReconciliationGate). dependencies.md orchestrator Uses += lifecycle/gate_logic + gate_logic reverse-pointer. | interactive |
