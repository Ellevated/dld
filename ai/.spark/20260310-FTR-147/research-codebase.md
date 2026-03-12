# Codebase Research — FTR-147 Multi-Project Orchestrator Phase 2: Architecture & Reliability

## Existing Code

### Reusable Modules

| Module | File:line | Description | Reuse how |
|--------|-----------|-------------|-----------|
| `db.get_project_state` | `.worktrees/FTR-146/scripts/vps/db.py:90` | Returns full project dict by ID | Import directly — read phase before night scan dispatch |
| `db.update_project_phase` | `.worktrees/FTR-146/scripts/vps/db.py:119` | Update project phase + current_task | Import directly — set `night_reviewing` phase |
| `db.get_all_projects` | `.worktrees/FTR-146/scripts/vps/db.py:110` | All enabled projects list | Import directly — iterate for night scan |
| `db.log_task` | `.worktrees/FTR-146/scripts/vps/db.py:130` | Create task_log entry | Import directly — log night scan runs |
| `db.finish_task` | `.worktrees/FTR-146/scripts/vps/db.py:147` | Mark task finished with exit_code | Import directly — track night scan completion |
| `notify.send_to_project` | `.worktrees/FTR-146/scripts/vps/notify.py:53` | Send to project's Telegram topic | Import directly — deliver findings to project topic |
| `notify.send_to_general` | `.worktrees/FTR-146/scripts/vps/notify.py:70` | Send to General topic | Import directly — nightly summary across all projects |
| `audit-coroner` persona | `.claude/agents/audit/coroner.md:1` | Tech debt + security red flags, structured output | Extend — add `night` mode output (individual finding files vs one report) |
| `audit-scout` persona | `.claude/agents/audit/scout.md:1` | External integrations, APIs, secrets | Reuse directly — security persona fits night scan perfectly |
| `bughunt-findings-collector` | `.claude/agents/bug-hunt/findings-collector.md:1` | Normalize per-persona findings into YAML | Pattern — same fan-in logic needed for night findings |
| `run-agent.sh` | `.worktrees/FTR-146/scripts/vps/run-agent.sh:1` | Provider dispatch (claude/codex) | Extend — add `skill=audit` as valid skill value (already parameterized) |
| `claude-runner.sh` | `.worktrees/FTR-146/scripts/vps/claude-runner.sh:1` | `claude --print /skill task` wrapper | Extend — `PROMPT="/${SKILL} ${TASK}"` already supports any skill |
| `qa-loop.sh` (Task 8 — not yet committed) | `FTR-146 spec:2053` | QA dispatch + inbox write-back on fail | Pattern — night-reviewer.sh follows same pattern: run skill → parse output → write findings to inbox |
| `_save_to_inbox` + `detect_route` | `.worktrees/FTR-146/scripts/vps/telegram-bot.py:318` | Save message with metadata + skill routing | Extend — add `voice` route + `groq_stt` pre-processing |
| `handle_text` handler | `.worktrees/FTR-146/scripts/vps/telegram-bot.py:342` | Plain text → inbox | Extend — add `handle_voice` handler alongside |
| `ROUTE_PATTERNS` | `.worktrees/FTR-146/scripts/vps/telegram-bot.py:51` | Keyword routing dict | Extend — add `night_review` and `security_scan` patterns |
| `deep-mode.md` 6-persona protocol | `.claude/skills/audit/deep-mode.md:1` | Phase 0→4 with ADR-007/008/009/010 compliance | Pattern — night scan is a lighter version of this (2-3 personas, no Phase 0 inventory) |

### Similar Patterns

| Pattern | File:line | Description | Similarity |
|---------|-----------|-------------|------------|
| `qa-loop.sh` pattern (FTR-146 Task 8) | `FTR-146 spec:2053` | run skill → check exit → write back to inbox | Night reviewer follows identical control flow |
| `pueue-callback.sh` fail-safe | `.worktrees/FTR-146/scripts/vps/pueue-callback.sh:21` | `set -uo pipefail`, `|| true` everywhere, never exit non-zero | Night reviewer script must follow same fail-safe pattern |
| Bug Hunt findings split | `.claude/agents/bug-hunt/spec-assembler.md` (implicitly) | Per-finding YAML → individual spec files | Night mode needs same: one file per finding, not one big report |
| `task_log` in schema | `.worktrees/FTR-146/scripts/vps/schema.sql:30` | Records every task with status/exit/summary | New `night_findings` table follows same row-per-item structure |
| `autopilot-loop.sh` polling | `scripts/autopilot-loop.sh:88` | `grep queued backlog` → next spec ID | Night scan cron trigger uses same pattern |

**Recommendation:** Reuse `db.py`, `notify.py`, and runner chain as-is. Extend `audit` skill with a new `night` mode (new file: `.claude/skills/audit/night-mode.md`). Model `night-reviewer.sh` on `qa-loop.sh` — same structure. For voice: add `handle_voice` to `telegram-bot.py` using Groq API, Telethon-free (bot already has `filters.VOICE` available via PTB v21.9).

---

## Impact Tree Analysis

### Step 1: UP — Who uses changed code?

```bash
grep -r "from.*db\|import db\|notify\|telegram.bot" .worktrees/FTR-146/scripts/vps/ --include="*.py"
```

| File | Line | Usage |
|------|------|-------|
| `.worktrees/FTR-146/scripts/vps/telegram-bot.py` | 29 | `import db` |
| `.worktrees/FTR-146/scripts/vps/notify.py` | 23 | `import db` |
| `.worktrees/FTR-146/scripts/vps/pueue-callback.sh` | 71 | `python3 db.py callback` |

New Phase 2 consumers of existing modules:
- `night-reviewer.sh` → `db.py` (update_project_phase, log_task, finish_task)
- `night-reviewer.sh` → `notify.py` (send findings summary to project topic)
- `telegram-bot.py` ← Phase 2 adds `handle_voice` + `cmd_approve`/`cmd_reject` handlers

### Step 2: DOWN — What does it depend on?

| Dependency | File | Function |
|------------|------|----------|
| `sqlite3` stdlib | `.worktrees/FTR-146/scripts/vps/db.py:11` | All DB operations |
| `python-telegram-bot v21.9+` | `.worktrees/FTR-146/scripts/vps/requirements.txt:1` | Bot handlers |
| `python-dotenv` | `.worktrees/FTR-146/scripts/vps/requirements.txt:2` | `.env` loading |
| `claude` CLI | `.worktrees/FTR-146/scripts/vps/claude-runner.sh:12` | `--print /skill task` |
| `pueue` v4.0.4+ | `FTR-146 spec` | group-based parallelism |
| `orchestrator.db` (WAL) | `.worktrees/FTR-146/scripts/vps/schema.sql:1` | Runtime state |
| NEW: `groq` Python SDK | Phase 2 | STT for voice messages |

### Step 3: BY TERM — Grep key terms

```bash
grep -rn "night\|night_review\|voice\|groq\|findings\|individual.*find" .claude/ scripts/ --include="*.md" --include="*.sh" --include="*.py"
```

| File | Line | Context |
|------|------|---------|
| `.worktrees/FTR-146/scripts/vps/notify.py` | 6 | `Used by: pueue-callback.sh, orchestrator.sh, qa-loop.sh` — qa-loop.sh is future task, shows night-reviewer.sh fits same pattern |
| `.worktrees/FTR-146/scripts/vps/pueue-callback.sh` | 66 | `NEW_PHASE="qa_pending"` — Phase 2 adds `night_pending` as a new phase value |
| `.worktrees/FTR-146/scripts/vps/telegram-bot.py` | 159 | `status_icon = {"idle": "⚪", "running": "🟢", "qa_pending": "🟡", "failed": "🔴"}` — needs `night_reviewing`, `night_failed` added |
| `.claude/agents/audit/coroner.md` | 112 | Output is one big `report-coroner.md` — Phase 2 needs per-finding files instead |
| `.claude/skills/audit/deep-mode.md` | 46 | `node .claude/scripts/codebase-inventory.mjs src/` — too heavy for nightly; night mode skips Phase 0 |

```bash
grep -rn "qa_pending\|qa_running\|qa_failed\|night" .worktrees/FTR-146/scripts/vps/ --include="*.py" --include="*.sh" --include="*.sql"
```

| File | Line | Context |
|------|------|---------|
| `.worktrees/FTR-146/scripts/vps/pueue-callback.sh` | 66 | `NEW_PHASE="qa_pending"` |
| `.worktrees/FTR-146/scripts/vps/telegram-bot.py` | 159 | `qa_pending` phase icon |

### Step 4: CHECKLIST — Mandatory folders

- [ ] `tests/**` — 0 test files found for `scripts/vps/`. Phase 1 spec calls for `tests/vps/` but not yet created. Phase 2 must create tests for night-reviewer.sh and voice handler.
- [ ] `db/migrations/**` — Not applicable. SQLite schema lives in `scripts/vps/schema.sql`. Phase 2 needs new tables (see Step 5).
- [ ] `ai/glossary/**` — No glossary exists for orchestrator domain yet. Phase 2 should create `ai/glossary/orchestrator.md` (terms: night_scan, finding, voice_inbox, approve_flow).
- [ ] `.claude/skills/audit/` — Phase 2 adds `night-mode.md` here. Template sync rule applies: must also update `template/.claude/skills/audit/`.
- [ ] `.claude/agents/audit/` — Coroner + Scout personas are reused as-is; no modification needed.

### Step 5: DUAL SYSTEM check

Phase 2 changes `project_state.phase` state machine by adding new phases. Two systems read phase:

| System | File | Reads phase | Impact |
|--------|------|-------------|--------|
| `telegram-bot.py` | `.worktrees/FTR-146/scripts/vps/telegram-bot.py:159` | `status_icon` dict | Must add `night_reviewing`, `night_pending`, `night_failed` icons |
| `pueue-callback.sh` | `.worktrees/FTR-146/scripts/vps/pueue-callback.sh:66` | `NEW_PHASE="qa_pending"` hardcoded | Must add night-review trigger path (either after QA pass, or on cron) |
| `orchestrator.sh` (Task 6 — not yet committed) | `FTR-146 spec:1648` | `qa_pending` dispatch logic | Must also dispatch `night_pending` → `night-reviewer.sh` |

New phases in Phase 2: `night_pending`, `night_reviewing`, `night_failed`.

---

## Affected Files

### Phase 1 files that Phase 2 modifies

| File | LOC | Role | Change type |
|------|-----|------|-------------|
| `.worktrees/FTR-146/scripts/vps/schema.sql` | 46 | SQLite DDL | modify — add `night_findings` table, add new phase values to docs |
| `.worktrees/FTR-146/scripts/vps/db.py` | 231 | DB helpers | modify — add `get_night_findings()`, `save_finding()`, `get_projects_for_night_scan()` |
| `.worktrees/FTR-146/scripts/vps/telegram-bot.py` | 389 | Telegram bot | modify — add `handle_voice`, `cmd_approve`/`cmd_reject`, night phase icons, `CallbackQueryHandler` |
| `.worktrees/FTR-146/scripts/vps/requirements.txt` | 2 | Python deps | modify — add `groq>=0.5.0` for STT |
| `.worktrees/FTR-146/scripts/vps/notify.py` | 89 | Notification helper | read-only (used by new scripts, no changes needed) |
| `.worktrees/FTR-146/scripts/vps/pueue-callback.sh` | 116 | Pueue callback | modify — or keep as-is (night dispatch triggered by orchestrator cron, not callback) |

### Phase 2 new files

| File | LOC est. | Role | Change type |
|------|----------|------|-------------|
| `scripts/vps/night-reviewer.sh` | ~150 | Cron-triggered: run audit night mode on each project | create |
| `scripts/vps/voice-stt.py` | ~60 | Groq Whisper STT: OGG → text | create |
| `.claude/skills/audit/night-mode.md` | ~120 | Audit `night` mode: 2-3 personas, individual findings output | create |
| `template/.claude/skills/audit/night-mode.md` | ~120 | Template sync copy | create |
| `ai/glossary/orchestrator.md` | ~40 | Domain terms for orchestrator | create |
| `.claude/rules/domains/orchestrator.md` | ~30 | Domain context for orchestrator VPS scripts | create |

### Skills that remain read-only (used but not changed)

| File | LOC | Role |
|------|-----|------|
| `.claude/skills/audit/SKILL.md` | 301 | Audit skill dispatcher — add `night` trigger detection |
| `.claude/skills/audit/deep-mode.md` | 248 | Deep mode — used as design reference only |
| `.claude/skills/qa/SKILL.md` | 441 | QA skill — unchanged, called by qa-loop.sh |
| `scripts/autopilot-loop.sh` | 165 | Autopilot loop — unchanged by Phase 2 |

**Total affected:** ~12 files, ~2,300 LOC (existing) + ~520 LOC (new)

---

## Reuse Opportunities

### Import (use as-is)

- `db.get_all_projects()` — iterate all enabled projects for night scan scheduling
- `db.update_project_phase()` — set `night_reviewing` before scan, `idle` after
- `db.log_task()` / `db.finish_task()` — track night scan runs in task_log
- `notify.send_to_project()` — deliver individual findings as Telegram messages to project topic
- `notify.send_to_general()` — nightly summary across all projects to General topic
- `run-agent.sh` + `claude-runner.sh` — already supports `skill=audit`; just pass `skill=audit night` as task

### Extend (subclass or wrap)

- `telegram-bot.py` — add `handle_voice` MessageHandler alongside `handle_text`. PTB `filters.VOICE` is available in v21.9. Voice handler: download OGG → call `voice-stt.py` → pass text to `_save_to_inbox()`. Shared `_save_to_inbox` and `detect_route` need zero changes.
- `telegram-bot.py` — add `CallbackQueryHandler` for approve/reject inline buttons. `cmd_run` already has trigger file pattern (`.run-now-{project_id}`); approve writes to same trigger, reject writes `.reject-{project_id}`.
- `.claude/skills/audit/SKILL.md` — add `night` to Mode Detection table; add `night-mode.md` to Modules table.
- `schema.sql` — add `night_findings` table: `id, project_id, finding_id, severity, file_path, summary, created_at, spec_created`. This is a new append-only log that persists historical findings.

### Pattern (copy structure, not code)

- `qa-loop.sh` (FTR-146 Task 8) — `night-reviewer.sh` follows identical pattern: update phase → run claude → check exit → write findings to inbox or summarize.
- `pueue-callback.sh` fail-safe pattern — `set -uo pipefail` + `|| true` on every risky step + never exit non-zero. Night reviewer must follow this exactly (it runs as cron — a crash that fails silently is better than cron seeing error and spamming alerts).
- `bughunt-findings-collector` → normalize findings from audit personas into per-finding YAML → each finding becomes one inbox item (route: `spark_bug`).
- Deep mode ADR-007/008/009/010 compliance pattern — all sub-agent calls in night mode use `run_in_background: true`; orchestrator never reads TaskOutput directly.

---

## Git Context

### Recent Changes to Affected Areas

```bash
git log --oneline -10 -- scripts/vps/ .claude/skills/audit/ .claude/skills/qa/ scripts/autopilot-loop.sh
```

| Date | Commit | Summary |
|------|--------|---------|
| 2026-03-10 | `9c6af69` | feat(vps): add Telegram bot core with topic routing + notify helper |
| 2026-03-10 | `ec47ed4` | feat(vps): add Pueue callback with parameterized DB operations |
| 2026-03-10 | `f7b2866` | feat(vps): add provider abstraction runners for orchestrator |
| 2026-03-10 | `901eed9` | feat(vps): add SQLite schema + Python DB module for orchestrator |
| 2026-03-10 | `c11e1b8` | docs: create spec FTR-146 Multi-Project Orchestrator Phase 1 |
| (earlier) | `ca0499e` | feat(TECH-057): add semantic triggers to all skills |
| (earlier) | `db87ec9` | refactor: rename ralph-autopilot to autopilot-loop |

**Observation:** All Phase 1 VPS files committed today (2026-03-10) in 4 sequential commits. FTR-146 is still `in_progress` — Tasks 5-11 not yet committed (no `orchestrator.sh`, `inbox-processor.sh`, `qa-loop.sh`, `setup-vps.sh`). Phase 2 must wait for Phase 1 to be at least `qa_pending` before the integration hooks are known-stable.

Critical: `telegram-bot.py` at 389 LOC. Phase 2 adds voice handler + approve/reject buttons. If both are added inline, file will hit the 400 LOC limit. Plan to split: move `handle_voice` + STT logic to `voice_handler.py`, imported into `telegram-bot.py`.

---

## Risks

1. **Risk:** Phase 1 Tasks 5-11 not yet committed. `orchestrator.sh`, `qa-loop.sh`, `inbox-processor.sh` are missing from disk.
   **Impact:** Phase 2 integration (night-reviewer hook in orchestrator, QA fix loop) cannot be tested until Phase 1 is complete.
   **Mitigation:** Phase 2 spec must declare dependency: "Tasks 5-9 of FTR-146 must be done before Phase 2 implementation starts." Scout this again after Phase 1 is `done`.

2. **Risk:** `telegram-bot.py` is already at 389 LOC. Phase 2 adds voice handler + approve/reject + night phase icons.
   **Impact:** Will exceed 400 LOC limit. Pre-edit hook will soft-block with `askTool`.
   **Mitigation:** Extract voice handling to `scripts/vps/voice_handler.py`. `telegram-bot.py` imports `from voice_handler import handle_voice` — net delta minimal.

3. **Risk:** `project_state.phase` is a free-text column with no CHECK constraint. Adding new phases (`night_pending`, `night_reviewing`, `night_failed`) can silently conflict with existing phase names read by `telegram-bot.py` and `orchestrator.sh`.
   **Impact:** Wrong phase icon, orchestrator doesn't dispatch night scan correctly.
   **Mitigation:** Document all valid phases in schema comment. Consider adding `CHECK (phase IN (...))` in a `schema-v2.sql` migration — but read CLAUDE.md rule: migrations are git-first only, never applied directly.

4. **Risk:** Audit `night` mode reuses Coroner + Scout personas which write to `ai/audit/report-*.md`. If two projects run night scan simultaneously, persona output files from different projects will collide.
   **Impact:** Findings from project A overwrite project B.
   **Mitigation:** Night mode must scope output to `{PROJECT_DIR}/ai/audit/night-{YYYY-MM-DD}/` — not the shared DLD `ai/audit/`. Add `PROJECT_DIR` to persona prompts.

5. **Risk:** Groq STT (`voice-stt.py`) requires `GROQ_API_KEY`. This is a new secret not yet in Nexus.
   **Impact:** Voice inbox fails silently if key is missing.
   **Mitigation:** `voice_handler.py` checks `GROQ_API_KEY` on import; if missing, logs warning and routes to fallback (bot replies "Voice not configured, send text instead"). Add to `.env.example`.

6. **Risk:** Night scan runs as a cron job. If it crashes mid-scan, `project_state.phase` stays as `night_reviewing` forever — project appears "busy" to orchestrator.
   **Impact:** Project is never scheduled for new tasks.
   **Mitigation:** Night-reviewer.sh must have a cleanup trap: `trap 'python3 db.py update-phase $PROJECT_ID idle' EXIT ERR`. Same pattern as fail-safe in `pueue-callback.sh`.

---

## Appendix: Phase State Machine (as-built + Phase 2 additions)

```
Phase 1 phases (existing):
  idle → running → qa_pending → qa_running → idle
                             → qa_failed

Phase 2 additions:
  idle → night_pending → night_reviewing → idle
                                        → night_failed
```

Trigger: `pueue-callback.sh` currently hardcodes `NEW_PHASE="qa_pending"` on success. Phase 2 needs `orchestrator.sh` to schedule `night_pending` on a cron schedule (e.g., nightly at 02:00) — independent of task completion.

---

## Appendix: audit `night` mode vs `deep` mode comparison

| Aspect | Deep Mode | Night Mode (proposed) |
|--------|-----------|----------------------|
| Trigger | `/audit deep`, `/retrofit` | Cron, `/night project` |
| Phase 0 inventory | Mandatory (codebase-inventory.mjs) | Skip — too heavy for nightly |
| Personas | 6 parallel | 2 (Coroner + Scout) focused on security + debt |
| Output | One `deep-audit-report.md` | Individual finding files (one per finding) |
| Finding format | Consolidated report | Per-finding inbox items (route: spark_bug) |
| ADR-007/008/009/010 | Enforced | Enforced — same rules apply |
| Duration | 20-40 min | 5-10 min target |
| Scope | Full codebase forensics | Security regressions + critical debt since last scan |
