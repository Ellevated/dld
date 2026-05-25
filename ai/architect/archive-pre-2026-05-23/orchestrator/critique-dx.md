# Developer Experience Cross-Critique

**Persona:** Dan (DX Architect)
**Phase:** 2 — Peer Review
**Date:** 2026-03-10

---

## Peer Analysis Reviews

### Analysis A (Ops / Observability)

**Agreement:** Agree

**Reasoning from DX perspective:**

Analysis A found the most operationally dangerous DX problem in the entire set: the Claude CLI memory number is wrong by an order of magnitude. The spec says 200-500 MB per Claude process. Reality, per GitHub issues: 2-16 GB for extended autopilot runs. This is not a margin of error, it is a different category of infrastructure requirement. A founder who provisions an 8 GB VPS based on the spec's number will hit OOM at 3am and have zero idea why.

From a DX lens, the RAM floor check before semaphore acquisition is the right move. It turns a silent crash into an observable refusal: "Not launching Claude, only 1.8 GB free." That is debuggable. A silent OOM is not.

The structured logging approach (JSON to journald via systemd) is solid boring-tech thinking. `journalctl -u orchestrator -f` works on any Linux VPS, no setup required, searchable with `grep`. The Loki + Promtail extension is reasonable if the founder actually wants cross-project query power — but I would defer Loki to when there are 4+ projects. For 2-3, `journalctl --user -u pueued -f` is enough.

One thing I agree with strongly: Telegram as both control plane AND alert channel is a single point of failure worth flagging. The email fallback for critical alerts is the correct boring answer. Gmail SMTP with an app password takes 20 minutes to set up and costs nothing.

**Missed gaps:**

- No mention of Pueue as a replacement for the custom semaphore, despite the ops concern about flock failure modes. The RAM-aware slot admission logic Analysis A wrote is ~50 lines of bash that Pueue's `pueue parallel 2` and its daemon state machine already handle. That is 50 lines the founder does not have to debug at 3am.
- The Loki + Promtail + Grafana stack recommendation is 350 MB RAM that competes with the Claude processes. At `MAX_CONCURRENT=1` on an 8 GB VPS, that is meaningful. Should note this trade-off explicitly.

---

### Analysis B (Devil's Advocate)

**Agreement:** Agree — and this is the most important peer analysis in the set.

**Reasoning from DX perspective:**

Analysis B is doing my job better than I did in one area: calling out the business case problem. The spec is building tooling while Phase 1 (consulting content) is unfinished. Anti-pattern 2 from the founder's own profile is "optimizes tooling instead of product." Analysis B named this directly and included the specific phase from the business blueprint. That takes honesty.

The three-contradiction structure is excellent DX thinking dressed as skepticism:

1. Attended vs. unattended use case — this is a genuine DX fork. If the founder is at the keyboard, tmux windows are free and sufficient. If the founder is asleep, you need an orchestrator with monitoring. The spec assumes unattended but is designed without the monitoring that makes unattended safe. That is a contradiction I should have caught more explicitly.

2. Telegram as primary vs. optional layer — agreeing with my position. The spec committed to Telegram-primary before evaluating the alternative.

3. Bash orchestrator vs. production requirements — this is precisely where I landed on Pueue. The bash + flock path is "heroic choice pretending to be the boring choice." Analysis B's phrasing is better than mine.

The Fred Brooks quote is correct: there is no single unifying principle in the spec. When two components conflict, there is no tiebreaker rule.

**Missed gaps:**

- Analysis B identifies the problems without proposing the specific boring alternative. Naming Pueue once as the answer to bash + flock is not enough — it should show the concrete replacement: `pueue parallel 2` replaces the slot logic, `pueue group add saas-app` replaces the per-project configuration, `pueue status --json` replaces `.orchestrator-state.json`. The critique diagnoses the illness without prescribing the medicine.
- "Why not a CLI?" challenge at the end is asking the right question but not answering it. SSH + a 20-line status script answers `/status` immediately with zero Telegram dependency. The DX question is whether mobile-from-phone use cases (checking status at 2am in bed, adding an idea via voice on a walk) justify the Telegram bot's complexity. My answer is yes for those specific use cases, no for control plane commands.

---

### Analysis D (Security)

**Agreement:** Partially Agree

**Reasoning from DX perspective:**

Analysis D's P0 items are correct and genuinely required: `from_user.id` whitelist is a one-hour implementation that eliminates the spoofing risk. The `--max-turns` + timeout recommendation is already in my analysis. These should be in any final architecture.

The local whisper.cpp recommendation is correct from both security and DX perspectives. The API dependency adds latency, a network call per voice message, and vendor lock-in. whisper.cpp on CPU takes 2-5 seconds for a 30-second message and costs $0. Same result, zero dependency, better DX (works offline too).

The prompt injection section references real Trail of Bits research (Oct 2025). For inbox items that originate from external sources — GitHub Issue descriptions, web page summaries — XML structural separation in prompts is the right mitigation. This is worth 4 hours of implementation time.

**Where I partially disagree:**

The separate Unix user per project recommendation is architecturally correct but adds operational complexity that works against the "5-minute new project" DX goal. Every time the founder adds a project, they now need to create a user, set up home directory permissions, configure sudo rules for the orchestrator, and test the isolation. For a solo founder, this is a meaningful operational burden. The bubblewrap sandbox alternative (Analysis D mentions it) achieves most of the same isolation at lower operational cost. I would rank it: bubblewrap sandbox (P1), separate users (P2 / when you have reason to believe you need it).

The `projects.json` SHA256 integrity check is security theater for a single-user system. If an attacker has compromised the VPS user account, they can update both the config and the hash file. The value is as a change detection mechanism, not access control. Spending 2 hours on this is a poor DX trade-off when the `from_user.id` whitelist (also 2 hours) eliminates the primary attack vector.

**Missed gaps:**

- No assessment of the DX cost of security hardening. Security features are innovation tokens too. The P0 items are worth the cost. Some P3 items (systemd credentials, semaphore relocation) add maintenance burden for minimal threat reduction in a solo-user system.

---

### Analysis E (LLM Architect)

**Agreement:** Agree — strongest technical research in the set.

**Reasoning from DX perspective:**

Analysis E validated my Pueue recommendation from a different angle: the RAM reality. The documented 6.4 GB for a single Claude session in v2.1.62 regression changes the concurrency math entirely. `max_concurrent_claude: 2` on 8 GB VPS is not just risky, it is near-certain OOM on any extended autopilot run. That is a 3am incident waiting to happen.

The session contamination finding (GitHub #30348) is the most important new piece of information in the peer analyses. Two concurrent Claude sessions on the same Linux user with the same `~/.claude/` can contaminate each other's contexts. This is a known bug, open, no ETA. The fix — `CLAUDE_CODE_CONFIG_DIR` per project per invocation — is one env var, one line change, zero cost. This should be in any final architecture spec.

The Agent Teams ruling is definitive: 13-16 GB RAM on 8 GB VPS = immediate OOM. Cross-project scope explicitly not supported. Experimental bugs in production (teammates don't poll inbox, role degradation after 15 iterations). Analysis E documented this comprehensively. Result: Agent Teams is off the table for this architecture.

The `cwd` discipline finding is underappreciated: every `claude -p` invocation MUST use `(cd "$PROJECT_DIR" && claude -p ...)` pattern or CLAUDE.md auto-load breaks. This is the primary context injection mechanism and it is trivially easy to get wrong in a bash script.

The Codex CLI question (from the new agenda items) receives no coverage from Analysis E, which is the one gap in otherwise excellent research.

**Missed gaps:**

- No coverage of Codex CLI as a second worker type. The founder's addendum explicitly adds this requirement.
- The `CLAUDE_CODE_CONFIG_DIR` fix is mentioned as Option B but not pushed hard enough as the required solution. This should be a non-negotiable in the architecture spec, not an "open question."

---

### Analysis F (Evolutionary Architect)

**Agreement:** Partially Agree

**Reasoning from DX perspective:**

Analysis F's fitness functions are the most DX-valuable output in the entire peer set. The concept of "what automated check protects this architectural decision" is exactly the right framing for a system that will run unattended. The inbox latency check (stale files > 5 min = alert), the semaphore correctness check (active Claude count vs. config), and the `projects.json` schema validity pre-commit hook — these are all worth implementing.

The scaling inflection points analysis is well-calibrated. 4 projects (RAM ceiling), 6 projects (cycle time), 8 projects (bash LOC limit). These are specific, measurable thresholds. The `orchestrator.sh` LOC fitness function — cut to Python if it exceeds 400 lines — is exactly the kind of pre-committed refactoring trigger that prevents a 1200-line bash disaster.

The Strangler Fig migration path is appropriate for the use case. Starting with one project in `projects.json` and migrating incrementally is the right way to introduce a new orchestrator without breaking the existing manual flow.

**Where I partially disagree:**

The inotifywait + polling fallback combination is over-engineered for the problem. Analysis F recommends both together as "belt and suspenders." But inotifywait is an additional process to supervise, and polling already handles the case where inotifywait dies. The real recommendation should be: start with polling-only (3 lines of bash, no dependency), add inotifywait only when hot-reload latency becomes a user-perceived problem. YAGNI in practice.

The symlinked release pattern for zero-downtime upgrades is an interesting pattern but is significant complexity for solo-founder tooling. The simpler boring approach: `git pull && systemctl restart orchestrator`. Accept the 30-second downtime. This is internal tooling, not a product with an SLA. Time-box the upgrade procedure to the simplest thing that works.

**Missed gaps:**

- The fitness functions are defined but there is no recommendation on how many to implement on Day 1 vs. defer. I would say: 3 fitness functions on Day 1 (heartbeat liveness, schema validity pre-commit hook, RAM floor check) and defer the rest until they correspond to actual incidents. Implementing all 9 fitness functions before having 2 projects running is premature optimization.

---

### Analysis G (Data Architect)

**Agreement:** Partially Agree

**Reasoning from DX perspective:**

Analysis G makes one critical correct call: the `.orchestrator-state.json` race condition is real. The citation of Claude Code GitHub #29158 (335 corruption events in 7 days from concurrent JSON writes) is direct evidence that this failure mode happens in practice, not just in theory. A corrupted state file at 3am is exactly the kind of incident that turns "simple tooling" into a 4-hour debugging session.

The system-of-record table is excellent clarity. Separating config (projects.json, human-written, rare) from runtime state (SQLite, daemon-written, frequent) is the right principle.

**Where I substantially disagree:**

The SQLite recommendation for runtime state is over-engineered for the concurrency characteristics of this system.

The actual write concurrency is: one orchestrator daemon writes state. The Telegram bot reads state. This is single-writer, one-reader. That is the ideal case for a JSON file with atomic writes (`write → /tmp → mv`). The atomic `mv` on Linux is guaranteed to be atomic. The Pueue daemon's own SQLite serves as the semaphore state store natively. There is no need for a custom `orchestrator.db` with `claude_slots` table.

The case for SQLite requires true concurrent writes from multiple processes. This system does not have that. The fix for the state file corruption risk is one line: write to `.tmp` then `mv`. That is cheaper than adding a SQLite dependency, writing schema migrations, and learning SQLite WAL mode.

Analysis G's `usage_ledger` for cost tracking is the one case where SQLite is genuinely better than flat files (because you want aggregate queries). But this is a nice-to-have, not a requirement for the orchestrator to function.

**The DX cost of SQLite:**
- Every script that reads state now needs `sqlite3` CLI or a Python/Node wrapper
- Debugging state at 3am via SSH becomes `sqlite3 orchestrator.db "SELECT * FROM project_state"` instead of `cat .orchestrator-state.json | jq`
- Adding SQLite schema migrations is a maintenance surface that grows with the system

**What I recommend instead:**
- Atomic JSON writes for `projects.json` and `orchestrator-state.json` (the actual fix)
- Pueue's native SQLite for semaphore state (already there, zero effort)
- Optional: usage tracking in a separate append-only CSV or SQLite ledger file (add when you need it)

**Missed gaps:**

- No mention of Pueue as the semaphore state store. Pueue already maintains its own SQLite for task state. The `claude_slots` table Analysis G proposes is reinventing what Pueue groups + `pueue parallel N` already provide.

---

### Analysis H (Domain Architect)

**Agreement:** Partially Agree

**Reasoning from DX perspective:**

Analysis H makes the most architecturally sophisticated argument in the set: the orchestrator is an application service, not a domain concept. The bounded context model (Portfolio, Inbox, Pipeline, Notification) is well-reasoned. The critique that "project" is doing too much work — simultaneously meaning directory path, Telegram topic, scheduling unit, pipeline state, and business entity — is a legitimate signal of missing context boundaries.

The Telegram ACL argument is correct: `message_thread_id` is a Telegram-specific primitive that should not appear in the domain model. The domain should speak `RoutingKey`, not `message_thread_id`. If Telegram is replaced tomorrow, only the ACL adapter changes.

**Where I partially disagree:**

For a 2-3 project solo-founder orchestrator, the DDD bounded context model is a real innovation token. Implementing Portfolio, Inbox, Pipeline, and Notification as explicit bounded contexts with anti-corruption layers and published language domain events costs 3-5 days of design and implementation time. The spec has a 2-3 day build budget.

The DX principle here is: the right level of architecture for the problem. For a solo founder running 2-3 projects on a VPS, a well-named bash script with clear sections is more maintainable than a proper DDD application. The domain model Analysis H describes is the correct target for when this becomes a product (morning briefing platform managing 100 clients' projects). It is premature for personal tooling.

The `RoutingKey` abstraction is the one recommendation I would actually implement now: it costs 5 lines of config and makes the Telegram-to-project mapping explicit and replaceable. The rest — formal aggregates, domain events, ACL layers — defer until the orchestrator is a product.

**What Analysis H gets right that I missed:**

"The orchestrator's primary job is context delivery, not process management." This is from the Boden Fuller reference and it reframes the system correctly. The most valuable thing the orchestrator does is ensure Claude has the right CLAUDE.md loaded in the right project directory at the right time. The scheduling and semaphore logic is secondary.

**Missed gaps:**

- No mention of the new agenda items (Multi-LLM, topology, practical bootstrap). Analysis H stays in pure domain modeling.
- The DX cost of the DDD model is not mentioned. Bounded contexts are powerful but they are an innovation token.

---

## New Agenda Questions (Founder Addendum)

### 1. Multi-LLM DX: Claude Code + ChatGPT Codex (GPT-5.4)

*counts innovation tokens*

Adding Codex as a second worker type is not free. Let me be direct about the DX reality.

**The core difference:** Claude Code is a local-first CLI agent that runs in your terminal and reads your filesystem directly. Codex is a cloud-first agent that spawns an ephemeral sandbox pre-loaded with your repo. These are not equivalent workers. They have different invocation patterns, different auth, different resource profiles, and different failure modes.

**Invocation patterns side by side:**

```bash
# Claude Code — local, blocks, uses VPS RAM
cd $PROJECT_DIR && claude -p "run autopilot for FTR-042" \
  --max-turns 30 --model claude-opus-4-6

# Codex — cloud, fire-and-forget, VPS only needs to submit
codex "Fix the billing webhook retry logic in src/billing/webhook.py" \
  --model gpt-5.4-codex --approval-mode full-auto
```

The key DX insight: Codex running cloud-side means it does NOT consume VPS RAM. A concurrent Claude session costs 2-8 GB of VPS RAM. A concurrent Codex session costs ~100 MB (just the CLI client). This is the actual reason to run both.

**The honest router design:**

Do not build a smart router that analyzes tasks and picks Claude vs. Codex. That is an innovation token for a benefit you have not measured. Instead:

```json
// projects.json addition
{
  "id": "saas-app",
  "default_runner": "claude",
  "runners": {
    "claude": { "model": "claude-opus-4-6", "max_turns": 30 },
    "codex": { "model": "gpt-5.4-codex", "approval_mode": "full-auto" }
  }
}
```

Manual routing per task: the founder types `/run codex FTR-042` to explicitly use Codex for a specific task. No auto-routing logic needed in v1. The founder knows which tool is better for which task from experience.

**Pueue handles this cleanly:** Each runner gets its own Pueue group.

```bash
pueue group add claude-runner
pueue group add codex-runner
pueue parallel --group claude-runner 1  # RAM-constrained
pueue parallel --group codex-runner 3  # Cloud, RAM not a factor
```

This is the boring answer: two groups, explicit routing, no smart logic.

**Concurrency math with both runners:**

With Codex in the mix, the RAM constraint changes shape. Claude sessions are VPS-RAM-bound (max 1-2 concurrent). Codex sessions are network-bound (max whatever Codex API allows, probably 3-5). Pueue groups model this correctly with different parallel limits per group.

**DX friction of two CLI tools:**

Both Claude Code and Codex CLI require separate auth setup. `ANTHROPIC_API_KEY` for Claude, `OPENAI_API_KEY` for Codex. Both need separate `npm install -g` (or equiv). Both have different config directories, different session formats, different log outputs. The orchestrator wraps this complexity, but the `run_claude()` and `run_codex()` functions in `claude-runner.sh` will have different error handling, different timeout patterns, different exit codes.

**My recommendation:** Use Codex for discrete, well-scoped tasks where the cloud sandbox is an advantage (no VPS RAM consumed, full-auto approval mode is safe for isolated tasks). Use Claude for complex reasoning, deep refactoring, and anything requiring your project's CLAUDE.md context loaded from the actual codebase. Do not auto-route in v1.

---

### 2. Same VPS as Docker containers: DX of debugging

The founder already runs Docker containers for projects on the same VPS. The question is whether to add the orchestrator to the same VPS or use a dedicated lightweight orchestrator VPS.

**DX of same VPS (colocation):**

When something breaks, you have one place to SSH. `docker stats` shows container RAM. `pueue status` shows Claude task state. `journalctl -u telegram-bot -f` shows bot logs. Everything is in one place.

But RAM contention is the DX killer. If three Docker containers each use 512 MB and a Claude session leaks to 8 GB, the orchestrator, the bot, and the containers all compete for the same pool. OOM kills do not respect service boundaries. One leaked Claude session can take down a Docker container running a paying customer's service. That is the real risk.

**DX of separate orchestrator VPS:**

Two SSH targets. Two places to check. Two places to configure. But RAM isolation: the Docker project containers are on their own VPS (their RAM, their OOM boundary). The orchestrator VPS RAM is dedicated to Claude + Pueue + bot. One Claude leak cannot kill a customer-facing service.

**The boring verdict for this exact situation (founder already has Docker containers on VPS):**

Keep them on the same VPS only if:
- The Docker containers are not customer-facing (no paying-customer SLA)
- The VPS has at least 32 GB RAM (Hetzner CX51 at €31/mo)
- The Docker containers run with explicit `--memory` limits so OOM does not cascade

If any Docker container is customer-facing: separate VPS for the orchestrator. The cost is €8-16/mo for a 4-8 GB orchestrator VPS. The benefit is: a Claude memory leak cannot take down a customer's service.

**What "same VPS" debugging actually looks like:**

Good: one terminal, one SSH session, everything visible.
Bad: `free -h` shows 1.2 GB free, two Claude sessions are running, one Docker container gets OOM-killed at 4am, and the postmortem takes 2 hours because you're checking three log sources to reconstruct the cascade.

The DX cost of colocation is paid at incident time, not setup time.

---

### 3. Practical Bootstrap: "Add new project in 5 minutes"

Analysis A and F mention this goal but do not give a concrete answer. Here is the actual flow.

**What "5 minutes" requires:**

First, the infrastructure must already be running: Pueue daemon up, Telegram bot up, `projects.json` exists. The 5 minutes is for adding an incremental project, not first-time setup.

**The flow (both Claude and Codex runners):**

Step 1: Git clone the project repo to VPS (< 30 seconds if network is fast).
Step 2: In Telegram General topic: `/addproject "My App" /home/user/my-app`
Step 3: Bot creates Telegram topic, creates Pueue group `my-app`, appends to `projects.json`.
Step 4: For Codex: bot also sets `OPENAI_API_KEY` source for the project (reads from existing env).
Step 5: Bot responds in new project topic: "Ready. Write ideas here."

That is genuinely 2-3 minutes if the bot `/addproject` command is implemented correctly.

**What breaks this SLO:**

- Manual Telegram topic creation (adds 3-5 minutes)
- Manual `projects.json` edit + validation (adds 5-10 minutes with errors)
- SSH required for any step (adds context switch cost)

The `/addproject` command is the critical DX investment. This is where the Telegram bot earns its existence — automating the 10-step manual process into a single Telegram command.

**Bootstrap script for first-time VPS setup (the one-time cost):**

```bash
#!/bin/bash
# install-orchestrator.sh
apt install -y pueue whisper-cpp ffmpeg
cargo install pueue || true  # if not in apt
pip install python-telegram-bot python-dotenv
systemctl --user enable pueued && systemctl --user start pueued
cp projects.json.example projects.json
cp .env.example .env
echo "Edit .env with TELEGRAM_TOKEN, ALLOWED_USER_ID, then run:"
echo "systemctl --user start telegram-bot"
```

Target: 30 minutes from fresh VPS to first project managed.

---

### 4. Does Pueue handle heterogeneous runners (Claude + Codex)?

Yes. This is exactly what Pueue groups are designed for.

From the official Pueue Groups documentation (confirmed in research):

> "Grouping tasks can be useful whenever your tasks utilize different system resources. A possible scenario would be to have an `io` group for tasks that copy large files. At the same time there's the `cpu` group which will execute cpu-heavy tasks. The parallelism setting of `io` could be set to `1` and `cpu` be set to `2`."

The analogy to the orchestrator is direct:

```bash
# Claude group: RAM-constrained, VPS-local
pueue group add claude-runner
pueue parallel --group claude-runner 1  # or 2 on 32 GB VPS

# Codex group: network-constrained, cloud-side
pueue group add codex-runner
pueue parallel --group codex-runner 3  # Codex API allows more concurrency

# Add a Claude task
pueue add --group claude-runner -- bash -c \
  "cd /home/user/saas-app && CLAUDE_CODE_CONFIG_DIR=/var/orch/saas-app/.claude \
   claude -p '/autopilot' --max-turns 30"

# Add a Codex task
pueue add --group codex-runner -- bash -c \
  "cd /home/user/saas-app && codex 'fix billing webhook' --approval-mode full-auto"
```

Each group has its own parallel limit, its own task queue, and its own concurrency semantics. The heterogeneous runner model maps cleanly. No separate queue infrastructure needed.

**The only gap in Pueue for this use case:** Priority across groups. If a high-priority Claude task and a medium-priority Codex task are both queued, Pueue will not automatically deprioritize the Codex task to give Claude the slot it needs. This is acceptable at 2-3 projects — you just configure the right parallel limits. At 5+ projects with mixed runners, you may need a thin priority wrapper that submits to the appropriate group based on project priority.

---

## Ranking

**Best Analysis:** B (Devil's Advocate / Fred)

**Reason:** Analysis B is the only peer that asked the hardest DX question: "Why are we building this at all right now?" It named the anti-patterns from the founder's own profile, connected the orchestrator build to the Phase 1 consulting content work being left unfinished, and applied the business lens throughout. The three-contradiction structure is the most useful diagnostic tool in the peer set. DX is not just "how easy is the tooling to use" — it is "is this tooling justified by business value?" Analysis B answered that. Everyone else assumed the answer was yes.

**Worst Analysis:** H (Domain Architect)

**Reason:** Not because the analysis is wrong — the DDD model is correct. But Analysis H spends 1,200 words on bounded context theory for a system that has a 2-3 day build budget. The ACL for Telegram routing, the Portfolio-as-aggregate-root, the domain events for PhaseCompleted and ConcurrencySlotReleased — these are the right abstractions for a multi-tenant SaaS that will manage hundreds of clients' projects. They are innovation tokens spent on architecture for a solo founder's personal tooling. Analysis H also did not address any of the new agenda questions (Multi-LLM, topology, practical bootstrap). The depth of DDD analysis came at the cost of practical coverage.

---

## Revised Position

**Revised Verdict:** Same as Phase 1, with additions from peer research.

**What the peer analyses confirmed:**

- Pueue is the correct boring answer for concurrency management (confirmed by absence of any peer analysis showing a better alternative)
- RAM ceiling is the primary infrastructure risk (Analysis A and E both hit this independently from different angles)
- Session contamination via shared `~/.claude/` is a real bug requiring `CLAUDE_CODE_CONFIG_DIR` per project (Analysis E — this was missing from my Phase 1 research)
- Atomic writes for state files are required (Analysis G — correct diagnosis, wrong medicine)

**What the peer analyses changed:**

One position: I was too permissive about the state file. Analysis G's citation of the `~/.claude.json` corruption bug (335 events, 7 days) convinced me that atomic writes are not optional. My new recommendation: `projects.json` and any orchestrator state file MUST use write-to-tmp then mv. This is 3 lines of bash and costs nothing. The argument for SQLite is not wrong, but atomic mv is the boring fix that eliminates 95% of the corruption risk without adding a dependency.

**Final DX Recommendation:**

The boring stack for this orchestrator, incorporating peer analysis:

| Layer | Recommendation | Why |
|-------|---------------|-----|
| Task queue | Pueue with groups | Replaces flock + custom priority logic. Groups handle heterogeneous runners natively. |
| Semaphore | `pueue parallel N` per group | Claude group: 1-2. Codex group: 3. RAM-appropriate. |
| Process supervision | systemd user service | Restart on failure, journald logging, cgroup memory limits. |
| State store | Atomic JSON files | Atomic write (tmp + mv). Not SQLite. Single writer. `jq` debuggable at 3am. |
| Multi-LLM routing | Explicit per-task, two Pueue groups | `/run codex FTR-042` in Telegram. No auto-routing in v1. |
| Context isolation | `CLAUDE_CODE_CONFIG_DIR` per project + `cwd` discipline | Required. Prevents session contamination bug #30348. |
| Infrastructure topology | Same VPS only if Docker containers are not customer-facing | Separate VPS the moment any container has a paying-customer SLA. |
| Telegram bot | Notifications + `/addproject` + simple commands | The `/addproject` command is the primary DX value. Hard cap at 10 commands total. |
| Alerting | Telegram + Gmail SMTP fallback | Two channels for critical alerts. 20-minute setup. |
| Monitoring | healthchecks.io (free tier) | Dead man's switch for orchestrator. $0. 30 minutes to implement. |
| New project bootstrap | `/addproject` command: one Telegram message | Target 2-3 minutes per project. Git clone is the only SSH step. |

**The build budget is 3 days maximum.** Any feature that takes the build past 3 days gets cut. Any feature not in the boring stack requires explicit justification as an innovation token.

**Innovation tokens for this project (total: 3):**

1. Telegram bot (0.5 token) — mobile control is a real use case. Scope limited to notifications + simple commands + `/addproject`.
2. Multi-LLM routing (0.5 token) — explicit manual routing, two Pueue groups. No auto-routing.
3. Remaining 2 tokens — reserved for the actual business (morning briefing product). Do not spend them here.

---

## References

- [Dan McKinley — Choose Boring Technology](https://mcfunley.com/choose-boring-technology)
- [Pueue Groups — Official Wiki](https://github.com/Nukesor/pueue/wiki/Groups)
- [Claude Code vs Codex CLI — Blake Crosley (2026)](https://blakecrosley.com/blog/claude-code-vs-codex)
- [Codex vs Claude Code — DataCamp (2026)](https://www.datacamp.com/blog/codex-vs-claude-code)
- [Claude Code #30348 — Cross-session contamination](https://github.com/anthropics/claude-code/issues/30348)
- [Claude Code #29576 — Memory regression v2.1.62](https://github.com/anthropics/claude-code/issues/29576)
- [Choose Boring Technology Revisited (2025)](https://www.brethorsting.com/blog/2025/07/choose-boring-technology,-revisited/)
