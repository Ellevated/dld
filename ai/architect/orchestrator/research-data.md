# Data Architecture Research — Multi-Project Orchestrator

**Persona:** Martin (Data Architect)
**Focus:** Schema, migrations, data flows, system of record
**Date:** 2026-03-10

---

## Research Conducted

- [Filesystem vs. Database for Agent Memory](https://andersswanson.dev/2026/01/22/filesystem-vs-database-for-agent-memory/) — filesystem dominates coding agents; DB wins for concurrent/shared state
- [Comparing File Systems and Databases for AI Agent Memory](https://building.theatlantic.com/comparing-file-systems-and-databases-for-effective-ai-agent-memory-management-5322ac45f3b6) — polyglot persistence anti-pattern; shared state demands DB
- [~/.claude.json corruption from concurrent instances](https://github.com/anthropics/claude-code/issues/29158) — **CRITICAL**: 335 corruption events in 7 days; non-atomic JSON write race confirmed
- [Crash-safe JSON at scale: atomic writes + recovery](https://dev.to/constanta/crash-safe-json-at-scale-atomic-writes-recovery-without-a-db-3aic) — atomic write pattern (fsync + os.replace) makes JSON safe at human-cadence writes
- [GitHub Issues as agent context architecture](https://www.asklar.dev/ai/engineering/architecture/2025/12/20/context-architecture-for-agent-systems) — GitHub primitives (Issues, PRs) replace memory-bank for persistent agent context
- [Building an agentic memory system for GitHub Copilot](https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot/) — cross-agent memory: what to remember and when to forget
- [WCP — Work Context Protocol](https://github.com/dpaola2/work-context-protocol) — structured agent task context across sessions via MCP (Feb 2026)
- [SQLite Production Applications Guide](https://blogs.pavanrangani.com/sqlite-production-modern-applications-guide/) — WAL mode, busy_timeout, production config patterns
- [Introducing issy: AI-native Issue Tracking](https://mike.gg/issy) — markdown files in `.issy/` as portable issue store; no DB, no vendor lock-in
- [AI Agent Orchestration Patterns (Azure)](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns) — orchestrator state management patterns

**Total queries:** 9 web searches, targeting all six key questions from the agenda.

---

## Kill Question Answer

**"What is the system of record for each entity in this architecture?"**

| Entity | System of Record | Justification |
|--------|-----------------|---------------|
| Project registry (name, path, topic_id, priority) | `projects.json` on VPS filesystem | Human-edited config. Single writer (operator). Read at startup + hot-reload. No concurrency risk on writes. |
| Project runtime state (phase, current task, PID) | SQLite `orchestrator.db` | Written by orchestrator daemon, read by bot + CLI. Concurrent readers. Crash recovery critical. |
| Inbox items (text/voice/screenshot ideas) | `ai/inbox/` per-project filesystem | Already the DLD standard. Claude agents read from here natively. No change needed. |
| Transcription output | Flat file alongside audio in `ai/inbox/` | Derived from audio. One-to-one mapping. Git-trackable. |
| Screenshot context | Flat file in `ai/inbox/` | Same as transcription — binary blob stays as file, text description written alongside. |
| Project context for agents | `CLAUDE.md` per project (existing DLD) | Already the industry standard. Claude Code reads this on session start. |
| Project portfolio context (cross-project) | GitHub Issue (pinned) per project | Structured, API-accessible, version-controlled history via comments. |
| Agent task history | GitHub Issue comments + DLD `ai/features/` | Durable, searchable, human-readable. No separate DB table needed. |
| Orchestrator configuration | `projects.json` | Config is not state. Separate concerns. |
| API usage / budget | SQLite `orchestrator.db` | Append-only ledger. Needs queries. Cannot be JSON. |

**Conflicts identified:**
- The existing spec conflates config (`projects.json`) and runtime state (`.orchestrator-state.json`) — both are JSON, both are on the same VPS. The state file is written by the daemon on every cycle, making it a high-frequency concurrent-write target. This is the same pattern that caused 335 corruption events in the Claude Code `~/.claude.json` bug (GitHub #29158). This conflict must be resolved by splitting concerns: JSON for config (human-writes, rare), SQLite for state (daemon-writes, frequent).

---

## Proposed Data Decisions

### Core Schema Model

**Entity Relationship Diagram:**

```
projects.json (config, human-written)
    │
    │ 1:N (at startup, loaded into memory)
    ▼
┌─────────────────────┐      ┌──────────────────────────┐
│  projects           │      │  runtime_state            │
│  (SQLite)           │      │  (SQLite, daemon-written) │
│  ─────────────      │      │  ─────────────────────── │
│  id (slug)          │─1:1─▶│  project_id FK            │
│  name               │      │  phase                    │
│  path               │      │  current_task             │
│  topic_id           │      │  claude_pid               │
│  github_repo        │      │  slot_acquired_at         │
│  priority           │      │  last_checked_at          │
│  enabled            │      │  updated_at               │
└─────────────────────┘      └──────────────────────────┘
         │
         │ 1:N
         ▼
┌─────────────────────┐      ┌──────────────────────────┐
│  usage_ledger       │      │  inbox_items              │
│  (SQLite,           │      │  (filesystem per-project) │
│   append-only)      │      │  ────────────────────── │
│  ─────────────      │      │  ai/inbox/{timestamp}.md  │
│  project_id FK      │      │  ai/inbox/{ts}.ogg (raw)  │
│  event_type         │      │  ai/inbox/{ts}.txt (xcrpt)│
│  claude_tokens      │      │  ai/inbox/{ts}.png (img)  │
│  cost_usd           │      │  ai/inbox/{ts}-ctx.md     │
│  occurred_at        │      └──────────────────────────┘
└─────────────────────┘

GitHub (external SoR for project context narrative):
┌──────────────────────────────────────────────────────┐
│  Pinned Issue per project                            │
│  ─────────────────────────────────                  │
│  Title: [project-name] Context                       │
│  Body: current blueprint, architecture decisions     │
│  Labels: context, active/paused                      │
│  Comments: append-only history of major decisions    │
└──────────────────────────────────────────────────────┘
```

---

### Storage Layer Decisions

#### Decision 1: `projects.json` stays as JSON (config, not state)

**Verdict: Keep JSON. But strictly separate from state.**

Rationale:
- Written only by human operator (or `/addproject` bot command)
- Frequency: human-cadence (maybe 1x/day)
- Size: < 50 projects = < 10KB forever
- Benefits: human-readable, git-committable, grep-able, zero dependency
- Required change: atomic writes via `write → temp file → os.rename()`. This eliminates the corruption risk.

```json
// projects.json — config only, no runtime state
{
  "version": 1,
  "chat_id": -1001234567890,
  "max_concurrent_claude": 2,
  "projects": [
    {
      "id": "saas-app",
      "name": "SaaS App",
      "topic_id": 5,
      "path": "/home/user/saas-app",
      "github_repo": "user/saas-app",
      "priority": "high",
      "poll_interval": 300,
      "enabled": true,
      "created_at": "2026-03-10T00:00:00Z"
    }
  ]
}
```

**What moves OUT of projects.json:** Everything that changes at runtime (phase, current task, PID, last_check). Those go to SQLite.

---

#### Decision 2: Replace `.orchestrator-state.json` with SQLite

**Verdict: SQLite for all runtime state. Non-negotiable.**

The existing `.orchestrator-state.json` is written every orchestrator cycle (every 60-300 seconds per project). With 5 projects and 60s cycles, that is 5 concurrent write attempts per minute to the same JSON file. This is exactly the race condition pattern documented in Claude Code GitHub #29158 (335 corruptions in 7 days). The orchestrator runs as a daemon — it cannot afford state corruption at 3am.

SQLite with WAL mode gives:
- Single-writer, multiple-reader concurrency (bot reads while daemon writes)
- Crash recovery built into the WAL format
- `busy_timeout = 5000` prevents deadlock
- Atomic transactions: acquire slot + update state in one `BEGIN IMMEDIATE`
- Query power: "which projects have been idle > 30 minutes?" is one SQL line, not a bash loop

**Schema:**

```sql
-- Required pragmas on every connection
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

-- Project runtime state (mirrors projects.json but mutable)
CREATE TABLE project_state (
    project_id      TEXT PRIMARY KEY,       -- matches projects.json "id"
    phase           TEXT NOT NULL DEFAULT 'idle'
                    CHECK (phase IN ('idle', 'inbox', 'spark', 'autopilot', 'qa', 'paused', 'error')),
    current_task    TEXT,                   -- e.g. "FTR-042"
    claude_pid      INTEGER,               -- NULL if no process running
    slot_number     INTEGER,               -- 1 or 2 (semaphore slot)
    slot_acquired_at TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ,
    last_error      TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- API usage ledger: append-only, never UPDATE
CREATE TABLE usage_ledger (
    id              TEXT PRIMARY KEY,       -- UUID v4
    project_id      TEXT NOT NULL,
    event_type      TEXT NOT NULL CHECK (event_type IN (
                        'claude_session_start',
                        'claude_session_end',
                        'whisper_transcription',
                        'telegram_api_call'
                    )),
    claude_tokens_in  INTEGER,
    claude_tokens_out INTEGER,
    cost_usd_cents    INTEGER,             -- cents to avoid float
    duration_seconds  INTEGER,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_usage_project_date
    ON usage_ledger(project_id, occurred_at);

-- Semaphore state (replaces flock — more introspectable)
CREATE TABLE claude_slots (
    slot_number     INTEGER PRIMARY KEY CHECK (slot_number IN (1, 2)),
    project_id      TEXT,                  -- NULL = free
    acquired_at     TIMESTAMPTZ,
    pid             INTEGER
);

-- Pre-populate slots
INSERT INTO claude_slots (slot_number) VALUES (1), (2);
```

**Semaphore via SQLite (replaces flock):**

```sql
-- Acquire slot atomically
BEGIN IMMEDIATE;
UPDATE claude_slots
SET project_id = ?, acquired_at = CURRENT_TIMESTAMP, pid = ?
WHERE slot_number = (
    SELECT slot_number FROM claude_slots
    WHERE project_id IS NULL
    LIMIT 1
)
AND project_id IS NULL;
-- If rows_affected = 0: no slot available, retry
COMMIT;

-- Release slot
UPDATE claude_slots SET project_id = NULL, acquired_at = NULL, pid = NULL
WHERE project_id = ?;
```

This replaces the `flock` semaphore with something that survives process crashes (no stale lock files), is visible to the Telegram bot for status queries, and can be debugged with `sqlite3 orchestrator.db "SELECT * FROM claude_slots"`.

---

#### Decision 3: Inbox stays per-project filesystem

**Verdict: Keep `ai/inbox/` per-project. Do not centralize.**

Rationale:
- DLD agents already read from `ai/inbox/` natively — this is load-bearing convention
- Claude Code sessions are run with `cwd = project_path` — relative paths work
- Filesystem is the natural format for binary blobs (audio, images)
- Git provides history for text inbox items if the project uses it

**Inbox file naming convention (standardized):**

```
ai/inbox/
├── 20260310-143022-voice.ogg          # raw audio (Telegram voice message)
├── 20260310-143022-voice.txt          # Whisper transcription output
├── 20260310-143022-idea.md            # assembled inbox item for DLD processing
├── 20260310-151500-screenshot.png     # raw screenshot
├── 20260310-151500-screenshot-ctx.md  # text context written by vision model
└── 20260310-151500-idea.md            # assembled inbox item
```

**Assembly pattern:** The bot handler assembles a final `.md` inbox item that combines text/transcription/screenshot-context into a single DLD-readable file. The raw binary stays alongside for audit/replay.

**Inbox item schema (the `.md` file DLD agents read):**

```markdown
---
id: 20260310-143022
source: voice
project: saas-app
telegram_message_id: 99821
received_at: 2026-03-10T14:30:22Z
has_audio: true
has_screenshot: false
---

# Inbox Item

Transcription: "Add a retry mechanism to the billing webhook handler,
it's dropping events when Stripe has a timeout."

Raw audio: ai/inbox/20260310-143022-voice.ogg
```

This structure is DLD-compatible (spark reads it), git-trackable (text only), and auditable (raw binary available).

---

#### Decision 4: Voice transcription storage

**Verdict: Flat file pair. No DB record needed.**

Pattern: `{timestamp}-voice.ogg` + `{timestamp}-voice.txt`

- `.ogg` is the Telegram voice file (downloaded by bot)
- `.txt` is the Whisper output (plain text, no metadata)
- The assembled `-idea.md` file contains the transcription inline plus a reference to the raw files
- Whisper runs locally on VPS (`whisper.cpp` or `faster-whisper`) — no cloud upload
- Retention: keep both files for 30 days, then purge audio; keep `.txt` indefinitely

Why not DB? Because:
1. Transcription is one-to-one with the audio file — no join queries needed
2. Full-text search on transcriptions is done by `grep` / Claude's file tools
3. SQLite TEXT column for transcription adds zero benefit over a `.txt` file at this scale

---

#### Decision 5: Screenshot storage

**Verdict: Flat file pair. Vision model writes context alongside.**

Pattern: `{timestamp}-screenshot.png` + `{timestamp}-screenshot-ctx.md`

When a screenshot arrives via Telegram:
1. Bot downloads PNG to `ai/inbox/`
2. Bot calls vision model (Claude Haiku) with the image
3. Model outputs a text description: "Screenshot shows the Stripe dashboard. Error: 'Webhook delivery failed for endpoint...' with a 404 status. The endpoint URL shown is..."
4. That text is written to `-screenshot-ctx.md`
5. The assembled `-idea.md` embeds the text description and references the PNG

Why vision model at ingest time, not at agent-processing time? Because:
- Claude Code agents called later may not have vision tool available in all contexts
- Text description is searchable, Git-trackable, and reusable across sessions
- One vision call per screenshot at ingest is cheaper than repeated calls in every future agent session

---

#### Decision 6: GitHub Issues as data layer

**Verdict: GitHub Issues for project context narrative. Not for operational state.**

The Сережа Рис pattern — using a pinned GitHub Issue as the project's "living document" — is the right call for a specific use case: **human-readable, version-controlled project context** that agents can read via `gh` CLI.

What works well:
- Pinned issue body = current blueprint summary (what DLD agents should know about this project)
- Comments = append-only history of architectural decisions, major pivots, completed milestones
- Labels = project status (`active`, `paused`, `blocked`)
- The `gh` CLI makes this readable by Claude Code: `gh issue view 1 --repo user/project`

What does NOT work as GitHub Issues:
- Operational state (phase, current task, PID) — too slow for 60s polling cycles
- Inbox items — binary files cannot be stored in Issues
- API usage ledger — requires aggregation queries

**Pinned Issue schema (body template):**

```markdown
## Project Context: SaaS App

**Status:** Active | Phase: Autopilot
**Last Updated:** 2026-03-10

### Current Focus
Building billing webhook retry mechanism (FTR-042)

### Architecture Decisions
- Stack: Python 3.12 + FastAPI + PostgreSQL
- Auth: Clerk
- Payments: Stripe

### Active Constraints
- Max 2 concurrent Claude sessions (shared VPS resource)
- QA gate required before any billing changes ship

### History (append comments below, never edit this body)
```

**Integration with orchestrator:**
- Orchestrator updates the Issue label when project phase changes (via `gh label add`)
- Major completions are posted as comments (via `gh issue comment`)
- The `/status` bot command reads from SQLite (fast), not GitHub (slow API)
- The `/context` bot command fetches the pinned Issue body for human review

---

### Data Flow Architecture

**Flow Diagram:**

```
Telegram Message (voice/text/screenshot)
    │
    ▼
[telegram-bot.py]
    │
    ├── extract thread_id
    ├── lookup project from projects.json (in-memory)
    │
    ├── if voice: download .ogg → whisper → .txt → assemble -idea.md
    ├── if screenshot: download .png → vision model → -ctx.md → assemble -idea.md
    └── if text: write directly as -idea.md
    │
    ▼
[ai/inbox/{project}/] ← per-project filesystem (SoR for inbox items)
    │
    ▼
[orchestrator.sh] ← event loop (reads SQLite for state, reads filesystem for inbox)
    │
    ├── reads project_state from SQLite
    ├── if inbox has unprocessed items → run inbox-processor (spark)
    ├── if backlog has queued items → acquire slot → run autopilot
    │   └── slot acquisition: BEGIN IMMEDIATE on claude_slots table
    │
    ├── writes back to project_state (phase, current_task, updated_at)
    └── appends to usage_ledger
    │
    ▼
[Claude Code process] ← runs in project_path, reads CLAUDE.md + ai/inbox/
    │
    └── writes: ai/features/, ai/backlog.md, src/ code changes
    │
    ▼
[Post-completion]
    ├── orchestrator updates project_state phase → 'idle'
    ├── releases claude_slots entry
    └── optionally: gh issue comment (major milestone)

GitHub Issues (external, async, non-critical path):
    ├── pinned issue body: read by /context command
    └── comments: append-only audit trail
```

**Consistency model per flow segment:**

| Segment | Pattern | Consistency | Justification |
|---------|---------|-------------|---------------|
| Telegram → inbox files | Sync write | Strong (local FS) | File must exist before orchestrator runs |
| Slot acquisition | SQLite BEGIN IMMEDIATE | ACID | Lost update = two Claude processes, OOM risk |
| State update | SQLite UPDATE | ACID | Phase must be consistent for status commands |
| Usage ledger insert | SQLite INSERT | ACID | Financial data, idempotency key prevents duplication |
| GitHub Issue update | Async, non-blocking | Eventual | Audit trail, not operational state |
| projects.json write | Atomic rename (os.replace) | Strong | Config must never be half-written |

---

### Migration Strategy

**Approach:** Expand-Contract in two phases.

**Phase 1 — Bootstrap (Day 1):**
The existing spec has no DB. Adding SQLite from the start is expand (not migrate).
Steps:
1. Create `orchestrator.db` with schema above at first startup
2. Load `projects.json` → seed `project_state` rows (all `phase = 'idle'`)
3. Pre-populate `claude_slots` with 2 rows
4. Remove `.orchestrator-state.json` on first successful DB write

**Phase 2 — Schema evolution (future):**
Use numbered migration files: `migrations/001_initial.sql`, `migrations/002_add_github_integration.sql`
Applied at orchestrator startup via `user_version` PRAGMA:
```sql
PRAGMA user_version;  -- check current version
-- if < target: apply next migration
PRAGMA user_version = N;  -- bump after applying
```

**Rollback:** Keep `projects.json` as the authoritative project list forever. If SQLite corrupts, delete `orchestrator.db` and rebuild from `projects.json` + filesystem scan. The DB holds only ephemeral state — no data is permanently lost by a full DB drop.

**Zero-downtime:** The orchestrator is single-process, single-VPS. There is no zero-downtime requirement — a 5-second restart is acceptable. Schema changes are applied at startup before the event loop begins.

---

### Consistency & Transactions

**Transaction Boundaries:**

| Operation | Scope | Pattern | Justification |
|-----------|-------|---------|---------------|
| Acquire Claude slot | Single SQLite TX | ACID (BEGIN IMMEDIATE) | Race condition = two processes = OOM |
| Release Claude slot + update phase | Single SQLite TX | ACID | Must be atomic: release then update is wrong order |
| Insert usage ledger entry | Single row INSERT | ACID | Append-only, idempotency via event UUID |
| projects.json write | File atomic rename | Strong | Config corruption = orchestrator cannot start |
| Inbox file write | Single file write (already atomic on Linux for small writes; use rename for large) | Strong | Must be complete before orchestrator reads it |
| GitHub Issue update | Async HTTP | Eventual | Non-critical, retry on failure |

**Invariants to Maintain:**

1. **Slot count invariant:** `COUNT(*) WHERE project_id IS NOT NULL` in `claude_slots` must never exceed `max_concurrent_claude` from projects.json. Enforced by SQLite transaction, not application logic.

2. **Phase machine invariant:** `project_state.phase` transitions must follow the state machine: `idle → inbox → spark → autopilot → qa → idle` (or error at any point). No skipping states without an error record.

3. **Inbox file completeness:** An assembled `-idea.md` file is only written after all component files (`.txt` transcription, `-ctx.md` screenshot description) are fully written. Bot handler: write components first, write `-idea.md` last. Orchestrator: only processes `-idea.md` files (never raw audio/screenshot directly).

4. **projects.json is read-only to the daemon:** Only the bot `/addproject` and `/removeproject` commands write to projects.json, using atomic rename. The orchestrator daemon reads it at startup and on inotifywait event. It never writes to it.

---

## Cross-Cutting Implications

### For Domain Architecture
- The split between `projects.json` (config) and `orchestrator.db` (state) maps cleanly to the separation of "Project Registry" domain vs "Execution Engine" domain
- `ai/inbox/` is the bounded context boundary between the "Input" domain (Telegram bot) and the "Processing" domain (DLD agents) — nothing crosses except the assembled `-idea.md` files
- GitHub Issues as context store creates a weak coupling to GitHub — if GitHub is unavailable, the orchestrator continues running; Issues are degraded functionality, not critical path

### For API Design
- The Telegram bot's `/status` command reads from SQLite only (< 1ms, no external calls)
- The Telegram bot's `/context` command reads from GitHub Issues (500ms, acceptable for human-triggered)
- The Telegram bot's `/budget` command queries `usage_ledger` by month: `SELECT SUM(cost_usd_cents) FROM usage_ledger WHERE project_id = ? AND occurred_at >= ?`

### For Agent Architecture
- Claude Code agents receive project context via `CLAUDE.md` (existing DLD mechanism, unchanged)
- Agents do not need to query the SQLite DB — that is orchestrator infrastructure, invisible to agents
- The pinned GitHub Issue provides supplemental context accessible via `gh issue view` tool call
- Voice transcriptions and screenshot descriptions flow into agent sessions via the standard `ai/inbox/` → spark pipeline

### For Operations
- SQLite DB file: daily backup via `sqlite3 orchestrator.db ".backup /backup/orchestrator-$(date +%Y%m%d).db"`
- `projects.json` committed to a private git repo — full history, trivial rollback
- Inbox files: per-project, backed up with project git repo (text files) or periodic rsync (binary files)
- DB size: at 5 projects × 30 cycles/hour × 24 hours = 3,600 state updates/day. At 100 bytes/row, that is 360KB/day for state. Usage ledger grows at ~50 rows/day. 1 year of operation ≈ 5MB total. No archival needed for years.

---

## Concerns & Recommendations

### Critical Issues

- **`.orchestrator-state.json` race condition**: The existing spec writes a JSON state file every orchestrator cycle. With concurrent Claude processes running and the Telegram bot also reading state, this is the exact race that caused 335 corruptions in the Claude Code `~/.claude.json` (GitHub #29158). The fix is mandatory: SQLite for all daemon-written state.
  - **Fix:** Replace `.orchestrator-state.json` with `orchestrator.db` as specified above.
  - **Rationale:** "Data outlives code." A corrupted state file at 3am means the orchestrator cannot tell which Claude processes are running, cannot acquire slots safely, and may launch duplicate processes that OOM the VPS.

- **flock semaphore is not introspectable or crash-safe**: Stale lock files survive crashes. The orchestrator cannot query "which projects currently hold a slot" without scanning `/tmp/claude-semaphore/`. If the VPS reboots mid-autopilot, flock files in `/tmp/` vanish — but the orchestrator has no record of what was running.
  - **Fix:** SQLite `claude_slots` table as specified. On startup: clear any stale slots where `acquired_at < NOW() - INTERVAL '30 minutes'` or where the PID is no longer running.
  - **Rationale:** DDIA Chapter 8 — "Unreliable Networks." The orchestrator must assume it will crash and design its state to be recoverable.

- **No idempotency key on inbox items**: If the Telegram bot crashes between downloading the voice file and writing the `-idea.md`, the next restart may re-process the same message.
  - **Fix:** Write a `.lock` marker file with the Telegram `message_id` before processing. If the lock exists on restart, continue from where it stopped (components exist) or re-process clean.
  - **Rationale:** At-least-once delivery is acceptable for ideas; duplicates in inbox are detectable and cheap to remove.

### Important Considerations

- **projects.json atomic writes**: The current spec does not specify atomic writes for `projects.json`. The `/addproject` command must use `write → temp → rename` pattern, not `open → write → close`. Add this constraint to the implementation spec.

- **GitHub Issues as optional, not required**: The spec should make GitHub integration opt-in per project (`"github_repo": null` = no GitHub integration). Projects without a GitHub repo should work fully — status commands read SQLite, no Issues required.

- **Voice transcription latency**: Whisper on VPS CPU adds 2-10 seconds latency for typical voice messages. The bot should respond with "Idea received, transcribing..." immediately, then send the inbox confirmation when the `-idea.md` is written. Do not block the Telegram response on transcription completion.

- **Screenshot vision model cost**: Each screenshot requires a vision LLM call. At Claude Haiku pricing (~$0.001 per image), 100 screenshots/month = $0.10. Negligible. But the vision call should be async (do not block the bot handler) with the same deferred confirmation pattern as voice.

### Questions for Clarification

- Should `usage_ledger` track costs per project for the `/budget` command, or is global-only sufficient? (Recommend per-project — makes the command useful for prioritization.)
- Is the GitHub pinned Issue body updated by the orchestrator automatically, or only manually by the founder? (Recommend: orchestrator updates labels only; body is human-maintained narrative.)
- Should the SQLite `orchestrator.db` be inside the DLD repo or in a separate system path? (Recommend: `scripts/vps/orchestrator.db` — alongside the orchestrator scripts, excluded from git via `.gitignore`.)

---

## References

- [Martin Kleppmann — DDIA](https://dataintensive.net/) — Chapter 7 (Transactions), Chapter 8 (Unreliable Networks), Chapter 9 (Consistency and Consensus)
- [Claude Code #29158: ~/.claude.json corruption from concurrent instances](https://github.com/anthropics/claude-code/issues/29158)
- [Filesystem vs. Database for Agent Memory](https://andersswanson.dev/2026/01/22/filesystem-vs-database-for-agent-memory/)
- [Crash-safe JSON: atomic writes + recovery](https://dev.to/constanta/crash-safe-json-at-scale-atomic-writes-recovery-without-a-db-3aic)
- [Choosing the Right Context Architecture for Agent Systems](https://www.asklar.dev/ai/engineering/architecture/2025/12/20/context-architecture-for-agent-systems)
- [Building an agentic memory system for GitHub Copilot](https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot/)
- [WCP — Work Context Protocol](https://github.com/dpaola2/work-context-protocol)
- [SQLite Production Applications Guide](https://blogs.pavanrangani.com/sqlite-production-modern-applications-guide/)
- [AI Agent Orchestration Patterns — Azure](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)
