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
| schema.sql | scripts/vps/schema.sql | project_state, compute_slots, task_log, night_findings |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| telegram-bot.py | scripts/vps/telegram-bot.py (FTR-146 Task 3) | get_project_by_topic(), update_project_phase() |
| notify.py | scripts/vps/notify.py (FTR-146 Task 5) | get_project_state(), finish_task() |
| orchestrate.sh | scripts/vps/orchestrate.sh (FTR-146 Task 4) | try_acquire_slot(), release_slot() via db_exec.sh |
| pueue-callback.sh | scripts/vps/pueue-callback.sh | CLI: python3 db.py callback (release_slot, finish_task, update_project_phase) |
| night-reviewer.sh | scripts/vps/night-reviewer.sh (FTR-147 Task 4) | CLI: save-finding, get-new-findings, update-phase |
| approve_handler.py | scripts/vps/approve_handler.py (FTR-147 Task 5) | update_finding_status(), get_finding_by_id(), get_all_findings() |

### When changing API, check

- [ ] telegram-bot.py
- [ ] notify.py
- [ ] orchestrate.sh
- [ ] night-reviewer.sh (CLI: save-finding / get-new-findings / update-phase)
- [ ] approve_handler.py (update_finding_status, get_finding_by_id, get_all_findings)

---

## scripts/vps/run-agent.sh (provider dispatcher)

**Path:** `scripts/vps/run-agent.sh`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| claude-runner.sh | scripts/vps/claude-runner.sh | exec dispatch |
| codex-runner.sh | scripts/vps/codex-runner.sh | exec dispatch |
| /proc/meminfo | Linux kernel | RAM floor gate (3GB check) |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| Pueue daemon | pueue.yml callback config | task execution |
| orchestrate.sh | scripts/vps/orchestrate.sh (FTR-146 Task 6) | pueue add invocation |

### When changing API, check

- [ ] orchestrate.sh (pueue add arg order)
- [ ] pueue-callback.sh (label format)

---

## scripts/vps/claude-runner.sh

**Path:** `scripts/vps/claude-runner.sh`

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

## scripts/vps/pueue-callback.sh

**Path:** `scripts/vps/pueue-callback.sh`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| db.py | scripts/vps/db.py | python3 db.py callback (parameterized SQL via release_slot, finish_task, update_project_phase) |
| notify.py | scripts/vps/notify.py | send Telegram notification by project_id |
| openclaw CLI | ${HOME}/.npm-global/bin/openclaw | system event --mode now (immediate wake after pending-event write) |
| pueue CLI | PATH | pueue log (optional summary) |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| Pueue daemon | pueue.yml callback config | fires on task completion/failure |

### When changing API, check

- [ ] pueue.yml callback config (arg order: id label group result)
- [ ] run-agent.sh (label format "project_id:SPEC-ID" must stay consistent)
- [ ] schema.sql (compute_slots, task_log, project_state column names)

---

## scripts/vps/telegram-bot.py

**Path:** `scripts/vps/telegram-bot.py`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| db.py | scripts/vps/db.py | get_project_by_topic(), get_project_state(), get_all_projects(), update_project_phase(), get_available_slots() |
| pueue CLI | PATH | pueue status --json, pueue add --group, pueue pause --group, pueue start --group |
| run-agent.sh | scripts/vps/run-agent.sh | invoked via pueue add for autopilot dispatch |
| python-telegram-bot v21.9+ | pip | Application, CommandHandler, MessageHandler, CallbackQueryHandler, InlineKeyboardMarkup |
| photo_handler.py | scripts/vps/photo_handler.py | handle_photo — PHOTO MessageHandler |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| systemd | dld-telegram-bot.service | main() — runs as service |
| inbox-processor.sh / orchestrator | external | auto_approve_start() — called after spec creation |

### When changing API, check

- [ ] notify.py (shares same env vars: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
- [ ] db.py (get_project_by_topic, get_project_state signatures)
- [ ] auto_approve_start() signature (project_id, task_id, summary, scope, topic_id, context)

---

## scripts/vps/notify.py

**Path:** `scripts/vps/notify.py`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| db.py | scripts/vps/db.py | get_project_state() — topic_id lookup |
| python-telegram-bot | pip | Bot.send_message() |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| pueue-callback.sh | scripts/vps/pueue-callback.sh | python3 notify.py <project_id> <message> |
| orchestrator.sh | scripts/vps/orchestrator.sh (Task 6) | completion notifications |
| qa-loop.sh | scripts/vps/qa-loop.sh (Task 8) | QA result notifications |

### When changing API, check

- [ ] pueue-callback.sh (CLI: python3 notify.py <project_id> <msg>)
- [ ] orchestrator.sh, qa-loop.sh (same CLI interface)

---

## scripts/vps/inbox-processor.sh

**Path:** `scripts/vps/inbox-processor.sh`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| db.py | scripts/vps/db.py | get_project_state(), log_task(), update_project_phase() |
| run-agent.sh | scripts/vps/run-agent.sh | pueue add dispatch (project_dir, task_cmd, provider, skill) |
| notify.py | scripts/vps/notify.py | send_to_project() — pre-dispatch Telegram notification |
| pueue CLI | PATH | pueue add --group --label --print-task-id |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| orchestrator.sh | scripts/vps/orchestrator.sh (FTR-146 Task 6) | per-file inbox scan |

### When changing API, check

- [ ] orchestrator.sh (arg order: project_id project_dir inbox_file)
- [ ] run-agent.sh (arg order: project_dir task provider skill)
- [ ] db.py (log_task, update_project_phase signatures)
- [ ] notify.py (CLI: python3 notify.py <project_id> <msg>)

---

## scripts/vps/orchestrator.sh

**Path:** `scripts/vps/orchestrator.sh`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| db.py | scripts/vps/db.py | seed_projects_from_json(), get_all_projects(), get_project_state(), get_available_slots(), try_acquire_slot(), log_task(), update_project_phase() |
| inbox-processor.sh | scripts/vps/inbox-processor.sh | per-file inbox dispatch (project_id, project_dir, inbox_file) |
| run-agent.sh | scripts/vps/run-agent.sh | pueue add autopilot dispatch (project_dir, task_cmd, provider, skill) |
| qa-loop.sh | scripts/vps/qa-loop.sh | QA dispatch when phase=qa_pending (Task 8) |
| night-reviewer.sh | scripts/vps/night-reviewer.sh | pueue add --group night-reviewer (dispatch_night_review) |
| pueue CLI | PATH | pueue add --group --label --print-task-id |
| git CLI | PATH | git -C <dir> pull --ff-only origin develop |
| projects.json | PROJECTS_JSON env | hot-reload project list each cycle |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| systemd | dld-orchestrator.service | main daemon loop (Task 9) |
| telegram-bot.py | scripts/vps/telegram-bot.py | /run command creates .run-now-{id} trigger file |

### When changing API, check

- [ ] qa-loop.sh (arg order: project_id project_dir current_task)
- [ ] inbox-processor.sh (arg order: project_id project_dir inbox_file)
- [ ] run-agent.sh (arg order: project_dir task provider skill)
- [ ] night-reviewer.sh (pueue add arg order: space-separated project IDs)
- [ ] db.py (get_all_projects, try_acquire_slot, log_task, update_project_phase signatures)
- [ ] telegram-bot.py (/run command uses .run-now-{project_id} convention)

---

## scripts/vps/night-reviewer.sh

**Path:** `scripts/vps/night-reviewer.sh`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| db.py | scripts/vps/db.py | get_project_state() (inline python3 -c), update-phase, save-finding, get-new-findings (CLI) |
| notify.py | scripts/vps/notify.py | python3 notify.py <project_id> <msg> |
| claude CLI | $CLAUDE_PATH or PATH | flock --timeout 120 /tmp/claude-oauth.lock claude --print --output-format json --max-turns 30 --cwd <path> -p "/audit night" |
| flock | util-linux | serialize claude OAuth token access |
| jq | PATH | parse claude JSON output (.result field + findings array) |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| orchestrator.sh | scripts/vps/orchestrator.sh:256 | dispatch_night_review() — pueue add --group night-reviewer |
| pueue daemon | night-reviewer group | task execution |

### When changing API, check

- [ ] orchestrator.sh dispatch_night_review() (arg order: space-separated project IDs)
- [ ] db.py (save_finding, get_new_findings, update_project_phase signatures)
- [ ] notify.py (CLI: python3 notify.py <project_id> <msg>)

---

## scripts/vps/qa-loop.sh

**Path:** `scripts/vps/qa-loop.sh`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| db_exec.sh | scripts/vps/db_exec.sh | UPDATE project_state (phase transitions: qa_running, idle, qa_failed) |
| notify.py | scripts/vps/notify.py | python3 notify.py <project_id> <msg> |
| claude CLI | $CLAUDE_PATH or PATH | --print --output-format json --max-turns 15 -p "/qa SPEC_ID" |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| orchestrator.sh | scripts/vps/orchestrator.sh:267 | dispatch_qa() — background call when phase=qa_pending |

### When changing API, check

- [ ] orchestrator.sh dispatch_qa() (arg order: project_id project_dir spec_id)
- [ ] db_exec.sh (SQL phase values: qa_running, idle, qa_failed)
- [ ] notify.py CLI interface

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
| pueue-callback.sh | scripts/vps/pueue-callback.sh | registered in pueue.yml callback |
| orchestrator.sh | scripts/vps/orchestrator.sh | ExecStart in dld-orchestrator.service |
| telegram-bot.py | scripts/vps/telegram-bot.py | ExecStart in dld-telegram-bot.service |
| .env | scripts/vps/.env | EnvironmentFile in both systemd units |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| operator | manual | one-command VPS bootstrap |
| systemd | generated units | ExecStart paths reference SCRIPT_DIR |

### When changing API, check

- [ ] pueue-callback.sh (callback arg order must match pueue.yml template)
- [ ] orchestrator.sh (ExecStart path in dld-orchestrator.service)
- [ ] telegram-bot.py (ExecStart path in dld-telegram-bot.service)

---

## scripts/vps/photo_handler.py

**Path:** `scripts/vps/photo_handler.py`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| db.py | scripts/vps/db.py | get_project_by_topic() |
| telegram-bot.py | scripts/vps/telegram-bot.py (via sys.modules) | is_authorized(), get_topic_id(), detect_route() |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| telegram-bot.py | scripts/vps/telegram-bot.py:44,406 | handle_photo registered as PHOTO & SUPERGROUP MessageHandler |

### When changing API, check

- [ ] telegram-bot.py (handle_photo import at line 44, handler at line 406)

---

## scripts/vps/voice_handler.py

**Path:** `scripts/vps/voice_handler.py`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| groq SDK | pip | Groq.audio.transcriptions.create() |
| db.py | scripts/vps/db.py | get_project_by_topic() |
| telegram-bot.py | scripts/vps/telegram-bot.py (via sys.modules) | is_authorized(), get_topic_id(), _save_to_inbox() |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| telegram-bot.py | scripts/vps/telegram-bot.py:30,369 | handle_voice registered as VOICE & SUPERGROUP MessageHandler |

### When changing API, check

- [ ] telegram-bot.py (handle_voice import at line 30, handler at line 369)

---

## scripts/vps/approve_handler.py

**Path:** `scripts/vps/approve_handler.py`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| db.py | scripts/vps/db.py | get_all_projects(), get_finding_by_id(), update_finding_status(), get_all_findings(), get_project_state(), get_project_by_topic() |
| telegram-bot.py | scripts/vps/telegram-bot.py (via sys.modules) | _submit_to_pueue(), get_topic_id() |
| python-telegram-bot | pip | InlineKeyboardButton, InlineKeyboardMarkup, CallbackQueryHandler |
| zoneinfo | stdlib Python 3.9+ | ZoneInfo — timezone for run_daily |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| telegram-bot.py | scripts/vps/telegram-bot.py:30-40,380-391 | all 7 handlers + register_evening_job() |

### When changing API, check

- [ ] telegram-bot.py (imports at lines 30-39, handler registrations at lines 380-386)
- [ ] db.py (get_all_findings status param, update_finding_status, get_finding_by_id)

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

## scripts/vps/admin_handler.py

**Path:** `scripts/vps/admin_handler.py`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| db.py | scripts/vps/db.py | add_project(), get_project_state(), get_project_by_topic() |
| pueue CLI | PATH | pueue group add, pueue parallel |
| nexus-cache-refresh.sh | scripts/vps/nexus-cache-refresh.sh | subprocess call on confirm + /nexussync |
| python-telegram-bot | pip | ConversationHandler, InlineKeyboardButton/Markup, CallbackQueryHandler |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| telegram-bot.py | scripts/vps/telegram-bot.py:30,383-384 | create_addproject_handler() + cmd_nexussync |

### When changing API, check

- [ ] telegram-bot.py (import + handler registration)
- [ ] db.py (add_project, get_project_state, get_project_by_topic signatures)

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
| admin_handler.py | scripts/vps/admin_handler.py | subprocess on /nexussync + /addproject confirm |
| setup-vps.sh | scripts/vps/setup-vps.sh (--phase3) | cron installation |

### When changing API, check

- [ ] admin_handler.py (subprocess call path)
- [ ] setup-vps.sh --phase3 (cron line)

---

## Last Update

| Date | What | Who |
|------|------|-----|
| 2026-03-10 | Added scripts/vps/db module (FTR-146 Task 1) | coder |
| 2026-03-10 | Added run-agent.sh, claude-runner.sh, codex-runner.sh (FTR-146 Task 2) | coder |
| 2026-03-10 | Added pueue-callback.sh (FTR-146 Task 3) | coder |
| 2026-03-10 | Fix SQL injection + duplication in pueue-callback.sh (FTR-146 Task 3 review) | coder |
| 2026-03-10 | Added telegram-bot.py, notify.py, requirements.txt (FTR-146 Task 4) | coder |
| 2026-03-10 | Fix 4 code review issues in telegram-bot.py + notify.py (FTR-146 Task 4 review) | coder |
| 2026-03-10 | Added voice_handler.py (FTR-147 Task 2) | coder |
| 2026-03-10 | Added inbox-processor.sh (FTR-146 Task 5) | coder |
| 2026-03-10 | Added orchestrator.sh (FTR-146 Task 6) | coder |
| 2026-03-10 | Added auto-approve flow to telegram-bot.py (FTR-146 Task 7) | coder |
| 2026-03-10 | Added qa-loop.sh (FTR-146 Task 8) | coder |
| 2026-03-10 | Added setup-vps.sh, .env.example, projects.json.example (FTR-146 Task 9) | coder |
| 2026-03-10 | Extended db.py + schema.sql: night_findings table + 6 CRUD functions (FTR-147 Task 1) | coder |
| 2026-03-10 | Added night-reviewer.sh + dispatch_night_review() in orchestrator.sh (FTR-147 Task 4) | coder |
| 2026-03-10 | Added approve_handler.py + evening prompt + approve/reject handlers (FTR-147 Task 5) | coder |
| 2026-03-10 | Added gemini-runner.sh, admin_handler.py, nexus-cache-refresh.sh (FTR-148) | coder |
| 2026-03-12 | Added photo_handler.py + registered PHOTO handler in telegram-bot.py | coder |
| 2026-03-18 | Added openclaw CLI dependency to pueue-callback.sh (TECH-157) | coder |
