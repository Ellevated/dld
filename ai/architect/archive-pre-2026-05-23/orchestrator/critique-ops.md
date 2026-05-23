# Operations Architecture Cross-Critique

**Persona:** Charity (Operations Engineer)
**Phase:** 2 — Peer Review
**Date:** 2026-03-10
**System:** Multi-Project Orchestrator — VPS managing N DLD projects via Telegram + GitHub Issues

---

## Peer Analysis Reviews

### Analysis B (Devil's Advocate / Fred)

**Agreement:** Partially Agree

**Reasoning from ops perspective:**

Fred lands the most important systemic critique: the orchestrator can die silently with no alert, and the flock semaphore fails in ways the spec does not address. I agree completely. His "load-bearing shell script" warning is exactly what I would say from 3 AM experience — a 400-line bash script with no error handling standard is a liability that compounds with every edge case added.

His stress test #1 (Claude hangs, slot held, all other projects blocked silently) is a real production scenario. I documented the same thing in my research but called it differently: `acquire_claude_slot` with no timeout ceiling means the orchestrator can be stuck for hours with zero notification.

However, Fred overweights the philosophical critique at the expense of specific fixes. He points out the problems but the proposed mitigations remain vague. "Pueue is simpler" is valid but he doesn't address what Pueue does when the Pueue daemon itself crashes — which is the same restartability problem he criticizes in the bash orchestrator. systemd handles pueued restart the same way it handles orchestrator.sh restart. The complexity reduction from adopting Pueue is real but smaller than Fred implies.

His "is this Phase 1 work?" question is legitimately useful and completely outside my ops scope. I will defer to the founder on that framing.

**Missed gaps:**

- Fred identifies the "orchestrator dies silently" problem but doesn't give the specific fix: healthchecks.io dead man's switch ping at the end of each loop iteration. This is free, takes 30 minutes to implement, and solves his SPOF #3 completely.
- He raises the stale lock concern but doesn't address that flock on Linux releases locks on process death automatically (FD close). The real orphan problem is the Claude child process, not the flock file. The fix is `KillMode=control-group` in systemd, not a different concurrency primitive.
- His Telegram SPOF analysis (SPOF #2) correctly identifies the risk but misses the obvious mitigation: polling mode (no inbound port) + email fallback for critical alerts. This costs nothing.

---

### Analysis C (DX Architect / Dan)

**Agreement:** Agree

**Reasoning from ops perspective:**

Dan's Pueue recommendation is operationally sound and I endorse it from an ops angle. Pueue's daemon-level restart recovery via systemd eliminates the "who's watching the orchestrator" problem for task queue state. The fact that `pueue status --json` is the debugging interface instead of "SSH, grep, count processes, check state file" is a genuine operational improvement.

His DX metrics table is exactly how I think about this system's SLOs. "Time to debug stuck task: <2 min" is a real SLI. The current bash approach cannot guarantee this because there is no structured log of which task was running at process death. Pueue's per-task stdout capture changes this.

His 3-day build plan is the right framing — if the build exceeds 3 days, something is over-engineered.

**Missed gaps:**

- Dan doesn't address RAM. Pueue's `pueue parallel 2` prevents two Claude processes from starting concurrently, but it doesn't prevent one Claude process from leaking to 8GB and starving the second slot. The RAM floor check I described (refuse slot if < 3GB free) must be implemented regardless of whether the queue is flock or Pueue.
- The Pueue daemon itself is a new monitoring target. Uptime Kuma or healthchecks.io needs to watch pueued, not just the orchestrator. Dan's "systemd watches pueued" is correct but incomplete — you also need the heartbeat confirming that pueued is actually processing tasks, not just running.
- He defers GitHub Issues integration with a note about adding `github_repo` as an optional field. Correct call — but he doesn't specify how this interacts with inbox delivery latency if GitHub API is slow. The inbox write must never block on GitHub API response.

---

### Analysis D (Security Architect / Bruce)

**Agreement:** Agree

**Reasoning from ops perspective:**

Bruce's security analysis is production-quality and I have very few objections. His STRIDE table is the most complete threat model I've seen for this system. Three points align directly with my ops concerns:

First, the `from_user.id` whitelist is a security gap that is also an ops gap — without it, anyone in the group can spam `/run` commands, which means unbounded Claude slot requests and RAM exhaustion. The security fix is also the ops fix.

Second, his recommendation to use polling mode rather than webhook mode is correct. Polling mode requires no inbound port, no SSL cert management, and no nginx proxy. That is one fewer surface area to monitor and one fewer failure mode at 3 AM.

Third, local whisper.cpp for voice transcription is the right call. An OpenAI API dependency in the transcription path means voice inbox processing fails whenever OpenAI has an outage — which is separate from and uncoordinated with Anthropic API outages. Local whisper.cpp makes the system single-dependency (Anthropic API only, not Anthropic + OpenAI simultaneously).

**Missed gaps:**

- Bruce documents cgroup memory limits in the context of security (`systemd-run --scope -p MemoryMax=600M`) but 600MB is drastically too low based on documented Claude CLI behavior (2-16GB in real autopilot runs). This would cause constant OOM kills of legitimate Claude sessions. The correct cgroup limit is per the VPS tier: 14GB MemoryMax on a 16GB VPS.
- He doesn't address what happens to the audit log when disk fills up. An append-only audit log with no rotation policy on a VPS with active Claude sessions will fill the disk and take down everything. logrotate is mandatory for the audit log as much as for the operational logs.
- The systemd credential approach is excellent but he doesn't mention that the Telegram bot token must also have a rotation procedure. Tokens don't expire, so the "rotate on suspected compromise" guidance needs to be explicit about what "suspected compromise" looks like operationally (e.g., unexpected auth attempts in the audit log).

---

### Analysis E (LLM Architect / Erik)

**Agreement:** Agree

**Reasoning from ops perspective:**

Erik's research is the most operationally useful of all peers. His documentation of cross-session contamination (GitHub issue #30348) is a production blocker that no other peer identified, and it maps directly to my RAM concerns — separate `CLAUDE_CODE_CONFIG_DIR` per project is the correct isolation mechanism, and it costs nothing.

His explicit ruling-out of Agent Teams (13-16GB RAM, experimental bugs, intra-project only) is the right call. I was surprised this wasn't obvious to everyone: 13-16GB on an 8GB VPS is immediate OOM. No amount of architectural elegance changes that arithmetic.

His per-phase `--max-turns` tuning table (triage: 5-8, spark: 30-40, autopilot: 25-35) is exactly the kind of specific configuration that ops engineers need to prevent runaway processes. `--max-budget-usd 2.00` as a safety valve per autopilot run is smart.

**Missed gaps:**

- Erik establishes that the flock semaphore is "fine" and "the flock approach works" but doesn't acknowledge the RAM floor check requirement. Flock prevents a second slot from being acquired but doesn't check whether the first slot's Claude process has leaked to 8GB and made a second slot unsafe even if technically unoccupied. The RAM floor check is a separate gate that must coexist with flock.
- He doesn't address what happens to the `CLAUDE_CODE_CONFIG_DIR` directories over time. Separate config dirs per project accumulate session history, which grows indefinitely. A cleanup policy for old session data is needed.
- His cost estimate for Haiku triage ($0.06/day for 100 messages) is correct, but he doesn't address the case where the Anthropic API itself is rate-limited or down. Rule-based fallback for triage must exist — if Haiku is unavailable, unstructured messages should go to the General inbox, not be dropped.

---

### Analysis F (Evolutionary Architect / Neal)

**Agreement:** Agree

**Reasoning from ops perspective:**

Neal's fitness function suite is the most operationally concrete output in the peer set. The inbox latency check (`find ai/inbox -mmin +5`), semaphore correctness check (`pgrep -c 'claude'` vs config), and liveness heartbeat implementation are all runnable today. This is the difference between architecture and operations engineering — runnable checks that tell you if the architecture is still behaving correctly.

His scaling inflection point analysis (3-4 projects: RAM ceiling; 5-6 projects: loop cycle time; 8-10 projects: orchestrator complexity) maps exactly to what I would set as trigger thresholds for ops escalation.

The symlinked release pattern for zero-downtime upgrades is elegant and operationally sound. Atomic `ln -sfn` swap means the next loop cycle uses new code without restart. The grace window (wait for no active Claude processes) is exactly how I'd design a safe deploy.

**Missed gaps:**

- Neal's semaphore check (`pgrep -c 'claude'`) will false-positive if any other user on the VPS runs Claude for any reason, or if the founder's own Claude session is open in a different terminal. The check should filter by the orchestrator user and project working directory: `pgrep -u orchestrator-user -f "claude.*project-dir"`.
- The inflection point at 3-4 projects (RAM ceiling) assumes 500MB per Claude process. This is wrong by 4-30x based on documented behavior. The real inflection point for RAM is at 2 projects on an 8GB VPS, not 4. This needs correction.
- His inotifywait + polling fallback recommendation is correct. But he doesn't address that inotifywait dies silently if the directory it watches is deleted and recreated (common if `projects.json` is managed by another tool). The polling fallback catching this within one cycle is the right safety net.

---

### Analysis G (Data Architect / Martin)

**Agreement:** Partially Agree

**Reasoning from ops perspective:**

Martin's identification of the `.orchestrator-state.json` race condition (citing the 335 corruption events in Claude Code's own `~/.claude.json`, GitHub #29158) is the most important data-layer finding in the peer set. I documented atomic writes as a fix, but Martin correctly argues that the pattern of "daemon writes JSON every 60 seconds" is itself the problem — not just the write implementation. Moving to SQLite for runtime state is the right fix.

His SQLite slot acquisition via `BEGIN IMMEDIATE` transaction is a better semaphore than flock for this reason: it is introspectable. `sqlite3 orchestrator.db "SELECT * FROM claude_slots"` tells you the exact state at any moment. flock tells you nothing without examining `/proc` for file descriptors.

However, I have a specific operational concern with his recommendation: adding SQLite as a dependency introduces a backup requirement that JSON files avoid. If the SQLite database corrupts (power loss during a write, which WAL mode mitigates but doesn't eliminate), the orchestrator cannot start. Martin does address this ("delete orchestrator.db and rebuild from projects.json") but this recovery procedure needs to be documented as a runbook, not just mentioned.

**Missed gaps:**

- Martin's backup strategy for SQLite is "sqlite3 orchestrator.db '.backup path'" but doesn't address the backup of an in-use WAL file. You cannot safely copy a WAL-mode SQLite database with cp while it's being written — you need either a checkpoint first or sqlite3's backup API. The backup cron job must use the backup API.
- His usage_ledger is valuable but he doesn't specify what triggers a cost alert. If the founder is charged $50 in a day due to a runaway Claude session, the `usage_ledger` table contains the evidence but there's no alert path. The ledger needs an associated alert: if `SUM(cost_usd_cents) WHERE occurred_at > NOW() - INTERVAL '1 hour'` exceeds a threshold, fire a Telegram alert.
- His inbox idempotency key (`.lock` marker file with `message_id`) is correct but doesn't address the case where the marker file is written but the inbox item is corrupted. The lock should contain a checksum of the inbox file, not just the existence flag.

---

### Analysis H (Domain Architect / Eric)

**Agreement:** Partially Agree

**Reasoning from ops perspective:**

Eric's domain analysis is intellectually sound but operationally abstract. His four-context model (Portfolio, Inbox, Pipeline, Notification) is correct as a conceptual framework. His most valuable concrete finding: "project" is overloaded across the system, doing too much work in different layers. This creates debugging confusion at 3 AM — when a log says "project X failed," which layer failed?

His ubiquitous language proposal is directly useful for logging. If every log line uses the domain terms (Portfolio, Pipeline, Phase, Slot) rather than the technical terms (process, flock, thread_id), the 3 AM debugging path becomes more readable. Log-level clarity comes from language consistency.

However, Eric's analysis is mostly silent on production failure scenarios. He proposes domain events (`IdeaCaptured`, `PhaseCompleted`) but doesn't address what happens when an event is emitted and the consumer is down. In his model, Pipeline context emits `PhaseCompleted` to Portfolio and Notification contexts. If Notification is down (Telegram API failure), does the event queue? Does it drop? Does it block Pipeline? These are ops questions that must be answered before the domain model is implementable.

**Missed gaps:**

- His ACL for Claude CLI ("Anti-Corruption Layer: ClaudeAdapter") is conceptually correct but he doesn't acknowledge that the Claude CLI RAM leak is a domain invariant violation: the Pipeline context acquires a slot but that slot's RAM consumption is unbounded and invisible to the Portfolio context. The Portfolio context's invariant (active count <= ConcurrencyBudget) is satisfied, but the actual resource consumption is not bounded. The domain model needs a RAM awareness layer.
- The Notification context has no fallback design. If Telegram is down, `PhaseCompleted` notifications are lost. An "alert delivered" invariant is not enforced. From ops perspective, this means the founder may not know that three autopilot tasks completed successfully overnight.
- His concurrency budget as a Portfolio concept is elegant but he doesn't address the dynamic case: VPS can be upgraded mid-operation. If the founder upgrades from 16GB to 32GB, the concurrency budget should be hot-reloadable. This maps to the `max_concurrent_claude` field in `projects.json` needing to be read on each scheduling decision, not cached at startup.

---

## Addressing the Founder's New Questions

### 1. Multi-LLM: Claude Code + ChatGPT Codex (GPT-5.4)

**Resource profiling for Codex CLI:**

From GitHub issues confirmed March 2026:

| Codex CLI Scenario | RAM observed | Source |
|-------------------|-------------|--------|
| Single Codex session at rest | ~400-800 MB | Baseline reports |
| Codex with sandbox enabled | +200-500MB overhead | Sandbox process tree |
| Memory leak (idle, uncapped) | 90GB+ virtual commit | GitHub #12414 |
| Non-interactive mode, memory not reclaimed | Progressive OOM | GitHub #13314 |

Codex has the same memory leak pattern as Claude. Both are open GitHub issues as of March 2026. This is not a theoretical risk — it is a documented production pattern on both CLIs.

**Combined RAM budget (Claude + Codex on same VPS):**

| Component | Baseline | Extended/Leak risk |
|-----------|----------|-------------------|
| OS + systemd | 0.5 GB | 0.5 GB |
| Monitoring stack (Loki + Grafana + Promtail) | 0.4 GB | 0.4 GB |
| Telegram bot | 0.1 GB | 0.1 GB |
| 1x Claude CLI (active autopilot) | 2-4 GB | 6-16 GB |
| 1x Codex CLI (active session) | 2-4 GB | 6-16 GB |
| Docker containers (project hosting) | 1-4 GB | variable |
| Safety headroom | 2 GB | needed |

**On a 16GB VPS:** Running one Claude + one Codex simultaneously is at capacity with zero headroom for leaks. Any leak from either CLI OOM-kills the VPS.

**On a 32GB VPS:** One Claude + one Codex + Docker containers is comfortable for typical sessions. Extended runs that leak can be caught by cgroup limits before hitting the OOM killer.

**On a 64GB VPS:** Two Claude + two Codex + Docker containers fits comfortably even with moderate leak behavior.

**Recommendation:** 32GB minimum for dual-CLI operation. 64GB if you plan 2+ concurrent projects per LLM type.

**Separate semaphore queues for each LLM:**

```bash
# Two semaphore directories — separate slot pools
CLAUDE_SEMAPHORE_DIR="/var/lock/orchestrator/claude"
CODEX_SEMAPHORE_DIR="/var/lock/orchestrator/codex"

# Separate concurrent limits
MAX_CONCURRENT_CLAUDE=2
MAX_CONCURRENT_CODEX=1  # More conservative — Codex leak pattern is worse

# Combined RAM floor check before acquiring ANY slot
check_combined_ram() {
    local free_gb=$(( $(grep MemAvailable /proc/meminfo | awk '{print $2}') / 1024 / 1024 ))
    if [[ $free_gb -lt 4 ]]; then
        log_error "Combined RAM floor: ${free_gb}GB free, refusing any new LLM process"
        return 1
    fi
}
```

**Monitoring for both LLMs:**

The Loki/Promtail structured log approach works identically for Codex — add `"llm_type": "codex"` to log JSON alongside `"llm_type": "claude"`. Grafana dashboard can then show RAM consumption per LLM type, task completion rates per LLM, and cost per LLM (Claude charges per token via Anthropic API; Codex charges per API call via OpenAI API — different billing models, different monitoring).

**Task routing by LLM type:**

The founder's observation that "GPT-5.4 codes well" suggests a capability-based routing model. Practical approach:

```json
// projects.json addition
{
  "id": "saas-app",
  "priority": "high",
  "llm_routing": {
    "autopilot": "claude",       // Complex architecture: Claude's strength
    "quick_fix": "codex",        // Fast implementation: Codex's strength
    "qa": "claude",              // Review and analysis: Claude
    "inbox_triage": "claude"     // Semantic understanding: Claude
  }
}
```

The orchestrator uses `llm_routing.autopilot` to decide which CLI to invoke. If the specified LLM's slot is occupied, fall back to the other LLM (with a flag in the log). This prevents a "Claude slots full" situation from blocking tasks that could run on Codex.

---

### 2. Infrastructure Topology: Same VPS vs Separate

**Resource contention analysis: Docker containers + Claude + Codex on one box:**

The core tension is that Docker containers (for project hosting) consume RAM in a baseline way, while Claude and Codex consume RAM in a bursty, leak-prone way. These are fundamentally different resource consumption profiles.

| Configuration | Pro | Con |
|---------------|-----|-----|
| Same VPS (orchestrator + Docker containers) | One server to manage, lower cost ($40-80/mo) | Docker container RAM competes directly with LLM processes. One Claude leak takes down project containers. |
| Separate VPS (dedicated orchestrator) | LLM processes isolated from project containers. Container OOM can't kill orchestrator. | Two servers to manage, slightly higher cost (+$15-30/mo for small orchestrator VPS) |

**My recommendation: Separate VPS for the orchestrator.**

The operational argument is clear: when Claude leaks to 14GB and OOM-kills the VPS, you want that event to affect ONLY the orchestrator — not the live Docker containers running the morning briefing product or any client-facing service. Mixing the resource chaos of LLM CLI processes with production container workloads creates cascading failures that are hard to isolate and debug at 3 AM.

The cost delta is $15-30/month for a small orchestrator VPS (Hetzner CX31, 8GB RAM, if using `MAX_CONCURRENT=1` for each LLM with conservative limits). This is cheap insurance.

**Topology:**

```
VPS-1 (Orchestrator, 32GB RAM, ~$35/mo Hetzner):
  - orchestrator.sh + pueued
  - telegram-bot.py
  - Claude CLI processes (max 2)
  - Codex CLI processes (max 1)
  - Monitoring: Loki + Grafana + Promtail
  - systemd cgroup: MemoryMax=28G (leaves 4GB for OS + monitoring)

VPS-2 (Projects, 16GB RAM, ~$16/mo Hetzner):
  - Docker containers per project
  - Production services (morning briefing product, etc.)
  - No LLM processes — pure container workload
```

Total cost: ~$51/mo vs $40-80/mo for a single beefy VPS. Within budget. Separation of concerns pays for itself the first time a Claude OOM kill would have taken down a production container.

**If single VPS is required (budget constraint):**

Docker memory limits become mandatory. Each project container must have `--memory=512m --memory-swap=512m`. The LLM cgroup limit (via systemd MemoryMax) must account for container baseline:

```
64GB VPS single-box budget:
- OS: 2 GB
- Docker containers (5 projects × 1GB): 5 GB
- Monitoring: 1 GB
- Claude × 2: up to 16 GB (with leak headroom)
- Codex × 1: up to 8 GB (with leak headroom)
- Safety buffer: 2 GB
Total needed: ~34 GB
→ 64GB VPS gives real headroom. 32GB is tight.
```

---

### 3. Practical Bootstrap: Day 1 Setup

**VPS provisioning checklist (Hetzner CX41/CX51):**

```bash
# Phase 1: Base hardening (30 min)
# 1. SSH key auth only, disable password
echo "PasswordAuthentication no" >> /etc/ssh/sshd_config
echo "PermitRootLogin no" >> /etc/ssh/sshd_config
systemctl restart sshd

# 2. UFW firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw enable

# 3. fail2ban
apt install fail2ban -y
# Default config bans after 5 failures in 10 minutes

# 4. Unattended upgrades for security patches
apt install unattended-upgrades -y
dpkg-reconfigure --priority=low unattended-upgrades

# Phase 2: Orchestrator dependencies (20 min)
# 5. Node.js (for Claude Code CLI)
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt install nodejs -y

# 6. Claude Code CLI — pinned version
npm install -g @anthropic-ai/claude-code@2.1.34  # Pin — don't use @latest
claude --version  # Verify

# 7. Codex CLI — pinned version
npm install -g @openai/codex@0.103.0  # Pin — avoid known leak versions
codex --version

# 8. Python + python-telegram-bot
apt install python3 python3-pip python3-venv -y
python3 -m venv /home/ubuntu/orchestrator-venv
source /home/ubuntu/orchestrator-venv/bin/activate
pip install python-telegram-bot==22.0 aiofiles

# 9. Pueue (task queue)
cargo install pueue
# OR: download binary from GitHub releases
# https://github.com/Nukesor/pueue/releases

# 10. Monitoring stack (optional but recommended)
# Grafana + Loki + Promtail via Docker Compose
# ~512MB RAM, negligible at 32GB VPS

# Phase 3: Orchestrator setup (30 min)
# 11. Clone orchestrator scripts
git clone https://github.com/user/orchestrator-scripts /home/ubuntu/scripts/vps

# 12. Create .env with secrets
cat > /home/ubuntu/scripts/vps/.env << 'EOF'
TELEGRAM_BOT_TOKEN=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
ALLOWED_TELEGRAM_USER_IDS=
ORCHESTRATOR_HB_UUID=
EOF
chmod 600 /home/ubuntu/scripts/vps/.env

# 13. Systemd service
cp /home/ubuntu/scripts/vps/systemd/orchestrator.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable orchestrator
systemctl start orchestrator

# 14. Pueue daemon
systemctl --user enable pueued
systemctl --user start pueued

# 15. Verify heartbeat
# Go to healthchecks.io, get UUID, set ORCHESTRATOR_HB_UUID
# Watch for first ping within 10 minutes
```

**Adding a new project (<5 min):**

```
1. /addproject "Project Name" /home/ubuntu/projects/project-name
   → Bot creates Telegram topic
   → Bot creates Pueue group "project-name"
   → Bot appends to projects.json (atomic write)
   → Bot responds in new topic: "Ready. Send ideas here."

2. Verify: /status in project topic
   → Should show "idle, no inbox items"

Done.
```

**systemd service file (production-grade):**

```ini
# /etc/systemd/system/orchestrator.service
[Unit]
Description=DLD Multi-Project Orchestrator
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=3

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/scripts/vps
EnvironmentFile=/home/ubuntu/scripts/vps/.env

ExecStartPre=/usr/bin/test -f /home/ubuntu/scripts/vps/projects.json
ExecStartPre=/usr/bin/python3 /home/ubuntu/scripts/vps/checks/validate-config.py
ExecStart=/home/ubuntu/scripts/vps/orchestrator.sh
ExecStop=/home/ubuntu/scripts/vps/drain-stop.sh

Restart=on-failure
RestartSec=30

# Memory ceiling: prevents Claude/Codex leak from OOM-killing VPS
# Set to 85% of VPS RAM
MemoryMax=27G   # for 32GB VPS
MemorySwapMax=0

# Kill ALL child processes (Claude, Codex, Python) on service stop
KillMode=control-group

StandardOutput=journal
StandardError=journal
SyslogIdentifier=orchestrator

[Install]
WantedBy=multi-user.target
```

**Key ops gotcha:** `ExecStartPre` validation gates prevent the orchestrator from starting with a broken config. Better to fail at startup than to start and silently misconfigure all projects.

---

### 4. VPS Sizing: 16GB vs 32GB vs 64GB

**The answer changes completely based on concurrent LLM count.**

**Claude only (no Codex), 2-3 active projects:**

| VPS | Verdict | Reasoning |
|-----|---------|-----------|
| 16GB | Minimum viable | MAX_CONCURRENT=2, RAM floor 4GB. One leak can survive without OOM kill. No Docker containers. |
| 32GB | Comfortable | MAX_CONCURRENT=2 with real headroom. Can add monitoring + small Docker containers. |
| 64GB | Overkill | Unless running 4+ concurrent projects or Agent Teams mode (not recommended). |

**Claude + Codex, 2-3 active projects:**

| VPS | Verdict | Reasoning |
|-----|---------|-----------|
| 16GB | Insufficient | Two LLMs at baseline already consume 4-8GB. Any leak = OOM. Not recommended. |
| 32GB | Minimum viable | MAX_CONCURRENT_CLAUDE=2, MAX_CONCURRENT_CODEX=1, RAM floor 6GB. Works but tight. |
| 64GB | Comfortable | Real headroom. Can absorb simultaneous leaks from both CLIs. |

**Claude + Codex + Docker containers (same VPS):**

| VPS | Verdict | Reasoning |
|-----|---------|-----------|
| 16GB | Do not use | No room for Docker + LLMs + monitoring |
| 32GB | Tight | Works if Docker containers are small (<512MB each, max 3 containers) |
| 64GB | Recommended | Comfortable separation of Docker + LLM workloads |

**Cost/risk decision matrix:**

```
Scenario A: Claude only, 2 projects, no Docker
→ 16GB ($16/mo) is sufficient with strict RAM floor

Scenario B: Claude + Codex, 2-3 projects, no Docker
→ 32GB ($35/mo) is the minimum responsible choice

Scenario C: Claude + Codex + Docker containers, 3-5 projects
→ Two VPS strategy: 16GB project VPS + 32GB orchestrator VPS ($51/mo total)
  OR single 64GB VPS ($78/mo) if operational simplicity is prioritized

Scenario D: Full scale, 5+ projects, both LLMs
→ 64GB minimum, or two VPS
```

**The $50-100/month budget can support:**
- Hetzner CX51 (32GB): €31/mo — dual-LLM orchestrator only
- Hetzner CCX33 (32GB, dedicated): €65/mo — if CPU matters for whisper.cpp
- Two Hetzner CX31 (8GB each): €16/mo — split if single-LLM per VPS

**Final answer on VPS sizing:** For the founder's scenario (Claude + Codex + Docker, 2-5 projects), 32GB is the minimum that doesn't require constant RAM anxiety. 64GB buys true peace of mind. The delta in cost ($35/mo vs $78/mo) is noise against the $200/month Claude subscription budget.

---

## Ranking

**Best Analysis:** E (LLM Architect / Erik)

**Reason:** Erik's research is the most operationally concrete and directly actionable. His cross-session contamination finding (GitHub #30348) is a production blocker that no other peer identified. His Agent Teams dismissal (13-16GB RAM, intra-project only, experimental bugs) eliminates a dangerous path before anyone gets committed to it. His per-phase `--max-turns` tuning table is a specification that the orchestrator can implement directly. The research behind this analysis is clearly from live GitHub issues, not theoretical — which is exactly how ops engineering should work.

**Worst Analysis:** H (Domain Architect / Eric)

**Reason:** Eric's domain model is intellectually rigorous but operationally disconnected. His four bounded contexts (Portfolio, Inbox, Pipeline, Notification) are correct, but his analysis doesn't engage with any of the actual failure modes that determine whether this system works at 3 AM. He identifies that "the Notification context is down" without addressing what the system does in that case (is Pipeline blocked? do events queue?). He notes that ConcurrencyBudget is a Portfolio invariant without addressing that RAM consumption makes this invariant impossible to enforce through coordination alone — it requires cgroup limits at the OS level. A domain model that cannot survive the domain it operates in is not operational architecture.

---

## Revised Position

**Revised Verdict:** Changed in one area.

**Change Reason:**

Martin's (Analysis G) finding about the `.orchestrator-state.json` race condition (335 corruptions in 7 days documented in Claude Code's own state file) changes my recommendation on the state file. I had previously proposed atomic writes to JSON as sufficient. Martin is right: the pattern of "daemon writes JSON every 60 seconds with concurrent readers" is itself the problem. Moving to SQLite for runtime state (not config) is the correct fix. The cgroup MemoryMax on the systemd unit still handles the RAM ceiling; SQLite handles the state consistency.

The flock semaphore position is unchanged: flock is correct for 1-2 concurrent sessions because process death releases the lock correctly (FD close). The RAM floor check must coexist with flock. But at 3+ projects or dual-LLM operation, SQLite's `BEGIN IMMEDIATE` transaction for slot acquisition is better because it is introspectable and crash-safe without the "did the lock file persist?" ambiguity.

**Final Ops Recommendation:**

This system is production-viable with the following non-negotiable ops requirements implemented before the first real project is added:

1. **healthchecks.io dead man's switch** — ping at end of each successful loop iteration. Free tier, 30-minute implementation. Without it, the orchestrator can die silently for days.

2. **systemd unit with `KillMode=control-group` and `MemoryMax=85% of VPS RAM`** — prevents Claude and Codex leaks from OOM-killing the VPS. Kills orphan LLM child processes on service stop.

3. **RAM floor check before any slot acquisition** — refuse to launch any LLM process if free RAM < 3GB (single LLM) or < 6GB (dual LLM). This is the operational guard against the most common 3 AM failure scenario.

4. **SQLite for runtime state** (replacing `.orchestrator-state.json`) — atomic slot acquisition via `BEGIN IMMEDIATE` transaction, crash-safe state on VPS reboot.

5. **Separate `CLAUDE_CODE_CONFIG_DIR` per project** — prevents cross-session contamination (GitHub #30348). `export CLAUDE_CODE_CONFIG_DIR=/var/orchestrator/projects/{project-id}/.claude-state` in every Claude invocation.

6. **LLM version pinning** — both Claude CLI and Codex CLI have regression histories. Pin versions in the install script, test upgrades on a single project before rolling to all.

7. **Separate VPS for orchestrator if any production containers run on the same machine** — LLM RAM leak should not cascade into production service downtime.

8. **Structured JSON logging with `llm_type` field** — when debugging at 3 AM, knowing whether the failure was Claude or Codex narrows the fix immediately.

For dual-LLM operation specifically: separate semaphore pools (Claude pool and Codex pool), separate cgroup limits per LLM type, and a combined RAM floor check that fires before acquiring any slot from either pool. The Hydra pattern (GitHub: PrimeLocus/Hydra) provides a reference implementation of Claude + Codex + Gemini routing via a shared task queue — worth reading before designing the routing layer.

---

## References

- My initial research: `ai/architect/orchestrator/research-ops.md`
- [GitHub openai/codex #9345 — Codex CLI serious memory leak](https://github.com/openai/codex/issues/9345)
- [GitHub openai/codex #12414 — Codex CLI 90GB+ idle memory growth](https://github.com/openai/codex/issues/12414)
- [GitHub openai/codex #13314 — Codex CLI memory not reclaimed after exit](https://github.com/openai/codex/issues/13314)
- [PrimeLocus/Hydra — Multi-LLM orchestration (Claude + Codex + Gemini)](https://github.com/PrimeLocus/Hydra)
- [anthropics/claude-code #30348 — Cross-session contamination](https://github.com/anthropics/claude-code/issues/30348) (cited by Analysis E)
- [anthropics/claude-code #29158 — state file corruption (335 events)](https://github.com/anthropics/claude-code/issues/29158) (cited by Analysis G)
- [Healthchecks.io — dead man's switch](https://healthchecks.io)
- [Hetzner Cloud Pricing](https://www.hetzner.com/cloud) — CX31/CX41/CX51 for VPS sizing
