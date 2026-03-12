# Developer Experience Architecture Research

**Persona:** Dan (DX Architect)
**Focus:** Innovation tokens, boring tech, developer workflow
**Date:** 2026-03-10

---

## Research Conducted

- [Pueue v4.0 — Task Management CLI](https://github.com/Nukesor/pueue/wiki/FAQ) — feature-complete task queue for shell commands, groups, parallelism
- [Choose Boring Technology Revisited (2025)](https://www.brethorsting.com/blog/2025/07/choose-boring-technology,-revisited/) — LLM era makes boring tech even more critical
- [GitHub Copilot Coding Agent Docs](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent) — Issues as agent interface: assign issue, get PR
- [block/agent-task-queue](https://github.com/block/agent-task-queue) — Python-based local task queue for AI agents, prevents concurrent resource thrashing
- [CCBot: Telegram + tmux for Claude Code](https://www.reddit.com/r/AgentsOfAI/comments/1qzahrg/) — production proof that Telegram topics map 1:1 to tmux windows
- [codex-cli-farm: tmux session manager](https://github.com/waskosky/codex-cli-farm) — shell-based multi-agent tmux orchestration, actually ships
- [workmux: git worktrees + tmux](https://github.com/raine/workmux) — 619 stars, zero-friction parallel dev, real-world validation
- [kingbootoshi/codex-orchestrator](https://github.com/kingbootoshi/codex-orchestrator) — TypeScript tmux orchestrator for Claude/Codex, 225 stars
- [GitHub Agentic Workflows (Feb 2026)](https://github.blog/ai-and-ml/automate-repository-tasks-with-github-agentic-workflows/) — Issues as task queue, Markdown workflows, GitHub Actions runner
- [systemd timers vs cron 2026](https://crongen.com/blog/cron-vs-systemd-timers-2026) — systemd timers: better logging, dependency management, no polling
- [Cron vs systemd comparison](https://oneuptime.com/blog/post/2026-03-04-systemd-timers-alternative-cron-rhel-9/view) — systemd preferred for long-running service management

**Total queries:** 8 web searches

---

## Kill Question Answer

**"Is this solving a business problem or engineering curiosity?"**

| Proposed Technology | Business Problem Solved | Engineering Curiosity | Verdict |
|---------------------|------------------------|----------------------|---------|
| Custom Telegram bot (Python) | Mobile control of VPS without SSH on phone | Partially — "cool interface" appeal | Conditional keep — with scope limit |
| Shell script orchestrator.sh | Route tasks between projects, manage concurrency | No — pure ops tooling | Keep but scope it |
| Semaphore via flock | Limit concurrent Claude processes (RAM constraint) | No — real hardware constraint | Keep |
| projects.json config | Register N projects declaratively | No — standard config pattern | Keep |
| Hot-reload via inotifywait | React to config changes without restart | Mild curiosity | Defer — polling every 60s is fine |
| GitHub Issues as primary interface | Structured, version-controlled task queue | Yes — elegant but over-engineered for solo founder | Defer for now |
| Pueue daemon | Replace custom semaphore logic | No — it's boring, existing tool | Strong candidate to adopt |
| Docker containerization | Isolation between projects | Yes — resume-driven | Reject |
| Custom priority queue algorithm | Schedule high vs low priority projects | Yes — the priority math is engineering curiosity | Replace with Pueue groups |

**Innovation tokens spent on business:** 0 (this whole system is tooling, not product)
**Innovation tokens spent on infrastructure:** Already at 2+ before writing a line

---

## The Core Problem with This Architecture

*counts innovation tokens*

Let me inventory what we're building:

1. Custom Python Telegram bot with topic routing — that's new code to maintain
2. Custom bash orchestrator.sh with priority logic — more custom code
3. Custom semaphore via flock in /tmp — home-rolled concurrency primitive
4. Custom state machine in .orchestrator-state.json — manual state tracking
5. Custom config hot-reload via inotifywait — more plumbing

We're building FIVE custom pieces of infrastructure before doing anything for the actual business (consulting, morning briefing). This is all undifferentiated heavy lifting.

**The dirty secret:** This is infrastructure for managing your infrastructure. The more complex it is, the harder it is to debug at 3am.

---

## Proposed DX Decisions

### Innovation Token Accounting

**Token Budget:** 3 tokens total. Zero should go to tooling. All three should go to the product.

**Current proposed spending:**

| # | Technology | Boring Alternative | Why Innovate Here? | Token Cost | Verdict |
|---|------------|-------------------|-------------------|------------|---------|
| 1 | Custom Python Telegram bot | SSH + tmux attach (or existing CCBot pattern) | Mobile control is real UX need | 0.5 token | Trim scope aggressively |
| 2 | Custom bash orchestrator with priority logic | Pueue daemon with groups | None — Pueue already solves this | 1 token wasted | Replace with Pueue |
| 3 | Custom flock semaphore | Pueue parallel limit | None — Pueue has `pueue parallel N` | 0.5 token wasted | Pueue eliminates this |
| 4 | Custom state machine in JSON | Pueue's native state + SQLite | None | 0.5 token wasted | Pueue eliminates this |
| 5 | Custom hot-reload | Poll config every 60s in simple loop | YAGNI | 0.5 token wasted | Defer |

**Total tokens spent on tooling:** 3+ (over budget before writing business logic)

**Recommendations:**
- Keep: Telegram bot for notifications ONLY (push, not pull) — this solves mobile visibility
- Replace: Custom orchestrator.sh priority/semaphore logic → Pueue groups + parallel limits
- Replace: Custom flock semaphore → `pueue parallel 2` per group
- Replace: Custom state machine → Pueue's native task state (`pueue status --json`)
- Defer: GitHub Issues as primary interface — valuable pattern but a full token for solo founder
- Defer: inotifywait hot-reload — polling loop every 60s is fine, YAGNI
- Reject: Docker containerization — overkill for 2-3 projects on single VPS

**Reclaimed tokens:** 2.5 tokens freed by adopting Pueue

---

### The Boring Stack: What Already Exists

**Pueue** (Rust, 4.6k stars, feature-complete as of v4.0.0, MIT license):
- Groups = projects. `pueue group add saas-app`, `pueue group add side-project`
- Parallel limit per group = `pueue parallel --group saas-app 1`
- Global parallel limit = `pueue parallel 2` (caps Claude concurrency at VPS RAM limit)
- Priority = native. Add tasks with `--priority 10`
- Persistence = pueued daemon handles restart recovery (no custom state file)
- Status = `pueue status --json` (machine-readable, already there)
- Kill task = `pueue kill <id>`, pause group = `pueue pause --group saas-app`
- Dependencies between tasks = `pueue add --after <id>`
- Logs = `pueue log <id>`, per-task stdout/stderr captured automatically

This eliminates orchestrator.sh, flock semaphore, .orchestrator-state.json, and the priority algorithm. All of it. In one `cargo install pueue`.

**systemd user service** for pueued:
```ini
# ~/.config/systemd/user/pueued.service
[Unit]
Description=Pueue Daemon

[Service]
ExecStart=/usr/bin/pueued --daemonize false
Restart=on-failure

[Install]
WantedBy=default.target
```
`systemctl --user enable pueued && systemctl --user start pueued`

This gives VPS-reboot resilience for free. No custom restart logic.

---

### Tech Stack: Boring First

**Boring Choices:**

| Layer | Technology | Why Boring | Why Good Enough |
|-------|------------|------------|-----------------|
| Task queue | Pueue (existing tool) | 5 years old, feature-complete, MIT | Designed exactly for this use case |
| Process supervision | systemd user service | 12 years old, standard on every Linux | Handles restart, logging, dependencies |
| Bot language | Python (python-telegram-bot) | 10+ years old, massive ecosystem | PTB v22 fully supports Forum topics |
| Config | JSON file | Everyone knows it | `jq` readable, no schema drama |
| Scheduling | cron or systemd timer | Literally 50 years old | Good enough for poll intervals |
| Logging | journald (via systemd) | Built-in, no setup | `journalctl -u pueued -f` just works |
| State | Pueue's native SQLite | Already there | No extra DB to manage |

**What we can delete:**
- orchestrator.sh custom event loop → `pueue status --json` + simple Python wrapper
- flock semaphore → `pueue parallel 2`
- .orchestrator-state.json → `pueue status --json`
- Priority math → `pueue parallel --group high-priority 2`, `--group low-priority 1`
- Custom restart recovery → systemd + pueued persistence

---

### Build vs Buy Analysis

**Core to Business** (build these — they're unique):

| Component | Why Build | Estimated Size |
|-----------|-----------|----------------|
| Telegram topic routing | Maps topic_id to project, your DLD convention | ~100 LOC Python |
| Inbox file writer | Writes messages/voice/screenshots to ai/inbox/ | ~80 LOC Python |
| Notify.sh integration | Sends pueue task completion to Telegram topic | ~50 LOC bash |
| Project registration | /addproject command creates topic + Pueue group | ~60 LOC Python |

**Buy/Use Existing** (do NOT build):

| Need | Existing Tool | Lines Eliminated |
|------|---------------|------------------|
| Task queue + concurrency | Pueue | ~200 LOC bash |
| Process supervision | systemd | ~50 LOC bash |
| Task state persistence | Pueue native | ~100 LOC JSON handling |
| Log collection | journald | ~30 LOC bash |
| Priority scheduling | Pueue groups + parallel limits | ~80 LOC bash |

**ROI of boring:**
- Time saved: ~2 days not writing/debugging custom queue and semaphore logic
- Invested in: Telegram integration and first business feature

---

### Developer Workflow: Adding a New Project

**Current proposed flow:**
1. SSH to VPS
2. `git clone <repo> /home/user/<project-name>` — manual
3. Edit `projects.json` manually — error-prone, no validation
4. Restart orchestrator — manual, disruptive
5. Go to Telegram, create topic manually — separate step
6. Map topic_id back to projects.json — requires reading Telegram API response
7. Test that routing works — prayer-based

**Time to add a project:** 15-30 minutes, SSH required

**Boring alternative flow with /addproject:**
1. In Telegram General topic: `/addproject "My App" /home/user/my-app`
2. Bot creates topic, creates Pueue group `my-app`, appends to projects.json
3. Bot responds in new topic: "Ready. Write ideas here."

**Time to add a project:** 2 minutes, phone works

This is the ONE place the Telegram bot earns its complexity. Keep this. This is real UX.

**Onboarding Checklist (for this orchestrator):**

- [ ] `cargo install pueue` on VPS (one command)
- [ ] `systemctl --user enable pueued && systemctl --user start pueued`
- [ ] `pip install python-telegram-bot` in virtualenv
- [ ] Copy `scripts/vps/projects.json.example` to `projects.json`
- [ ] Set `TELEGRAM_TOKEN` and `ALLOWED_USER_ID` in `.env`
- [ ] `systemctl --user start telegram-bot`
- [ ] `/addproject` in Telegram to add first project

**Time from zero to first project managed:** Target 30 minutes (currently undefined/much longer)

---

### Debugging a Stuck Project

**The key DX question:** When autopilot hangs on project X at 2am, how do I know and what do I do?

**With current proposed design:**
- SSH, look at .orchestrator-state.json, figure out PID, `ps aux | grep claude`
- No structured log of what task was running
- Kill it, restart, pray it picks up where it left off

**With Pueue:**
- Telegram notification: "Task saas-app:FTR-042 stuck >900s" (timeout)
- `/log` command → bot runs `pueue log <task_id>` → shows last N lines of stdout
- `pueue kill saas-app` from Telegram, `pueue start saas-app` to resume queue
- `pueue status --json` shows exact state of every task across all groups

**The DX difference is enormous.** Pueue makes state inspectable without SSH.

**Debugging Checklist:**
- Task stuck? `/log` in Telegram topic shows stdout tail
- Want to kill? `/pause` in Telegram topic + Pueue kills gracefully
- VPS rebooted? systemd restarts pueued, Pueue restores queued tasks automatically
- Config changed? `/projects` shows current state from projects.json
- RAM pressure? `pueue status` shows running tasks, kill lowest priority

---

### CLI Ergonomics: Telegram vs SSH + tmux

**The real question is: what are you doing on your phone at 3am?**

**Scenario A: You want to check status** → Telegram `/status` wins. SSH + tmux is painful on mobile.
**Scenario B: You want to add an idea** → Telegram wins. Voice message → inbox.
**Scenario C: You want to debug** → SSH + tmux wins. Logs, interactive debugging, grep.
**Scenario D: You want to stop a runaway process** → Telegram `/pause` wins for immediate kill.

**Verdict:** Telegram is the RIGHT control plane for:
- Read-only status checks
- Adding ideas (inbox)
- Emergency kill/pause
- Getting notified (push)

SSH + tmux is the RIGHT control plane for:
- Active development
- Deep debugging
- Reviewing Claude output
- One-time setup

**Anti-pattern to avoid:** Making Telegram a full terminal replacement. The current spec already shows this creep with `/log` showing 20 lines. That's fine. `/shell <command>` would be wrong.

**The Сережа Рис GitHub Issues approach:**

GitHub Issues as agent interface is genuinely interesting for a different reason than the spec discusses. GitHub Copilot Coding Agent (March 2026) works like this:
1. Assign issue to Copilot
2. Copilot works, asks clarifying questions IN the issue
3. Opens draft PR when done
4. Human reviews PR

This is powerful because issues are: version-controlled, searchable, API-native, structured (title + description + labels + comments), and have a linear history. The spec's `ai/inbox/` files are none of these things.

**However:** For a solo founder running DLD on a VPS, GitHub Issues adds:
- 1 more system to check
- GitHub API dependency
- Webhook complexity for real-time triggering
- Context switch from Telegram to GitHub per task

**Verdict:** GitHub Issues as task queue is worth ONE innovation token IF the morning briefing product needs it (it won't for v1). Defer this. Use Telegram topics + file inbox for now. Revisit when you have more than 5 projects or when the DLD framework needs external contributors.

---

### Pueue vs Task Spooler Comparison

| Feature | Pueue | Task Spooler (tsp) | Custom flock |
|---------|-------|-------------------|--------------|
| Daemon persistence | Yes (systemd-ready) | No | No |
| Groups/namespaces | Yes (per-project isolation) | No | Manual |
| Parallel limit | Per group + global | Global only | Manual with slots |
| Priority | Yes (--priority flag) | FIFO only | Manual |
| Status JSON output | Yes (pueue status --json) | No | Custom |
| Log capture | Yes (per-task stdout/stderr) | Yes | No |
| Kill/pause | Yes (by ID, group, or all) | Limited | Kill PID |
| Restart recovery | Yes (pueued state persists) | No | No |
| Dependency between tasks | Yes (--after flag) | No | Manual |
| Package availability | apt, cargo, brew | apt | built-in |
| Maintenance status | Active (v4.0 March 2025) | Abandoned | N/A |

**Verdict:** Pueue wins comprehensively. Task Spooler is too limited. Custom flock is home-rolling what Pueue already provides.

---

### DX Metrics for This Orchestrator

**Target metrics (since this is internal tooling):**

| Metric | Target | How Measured |
|--------|--------|--------------|
| Time to add new project | <5 min | Manual test: /addproject to first idea stored |
| Time to debug stuck task | <2 min | Manual test: task hangs, how fast to identify + kill |
| Time to check cross-project status | <30 sec | Telegram /global_status latency |
| VPS reboot recovery | <2 min | systemd brings everything up automatically |
| Config change to live | <60 sec | Next orchestrator poll cycle |
| Onboarding on fresh VPS | <30 min | README + one-command setup |

**Cognitive load:**

| Tool to learn | Count | Notes |
|---------------|-------|-------|
| pueue CLI | 1 | 10 commands cover 90% of cases |
| systemctl --user | 1 | Already know if you run a VPS |
| python-telegram-bot | 1 | Already in current spec |
| jq (for projects.json) | 1 | Optional, most people know it |

Total: 4 tools. That's acceptable. Current spec adds bash + Python + custom state format + flock = 5+ concepts with no existing documentation.

---

## Cross-Cutting Implications

### For Domain Architecture (Eric)
- Pueue groups ARE the project domain boundary. One group per project = natural isolation.
- "Orchestrator" should be thin: Telegram routing + Pueue task submission. No business logic.
- The `ai/inbox/` file convention maps cleanly to Pueue task: `pueue add --group saas-app "claude --project /home/user/saas-app spark"`

### For Data Architecture (Martin)
- Pueue's internal SQLite replaces .orchestrator-state.json entirely
- projects.json remains the human-readable config (thin, just topic_id to path mapping)
- No additional database needed for task queue layer

### For Operations (Charity)
- systemd watches pueued, pueued watches tasks. Two layers of supervision, both boring.
- `journalctl --user -u pueued -f` = aggregated logs across all projects
- `pueue status --json | jq` = instant cross-project state view
- Dead man's switch: cron job every 5 min checks pueued is alive, Telegram alert if not

### For Security (Bruce)
- Pueue runs as user process (not root). Each claude CLI invocation inherits user permissions.
- Project isolation: Pueue groups have separate working directories
- No network exposure: pueued listens on Unix socket only, not network

---

## Concerns and Recommendations

### Critical Issues

- **Over-engineering the orchestrator loop**: The proposed orchestrator.sh with priority math, flock semaphore slots, and cycle counting is custom infrastructure solving a solved problem. Pueue exists and does this better.
  - **Fix:** Replace orchestrator.sh event loop with: (a) simple script that submits tasks to Pueue groups, (b) Pueue daemon manages all concurrency and priority. ~300 LOC of bash disappears.
  - **Rationale:** Pueue has 4.6k stars, active maintenance, and handles exactly this use case. Building custom is resume-driven development.

- **Telegram as control plane is correct but scope must be limited**: The spec has the right insight (topics = projects). But scope creep will turn the bot into a pseudo-terminal. Define hard limit now: Telegram = notifications + simple commands. No log streaming, no arbitrary shell commands.
  - **Fix:** Command list maximum is the 8 commands in the spec. Every new command must justify its existence against "just SSH instead."
  - **Rationale:** Each bot command is code to maintain, test, and keep working through Telegram API changes.

### Important Considerations

- **GitHub Issues deferred, not rejected**: Сережа Рис's approach is architecturally sound. GitHub Copilot Coding Agent in March 2026 proves this pattern works. But it assumes GitHub-centric workflow and adds webhook infrastructure. For solo founder on VPS running DLD: defer to phase 2 when you have collaborators or when the briefing product needs it.
  - **Recommendation:** Design projects.json to include `github_repo` field as optional. If set, bot can post inbox items as GitHub Issues. Don't block v1 on this.

- **inotifywait is overengineering at this scale**: Hot-reload via inotifywait adds a file watcher process, edge cases around incomplete writes, and a learning curve. Polling projects.json every 60 seconds in the main loop is completely adequate for a solo founder adding 1-2 projects per month.
  - **Recommendation:** Simple `while True: reload config, sleep 60` in Python. Ship it.

- **This is tooling, not product**: The business blueprint says Phase 1 is consulting, Phase 2 is morning briefing. This orchestrator is pure tooling — it enables the work but generates no revenue. Time-box the build to 2-3 days maximum. Any feature that would take the build past 3 days gets cut.
  - **Recommendation:** Set a hard deadline. If you find yourself writing a custom priority scheduler, stop and adopt Pueue.

### Questions for Clarification

- Is Whisper transcription running locally or via API? (Affects which project handles audio)
- What's the VPS RAM exactly? (Determines `pueue parallel N` limit)
- Do you need cross-project task dependencies? (e.g., "start project B only after project A QA passes") If yes, Pueue's `--after` flag handles this natively.
- Is the morning briefing product going to need GitHub Issues as input source? (This is the real trigger for GitHub Issues integration, not the orchestrator itself)

---

## The 3-Day Build Plan (Boring Stack)

If time-boxing to 72 hours:

**Day 1 (4 hours):**
- Install pueued, configure systemd user service, verify it survives reboot
- Create Pueue groups for 2 test projects
- Wire `autopilot-loop.sh` to submit tasks via `pueue add --group <project>`
- Verify concurrency limit works: `pueue parallel 2`

**Day 2 (4 hours):**
- Minimal Telegram bot: topic routing, /status, /pause, /resume, /addproject
- Wire Pueue task completion to Telegram notification
- Test: add idea via Telegram, watch it flow through inbox-processor, verify Pueue task submitted

**Day 3 (4 hours):**
- `/addproject` command: create topic + Pueue group + write to projects.json
- Error handling: Claude timeout, OOM, Pueue task failure → Telegram alert
- README: 30-minute setup on fresh VPS

**Total: 12 hours.** If it's taking longer, something is over-engineered.

---

## References

- [Dan McKinley — Choose Boring Technology](https://mcfunley.com/choose-boring-technology)
- [Choose Boring Technology Revisited (2025)](https://www.brethorsting.com/blog/2025/07/choose-boring-technology,-revisited/)
- [Pueue — Task Management CLI](https://github.com/Nukesor/pueue) — the boring tool that replaces the custom orchestrator
- [Pueue Groups Documentation](https://github.com/Nukesor/pueue/wiki/Groups)
- [block/agent-task-queue](https://github.com/block/agent-task-queue) — industry pattern: existing tools for agent concurrency
- [CCBot: Telegram + tmux for Claude Code](https://www.reddit.com/r/AgentsOfAI/comments/1qzahrg/) — production proof of Telegram topics pattern
- [codex-cli-farm](https://github.com/waskosky/codex-cli-farm) — shell-first approach works in practice
- [GitHub Copilot Coding Agent](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent) — GitHub Issues pattern for reference
- [GitHub Agentic Workflows (Feb 2026)](https://github.blog/ai-and-ml/automate-repository-tasks-with-github-agentic-workflows/) — validates Issues-as-queue approach
- [systemd timers vs cron 2026](https://crongen.com/blog/cron-vs-systemd-timers-2026) — use systemd for process supervision
