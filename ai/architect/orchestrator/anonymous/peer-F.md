# Evolutionary Architecture Research — Multi-Project Orchestrator

**Persona:** Neal (Evolutionary Architect)
**Focus:** Fitness functions, change vectors, tech debt prevention
**Date:** 2026-03-10

---

## Research Conducted

- [Evolving Systems: Fitness Functions in Continuous Adaptation](https://architecturalbytes.substack.com/p/evolving-systems-the-role-of-fitness-functions-in-continuous-adaptation) — fitness function taxonomy and CI integration patterns
- [Building Evolutionary Architectures, 2nd Ed — Chapter 2](https://www.oreilly.com/library/view/building-evolutionary-architectures/9781492097532/ch02.html) — canonical fitness function definitions (Neal Ford, Rebecca Parsons)
- [inotifywait setup for file-based triggers](https://oneuptime.com/blog/post/2026-03-02-how-to-set-up-inotifywait-for-file-based-triggers-on-ubuntu/view) — inotify vs polling production comparison
- [inotify cannot be used, reverting to polling — limits](https://medium.com/@ivanermilov/how-to-fix-inotify-cannot-be-used-reverting-to-polling-too-many-open-files-bb1c1437dbf) — inotify instance limits and remediation
- [Polling vs inotify comparison on Linux](https://www.baeldung.com/linux/command-execute-file-dir-change) — authoritative comparison with tradeoffs
- [46 Microservices on a $20 VPS — Architecture](https://dev.to/robocular/i-run-46-microservices-on-a-single-20-vps-heres-the-architecture-259e) — PM2 vs Docker, per-process RAM, VPS ceiling
- [Multi-Agent AI Fleet on a Single VPS](https://dev.to/oguzhanatalay/architecting-a-multi-agent-ai-fleet-on-a-single-vps-3h4c) — systemd-per-agent, rate limit management, context isolation
- [When to Split VPS: Single vs Multi-Server](https://www.massivegrid.com/blog/vps-single-vs-multi-server-architecture/) — scaling inflection signals
- [Zero-Downtime CI/CD to VPS: rsync + symlink + systemd](https://www.dchost.com/blog/en/zero%E2%80%91downtime-ci-cd-to-a-vps-the-friendly-rsync-symlink-systemd-playbook-i-keep-reusing/) — symlinked releases pattern
- [Strangler Fig Pattern for Legacy Modernization](https://blogs.pavanrangani.com/strangler-fig-pattern-legacy-modernization/) — incremental migration strategy
- [Claude Code Agent Teams Guide 2026](https://claudefa.st/blog/guide/agents/agent-teams) — CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS native support
- [Config Hot-Reload Patterns](https://oneuptime.com/blog/post/2026-01-25-configuration-hot-reload/view) — inotify + SIGHUP + etcd/Consul patterns
- [TARS: Multi-project Claude Code manager](https://github.com/inceptyon-labs/TARS) — existing art for multi-project CC management

**Total queries:** 7 web searches + 1 code context search

---

## Kill Question Answer

**"What fitness functions protect this architectural decision?"**

| Architectural Decision | Fitness Function | How It's Automated |
|------------------------|------------------|-------------------|
| Max latency for inbox pickup | Inbox file age never exceeds 5 min in active hours | Cron every 5 min: `find ai/inbox -mmin +5 -type f \| wc -l > 0 = ALERT` |
| Semaphore correctness (max N concurrent Claude) | Slot count never exceeds `max_concurrent_claude` | Nightly: count `flock`-held slots vs config; alert if mismatch |
| projects.json schema validity | Config always parses without error | Git hook (pre-commit): `python3 -c "import json; json.load(open('projects.json'))"` |
| Dependency direction (shared←infra←domains←api) | No reverse imports detected | CI: `dependency-cruiser` check on every commit |
| File size limit (400 LOC) | No source file exceeds limit | CI: `find src/ -name "*.py" -exec wc -l {} \; \| awk '$1>400'` |
| State file consistency | `.orchestrator-state.json` never stale >10 min | Cron: compare `updated` field to `now`; alert if delta >10 min |
| Project isolation | No cross-project file writes | Filesystem: each project Claude runs under dedicated user or `--chroot` path check |
| Orchestrator liveness | Orchestrator PID alive and loop cycling | Dead man's switch: orchestrator writes heartbeat every 60s; external watchdog alerts if gap >120s |
| Config hot-reload correctness | Adding a project requires 0 restarts | Integration test: add project, wait 30s, verify routing without restart |

**Missing fitness functions (unprotected decisions in current spec):**
- No automated check that `topic_id` in Telegram is still valid (topic can be deleted)
- No check that `path` in projects.json actually exists on disk
- No test for semaphore starvation under load (high-priority project monopolizing slots)
- No latency SLO for `/status` Telegram response time

---

## Proposed Evolutionary Decisions

### Change Vector Analysis

**High-Change Areas** (update frequently, isolate):

| Component | Change Frequency | Change Driver | Isolation Strategy |
|-----------|-----------------|---------------|-------------------|
| `projects.json` schema | Monthly | Adding projects, changing priorities | JSON Schema validation at load time; schema version field for migrations |
| Telegram Bot API | Uncontrolled (Telegram changes) | External dependency | Adapter pattern: `TelegramNotifier` interface, swap implementation |
| Claude CLI invocation args | Quarterly (Anthropic releases) | `--max-turns`, `--model`, new flags | Separate `claude-runner.sh` that wraps CLI; one change location |
| DLD skill scripts (spark, autopilot, qa) | Per-feature | DLD framework evolution | Pass `PROJECT_DIR` + run from project dir — skills are version-controlled per project |
| Priority/scheduling algorithm | Monthly | Founder preferences | Isolated in `scheduler.sh`; easy to swap round-robin logic |
| VPS resource limits | Quarterly | Hetzner upgrade / scale | Config-driven `max_concurrent_claude`; no hardcoded values |

**Stable Core** (rarely changes, protect):

| Component | Why Stable | Protection Needed |
|-----------|------------|-------------------|
| `message_thread_id → project` routing | Telegram API contract stable for topics | Fitness function: validate topic IDs on startup |
| `flock`-based semaphore primitive | POSIX, decades stable | Unit test: verify slot count correctness |
| `ai/inbox/` directory protocol | Agreed convention across all DLD projects | Architecture test: verify protocol in project structure check |
| Heartbeat/dead man's switch pattern | Fundamental reliability contract | Never refactor without explicit fitness function validation |
| `.orchestrator-state.json` write protocol | Atomic write pattern (write-rename) | Test: concurrent writes should never corrupt state |

**Change Isolation Techniques:**
- Wrap Telegram API in `TelegramAdapter` class — swap if Telegram blocks bots or GitHub Issues wins
- `claude-runner.sh` as the only Claude CLI invocation point — flag changes isolated here
- Schema version in `projects.json` — allows backward-compatible evolution
- Per-project `poll_interval` already isolated — can tune without touching orchestrator logic

---

### Fitness Function Suite

**Architectural Properties to Preserve:**

#### 1. Inbox Pickup Latency SLO

**Rule:** No inbox file older than 5 minutes during active hours (08:00-22:00)

**Fitness Function:**
```bash
#!/bin/bash
# /scripts/vps/checks/inbox-latency-check.sh
# Run via cron: */5 8-22 * * * /scripts/vps/checks/inbox-latency-check.sh

STALE_COUNT=0
for project_dir in $(jq -r '.projects[].path' /scripts/vps/projects.json); do
    inbox="$project_dir/ai/inbox"
    if [ -d "$inbox" ]; then
        count=$(find "$inbox" -type f -mmin +5 | wc -l)
        STALE_COUNT=$((STALE_COUNT + count))
    fi
done

if [ "$STALE_COUNT" -gt 0 ]; then
    echo "FAIL: $STALE_COUNT stale inbox files (>5min unprocessed)"
    exit 1
fi
echo "OK: All inbox files processed within SLO"
```

**Tool:** cron + Telegram alert via `notify.sh`

#### 2. Semaphore Slot Correctness

**Rule:** Active Claude processes never exceed `max_concurrent_claude` from config

**Fitness Function:**
```bash
#!/bin/bash
# /scripts/vps/checks/semaphore-check.sh
# Run every 2 minutes via cron

MAX=$(jq -r '.max_concurrent_claude' /scripts/vps/projects.json)
ACTIVE=$(pgrep -c 'claude' 2>/dev/null || echo 0)

if [ "$ACTIVE" -gt "$MAX" ]; then
    echo "FAIL: $ACTIVE Claude processes running, max is $MAX"
    notify.sh "ORCHESTRATOR ALERT: semaphore violated ($ACTIVE > $MAX)"
    exit 1
fi
echo "OK: $ACTIVE/$MAX slots used"
```

**Why:** `flock` is correct in theory but `flock` leaks on crash are known. This catches it.

#### 3. projects.json Schema Validity

**Rule:** Config always valid JSON, always contains required fields

**Fitness Function:**
```bash
#!/bin/bash
# Git pre-commit hook + CI step
python3 - << 'EOF'
import json, sys

with open("scripts/vps/projects.json") as f:
    cfg = json.load(f)

required_top = ["chat_id", "max_concurrent_claude", "projects"]
required_project = ["name", "topic_id", "path", "priority", "enabled"]

for field in required_top:
    assert field in cfg, f"Missing top-level field: {field}"

for p in cfg["projects"]:
    for field in required_project:
        assert field in p, f"Project '{p.get('name','?')}' missing field: {field}"
    import os
    assert os.path.isdir(p["path"]), f"Project path does not exist: {p['path']}"

print("OK: projects.json valid")
EOF
```

**Tool:** Git hook (pre-commit) prevents broken config from being committed

#### 4. Orchestrator Liveness Heartbeat

**Rule:** Orchestrator writes heartbeat every 60s; gap >120s = dead

**Fitness Function:**
```bash
#!/bin/bash
# /scripts/vps/checks/liveness-check.sh
# Run via cron: * * * * * (every minute)

STATE_FILE="/scripts/vps/.orchestrator-state.json"
MAX_STALENESS=120  # seconds

if [ ! -f "$STATE_FILE" ]; then
    notify.sh "ORCHESTRATOR DEAD: state file missing"
    exit 1
fi

UPDATED=$(jq -r '.updated' "$STATE_FILE")
UPDATED_EPOCH=$(date -d "$UPDATED" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%SZ" "$UPDATED" +%s)
NOW_EPOCH=$(date +%s)
DELTA=$((NOW_EPOCH - UPDATED_EPOCH))

if [ "$DELTA" -gt "$MAX_STALENESS" ]; then
    notify.sh "ORCHESTRATOR DEAD: last heartbeat ${DELTA}s ago"
    exit 1
fi
echo "OK: heartbeat ${DELTA}s ago"
```

**Why:** The orchestrator has no external watchdog. This IS the watchdog.

#### 5. Dependency Direction Check

**Rule:** `shared ← infra ← domains ← api` (never reverse)

**Fitness Function:**
```bash
# CI step (if/when Python rewrite happens)
pip install dependency-cruiser
depcruise src/ --config .dependency-cruiser.json --output-type err
```

**For bash scripts:** Manual convention — `orchestrator.sh` calls helpers, helpers never call up

#### 6. Zero-Restart Config Reload

**Rule:** Adding/modifying a project requires no orchestrator restart

**Fitness Function (integration test):**
```bash
#!/bin/bash
# /scripts/vps/tests/hot-reload-test.sh

# Add a test project to config
python3 -c "
import json
cfg = json.load(open('scripts/vps/projects.json'))
cfg['projects'].append({'name':'TEST','topic_id':9999,'path':'/tmp/test-proj',
  'priority':'low','poll_interval':300,'enabled':True})
json.dump(cfg, open('scripts/vps/projects.json','w'))
"

sleep 35  # wait for next orchestrator cycle to pick up

# Verify test project appears in status
RESULT=$(curl -s http://localhost:8080/status 2>/dev/null | jq '.projects | has("TEST")')
# (or grep state file)
RESULT=$(jq '.projects | has("TEST")' /scripts/vps/.orchestrator-state.json)

if [ "$RESULT" = "true" ]; then
    echo "OK: hot-reload works"
else
    echo "FAIL: new project not picked up without restart"
    exit 1
fi
```

---

### Architectural Characteristics Prioritization

**Critical Characteristics** (system fails without these):

| Characteristic | Why Critical | How Measured | Fitness Function |
|----------------|--------------|--------------|------------------|
| Reliability | Solo founder, no on-call. Orchestrator must self-heal | Uptime %, heartbeat gap | Liveness check (cron) |
| Isolation | Bug in project A must not kill project B's Claude session | Process count per project | `pgrep` per project path |
| Observability | "What failed at 3am?" must be answerable from Telegram | Log completeness, alert delivery | Alert round-trip test |
| Recoverability | VPS reboot mid-autopilot — what is lost? | State file completeness at restart | `systemd` restart policy test |

**Important** (degraded without, not failed):

| Characteristic | Trade-off Accepted | Mitigation |
|----------------|-------------------|------------|
| Latency | 5-min pickup SLO, not real-time | Inbox polling every 30s is sufficient for async work |
| Scalability | Design for 2-10 projects, not 100 | Explicit `max_projects = 10` ceiling with clear upgrade path |
| Throughput | Sequential project iteration acceptable | Priority + round-robin scheduling handles this |

**Nice-to-Have** (defer):

- Real-time streaming of Claude output to Telegram: defer — polling every 30s is enough
- Per-project cost tracking dashboard: defer — `--max-turns` + timeout is sufficient guard
- Multi-VPS orchestration: defer — explicit ceiling at single VPS until revenue justifies

**Trade-offs Made:**
- Chose **simplicity (bash)** over **correctness (proper job queue)** because 2-3 projects, solo founder, revenue focus
- Chose **polling loop** over **event-driven** for the main cycle because bash + `flock` is 100% debuggable over SSH at 3am
- Chose **inotifywait** for inbox specifically because inbox files arrive sparsely — pure push is efficient here
- Chose **JSON file** over **SQLite** for state because single writer (orchestrator process), no concurrent reads that matter

---

### Config Hot-Reload: inotifywait vs Polling vs SIGHUP

**Research finding:** Three viable patterns, each with different tradeoffs for this use case.

#### Option A: inotifywait (event-driven, Linux-native)

```bash
# Background watcher for projects.json
inotifywait -m -e close_write,modify /scripts/vps/projects.json |
while read -r dir event file; do
    reload_config
done
```

**Pros:**
- Zero CPU overhead between changes
- Immediate reaction (<100ms)
- No polling loop complexity

**Cons:**
- Linux-only (not macOS — matters if you develop locally)
- `max_user_watches` limit (default 8192, but we only watch 1 file — irrelevant here)
- Another process to supervise; dies silently if not managed

**Verdict for this use case:** USE inotifywait for `projects.json` hot-reload. Single file watch, Linux VPS target, immediate feedback needed when adding projects.

#### Option B: Polling (every-cycle re-read)

```bash
# In orchestrator main loop
CONFIG_MTIME_PREV=0
while true; do
    CONFIG_MTIME=$(stat -c %Y /scripts/vps/projects.json)
    if [ "$CONFIG_MTIME" != "$CONFIG_MTIME_PREV" ]; then
        reload_config
        CONFIG_MTIME_PREV=$CONFIG_MTIME
    fi
    # ... rest of loop
done
```

**Pros:**
- No extra process, no dependencies
- Works everywhere (Linux, macOS, WSL)
- Simpler failure mode — if loop hangs, config doesn't reload, but nothing crashes

**Cons:**
- Up to 1 full cycle delay (30-60s) before config change takes effect
- Slightly wasteful `stat` call each cycle

**Verdict:** USE polling as the fallback if inotifywait process dies. Both inotifywait AND polling-every-cycle protects against the "inotifywait died silently" failure mode.

#### Option C: SIGHUP signal-driven reload

```bash
# Orchestrator catches SIGHUP
trap 'reload_config' SIGHUP

# Caller: signal the orchestrator to reload
kill -HUP $(cat /scripts/vps/.orchestrator-state.json | jq -r '.pid')
```

**Pros:**
- Explicit, deterministic, zero delay
- Standard Unix pattern (nginx, sshd all use this)

**Cons:**
- Requires knowing the orchestrator PID
- Manual trigger — not automatic on file change

**Verdict:** IMPLEMENT SIGHUP as a manual escape hatch for `/reload` Telegram command. Combined approach:

```
inotifywait (auto) → reloads within 100ms of file change
polling mtime (fallback) → reloads within 1 cycle if inotifywait dies
SIGHUP (manual) → /reload command from Telegram for immediate force-reload
```

---

### Migration Path: Single-Project VPS → Multi-Project Orchestrator

**Strangler Fig applied to the orchestrator itself.**

The current state: one project, manual `claude` calls, ad-hoc `notify.sh`. The target: orchestrator managing N projects. The risk: breaking the working single-project setup.

#### Phase 0 — Strangler Setup (Day 1-2, zero risk)

Add `projects.json` with exactly one project — the current project. Run the new orchestrator in parallel with the existing manual flow. Both can coexist — orchestrator simply wraps what already works.

```json
{
  "chat_id": -1001234567890,
  "max_concurrent_claude": 1,
  "projects": [
    {
      "name": "Current Project",
      "topic_id": null,
      "path": "/home/user/current-project",
      "priority": "high",
      "poll_interval": 300,
      "enabled": true
    }
  ]
}
```

**Fitness gate:** Orchestrator runs without errors for 48h alongside manual flow.

#### Phase 1 — Migrate Control Plane (Day 3-5)

Migrate Telegram routing to topic-based. Create one supergroup topic per project. Update `telegram-bot.py` to route by `message_thread_id`. Old `notify.sh` calls continue working (General topic fallback).

**Fitness gate:** All Telegram commands work via topic. Zero regression in notification delivery.

#### Phase 2 — Migrate Automation (Day 6-10)

Cut over `autopilot-loop.sh`, `inbox-processor.sh`, `qa-loop.sh` to accept `PROJECT_DIR`. Remove manual cron jobs that did per-project runs. Orchestrator becomes the sole scheduler.

**Fitness gate:** Run both old and new for 24h, compare task completion rates. Retire old crons only after parity confirmed.

#### Phase 3 — Add Second Project (Day 10+)

Add second project to `projects.json`. Verify semaphore holds under concurrent load. Check that Project A activity does not delay Project B beyond priority SLO.

**Fitness gate:** Both projects complete at least one autopilot cycle within their expected interval.

**Reversibility at each phase:** Every phase is independently reversible. Phase 0 can be rolled back by deleting `projects.json`. Phase 1 by reverting `telegram-bot.py`. Phase 2 by re-enabling old crons. Phase 3 by disabling the second project entry.

---

### Scaling Inflection Points: 2 → 10 Projects

*Thinks about the 5-year trajectory.*

**Inflection Point 1: 3-4 projects (RAM ceiling)**

At 2 projects: `max_concurrent_claude=2`, ~500MB-1GB RAM consumed when both active.
At 4 projects: With 8GB VPS and 500MB per Claude process, theoretical max is 16 concurrent — but in practice autopilot runs are long (10-30 min), so slots are occupied, not idle. The semaphore becomes a real bottleneck.

**Signal to watch:** Projects waiting >30 min for a semaphore slot. Fitness function: log average wait time per project.

**Fix at this inflection:** Upgrade VPS tier OR implement priority-weighted semaphore (high-priority projects can preempt medium after 20 min wait).

**Inflection Point 2: 5-6 projects (loop cycle time)**

The orchestrator iterates N projects per cycle. With 5 projects and 30s per check: one full cycle takes 2.5 min. With 10 projects: 5 min. The inbox latency SLO (5 min) becomes impossible to guarantee.

**Signal to watch:** Cycle completion time > 3 minutes. Fitness function: log `cycle_duration` to state file, alert if >180s.

**Fix at this inflection:** Switch from sequential loop to parallel project checks with `&` + `wait`. Still single semaphore for Claude slots but project polling runs concurrently.

```bash
# Sequential (current, works to ~4 projects):
for project in "${projects[@]}"; do check_project "$project"; done

# Parallel (needed at 5+ projects):
for project in "${projects[@]}"; do check_project "$project" & done
wait
```

**Inflection Point 3: 8-10 projects (orchestrator complexity)**

At 8+ projects, `orchestrator.sh` becomes a liability. Bash lacks structured logging, retry logic, and graceful error handling per project. One project's check_inbox crashing takes down the whole loop.

**Signal to watch:** `orchestrator.sh` LOC > 400. Fitness function: file size check on CI.

**Fix at this inflection:** Rewrite in Python or Node.js. NOT before. The bash version is perfectly adequate for 2-7 projects and the rewrite risk is real.

**Critical insight:** The inflection points are at 4, 6, and 8 projects — not at 2 and 10. Plan for them explicitly.

---

### Versioning the Orchestrator Itself — Upgrading Without Downtime

**The core constraint:** Orchestrator runs as a long-lived bash loop. Active Claude processes must not be interrupted during upgrade.

#### Strategy: Symlinked Release Pattern

```
/scripts/vps/
├── releases/
│   ├── v1.2/           ← previous
│   └── v1.3/           ← new, fully staged
├── current -> releases/v1.3/   ← atomic symlink swap
└── orchestrator.sh -> current/orchestrator.sh
```

**Upgrade procedure (zero-downtime):**
```bash
#!/bin/bash
# upgrade-orchestrator.sh

NEW_VERSION=$1
RELEASES_DIR="/scripts/vps/releases"
CURRENT_LINK="/scripts/vps/current"

# 1. Stage new version (does not affect running orchestrator)
cp -r "$RELEASES_DIR/latest" "$RELEASES_DIR/$NEW_VERSION"

# 2. Validate new version config compatibility
"$RELEASES_DIR/$NEW_VERSION/checks/schema-check.sh" || exit 1

# 3. Wait for no active Claude processes (grace window)
while pgrep -f 'claude' > /dev/null; do
    echo "Waiting for active Claude sessions to complete..."
    sleep 30
done

# 4. Atomic symlink swap (single syscall, cannot be interrupted)
ln -sfn "$RELEASES_DIR/$NEW_VERSION" "$CURRENT_LINK"

# 5. Orchestrator's next cycle picks up new scripts automatically
echo "Upgrade to $NEW_VERSION complete. Next cycle will use new version."
```

**Key property:** The orchestrator's main loop reads scripts from `current/` symlink. After the atomic `ln -sfn`, the next cycle automatically uses new code. No restart needed.

**Rollback:**
```bash
ln -sfn "$RELEASES_DIR/v1.2" /scripts/vps/current
# Done. Next cycle reverts.
```

**Fitness function for upgrade correctness:**
```bash
# Post-upgrade smoke test (run 2 minutes after upgrade)
/scripts/vps/checks/liveness-check.sh
/scripts/vps/checks/semaphore-check.sh
/scripts/vps/checks/inbox-latency-check.sh
```

---

### The Claude Code Native Multi-Project Question

**Research finding:** Claude Code Agent Teams (experimental, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) exists as of early 2026 but is:
- Per-session, not persistent
- Not designed for cross-project orchestration
- No native multi-project workspace concept

TARS (open source, Rust desktop app) provides a visual multi-project Claude Code manager but is a UI tool, not a VPS orchestrator.

**The reversibility question:** If Anthropic ships native multi-project support in 12-18 months, how much of this orchestrator is throwaway?

**Stable components** (survive Claude Code native evolution):
- `projects.json` project registry concept — any orchestration layer needs this
- Telegram routing layer — Anthropic won't build this
- Inbox protocol (`ai/inbox/` directory) — DLD-specific, not CC-native
- Fitness functions / monitoring — always needed

**Disposable components** (if Claude Code adds native multi-project):
- `orchestrator.sh` loop — replaced by CC native scheduler
- `flock` semaphore — replaced by CC native concurrency control
- `autopilot-loop.sh` invocation — CC native handles this

**Architectural escape hatch:** Wrap Claude invocation in `claude-runner.sh`. When CC adds native multi-project, `claude-runner.sh` is the only change point. The rest of the orchestrator (routing, state, notifications) survives.

```bash
# claude-runner.sh — the ONLY place that invokes Claude CLI
# When CC native multi-project arrives, modify only this file.
run_claude() {
    local project_dir=$1
    local task=$2
    cd "$project_dir"
    # TODAY: direct claude CLI invocation
    claude --dangerously-skip-permissions --max-turns 25 \
        -p "$(cat ai/features/$task)"
    # FUTURE: claude workspace run --project "$project_dir" "$task"
}
```

---

### Tech Debt Prevention Strategy

**Debt Visibility:**
```bash
# In any script file:
# DEBT: Using polling fallback instead of proper job queue
# COST: 2 hours to migrate to Pueue when needed
# TRIGGER: When cycle_duration consistently > 2 min (>5 projects)
```

**Refactoring Triggers:**

| Trigger | Action |
|---------|--------|
| `orchestrator.sh` > 400 LOC | Split into modules before next feature |
| Average semaphore wait > 20 min | Implement priority-weighted semaphore |
| Cycle duration > 180s | Parallelize project checks |
| 3+ projects using same claude invocation pattern | Extract to `claude-runner.sh` |
| Bash error handling causes lost projects | Migrate to Python |

**Debt the current spec is already incurring:**
1. `flock` semaphore is not starvation-proof — low-priority project can wait indefinitely. COST: 1 hour to add timeout + alert. TRIGGER: When third project added.
2. State file is append/overwrite, not atomic — rare corruption risk. COST: 30 min to add write-rename pattern. TRIGGER: Now (do this on day 1).
3. No per-project error isolation — one project's crash affects loop timing. COST: 4 hours to add `set +e` per-project sandboxing. TRIGGER: Second project.

---

### Reversibility Analysis

**Irreversible Decisions** (require careful thought now):

| Decision | Why Irreversible | Cost to Reverse | Mitigation |
|----------|-----------------|----------------|------------|
| Telegram as primary UI | Topic IDs are baked into `projects.json`, users habituated | 1 week to migrate to GitHub Issues UI | Build `TelegramAdapter` interface from day 1 |
| Bash orchestrator | Behavioral correctness baked in over months; Python rewrite = re-testing all edge cases | 1-2 weeks | Hard LOC limit at 400; above that, Python |
| `ai/inbox/` directory protocol | All DLD projects rely on this; changing breaks every project | Major coordination effort | Treat as stable API, version it |
| VPS (Hetzner/DO) choice | Moving servers = DNS changes, IP changes, re-auth | 2-3 hours | Use domain name (not raw IP) for any external references |

**Reversible Decisions** (low risk, decide quickly):

| Decision | Easy to Reverse Because | Decide Now? |
|----------|------------------------|----------------|
| `projects.json` schema fields | Additive changes are backward compatible | Yes — add `schema_version: 1` on day 1 |
| `poll_interval` values | Per-project config, change anytime | Yes — sane defaults, tune live |
| `max_concurrent_claude` | Single config value | Yes — start at 2 |
| Priority algorithm (round-robin vs weighted) | Isolated in scheduler logic | Yes — start simple round-robin |
| inotifywait vs polling-only for hot reload | Config reload is isolated | Implement both (belt and suspenders) |

**Deferrable Decisions:**
- GitHub Issues as agent interface: Wait until consulting pipeline shows whether clients prefer GitHub or Telegram
- Pueue vs custom queue: Wait until cycle duration exceeds 3 minutes (inflection point 2)
- Python rewrite: Wait until `orchestrator.sh` hits 400 LOC
- Multi-VPS: Wait until revenue from consulting funds the second VPS

---

## Cross-Cutting Implications

### For Domain Architecture
- The orchestrator is infrastructure, not a domain. It enforces the DLD lifecycle (inbox → spark → autopilot → QA) without owning any of those domains
- Change vector: if DLD lifecycle adds a new phase (e.g., `/eval`), the orchestrator loop needs a new check — isolate this as a function per phase, not per project

### For Data Architecture
- State file write must be atomic (write to `.tmp` then `mv`) — single writer makes this safe without transactions
- GitHub Issues as data layer is an additive decision — can coexist with `projects.json` by syncing state bidirectionally

### For Operations
- Dead man's switch (heartbeat fitness function) is the primary reliability mechanism for a single-VPS system with no redundancy
- Systemd unit for the orchestrator is non-negotiable — VPS reboots happen; `Restart=always` is the minimum

### For Security
- Each Claude invocation runs in the project directory context. A malicious project spec could attempt `../` traversal. Fitness function: validate `PROJECT_DIR` is an allowed path before any Claude invocation.

---

## Concerns and Recommendations

### Critical Issues

- **Atomic state writes not in spec.** The current spec overwrites `.orchestrator-state.json` directly. Race condition if VPS loses power mid-write. Fix: write to `.orchestrator-state.json.tmp` then `mv`.
  - Rationale: Data outlives code. A corrupted state file means the orchestrator cannot determine what was running when it restarts.

- **Semaphore starvation is unaddressed.** With `flock` and priority-based scheduling, a sustained high-priority project could indefinitely block low-priority projects. For 2 projects this is acceptable. For 3+, it is not.
  - Fix: Add maximum wait time per project (30 min). After timeout, emit alert and skip cycle.

- **No fitness function for project path validity.** If `projects.json` references a path that does not exist, the orchestrator silently skips it. This is an invisible failure.
  - Fix: Validate paths on startup AND on hot-reload. Alert via Telegram if path missing.

### Important Considerations

- **The 400-LOC tripwire for bash.** `orchestrator.sh` will grow. The fitness function that caps it at 400 LOC is what prevents a 1200-line bash script disaster. Enforce this from day 1, not after the fact.

- **inotifywait + polling-fallback is the correct hot-reload strategy.** Not inotifywait alone (process dies silently) and not polling alone (30-60s delay). Both together costs nothing and eliminates the failure mode.

- **Escape hatch for Claude Code native multi-project.** Anthropic's roadmap is opaque. Wrapping Claude invocation in `claude-runner.sh` is a 30-minute investment that preserves architectural options for 18 months. This is a reversibility move, not a premature abstraction.

### Questions for Clarification

- What is the acceptable inbox pickup latency SLO? (Current assumption: 5 minutes during active hours)
- When the orchestrator crashes mid-autopilot, should the task be marked `blocked` automatically, or left in `in_progress`? This drives the recovery state machine design.
- Is there a plan for when VPS RAM is exhausted? (Current spec says 6-10 projects on 8GB, but autopilot can spike to 1GB per Claude process under load)
- Should the orchestrator manage project creation (git init, DLD bootstrap) or only manage existing projects?

---

## References

- [Neal Ford — Building Evolutionary Architectures](https://evolutionaryarchitecture.com/)
- [Martin Fowler — Fitness Functions](https://martinfowler.com/bliki/FitnessFunction.html)
- [Martin Fowler — Strangler Fig Application](https://martinfowler.com/bliki/StranglerFigApplication.html)
- [inotifywait Linux man page](https://linux.die.net/man/1/inotifywait)
- [Polling vs inotify — Baeldung](https://www.baeldung.com/linux/command-execute-file-dir-change)
- [Zero-downtime VPS deploy: rsync + symlink + systemd](https://www.dchost.com/blog/en/zero%E2%80%91downtime-ci-cd-to-a-vps-the-friendly-rsync-symlink-systemd-playbook-i-keep-reusing/)
- [Multi-Agent AI Fleet on Single VPS](https://dev.to/oguzhanatalay/architecting-a-multi-agent-ai-fleet-on-a-single-vps-3h4c)
- [46 Microservices on a $20 VPS](https://dev.to/robocular/i-run-46-microservices-on-a-single-20-vps-heres-the-architecture-259e)
- [TARS: Multi-project Claude Code Manager](https://github.com/inceptyon-labs/TARS)
- [Claude Code Agent Teams Guide 2026](https://claudefa.st/blog/guide/agents/agent-teams)
