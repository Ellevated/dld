# Architecture Synthesis: Multi-Project Orchestrator

**Synthesizer:** Oracle (Chairman)
**Input:** 8 persona research + 8 critiques
**Output:** 3 architecture alternatives
**Date:** 2026-03-10

---

## Synthesis Summary

**Key insights from research:**

1. **Claude CLI memory is 10x understated.** The spec says 200-500 MB. Reality from 4 GitHub issues: 2-16 GB per extended session, up to 120+ GB with leaks. This single fact changes every VPS sizing, concurrency, and deployment decision. (Charity, Erik -- independent convergence)

2. **Pueue eliminates ~300 LOC of custom infrastructure.** Custom flock semaphore, priority scheduler, state machine, and restart recovery are all solved by a 4.6k-star Rust task queue that already exists. (Dan -- validated by Neal, Charity, Fred)

3. **SQLite WAL replaces JSON state.** The `.orchestrator-state.json` write pattern matches the exact race condition that caused 335 corruption events in Claude Code's own state file (GitHub #29158). SQLite with `BEGIN IMMEDIATE` is the correct primitive for daemon-frequency writes with concurrent readers. (Martin -- changed positions of Neal and Charity)

4. **Cross-session contamination is a production bug.** Two concurrent Claude sessions on the same user account can contaminate each other (GitHub #30348). Fix: `CLAUDE_CODE_CONFIG_DIR` per project. One env var, one line, zero cost. (Erik -- non-negotiable)

5. **The orchestrator is an Application Service, not a domain.** The domains are Portfolio, Inbox, Pipeline, Notification. The bash/Python process is coordination glue. Telegram topics must not leak into the domain model. (Eric -- validated by all except Fred who questions whether the distinction matters for 2-3 projects)

6. **Anti-Pattern #2 is active.** The business blueprint says Phase 1 is consulting content. The orchestrator is pure tooling with zero revenue path. The honest question is not "how" but "when." (Fred -- validated by Dan)

7. **Multi-LLM doubles complexity non-linearly.** Codex has the same memory leak class (GitHub #9345, #13314). Running two leaky CLIs on one VPS is additive OOM risk. Per-project routing (v1) is simpler than per-task routing. (Erik Phase 2, Fred Phase 2)

8. **`run-agent.sh` provider abstraction is a 30-minute investment.** Wrap Claude and Codex invocations in provider-specific runners. The orchestrator loop never calls `claude` or `codex` directly. Adding a third provider becomes a configuration change. (Neal -- validated by Erik)

---

## Major Contradictions Resolved

### Evaporating Cloud 1: State Management Primitive

**Conflict:** Dan wants atomic JSON files (no new dependency). Martin wants SQLite WAL (ACID guarantees).

```
        [Reliable orchestrator state that survives 3am crashes]
              |
      +-------+-------+
      |               |
[Simplicity]      [Correctness]
      |               |
      v               v
[JSON files] <--conflict--> [SQLite WAL]
```

**Common Goal:** State that survives crash and is debuggable at 3am.

**Need A (Dan):** Minimal dependencies, boring tech, fits bash-native workflow.
**Want A:** Atomic JSON files (`write -> tmp -> mv`).

**Need B (Martin):** ACID writes under daemon-frequency concurrent access. Introspectable slot state.
**Want B:** SQLite WAL with `BEGIN IMMEDIATE` transactions.

**Assumptions underlying conflict:**
1. "JSON with atomic rename is sufficient for daemon-frequency writes" -- FALSE. GitHub #29158 documents 335 corruptions at lower write frequency.
2. "SQLite adds meaningful complexity to a bash system" -- PARTIALLY TRUE. Requires `sqlite3` CLI subprocess calls.

**Resolution:** Layered approach.
- **Config** stays JSON (`projects.json`) -- human-written, rare changes, atomic rename sufficient.
- **Runtime state** uses SQLite WAL (`orchestrator.db`) -- daemon-written, concurrent readers, crash-safe.
- **Task queue state** lives in Pueue's native SQLite -- no custom management needed.

This satisfies Dan's "boring tech" principle (SQLite is the most deployed DB in history) AND Martin's ACID requirement. The dependency cost is `sqlite3` CLI which ships with every Linux distro.

---

### Evaporating Cloud 2: Build Scope

**Conflict:** Dan says 3-day timebox. Martin/Charity/Neal's combined proposals need 2+ weeks.

```
        [Working orchestrator without over-engineering]
              |
      +-------+-------+
      |               |
[Ship fast]       [Ship safe]
      |               |
      v               v
[3-day MVP] <--conflict--> [Full system]
```

**Common Goal:** A working multi-project orchestrator that the founder can trust.

**Need A (Dan):** Ship before the orchestrator itself becomes anti-pattern #2.
**Want A:** 3-day build with Pueue + Telegram bot only.

**Need B (Charity/Martin/Neal):** Production-grade reliability for unattended 3am operation.
**Want B:** SQLite + monitoring + fitness functions + security hardening.

**Assumptions underlying conflict:**
1. "You must choose between fast and safe" -- FALSE if you layer the build.
2. "All safety features must be in v1" -- FALSE. Some can gate v2.

**Resolution:** Phase-gated build sequence (Neal's Strangler Fig applied).
- **Days 1-3:** Pueue + systemd + minimal Telegram bot. Attended mode works.
- **Days 4-5:** SQLite state + RAM floor gate + heartbeat. Unattended mode works.
- **Days 6-7:** Security hardening (P0 items) + provider abstraction. Multi-LLM ready.
- **Day 8+:** Fitness functions, monitoring, Codex integration. Production-grade.

Each phase has a fitness gate. The founder can STOP at any phase boundary and have a working system.

---

### Evaporating Cloud 3: LLM CLI Isolation

**Conflict:** Bruce wants separate Unix users per project (full isolation). Erik wants `CLAUDE_CODE_CONFIG_DIR` per call (partial isolation). Fred says run CLIs inside Docker containers (containment).

```
        [Claude/Codex processes cannot damage each other or leak secrets]
              |
      +-------+-------+
      |               |
[Simple setup]    [Strong isolation]
      |               |
      v               v
[Config dir   <--conflict--> [Per-user or
 per call]                    Docker containers]
```

**Common Goal:** Projects cannot read each other's secrets or contaminate each other's contexts.

**Need A (Erik):** Fix the documented contamination bug (#30348) with minimal friction.
**Want A:** `CLAUDE_CODE_CONFIG_DIR` per project -- one env var.

**Need B (Bruce):** Prevent cross-project `.env` file reading via prompt injection.
**Want B:** Separate Unix users per project -- OS-enforced filesystem isolation.

**Need C (Fred):** Contain OOM blast radius from leaky CLIs.
**Want C:** Docker containers with `--memory` limits for CLI processes.

**Resolution:** Layered isolation that addresses all three threats independently.
1. `CLAUDE_CODE_CONFIG_DIR` per project (Day 1) -- fixes session contamination. Zero cost.
2. systemd `MemoryMax` on orchestrator service (Day 1) -- contains OOM blast radius.
3. Per-project Unix users (Day 7+) -- adds filesystem isolation when handling sensitive projects.
4. Docker for CLI (deferred) -- only if OOM blast radius proves uncontainable by cgroups.

Layers 1-2 are non-negotiable for any alternative. Layers 3-4 are risk-proportional additions.

---

### Evaporating Cloud 4: Build Now vs Build After Phase 1

**Conflict:** Fred says this is anti-pattern #2. Dan says timebox to 3 days. Business blueprint says Phase 1 is consulting content.

```
        [Founder productive on multiple projects]
              |
      +-------+-------+
      |               |
[Revenue first]   [Tooling enables
      |            revenue]
      v               v
[Don't build, <--conflict--> [Build orchestrator
 use tmux]                     to manage projects]
```

**Resolution:** This is a decision for the human, not the synthesizer. The three alternatives below are ordered from "minimal investment" to "full system" specifically so the founder can choose based on their current Phase 1 progress and energy.

---

## Alternative A: Minimal Viable (tmux + cron + notify.sh)

**Philosophy:** Do the least possible. The orchestrator is a human with tmux windows.

**Best for:** Founder who has 2 projects, is actively at keyboard, needs to ship Phase 1 consulting content first.

---

### 1. Architecture Overview

The founder IS the orchestrator. No custom software. Existing tools compose.

```
tmux session "work"
  |-- window 0: saas-app    (cd ~/saas-app && claude)
  |-- window 1: side-project (cd ~/side-project && claude)
  |-- window 2: monitoring   (htop / journalctl / pueue status)

cron (every 5 min):
  check-inbox.sh  --> for each project, if ai/inbox/ has files, notify via Telegram

notify.sh (existing, 20 lines):
  sends task completion to Telegram General topic
```

**No state file. No semaphore. No bot. Human is the scheduler.**

### 2. Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Session mgmt | tmux | Already installed, sessions persist SSH disconnects |
| Task queue | Pueue (optional) | Only if unattended runs needed. `pueue add --group saas-app "claude -p '/autopilot'"` |
| Notifications | `notify.sh` (existing) | 20 lines of curl to Telegram API |
| Inbox check | cron + `find` | `*/5 * * * * ~/scripts/check-inbox.sh` |
| Voice transcription | whisper.cpp | Local, no API dependency |

**Innovation tokens used:** 0

### 3. VPS Topology

**Same VPS as everything else.** 16GB minimum.

| Component | RAM |
|-----------|-----|
| OS + tmux | 0.5 GB |
| 1x Claude CLI (active) | 2-8 GB |
| Docker containers (if any) | 1-4 GB |
| Headroom | 2 GB |

**`MAX_CONCURRENT=1`.** Human decides when to run second Claude.

### 4. Multi-LLM Strategy

Manual. The founder types `claude` or `codex` in the appropriate tmux window.

Per-project convention in `projects.json` (human-read, not machine-read):
```json
{
  "saas-app": {"engine": "claude", "notes": "complex architecture"},
  "side-project": {"engine": "codex", "notes": "pure implementation"}
}
```

No automated routing. No provider abstraction. YAGNI until attended mode is insufficient.

### 5. Security Model

| Item | Implementation | Effort |
|------|---------------|--------|
| `from_user.id` whitelist | N/A -- no bot | 0 |
| Project isolation | Separate tmux windows, `CLAUDE_CODE_CONFIG_DIR` per project | 10 min |
| Secret isolation | `chmod 600 .env` per project | 5 min |
| Prompt injection | `--max-turns 30` + `--sandbox` on Claude invocations | 5 min |
| VPS hardening | SSH keys only, `fail2ban`, `ufw` | 30 min |

### 6. Day-1 Bootstrap Checklist

```bash
# 1. VPS hardening (30 min)
ssh-keygen && ssh-copy-id user@vps
echo "PasswordAuthentication no" >> /etc/ssh/sshd_config
apt install fail2ban ufw && ufw allow 22 && ufw enable

# 2. Tools (20 min)
npm install -g @anthropic-ai/claude-code@2.1.34
apt install whisper-cpp tmux jq

# 3. Projects (10 min per project)
git clone <repo> ~/projects/saas-app
cd ~/projects/saas-app && claude --init  # auth once

# 4. Inbox check cron (5 min)
cat >> /etc/crontab << 'EOF'
*/5 * * * * user ~/scripts/check-inbox.sh
EOF

# 5. Notify.sh (already exists)
chmod +x ~/scripts/notify.sh

# Total: ~1 hour from zero to working
```

### 7. Build Effort

| Phase | Time | What |
|-------|------|------|
| Setup | 1 hour | VPS + tmux + cron |
| Per project | 10 min | git clone + claude --init |
| Total | 1.5 hours | Done |

### 8. Trade-Offs

**Optimizes for:** Zero engineering investment. Maximum time for Phase 1 consulting content.

**At the cost of:** No unattended execution. No mobile status. No automatic scheduling. Human is single point of failure.

**Biggest risk:** Founder forgets to check projects. No alerting if inbox piles up.

**Migration path to B:** Add Pueue + Telegram bot when attended mode becomes insufficient. All project data is portable.

---

## Alternative B: Boring Stack (Pueue + Telegram Bot + SQLite)

**Philosophy:** Use existing tools for everything undifferentiated. Build custom only for the Telegram-native founder experience.

**Best for:** Founder who needs unattended execution for 2-5 projects, wants mobile control, accepts 5-7 day build investment.

---

### 1. Architecture Overview

```
Telegram Supergroup (topics per project)
  |
  v
telegram-bot.py (Python, polling mode)
  |-- Routes messages by topic_id -> project
  |-- Writes ideas to ai/inbox/{project}/
  |-- /status, /pause, /run, /addproject commands
  |-- Queries orchestrator.db for state
  |
  v
Pueue Daemon (systemd user service)
  |-- Groups: one per project (saas-app, side-project, ...)
  |-- Global parallel limit: 2 (VPS RAM-bound)
  |-- Per-group parallel: 1 (one task per project at a time)
  |-- Persistence: survives reboot via systemd
  |
  v
run-agent.sh (provider-agnostic entry point)
  |-- claude-runner.sh (sets CLAUDE_CODE_CONFIG_DIR, cwd, --max-turns)
  |-- codex-runner.sh  (sets cwd, --sandbox workspace-write)
  |
  v
orchestrator.db (SQLite WAL)
  |-- project_state: phase, current_task, last_error
  |-- compute_slots: which project holds which slot, which provider
  |-- usage_ledger: append-only cost tracking
  |-- command_audit: who ran what command when
```

### 2. Domain Map

**Bounded Contexts (lightweight, enforced by naming conventions):**

| Context | Responsibility | Core Entities | Implementation |
|---------|---------------|---------------|----------------|
| Portfolio | Project registry, priority, concurrency budget | Project, Priority, ConcurrencyBudget | `projects.json` + `orchestrator.db:project_state` |
| Inbox | Capture and route founder inputs | InboxItem, RoutingKey, Channel | `ai/inbox/` filesystem + Telegram ACL |
| Pipeline | DLD lifecycle per project | Phase, PipelineRun, Slot | `orchestrator.db:compute_slots` + Pueue |
| Notification | Status delivery to founder | Notification, DeliveryChannel | Telegram topic per project |

**Context Relationships:**

```
Telegram API --[ACL: topic_id -> RoutingKey]--> Inbox
                                                  |
                                          [IdeaCaptured]
                                                  |
                                                  v
Portfolio --[ProjectActivated]--> Pipeline
    ^                                |
    |                        [PhaseCompleted]
    +--[SlotReleased]<---------------+
                                     |
                             [Notify founder]
                                     |
                                     v
                              Notification --> Telegram topic
```

**Domain Events (implemented as function calls + SQLite writes, not an event bus):**

| Event | Source | Triggered By | Action |
|-------|--------|-------------|--------|
| IdeaCaptured | Inbox | Message in project topic | Write to `ai/inbox/`, update `last_activity` |
| ProjectActivated | Portfolio | Scheduler selects project | Acquire compute slot, submit Pueue task |
| PhaseStarted | Pipeline | Pueue task begins | Update `project_state.phase`, notify topic |
| PhaseCompleted | Pipeline | Pueue task succeeds | Release slot, update phase to idle, notify |
| PipelineFailed | Pipeline | Pueue task fails / timeout | Release slot, set phase=error, alert |

### 3. Data Model

**Schema Approach:** JSON for config, SQLite WAL for runtime state, filesystem for inbox.

**System of Record:**

| Entity | SoR | Format | Writer | Consistency |
|--------|-----|--------|--------|------------|
| Project registry | `projects.json` | JSON | Human / `/addproject` | Atomic rename |
| Runtime phase | `orchestrator.db` | SQLite WAL | Orchestrator daemon | ACID |
| Compute slots | `orchestrator.db` | SQLite WAL | Orchestrator daemon | `BEGIN IMMEDIATE` |
| Inbox items | `ai/inbox/{project}/` | Markdown files | Telegram bot | Filesystem atomic |
| Task queue | Pueue internal SQLite | SQLite | Pueue daemon | Pueue-managed |
| Usage costs | `orchestrator.db` | SQLite WAL | Post-task hook | Append-only |

**SQLite Schema:**

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE project_state (
    project_id        TEXT PRIMARY KEY,
    phase             TEXT NOT NULL DEFAULT 'idle'
                      CHECK (phase IN ('idle','inbox','spark','autopilot','qa','paused','error')),
    preferred_provider TEXT DEFAULT 'claude'
                      CHECK (preferred_provider IN ('claude','codex','any')),
    current_task      TEXT,
    pid               INTEGER,
    config_dir        TEXT,
    slot_number       INTEGER,
    slot_acquired_at  TEXT,
    last_checked_at   TEXT,
    last_error        TEXT,
    updated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE compute_slots (
    slot_number  INTEGER PRIMARY KEY,
    provider     TEXT NOT NULL CHECK (provider IN ('claude','codex')),
    project_id   TEXT,
    acquired_at  TEXT,
    pid          INTEGER
);

-- Seed: 2 Claude + 1 Codex (adjust per VPS RAM)
INSERT INTO compute_slots (slot_number, provider) VALUES
    (1, 'claude'), (2, 'claude'), (3, 'codex');

CREATE TABLE usage_ledger (
    id               TEXT PRIMARY KEY,
    project_id       TEXT NOT NULL,
    provider         TEXT NOT NULL DEFAULT 'claude',
    event_type       TEXT NOT NULL,
    tokens_in        INTEGER,
    tokens_out       INTEGER,
    cost_usd_cents   INTEGER,
    duration_seconds INTEGER,
    occurred_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX idx_usage_project_date ON usage_ledger(project_id, occurred_at);

CREATE TABLE command_audit (
    id               TEXT PRIMARY KEY,
    occurred_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    telegram_user_id INTEGER NOT NULL,
    command          TEXT NOT NULL,
    project_id       TEXT,
    result           TEXT
);

PRAGMA user_version = 1;
```

**Slot Acquisition (replaces flock):**

```sql
-- Atomic slot acquisition
BEGIN IMMEDIATE;
UPDATE compute_slots
SET project_id = :project, acquired_at = strftime('%Y-%m-%dT%H:%M:%SZ','now'), pid = :pid
WHERE slot_number = (
    SELECT slot_number FROM compute_slots
    WHERE project_id IS NULL AND provider = :preferred_provider
    LIMIT 1
) AND project_id IS NULL;
COMMIT;
-- If rows_affected = 0: no slot available
```

### 4. Tech Stack

| Layer | Technology | Why Boring |
|-------|-----------|------------|
| Task queue | Pueue v4.0 (Rust, 4.6k stars) | Feature-complete, handles concurrency + priority + persistence |
| Process supervisor | systemd | 12 years old, on every Linux |
| Bot | Python 3.12 + python-telegram-bot v22 | Massive ecosystem, Forum topics supported |
| State | SQLite WAL | Most deployed DB in history. Ships with every Linux. |
| Config | JSON file | Everyone knows it |
| Logging | Structured JSON to journald | `journalctl -u orchestrator -f` just works |
| Voice | whisper.cpp (local) | No cloud dependency, no PII exfiltration |
| Scheduling | Pueue priority + systemd timer | Zero custom scheduler code |

**Innovation tokens spent:** 0.5 (Telegram bot with topic routing is the only custom code)

### 5. Cross-Cutting Rules (as CODE)

**Provider Abstraction:**

```bash
#!/usr/bin/env bash
# /scripts/vps/run-agent.sh -- provider-agnostic entry point
# The ONLY place that invokes LLM CLIs

run_agent() {
    local project_dir="$1"
    local task="$2"
    local provider="${3:-claude}"

    # RAM floor gate (non-negotiable)
    local free_ram_kb
    free_ram_kb=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
    local free_ram_gb=$(( free_ram_kb / 1024 / 1024 ))
    if [[ $free_ram_gb -lt 3 ]]; then
        log_json "error" "orchestrator" "RAM floor: ${free_ram_gb}GB free, refusing launch"
        return 1
    fi

    case "$provider" in
        claude)
            CLAUDE_CODE_CONFIG_DIR="/var/orchestrator/projects/$(basename "$project_dir")/.claude-state" \
            (cd "$project_dir" && timeout 900 claude -p "$task" \
                --max-turns 30 \
                --output-format json)
            ;;
        codex)
            (cd "$project_dir" && timeout 900 codex exec "$task" \
                --sandbox workspace-write \
                --json)
            ;;
        *)
            log_json "error" "orchestrator" "Unknown provider: $provider"
            return 1
            ;;
    esac
}
```

**Structured Logging:**

```bash
log_json() {
    local level="$1" service="$2" message="$3" extra="${4:-{}}"
    printf '{"ts":"%s","level":"%s","service":"%s","msg":"%s","meta":%s}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$level" "$service" "$message" "$extra"
}
```

**Error Pattern:**

```json
{
  "ts": "2026-03-10T14:30:00Z",
  "level": "error",
  "service": "orchestrator",
  "msg": "Claude OOM killed",
  "meta": {
    "project": "saas-app",
    "task": "FTR-042",
    "free_ram_gb": 1,
    "pid": 12345,
    "action": "Reduce MAX_CONCURRENT or upgrade VPS"
  }
}
```

### 6. Multi-LLM Strategy

**v1: Project-level routing.**

```json
// projects.json
{
  "id": "saas-app",
  "preferred_provider": "claude",
  "codex_fallback": false
}
```

Orchestrator reads `preferred_provider`, passes to `run-agent.sh`. No per-task routing in v1.

**Pueue groups for provider isolation:**

```bash
pueue group add claude-runner   # parallel 2
pueue group add codex-runner    # parallel 1

# Claude task:
pueue add --group claude-runner -- run-agent.sh /home/user/saas-app "/autopilot" claude

# Codex task:
pueue add --group codex-runner -- run-agent.sh /home/user/side-project "/autopilot" codex
```

**Per-project mutex (same project cannot run both CLIs simultaneously):**

```sql
-- Before submitting ANY task, check:
SELECT COUNT(*) FROM compute_slots
WHERE project_id = :project AND project_id IS NOT NULL;
-- If > 0: project already has an active session. Queue, don't run.
```

### 7. Security Model

| Priority | Item | Implementation | Effort |
|----------|------|---------------|--------|
| P0 | `from_user.id` whitelist | `ALLOWED_USER_IDS` env var, check on every message | 2h |
| P0 | `--max-turns` + `timeout` | In `run-agent.sh` (already shown above) | 0 (built-in) |
| P0 | `CLAUDE_CODE_CONFIG_DIR` per project | In `run-agent.sh` (already shown above) | 0 (built-in) |
| P1 | Local whisper.cpp | `apt install whisper-cpp`, no OpenAI API | 4h |
| P1 | Prompt injection defense | XML structural separation in inbox-processing prompts | 4h |
| P2 | Fine-grained GitHub PATs per project | One token per repo, 90-day expiry | 2h |
| P2 | Audit log | `command_audit` table in SQLite (already in schema) | 0 (built-in) |
| P3 | Per-project Unix users | `useradd user-saas-app`, `sudo -u` in runner | 30 min/project |

### 8. VPS Topology

**Same VPS for orchestrator + projects. Orchestrator on host, Docker containers for project hosting.**

| VPS Size | Scenario | Verdict |
|----------|----------|---------|
| 16GB ($16/mo) | Claude only, 2 projects, no Docker | Minimum viable |
| 32GB ($35/mo) | Claude + Codex, 2-3 projects | Recommended |
| 64GB ($78/mo) | Claude + Codex + Docker containers, 4-5 projects | Comfortable |

**systemd unit:**

```ini
# /etc/systemd/system/orchestrator.service
[Unit]
Description=DLD Multi-Project Orchestrator
After=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/scripts/vps
EnvironmentFile=/home/ubuntu/scripts/vps/.env
ExecStartPre=/usr/bin/python3 checks/validate-config.py
ExecStart=/home/ubuntu/scripts/vps/orchestrator.sh
ExecStop=/home/ubuntu/scripts/vps/drain-stop.sh
Restart=on-failure
RestartSec=30
StartLimitIntervalSec=300
StartLimitBurst=3
MemoryMax=27G        # 85% of 32GB VPS
MemorySwapMax=0
KillMode=control-group
StandardOutput=journal
StandardError=journal
SyslogIdentifier=orchestrator

[Install]
WantedBy=multi-user.target
```

### 9. Day-1 Bootstrap Checklist

```bash
# Phase 1: VPS Hardening (30 min)
echo "PasswordAuthentication no" >> /etc/ssh/sshd_config
echo "PermitRootLogin no" >> /etc/ssh/sshd_config
systemctl restart sshd
apt install fail2ban ufw -y
ufw default deny incoming && ufw allow 22 && ufw enable

# Phase 2: Dependencies (20 min)
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt install nodejs python3 python3-pip python3-venv sqlite3 whisper-cpp jq -y
npm install -g @anthropic-ai/claude-code@2.1.34
python3 -m venv /home/ubuntu/orchestrator-venv
source /home/ubuntu/orchestrator-venv/bin/activate
pip install python-telegram-bot==22.0

# Phase 3: Pueue (5 min)
# Download binary from GitHub releases
wget https://github.com/Nukesor/pueue/releases/download/v4.0.0/pueue-linux-x86_64 -O /usr/local/bin/pueue
wget https://github.com/Nukesor/pueue/releases/download/v4.0.0/pueued-linux-x86_64 -O /usr/local/bin/pueued
chmod +x /usr/local/bin/pueue /usr/local/bin/pueued
systemctl --user enable pueued && systemctl --user start pueued

# Phase 4: Orchestrator (15 min)
git clone <repo> /home/ubuntu/scripts/vps
sqlite3 /var/orchestrator/orchestrator.db < scripts/vps/schema.sql
cp scripts/vps/.env.example scripts/vps/.env
# Fill: TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, ALLOWED_TELEGRAM_USER_IDS
chmod 600 scripts/vps/.env
cp scripts/vps/systemd/orchestrator.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable orchestrator

# Phase 5: First project (5 min)
# In Telegram: /addproject "SaaS App" /home/ubuntu/saas-app
# Bot creates topic + Pueue group + writes projects.json + seeds SQLite

# Phase 6: Verify (5 min)
systemctl start orchestrator
# Watch: journalctl -u orchestrator -f
# In Telegram: /status -> should show "saas-app: idle"

# Total: ~80 minutes from bare VPS to first project managed
```

### 10. Ops Model

**Heartbeat:** Healthchecks.io ping at end of each loop iteration. Free tier. 15-min grace period.

**SLOs (internal tooling, not customer-facing):**

| SLI | Target | Measurement |
|-----|--------|-------------|
| Orchestrator uptime | 99%/week (43 min budget) | Healthchecks.io |
| Inbox pickup latency | < 5 min during active hours | `find ai/inbox -mmin +5` cron |
| Task completion rate | > 90% of started tasks | `pueue status --json` audit |
| OOM kills/week | 0 target, < 2 acceptable | `dmesg | grep oom` |

**Alerting:**

| Alert | Condition | Channel | Action |
|-------|-----------|---------|--------|
| Orchestrator down | Heartbeat miss > 15 min | Telegram General + Email | SSH, check systemctl |
| OOM kill | dmesg shows oom_killer | Telegram General | Kill orphans, reduce concurrency |
| Project stuck | Phase=autopilot > 90 min | Project topic | `/log`, then `/pause` + `/run` |
| RAM pressure | Free RAM < 3 GB | Telegram General | Kill orphans, pause low-priority |

### 11. Fitness Functions

| # | Property | Check | Trigger |
|---|----------|-------|---------|
| 1 | Inbox SLO | `find ai/inbox -mmin +5 -type f` = 0 | Cron */5 active hours |
| 2 | RAM floor | `MemAvailable >= 3GB` before every launch | Every slot acquisition |
| 3 | LLM count | `pgrep -c "claude\|codex" <= max_concurrent` | Cron */2 |
| 4 | Config validity | JSON parses + paths exist + provider valid | Git pre-commit |
| 5 | DB integrity | `PRAGMA integrity_check` = ok | Daily cron |
| 6 | Liveness | Heartbeat gap <= 120s | Healthchecks.io |
| 7 | cwd discipline | All claude/codex calls use `cd $PROJECT_DIR` | CI grep check |
| 8 | Provider abstraction | No direct `claude`/`codex` calls in orchestrator.sh | CI grep check |
| 9 | Auth whitelist | `from_user.id` check exists in bot | CI grep check |
| 10 | CLI version pin | `claude --version` matches pinned | Weekly cron |
| 11 | Orchestrator LOC | `wc -l orchestrator.sh < 400` | CI check |

### 12. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Claude OOM kills VPS | Medium | High | RAM floor gate + `MemoryMax` cgroup |
| Telegram API down | Low | Medium | Email fallback for critical alerts; orchestrator continues |
| State DB corruption | Low | High | WAL mode + rebuild from `projects.json` |
| Codex memory leak stacks with Claude | Medium | High | Separate Pueue groups, combined RAM floor |
| Anti-pattern #2 (builds too long) | Medium | Medium | 7-day hard timebox. Stop and use Alternative A if exceeded. |

**Irreversible decisions:** Telegram as primary UI (topic IDs in config). SQLite as state store (schema committed). Provider abstraction layer (function signatures).

**Reversible decisions:** Pueue vs custom queue. Poll interval. Priority algorithm. Monitoring stack.

### 13. Build Effort

| Phase | Days | What | Fitness Gate |
|-------|------|------|-------------|
| Days 1-3 | 3 | Pueue + systemd + Telegram bot (status, addproject) + SQLite | Bot responds to /status |
| Days 4-5 | 2 | RAM floor gate + heartbeat + run-agent.sh abstraction | Heartbeat pings for 24h |
| Days 6-7 | 2 | P0 security + Codex runner + inbox voice processing | /addproject creates full project |
| Total | 7 | Production-grade for 2-5 projects | All 11 fitness functions pass |

---

## Alternative C: Production-Grade (Docker-Isolated LLMs + Full Monitoring)

**Philosophy:** LLM CLI processes are untrusted workloads. Contain them like you would any untrusted container.

**Best for:** Founder who runs production containers on the same VPS, has 4+ projects, and needs the orchestrator to be truly unattended for weeks.

---

### 1. Architecture Overview

The key difference from Alternative B: **LLM CLI processes run inside Docker containers with hard memory limits.** This is Fred's insight that nobody else proposed: the OOM blast radius problem is only truly solved by container-level cgroup isolation.

```
VPS Host (64GB RAM)
  |
  |-- orchestrator.service (systemd, host process)
  |     |-- orchestrator.sh (bash loop)
  |     |-- telegram-bot.py (Python, polling)
  |     |-- orchestrator.db (SQLite WAL)
  |
  |-- pueued.service (systemd user service)
  |     |-- group: claude-runner (parallel 2)
  |     |-- group: codex-runner (parallel 1)
  |
  |-- Docker: claude-worker (per-task container)
  |     |-- docker run --rm --memory=10g --memory-swap=10g
  |     |-- mounts: project dir (rw), .claude-state (rw)
  |     |-- env: ANTHROPIC_API_KEY, CLAUDE_CODE_CONFIG_DIR
  |     |-- entrypoint: claude -p "$TASK" --max-turns 30
  |
  |-- Docker: codex-worker (per-task container)
  |     |-- docker run --rm --memory=8g --memory-swap=8g
  |     |-- mounts: project dir (rw)
  |     |-- env: OPENAI_API_KEY
  |     |-- entrypoint: codex exec "$TASK" --sandbox workspace-write
  |
  |-- Docker: project containers (production services)
  |     |-- morning-briefing (--memory=1g)
  |     |-- other-services (--memory=512m each)
  |
  |-- Monitoring stack (Docker Compose)
        |-- Loki (150 MB)
        |-- Promtail (50 MB)
        |-- Grafana (150 MB)
```

### 2. Docker Runner (replaces bare-metal CLI invocation)

```bash
#!/usr/bin/env bash
# /scripts/vps/claude-runner.sh -- Docker-isolated Claude execution

run_claude_docker() {
    local project_dir="$1"
    local task="$2"
    local project_id
    project_id=$(basename "$project_dir")
    local config_dir="/var/orchestrator/projects/${project_id}/.claude-state"

    mkdir -p "$config_dir"

    docker run --rm \
        --name "claude-${project_id}-$$" \
        --memory=10g \
        --memory-swap=10g \
        --cpus=2 \
        -e ANTHROPIC_API_KEY \
        -e "CLAUDE_CODE_CONFIG_DIR=/claude-state" \
        -v "${project_dir}:/workspace:rw" \
        -v "${config_dir}:/claude-state:rw" \
        -v "/home/ubuntu/.claude/settings.json:/root/.claude/settings.json:ro" \
        -w /workspace \
        ghcr.io/anthropics/claude-code:latest \
        claude -p "$task" --max-turns 30 --output-format json

    local exit_code=$?
    return $exit_code
}
```

**Why Docker solves OOM blast radius:**
- `--memory=10g` creates a hard cgroup boundary. Claude cannot exceed 10 GB.
- If Claude leaks, Docker OOM-kills the container. Production containers on the same host are unaffected.
- `--rm` ensures no orphan containers accumulate.
- Host system, Telegram bot, Pueue daemon, and production containers are in separate cgroup hierarchies.

### 3. VPS Topology

**Single VPS, 64GB recommended.** Docker for ALL workloads.

```
64GB VPS RAM Budget:
  OS + Docker daemon:              2 GB
  Orchestrator + bot:              0.5 GB
  Pueue daemon:                    0.1 GB
  Monitoring (Loki+Grafana):       0.5 GB
  2x Claude containers (10g each): 20 GB
  1x Codex container (8g):         8 GB
  3x project containers (1g each): 3 GB
  Safety headroom:                 ~30 GB
```

On 64 GB: two Claude + one Codex + three production containers + monitoring, with 30 GB headroom for leak containment.

On 32 GB: one Claude + one Codex + two production containers. Tight but workable.

### 4. Multi-LLM Strategy

Same as Alternative B (project-level routing in v1), but Docker provides stronger isolation:

- Claude and Codex containers cannot see each other's filesystem mounts.
- Per-project mutex is enforced by SQLite (same as B) AND by Docker container naming (`claude-saas-app-$$` prevents duplicate containers).
- Each container has its own cgroup: one LLM leaking does not affect the other.

### 5. Security Model

Everything from Alternative B, plus:

| Priority | Item | Implementation |
|----------|------|---------------|
| P0 | Container memory limits | `--memory=10g --memory-swap=10g` on every LLM container |
| P0 | No host network | LLM containers use default bridge network (isolated) |
| P1 | Read-only project mount | For QA/audit phases: `-v ${project}:/workspace:ro` |
| P1 | No `--privileged` | Never. LLM containers run unprivileged. |
| P2 | Docker content trust | `DOCKER_CONTENT_TRUST=1` for signed images |

### 6. Monitoring Stack

```yaml
# docker-compose.monitoring.yml
version: '3.8'
services:
  loki:
    image: grafana/loki:2.9.0
    ports: ["3100:3100"]
    volumes: ["loki-data:/loki"]
    deploy:
      resources:
        limits: { memory: 256M }

  promtail:
    image: grafana/promtail:2.9.0
    volumes:
      - /var/log:/var/log:ro
      - ./promtail-config.yml:/etc/promtail/config.yml:ro
    deploy:
      resources:
        limits: { memory: 128M }

  grafana:
    image: grafana/grafana:10.0.0
    ports: ["3000:3000"]
    volumes: ["grafana-data:/var/lib/grafana"]
    deploy:
      resources:
        limits: { memory: 256M }

volumes:
  loki-data:
  grafana-data:
```

**Grafana dashboard provides:**
- RAM per LLM container over time
- Task completion rate per project
- Cost per project per day (from usage_ledger)
- Alert history

### 7. Build Effort

| Phase | Days | What |
|-------|------|------|
| Days 1-3 | 3 | Everything from Alternative B Days 1-3 |
| Days 4-5 | 2 | Docker runners + container configuration |
| Days 6-7 | 2 | Monitoring stack (Loki + Grafana) + dashboards |
| Days 8-10 | 3 | Fitness functions + per-project Unix users + hardening |
| Total | 10 | Production-grade with full observability |

### 8. Trade-Offs

**Optimizes for:** Maximum isolation. Unattended reliability for weeks. OOM blast radius containment.

**At the cost of:** Higher VPS cost (64GB = $78/mo). Docker learning curve. 10-day build (3x Alternative A).

**Biggest risk:** Over-engineering for 2-3 projects. Docker layer adds debugging complexity ("is the issue in the container or the host?").

---

## Comparison Matrix

| Aspect | Alternative A: Minimal | Alternative B: Boring Stack | Alternative C: Docker-Isolated |
|--------|----------------------|---------------------------|-------------------------------|
| **Complexity** | None | Medium | High |
| **Time to working** | 1.5 hours | 7 days | 10 days |
| **Unattended execution** | No | Yes | Yes |
| **Mobile control** | No (SSH only) | Yes (Telegram) | Yes (Telegram) |
| **Multi-LLM** | Manual | Project-level routing | Project-level + isolated |
| **OOM blast radius** | Human manages | systemd cgroup (good) | Docker containers (best) |
| **VPS minimum** | 16 GB | 32 GB | 64 GB |
| **VPS cost** | $16/mo | $35/mo | $78/mo |
| **Innovation tokens** | 0 | 0.5 | 1.5 |
| **Fitness functions** | 0 | 11 | 15 |
| **Projects supported** | 2-3 (attended) | 2-5 (unattended) | 3-10 (unattended) |
| **3am debuggability** | SSH + tmux | Telegram + journalctl | Grafana + docker logs |
| **Biggest risk** | No automation | Anti-pattern #2 (7 days) | Over-engineering |
| **Reversibility** | Trivial | Medium (SQLite, Pueue) | Low (Docker infra) |
| **Migration path** | -> B (add Pueue+bot) | -> C (add Docker runners) | Stable end-state |

---

## Recommendation for Human

**If your priority is shipping Phase 1 consulting content NOW:**
Choose Alternative A. 1.5 hours of setup. tmux + cron. Start writing articles today. The orchestrator problem can wait until you actually have 3+ projects that need unattended management.

**If your priority is productive unattended multi-project management:**
Choose Alternative B. 7-day build. Pueue + Telegram bot + SQLite. This is the sweet spot: boring tech, real automation, mobile control, multi-LLM ready. Phase-gated build means you can stop at day 3 and have a working attended-mode system.

**If you run production containers on the same VPS and cannot tolerate OOM cascade:**
Choose Alternative C. 10-day build. Docker-isolated LLMs. Full monitoring. This is the right answer if a Claude memory leak at 3am would take down a customer-facing service. The cost is real ($78/mo VPS + 10 days build).

**No clear winner.** The choice depends on:
1. How far along is Phase 1? (If zero articles published: A. If Phase 1 is done: B or C.)
2. How many projects need unattended execution right now? (If 0-2: A. If 3+: B.)
3. Are production containers on the same VPS? (If yes: C. If no: B.)

---

## What Happens Next

Human chooses ONE alternative.

The choice is written to `ai/architect/orchestrator/decision.md` with the founder's reasoning.

If Alternative B or C is chosen, the build follows the phase-gated sequence with fitness gates at each phase boundary. The founder can stop at any gate and have a working system.

**The orchestrator is tooling. It must not become the project.**
