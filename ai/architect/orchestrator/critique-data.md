# Data Architecture Cross-Critique

**Persona:** Martin (Data Architect)
**Phase:** 2 — Peer Review
**Date:** 2026-03-10

---

## Peer Analysis Reviews

### Analysis A (Operations — Charity)

**Agreement:** Partially Agree

**Reasoning from data perspective:**

Charity's RAM documentation is the single most valuable empirical finding across the entire council. The gap between "200-500 MB spec claim" and "2-16 GB reality from GitHub issues" is a data-correctness problem, not just an ops problem. Every schema and state decision I made about slot counting and semaphore tables was premised on VPS survival, and Charity's evidence makes that foundation concrete with actual numbers.

The `.orchestrator-state.json` crash-safe analysis (write-rename) aligns exactly with my own finding from the Claude Code #29158 corruption incident. We converge independently on the same fix from different angles — that is strong signal.

**Missed gaps:**

- Charity keeps `.orchestrator-state.json` as a JSON file throughout the analysis and proposes "commit state file to git on every write" as a backup strategy. This is the wrong data primitive for a high-frequency daemon write. State written every 60s cycle across 5 projects is 300 writes/hour — this is not human-cadence. The data should live in SQLite with WAL mode. Git commits of JSON state are not a substitute for ACID writes.
- The backup section says "No database to back up — the existing design uses JSON files which are in git." This misses the point: the problem is not backup, it is concurrent write correctness under crash. A JSON file committed to git is still a JSON file that a daemon will corrupt via race condition.
- No coverage of inbox file completeness invariant — what happens if the bot crashes between writing `voice.ogg` and writing `idea.md`? Charity's recovery protocol only handles task-level crashes, not ingest-level partial writes.

---

### Analysis B (Devil's Advocate — Fred)

**Agreement:** Partially Agree

**Reasoning from data perspective:**

Fred raises a genuine and important data concern in Inconsistency #1: "Five different state stores for a system meant to be simple." From a data architecture perspective, this is the most dangerous anti-pattern in the current spec. Multiple state stores with no declared System of Record guarantees that any crash will leave the system in an indeterminate state. Fred correctly identifies: `.orchestrator-state.json`, `projects.json`, GitHub Issues, inotifywait events, and Telegram thread IDs as five different places where system state lives.

The atomic write requirement for `projects.json` — mentioned by Fred as "one line of code and costs nothing" — is exactly right. What the spec does not say is that you need `write → temp → mv` (atomic rename), which is what makes this safe on Linux.

**Missed gaps:**

- Fred's proposed solution ("one state store, JSON file is fine for 2-3 projects") underestimates the problem it is trying to solve. A single JSON state file written by a daemon every 60s is exactly the pattern from Claude Code #29158 (335 corruptions in 7 days). The solution is not "choose one JSON file" — it is "use the right data primitive." SQLite WAL is what you use when a daemon writes frequently and other processes read concurrently.
- The "bus factor" / "forget how this works in 6 months" concern is valid but Fred's proposed solution (tmux + Pueue + 50-line Python) still does not answer the fundamental data question: where is the system of record for project phase when the VPS reboots? Fred identifies the problem but does not propose a data model that actually survives crash and restart.
- Fred's Stress Test #4 (projects.json as single point of failure) correctly diagnoses the problem but dismisses it as "one line of code." The deeper issue is that fixing this requires understanding which data model owns what: config (projects.json) vs runtime state (SQLite) must be explicitly separated, not just made safe with atomic writes.

---

### Analysis C (DX Architect — Dan)

**Agreement:** Partially Agree

**Reasoning from data perspective:**

Dan's recommendation to use Pueue has a direct data implication worth analyzing separately from the DX argument. Pueue uses its own internal SQLite database for state persistence. This actually aligns with my recommendation to use SQLite for runtime state — the question is whether Pueue's SQLite is the right schema or whether the orchestrator needs additional tables (usage ledger, slot tracking) that Pueue does not provide.

Dan says "Pueue's internal SQLite replaces .orchestrator-state.json entirely" in the cross-cutting section. This is half right. Pueue's SQLite covers task queue state. It does not cover: per-project API usage tracking (cost ledger), slot health after crash (which project was running and for how long), or the inbox processing state machine. These need additional schema.

The key insight Dan gives that I did not have: `pueue status --json` is already a machine-readable state output. This means the Telegram bot's `/status` command can read structured state without a separate SQLite query. That partially simplifies the read path I designed.

**Missed gaps:**

- Dan does not address what happens to Pueue's SQLite on VPS reboot. Pueue's persistence model keeps queued tasks across restarts, but it does not know which project was mid-autopilot when the OOM occurred. The usage ledger and per-project error history are not in Pueue. A cost tracking requirement (`/budget` command) still needs a separate append-only table.
- The `projects.json` format in Dan's recommendation is thin (just `topic_id` to path mapping). This loses the metadata I specified: `priority`, `poll_interval`, `github_repo`, `enabled`. These fields drive runtime decisions. If projects.json becomes too thin, runtime behavior becomes implicit.
- No discussion of what data gets initialized on day 1. Pueue groups need to be seeded per project, projects.json needs to be populated, and any existing backlog state needs to be imported. The bootstrap problem is not addressed.

---

### Analysis D (Security — Bruce)

**Agreement:** Agree

**Reasoning from data perspective:**

Bruce's security concerns have direct data architecture implications. The per-project Unix user isolation recommendation changes the data model in a meaningful way: if each project runs as a separate user, then the per-project `.env` files ARE the data isolation boundary. The `orchestrator.db` I proposed (single file, single owner) still works — the orchestrator process owns the DB, project users cannot read it.

Bruce's audit log requirement ("structured append-only log, write to `/var/log/orchestrator/audit.log`, mode 640, log-rotation daily") is a data requirement that I did not include in my schema. This should be a table in the orchestrator SQLite, not a separate log file. A `command_audit` table with `(id, timestamp, user_id, telegram_username, command, project_id, result)` gives you structured, queryable audit data.

The `projects.json` integrity check (SHA256 stored root-owned) overlaps with the atomic write pattern I specified. Together these make the config data source robust.

**Missed gaps:**

- Bruce proposes writing audit data to a flat log file. From a data architecture perspective, this is a missed opportunity. The orchestrator already has SQLite — the audit log belongs there as an append-only table with an index on `(timestamp, project_id)`. This enables queries like "all commands in the last 24 hours for project X" from the `/history` bot command, which a flat log cannot do efficiently.
- No discussion of how per-project Unix users affects the SQLite file ownership. If the orchestrator runs as `user-orchestrator` and project Claudes run as `user-project-A`, the `claude_slots` table in `orchestrator.db` must be readable only by `user-orchestrator`. This is correct, but the implication — that the orchestrator process is the sole writer to all shared state — needs to be stated explicitly as a data invariant.
- The `CLAUDE_CODE_CONFIG_DIR` per-project isolation (referenced in Erik's analysis, not Bruce's) is a data isolation mechanism with a direct impact on the MCP-server-per-session RAM overhead. Bruce does not connect these. More RAM per isolated session affects the slot table capacity (how many concurrent Claude processes are safe).

---

### Analysis E (LLM Architect — Erik)

**Agreement:** Agree

**Reasoning from data perspective:**

Erik's finding that cross-session contamination is a known bug (issue #30348) is the strongest single data integrity finding in the whole council. This is not a theoretical concern — it is a documented production bug where content from Session A appeared in Session B. The root cause is shared `~/.claude/` state: memories, session history, and config are not project-scoped by default.

The fix Erik proposes — per-project `CLAUDE_CODE_CONFIG_DIR` — is correct and has a direct schema implication. The orchestrator needs to track which config directory is in use per project. This is a field in `project_state`: `config_dir TEXT NOT NULL DEFAULT '/var/orchestrator/projects/{project_id}/.claude-state'`. When a slot is acquired, the orchestrator sets this env variable before launching Claude. When the slot is released, the session state remains in that directory for the next run.

**Missed gaps:**

- Erik does not address how `CLAUDE_CODE_CONFIG_DIR` interacts with the Pueue-based approach (Dan's recommendation). If Pueue submits tasks as shell commands, the `CLAUDE_CODE_CONFIG_DIR` env variable needs to be passed at task submission time — not just at orchestrator startup. This is a data flow detail that matters for correctness.
- The per-phase `--max-turns` tuning table is operationally important. The orchestrator needs to store this per-phase configuration somewhere. Right now it would be hardcoded in the shell script. A better design: store it in `projects.json` as `"phases": {"inbox": 8, "spark": 35, "autopilot": 30, "qa": 12}`. This makes the policy data-driven and tunable without code changes.
- Erik identifies that flock is actually safe on crash (FD closes on process death = lock released). This is a correction to my analysis where I was uncertain about the flock cleanup behavior. Erik's research on this is more precise than mine. I was right to recommend SQLite as a replacement, but my justification ("stale lock files") was slightly wrong — the real issue is introspectability and crash diagnosis, not correctness.

---

### Analysis F (Evolutionary Architect — Neal)

**Agreement:** Agree

**Reasoning from data perspective:**

Neal's fitness function suite is excellent data architecture enforcement. The projects.json schema validation function (git pre-commit hook, validates required fields, checks that `path` exists on disk) is exactly the kind of runtime contract I should have specified but did not. This should be in the migration strategy section — it is not just a deployment concern, it is a data integrity gate.

The `.orchestrator-state.json.tmp → mv` atomic write recommendation matches my own analysis exactly. The fact that both Ops (Charity) and Evolutionary (Neal) independently identify this as a critical fix strengthens the recommendation significantly.

Neal's scaling inflection point at 5-6 projects (loop cycle time exceeds inbox latency SLO) is a data flow insight: the orchestrator's polling architecture creates a data latency problem that compounds with scale. At 5+ projects, sequential polling creates > 2.5 min cycles, violating the 5-min SLO. The fix (parallel project checks with `&` + `wait`) has a data implication: parallel concurrent writes to `orchestrator-state.json` if projects check simultaneously. SQLite handles this. JSON does not.

**Missed gaps:**

- Neal recommends atomics for state writes but still keeps the state in JSON. The scaling analysis (parallel checks at 5+ projects) would create exactly the concurrent-write scenario where JSON is unsafe. The evolutionary analysis and the data analysis lead to the same conclusion, but Neal does not follow the thread all the way: parallel project checks + JSON state = inevitable corruption. The conclusion should be SQLite, not "add parallelism carefully."
- The versioning strategy (`schema_version: 1` in projects.json) is good. But Neal does not address how to migrate the runtime state schema. If `project_state` in SQLite needs a new column (e.g., adding `config_dir` from Erik's finding), what is the migration path? The `PRAGMA user_version` approach I specified solves this, but Neal does not reference it.

---

### Analysis H (Domain Architect — Eric)

**Agreement:** Agree

**Reasoning from data perspective:**

Eric's domain analysis has the clearest alignment with my data architecture work. The bounded context map directly answers my Kill Question about System of Record:

| Entity | Eric's SoR mapping | My SoR mapping | Agreement |
|--------|-------------------|----------------|-----------|
| Project registry | Portfolio context → `projects.json` | `projects.json` | Yes |
| Runtime phase | Pipeline context → `.orchestrator-state.json` | `orchestrator.db: project_state` | Yes (different storage, same owner) |
| Inbox items | Inbox context → `ai/inbox/` filesystem | Per-project filesystem | Yes |
| Slot occupancy | Portfolio context → concurrency budget | `orchestrator.db: claude_slots` | Yes |

Eric's observation that "the same word 'project' is doing too much work" is a data modeling insight, not just a DDD insight. In the schema, the conflation of `project` (business entity) with `project` (filesystem path) with `project` (pipeline state) means queries can become confused. My schema separates these: `project_state.project_id` (FK to projects.json slug, not to a path). The path lives only in projects.json config.

The anti-corruption layer for Telegram (`message_thread_id` → `RoutingKey` → `project_id`) is exactly right. The `topic_id` field in `projects.json` is the ACL translation table. It should not be called `topic_id` (Telegram-specific) — it should be called `telegram_routing_key` to make the domain boundary explicit. When GitHub Issues becomes the interface, a `github_routing_key` field is added alongside it.

**Missed gaps:**

- Eric's domain events model (`IdeaCaptured`, `PhaseStarted`, etc.) implies event storage. For a shell-script implementation, domain events are just log lines. But Eric does not specify what persistent record these events leave. A `pipeline_events` table (append-only, like an event log) would give the orchestrator replay capability on crash and a queryable history for the `/history` command.
- The Portfolio aggregate's `ConcurrencyBudget` invariant ("Active project count <= ConcurrencyBudget") is the exact invariant my `claude_slots` table enforces via `BEGIN IMMEDIATE`. Eric names it correctly at the domain level. The connection to the SQLite implementation should be explicit: this invariant requires a transaction boundary, not just application-level checking.

---

## Ranking

**Best Analysis:** F (Neal — Evolutionary Architect)

**Reason:** Neal's analysis is the most useful to my data work because it provides concrete, automated enforcement mechanisms for data invariants (fitness functions), identifies the exact scaling inflection points where my data model choices will break (sequential JSON writes at 5+ projects), and proposes a versioning/migration strategy with `schema_version`. The evolutionary lens and the data lens are more closely aligned than any other pairing in this council.

**Worst Analysis:** B (Fred — Devil's Advocate)

**Reason:** Fred correctly identifies that multiple state stores is a critical problem, but the proposed solution ("one JSON file, it's fine for 2-3 projects") leaves the most dangerous failure mode unresolved. The whole point of the analysis is to prevent the 3am incident. A single JSON state file with daemon-frequency writes still fails at 3am — not at 10 projects, but at 2 projects with a 60s cycle. Fred found the symptom but prescribed the wrong medicine, and then spent most of the analysis on business justification rather than fixing the data problem.

---

## Addressing the Founder's New Questions

### 1. Multi-LLM (Claude Code + ChatGPT Codex GPT-5.4): Data Model Implications

*Traces the data flow mentally.*

The core question: does adding Codex require separate task tables per provider, or does a unified schema work?

**Unified schema with provider discriminator. Not separate tables.**

The reason is data integrity, not convenience. If you have `claude_tasks` and `codex_tasks` as separate tables, you have created two Systems of Record for the same concept (a project pipeline run). When you want to answer "what ran yesterday across all projects?" you need a UNION. When you want slot accounting, you need to count from both tables. This is the classic splitting-what-should-be-together mistake from DDIA Chapter 2.

**Revised schema for multi-LLM:**

```sql
-- Unified slot table: extends existing claude_slots
CREATE TABLE compute_slots (
    slot_number     INTEGER PRIMARY KEY,
    provider        TEXT NOT NULL CHECK (provider IN ('claude', 'codex')),
    project_id      TEXT,
    acquired_at     TIMESTAMPTZ,
    pid             INTEGER
);

-- Separate slot pools per provider
-- Slot 1-2: Claude slots (ram-heavy, 2-8 GB each)
-- Slot 3-4: Codex slots (different RAM profile)
INSERT INTO compute_slots (slot_number, provider) VALUES
    (1, 'claude'), (2, 'claude'),
    (3, 'codex'),  (4, 'codex');

-- project_state: add preferred_provider
ALTER TABLE project_state ADD COLUMN preferred_provider TEXT
    DEFAULT 'claude' CHECK (preferred_provider IN ('claude', 'codex', 'any'));

-- Usage ledger: already handles this by extending event_type
-- Add codex event types:
-- 'codex_session_start', 'codex_session_end'
-- cost_usd_cents still works (Codex has its own pricing)
```

**projects.json** gets a per-project provider preference:
```json
{
  "id": "saas-app",
  "preferred_provider": "claude",
  "codex_fallback": true
}
```

**Task routing logic (data flow):**

```
Orchestrator checks inbox for project X
  → preferred_provider = "claude"
  → Acquire slot WHERE provider = 'claude' AND project_id IS NULL
  → If no claude slot available AND codex_fallback = true:
      → Acquire slot WHERE provider = 'codex' AND project_id IS NULL
  → Launch provider-specific CLI
  → Record in usage_ledger with event_type = '{provider}_session_start'
```

**Concurrency budget math changes.** Claude is RAM-bound (2-8 GB each). Codex has its own RAM profile (needs separate profiling — see Ops person's RAM table for context). The slot table must encode the per-provider pool size. Starting conservative: 2 Claude slots, 1 Codex slot on 16 GB VPS.

**System of Record clarity:** `compute_slots` is the SoR for "who is currently running what." `project_state.preferred_provider` is the SoR for "which provider should this project prefer." These are two different questions with two different owners.

---

### 2. Same VPS as Docker Containers vs Separate: Data Implications

*The key question is: does shared hosting change the data primitive for state management?*

**Same VPS with Docker: shared SQLite is a problem. Use named Unix socket or host-mounted volume.**

If the orchestrator runs as a systemd service on the VPS host AND Docker containers run project workloads on the same host, then `orchestrator.db` is on the host filesystem. Docker containers need to read/write project state — but a SQLite WAL file cannot be safely shared across a host process and a Docker container process without careful mount configuration.

**Two viable data topologies:**

**Topology A: Orchestrator on host, projects in containers (recommended)**

```
VPS host:
├── orchestrator.service (systemd) ← owns orchestrator.db
├── compute_slots table ← managed by orchestrator only
└── docker.service

Docker containers (per project):
├── project-A container
│   └── /app/ai/inbox/ ← host-mounted volume: /home/user/project-A/ai/inbox
│   └── /app/CLAUDE.md  ← read-only host-mount
│   └── /app/.env        ← read-only host-mount (secrets)
└── project-B container (same pattern)

Data flow:
  Orchestrator launches docker exec claude ... inside container
  SQLite lives on HOST only (not inside container)
  Inbox files on HOST, mounted read-write into container
```

The orchestrator NEVER runs inside Docker. It runs on the host because it needs to manage Docker containers — running the manager inside a container it manages is a circular dependency.

**Topology B: Orchestrator in container on same VPS (avoid)**

If the orchestrator itself runs inside Docker, SQLite becomes a shared file across containers. SQLite WAL works fine for host-mount volumes on Linux (same kernel, same locking primitives). But you introduce a new risk: if the Docker volume mount is lost or the container is killed, the SQLite file is inaccessible but still "open" by the host. Recovery becomes complex.

**Data implication for separate VPS topology:**

If orchestrator runs on a lightweight separate VPS (Hetzner CX21 at €4.51/mo) and project containers run on the main VPS:

```
Orchestrator VPS (lightweight, €4.51/mo):
├── orchestrator.db (SQLite, stays here)
├── Telegram bot
└── SSH commands to project VPS

Project VPS (beefy, 32 GB RAM):
├── Docker containers per project
└── ai/inbox/ directories (project data, stays here)
```

In this topology, the orchestrator launches Claude remotely via SSH. The usage_ledger is on the orchestrator VPS. The inbox files are on the project VPS. **This means inbox polling requires SSH or a shared mount.** That is a new network dependency on a previously local-only operation.

**Recommendation:** Same VPS, orchestrator on host, project workloads in Docker containers mounted to host directories. This keeps SQLite local (single kernel, ACID guarantees), avoids network latency on inbox polling, and costs nothing extra ($0 additional VPS).

**Cost analysis:**
- 1 beefy VPS (32 GB, Hetzner CX51) = €31.10/mo. Orchestrator + 4 Docker containers all on same host.
- 2 VPS (CX21 orchestrator at €4.51 + CX51 project at €31.10) = €35.61/mo. 15% more expensive, adds network hop for every inbox check.

The data arguments favor the single-VPS topology.

---

### 3. Practical Bootstrap: What Data Needs to Be Initialized on Day 1

*This is a schema + seed data question with operational urgency.*

**Day 1 bootstrap sequence (data perspective):**

**Step 1: Create orchestrator.db with schema (< 1 minute)**

```sql
-- Run once: init-db.sh
sqlite3 /var/orchestrator/orchestrator.db << 'EOF'
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS project_state (
    project_id       TEXT PRIMARY KEY,
    phase            TEXT NOT NULL DEFAULT 'idle'
                     CHECK (phase IN ('idle','inbox','spark','autopilot','qa','paused','error')),
    preferred_provider TEXT DEFAULT 'claude',
    current_task     TEXT,
    claude_pid       INTEGER,
    config_dir       TEXT,
    slot_number      INTEGER,
    slot_acquired_at TIMESTAMPTZ,
    last_checked_at  TIMESTAMPTZ,
    last_error       TEXT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS compute_slots (
    slot_number  INTEGER PRIMARY KEY,
    provider     TEXT NOT NULL,
    project_id   TEXT,
    acquired_at  TIMESTAMPTZ,
    pid          INTEGER
);

-- Seed: 2 Claude slots, 1 Codex slot (adjust per VPS RAM)
INSERT OR IGNORE INTO compute_slots (slot_number, provider) VALUES
    (1, 'claude'), (2, 'claude'), (3, 'codex');

CREATE TABLE IF NOT EXISTS usage_ledger (
    id               TEXT PRIMARY KEY,
    project_id       TEXT NOT NULL,
    provider         TEXT NOT NULL DEFAULT 'claude',
    event_type       TEXT NOT NULL,
    tokens_in        INTEGER,
    tokens_out       INTEGER,
    cost_usd_cents   INTEGER,
    duration_seconds INTEGER,
    occurred_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_usage_project_date
    ON usage_ledger(project_id, occurred_at);

CREATE TABLE IF NOT EXISTS command_audit (
    id            TEXT PRIMARY KEY,
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    telegram_user_id  INTEGER NOT NULL,
    telegram_username TEXT,
    command       TEXT NOT NULL,
    project_id    TEXT,
    result        TEXT
);

PRAGMA user_version = 1;
EOF
```

**Step 2: Create projects.json with first project (< 2 minutes)**

```json
{
  "version": 1,
  "chat_id": -100XXXXXXXXXX,
  "max_concurrent_claude": 2,
  "max_concurrent_codex": 1,
  "projects": [
    {
      "id": "my-first-project",
      "name": "My First Project",
      "topic_id": 5,
      "path": "/home/user/my-first-project",
      "github_repo": "user/my-first-project",
      "priority": "high",
      "preferred_provider": "claude",
      "codex_fallback": false,
      "poll_interval": 300,
      "enabled": true,
      "created_at": "2026-03-10T00:00:00Z"
    }
  ]
}
```

**Step 3: Seed project_state from projects.json (< 1 minute)**

```bash
# seed-projects.sh — run after projects.json is populated
python3 - << 'EOF'
import json, sqlite3, os

cfg = json.load(open('/var/orchestrator/projects.json'))
db = sqlite3.connect('/var/orchestrator/orchestrator.db')

for p in cfg['projects']:
    config_dir = f"/var/orchestrator/projects/{p['id']}/.claude-state"
    os.makedirs(config_dir, exist_ok=True)

    db.execute("""
        INSERT OR IGNORE INTO project_state
        (project_id, phase, preferred_provider, config_dir, updated_at)
        VALUES (?, 'idle', ?, ?, CURRENT_TIMESTAMP)
    """, (p['id'], p.get('preferred_provider', 'claude'), config_dir))

db.commit()
db.close()
print("Seeded project_state for", len(cfg['projects']), "projects")
EOF
```

**Step 4: Create per-project CLAUDE_CODE_CONFIG_DIR directories**

These were created in Step 3 via `os.makedirs`. Each directory starts empty — Claude will populate it with session state on first run. This is the per-project isolation mechanism from Erik's finding.

**Step 5: Validate everything before first run (< 1 minute)**

```bash
# validate-setup.sh
python3 - << 'EOF'
import json, sqlite3, os, sys

errors = []

# Check projects.json
cfg = json.load(open('/var/orchestrator/projects.json'))
for p in cfg['projects']:
    if not os.path.isdir(p['path']):
        errors.append(f"Project path does not exist: {p['path']}")

# Check SQLite
db = sqlite3.connect('/var/orchestrator/orchestrator.db')
rows = db.execute("SELECT COUNT(*) FROM project_state").fetchone()[0]
if rows != len(cfg['projects']):
    errors.append(f"project_state rows ({rows}) != projects.json count ({len(cfg['projects'])})")

slots = db.execute("SELECT COUNT(*) FROM compute_slots WHERE project_id IS NULL").fetchone()[0]
if slots == 0:
    errors.append("No free slots in compute_slots table")

if errors:
    print("BOOTSTRAP ERRORS:")
    for e in errors: print(f"  - {e}")
    sys.exit(1)
else:
    print("Bootstrap validation passed.")
    print(f"  Projects: {rows}")
    print(f"  Free slots: {slots}")
EOF
```

**What data exists at the end of Day 1:**

| Entity | Location | State |
|--------|----------|-------|
| Project registry | `projects.json` | 1+ projects, human-written |
| project_state rows | `orchestrator.db` | One row per project, phase='idle' |
| compute_slots | `orchestrator.db` | 2 Claude + 1 Codex, all free |
| usage_ledger | `orchestrator.db` | Empty (no runs yet) |
| command_audit | `orchestrator.db` | Empty (no commands yet) |
| Per-project config dirs | `/var/orchestrator/projects/{id}/.claude-state/` | Created, empty |
| ai/inbox/ | Per-project filesystem | Already exists from DLD |

The total setup time is under 10 minutes. The data state after bootstrap is deterministic and verifiable.

---

## Revised Position

**Revised Verdict:** Changed

**Change Reason:**

Two findings from peers forced revisions to my original analysis:

1. **Erik's correction on flock safety.** I stated that flock leaves stale locks on crash. Erik's research corrects this: flock IS released when the FD closes (on process death). My SQLite `claude_slots` recommendation is still correct, but for a different reason than I stated — introspectability and cross-process visibility, not crash safety. The justification should be: "SQLite slots are queryable by the Telegram bot; flock state is not."

2. **Multi-LLM provider requirement (from agenda).** My original schema was Claude-only. The `claude_slots` table needed to become `compute_slots` with a `provider` discriminator. This is a schema change that would have required a migration if I had shipped the Claude-only version first. The multi-LLM question is not new complexity — it is a requirement that should be in the v1 schema, not a migration later.

**Final Data Recommendation:**

The core data architecture stands: `projects.json` for config (human-written, atomic rename), `orchestrator.db` SQLite for runtime state (daemon-written, WAL mode), `ai/inbox/` filesystem for inbox items (agent-native format). The changes from peer review:

1. `claude_slots` becomes `compute_slots` with `provider` column from day 1. Multi-LLM is a v1 data requirement.
2. Add `command_audit` table for Bruce's audit log requirement. Flat log file is the wrong primitive.
3. Add `config_dir` column to `project_state` for Erik's per-project `CLAUDE_CODE_CONFIG_DIR` isolation.
4. On same VPS + Docker topology: orchestrator runs on host, SQLite stays on host, project containers mount inbox directories as host volumes. Do NOT put SQLite inside a Docker container.
5. The bootstrap script sequence (Steps 1-5 above) is the Day 1 data initialization protocol. Target: < 10 minutes from zero to first valid run.

The most important unchanged finding: `.orchestrator-state.json` must be replaced with SQLite. Every peer who addressed this independently confirmed the need for an ACID-capable state store. The JSON race condition is not theoretical — it is documented in production (Claude Code #29158). This is the single most important data decision in this architecture.
