# Feature: [FTR-147] Multi-Project Orchestrator Phase 2: Architecture & Reliability

**Status:** queued | **Priority:** P0 | **Date:** 2026-03-10

## Why

Founder spends 50% of time manually finding bugs and poking Claude in its mistakes.
Phase 2 automates quality gates: Night Reviewer finds issues while founder sleeps,
voice inbox captures ideas on the go, QA fix loop closes the gap between "done" and "actually works".

## Context

- Phase 1 (FTR-146): Pueue + Telegram Bot + SQLite orchestrator (`in_progress`)
- **Hard gate:** FTR-147 cannot start until FTR-146 status = `done` and `/status` verified on live VDS
- Architecture: `ai/architect/multi-project-orchestrator.md` (committed as `c11e1b8`)
- Research: `ai/.spark/20260310-FTR-147/research-*.md` (4 files)
- User interview: 39 questions, all decisions documented

---

## Scope

**In scope:**
- Groq Whisper voice inbox (Telegram voice → text → ai/inbox/)
- Audit Night Mode (full project scan + finding dedup via SQLite)
- Evening review prompt (PTB JobQueue + project multi-select)
- Approve/Reject flow (per-finding Telegram messages + Spark dispatch)
- Claude OAuth safety (flock wrapper for race condition #27933)
- Global CLAUDE.md template for VDS
- Claude context switching verification (--cwd + CLAUDE.md hierarchy)
- Nexus read-only setup integration (project list at setup time)
- systemd exponential backoff + file-based logging

**Out of scope:**
- /addproject Telegram command (manual projects.json — Phase 3)
- Task-level LLM routing (project-level only)
- Web dashboard
- Digest notifications (individual messages for now)
- whisper.cpp local fallback (Groq is primary, text fallback on error)

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses changed code?

| File | Usage | Impact |
|------|-------|--------|
| `scripts/vps/telegram-bot.py` | Phase 1 bot core (389 LOC) | Add voice handler import, evening prompt, approve/reject handlers, night phase icons |
| `scripts/vps/db.py` | Phase 1 DB module (231 LOC) | Add finding CRUD functions |
| `scripts/vps/schema.sql` | Phase 1 DDL (46 LOC) | Add night_findings table |
| `scripts/vps/run-agent.sh` | Phase 1 provider dispatcher | Add flock OAuth wrapper |
| `scripts/vps/orchestrator.sh` | Phase 1 main loop | Night review scheduling hook |
| `.claude/skills/audit/SKILL.md` | Audit skill dispatcher | Add night mode trigger |
| `scripts/vps/requirements.txt` | Python deps | Add groq SDK |

### Step 2: DOWN — dependencies

| Dependency | Notes |
|------------|-------|
| `groq` Python SDK | Whisper STT endpoint |
| `claude` CLI | `--cwd` flag for project context |
| `flock` | POSIX, available on all Linux |
| PTB v21.9+ JobQueue | `run_daily`, APScheduler backend |
| SQLite | night_findings table |

### Step 3: BY TERM — grep

| File | Line | Context |
|------|------|---------|
| `telegram-bot.py` | 159 | `status_icon` dict — add `night_reviewing`, `night_pending` |
| `telegram-bot.py` | 51 | `ROUTE_PATTERNS` — no change needed (findings route as `spark_bug`) |
| `pueue-callback.sh` | 66 | `NEW_PHASE="qa_pending"` — night reviewer has own phase flow |
| `schema.sql` | all | No existing `night` or `finding` references |

### Step 4: CHECKLIST

- [x] `scripts/vps/` — Phase 2 extends Phase 1 files
- [x] `.claude/skills/audit/` — adds night-mode.md
- [x] `template/.claude/skills/audit/` — template sync copy
- [ ] `tests/vps/` — Phase 1 creates this; Phase 2 adds voice + findings tests

### Verification

- [x] All found files added to Allowed Files
- [x] No collision with existing files

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `scripts/vps/schema.sql` — add night_findings table
2. `scripts/vps/db.py` — add finding CRUD + QA iteration tracking
3. `scripts/vps/telegram-bot.py` — import handlers, register routes, add phase icons
4. `scripts/vps/requirements.txt` — add groq SDK
5. `scripts/vps/run-agent.sh` — add flock OAuth wrapper
6. `scripts/vps/orchestrator.sh` — add night review dispatch hook
7. `.claude/skills/audit/SKILL.md` — add night mode to mode detection

**New files allowed:**

1. `scripts/vps/voice_handler.py` — Groq Whisper STT + Telegram voice handler
2. `scripts/vps/night-reviewer.sh` — cron-triggered night scan orchestrator
3. `scripts/vps/approve_handler.py` — approve/reject callbacks + evening prompt + finding dispatch
4. `.claude/skills/audit/night-mode.md` — audit night mode protocol
5. `template/.claude/skills/audit/night-mode.md` — template sync copy
6. `scripts/vps/global-claude-md.template` — template for VDS global CLAUDE.md

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: true (SQLite — extend Phase 1 schema)

---

## Blueprint Reference

**Domain:** Orchestrator (VPS infrastructure), Audit (skill extension)
**Cross-cutting:** Process isolation (OAuth flock), quality gates (night reviewer + QA loop)
**Data model:** night_findings (new SQLite table)

---

## Approaches

### Approach 1: Rotating Zone Scanner
**Source:** Codebase scout — existing audit zones
**Summary:** One zone per night per project. Full coverage over a week.
**Pros:** Cheap, uses existing zones, simple
**Cons:** No "25→15→5" trend per night, week for full coverage

### Approach 2: Git-Diff Daily + Full on Demand
**Source:** Devil Alternative 1
**Summary:** Daily diff-only scan, full scan on manual trigger.
**Pros:** Very cheap ($0.10-0.50/night), no dedup needed for daily
**Cons:** Misses systemic issues, no improvement trend

### Approach 3: Full Project Scan + Smart Dedup
**Source:** External (Claude Code Security patterns) + Codebase (audit personas)
**Summary:** Full project scan each approved night. Finding dedup via SQLite fingerprinting.
Only NEW findings sent to Telegram. Trend: 25→15→5 as issues get fixed.
**Pros:** Matches user vision exactly, comprehensive, security patterns included
**Cons:** Most complex, needs dedup design, longer scans

### Selected: 3

**Rationale:** User's core goal is reducing manual bug-finding (50% of time). Only full project
scan shows the 25→15→5 improvement trend. Claude Max subscription = no per-token cost, only
session time (3 projects × 20 min = 1 hour, well within 5-hour window). Smart dedup via
SQLite fingerprinting is a one-time design cost that pays off every night.

---

## Design

### User Flow

**Flow A: Voice Idea**

1. Founder sends voice message in project's Telegram topic
2. Bot downloads .ogg file
3. `voice_handler.py` sends to Groq API (`whisper-large-v3`, `language="ru"`)
4. Transcribed text saved to `{project}/ai/inbox/{timestamp}-voice.md`
5. Keyword routing runs on transcribed text (same as text messages)
6. Bot replies: "Записано: {first 100 chars of transcription}"

**Flow B: Evening Review Prompt**

1. 22:00 Moscow time: PTB JobQueue fires `evening_prompt`
2. Bot sends to General topic: "Запустить ревью? Выбери проекты:"
3. Inline keyboard shows all projects with checkboxes (toggle on tap)
4. User selects projects, clicks "Start Review"
5. Bot confirms: "Ревью запланировано для N проектов"
6. night-reviewer.sh triggered (pueue job, separate from compute slots)

**Flow C: Night Review → Approve/Reject**

1. night-reviewer.sh iterates selected projects
2. For each project: `claude -p "/audit night" --cwd {project_path}`
3. Audit night mode scans: code bugs + architecture violations + security
4. Output: JSON array of findings with severity, file, line, description, suggestion
5. night-reviewer.sh parses findings → INSERT OR IGNORE into night_findings table
6. Only NEW findings (not in table) dispatched to Telegram
7. Each finding = separate message in project's topic with [Approve] [Reject] buttons
8. After all findings sent: batch message "Approve All / Reject All"
9. User taps Approve → finding written to `{project}/ai/inbox/` with `route: spark_bug`
10. Next orchestrator cycle: Spark processes → spec created → summary in Telegram → confirm → autopilot

**Flow D: QA Fix Loop**

1. Autopilot completes task → QA dispatch (Phase 1 qa-loop.sh)
2. QA finds bugs → each bug sent as individual Telegram message with [Approve] [Reject]
3. User approves → bug written to ai/inbox/ with route: spark_bug → Spark → Autopilot → QA again
4. User rejects → bug discarded
5. Loop terminates when: QA passes OR user stops approving fixes

### Architecture

```
Evening Prompt (22:00)
    ↓
Project Selection (Telegram multi-select)
    ↓
night-reviewer.sh (pueue job, separate group)
    ↓
For each project:
    claude --cwd {project} -p "/audit night"
    ↓
    JSON findings
    ↓
    SQLite dedup (INSERT OR IGNORE by fingerprint)
    ↓
    NEW findings → Telegram messages (per project topic)
    ↓
    [Approve] → ai/inbox/ (route: spark_bug)
    [Reject]  → status = rejected in SQLite
    ↓
    Next orchestrator cycle picks up inbox
    ↓
    Spark → spec → confirm → Autopilot → QA
```

### Database Changes

```sql
-- Finding deduplication store
CREATE TABLE IF NOT EXISTS night_findings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   TEXT NOT NULL REFERENCES project_state(project_id),
    fingerprint  TEXT NOT NULL,
    severity     TEXT NOT NULL DEFAULT 'medium',
    confidence   TEXT NOT NULL DEFAULT 'medium',
    file_path    TEXT,
    line_range   TEXT,
    summary      TEXT NOT NULL,
    suggestion   TEXT,
    status       TEXT NOT NULL DEFAULT 'new',
    message_id   INTEGER,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    reviewed_at  TEXT,
    UNIQUE(project_id, fingerprint)
);

```

**Finding fingerprint:** `SHA256(project_id + file_path + issue_type_normalized)`
- `issue_type_normalized` = first 3 words of description, lowercased (stable across reformulations)
- Does NOT include line number (shifts after fixes) or full description (changes between runs)

**Finding status values:**
- `new` — just discovered, not yet sent to Telegram
- `sent` — message sent, awaiting user action
- `approved` — user approved, written to inbox
- `rejected` — user rejected, will not resurface
- `fixed` — approved + Autopilot completed the fix

---

## UI Event Completeness (REQUIRED for UI features)

| Producer (button/keyboard) | callback_data | Consumer (handler) | Handler File in Allowed Files? |
|---------------------------|---------------|-------------------|-------------------------------|
| Evening prompt keyboard | `toggle:{project_id}` | `handle_project_toggle()` | `approve_handler.py` ✓ |
| Evening prompt keyboard | `launch_review` | `handle_launch_review()` | `approve_handler.py` ✓ |
| Finding message | `approve:{finding_id}` | `handle_approve()` | `approve_handler.py` ✓ |
| Finding message | `reject:{finding_id}` | `handle_reject()` | `approve_handler.py` ✓ |
| Batch message | `approve_all:{project_id}` | `handle_approve_all()` | `approve_handler.py` ✓ |
| Batch message | `reject_all:{project_id}` | `handle_reject_all()` | `approve_handler.py` ✓ |
| Spec confirm message | `confirm_spec:{spec_id}` | `handle_confirm_spec()` | `approve_handler.py` ✓ |

---

## Implementation Plan

### Research Sources
- [Groq Whisper API](https://console.groq.com/docs/speech-to-text) — endpoint, .ogg support, language param
- [Claude Code Security Pipeline](https://www.anthropic.com/news/claude-code-security) — severity+confidence, self-debate pattern
- [OAuth Race Condition #27933](https://github.com/anthropics/claude-code/issues/27933) — flock workaround
- [PTB Multi-Select Keyboards](https://medium.com/@moraneus/enhancing-user-engagement-with-multiselection-inline-keyboards-in-telegram-bots-7cea9a371b8d) — toggle pattern
- [systemd Exponential Backoff](https://enotty.pipebreaker.pl/posts/2024/01/how-systemd-exponential-restart-delay-works/) — RestartSteps v254+
- [QA Bug Fingerprinting](https://www.james-ralph.com/posts/2026-02-15-agentic-development-feedback.html) — hash dedup, max iterations

### Task 1: SQLite Schema Extension + DB Functions
**Type:** code
**Files:**
  - modify: `scripts/vps/schema.sql`
  - modify: `scripts/vps/db.py`
**Pattern:** [Groq Whisper API](https://console.groq.com/docs/speech-to-text)
**Details:**
- Add `night_findings` table (see Database Changes above)
- Add to db.py:
  - `save_finding(project_id, fingerprint, severity, confidence, file_path, line_range, summary, suggestion)` — INSERT OR IGNORE
  - `get_new_findings(project_id)` — SELECT WHERE status = 'new'
  - `update_finding_status(finding_id, status)` — UPDATE status, reviewed_at
  - `get_finding_by_id(finding_id)` — single finding lookup
  - `get_all_findings(project_id, status=None)` — filtered list
  - `get_projects_for_night_scan(project_ids)` — filter enabled projects by ID list
- Follow Phase 1 pattern: `PRAGMA busy_timeout=5000` per-connection, `BEGIN IMMEDIATE` for writes
**Acceptance:** `python3 -c "import db; print(db.save_finding('test', 'abc', 'high', 'high', 'f.py', '1-5', 'bug', 'fix'))"` → no error. Duplicate INSERT returns silently (OR IGNORE).

### Task 2: Groq Voice Handler
**Type:** code
**Files:**
  - create: `scripts/vps/voice_handler.py`
  - modify: `scripts/vps/telegram-bot.py`
  - modify: `scripts/vps/requirements.txt`
**Pattern:** [Groq Whisper API](https://console.groq.com/docs/speech-to-text)
**Details:**
- `voice_handler.py` (~80 LOC):
  - `transcribe_voice(ogg_bytes: bytes) -> str` — call Groq API
  - `handle_voice(update, context)` — PTB handler: download OGG → transcribe → _save_to_inbox → reply
  - Error handling: 429 → retry once after 2s, 5xx → reply "Voice unavailable, send text", missing GROQ_API_KEY → reply "Voice not configured"
  - Model: `whisper-large-v3`, `language="ru"`, `response_format="text"`
- telegram-bot.py changes:
  - `from voice_handler import handle_voice`
  - Register: `app.add_handler(MessageHandler(filters.VOICE & filters.ChatType.SUPERGROUP, handle_voice))`
- requirements.txt: add `groq>=0.5.0`
- Env: `GROQ_API_KEY` via .env (add to .env.example)
**Acceptance:** Send voice message in Telegram topic → bot replies with transcription → file appears in `ai/inbox/`.

### Task 3: Audit Night Mode Skill Extension
**Type:** code
**Files:**
  - create: `.claude/skills/audit/night-mode.md`
  - create: `template/.claude/skills/audit/night-mode.md`
  - modify: `.claude/skills/audit/SKILL.md`
**Pattern:** [Claude Code Security Pipeline](https://www.anthropic.com/news/claude-code-security)
**Details:**
- `night-mode.md` (~100 LOC):
  - **Trigger:** `/audit night`, cron via night-reviewer.sh
  - **Scope:** 2-3 personas (Coroner for code bugs/debt + Scout for security/integrations + optional Archaeologist for patterns)
  - **Skip Phase 0** (no codebase-inventory.mjs — too heavy for nightly)
  - **Output format:** JSON array, NOT prose report:
    ```json
    [
      {
        "severity": "high",
        "confidence": "high",
        "file": "src/billing/service.py",
        "line": "42-48",
        "issue_type": "sql_injection",
        "description": "f-string in SQL query allows injection",
        "suggestion": "Use parameterized query with ? placeholders"
      }
    ]
    ```
  - **Self-debate pattern** (from Claude Code Security): for each potential finding, argue for/against it being real. Only include if confidence ≥ medium.
  - **ADR-007/008/009/010 compliance:** persona subagents run in background, orchestrator collects via file gate
  - **Duration target:** 10-20 min per project (vs 30-60 for deep mode)
- SKILL.md changes: add `night` to Mode Detection table, add `night-mode.md` to Modules table
**Acceptance:** `claude -p "/audit night" --cwd /path/to/project` → outputs valid JSON array of findings.

### Task 4: Night Reviewer Script
**Type:** code
**Files:**
  - create: `scripts/vps/night-reviewer.sh`
  - modify: `scripts/vps/orchestrator.sh`
**Pattern:** [Cron Agent Pattern](https://dev.to/askpatrick/the-cron-agent-pattern-how-to-run-ai-agents-on-a-schedule-without-them-going-off-the-rails-4gma)
**Details:**
- `night-reviewer.sh` (~120 LOC):
  - Arguments: space-separated project IDs
  - PID file guard (prevent double-run)
  - For each project:
    1. `python3 db.py update-phase $PROJECT_ID night_reviewing`
    2. `flock /tmp/claude-oauth.lock claude -p "/audit night" --cwd $PROJECT_PATH --output-format json --max-turns 30`
    3. Parse JSON findings array from stdout
    4. For each finding: `python3 db.py save-finding $PROJECT_ID $FINGERPRINT ...` (INSERT OR IGNORE)
    5. `python3 db.py get-new-findings $PROJECT_ID` → list of unseen findings
    6. For each new finding: `python3 notify.py finding $PROJECT_ID "$FINDING_JSON"`
    7. `python3 db.py update-phase $PROJECT_ID idle`
  - Cleanup trap: `trap 'python3 db.py update-phase $PROJECT_ID idle' EXIT ERR`
  - Fail-safe: `set -uo pipefail`, every risky step with `|| true`
  - Runs as pueue job in separate group `night-reviewer` (parallel 1)
- orchestrator.sh changes:
  - Check for `.review-trigger` file (written by evening prompt handler)
  - If found: read project IDs from file, submit `night-reviewer.sh` to pueue group `night-reviewer`
  - Delete trigger file after submission
**Acceptance:** `bash night-reviewer.sh project1` → findings appear in SQLite + Telegram topic.

### Task 5: Evening Prompt + Approve/Reject Handlers
**Type:** code
**Files:**
  - create: `scripts/vps/approve_handler.py`
  - modify: `scripts/vps/telegram-bot.py`
**Pattern:** [PTB Multi-Select Keyboards](https://medium.com/@moraneus/enhancing-user-engagement-with-multiselection-inline-keyboards-in-telegram-bots-7cea9a371b8d)
**Details:**
- `approve_handler.py` (~150 LOC):
  - **Evening prompt:**
    - `register_evening_job(app)` — called from telegram-bot.py `post_init`
    - `evening_prompt(context)` — sends multi-select keyboard to General topic
    - `handle_project_toggle(update, context)` — toggle project in `context.bot_data["selected"]`
    - `handle_launch_review(update, context)` — write `.review-trigger` file with project IDs
    - Configurable time via `REVIEW_TIME` env var (default "22:00"), timezone `REVIEW_TZ` (default "Europe/Moscow")
  - **Approve/Reject:**
    - `handle_approve(update, context)` — mark finding approved → write to ai/inbox/
    - `handle_reject(update, context)` — mark finding rejected in SQLite
    - `handle_approve_all(update, context)` — approve all new findings for project
    - `handle_reject_all(update, context)` — reject all
    - `handle_confirm_spec(update, context)` — trigger autopilot for approved spec
  - **Finding message format:**
    ```
    [{severity}] {confidence}
    📁 {file}:{line}
    {description}

    💡 {suggestion}

    [Approve] [Reject]
    ```
  - **Batch message** (after all findings sent):
    ```
    Ревью {project}: {N} новых находок
    [Approve All] [Reject All]
    ```
- telegram-bot.py changes:
  - `from approve_handler import register_evening_job, handle_project_toggle, handle_launch_review, handle_approve, handle_reject, handle_approve_all, handle_reject_all, handle_confirm_spec`
  - Register all CallbackQueryHandlers with pattern matching
  - Add to `post_init`: `register_evening_job(app)`
  - Add night phase icons: `"night_pending": "🌙", "night_reviewing": "🔍", "night_failed": "💀"`
- Throttle: `asyncio.sleep(0.05)` between finding messages (Telegram rate limit)
**Acceptance:** Evening prompt appears at configured time. User selects projects. Review trigger file created. After review: individual messages with buttons appear. Approve → file in inbox.

### Task 6: Claude OAuth Safety + Context Switching
**Type:** code
**Files:**
  - modify: `scripts/vps/run-agent.sh`
  - create: `scripts/vps/global-claude-md.template`
**Pattern:** [OAuth Race Condition](https://github.com/anthropics/claude-code/issues/27933)
**Details:**
- run-agent.sh changes:
  - Wrap claude invocation with flock: `flock --timeout 120 /tmp/claude-oauth.lock ...`
  - flock serializes launches (OAuth refresh race prevention)
  - Each process holds lock only during startup (~5s), then releases
  - If lock timeout (120s) → log warning, proceed without lock (better than deadlock)
- `global-claude-md.template` (~30 LOC):
  ```markdown
  # VDS Global Rules

  ## Git Policy
  - Push only to `develop` branch. Never push to `main` directly.
  - Conventional Commits format.

  ## Quality Rules
  - Never mock in integration tests.
  - Tests must pass before committing.
  - Max 400 LOC per file (600 for tests).

  ## Orchestrator Awareness
  - This VDS runs up to 3 concurrent autopilot sessions.
  - Night reviewer runs independently — do not interfere with its processes.
  - Max session length: 30 turns.
  ```
- setup-vps.sh (Phase 1 Task 9) already creates systemd units. Phase 2 adds:
  - Copy global-claude-md.template → `~/.claude/CLAUDE.md` on VDS
  - Add GROQ_API_KEY to .env.example
  - Add pueue group `night-reviewer` with parallel=1
**Acceptance:** Two concurrent `run-agent.sh` invocations don't corrupt OAuth token. `claude --cwd /path/to/project` loads both global and project CLAUDE.md.

### Task 7: Nexus Read-Only Setup
**Type:** code
**Files:**
  - modify: `scripts/vps/orchestrator.sh` (or setup-vps.sh)
**Pattern:** Devil Alternative 3 — read-only, not runtime
**Details:**
- During `setup-vps.sh`:
  1. If `nexus` CLI available: `nexus list-projects --format json > /tmp/nexus-projects.json`
  2. Parse project list → generate `projects.json` entries
  3. User reviews + edits `projects.json` (adds topic_ids manually)
  4. If `nexus` not available: skip, use manual projects.json
- Secrets: `nexus get-secret GROQ_API_KEY --env prod` → write to .env
- No runtime Nexus dependency. No MCP server on VDS.
**Acceptance:** `setup-vps.sh` with Nexus installed → projects.json pre-populated. Without Nexus → manual setup still works.

### Task 8: systemd + Logging + Integration
**Type:** code
**Files:**
  - modify: `scripts/vps/orchestrator.sh` (or setup-vps.sh)
**Pattern:** [systemd Exponential Backoff](https://enotty.pipebreaker.pl/posts/2024/01/how-systemd-exponential-restart-delay-works/)
**Details:**
- systemd service files update (in setup-vps.sh):
  ```ini
  [Service]
  Restart=on-failure
  RestartSec=1s
  RestartMaxDelaySec=60s
  RestartSteps=5
  StartLimitBurst=10
  StartLimitIntervalSec=300s
  ```
- Add pueue group for night reviewer:
  ```bash
  pueue group add night-reviewer
  pueue parallel 1 --group night-reviewer
  ```
- File-based logging for orchestrator:
  - `LOG_DIR=/var/log/dld-orchestrator/`
  - Each run: `orchestrator-YYYY-MM-DD.log`
  - Log rotation: keep last 7 days
- Verify systemd version ≥ 254 (Ubuntu 24.04 = v255, Ubuntu 22.04 = v249 → flat RestartSec fallback)
**Acceptance:** `systemctl status dld-orchestrator` shows service with restart policy. Logs written to LOG_DIR.

### Execution Order

```
1 (schema) → 2 (voice) → 3 (audit night mode) → 4 (night reviewer) → 5 (approve/reject) → 6 (OAuth + context) → 7 (Nexus) → 8 (systemd)
```

Dependencies:
- Task 2 needs Task 1 (DB functions for inbox)
- Task 4 needs Task 1 (save_finding) + Task 3 (night-mode.md skill)
- Task 5 needs Task 1 (get_new_findings) + Task 4 (review trigger)
- Tasks 6, 7, 8 are independent of each other

---

## Flow Coverage Matrix (REQUIRED)

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | Founder sends voice message in topic | Task 2 | ✓ |
| 2 | Bot downloads OGG, sends to Groq | Task 2 | ✓ |
| 3 | Transcription saved to ai/inbox/ | Task 2 | ✓ |
| 4 | Bot replies with transcription preview | Task 2 | ✓ |
| 5 | Keyword routing on transcribed text | - | existing (Phase 1) |
| 6 | 22:00: Evening review prompt appears | Task 5 | ✓ |
| 7 | User selects projects via checkboxes | Task 5 | ✓ |
| 8 | User clicks "Start Review" | Task 5 | ✓ |
| 9 | Orchestrator picks up review trigger | Task 4 | ✓ |
| 10 | night-reviewer.sh runs for each project | Task 4 | ✓ |
| 11 | claude -p "/audit night" scans project | Task 3, 4 | ✓ |
| 12 | Findings parsed, deduped via SQLite | Task 1, 4 | ✓ |
| 13 | New findings sent as individual Telegram messages | Task 5 | ✓ |
| 14 | User taps Approve on finding | Task 5 | ✓ |
| 15 | Approved finding → ai/inbox/ with route: spark_bug | Task 5 | ✓ |
| 16 | Spark processes inbox → spec created | - | existing (Phase 1) |
| 17 | Spec summary sent to Telegram | - | existing (Phase 1) |
| 18 | User confirms spec → autopilot runs | Task 5 | ✓ |
| 19 | QA runs after autopilot | - | existing (Phase 1) |
| 20 | QA finds bug → sends to Telegram for approval | Task 5 | ✓ |
| 21 | User approves QA bug → inbox → Spark → fix | Task 5 | ✓ |
| 22 | OAuth refresh serialized via flock | Task 6 | ✓ |
| 23 | Global CLAUDE.md loaded on VDS | Task 6 | ✓ |
| 24 | Nexus populates projects.json at setup | Task 7 | ✓ |
| 25 | systemd restarts services with backoff | Task 8 | ✓ |

**GAPS:** None. All steps covered.

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Voice message transcription | 30s OGG Russian + English terms | Text file in ai/inbox/ containing recognizable words | deterministic | user requirement | P0 |
| EC-2 | Groq API failure fallback | Groq returns 5xx | Bot replies "Voice unavailable, send text", no crash | deterministic | devil DA-5 | P0 |
| EC-3 | Finding deduplication | Same finding inserted twice | Second INSERT ignored (UNIQUE constraint), no duplicate Telegram message | deterministic | devil DA-3 | P0 |
| EC-4 | Night reviewer only sends new findings | 25 findings night 1, 3 fixed, night 2 runs | Night 2 sends 0 new messages (22 existing + 3 fixed = 25 known) | deterministic | devil DA-3 | P0 |
| EC-5 | Evening prompt project selection | User toggles 3 of 10 projects | Review trigger file contains exactly 3 project IDs | deterministic | user requirement | P0 |
| EC-7 | Approve finding → inbox | User taps Approve on finding | File created in `{project}/ai/inbox/` with route: spark_bug | deterministic | user requirement | P0 |
| EC-8 | Reject finding → no inbox | User taps Reject | Finding status = rejected in SQLite, NO inbox file | deterministic | user requirement | P0 |
| EC-9 | OAuth flock serialization | 2 concurrent claude launches | Both complete without auth error (429/404 on token) | deterministic | devil DA-13, patterns 5B | P0 |
| EC-10 | Night reviewer crash cleanup | night-reviewer.sh killed mid-scan | Project phase reset to idle (trap fires) | deterministic | codebase risk 6 | P0 |
| EC-11 | Night findings table schema | CREATE TABLE statement | Has fingerprint UNIQUE constraint, all required columns | deterministic | codebase | P1 |
| EC-12 | Voice handler missing API key | GROQ_API_KEY unset | Bot replies "Voice not configured", no crash | deterministic | codebase risk 5 | P1 |
| EC-13 | Approve All / Reject All batch | User taps "Approve All" | All new findings for project marked approved, inbox files created | deterministic | user requirement | P1 |
| EC-14 | Night reviewer PID guard | Two concurrent night-reviewer.sh | Second exits with "already running" | deterministic | patterns Pattern 3 | P1 |
| EC-15 | Phase icons include night states | /status command after night review | Status shows night_reviewing with correct icon | deterministic | codebase impact | P1 |
| EC-16 | Global CLAUDE.md template valid | Cat global-claude-md.template | Contains git policy, quality rules, orchestrator awareness sections | deterministic | user requirement | P2 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-17 | Project registered, Groq key set | Send voice message in topic | Transcription appears in inbox, bot confirms | integration | user requirement | P0 |
| EC-18 | Night mode configured, 1 project | Evening prompt → select → start | Findings appear in Telegram topic as individual messages | integration | user requirement | P0 |
| EC-19 | Finding approved | Approve → wait for orchestrator cycle | Spark processes inbox → spec summary in Telegram | integration | user requirement | P1 |
| EC-20 | Full night cycle E2E | Evening → select → review → findings → approve → spark → autopilot | Complete cycle from review prompt to autopilot execution | integration | user requirement | P1 |

### Coverage Summary
- Deterministic: 15 | Integration: 4 | Total: 19

### TDD Order
1. EC-3 (dedup) → EC-11 (schema) → EC-1 (voice) → EC-5 (evening prompt) → EC-7 (approve)
2. Continue by priority (P0 first)

---

## Acceptance Verification (MANDATORY)

### Smoke Checks (process alive)

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Telegram bot starts with voice handler | `python3 telegram-bot.py` | No import errors, bot running | 10s |
| AV-S2 | Night reviewer script runs | `bash night-reviewer.sh test-project` | Exits 0 or with findings JSON | 300s |
| AV-S3 | SQLite schema applies cleanly | `sqlite3 orchestrator.db < schema.sql` | No errors, tables created | 5s |

### Functional Checks (business logic)

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Voice transcription | Set GROQ_API_KEY, send voice in topic | Bot replies with text | Transcription in inbox |
| AV-F2 | Finding dedup | Insert same finding twice | Second insert silently ignored | 1 row in table |
| AV-F3 | Evening prompt | Wait for configured time (or trigger manually) | Multi-select keyboard appears | Project list shown |
| AV-F4 | Approve finding | Tap Approve on finding message | Button removed, file in inbox | Inbox file exists |

### Verify Command (copy-paste ready)

```bash
# Smoke
cd scripts/vps && python3 -c "import voice_handler; import approve_handler; print('imports OK')"
sqlite3 /tmp/test.db < schema.sql && echo "schema OK"
bash -n night-reviewer.sh && echo "syntax OK"

# Functional
python3 -c "
import db
db.DB_PATH = '/tmp/test.db'
# Test dedup
db.save_finding('proj1', 'abc123', 'high', 'high', 'f.py', '1-5', 'bug desc', 'fix suggestion')
db.save_finding('proj1', 'abc123', 'high', 'high', 'f.py', '1-5', 'bug desc', 'fix suggestion')  # duplicate
findings = db.get_new_findings('proj1')
assert len(findings) == 1, f'Expected 1 finding, got {len(findings)}'
print('dedup OK')
"
```

### Post-Deploy URL
```
DEPLOY_URL=local-only (VDS deployment after Phase 1 verified)
```

---

## Definition of Done

### Functional
- [ ] Voice messages transcribed via Groq and saved to inbox
- [ ] Evening review prompt appears at configured time with project multi-select
- [ ] Night reviewer scans selected projects and produces individual findings
- [ ] Finding deduplication works (same finding not re-sent)
- [ ] Approve → inbox file created with route: spark_bug
- [ ] Reject → finding marked rejected, not resurfaced
- [ ] OAuth race condition prevented via flock

### Tests
- [ ] All 19 eval criteria from ## Eval Criteria section pass
- [ ] Coverage not decreased

### E2E User Journey (REQUIRED for UI features)
- [ ] Voice message → transcription → inbox → routing (full path)
- [ ] Evening prompt → project selection → review → findings → approve → spec → autopilot (full path)
- [ ] QA loop: autopilot → QA fail → bug to Telegram → user approves → fix (human-in-the-loop verified)

### Acceptance Verification
- [ ] All Smoke checks (AV-S*) pass locally
- [ ] All Functional checks (AV-F*) pass locally
- [ ] Verify Command runs without errors

### Technical
- [ ] Tests pass (./test fast)
- [ ] No regressions
- [ ] telegram-bot.py stays under 400 LOC (handlers extracted to voice_handler.py + approve_handler.py)
- [ ] night-reviewer.sh has fail-safe traps (phase reset on crash)

---

## Autopilot Log
[Auto-populated by autopilot during execution]
