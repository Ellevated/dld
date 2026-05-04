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

### When changing API, check

- [ ] orchestrator.py
- [ ] callback.py
- [ ] night-reviewer.sh (CLI: save-finding / get-new-findings / update-phase)

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

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| run-agent.sh | scripts/vps/run-agent.sh:47 | exec dispatch (provider=claude) |

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
| run-agent.sh | scripts/vps/run-agent.sh | pueue add autopilot + inbox dispatch |
| night-reviewer.sh | scripts/vps/night-reviewer.sh | pueue add --group night-reviewer (dispatch_night_review) |
| pueue CLI | PATH | pueue add --group --label --print-task-id |
| git CLI | PATH | git -C <dir> pull --ff-only origin develop |
| projects.json | PROJECTS_JSON env | hot-reload project list each cycle |

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
| event_writer.py | scripts/vps/event_writer.py | notify() — send OpenClaw event |
| event_writer.py | scripts/vps/event_writer.py | notify_circuit_event() (TECH-169) |
| run-agent.sh | scripts/vps/run-agent.sh | pueue add for QA/Reflect dispatch |
| pueue CLI | PATH | pueue status --json, pueue log --json, pueue add |
| pueue CLI | PATH | pueue pause/start --group claude-runner (TECH-169 circuit) |
| spec files | ai/features/{SPEC_ID}*.md | verify_status_sync() reads/fixes **Status:** field |
| backlog.md | ai/backlog.md | verify_status_sync() reads/fixes status column |
| git CLI | PATH | _git_commit_push() — auto-fix commit + push to develop |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| Pueue daemon | pueue.yml callback config | fires on task completion/failure |

### When changing API, check

- [ ] pueue.yml (arg order: id group result)
- [ ] run-agent.sh (arg order: project_dir task provider skill)
- [ ] event_writer.py (notify signature)
- [ ] schema.sql (compute_slots, task_log, project_state column names)
- [ ] ai/features/ spec files (verify_status_sync reads **Status:** field format)
- [ ] ai/backlog.md (verify_status_sync reads status column in markdown table)

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

### When changing API, check

- [ ] callback.py (notify import)
- [ ] night-reviewer.sh (CLI arg order)

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
| .env | scripts/vps/.env | EnvironmentFile in systemd unit |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| operator | manual | one-command VPS bootstrap |
| systemd | generated units | ExecStart paths reference SCRIPT_DIR |

### When changing API, check

- [ ] callback.py (callback arg order must match pueue.yml template)
- [ ] orchestrator.py (ExecStart path in dld-orchestrator.service)

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
