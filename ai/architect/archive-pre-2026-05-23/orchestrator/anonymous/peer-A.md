# Operations Architecture Research

**Persona:** Charity (Operations Engineer)
**Focus:** Deployment, observability, SLOs, production readiness
**Date:** 2026-03-10
**System:** Multi-Project Orchestrator — VPS managing N DLD projects via Telegram + GitHub Issues

---

## Research Conducted

- [Claude Code GitHub Issues — Memory Leak: Process Grows to 120+ GB RAM](https://github.com/anthropics/claude-code/issues/4953) — documented OOM kill pattern in long autopilot runs (58 upvotes, open as of Mar 2026)
- [Claude Code #29576 — Memory regression v2.1.62: 6.4GB on 6.5GB system](https://github.com/anthropics/claude-code/issues/29576) — regression Feb 2026, VPS-relevant
- [Claude Code #23883 — High memory usage ~13-16 GB in Team/Teammate mode](https://github.com/anthropics/claude-code/issues/23883) — multi-agent sessions critical reference
- [Claude Code #21378 — Memory leak causes freeze after 20+ minutes (15GB)](https://github.com/anthropics/claude-code/issues/21378) — 11th occurrence report, systemic issue
- [Healthchecks.io — Dead man's switch VPS setup](https://blog.healthchecks.io/2023/05/walk-through-set-up-self-hosted-healthchecks-instance-on-a-vps/) — canonical heartbeat monitoring pattern
- [Uptime Kuma vs Healthchecks.io comparison](https://selfhosting.sh/compare/uptime-kuma-vs-healthchecks/) — Uptime Kuma = active polling; Healthchecks = passive heartbeat; both needed
- [Production Monitoring Stack 2026: Prometheus + Grafana + Loki on single VPS](https://zeonedge.com/so/blog/production-monitoring-prometheus-grafana-loki-alertmanager-vps-2026) — full stack on 2GB VPS, ~512MB for Loki vs ELK's 2GB
- [Build a Log Pipeline: Loki + Promtail + Grafana on Ubuntu VPS](https://www.massivegrid.com/blog/loki-grafana-log-pipeline-ubuntu-vps/) — multi-project log aggregation with label-based routing
- [flock in Bash — Semaphore patterns](https://bashscript.net/using-flock-in-bash-scripts-manage-file-locks-and-prevent-task-overlaps/) — flock for concurrency control, Linux-native
- [Parallelism with Semaphores in Bash](https://7tonshark.com/posts/parallelism-with-semaphores-in-bash/) — N-slot semaphore with flock, production pattern
- [14 Production-Ready Bash Patterns with systemd](https://medium.com/@obaff/14-production-ready-bash-patterns-with-systemd-168e96ea6ed9) — systemd as Bash script supervisor, Restart= semantics
- [How to Use cgroups to Limit Process Resources on Ubuntu](https://oneuptime.com/blog/post/2026-03-02-how-to-use-cgroups-to-limit-process-resources-on-ubuntu/view) — cgroups v2 + systemd MemoryMax for per-process limits
- [Job Checkpointing for Long-Running Batch Processes](https://oneuptime.com/blog/post/2026-02-09-job-checkpointing-long-running-batch/view) — checkpoint file pattern for mid-job recovery
- [Pueue — Task queue manager for shell commands](https://github.com/Nukesor/pueue/wiki/FAQ) — Pueue groups for per-resource concurrency limits
- [Systemd on Linux: Patterns for 2026](https://thelinuxcode.com/systemd-on-linux-components-control-flow-and-practical-patterns-for-2026/) — modern systemd lifecycle, ExecStartPre gates

**Total queries:** 9 web searches, targeted against documented failure modes

---

## Kill Question Answer

**"How will you know this broke in production?"**

**Scenario:** The orchestrator process dies at 3 AM. Claude was mid-autopilot on FTR-042 for the saas-app project. The Telegram bot is unresponsive. No one gets paged.

**Debugging path:**

1. **Alert fires:** Healthchecks.io sends Telegram alert to General topic — "Orchestrator heartbeat missed (last seen 47 min ago)". Threshold: 15 min grace period on a 5-min heartbeat.

2. **First look:** SSH into VPS. `systemctl status orchestrator` → shows state: failed, ExitCode=1, last restart timestamp. `journalctl -u orchestrator -n 100` → last log lines before death.

3. **Diagnosis:**
   - `free -h` → is RAM exhausted? Claude memory leak?
   - `dmesg | grep oom` → OOM killer entries identify which PID died
   - `.orchestrator-state.json` → which project was active, which task
   - Per-project logs → `tail -n 50 /var/log/orchestrator/saas-app.log`

4. **Mitigation:** `systemctl start orchestrator` → auto-restarts (systemd `Restart=on-failure`). If RAM-caused: kill orphan Claude processes first (`pkill -f "claude"` then restart). Check checkpoint file for which task was mid-run.

5. **Resolution:** If mid-autopilot task was interrupted: state file shows `"phase": "autopilot", "detail": "FTR-042"`. Orchestrator restart picks up from task boundary (not mid-task — checkpoint files track task-level completion). Notify project topic: "Orchestrator restarted. Resuming FTR-042."

**Critical observability gaps in current spec:**
- No heartbeat mechanism defined
- No per-project structured logging (only shell echo)
- RAM ceiling per Claude process is dangerously underestimated (spec says 200-500MB; reality is 2-16GB)
- Semaphore orphan cleanup on crash not addressed
- No checkpoint files — restart could re-run already-completed tasks

---

## CRITICAL: Claude CLI Memory Reality

**This is the most dangerous assumption in the current spec.**

The spec states: "RAM на 1 Claude процесс: 200-500 MB"

**What GitHub issues document (March 2026):**

| Scenario | RAM observed | Issue |
|----------|-------------|-------|
| Normal single session | 500MB-2GB | Baseline |
| Extended session (20+ min) | 6-16 GB | #21378, #29576 |
| Multi-agent / Team mode | 13-16 GB | #23883 |
| Memory leak (uncapped) | 120+ GB → OOM kill | #4953, #11315 |
| Autopilot 30-turn run | 2-8 GB typical | #29576 context |

**Implication for VPS sizing:**

| VPS RAM | Safe concurrent Claude | Notes |
|---------|----------------------|-------|
| 8 GB | 1 safely, 2 risky | OOM risk if any session leaks |
| 16 GB | 2 safely, 3 risky | Minimum recommended |
| 32 GB | 4-5 comfortably | Headroom for leak recovery |

**The spec's `max_concurrent_claude: 2` on 8GB VPS is a ticking time bomb.**

---

## Proposed Ops Decisions

### Deployment Strategy

**Pattern:** systemd service + file-gate checkpointing + cgroups memory limits

**Why this pattern:**
The orchestrator is a long-running daemon, not a web service. It doesn't need blue-green or canary deploys. It needs: automatic restart on crash, resource limits to prevent cascade failures, and state persistence across restarts. systemd handles all three natively without adding dependencies.

**Deployment Flow:**

```
┌──────────────────────────────┐
│  git pull + chmod scripts    │
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│  systemctl stop orchestrator │  ← drain: wait for active Claude
└──────────────┬───────────────┘    to finish (ExecStop script)
               ↓
┌──────────────────────────────┐
│  Deploy new scripts          │
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│  systemctl start orchestrator│  ← reads state.json → resume
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│  Verify heartbeat ping       │  ← healthchecks.io check within 2 min
└──────────────────────────────┘
```

**Rollback Plan:**
- **Trigger:** Heartbeat miss within 5 min of deploy, or Telegram bot silent
- **Time to rollback:** < 2 minutes (`git stash && systemctl restart orchestrator`)
- **Process:** Manual — this is solo founder tooling, not a product SLA

**No database migrations:** State is flat JSON files. Schema changes = backwards-compatible field additions only. Breaking changes require a migration script run before deploy.

---

### systemd Unit Configuration

```ini
# /etc/systemd/system/orchestrator.service
[Unit]
Description=DLD Multi-Project Orchestrator
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/scripts/vps
ExecStartPre=/usr/bin/test -f /home/ubuntu/scripts/vps/projects.json
ExecStart=/home/ubuntu/scripts/vps/orchestrator.sh
ExecStop=/home/ubuntu/scripts/vps/drain-stop.sh
Restart=on-failure
RestartSec=30
StartLimitIntervalSec=300
StartLimitBurst=3

# Memory ceiling — prevent runaway Claude leak from killing the VPS
MemoryMax=14G
MemorySwapMax=0

# Stdout/stderr → journald (structured via systemd)
StandardOutput=journal
StandardError=journal
SyslogIdentifier=orchestrator

# Kill orphan Claude processes on service stop
KillMode=control-group

[Install]
WantedBy=multi-user.target
```

**Key decisions:**
- `MemoryMax=14G` on a 16GB VPS: leaves 2GB for OS + Telegram bot + monitoring stack
- `KillMode=control-group`: stops ALL child processes (including Claude CLI children) on service stop
- `StartLimitBurst=3` with `RestartSec=30`: prevents restart storm if Claude OOM kills every cycle
- `ExecStartPre` gate: fail fast if projects.json missing, not silent loop failure

---

### Semaphore Implementation: Revised

The current spec's `flock` semaphore is correct in principle but has two failure modes:

**Problem 1 — Lock files survive a crash:**
If orchestrator dies while holding slot-1, the flock file on `/tmp/claude-semaphore/slot-1` persists but no process holds it. flock releases when the file descriptor closes — so on crash the lock IS released. This is actually correct behavior. flock on Linux is advisory and process-death releases the lock automatically.

**Problem 2 — Zombie Claude processes:**
If the orchestrator crashes while Claude is running as a child, `KillMode=control-group` in the systemd unit handles cleanup. Without systemd, orphan Claude processes accumulate and consume RAM indefinitely.

**Revised semaphore with RAM-aware admission:**

```bash
#!/usr/bin/env bash
# semaphore.sh — RAM-aware Claude slot manager

SEMAPHORE_DIR="/tmp/claude-semaphore"
MAX_CONCURRENT="${MAX_CONCURRENT_CLAUDE:-2}"
RAM_FLOOR_GB=3  # refuse to launch Claude if free RAM < this

mkdir -p "$SEMAPHORE_DIR"

acquire_claude_slot() {
    local project_name="$1"

    # RAM check before acquiring slot
    local free_ram_kb
    free_ram_kb=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
    local free_ram_gb=$(( free_ram_kb / 1024 / 1024 ))

    if [[ $free_ram_gb -lt $RAM_FLOOR_GB ]]; then
        log_warn "[$project_name] Refusing Claude launch: only ${free_ram_gb}GB RAM free (floor: ${RAM_FLOOR_GB}GB)"
        return 1
    fi

    # Slot acquisition with timeout (avoid infinite wait)
    local timeout=300  # 5 min max wait
    local elapsed=0

    while [[ $elapsed -lt $timeout ]]; do
        for i in $(seq 1 "$MAX_CONCURRENT"); do
            local lock_file="$SEMAPHORE_DIR/slot-$i"
            if flock -n -x "$lock_file" true 2>/dev/null; then
                echo "$i"
                return 0
            fi
        done
        sleep 10
        elapsed=$((elapsed + 10))
    done

    log_error "[$project_name] Timeout waiting for Claude slot after ${timeout}s"
    return 1
}

release_claude_slot() {
    local slot="$1"
    # flock releases on FD close — this is automatic, but log it
    log_info "Released Claude slot $slot"
}
```

**Why `MAX_CONCURRENT=1` on 8GB VPS, not 2:**
With documented 6-16GB per Claude session in extended runs, two concurrent sessions on 8GB = certain OOM. On 16GB VPS: `MAX_CONCURRENT=2` is defensible with RAM floor check.

---

### Observability Model

**SLIs (Service Level Indicators):**

| Component | SLI | Target | Measurement |
|-----------|-----|--------|-------------|
| Orchestrator heartbeat | Alive | < 15 min gap | healthchecks.io ping |
| Telegram bot responsiveness | `/status` response | < 10 seconds | manual spot check |
| Inbox processing | Idea → file latency | < 5 min | timestamp diff in inbox file |
| Autopilot completion | Task done rate | > 90% of started tasks | state.json audit |
| Claude OOM rate | OOM kills per week | 0 target / <2 acceptable | dmesg + oom_killer logs |

**SLOs (Service Level Objectives):**
- Orchestrator uptime: 99% per week (43 min downtime budget) — this is internal tooling, not customer-facing
- Inbox processing: 95% of voice/text messages processed within 10 min
- Autopilot: 85% of started tasks complete without manual intervention

**Error Budget:**
- At >2 OOM kills/week: reduce `MAX_CONCURRENT`, increase `RAM_FLOOR_GB`
- At >3 orchestrator restarts/day: pause automation, investigate root cause before resuming

**Structured Logging:**

```bash
# orchestrator.sh — structured log function
log_json() {
    local level="$1"
    local project="${2:-orchestrator}"
    local message="$3"
    local extra="${4:-{}}"

    printf '{"ts":"%s","level":"%s","service":"orchestrator","project":"%s","msg":"%s","meta":%s}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        "$level" \
        "$project" \
        "$message" \
        "$extra"
}

# Usage:
log_json "info" "saas-app" "Starting autopilot" '{"task":"FTR-042","slot":1}'
log_json "error" "orchestrator" "OOM detected" '{"free_ram_gb":1,"pid":12345}'
```

**Promtail label strategy for multi-project aggregation:**

```yaml
# /etc/promtail/config.yml
scrape_configs:
  - job_name: orchestrator
    static_configs:
      - targets: ['localhost']
        labels:
          job: orchestrator
          host: vps-01
          __path__: /var/log/orchestrator/orchestrator.log

  - job_name: project_logs
    static_configs:
      - targets: ['localhost']
        labels:
          job: project
          host: vps-01
          __path__: /var/log/orchestrator/*.log
    pipeline_stages:
      - json:
          expressions:
            project: project
            level: level
      - labels:
          project:
          level:
```

**Loki query patterns for debugging:**

```logql
# All errors in last hour
{job="orchestrator"} |= "error" | json | line_format "{{.ts}} [{{.project}}] {{.msg}}"

# OOM events
{job="orchestrator"} |= "OOM" | json

# Activity on specific project
{job="project", project="saas-app"} | json | line_format "{{.ts}} {{.level}} {{.msg}}"
```

**Distributed Tracing:**
Not applicable for this system. The orchestrator runs sequential shell scripts, not distributed services. Structured logs with correlation via `task_id` and `project` labels are sufficient. Adding OpenTelemetry would be overengineering for a solo-developer toolchain.

---

### Dead Man's Switch Design

**Three-layer heartbeat design:**

```
Layer 1: Orchestrator self-ping (every 5 min loop)
         orchestrator.sh → curl -fsS https://hc-ping.com/${ORCHESTRATOR_CHECK_UUID}
         Grace period: 15 min
         Alert: Telegram General topic + email

Layer 2: Per-project activity check (daily)
         cron: 0 9 * * * check-project-activity.sh
         Fires if any project has had 0 activity for >24h AND is enabled+not-paused
         Alert: Telegram General topic only (informational)

Layer 3: Telegram bot liveness (Uptime Kuma)
         Uptime Kuma polls /health endpoint on Telegram bot process (HTTP on localhost:8080)
         Alert: email (Telegram bot might be down if Telegram is down)
```

**Dead man's switch for the orchestrator itself:**

```bash
# At the top of each orchestrator event loop iteration:
ping_heartbeat() {
    local uuid="${ORCHESTRATOR_HB_UUID}"
    if [[ -n "$uuid" ]]; then
        curl -fsS --max-time 5 "https://hc-ping.com/${uuid}" > /dev/null 2>&1 || true
        # "|| true" — heartbeat failure must NEVER crash the orchestrator
    fi
}

# Called at END of each successful loop cycle (not beginning)
# This way: if loop hangs, heartbeat is missed → alert fires
```

**Why call at END not START:** If called at loop start, a hung Claude process (infinite wait) would still ping heartbeat at next loop start. Calling at end catches the hung state.

---

### Restart Recovery: VPS Reboot Mid-Autopilot

**The scenario:**
1. Orchestrator running autopilot on FTR-042 for saas-app
2. VPS reboots (kernel update, OOM, manual reboot)
3. Claude CLI process dies mid-turn

**What state is preserved:**
- `projects.json` — project registry (persistent file)
- `.orchestrator-state.json` — last known phase per project (persistent file)
- Git history — any commits Claude made before crash are safe
- AI features files — if Claude wrote spec/task files before crash, they persist

**What is NOT preserved:**
- Claude's in-progress context (turn 8 of 20 — lost)
- Semaphore locks (released by process death — correct behavior)
- Active Claude CLI session (dies with VPS)

**Recovery protocol on restart:**

```bash
# orchestrator.sh startup sequence
recover_from_crash() {
    local state_file=".orchestrator-state.json"

    if [[ ! -f "$state_file" ]]; then
        log_json "info" "orchestrator" "No state file, fresh start"
        return 0
    fi

    # Read last state for each project
    for project in $(jq -r '.projects | keys[]' "$state_file"); do
        local phase
        phase=$(jq -r ".projects[\"$project\"].phase" "$state_file")
        local detail
        detail=$(jq -r ".projects[\"$project\"].detail" "$state_file")

        case "$phase" in
            "autopilot")
                # Task was in-progress — mark as interrupted, not failed
                # Autopilot will retry the task (tasks are idempotent at file level)
                log_json "warn" "$project" "Crashed mid-autopilot" "{\"task\":\"$detail\"}"
                notify_project "$project" "Orchestrator restarted. Was running $detail — will retry."
                # Reset phase to "idle" so normal check cycle picks it up
                update_state "$project" "idle" ""
                ;;
            "idle"|"inbox")
                # No in-progress work — clean restart
                log_json "info" "$project" "Clean state on restart" "{\"phase\":\"$phase\"}"
                ;;
        esac
    done
}
```

**Task-level idempotency requirement:**
For this recovery to work, autopilot tasks MUST be idempotent. A task that was 70% done will be restarted from the beginning. This is acceptable because:
- DLD autopilot generates code/specs into files
- Git tracks what was already committed
- Uncommitted changes are in the worktree → Claude can see them and skip or continue

**This is NOT crash-safe for tasks that write to external systems** (e.g., if autopilot posts to GitHub Issues, it might double-post). Mitigation: check for existing GitHub Issue before creating.

---

### Alerting Strategy

**Alerting Principles:**
- Solo founder — only alert on things that require action NOW (at 3 AM)
- Telegram is both the control plane AND the alert channel — this is a risk (see Concerns section)
- Every alert must say what to do, not just what happened

**Alerts:**

| Alert Name | Condition | Severity | Channel | Action |
|------------|-----------|----------|---------|--------|
| Orchestrator down | Heartbeat miss >15 min | Critical | Telegram General + Email | SSH in, check `systemctl status orchestrator` |
| OOM kill detected | `dmesg` shows oom_killer | Critical | Telegram General | Kill orphan Claude processes, reduce MAX_CONCURRENT |
| Project stuck | Project in "autopilot" phase > 90 min | Warning | Project topic | `/log` to inspect, `/pause` then `/run` |
| Disk space low | VPS disk >80% | Warning | Telegram General | Clean old logs, worktrees, Claude cache |
| RAM pressure | Free RAM < 2GB | Warning | Telegram General | Kill orphan Claude, pause low-priority projects |
| No activity for 24h | All projects idle, founder active | Info | General topic | Informational — did automation stop working? |

**Alert implementation for Telegram (no external tool needed for MVP):**

```bash
# alert.sh — send to appropriate topic
alert_critical() {
    local message="$1"
    send_telegram_message "${GENERAL_TOPIC_ID}" "ALERT: ${message}"
    send_email_alert "${message}"  # fallback if Telegram is down
}

alert_project() {
    local project="$1"
    local message="$2"
    local topic_id
    topic_id=$(get_project_topic_id "$project")
    send_telegram_message "${topic_id}" "${message}"
}
```

**On-call rotation:** Solo founder. No rotation. Budget: 1-2 incidents/week acceptable. More = revisit architecture.

---

### Log Aggregation Across N Projects

**Strategy: Structured JSON to files, Promtail → Loki, query in Grafana**

**Directory structure:**

```
/var/log/orchestrator/
├── orchestrator.log        # main event loop
├── saas-app.log            # project-specific events
├── side-project.log        # project-specific events
└── freelance.log           # project-specific events

/home/ubuntu/scripts/vps/
├── .orchestrator-state.json  # runtime state (not logs)
└── projects.json             # config
```

**Log rotation (logrotate config):**

```
/var/log/orchestrator/*.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
    create 640 ubuntu ubuntu
}
```

**For MVP (before Loki setup):** `journalctl -u orchestrator -f` is sufficient. Loki adds querying across projects.

**Loki resource footprint on VPS:**

| Component | RAM | CPU | Notes |
|-----------|-----|-----|-------|
| Loki | ~150MB | Low | Label-indexed, not full-text |
| Promtail | ~50MB | Low | Log tail agent |
| Grafana | ~150MB | Low | UI + alerting |
| **Total** | **~350MB** | Low | Viable on 16GB VPS |

This is why Loki beats ELK: Elasticsearch alone needs 2GB heap.

---

### Backup Strategy

**What to back up and how:**

| Data | Location | Backup method | RPO | Where |
|------|----------|---------------|-----|-------|
| Project state | `.orchestrator-state.json` | Git commit on every change | Per change | GitHub |
| Projects config | `projects.json` | Git commit on change | Per change | GitHub |
| Orchestrator scripts | `scripts/vps/` | Git (already) | Per commit | GitHub |
| Per-project AI data | `ai/` directories | Git (already per project) | Per commit | GitHub |
| VPS system config | `/etc/systemd/` | Ansible/snapshot | Weekly | S3 or local |
| Logs | `/var/log/orchestrator/` | logrotate 14-day retain | Daily | VPS local |

**No database to back up** — the existing design uses JSON files which are in git. This is the right call for this scale.

**VPS snapshot:** Hetzner/DigitalOcean weekly automated snapshots. $1-2/month. Recovery: restore snapshot + `git pull` + `systemctl start orchestrator`. RTO: ~15 minutes.

**What you LOSE in worst case (VPS dies, no snapshot):**
- All logs (not in git) — acceptable
- In-progress Claude work (uncommitted) — acceptable, will retry
- State file (`.orchestrator-state.json`) — lose current phase, restart from idle — acceptable
- Everything committed to git — SAFE

**Risk:** State file changes without git commit (common in bash orchestrator). Mitigation: commit state file to git on every write via post-write hook.

---

### Resilience Patterns

**Failure Modes:**

| Dependency | Failure Impact | Mitigation | Degraded Mode |
|------------|----------------|------------|---------------|
| Claude CLI crashes (OOM) | Current task fails | systemd restart orchestrator, KillMode=control-group | Task retried next cycle |
| Claude memory leak | Cascading OOM | RAM floor check before each slot; cgroups MemoryMax on orchestrator | New Claude sessions blocked until RAM recovered |
| Telegram API down | Bot unresponsive, no alerts | Email fallback for critical alerts | Orchestrator continues, just no Telegram notifications |
| VPS reboots | All processes die | systemd `After=network-online.target` + `Restart=on-failure` | Restarts within 1 min, tasks retry |
| Anthropic API rate limit | Claude exits early | `--max-turns` limit + retry in next cycle (5-30 min) | Task queued, not dropped |
| GitHub API down | git push fails | git commits locally, retry push in next cycle | Work continues locally |
| flock semaphore hung | Claude session never launches | timeout in `acquire_claude_slot` (5 min max) | Project skipped this cycle, logged |
| Disk full | Logs/worktrees fill disk | logrotate + worktree pruning after each task | Alert fires; orchestrator may fail writes |

**Timeout Strategy:**
- `acquire_claude_slot`: 5 min max wait
- Claude CLI execution: `timeout 900 claude --max-turns 30 ...` (15 min absolute ceiling)
- Telegram API calls: 10s timeout, 3 retries
- healthchecks.io ping: 5s max-time, failure is non-fatal

**Graceful Degradation Order:**

```
All projects running (ideal)
  → RAM pressure: pause low-priority projects
    → RAM critical: pause medium-priority, only high runs
      → RAM exhausted: pause ALL Claude, keep Telegram bot alive
        → Telegram down: orchestrator continues, email alerts
          → Full crash: systemd restarts within 30s
```

---

### VPS Sizing Decision

**Recommendation: 16GB RAM minimum. 32GB preferred.**

**Reasoning:**

| Component | RAM need |
|-----------|----------|
| OS + systemd | 0.5 GB |
| Telegram bot (Python) | 0.1 GB |
| Monitoring stack (Loki + Promtail + Grafana) | 0.4 GB |
| Orchestrator shell process | 0.05 GB |
| 1x Claude CLI (normal) | 2-4 GB |
| 1x Claude CLI (extended autopilot, leak possible) | 6-16 GB |
| 2x Claude CLI concurrent | 4-32 GB |
| **Safety headroom** | **2 GB** |

**8GB VPS verdict:** Only safe with `MAX_CONCURRENT=1` and strict RAM floor enforcement. One leaked Claude session will OOM the entire VPS. Not recommended for production use.

**16GB VPS verdict:** Safe with `MAX_CONCURRENT=2` and `RAM_FLOOR_GB=4`. Extended runs can leak to 8-12GB without crashing. This is the minimum viable production VPS.

**32GB VPS verdict:** Comfortable for 3-4 concurrent projects. Provides real headroom against memory leak incidents.

**Cost comparison (Hetzner, March 2026):**
- CX21 (4GB): €4.51/mo — insufficient
- CX31 (8GB): €8.21/mo — risky, only with MAX_CONCURRENT=1
- CX41 (16GB): €15.90/mo — recommended minimum
- CX51 (32GB): €31.10/mo — preferred for 4+ active projects

At the founder's $50-100/month VPS budget, CX51 (32GB) is achievable and removes the RAM anxiety entirely.

---

### CI/CD for the Orchestrator Itself

The orchestrator is tooling, not a product. "CI/CD" is:

1. `git pull` on VPS (or Ansible deploy script)
2. `systemctl restart orchestrator`
3. Watch journalctl for 2 min for errors
4. If heartbeat pings within 5 min: deploy successful

**No automated deploy pipeline needed.** The deployment risk is low (bash scripts, no compiled artifacts). The rollback risk is higher (if new orchestrator crashes constantly, `git stash` and restart). Manual deploy is the right choice here.

---

## Cross-Cutting Implications

### For Domain Architecture
- The orchestrator is NOT a domain service. It is infrastructure for the DLD framework. It should not encode business logic.
- Bounded contexts: each project directory is a self-contained unit. The orchestrator only touches the boundary: inbox, state file, notification.
- Independent deploys: each project's DLD lifecycle is independent. The orchestrator coordinates but does not depend on project internals.

### For Data Architecture
- `.orchestrator-state.json` must be git-committed on every write (not just on clean shutdown)
- If state corruption occurs (partial write), fallback: delete state file, restart from idle
- `projects.json` is the SSOT for project registry. Must not be modified by automation (only by `addproject` command with validation)

### For API Design
- Health check endpoint: Telegram bot should expose `GET /health` on localhost:8080 for Uptime Kuma
- The orchestrator has no API — control is via Telegram commands and the state file
- Secrets (ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN) must be in `.env`, not in scripts

### For Security
- `KillMode=control-group` in systemd unit prevents orphan Claude processes accumulating tokens
- Semaphore directory `/tmp/claude-semaphore/` must be owned by orchestrator user only (chmod 700)
- Log files may contain sensitive data (task names, project names) — store in `/var/log/orchestrator/`, not in git

---

## Concerns & Recommendations

### Critical Issues

- **Claude CLI memory leak is unmitigated in current spec.** Description says "200-500 MB per Claude process." Reality per GitHub issues: 2-16GB normal, up to 130GB with leak. On 8GB VPS this means `MAX_CONCURRENT=1` is the only safe config.
  - **Fix:** Add RAM floor check before slot acquisition. Set `MemoryMax=14G` via systemd cgroups on 16GB VPS. Set `MAX_CONCURRENT=1` on 8GB until Anthropic fixes the leak.
  - **Rationale:** An OOM kill of the entire VPS at 3 AM takes down ALL projects simultaneously. This is the #1 production risk.

- **No heartbeat defined in the spec.** The orchestrator can die silently with no alert.
  - **Fix:** Add healthchecks.io ping at end of each event loop. $0 cost (free tier). 30 minutes to implement.
  - **Rationale:** Without a dead man's switch, the founder won't know the orchestrator stopped until they check manually — potentially days later.

- **Semaphore orphan cleanup not addressed.** If the orchestrator crashes while holding a slot, flock correctly releases the lock (process death). But the Claude CLI child process may continue running as an orphan.
  - **Fix:** `KillMode=control-group` in systemd unit. This ensures all child processes (including Claude) are killed when the orchestrator service stops.
  - **Rationale:** An orphan Claude process continues consuming RAM and Anthropic API quota with no supervision.

- **State file write is not atomic.** Bash `>` redirection can produce partial writes on crash.
  - **Fix:** Write to `.orchestrator-state.json.tmp`, then `mv` (atomic on same filesystem). `mv` is atomic on Linux.
  - **Rationale:** A corrupted state file on VPS reboot can prevent orchestrator from starting.

### Important Considerations

- **Telegram is both control plane and alert channel.** If Telegram API is down, you lose both the control interface AND the alerting system simultaneously.
  - **Recommendation:** Add email as secondary alert channel for critical alerts only. Gmail SMTP with app password — free, reliable.

- **Log volume across N projects.** With 5 projects running autopilot daily, log volume grows quickly. Without logrotate, disk fills up.
  - **Recommendation:** Configure logrotate from day one (daily, 14-day retain, compress). Add disk usage to Uptime Kuma monitoring.

- **Claude CLI version pinning.** Memory regressions in v2.1.62 show that upgrading Claude CLI can break production.
  - **Recommendation:** Pin Claude CLI version in the deploy script. Test new versions on a single project before rolling out to all projects. `npm list -g @anthropic-ai/claude-code` to check current version.

### Questions for Clarification

- How many projects will be actively running autopilot simultaneously at peak? (This directly determines VPS sizing)
- Is data loss of in-progress Claude work acceptable (task will retry from scratch)? Or do we need mid-task checkpoint files?
- Is the founder okay with 1-2 minutes of downtime when the orchestrator restarts after an OOM kill?
- Should per-project logs be visible in Telegram via `/log` command, or is SSH+journalctl acceptable for debugging?

---

## References

- [Claude Code GitHub Issues — Memory tracking](https://github.com/anthropics/claude-code/issues?q=memory+leak) — live tracking of Claude CLI RAM issues
- [Healthchecks.io — Dead man's switch for cron/scripts](https://healthchecks.io) — free tier covers 20 checks
- [Uptime Kuma — Self-hosted active monitoring](https://github.com/louislam/uptime-kuma) — runs on VPS, monitors HTTP endpoints
- [Pueue — Shell command queue manager](https://github.com/Nukesor/pueue) — alternative to flock semaphore; adds priority queues and persistence
- [Google SRE Book — Chapter 4: SLOs](https://sre.google/sre-book/service-level-objectives/) — SLO/SLI framework
- [systemd cgroups v2 resource limits](https://www.freedesktop.org/software/systemd/man/systemd.resource-control.html) — MemoryMax, KillMode reference
- [Grafana Loki — Log aggregation for small teams](https://grafana.com/docs/loki/latest/) — 512MB VPS footprint vs ELK's 2GB+
- [Production Monitoring Stack 2026 on VPS](https://zeonedge.com/so/blog/production-monitoring-prometheus-grafana-loki-alertmanager-vps-2026) — Prometheus + Loki + Grafana on single 2GB VPS
