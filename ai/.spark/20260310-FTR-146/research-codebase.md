# Codebase Research — Multi-Project Orchestrator Phase 1 (FTR-146)

## Existing Code

### KEY FINDING: All core VPS scripts already exist in git history

Commit `51e7788` (2026-03-10) added a full autonomous pipeline. Commit `f585ba5` (2026-03-10)
extended it with QA loop. These files are NOT on the current filesystem (`scripts/vps/` is absent)
but are 100% recoverable from git. The architecture spec for Phase 1 is fully written at
`ai/architect/multi-project-orchestrator.md` (commit `a2461ab`, same day).

### Reusable Modules

| Module | File:git | Description | Reuse how |
|--------|----------|-------------|-----------|
| `notify.sh` | git:51e7788:scripts/vps/notify.sh:46 | curl-based Telegram notifier, reads `.env`, graceful fallback to stdout | Extend with `--project` param + `message_thread_id` routing |
| `orchestrator.sh` (v1) | git:51e7788:scripts/vps/orchestrator.sh:244 | Single-project daemon: inbox poll → Spark, backlog poll → autopilot, `.run-now` trigger | Refactor: add `projects.json` loop, semaphore, multi-project state |
| `orchestrator.sh` (v2 with QA) | git:f585ba5:scripts/vps/orchestrator.sh | Updated: adds Phase 3 QA poll (`QA_POLL_INTERVAL=120`) | Start from this version |
| `telegram-bot.py` | git:51e7788:scripts/vps/telegram-bot.py:287 | PTB polling bot: text/voice → inbox, `/status /queue /inbox /run` commands, Groq/OpenAI Whisper | Refactor: add `message_thread_id` routing per `multi-project-orchestrator.md` |
| `inbox-processor.sh` | git:51e7788:scripts/vps/inbox-processor.sh:152 | Runs `claude --print` with Spark headless prompt, moves done files to `inbox/done/` | Extend: accept `PROJECT_DIR` as arg |
| `qa-loop.sh` | git:f585ba5:scripts/vps/qa-loop.sh | Runs QA agent on done specs, routes PASS to `ai/qa/`, FAIL back to `ai/inbox/` | Extend: accept `PROJECT_DIR` as arg |
| `setup-vps.sh` | git:51e7788:scripts/vps/setup-vps.sh:232 | One-command setup: pip install, dirs, systemd service templates inline | Extend: add `projects.json` init, multi-project services |
| `.env.example` | git:51e7788:scripts/vps/.env.example | All env vars: bot token, allowed users, whisper, paths, poll intervals | Add: `TELEGRAM_CHAT_ID`, `GENERAL_TOPIC_ID`, `MAX_CONCURRENT_CLAUDE` |
| `autopilot-loop.sh` | scripts/autopilot-loop.sh:165 | Reads backlog, runs `claude --print "autopilot $SPEC_ID"`, handles done/blocked/in_progress | Used by orchestrator as subprocess; needs `PROJECT_DIR` param |
| `multi-project-orchestrator.md` | ai/architect/multi-project-orchestrator.md:319 | Full architecture spec: projects.json schema, semaphore pattern, Telegram routing, bot commands | This IS the design document for Phase 1 |

### Similar Patterns

| Pattern | File:line | Description | Similarity |
|---------|-----------|-------------|------------|
| flock semaphore | git:51e7788:scripts/vps/orchestrator.sh | Single-project lock (`acquire_lock/release_lock`) | Extend to N-slot semaphore per `multi-project-orchestrator.md:90-105` |
| State JSON | git:51e7788:scripts/vps/orchestrator.sh | `.orchestrator-state.json` with phase/detail/pid | Extend to per-project states per architecture spec |
| `update_state()` | git:51e7788:scripts/vps/orchestrator.sh | Writes state JSON atomically | Copy pattern, add `projects` key |
| `.run-now` trigger | git:51e7788:scripts/vps/orchestrator.sh | Touch file → immediate poll cycle | Already in Telegram bot `/run` command |
| Hot-reload config | ai/architect/multi-project-orchestrator.md:65 | Reread `projects.json` each cycle or via `inotifywait` | Pattern to implement in new orchestrator |
| `CLAUDE_PROJECT_DIR` env | `.claude/hooks/pre-edit.mjs:84` | Hook reads project dir from env | Must set this when launching claude per project |
| `inferSpecFromBranch()` | `.claude/hooks/utils.mjs` | Infers spec from git branch name | Used by pre-edit; orchestrator must set branch per task |
| Pueue reference | ai/architect/multi-project-orchestrator.md:295 | Listed as optional tool for task queue | Architecture spec recommends it but doesn't mandate |

**Recommendation:** Restore all 6 VPS files from git (`git show 51e7788:scripts/vps/X`),
then refactor following the design in `multi-project-orchestrator.md`. The architecture is
already decided — no need to redesign. The telegram-bot.py refactor is the main lift (add
`message_thread_id` routing). The orchestrator refactor adds the `projects.json` loop and
N-slot semaphore.

---

## Impact Tree Analysis

### Step 1: UP — Who uses changed code?

```bash
grep -rn "autopilot-loop\|inbox-processor\|orchestrator\|notify\.sh" . --include="*.sh" --include="*.md" --include="*.py"
# scripts/vps/ doesn't exist on disk yet — git restore needed
# autopilot-loop.sh is called by orchestrator.sh (git history)
# notify.sh is called by orchestrator.sh, inbox-processor.sh, qa-loop.sh
```

| File | Line | Usage |
|------|------|-------|
| `scripts/vps/orchestrator.sh` (git) | ~120 | calls `inbox-processor.sh` |
| `scripts/vps/orchestrator.sh` (git) | ~148 | calls `scripts/autopilot-loop.sh` |
| `scripts/vps/orchestrator.sh` (git) | multiple | calls `notify.sh` |
| `scripts/vps/inbox-processor.sh` (git) | last line | calls `notify.sh` |
| `scripts/vps/qa-loop.sh` (git) | `notify()` fn | calls `notify.sh` |
| `scripts/autopilot-loop.sh` | :117 | `claude --print "autopilot $SPEC_ID"` |

### Step 2: DOWN — What does it depend on?

| Dependency | File | Notes |
|------------|------|-------|
| `claude` CLI | PATH | `claude --print --dangerously-skip-permissions` |
| `ai/backlog.md` | project root | orchestrator reads for queued specs |
| `ai/inbox/*.md` | project root | telegram-bot writes, inbox-processor reads |
| `ai/features/*.md` | project root | qa-loop reads spec files |
| `ai/qa/` | project root | qa-loop writes results |
| `.orchestrator-state.json` | project root | state file per project |
| `.orchestrator.lock` | project root | flock-style lock |
| `.run-now` | project root | manual trigger from Telegram `/run` |
| `scripts/vps/.env` | scripts/vps/ | all secrets and config |
| `projects.json` | scripts/vps/ | NEW: multi-project registry |
| `python-telegram-bot` | pip | PTB v22+ for `message_thread_id` |
| `groq` or `openai` | pip | Whisper voice transcription |
| `python-dotenv` | pip | .env loading |
| Node.js 18+ | system | required for hooks |
| `flock` | system (Linux) | semaphore for concurrent Claude calls |
| `inotifywait` | system (optional) | event-driven inbox watching |

### Step 3: BY TERM — Grep key terms

```bash
grep -rn "scripts/vps\|ai/inbox\|\.run-now\|orchestrator" . --include="*.md" --include="*.sh"
# Results: 1 file with architecture spec, git history only for scripts
```

| File | Line | Context |
|------|------|---------|
| `ai/architect/multi-project-orchestrator.md` | 63 | `scripts/vps/projects.json` path defined |
| `ai/architect/multi-project-orchestrator.md` | 76-83 | orchestrator architecture diagram |
| `ai/architect/multi-project-orchestrator.md` | 256-265 | exact file structure for scripts/vps/ |
| `.claude/hooks/pre-edit.mjs` | 84 | `CLAUDE_PROJECT_DIR` env var hook reads |
| `scripts/autopilot-loop.sh` | 15 | `BACKLOG_FILE="ai/backlog.md"` — hardcoded, needs PROJECT_DIR param |
| `scripts/autopilot-loop.sh` | 88 | spec ID parsed from backlog — project-agnostic already |

```bash
grep -rn "TELEGRAM_BOT_TOKEN\|TELEGRAM_ALLOWED\|message_thread_id" . --include="*.py" --include="*.sh" --include="*.md"
# Results: only in .env.example and architecture spec (git history)
```

### Step 4: CHECKLIST — Mandatory folders

- [x] `scripts/` — `autopilot-loop.sh` exists (165 LOC), hooks dir has pre-review-check.py
- [x] `scripts/vps/` — 6 files in git history (NOT on disk), need restore
- [ ] `tests/**` — no tests for VPS scripts currently
- [ ] `db/migrations/**` — N/A (SQLite only, no migration runner)
- [ ] `ai/glossary/**` — no glossary for orchestrator domain yet
- [x] `template/.claude/agents/qa-tester.md` — exists (from commit f585ba5, used by qa-loop.sh)
- [x] `ai/architect/multi-project-orchestrator.md` — 319 LOC full design document

### Step 5: DUAL SYSTEM check

**Data flow change:** Single `PROJECT_DIR` → N project directories.

Who reads from both old path and new:
- `autopilot-loop.sh`: currently hardcodes `ai/backlog.md` relative to cwd. When called with multi-project orchestrator, must receive `PROJECT_DIR` as arg or `cd $PROJECT_DIR` before running.
- `.claude/hooks/pre-edit.mjs`: reads `CLAUDE_PROJECT_DIR` env var. When launching claude per project, must `CLAUDE_PROJECT_DIR=$project_path claude ...`.
- `ai/backlog.md`: each project has its own. Old single-project orchestrator assumed one backlog. New orchestrator loops over projects, passes correct path.
- `.orchestrator-state.json`: currently one file at project root. Multi-project needs per-project state OR single file with `projects` key (architecture spec shows the latter).

**Critical:** `scripts/autopilot-loop.sh` line 15 hardcodes `BACKLOG_FILE="ai/backlog.md"` as relative path. The multi-project orchestrator must either: (a) `cd $project_dir` before calling it, or (b) pass `BACKLOG_FILE` env var override.

---

## Affected Files

| File | LOC | Role | Change type |
|------|-----|------|-------------|
| `scripts/vps/orchestrator.sh` | 0 (git:244) | Main daemon | restore + refactor (add projects.json loop, N-semaphore) |
| `scripts/vps/telegram-bot.py` | 0 (git:287) | Telegram bot | restore + refactor (add message_thread_id routing) |
| `scripts/vps/notify.sh` | 0 (git:46) | Telegram notifier | restore + extend (--project param, topic_id) |
| `scripts/vps/inbox-processor.sh` | 0 (git:152) | Inbox → Spark | restore + extend (PROJECT_DIR arg) |
| `scripts/vps/qa-loop.sh` | 0 (git:~150) | QA after autopilot | restore + extend (PROJECT_DIR arg) |
| `scripts/vps/setup-vps.sh` | 0 (git:232) | VPS setup | restore + extend (projects.json init, multi-service) |
| `scripts/vps/.env.example` | 0 (git:36) | Config template | restore + add multi-project vars |
| `scripts/vps/projects.json` | 0 | NEW: project registry | create |
| `scripts/autopilot-loop.sh` | 165 | Autopilot loop | modify: add PROJECT_DIR param support |
| `template/scripts/autopilot-loop.sh` | 165 | Mirror | sync change |
| `ai/architect/multi-project-orchestrator.md` | 319 | Architecture spec | read-only reference |
| `template/.claude/agents/qa-tester.md` | ~50 | QA agent prompt | read-only (already exists) |

**Systemd files (NEW, generated by setup-vps.sh --systemd):**
- `/etc/systemd/system/dld-telegram-bot.service`
- `/etc/systemd/system/dld-orchestrator.service`

**Total:** 10 files to create/modify on disk, 8 lines from git to restore

**SQLite for state:** Architecture spec mentions SQLite. The current v1 uses JSON files
(`.orchestrator-state.json`). The Phase 1 spec says "SQLite" — this would replace the JSON
state files. New file: `scripts/vps/state.db` (schema: projects, runs, events tables).

---

## Reuse Opportunities

### Import (use as-is)

- `notify.sh` core (curl + .env loading) — only the `CHAT_ID` and absence of `message_thread_id` needs changing
- `inbox-processor.sh` Spark headless prompt — the prompt engineering for Mode B is tested and working
- `qa-loop.sh` QA verdict parsing (`QA_VERDICT: PASS/FAIL/WARN`) — works as-is, just needs PROJECT_DIR
- `orchestrator.sh` lock management (`acquire_lock/release_lock/flock`) — copy verbatim
- `orchestrator.sh` `update_state()` pattern — copy, extend state schema
- `orchestrator.sh` `.run-now` trigger mechanism — copy verbatim
- `setup-vps.sh` systemd unit templates — copy verbatim, rename service names
- `telegram-bot.py` auth (`is_authorized()`) — copy verbatim
- `telegram-bot.py` voice transcription (`transcribe_voice()`) — copy verbatim
- `telegram-bot.py` `save_to_inbox()` — copy, extend with `project_path` parameter
- `scripts/autopilot-loop.sh` backlog parsing regex — already project-agnostic if cwd is correct

### Extend (subclass or wrap)

- `orchestrator.sh`: single-project loop → multi-project loop with `jq` parsing `projects.json` + `flock` semaphore slots
- `telegram-bot.py`: add `projects_by_topic: dict[int, dict]` lookup on startup, pass `project` to all handlers
- `notify.sh`: add `--project <name>` param → lookup `topic_id` from `projects.json` → add `message_thread_id` to curl payload

### Pattern (copy structure, not code)

- `ai/architect/multi-project-orchestrator.md:90-105` — N-slot flock semaphore pattern to implement in orchestrator
- `ai/architect/multi-project-orchestrator.md:140-170` — Python routing pattern for `handle_message()` / `notify_project()`
- `ai/architect/multi-project-orchestrator.md:200-225` — `/addproject` command creates forum topic + appends to `projects.json`
- `ai/architect/multi-project-orchestrator.md:113-133` — Extended state JSON schema with `projects` key

---

## Git Context

### Recent Changes to Affected Areas

```bash
git log --oneline --all -- scripts/vps/ scripts/autopilot-loop.sh template/scripts/autopilot-loop.sh
```

| Date | Commit | Author | Summary |
|------|--------|--------|---------|
| 2026-03-10 | a2461ab | Claude | docs: multi-project orchestrator architecture spec |
| 2026-03-10 | f585ba5 | Claude | feat: add QA loop — user-perspective testing after autopilot |
| 2026-03-10 | 51e7788 | Claude | feat: add VPS autonomous pipeline (Telegram → Spark → Autopilot) |
| 2026-02-02 | db87ec9 | Ellevated | refactor: rename ralph-autopilot to autopilot-loop |

**Observation:** All three VPS commits were made on 2026-03-10 in a single day session. They are on
`develop` branch (not merged to `main` yet based on git log). The files were never pushed to
disk — the working tree was reset or the session ran in a worktree. They are fully accessible
via `git show 51e7788:scripts/vps/X`. Restore with:
`git show 51e7788:scripts/vps/notify.sh > scripts/vps/notify.sh`

**No conflicts:** `scripts/vps/` does not exist on disk. `scripts/autopilot-loop.sh` hasn't been
touched since Feb 2. No collision risk.

```bash
git log --oneline -5 -- .claude/hooks/
```

| Date | Commit | Author | Summary |
|------|--------|--------|---------|
| 2026-03-09 | edf6b9f | Ellevated | fix(diary): replace broken diary-recorder subagent with inline caller-writes |
| 2026-03-01 | 31fbd51 | Ellevated | feat(hooks): deterministic mock ban in integration tests (ADR-013) |

**Observation:** Hooks were last changed 2026-03-09 (yesterday). The pre-edit hook now checks
`CLAUDE_PROJECT_DIR` env. When launching `claude` per project in the orchestrator, must set:
`CLAUDE_PROJECT_DIR=$project_path claude --print ...`

---

## Hooks Impact

The orchestrator launches `claude --print` which inherits the hook environment. Key hooks:

| Hook | Trigger | Impact for orchestrator |
|------|---------|------------------------|
| `pre-bash.mjs` | Every `Bash` tool call | Blocks `git push main`, `git reset --hard`. Orchestrator must NOT push to main. Safe. |
| `pre-edit.mjs` | Every `Edit/Write` | Checks `CLAUDE_CURRENT_SPEC_PATH` and `CLAUDE_PROJECT_DIR`. Set both per project. |
| `validate-spec-complete.mjs` | `git commit` | Validates spec structure. Will fire during autopilot commits. Needs research phases done. |
| `prompt-guard.mjs` | User prompt submit | Only fires on interactive prompts. Headless `--print` mode: no impact. |
| `session-end.mjs` | Stop hook | Checks diary index. Headless mode: still fires. Safe (only advisory). |

**Critical env vars to set per claude launch:**
```bash
CLAUDE_PROJECT_DIR="$project_path" \
CLAUDE_CURRENT_SPEC_PATH="$project_path/ai/features/$spec_file.md" \
claude --print --dangerously-skip-permissions "autopilot $SPEC_ID"
```

---

## Inbox Convention

Format defined by `save_to_inbox()` in `telegram-bot.py`:

```markdown
# Idea: {timestamp}

**Source:** {text|voice}
**From:** {user_name}
**Date:** {YYYY-MM-DD HH:MM UTC}
**Status:** new

---

{idea text}
```

`inbox-processor.sh` strips the `---` separator and everything above it, sends only the raw
idea text to Spark. Files named: `{timestamp}-{source}.md` (e.g., `2026-03-10-143022-text.md`).
QA bugs filed to inbox use pattern `{SPEC_ID}-qa-bugs.md`.

---

## CLAUDE.md and Per-Project Context Loading

When the orchestrator calls `claude --print` for a project:

1. `CLAUDE_PROJECT_DIR` must point to the project root
2. Claude Code loads `{project}/.claude/settings.json` for hooks
3. Claude Code loads `{project}/CLAUDE.md` as project context
4. Each project must have its own `.claude/` folder (DLD template)

**For the orchestrator to work with each project:** Every managed project must be a DLD project
(has `CLAUDE.md`, `ai/backlog.md`, `.claude/settings.json`). The `projects.json` `path` field
must point to the project root. The orchestrator sets `CLAUDE_PROJECT_DIR` and `cd`s to it
before each `claude` call.

---

## Risks

1. **Risk:** `scripts/vps/` only in git history, not on disk
   **Impact:** Phase 1 requires restoring all 6 files before any extension
   **Mitigation:** `git restore scripts/vps/` won't work (never staged in worktree). Use `git show 51e7788:scripts/vps/X > scripts/vps/X` for each file. Or create new branch from 51e7788.

2. **Risk:** `autopilot-loop.sh` hardcodes relative paths (`ai/backlog.md`, `ai/diary/`)
   **Impact:** Multi-project orchestrator calling it without `cd $project_dir` reads wrong files
   **Mitigation:** Either (a) wrap call with `cd "$project_path" &&`, or (b) add `PROJECT_DIR` override env var to autopilot-loop.sh. Option (a) is simpler and non-breaking.

3. **Risk:** Hook `pre-edit.mjs` checks `CLAUDE_CURRENT_SPEC_PATH` — if not set, uses `inferSpecFromBranch()`
   **Impact:** In headless mode, branch name may not match spec ID → wrong allowlist → edit denied
   **Mitigation:** Always set `CLAUDE_CURRENT_SPEC_PATH` when launching claude per task. Orchestrator must pass this var explicitly.

4. **Risk:** `flock` is Linux-only (`man flock`)
   **Impact:** N-slot semaphore from architecture spec won't work on macOS dev machine
   **Mitigation:** VPS is Linux — production is fine. Dev/test on macOS: skip semaphore or use `lockfile` command. Document macOS limitation.

5. **Risk:** `jq` required to parse `projects.json` in bash orchestrator
   **Impact:** If `jq` not installed on VPS, orchestrator crashes at config parse
   **Mitigation:** `setup-vps.sh` must check `jq` in prerequisites. Add `apt-get install jq` to setup.

6. **Risk:** Telegram forum topics require supergroup + `can_manage_topics` bot permission
   **Impact:** `/addproject` command fails if bot lacks permission or group is not a supergroup
   **Mitigation:** `setup-vps.sh` must verify bot permissions. Document setup steps. `general_topic_id=1` bug: send without `message_thread_id` for general topic (per architecture spec:232).

7. **Risk:** No tests for any VPS script
   **Impact:** Regression risk on refactor — behavior changes silently
   **Mitigation:** Add integration tests in `tests/vps/` that mock Telegram API and verify routing logic. At minimum: `setup-vps.sh --check` as smoke test.

8. **Risk:** `--dangerously-skip-permissions` in `.env.example`
   **Impact:** Claude can run any command in any project on the VPS
   **Mitigation:** The existing `.env.example` already has `CLAUDE_ALLOWED_TOOLS` as a safer alternative. Architecture spec assumes isolated VPS. Document this explicitly. Consider using `CLAUDE_ALLOWED_TOOLS` instead of `--dangerously-skip-permissions` for production.
