# Feature: [FTR-148] Multi-Project Orchestrator Phase 3: Functionality & Multi-Provider

**Status:** queued | **Priority:** P1 | **Date:** 2026-03-10

## Why

Phase 1+2 orchestrator is locked to Claude (+ Codex). Founder wants Gemini as third provider,
Telegram-based project registration (no SSH for JSON edits), global DLD skills across all VDS projects,
and Nexus as single source of truth for deploy rules and project configs.

## Context

- Phase 1 (FTR-146): Pueue + Telegram Bot + SQLite orchestrator (`in_progress`)
- Phase 2 (FTR-147): Whisper, Night Reviewer, approve/reject, OAuth flock, systemd (`in_progress`)
- **Hard gate:** FTR-146 AND FTR-147 must be `done` before Phase 3 implementation starts
- **Cross-repo prerequisite:** Nexus CLI needs `list-projects` + `get-project-context` subcommands (Task 1)
- Architecture: `ai/architect/multi-project-orchestrator.md`
- Research: `ai/.spark/20260310-FTR-148/research-*.md` (4 files)

---

## Scope

**In scope:**
- Gemini CLI runner (`gemini-runner.sh` with `GEMINI_API_KEY`)
- Task-level LLM routing (spec frontmatter `provider:` override)
- `/addproject` Telegram ConversationHandler wizard
- Global DLD skills on VDS (`~/.claude/skills/` via setup-vps.sh)
- Nexus cached file SSOT (cron refresh + `/nexussync` bot command)
- setup-vps.sh --phase3 extension
- VPS manual setup checklist (inline in spec)

**Out of scope:**
- Web dashboard
- Digest notifications (individual messages)
- Metrics/statistics
- Dynamic LLM routing classifier (static metadata is enough at 10 projects)
- Nexus as runtime MCP dependency (cached file, not live queries)

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses changed code?

| File | Usage | Impact |
|------|-------|--------|
| `scripts/vps/run-agent.sh` | Provider dispatch (3 callers: orchestrator, inbox-processor, qa-loop) | Add `gemini)` case branch |
| `scripts/vps/orchestrator.sh` | Main daemon (reads provider from DB) | Add spec frontmatter provider override |
| `scripts/vps/inbox-processor.sh` | Inbox dispatch (reads provider from DB) | Add `Provider:` header override from inbox file |
| `scripts/vps/telegram-bot.py` | Bot core (397 LOC) | Import admin_handler, register handlers |
| `scripts/vps/schema.sql` | DDL (64 LOC) | Add Gemini slot seed |
| `scripts/vps/setup-vps.sh` | VPS bootstrap (352 LOC) | Add --phase3 with skills copy, Gemini group, cache dir |
| `scripts/vps/db.py` | SQLite module (370 LOC) | Add `add_project()` function |

### Step 2: DOWN — dependencies

| Dependency | Notes |
|------------|-------|
| `gemini` CLI (`@google/gemini-cli`) | Headless: `gemini "PROMPT" --output-format json`, auth via `GEMINI_API_KEY` |
| `python-telegram-bot` v21.9+ | ConversationHandler for /addproject wizard |
| Nexus CLI (`bootstrap`) | Need `list-projects` + `get-project-context` subcommands (don't exist yet) |
| `flock` | POSIX, for projects.json write serialization |
| `cron` | Nexus cache refresh every 5 min |

### Step 3: BY TERM — grep

| Term | Occurrences | Key locations |
|------|-------------|---------------|
| `provider` | 28 | schema.sql:13,23,44; run-agent.sh:5,43; orchestrator.sh:175,185,204; db.py:58,164,185 |
| `addproject` | 0 | Does not exist yet |
| `nexus/bootstrap` | 5 | All in setup-vps.sh:247-266 (dead code — `list-projects` doesn't exist) |
| `gemini` | 0 | Does not exist yet |

### Step 4: CHECKLIST

- [x] `scripts/vps/` — 15 files, all analyzed
- [ ] `tests/` — no VPS tests exist
- [x] `schema.sql` — idempotent INSERT OR IGNORE for new slot
- [x] `.claude/rules/dependencies.md` — needs gemini-runner entry

### Verification

- [x] All found files added to Allowed Files
- [x] No collision with existing files

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `scripts/vps/run-agent.sh` — add `gemini)` case in provider dispatch
2. `scripts/vps/schema.sql` — add Gemini compute_slot seed
3. `scripts/vps/orchestrator.sh` — task-level provider routing from spec frontmatter
4. `scripts/vps/inbox-processor.sh` — read `Provider:` header from inbox file
5. `scripts/vps/telegram-bot.py` — import admin_handler, register ConversationHandler + /nexussync
6. `scripts/vps/setup-vps.sh` — add --phase3 flag (skills, gemini group, cache dir, Gemini CLI check)
7. `scripts/vps/db.py` — add `add_project()`, `get_nexus_cache()` functions
8. `scripts/vps/.env.example` — add GEMINI_API_KEY, GEMINI_PATH
9. `.claude/rules/dependencies.md` — add gemini-runner.sh + admin_handler.py entries

**New files allowed:**

1. `scripts/vps/gemini-runner.sh` — Gemini CLI headless wrapper
2. `scripts/vps/admin_handler.py` — /addproject ConversationHandler wizard
3. `scripts/vps/nexus-cache-refresh.sh` — cron script: Nexus → cache JSON files

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: true (SQLite — extend Phase 1 schema with Gemini slot)

---

## Blueprint Reference

**Domain:** Orchestrator (VPS infrastructure)
**Cross-cutting:** Multi-provider dispatch, project lifecycle management
**Data model:** project_state (existing), compute_slots (extend with gemini)

---

## Approaches

### Approach 1: Minimal (Devil-aligned)
**Source:** Devil scout — simpler alternatives
**Summary:** Task routing via projects.json only, single-line /addproject, no Gemini, Nexus setup-time-only.
**Pros:** ~135 LOC, minimal risk
**Cons:** No multi-provider, Nexus not SSOT

### Approach 2: Full Feature (User-aligned)
**Source:** External + Patterns + Codebase scouts
**Summary:** Gemini runner + spec frontmatter routing + ConversationHandler wizard + cached file Nexus SSOT + setup-vps.sh --phase3.
**Pros:** Full user vision, multi-provider, Nexus runtime SSOT
**Cons:** ~400 LOC, Nexus CLI prerequisite, 7 tasks

### Approach 3: Pragmatic
**Source:** Synthesis of all scouts
**Summary:** Like Approach 2 but /addproject single-line and Nexus on-demand only.
**Pros:** Balanced complexity
**Cons:** Less mobile-friendly, Nexus not auto-refresh

### Selected: 2

**Rationale:** User explicitly chose full feature set. Multi-provider is the core value (Gemini + Codex + Claude).
Nexus as SSOT aligns with user's stated goal ("данные постоянно теряются, нексус = SSOT").
ConversationHandler wizard prevents bad registrations on mobile.
Pre-requisite: fix Nexus CLI with `list-projects` subcommand before Task 6.

---

## Design

### User Flow

**Flow A: Task with Gemini Provider**

1. Spec file has frontmatter: `provider: gemini`
2. Orchestrator `scan_backlog` reads spec, finds `provider:` override
3. Override takes priority over project default
4. Dispatches to `gemini-runner` pueue group
5. `gemini-runner.sh` runs: `gemini "PROMPT" --output-format json --cwd $PROJECT_PATH`
6. Output parsed, callback fires, notification sent

**Flow B: Register New Project via Telegram**

1. User sends `/addproject` in any topic
2. Bot asks: "Enter project ID (e.g., `my-saas-app`):"
3. User replies: `my-saas-app`
4. Bot asks: "Enter absolute path on VDS:"
5. User replies: `/home/ubuntu/projects/my-saas-app`
6. Bot validates: path exists? git repo? → if not, retry
7. Bot asks: "Send this message in the project's forum topic (or enter topic_id):"
8. User sends message in correct topic → bot captures topic_id
9. Bot asks: "Default provider?" with inline keyboard: [Claude] [Codex] [Gemini]
10. User taps provider
11. Bot shows summary: "Register my-saas-app at /home/... topic 42, provider claude?" [Confirm] [Cancel]
12. Confirm → DB insert + pueue group create + Nexus cache refresh → "Project registered!"

**Flow C: Sync Nexus Data**

1. User sends `/nexussync` (or data refreshes via cron every 5 min)
2. `nexus-cache-refresh.sh` runs: `bootstrap list-projects --ids`
3. For each project: `bootstrap get-project-context $ID > /var/dld/nexus-cache/$ID.json`
4. Orchestrator reads cached files before task dispatch (deploy rules, secrets references)
5. If Nexus unavailable: last-known-good cache used (resilient)

**Flow D: Update Global Skills**

1. User updates DLD repo on VDS: `cd ~/dev/dld && git pull`
2. User runs: `bash setup-vps.sh --update-skills`
3. Script: `rsync -a --delete .claude/skills/ ~/.claude/skills/`
4. All 10 projects immediately use updated skills (Claude Code reads `~/.claude/skills/`)

### Architecture

```
Spec file (provider: gemini)
    ↓
orchestrator.sh scan_backlog()
    ↓
Provider override from frontmatter (or project default)
    ↓
run-agent.sh case dispatch
    ├── claude  → claude-runner.sh (flock OAuth)
    ├── codex   → codex-runner.sh
    └── gemini  → gemini-runner.sh (GEMINI_API_KEY)
         ↓
    pueue group: {provider}-runner
         ↓
    pueue-callback.sh → notify.py

/addproject (Telegram wizard)
    ↓
admin_handler.py ConversationHandler
    ↓
db.add_project() + pueue group add
    ↓
nexus-cache-refresh.sh (immediate for new project)

Nexus SSOT (cron every 5 min)
    ↓
nexus-cache-refresh.sh
    ↓
/var/dld/nexus-cache/{project_id}.json
    ↓
orchestrator.sh reads cache before dispatch
```

### Database Changes

```sql
-- Add Gemini compute slot (idempotent)
INSERT OR IGNORE INTO compute_slots (slot_number, provider) VALUES (4, 'gemini');
```

No new tables needed. `project_state.provider` already supports any string value.

---

## UI Event Completeness (REQUIRED for UI features)

| Producer (keyboard/button) | callback_data | Consumer (handler) | Handler File in Allowed Files? |
|---------------------------|---------------|-------------------|-------------------------------|
| Provider selection step | `addproject:provider:claude` | `handle_provider_select()` | `admin_handler.py` ✓ |
| Provider selection step | `addproject:provider:codex` | `handle_provider_select()` | `admin_handler.py` ✓ |
| Provider selection step | `addproject:provider:gemini` | `handle_provider_select()` | `admin_handler.py` ✓ |
| Confirmation step | `addproject:confirm` | `handle_confirm()` | `admin_handler.py` ✓ |
| Confirmation step | `addproject:cancel` | `handle_cancel()` | `admin_handler.py` ✓ |
| /nexussync command | — (CommandHandler) | `cmd_nexussync()` | `admin_handler.py` ✓ |

---

## Implementation Plan

### Research Sources
- [Gemini CLI Headless Mode](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/headless.md) — `--output-format json`, `GEMINI_API_KEY`
- [PTB ConversationHandler](https://docs.python-telegram-bot.org/en/v22.5/telegram.ext.conversationhandler.html) — multi-step wizard
- [Claude Code Skills Resolution](https://code.claude.com/docs/en/slash-commands) — `~/.claude/skills/` global scope
- [Nexus CLI + MCP Tools](~/dev/nexus) — `bootstrap` CLI, MCP `list_projects` tool
- [Claude Code Bridge](https://github.com/bfly123/claude_code_bridge) — per-runner architecture pattern

### Task 1: Nexus CLI Subcommands (PREREQUISITE — separate repo)
**Type:** code
**Repo:** `~/dev/nexus`
**Files:**
  - modify: `~/dev/nexus/src/app/cli/` — add `list-projects` and `get-project-context` subcommands
**Details:**
- Add `bootstrap list-projects [--ids] [--format json]` — wraps existing MCP tool `list_projects`
- Add `bootstrap get-project-context <project_id>` — wraps MCP tool `get_project_context`
- Both output JSON to stdout for `jq` parsing
- Fix dead code in `scripts/vps/setup-vps.sh:252` which calls non-existent `list-projects`
- Test: `bootstrap list-projects --format json | jq '.[] | .project_id'`
**Acceptance:** `bootstrap list-projects --format json` returns JSON array of projects. `bootstrap get-project-context test-project` returns JSON object.

### Task 2: Gemini Runner + Provider Extension
**Type:** code
**Files:**
  - create: `scripts/vps/gemini-runner.sh`
  - modify: `scripts/vps/run-agent.sh`
  - modify: `scripts/vps/schema.sql`
  - modify: `scripts/vps/.env.example`
**Pattern:** [Gemini CLI Headless Mode](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/headless.md)
**Details:**
- `gemini-runner.sh` (~45 LOC, modeled on codex-runner.sh):
  - Validate args: PROJECT_ID, SPEC_ID, PROJECT_DIR
  - `cd "$PROJECT_DIR"`
  - `GEMINI_API_KEY` from .env (no OAuth dance on VDS)
  - `gemini "$PROMPT" --output-format json --sandbox` (or equivalent flags)
  - Parse output: `jq -r '.response'` for result
  - Timeout: 1800s (same as Claude runner)
  - Exit codes: 0=success, 1=API error, 42=input error, 53=turn limit
- run-agent.sh: add `gemini)` case branch → exec `gemini-runner.sh`
- schema.sql: `INSERT OR IGNORE INTO compute_slots (slot_number, provider) VALUES (4, 'gemini');`
- .env.example: add `GEMINI_API_KEY=` and `GEMINI_PATH=` (optional, defaults to PATH lookup)
**Acceptance:** `bash run-agent.sh test-project TEST-001 /tmp/test gemini` → invokes gemini-runner.sh without errors (or exits with "gemini not found" if CLI not installed).

### Task 3: Task-Level Provider Routing
**Type:** code
**Files:**
  - modify: `scripts/vps/orchestrator.sh`
  - modify: `scripts/vps/inbox-processor.sh`
**Pattern:** [gabrielkoerich/orchestrator dispatch](https://github.com/gabrielkoerich/orchestrator)
**Details:**
- orchestrator.sh `scan_backlog()` (~10 LOC addition after line 175):
  ```bash
  # After: provider=$(python3 -c "...print(state['provider'])...")
  task_provider=$(grep -oE '^provider:\s+\w+' "$spec_file" 2>/dev/null | awk '{print $2}' || true)
  provider="${task_provider:-$provider}"
  ```
- inbox-processor.sh (~10 LOC addition after line 102):
  ```bash
  # Read Provider: header from inbox file
  file_provider=$(grep -oE '^Provider:\s+\w+' "$inbox_file" 2>/dev/null | awk '{print $2}' || true)
  provider="${file_provider:-$provider}"
  ```
- Validate provider exists in compute_slots: if unknown → log warning, fallback to project default
- Slot availability check works unchanged (`get_available_slots` already takes provider arg)
**Acceptance:** Spec with `provider: gemini` dispatches to gemini-runner group. Spec without `provider:` uses project default.

### Task 4: /addproject ConversationHandler Wizard
**Type:** code
**Files:**
  - create: `scripts/vps/admin_handler.py`
  - modify: `scripts/vps/telegram-bot.py`
  - modify: `scripts/vps/db.py`
**Pattern:** [PTB ConversationHandler](https://docs.python-telegram-bot.org/en/v22.5/telegram.ext.conversationhandler.html)
**Details:**
- `admin_handler.py` (~150 LOC):
  - States: `PROJECT_ID, PATH, TOPIC, PROVIDER, CONFIRM = range(5)`
  - `start_addproject(update, context)` — entry, asks for project_id
  - `receive_project_id(update, context)` — validate unique, store in user_data
  - `receive_path(update, context)` — validate exists + is git repo, store
  - `receive_topic(update, context)` — capture from current topic or manual input
  - `handle_provider_select(update, context)` — inline keyboard [Claude] [Codex] [Gemini]
  - `handle_confirm(update, context)` — db.add_project() + pueue group add + reply
  - `handle_cancel(update, context)` — cleanup user_data, reply "Cancelled"
  - `conversation_timeout=120` — auto-cleanup abandoned wizards
  - `cmd_nexussync(update, context)` — run nexus-cache-refresh.sh via subprocess
- db.py:
  - `add_project(project_id, path, topic_id, provider, auto_approve_timeout)` — INSERT OR IGNORE + seed compute slot
  - Validate: topic_id not already bound to another project
- telegram-bot.py changes (~10 LOC):
  - `from admin_handler import create_addproject_handler, cmd_nexussync`
  - Register ConversationHandler in `main()`
  - Register `/nexussync` CommandHandler
- flock on projects.json writes: `flock /tmp/projects-json.lock` to prevent race with orchestrator hot-reload
**Acceptance:** `/addproject` in Telegram → wizard walks through 5 steps → project appears in SQLite + pueue group created.

### Task 5: Global DLD Skills on VDS
**Type:** code
**Files:**
  - modify: `scripts/vps/setup-vps.sh`
**Pattern:** [Claude Code Skills Resolution](https://code.claude.com/docs/en/slash-commands)
**Details:**
- Add `--update-skills` flag to setup-vps.sh:
  ```bash
  update_skills() {
      local DLD_REPO="${DLD_REPO:-$HOME/dev/dld}"
      if [ ! -d "$DLD_REPO/.claude/skills" ]; then
          warn "DLD repo not found at $DLD_REPO"
          return 1
      fi
      mkdir -p ~/.claude/skills ~/.claude/rules
      rsync -a --delete "$DLD_REPO/.claude/skills/" ~/.claude/skills/
      cp "$DLD_REPO/.claude/rules/localization.md" ~/.claude/rules/localization.md 2>/dev/null || true
      ok "DLD skills synced to ~/.claude/skills/ ($(ls ~/.claude/skills/ | wc -l) skills)"
  }
  ```
- Also called during `--phase3` setup
- NOTE: Claude Code bugs #25209 and #16275 mean project-level overrides coexist with global (not replace). For VDS: no project-level skills → no conflict.
**Acceptance:** `bash setup-vps.sh --update-skills` → skills appear in `~/.claude/skills/`. `claude --cwd /any/project` sees global skills.

### Task 6: Nexus Cached File SSOT
**Type:** code
**Files:**
  - create: `scripts/vps/nexus-cache-refresh.sh`
  - modify: `scripts/vps/orchestrator.sh`
  - modify: `scripts/vps/db.py`
  - modify: `scripts/vps/setup-vps.sh`
**Pattern:** [Cache-file pattern from patterns scout](research-patterns.md#approach-4c)
**Details:**
- `nexus-cache-refresh.sh` (~40 LOC):
  ```bash
  #!/usr/bin/env bash
  set -euo pipefail
  CACHE_DIR="/var/dld/nexus-cache"
  mkdir -p "$CACHE_DIR"

  for pid in $(bootstrap list-projects --ids 2>/dev/null); do
      bootstrap get-project-context "$pid" \
          > "${CACHE_DIR}/${pid}.json.tmp" 2>/dev/null && \
          mv "${CACHE_DIR}/${pid}.json.tmp" "${CACHE_DIR}/${pid}.json"
  done
  ```
- Cron: `*/5 * * * * /path/to/nexus-cache-refresh.sh` (installed by setup-vps.sh)
- orchestrator.sh: before task dispatch, read cache:
  ```bash
  nexus_ctx=$(cat "/var/dld/nexus-cache/${PROJECT_ID}.json" 2>/dev/null || echo "{}")
  # Use for deploy rules, etc.
  ```
- db.py: `get_nexus_cache(project_id)` — reads JSON file, returns dict
- setup-vps.sh --phase3: create `/var/dld/nexus-cache/`, install cron entry
- Resilience: if Nexus down → stale cache used → log warning, continue
- `/nexussync` (Task 4) triggers immediate refresh
**Acceptance:** `bash nexus-cache-refresh.sh` → JSON files in `/var/dld/nexus-cache/`. Orchestrator reads cache without error. Nexus offline → stale cache used.

### Task 7: setup-vps.sh --phase3 + VPS Setup Checklist
**Type:** code
**Files:**
  - modify: `scripts/vps/setup-vps.sh`
  - modify: `.claude/rules/dependencies.md`
**Details:**
- Add `--phase3` flag to setup-vps.sh:
  1. Check Gemini CLI: `command -v gemini` or `GEMINI_PATH`
  2. Add pueue group: `pueue group add gemini-runner && pueue parallel 1 --group gemini-runner`
  3. Copy global skills: call `update_skills()` from Task 5
  4. Create Nexus cache dir: `/var/dld/nexus-cache/`
  5. Install cron for nexus-cache-refresh.sh
  6. Add GEMINI_API_KEY to .env if not present
  7. Verify: `gemini --version`, `bootstrap health`, skill count
- Update `.claude/rules/dependencies.md` with:
  - `gemini-runner.sh` uses/used-by
  - `admin_handler.py` uses/used-by
  - `nexus-cache-refresh.sh` uses/used-by
**Acceptance:** `bash setup-vps.sh --phase3` completes on fresh VDS. All checks pass. `pueue status` shows gemini-runner group.

### Execution Order

```
1 (Nexus CLI fix, separate repo) ──→ 6 (Nexus cache)
2 (Gemini runner) ──→ 3 (task-level routing)   ──→ 7 (setup + deps)
4 (/addproject) ─────────────────────────────────╯
5 (global skills) ──────────────────────────────╯
```

Dependencies:
- Task 3 needs Task 2 (gemini provider must exist for routing)
- Task 6 needs Task 1 (Nexus CLI subcommands must exist)
- Task 7 needs Tasks 2, 5, 6 (setup consolidates all)
- Tasks 1, 2, 4, 5 are independent of each other (can run in parallel)

---

## VPS Manual Setup Checklist

### Pre-Phase 3 (user's hands)

- [ ] FTR-146 (Phase 1) verified working on VDS
- [ ] FTR-147 (Phase 2) verified working on VDS
- [ ] Gemini CLI installed: `npm install -g @google/gemini-cli`
- [ ] Gemini authenticated: `GEMINI_API_KEY=xxx` in .env (get from Google AI Studio)
- [ ] Nexus CLI has `list-projects` command (Task 1 done)

### Phase 3 Setup (automated by setup-vps.sh --phase3)

- [ ] `bash setup-vps.sh --phase3`
  - Gemini CLI verified
  - `gemini-runner` pueue group created (parallel=1)
  - DLD skills copied to `~/.claude/skills/`
  - `localization.md` copied to `~/.claude/rules/`
  - `/var/dld/nexus-cache/` created
  - Cron installed for nexus-cache-refresh.sh
  - GEMINI_API_KEY verified in .env

### Post-Setup Verification

- [ ] `pueue status` shows: claude-runner, codex-runner, gemini-runner groups
- [ ] `ls ~/.claude/skills/` shows DLD skills (spark, autopilot, audit, etc.)
- [ ] `/nexussync` in Telegram → "Synced N projects"
- [ ] `/addproject` in Telegram → wizard starts
- [ ] Create test spec with `provider: gemini` → dispatches to gemini-runner group

---

## Flow Coverage Matrix (REQUIRED)

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | Spec has `provider: gemini` frontmatter | Task 3 | ✓ |
| 2 | Orchestrator reads provider override | Task 3 | ✓ |
| 3 | run-agent.sh dispatches to gemini-runner | Task 2 | ✓ |
| 4 | gemini-runner.sh calls Gemini CLI | Task 2 | ✓ |
| 5 | Gemini output parsed, callback fires | Task 2 | ✓ |
| 6 | Inbox file has `Provider:` header | Task 3 | ✓ |
| 7 | inbox-processor reads provider override | Task 3 | ✓ |
| 8 | User sends /addproject | Task 4 | ✓ |
| 9 | Bot asks for project_id | Task 4 | ✓ |
| 10 | Bot validates path (exists + git repo) | Task 4 | ✓ |
| 11 | Bot captures topic_id | Task 4 | ✓ |
| 12 | User selects provider via keyboard | Task 4 | ✓ |
| 13 | User confirms → DB + pueue group created | Task 4 | ✓ |
| 14 | DLD repo updated on VDS | Task 5 | ✓ |
| 15 | setup-vps.sh --update-skills syncs skills | Task 5 | ✓ |
| 16 | ~/.claude/skills/ available to all projects | Task 5 | ✓ |
| 17 | Cron refreshes Nexus cache every 5 min | Task 6 | ✓ |
| 18 | /nexussync triggers immediate refresh | Task 4, 6 | ✓ |
| 19 | Orchestrator reads cached Nexus context | Task 6 | ✓ |
| 20 | Nexus offline → stale cache used | Task 6 | ✓ |
| 21 | setup-vps.sh --phase3 installs everything | Task 7 | ✓ |
| 22 | Gemini CLI verified during setup | Task 7 | ✓ |

**GAPS:** None. All steps covered.

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Provider routing: spec override | spec with `provider: gemini` | Dispatches to gemini-runner group | deterministic | patterns 1A | P0 |
| EC-2 | Provider routing: no override | spec without `provider:`, project default=claude | Dispatches to claude-runner group | deterministic | devil DA-2 | P0 |
| EC-3 | Provider routing: unknown provider | spec with `provider: gpt5` | Falls back to project default, logs warning | deterministic | devil DA-3 | P0 |
| EC-4 | Gemini runner invocation | Valid project + spec | gemini-runner.sh calls `gemini` with correct flags | deterministic | external | P0 |
| EC-5 | Gemini runner: CLI not installed | GEMINI_PATH unset, gemini not in PATH | Exit with error "gemini not found", no crash | deterministic | devil | P0 |
| EC-6 | /addproject: valid wizard completion | All 5 steps filled correctly | DB entry created, pueue group exists, confirmation sent | deterministic | patterns 2B | P0 |
| EC-7 | /addproject: path not found | User enters `/nonexistent/path` | Bot replies "Path not found", stays on PATH step | deterministic | devil DA-5 | P0 |
| EC-8 | /addproject: duplicate project_id | project_id already in DB | Rejected with "already registered" | deterministic | devil DA-6 | P0 |
| EC-9 | /addproject: duplicate topic_id | topic_id bound to another project | Rejected with conflict error | deterministic | devil DA-7 | P1 |
| EC-10 | /addproject: wizard timeout | User starts but doesn't finish within 120s | Conversation cleaned up, no orphan state | deterministic | patterns | P1 |
| EC-11 | /addproject: pueue group created | Wizard completes | `pueue status` shows new group | deterministic | codebase risk 5 | P0 |
| EC-12 | Nexus cache: refresh works | bootstrap CLI available | JSON files in /var/dld/nexus-cache/ | deterministic | patterns 4C | P0 |
| EC-13 | Nexus cache: Nexus offline | bootstrap not available | Stale cache used, log warning, no crash | deterministic | devil DA-8 | P0 |
| EC-14 | /nexussync: immediate refresh | User sends /nexussync | Cache refreshed, reply "Synced N projects" | deterministic | user requirement | P1 |
| EC-15 | Global skills: visible in all projects | Skills in ~/.claude/skills/ | `claude --cwd /any/project` lists skills | deterministic | external | P1 |
| EC-16 | projects.json race condition | /addproject writes while orchestrator reads | No data corruption (flock) | deterministic | devil DA-11 | P0 |
| EC-17 | setup-vps.sh --phase3 | Fresh VDS after Phase 2 | Gemini group, skills, cache dir, cron all created | deterministic | user requirement | P1 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-18 | Gemini CLI installed + API key set | Submit spec with `provider: gemini` | Full cycle: dispatch → gemini-runner → callback → notification | integration | user requirement | P0 |
| EC-19 | /addproject wizard completed | Send task to new project's topic | Orchestrator picks up task, dispatches correctly | integration | patterns | P1 |
| EC-20 | Nexus cache populated | Orchestrator dispatches task | Pre-dispatch reads deploy rules from cache | integration | user requirement | P1 |

### Coverage Summary
- Deterministic: 17 | Integration: 3 | Total: 20

### TDD Order
1. EC-2 (default routing unchanged) → EC-1 (spec override) → EC-4 (gemini runner)
2. EC-6 (/addproject) → EC-7 (path validation) → EC-8 (duplicate)
3. EC-12 (cache refresh) → EC-13 (offline resilience)
4. Continue by priority (P0 first)

---

## Acceptance Verification (MANDATORY)

### Smoke Checks (process alive)

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Bot starts with admin_handler | `python3 telegram-bot.py` | No import errors, bot running | 10s |
| AV-S2 | Gemini runner syntax | `bash -n gemini-runner.sh` | Exit 0 | 2s |
| AV-S3 | Nexus cache refresh syntax | `bash -n nexus-cache-refresh.sh` | Exit 0 | 2s |
| AV-S4 | Schema applies cleanly | `sqlite3 /tmp/test.db < schema.sql` | No errors, gemini slot exists | 5s |

### Functional Checks (business logic)

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Provider routing override | Spec with `provider: gemini` | scan_backlog resolves provider | Returns "gemini" |
| AV-F2 | /addproject wizard | Bot running | Send /addproject, complete wizard | Project in DB |
| AV-F3 | Nexus cache | bootstrap CLI available | Run nexus-cache-refresh.sh | JSON files in cache dir |
| AV-F4 | Global skills | setup-vps.sh --update-skills | ls ~/.claude/skills/ | DLD skills present |

### Verify Command (copy-paste ready)

```bash
# Smoke
cd scripts/vps
python3 -c "import admin_handler; print('admin_handler OK')"
bash -n gemini-runner.sh && echo "gemini-runner syntax OK"
bash -n nexus-cache-refresh.sh && echo "cache-refresh syntax OK"
sqlite3 /tmp/test.db < schema.sql && sqlite3 /tmp/test.db "SELECT * FROM compute_slots WHERE provider='gemini'" && echo "schema OK"

# Functional: provider routing
python3 -c "
import db
db.DB_PATH = '/tmp/test.db'
# Test gemini slot exists
slots = db.get_available_slots('gemini')
assert slots >= 0, 'Gemini slot query failed'
print(f'gemini slots: {slots}')
print('routing OK')
"

# Functional: addproject (manual — run bot and test via Telegram)
# Functional: nexus cache (requires bootstrap CLI)
```

### Post-Deploy URL
```
DEPLOY_URL=local-only (VDS deployment after Phase 1+2 verified)
```

---

## Definition of Done

### Functional
- [ ] Gemini runner invokes Gemini CLI headlessly
- [ ] Task-level provider routing works (spec frontmatter override)
- [ ] /addproject wizard registers projects via Telegram
- [ ] Global DLD skills visible in all VDS projects
- [ ] Nexus cache refreshes automatically and on /nexussync
- [ ] Orchestrator reads Nexus cache before task dispatch
- [ ] setup-vps.sh --phase3 installs all Phase 3 components

### Tests
- [ ] All 20 eval criteria from ## Eval Criteria section pass
- [ ] Coverage not decreased

### E2E User Journey (REQUIRED for UI features)
- [ ] /addproject wizard: 5 steps → project registered → first task dispatches correctly
- [ ] Gemini spec: write spec with `provider: gemini` → dispatches to gemini-runner → callback → notification
- [ ] Nexus sync: /nexussync → cache refreshed → orchestrator uses cached context

### Acceptance Verification
- [ ] All Smoke checks (AV-S*) pass locally
- [ ] All Functional checks (AV-F*) pass locally
- [ ] Verify Command runs without errors

### Technical
- [ ] Tests pass (./test fast)
- [ ] No regressions
- [ ] telegram-bot.py stays under 400 LOC (handlers in admin_handler.py)
- [ ] gemini-runner.sh follows codex-runner.sh pattern
- [ ] Nexus cache is resilient to Nexus offline

---

## Autopilot Log
[Auto-populated by autopilot during execution]
