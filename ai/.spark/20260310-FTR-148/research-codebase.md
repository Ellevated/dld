# Codebase Research — FTR-148 Multi-Project Orchestrator Phase 3: Functionality & Multi-Provider

## Existing Code

### Reusable Modules

| Module | File:line | Description | Reuse how |
|--------|-----------|-------------|-----------|
| `db.get_project_state` | `scripts/vps/db.py:92` | Full project dict by ID including `provider` field | Import directly — Nexus integration queries same record |
| `db.seed_projects_from_json` | `scripts/vps/db.py:170` | Upsert projects into `project_state` | Extend — `/addproject` calls this with a single-project dict |
| `db.get_project_by_topic` | `scripts/vps/db.py:102` | Lookup project by Telegram `topic_id` | Import directly — `/addproject` must check topic is unique |
| `db.get_all_projects` | `scripts/vps/db.py:112` | All enabled projects | Import directly — Nexus sync iterates this |
| `db.try_acquire_slot` | `scripts/vps/db.py:49` | Acquire provider slot by `provider` arg | Import directly — Gemini needs its own provider string |
| `db.get_available_slots` | `scripts/vps/db.py:160` | Count free slots for a given provider | Import directly — orchestrator checks Gemini slots |
| `run-agent.sh` case dispatch | `scripts/vps/run-agent.sh:43` | `case "$PROVIDER" in claude\|codex)` | Extend — add `gemini)` branch pointing to new `gemini-runner.sh` |
| `claude-runner.sh` structure | `scripts/vps/claude-runner.sh:1` | flock + timeout + `--print --output-format json` pattern | Pattern — `gemini-runner.sh` follows identical structure (replace binary + flags) |
| `codex-runner.sh` structure | `scripts/vps/codex-runner.sh:1` | Minimal runner with `cd + exec + jq result` | Pattern — Gemini runner is similar minimal wrapper |
| `orchestrator.sh:scan_backlog` | `scripts/vps/orchestrator.sh:155` | Reads provider from DB → picks pueue group → submits | Extend — task-level routing reads provider from spec frontmatter, overrides project default |
| `inbox-processor.sh` | `scripts/vps/inbox-processor.sh:102` | Resolves provider from DB | Extend — also check inbox file for `Provider:` override header |
| `setup-vps.sh` | `scripts/vps/setup-vps.sh:136` | Creates pueue groups + sets parallelism | Extend — add `pueue group add gemini-runner` + `pueue parallel 1 --group gemini-runner` |
| `setup-vps.sh Nexus block` | `scripts/vps/setup-vps.sh:247` | `bootstrap list-projects --format json` → `projects.json` | Extend — new runtime query: `nexus get_project_context` before each task via MCP or CLI |
| `telegram-bot._resolve_project` | `scripts/vps/telegram-bot.py:91` | Resolves project from args or topic_id | Import directly — `/addproject` uses `get_topic_id(update)` for current topic |
| `telegram-bot._submit_to_pueue` | `scripts/vps/telegram-bot.py:114` | Submits task to pueue by project dict | Import directly — reuse for `/addproject` confirmation flow |
| `notify.py` | `scripts/vps/notify.py:1` | Sends Telegram message to project topic | Import directly — confirm project registration |

### Similar Patterns

| Pattern | File:line | Description | Similarity |
|---------|-----------|-------------|------------|
| `cmd_pause` / `cmd_resume` | `scripts/vps/telegram-bot.py:308` | Command: resolve project, run action, reply text | `/addproject` follows the exact same handler structure |
| Provider in `project_state` schema | `scripts/vps/schema.sql:13` | `provider TEXT NOT NULL DEFAULT 'claude'` | Task-level routing needs a `task_provider` override column or reads from spec file |
| Slot seed in `schema.sql` | `scripts/vps/schema.sql:44` | `INSERT OR IGNORE INTO compute_slots` | New Gemini slot needs identical seed row |
| `pueue_group = "{provider}-runner"` convention | `scripts/vps/orchestrator.sh:204` | Group name is deterministic from provider string | All code derives group from provider — add `gemini` and naming is consistent |
| `flock --timeout 120 /tmp/claude-oauth.lock` | `scripts/vps/claude-runner.sh:31` | Serializes OAuth refresh across sessions | Gemini runner may need separate lock file `/tmp/gemini-api.lock` |
| `CLAUDE_CODE_CONFIG_DIR` export | `scripts/vps/claude-runner.sh:19` | Per-project config isolation (DA-9) | No equivalent for Gemini CLI — document in devil's advocate |

**Recommendation:** For provider dispatch: add one `case` branch in `run-agent.sh` + new `gemini-runner.sh` (40 LOC, modeled on `codex-runner.sh`). For `/addproject`: add one command handler to `telegram-bot.py` (~30 LOC, modeled on `cmd_pause`). For schema: one new slot seed INSERT. For Nexus: implement as a pre-task bash query (`nexus get_project_context` via node CLI or store output in a tmp file). Global skills: `CLAUDE_CODE_CONFIG_DIR` already points to per-project `.claude-config/` — global `~/.claude/skills/` is loaded automatically by Claude CLI regardless, no code change needed.

---

## Impact Tree Analysis

### Step 1: UP — Who uses changed code?

Files that use `db.py`, `run-agent.sh`, and `telegram-bot.py`:

```bash
grep -r "from.*db\|import db\|run-agent\|telegram.bot" scripts/vps/ --include="*.py" --include="*.sh"
```

| File | Line | Usage |
|------|------|-------|
| `scripts/vps/telegram-bot.py` | 29 | `import db` |
| `scripts/vps/notify.py` | 23 | `import db` (via `get_project_state`) |
| `scripts/vps/approve_handler.py` | 21 | `import db` (findings CRUD) |
| `scripts/vps/voice_handler.py` | 64 | `import db` (via sys.modules lookup) |
| `scripts/vps/pueue-callback.sh` | 71 | `python3 db.py callback` |
| `scripts/vps/orchestrator.sh` | 214 | `run-agent.sh` as pueue task |
| `scripts/vps/inbox-processor.sh` | 165 | `run-agent.sh` as pueue task |
| `scripts/vps/night-reviewer.sh` | — | uses `claude` CLI directly (not run-agent.sh) |
| `scripts/vps/qa-loop.sh` | — | uses `run-agent.sh` |

**Callers of `run-agent.sh`:** orchestrator.sh, inbox-processor.sh, qa-loop.sh (3 files). All pass `provider` as positional arg $3 — Gemini extension is transparent to them.

### Step 2: DOWN — What does it depend on?

| Dependency | File | Function |
|------------|------|----------|
| `sqlite3` stdlib | `scripts/vps/db.py:11` | All DB operations |
| `python-telegram-bot >=21.9,<22.0` | `scripts/vps/requirements.txt:1` | Bot async framework |
| `python-dotenv` | `scripts/vps/requirements.txt:2` | `.env` loading |
| `groq >=0.5.0` | `scripts/vps/requirements.txt:3` | Voice transcription |
| `pueue v4.0.4` | systemd | Group-based parallelism |
| `claude` CLI | `scripts/vps/claude-runner.sh:12` | `--print --output-format json` |
| `codex` CLI | `scripts/vps/codex-runner.sh:11` | `exec --sandbox workspace-write --json` |
| NEW: `gemini` CLI | to be created | Gemini Code runner binary |
| `orchestrator.db` (WAL) | `scripts/vps/schema.sql:1` | Runtime state |
| Nexus CLI (`bootstrap` or `nexus`) | `scripts/vps/setup-vps.sh:247` | `list-projects`, `get-secret` |

### Step 3: BY TERM — Grep key terms

```bash
grep -rn "provider" scripts/vps/ --include="*.py" --include="*.sh" --include="*.sql"
# Results: 28 occurrences
```

| File | Line | Context |
|------|------|---------|
| `scripts/vps/schema.sql` | 13 | `provider TEXT NOT NULL DEFAULT 'claude'` — project_state |
| `scripts/vps/schema.sql` | 23 | `provider TEXT NOT NULL` — compute_slots |
| `scripts/vps/schema.sql` | 44-46 | Slot seeds: claude×2, codex×1 |
| `scripts/vps/run-agent.sh` | 5 | Comment: `provider: claude | codex` — needs update |
| `scripts/vps/run-agent.sh` | 43 | `case "$PROVIDER" in` — add gemini branch here |
| `scripts/vps/orchestrator.sh` | 175 | `print(state['provider'] if state else 'claude')` |
| `scripts/vps/orchestrator.sh` | 185 | `db.get_available_slots('${provider}')` |
| `scripts/vps/orchestrator.sh` | 204 | `local pueue_group="${provider}-runner"` |
| `scripts/vps/db.py` | 58 | `WHERE provider = ? AND project_id IS NULL` |
| `scripts/vps/db.py` | 164 | `WHERE provider = ? AND project_id IS NULL` |
| `scripts/vps/db.py` | 185 | `p.get("provider", "claude")` in seed_projects_from_json |
| `scripts/vps/telegram-bot.py` | 118 | `project.get("provider", "claude")` in `_submit_to_pueue` |
| `scripts/vps/telegram-bot.py` | 261 | `project.get('provider', 'claude')` in `_send_project_status` |
| `scripts/vps/inbox-processor.sh` | 108 | `print(state['provider'] if state else 'claude')` |

```bash
grep -rn "addproject\|/addproject\|add_project" scripts/vps/ --include="*.py" --include="*.sh"
# Results: 0 occurrences — does not exist yet
```

```bash
grep -rn "nexus\|bootstrap" scripts/vps/ --include="*.py" --include="*.sh"
# Results: 5 occurrences (all in setup-vps.sh)
```

| File | Line | Context |
|------|------|---------|
| `scripts/vps/setup-vps.sh` | 247 | `if command -v nexus &>/dev/null || command -v bootstrap` |
| `scripts/vps/setup-vps.sh` | 252 | `"${NEXUS_BIN}" list-projects --format json` — one-time seed |
| `scripts/vps/setup-vps.sh` | 266 | `"${NEXUS_BIN}" get-secret GROQ_API_KEY --env prod` |

**Nexus runtime integration is NOT present.** Current Nexus usage is setup-time only (seed `projects.json`, pull `GROQ_API_KEY`). The Nexus MCP tools available are: `list_projects`, `get_project_context`, `get_checklist`, `get_impact`, `get_secret`, `list_secrets`. The `bootstrap` CLI only supports: `serve`, `keygen`, `setup`, `deploy`, `health`. There is no `list-projects --format json` on current CLI — this was written speculatively in setup-vps.sh. **Nexus-as-runtime-SSOT needs design work** — the MCP tool interface is available but calling it from bash requires the MCP server to be running.

### Step 4: CHECKLIST — Mandatory folders

- [x] `scripts/vps/**` — 15 files, all read above
- [ ] `tests/**` — 0 files found for VPS scripts (no tests exist)
- [ ] `db/migrations/**` — N/A (SQLite, schema.sql is the migration)
- [ ] `ai/glossary/**` — no glossary for orchestrator domain yet

```bash
ls /Users/desperado/dev/dld/ai/features/ | grep FTR-14
# FTR-146, FTR-147 specs present
```

### Step 5: DUAL SYSTEM check

**Task-level routing** changes data flow: currently `provider` is project-level (one value per project). Phase 3 adds task-level override. Two systems will read provider:
- **Old path:** `orchestrator.sh:scan_backlog` reads `project_state.provider` → uses it for all tasks
- **New path:** `scan_backlog` must also check spec file frontmatter for `provider:` override

Both orchestrator AND inbox-processor read provider — both need updating.

If Nexus becomes runtime SSOT: `orchestrator.sh:sync_projects` currently reads from `projects.json`. A Nexus-driven flow would bypass `projects.json` entirely. This is a dual-source risk — either projects.json remains canonical (Nexus as enrichment only) or it's deprecated. Decision needed before implementation.

---

## Affected Files

| File | LOC | Role | Change type |
|------|-----|------|-------------|
| `scripts/vps/run-agent.sh` | 54 | Provider dispatch | modify — add `gemini)` case |
| `scripts/vps/gemini-runner.sh` | ~40 | Gemini CLI wrapper | create |
| `scripts/vps/schema.sql` | 64 | DB schema | modify — add Gemini slot seed |
| `scripts/vps/setup-vps.sh` | 352 | VPS bootstrap | modify — add gemini-runner group, Gemini CLI check |
| `scripts/vps/telegram-bot.py` | 397 | Telegram bot | modify — add `cmd_addproject` handler (~30 LOC) |
| `scripts/vps/db.py` | 370 | SQLite module | modify — add `add_project` function or reuse seed_projects_from_json |
| `scripts/vps/orchestrator.sh` | 361 | Main daemon | modify — task-level provider override in scan_backlog |
| `scripts/vps/inbox-processor.sh` | 186 | Inbox dispatch | modify — read Provider: from inbox file header |
| `scripts/vps/projects.json.example` | 16 | Example config | modify — document task-level provider in comments |
| `scripts/vps/.env.example` | 29 | Env template | modify — add GEMINI_PATH |
| `scripts/vps/pueue-callback.sh` | 116 | Completion callback | read-only (group comment may need update) |
| `scripts/vps/global-claude-md.template` | 29 | Global CLAUDE.md | read-only (no change needed) |
| `.claude/rules/dependencies.md` | — | Dep map | modify — add gemini-runner.sh entry |

**Total:** 10 files modified + 1 created, ~2850 LOC affected (read), ~150 LOC net new

---

## Reuse Opportunities

### Import (use as-is)
- `db.seed_projects_from_json(projects)` — `/addproject` passes `[{project_id, path, topic_id, provider, auto_approve_timeout}]`
- `db.get_project_by_topic(topic_id)` — validate topic not already registered in `/addproject`
- `db.get_available_slots(provider)` — orchestrator slot check works for Gemini unchanged
- `db.try_acquire_slot(project_id, provider, pueue_id)` — works for Gemini with `provider='gemini'`
- `telegram-bot.get_topic_id(update)` — `/addproject` reads current topic as the new project topic
- `telegram-bot.is_authorized(user_id)` — same auth check for new command

### Extend (subclass or wrap)
- `run-agent.sh` case block — add one `gemini)` branch, exec `gemini-runner.sh`
- `orchestrator.sh:scan_backlog` — after resolving `provider` from DB, check spec file for `provider:` frontmatter override (5-10 LOC addition)
- `setup-vps.sh` Pueue group section — add `pueue group add gemini-runner` + `pueue parallel 1` line

### Pattern (copy structure, not code)
- `codex-runner.sh` → `gemini-runner.sh` — same structure: validate args, cd, exec with timeout, jq result JSON
- `cmd_pause` handler → `cmd_addproject` handler — same pattern: validate auth, get args, run action, reply
- `schema.sql` slot seed lines → Gemini slot seed: `INSERT OR IGNORE INTO compute_slots (slot_number, provider) VALUES (4, 'gemini')`

---

## Git Context

### Recent Changes to Affected Areas

```bash
git log --oneline -15 -- scripts/vps/
```

| Date | Commit | Summary |
|------|--------|---------|
| recent | 5fc0275 | feat(vps): add systemd exponential backoff + file-based logging |
| recent | 8402072 | feat(vps): add Nexus integration + global CLAUDE.md + night pueue group |
| recent | a4649d3 | feat(vps): add flock OAuth wrapper + global CLAUDE.md template |
| recent | e5a2875 | feat(vps): add evening prompt + approve/reject finding handlers |
| recent | 52ffb61 | feat(vps): add night reviewer script + orchestrator trigger |
| recent | 98f6729 | feat(vps): add Groq Whisper voice handler for Telegram |
| recent | ffb4476 | feat(vps): add night_findings table + finding CRUD functions |
| recent | 907149c | feat(vps): add VPS bootstrap script + config templates |
| recent | 2b1a9fd | feat(vps): add QA dispatch loop after autopilot completion |
| recent | 5a7bf29 | feat(vps): add auto-approve flow with Spark summary + timer |
| recent | 42b219d | feat(vps): add orchestrator main daemon loop |
| recent | 4ccd090 | feat(vps): add inbox processor with keyword routing |
| recent | 9c6af69 | feat(vps): add Telegram bot core with topic routing + notify helper |
| recent | ec47ed4 | feat(vps): add Pueue callback with parameterized DB operations |
| recent | f7b2866 | feat(vps): add provider abstraction runners for orchestrator |

**Observation:** All 15 commits are from the current sprint. This is entirely new code — no legacy risk, no refactoring needed. Active area — expect merge conflicts if Phase 2 worktree is still alive.

---

## Key Findings Per Feature Area

### 1. Task-level LLM routing

**Current state:** Provider is **project-level only** — stored in `project_state.provider`, seeded from `projects.json`. All tasks for a project use the same provider. No per-task override mechanism exists anywhere.

**Where to add:** `orchestrator.sh:scan_backlog` (line 168) and `inbox-processor.sh` (line 102) both resolve provider from DB. Add spec-file frontmatter check AFTER DB lookup:
```bash
# After: provider=$(python3 -c "...db.get_project_state...print(state['provider'])...")
task_provider=$(grep -oE '^provider:\s+\w+' "$spec_file" 2>/dev/null | awk '{print $2}' || true)
provider="${task_provider:-$provider}"
```

**Pueue group convention** (`{provider}-runner`) already handles routing — no other changes needed once provider is resolved correctly.

### 2. /addproject Telegram command

**Current state:** Zero implementation. Projects added only via `projects.json` + `python3 db.py seed`.

**telegram-bot.py current LOC: 397** — already exceeds the 400 LOC soft limit. Adding `/addproject` inline will push it over. **Must split** or keep the handler body in a new module (e.g., `admin_handler.py`, same pattern as `approve_handler.py`).

**What `/addproject` needs:**
- Parse args: `project_id`, `path`, `provider` (optional), `auto_approve_timeout` (optional)
- Get `topic_id` from current forum thread via `get_topic_id(update)`
- Check: topic not already linked (`db.get_project_by_topic`)
- Upsert: call `db.seed_projects_from_json([{...}])`
- Create pueue group: `subprocess.run(["pueue", "group", "add", project_id])`
- Reply confirmation

**Does NOT need:** Forum topic creation (Telegram Bot API `createForumTopic` — user creates topic first, then runs `/addproject`).

### 3. Global DLD skills on VDS

**Current state:** `claude-runner.sh` sets `CLAUDE_CODE_CONFIG_DIR="${PROJECT_DIR}/.claude-config"`. Claude CLI also reads `~/.claude/` global config. Skills in `.claude/skills/` are project-local slash commands.

**How global skills work:** Claude CLI discovers slash commands from `{config_dir}/skills/` AND from `~/.claude/commands/` (confirmed by `~/.claude/commands/` directory existing with `focus.md`, `ship.md`, etc.). The `.claude/skills/` pattern uses project-local discovery.

**For global VDS skills:** Copy or symlink `~/.claude/skills/` → DLD `.claude/skills/` during `setup-vps.sh`. OR: use `--add-dir` flag to include global skills directory. **No code change to runners needed** — this is a setup/configuration task, not a code task.

### 4. Nexus as runtime SSOT

**Current Nexus CLI commands:** `serve`, `keygen`, `setup mcp`, `deploy sync`, `deploy check`, `health`. **No `list-projects` or `get-secret` as direct CLI subcommands** — these exist only as **MCP tools** (`list_projects`, `get_project_context`, `get_secret`, `list_secrets`).

The `setup-vps.sh` line `"${NEXUS_BIN}" list-projects --format json` was written speculatively — this command does not exist in the current Nexus CLI. **Dead code.**

**Practical Nexus-as-SSOT options:**
- Option A: Implement via Nexus MCP server (requires running `nexus serve` as a process, then calling MCP tools from bash via stdin/stdout JSON-RPC) — complex
- Option B: Add `list-projects` and `get-secret` subcommands to Nexus CLI (`~/dev/nexus/bin/nexus.js`) — requires Nexus change
- Option C: Nexus SSOT only at setup time (current behavior) — no runtime queries, `projects.json` remains canonical

**Recommendation for Phase 3:** Option C is the safe path. Nexus is relevant for seeding projects at setup. Real-time Nexus queries before each task add latency and a dependency on Nexus running on VPS.

### 5. VPS Setup Instructions

`setup-vps.sh` at 352 LOC is already comprehensive. Missing for Phase 3:
- Gemini CLI installation/path verification
- `gemini-runner` pueue group creation
- Gemini API key in `.env.example`

---

## Risks

1. **Risk:** `telegram-bot.py` is already at 397 LOC (3 lines under hard limit)
   **Impact:** Adding `/addproject` inline violates 400 LOC rule
   **Mitigation:** Create `admin_handler.py` module (same pattern as `approve_handler.py` at 199 LOC). Import in `telegram-bot.py`. Register handler in `main()`. Net addition to telegram-bot.py: ~5 LOC.

2. **Risk:** Gemini CLI interface is unknown — no existing runner to validate against
   **Impact:** `gemini-runner.sh` may need different flags than `codex` or `claude` (no `--print --output-format json` equivalent)
   **Mitigation:** Spike: run `gemini --help` on VPS before implementing. Document Gemini CLI flags in spec. Codex runner (34 LOC) is the simpler template to follow.

3. **Risk:** Task-level provider override may request Gemini when 0 Gemini slots are seeded
   **Impact:** Task queues indefinitely with no error feedback
   **Mitigation:** Add availability check for task-level provider in `scan_backlog`, same as the existing `available=$(db.get_available_slots('${provider}'))` check. Log warning if override provider has 0 slots.

4. **Risk:** Nexus `list-projects --format json` does not exist in current CLI
   **Impact:** `setup-vps.sh` Nexus integration block is dead code — projects are never auto-populated from Nexus
   **Mitigation:** Either fix setup-vps.sh to use MCP tool format OR simplify to manual `projects.json` creation. Do not carry forward the broken integration pattern.

5. **Risk:** `/addproject` does NOT create pueue group atomically with DB registration
   **Impact:** Project registered in DB but has no pueue group — first task submission will fail
   **Mitigation:** `/addproject` handler must call `pueue group add {project_id}` via subprocess after DB upsert. Wrap with `|| true` (group may already exist).

6. **Risk:** Multiple Phase specs alive in git (FTR-146, FTR-147 worktrees may still exist)
   **Impact:** Merge conflicts on `telegram-bot.py`, `schema.sql`, `db.py`
   **Mitigation:** Confirm Phase 2 worktree is merged before starting Phase 3 work.
