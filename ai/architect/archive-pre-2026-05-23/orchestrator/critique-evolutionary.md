# Evolutionary Architecture Cross-Critique

**Persona:** Neal (Evolutionary Architect)
**Phase:** 2 — Peer Review
**Date:** 2026-03-10

---

## Peer Analysis Reviews

### Analysis A (Operations / Charity)

**Agreement:** Agree — strongest technical finding in the set

**Reasoning from evolutionary perspective:**

Peer A did what fitness functions require: found real numbers, not assumptions. The RAM figure correction (200-500 MB → 2-16 GB per Claude session from actual GitHub issues) is not a minor calibration. It is the single most consequential architectural fact in this entire council session. A fitness function that monitors concurrent Claude counts against a RAM floor that is 10x wrong is not a fitness function — it is theater.

From an evolutionary perspective, this is a change vector that already materialized. Claude CLI memory behavior has already changed (regression in v2.1.62, documented in March 2026). The architecture must evolve to account for this, not assume it will be stable.

Peer A's RAM-aware semaphore implementation (check `/proc/meminfo` before slot acquisition) is exactly the kind of automated architectural check I advocate. It is a fitness function embedded in the operational path: before launching a Claude process, verify the system meets the memory precondition. This is not a monitoring alert — it is a gate.

The three-layer heartbeat design (orchestrator self-ping → per-project activity → Telegram bot liveness) reflects evolutionary thinking: don't assume one failure mode, design for independent failure at each layer.

The `MemoryMax=14G` systemd cgroup ceiling converts an unmonitored risk into a bounded, recoverable failure. When Claude leaks, it OOM-kills itself within the cgroup before killing the VPS. This is exactly the kind of "constraints as architecture" thinking that prevents decay.

**Missed gaps:**

- Peer A does not address the Multi-LLM question (Codex alongside Claude). Adding Codex means a second, independently behaving RAM profile — one that may spike differently and require its own RAM floor check and separate `MAX_CONCURRENT` accounting.
- No fitness function for Claude CLI version pinning. Peer A identified the regression risk but did not propose a CI check that prevents upgrading Claude CLI without a staged rollout.
- The three-layer heartbeat design has a single-medium dependency: all three layers use Telegram for alert delivery. If Telegram is the failure mode, all three alerts are silenced simultaneously. Peer A identifies this under Alerting but does not resolve it structurally.

---

### Analysis B (Devil's Advocate / Fred)

**Agreement:** Partially Agree — strongest strategic challenge, weakest technical follow-through

**Reasoning from evolutionary perspective:**

Peer B correctly identifies the most dangerous pattern in the founder's profile: anti-pattern #2 ("optimizes tooling instead of product"). The question "is this orchestrator Phase 1 or Phase 2 work?" is exactly the kind of question an architect should ask before building. The business blueprint is unambiguous that Phase 1 is consulting content, not tooling. Peer B earns full credit for naming this.

However, from an evolutionary perspective, Peer B's overall verdict is flawed in a critical way: it conflates "we should not build this now" with "this architecture is wrong." Those are separate questions. The architectural analysis (SPOF identification, flock failure modes, state management contradictions) is largely correct. The strategic analysis ("don't build this at all") is also worth considering. But the conclusion that tmux + cron + Pueue solves everything dismisses the very thing that makes this orchestrator worth building: the Telegram-native founder experience.

The Brooks "no conceptual integrity" critique is memorable but not accurate. The existing spec DOES have a unifying idea: "a founder manages multiple projects through a single Telegram interface, and the orchestrator routes, schedules, and reports." That is a conceptual identity. What the spec lacks is clean implementation of that identity. Peer B correctly identifies the implementation confusion but misidentifies it as a missing concept.

The most evolutionarily valuable insight from Peer B: the explicit demand to define whether this orchestrator is for attended or unattended operation. This is a change vector clarification — the two modes have completely different change velocity and failure mode profiles. An attended orchestrator needs to be debuggable. An unattended orchestrator needs to be self-healing. Building one while assuming the other leads to drift.

**Missed gaps:**

- No fitness functions proposed. Peer B identifies every problem but proposes zero automated checks. A skeptic who only names problems is a critic, not an architect.
- The Pueue recommendation ignores that Pueue does not speak Telegram natively. Adopting Pueue means the Telegram bot must bridge to Pueue's API — which is a new integration surface, not a simplification. Peer B's "50-line Python script" claim understates the real work.
- The bus factor argument (what if the founder forgets how this works in 6 months?) cuts both ways. tmux + cron + Pueue is NOT more memorable than a well-documented bash orchestrator. Both require a runbook. Peer B does not propose one.
- No reversibility analysis. Peer B correctly challenges the decisions but does not analyze which are reversible and which are not. From an evolutionary perspective, the question is not "should we build this?" but "can we change our mind if we're wrong?"

---

### Analysis C (DX / Dan)

**Agreement:** Agree — best practical simplification, strongest "boring tech" discipline

**Reasoning from evolutionary perspective:**

Peer C makes the innovation token framing work: count how many novel things you are building before any business feature exists. The answer — five custom pieces of infrastructure before shipping anything — is a genuine architectural smell. From an evolutionary standpoint, each custom-built component is a change vector that the founder must maintain. Pueue's 4.6k stars and active maintenance means its change velocity is managed by someone else. That is the right kind of architectural debt reduction.

The Pueue groups = project boundaries insight is elegant: the domain concept (project isolation) maps directly to the tool primitive (Pueue group). When a domain concept has a direct structural mapping to a boring tool, that is a signal to use the tool. This is what Martin Fowler calls "supple design" — the domain shapes the code, not the reverse.

The 3-day build plan is one of the most valuable artifacts in the entire council session. It operationalizes the evolutionary principle: build incrementally, verify fitness at each step, defer what is not needed for the current scale.

The fitness function the 3-day plan implicitly contains: "If it takes more than 72 hours to build the orchestrator, something is over-engineered." That is a time-boxed architectural constraint — a form of fitness function applied to the build process itself.

**Missed gaps:**

- No analysis of Multi-LLM implications. Adding Codex CLI to a Pueue-based system is actually simpler than adding it to a custom orchestrator — Codex is just another `pueue add --group <project> "codex ..."` command. Peer C missed the opportunity to show why their architecture handles the new requirement with less friction.
- The 3-day plan assumes Pueue's state persistence is sufficient recovery, but Pueue's SQLite state lives at `~/.local/share/pueue/` — not in the project git repo, not backed up, not atomic-rename-safe. On VPS reboot without systemd user service, tasks are lost. This is a fitness function gap.
- inotifywait dismissal ("YAGNI, poll every 60s") is correct for config hot-reload but does not address inbox pickup. A 60-second polling loop on inbox means a 60-second maximum latency for idea capture. Peer C does not discuss what the acceptable latency SLO is.
- The `github_repo` optional field suggestion for projects.json is good additive design. But it is not connected to a fitness function: how do you verify the optional field, if set, actually points to a valid repo?

---

### Analysis D (Security / Bruce)

**Agreement:** Partially Agree — highest severity findings, some over-engineering for the context

**Reasoning from evolutionary perspective:**

The prompt injection defense (Trail of Bits, October 2025) is not optional for an AI agent system. This is not a future risk — it is a current documented attack class. The fitness function for this is: every inbox-processing Claude invocation must use XML structural separation in the prompt. That is testable. The automated check: `grep -r "dangerously-skip-permissions" scripts/vps/` should return zero in the inbox-processing paths.

The `from_user.id` whitelist is a one-day implementation that eliminates the most likely real-world attack vector. This is a reversibility argument disguised as a security argument: if you build the orchestrator without user-level auth, adding it later requires touching every command handler. Start with it; the cost of the reverse decision is high.

The separate-Unix-user-per-project recommendation is architecturally sound and eliminates the cross-project secret leakage class. But from an evolutionary perspective, the right question is: what is the minimum viable isolation today that allows us to evolve to per-user isolation later? The answer is: `CLAUDE_CODE_CONFIG_DIR` per project (Peer G's recommendation) plus `--max-turns` and `--sandbox` flags. Full per-user Unix isolation can be added later without changing the call sites — just wrap `claude` in `sudo -u user-$project_slug`.

The bubblewrap/systemd credentials recommendations are correct but may be beyond the MVP scope for a solo founder's internal tooling. The evolutionary principle says: implement what prevents irreversible damage now (user-level auth, prompt injection defense, `--max-turns`), defer what can be added incrementally (per-user isolation, systemd credentials).

**Missed gaps:**

- No fitness function for prompt injection defense. Peer D identifies the risk and proposes mitigations but does not propose an automated check that verifies the mitigations are in place. A pre-commit hook that verifies inbox-processing scripts use XML-tagged prompts would be 30 minutes of work.
- The audit log proposal is correct but has no retention policy. An append-only log without log rotation is a disk-fill vulnerability — exactly the kind of slow-failure that escapes attention until it is critical. Fitness function: `df -h /var/log/orchestrator/audit.log` alert if > 90%.
- Codex CLI adds a new attack surface: Codex's network sandbox defaults to blocked. If the orchestrator runs Codex without explicit network policy, Codex may silently fail on tasks requiring network access. This is a different security profile than Claude and requires its own fitness function.
- The VPS SSH hardening section is correct but is not connected to the orchestrator architecture. These are baseline hygiene items, not architectural decisions. Mixing them with orchestrator-specific security creates a document that is harder to maintain as the architecture evolves.

---

### Analysis E (LLM Architect / Erik)

**Agreement:** Agree — most architecturally precise analysis, fills the most critical spec gap

**Reasoning from evolutionary perspective:**

Peer G's discovery (GitHub issue #30348: cross-session message contamination between parallel CLI sessions on the same user account) is a show-stopper bug that none of the other peers addressed. This is not a theoretical risk — it is a documented, open, reproducible bug. Running two Claude sessions under the same user for two different projects risks context contamination: project A's Claude session may receive messages intended for project B.

The `CLAUDE_CODE_CONFIG_DIR` per-project environment variable is the minimal fix. It costs one line of code per Claude invocation. Its fitness function: an integration test that launches two Claude sessions concurrently, verifies that session A cannot access files written by session B. That test is automatable.

The Agent Teams decision (categorically exclude from this architecture) is one of the most valuable binary choices in the council. 13-16 GB RAM for Team mode on an 8GB VPS is not an engineering problem — it is an arithmetic problem. The fitness function: if anyone proposes using Agent Teams, the RAM consumption benchmark (#23883) is the automated gate.

The `cwd` discipline requirement — every Claude invocation must be `(cd "$PROJECT_DIR" && claude ...)` — is a constraint that should be protected by an automated check. Fitness function: `grep -n "claude -p\|claude --" scripts/vps/orchestrator.sh | grep -v "cd \$PROJECT_DIR"` should return zero results.

**Missed gaps:**

- The Multi-LLM question (Codex alongside Claude) receives no analysis. Codex CLI has a fundamentally different invocation pattern: `codex --full-auto --model gpt-5.3-codex <task>`. Codex also has a by-default network-blocked sandbox on Linux (Landlock + seccomp). These differences create new change vectors that Peer E does not address.
- No fitness function for the `CLAUDE_CODE_CONFIG_DIR` isolation. Proposing the fix without proposing the automated check is half an answer.
- The model routing recommendation (Haiku for triage, Opus for autopilot) is correct and important. But no fitness function protects this routing decision. A grep check on all Claude invocations should verify that no `--max-turns 30` run uses Haiku (would be under-powered) and no `--max-turns 5` triage run uses Opus (would be over-powered and expensive).

---

### Analysis G (Data Architect / Martin)

**Agreement:** Agree — most consequential structural recommendation, strongest data integrity argument

**Reasoning from evolutionary perspective:**

The GitHub issue #29158 (335 `.claude.json` corruption events in 7 days from concurrent writes) is exactly the kind of empirical evidence that drives evolutionary architectural decisions. The existing spec's `.orchestrator-state.json` overwrites the same file every cycle. With 5 projects and 60-second cycles, the write frequency is one order of magnitude above what caused the documented corruption. This is not a theoretical risk — it is a demonstrated failure mode at a lower write frequency than the proposed spec.

Peer G's SQLite proposal is the correct evolutionary response to this: state with high write frequency and concurrent readers must be managed by a system designed for that access pattern. SQLite WAL mode is exactly that system. The `BEGIN IMMEDIATE` transaction for slot acquisition converts what was a racy flock operation into an atomic database operation with crash recovery.

The strongest evolutionary insight from Peer G: SQLite's state can be reconstructed from `projects.json` if the DB corrupts. This is the escape hatch — the irreversibility of the decision is bounded. If SQLite turns out to be wrong, delete the DB and rebuild from config. This is a reversibility-aware design.

The inbox-item idempotency key (`.lock` marker file with Telegram `message_id`) addresses a failure mode no other peer noticed: bot crash between download and write leaves a partial state. The marker file pattern converts this from a silent duplicate to a detectable, recoverable condition.

**Missed gaps:**

- The SQLite migration path does not specify a fitness function for schema version verification. The `PRAGMA user_version` pattern is described but no automated check is proposed that prevents the orchestrator from starting with an out-of-date schema.
- The API usage ledger (`usage_ledger` table) is described but its fitness function is absent. A daily check that verifies the ledger is being written (non-zero rows in the last 24h) would catch a silent failure in cost tracking.
- No discussion of Codex API token costs. Adding Codex to the system means the `usage_ledger` needs a new `provider` field (anthropic vs openai). The schema as proposed does not accommodate this without a migration.
- The per-project inbox file retention (30-day audio purge) is correct but has no enforcement mechanism. Fitness function: daily cron that finds `ai/inbox/**/*.ogg` older than 30 days and deletes them.

---

### Analysis H (Domain Architect / Eric)

**Agreement:** Partially Agree — most intellectually rigorous, least immediately actionable

**Reasoning from evolutionary perspective:**

Peer H's fundamental finding is correct: the existing spec conflates mechanism with architecture. Listing components (flock, inotifywait, Telegram, projects.json) is not a domain model. The bounded context identification (Portfolio, Inbox, Pipeline, Notification) is a genuine architectural contribution.

The most evolutionarily significant insight: Telegram topics leaking into the domain model. The existing spec has `topic_id` baked into `projects.json`, into the routing logic, into the state file. This means that if Telegram changes its forum API or the founder switches to a GitHub Issues primary interface, the domain model itself must change. The Anti-Corruption Layer (ACL) pattern — translating `message_thread_id` to `RoutingKey` at the boundary — is exactly how to isolate this high-change external dependency.

From a change vector analysis: Telegram API is an external dependency with uncontrolled change frequency. The domain model must never depend on its specifics. Peer H is correct that this is a structural violation in the current spec.

However, from a practical evolutionary perspective, there is a gap between "the domain should be technology-agnostic" and "implement DDD bounded contexts in bash." The Portfolio, Inbox, Pipeline, Notification contexts Peer H identifies are real conceptual boundaries. But for a bash orchestrator managing 2-3 projects, enforcing these boundaries through code structure is impractical. The evolutionary answer: enforce the conceptual boundaries through naming conventions and function organization within the bash script, not through separate processes or modules.

The fitness function for Peer H's architectural principle: `grep "topic_id\|message_thread_id" src/domains/` should return zero results. Domain code must never reference Telegram concepts. This is automatable.

**Missed gaps:**

- No fitness function for any of the domain principles proposed. Peer H describes the ideal architecture in full DDD vocabulary but does not propose a single automated check that enforces any of it.
- The bounded context analysis does not address the Multi-LLM question. Which context owns the decision "should this task run on Claude or Codex?" The answer is Pipeline context (it owns the execution decision), but Peer H's Pipeline context model does not include a `Provider` concept.
- The `project` disambiguation (project means different things in different contexts) is correct but the fix — "define project precisely per context" — is impractical in a single-process bash orchestrator. The practical fix: use distinct variable names. `$PROJECT_ID` for Portfolio context, `$ROUTING_KEY` for Inbox context, `$PIPELINE_PHASE` for Pipeline context. Name things after the concept they represent.
- No analysis of what happens to the domain model when Codex is added. Codex processes in the Pipeline context have different phase semantics: Codex does not read CLAUDE.md, does not use DLD skills, and uses different `--max-turns` equivalents. The Pipeline context's ubiquitous language must accommodate a heterogeneous executor set.

---

## Ranking

**Best Analysis:** Analysis A (Charity — Operations)

**Reason:** Peer A found the most consequential factual correction (RAM 10x understated), provided the most complete production-grade implementation (RAM-aware semaphore, systemd cgroups, three-layer heartbeat, structured JSON logging), and directly answered the architectural questions with automatable fitness functions. Every recommendation in Peer A's analysis can be verified by a machine. That is the standard I hold all architecture to. When an architect cannot automate the check, the architecture will drift.

**Second best:** Analysis G (Martin — Data Architecture). The corruption evidence from GitHub #29158 + SQLite WAL recommendation is structurally decisive. SQLite is not a preference — it is the correct answer to a documented failure mode.

**Worst Analysis:** Analysis H (Eric — Domain Architecture)

**Reason:** Peer H produced the most academically rigorous analysis and the least practically actionable one. The bounded context vocabulary is correct in a greenfield enterprise system. In a bash orchestrator managing 2-3 projects for a solo founder, enforcing DDD bounded contexts is an engineering exercise without a revenue payoff. More critically, Peer H proposed zero fitness functions. Beautiful domain models that cannot be automatically verified will not survive contact with the real codebase. Martin Fowler's own writing on fitness functions is explicit: the architecture will drift if the checks are not automated. Peer H knows the domain concepts but does not connect them to the evolutionary principle.

---

## Founder's New Questions — Evolutionary Analysis

### 1. Multi-LLM (Claude Code + ChatGPT Codex GPT-5.4): How does adding Codex change the evolutionary path? What fitness functions need updating?

*Thinks about the change vectors this introduces.*

Adding Codex creates a new high-change area: provider-specific CLI behavior. Claude CLI and Codex CLI are different invocation patterns, different sandbox semantics, different memory profiles, and different auth mechanisms. Each is externally controlled by a different vendor with its own release cadence.

**Change vectors introduced by Codex:**

| Component | Change Frequency | Change Driver | Isolation Strategy |
|-----------|-----------------|---------------|-------------------|
| Codex CLI flags (`--full-auto`, `--sandbox workspace-write`) | Monthly | OpenAI releases | Wrap in `codex-runner.sh`, single change point |
| Codex network sandbox (Landlock + seccomp on Linux) | Uncontrolled | Security policy | Never assume network access from Codex; always test with `--sandbox workspace-write` |
| Codex model names (GPT-5.3-Codex, GPT-5.4-Codex) | Quarterly | OpenAI releases | Model name in `projects.json` per task type, not hardcoded in runner |
| OpenAI API auth (separate from Anthropic) | Stable | External | Separate `.env` key per project, `OPENAI_API_KEY` distinct from `ANTHROPIC_API_KEY` |
| RAM profile per Codex session | Unknown | Different architecture | Measure empirically, start with same RAM floor check as Claude |

**Critical design decision: task routing to provider**

The orchestrator must decide: should the same project use both Claude and Codex on different tasks? Or is each project assigned to one provider?

The evolutionarily conservative answer: start with per-project provider assignment. Add `"provider": "claude"` or `"provider": "codex"` to `projects.json`. The `claude-runner.sh` / `codex-runner.sh` abstraction means the orchestrator loop does not change — only the runner script changes per provider.

The more powerful answer (defer until proven needed): per-task provider routing. "Use Codex for terminal-benchmark tasks (77.3% vs Claude's 65.4%), use Claude for architectural reasoning (Claude wins SWE-bench Pro 59% vs Codex 56.8%)." This requires a task-type classification step before each run. Implement this only when you have 5+ projects and empirical data on which provider performs better for which task type.

**Fitness functions that need updating:**

| Existing Fitness Function | How It Changes With Codex |
|--------------------------|--------------------------|
| Semaphore slot count vs `max_concurrent_claude` | Must become `max_concurrent_llm` counting both Claude AND Codex processes. `pgrep -c "claude\|codex"` in the check. |
| RAM floor check before slot acquisition | Codex RAM profile is unknown. Start with same 3GB floor as Claude, measure actual usage, adjust. Add a `provider`-aware RAM floor in config. |
| Projects.json schema validation | Add `provider` field as required. Add `codex_model` field as optional (default: `gpt-5.4-codex`). Schema check must validate `provider IN ["claude", "codex"]`. |
| Claude CLI version pinning | Add Codex CLI version pinning separately. `codex --version` output to a lock file. CI check: current version matches pinned version. |
| `cwd` discipline check | Codex does NOT load CLAUDE.md from `cwd`. Codex uses its own context mechanism. The `cwd` discipline check must differentiate: for Claude sessions, verify `CLAUDE.md` is in cwd; for Codex sessions, verify the project prompt file is passed explicitly. |

**New fitness functions required for Codex:**

1. **Codex network sandbox verification:** Before each Codex run, verify `--sandbox workspace-write` is set. Fitness function: `grep -n "codex" scripts/vps/codex-runner.sh | grep -v "sandbox workspace-write"` returns zero.

2. **Cross-provider context isolation:** After any Codex run, verify that Codex did not write to `$HOME/.claude/` directories (it should not, but worth verifying). Fitness function: `find ~/.claude -newer "$CODEX_START_TIMESTAMP" -type f | wc -l` should equal zero.

3. **Usage ledger provider field:** Every `usage_ledger` INSERT must include a `provider` field. Fitness function: `SELECT COUNT(*) FROM usage_ledger WHERE provider IS NULL` should equal zero after schema migration.

**The escape hatch question:** If Codex CLI changes radically (see Question 3 below), the escape hatch is the same as for Claude: `codex-runner.sh`. All Codex invocations go through this single wrapper. The wrapper can be rewritten to call the new API (REST, SDK, MCP) without touching the orchestrator loop, the Telegram bot, or `projects.json`. This is a 30-minute investment that preserves architectural options for 18 months.

**Abstraction layer I recommend:**

```bash
# /scripts/vps/run-agent.sh — provider-agnostic entry point
run_agent() {
    local project_dir="$1"
    local task="$2"
    local provider="$3"  # claude | codex

    case "$provider" in
        claude) source scripts/vps/claude-runner.sh; run_claude "$project_dir" "$task" ;;
        codex)  source scripts/vps/codex-runner.sh; run_codex "$project_dir" "$task" ;;
        *) log_error "Unknown provider: $provider"; exit 1 ;;
    esac
}
```

`run-agent.sh` is the ONLY change point when adding a third provider (Gemini CLI, Cursor, etc.). The orchestrator calls `run_agent`, never `claude` or `codex` directly.

---

### 2. Same VPS as Docker containers: Migration path from current setup to orchestrated

*Applying Strangler Fig at the infrastructure level.*

The founder already runs Docker containers for projects on the VPS. The orchestrator must coexist with those containers, not compete with them. This is a resource contention problem with a clear evolutionary path.

**The coexistence math (Hetzner CX41, 16GB):**

| Component | RAM estimate |
|-----------|-------------|
| OS + network | 0.5 GB |
| Docker daemon | 0.3 GB |
| N project containers (typical web apps) | 0.5-2 GB each |
| 3 project containers active | 1.5-6 GB |
| Orchestrator (bash process) | 0.05 GB |
| Telegram bot (Python) | 0.1 GB |
| 1x Claude session (realistic peak) | 3-8 GB |
| Monitoring stack (Loki + Promtail) | 0.4 GB |
| **Total at peak** | **~12-16 GB** |

On a 16GB VPS: coexistence is possible with `MAX_CONCURRENT=1` (one Claude session at a time). On an 8GB VPS: not viable with Docker containers also running. Peer A's recommendation of 16GB minimum is validated here — it is not just about Claude, it is about Docker + Claude simultaneously.

**Migration path: Strangler Fig applied to the VPS topology**

**Phase 0 — Inventory (Day 1, zero risk):**
Run the orchestrator alongside existing Docker infrastructure without touching containers. The orchestrator only manages the host-level Claude CLI invocations. Docker containers continue running as before. Establish baseline RAM usage measurements before the orchestrator takes any action.

Fitness gate: `free -h` with all containers running + orchestrator running (no Claude active) shows >= 4GB free. If not, resize VPS before proceeding.

**Phase 1 — Add RAM-aware governor (Day 2-3):**
Before each Claude invocation, the orchestrator checks `MemAvailable` from `/proc/meminfo`. If free RAM < 3GB, skip the cycle and alert. This prevents the orchestrator from OOM-killing a Docker container that a user is actively using.

The key insight: Docker container RAM is not always fully consumed. A stopped container uses near-zero RAM. An idle container may use a fraction of its limit. The governor should check actual available memory, not theoretical maximum consumption.

Fitness gate: Simulate peak load (start all Docker containers, launch Claude session) and verify the RAM floor check fires correctly before the RAM is exhausted.

**Phase 2 — Cgroup isolation (Day 4-5):**
Use systemd cgroups to assign the orchestrator service a RAM slice. Docker already uses cgroups for container limits. The orchestrator needs its own slice:

```ini
# /etc/systemd/system/orchestrator.service
MemoryMax=10G     # leaves remainder for Docker containers + OS
MemorySwapMax=0   # no swap (swap kills performance on AI workloads)
```

This converts resource contention from a runtime surprise to a bounded, predictable constraint. If Claude leaks, it crashes within its cgroup, not the Docker containers.

Fitness gate: Verify with `systemd-cgls` that the orchestrator service and Docker service are in separate cgroups with independent limits.

**Phase 3 — Add second project (Day 6+):**
Only after Phase 1 and 2 are stable. Add the second project to `projects.json`. Verify that the RAM governor correctly prevents concurrent Claude sessions when Docker containers are consuming memory.

**The topology question: same VPS vs dedicated orchestrator VPS**

Same VPS is correct for Phase 1 (0-3 projects). The cost savings ($20-40/month) are meaningful at this stage. The risk is bounded by the RAM governor and cgroup limits.

Dedicated orchestrator VPS becomes worth considering at 5+ active projects where simultaneous Claude sessions are common. At that point, separating the orchestrator onto a $10-15/month lightweight VPS (2GB RAM for orchestrator itself) and keeping the $40/month beefy VPS for Claude sessions is a viable topology. The orchestrator becomes a thin dispatcher that SSH-executes Claude on the project VPS.

**Decision deferral principle:** Do not add the second VPS until the `cycle_duration` fitness function consistently fires (cycle > 180 seconds), indicating the single VPS is unable to process all projects within the SLO window. That is the objective, automatable signal to upgrade topology.

---

### 3. Escape hatch if Codex or Claude CLI changes radically

*This is the reversibility question. Let me apply the framework directly.*

**Current irreversible dependencies:**

| Dependency | Cost to reverse | Escape hatch |
|-----------|----------------|--------------|
| Claude CLI invocation syntax | Medium (1-2 days) | `claude-runner.sh` — one file changes |
| Codex CLI invocation syntax | Medium (1-2 days) | `codex-runner.sh` — one file changes |
| Telegram Bot API (topic routing) | High (1 week) | `TelegramAdapter` class — swap implementation, project routing stays |
| `projects.json` schema | Low (backward-compatible additions) | `schema_version` field enables migration |
| `ai/inbox/` directory protocol | High (all DLD projects depend on it) | Treat as stable API, never change without explicit version bump |

**The architectural escape hatch for CLI radical change has three layers:**

**Layer 1: Provider abstraction (30-minute investment)**
`run-agent.sh` calls provider-specific runners. If Claude switches from CLI to an SDK or MCP server, only `claude-runner.sh` changes. The orchestrator loop, Telegram bot, and project config are unaffected.

**Layer 2: Context protocol abstraction (2-hour investment)**
The primary value of CLAUDE.md as context injection is that it is file-based — Claude reads it from the filesystem. If Anthropic changed this to a network-based context API, the escape hatch is: write the context to a file, have the runner pass it via `--system-prompt $(cat .claude/system.md)`. The context content stays the same; only the delivery mechanism changes.

**Layer 3: Output format abstraction (30-minute investment)**
Both Claude and Codex support `--output-format json`. Parse the JSON output in the runner, normalize to a standard schema, and return to the orchestrator. If either CLI changes its output format, only the parser in the runner changes.

**What is NOT protected by these escape hatches:**

- If Anthropic or OpenAI discontinues the CLI entirely and moves to browser-only or API-only: the orchestrator becomes a shell that calls REST APIs directly. This is a 1-2 week migration, not an afternoon. The mitigation is the MCP approach (Peer G found WCP — Work Context Protocol in February 2026): design the context injection to work via MCP server, which is more stable than CLI flags.

- If the AI coding agent market consolidates around a single standard (like GitHub's Spec Kit becoming dominant): the escape hatch is the `run-agent.sh` abstraction. If Spec Kit becomes the standard, `claude-runner.sh` becomes `spec-kit-runner.sh`.

**Concrete fitness function for escape hatch health:**

```bash
#!/bin/bash
# /scripts/vps/checks/provider-compatibility-check.sh
# Run weekly via cron

# Claude: verify CLI responds and outputs expected format
CLAUDE_VERSION=$(claude --version 2>/dev/null | head -1)
if [ -z "$CLAUDE_VERSION" ]; then
    notify.sh "ALERT: Claude CLI not responding — escape hatch needed"
    exit 1
fi

# Codex: verify CLI responds
CODEX_VERSION=$(codex --version 2>/dev/null | head -1)
if [ -z "$CODEX_VERSION" ]; then
    notify.sh "ALERT: Codex CLI not responding — escape hatch needed"
    exit 1
fi

# Verify pinned versions match
CLAUDE_PINNED=$(cat /scripts/vps/.claude-version-pin)
CODEX_PINNED=$(cat /scripts/vps/.codex-version-pin)

if [ "$CLAUDE_VERSION" != "$CLAUDE_PINNED" ]; then
    notify.sh "WARN: Claude CLI version changed ($CLAUDE_PINNED → $CLAUDE_VERSION). Test before accepting."
fi

echo "OK: Claude $CLAUDE_VERSION, Codex $CODEX_VERSION"
```

This check runs weekly and fires before the version mismatch breaks the orchestrator in production.

---

## Revised Position

**Revised Verdict:** Changed in two significant ways

**Change 1: SQLite for state is non-negotiable**

Before reading Peer G, my position was that `.orchestrator-state.json` with atomic writes (write-rename) was sufficient. Peer G's evidence from GitHub #29158 (335 corruptions at a lower write frequency than the proposed spec) changes this. The existing research I had cited (crash-safe JSON patterns) addresses single-writer scenarios. The orchestrator is multi-writer: the daemon writes, the bot reads, and on VPS reboot the orchestrator writes on restart. Under those conditions, SQLite WAL is the correct answer, not a cleverer JSON write pattern. My original position was wrong. I accept the correction.

**Change 2: RAM floor check must be a gate, not a fitness function**

Before reading Peer A, I had proposed the RAM check as a monitoring alert. Peer A correctly positions it as an admission gate: do not acquire the semaphore slot if RAM is below the floor. This converts monitoring into architecture. The system cannot get into a bad state because the bad state is prevented, not observed. That is a stronger evolutionary guarantee than a cron-based alert that fires after the OOM kill.

**Final Evolutionary Recommendation:**

Build the orchestrator in this sequence, with fitness functions enforced at each phase gate:

1. Start with Peer C's boring stack (Pueue + systemd + Python Telegram bot). This is the 3-day version.
2. Add Peer A's RAM-aware admission gate and three-layer heartbeat. This is the production-grade version.
3. Add Peer G's SQLite for state. Replace Pueue's native state with the orchestrator DB (Pueue handles job state; SQLite handles project state). This is the crash-safe version.
4. Add Peer D's P0 security items (user-level auth, `--max-turns`, local Whisper). This makes it safe to connect to real projects.
5. Add the provider abstraction layer (`run-agent.sh` + `claude-runner.sh` + `codex-runner.sh`) before adding Codex. This makes the Multi-LLM requirement a configuration change, not a rewrite.

The orchestrator is not done when the code is written. It is done when the fitness function suite is green and the founder can debug any failure at 3am from a Telegram message alone.

---

## Fitness Function Synthesis — Complete Suite

All fitness functions from my original research, updated with peer findings:

| # | Property | Automated Check | Trigger | Owner |
|---|----------|----------------|---------|-------|
| 1 | Inbox pickup SLO | `find ai/inbox -mmin +5 -type f \| wc -l > 0` | Cron every 5 min, active hours | Ops |
| 2 | RAM floor before launch | `MemAvailable >= 3GB` in `acquire_claude_slot()` | Every Claude/Codex invocation | Ops |
| 3 | Concurrent LLM count | `pgrep -c "claude\|codex" <= max_concurrent_llm` | Cron every 2 min | Ops |
| 4 | `projects.json` schema | Required fields present + paths exist + provider valid | Git pre-commit hook | Config |
| 5 | State DB integrity | SQLite `PRAGMA integrity_check` returns `ok` | Daily cron | Data |
| 6 | Orchestrator liveness | Heartbeat gap <= 120s in state DB | Cron every 1 min (Healthchecks.io) | Ops |
| 7 | `cwd` discipline (Claude) | `grep "claude -p\|claude --" orchestrator.sh \| grep -v "cd \$PROJECT_DIR"` = 0 | CI commit check | Dev |
| 8 | Provider abstraction | `grep -r "^claude \|^codex " scripts/vps/orchestrator.sh` = 0 | CI commit check | Dev |
| 9 | No domain term leaks | `grep "topic_id\|message_thread_id" src/domains/` = 0 | CI commit check | Domain |
| 10 | Prompt injection defense | All inbox-processing scripts use XML-tagged prompts | Code review + grep check | Security |
| 11 | User auth whitelist | `grep "from_user.id" scripts/vps/telegram-bot.py` exists | CI commit check | Security |
| 12 | Claude CLI version pin | `claude --version` matches `.claude-version-pin` | Weekly cron | Ops |
| 13 | Codex CLI version pin | `codex --version` matches `.codex-version-pin` | Weekly cron | Ops |
| 14 | Audio file retention | `find ai/inbox -name "*.ogg" -mtime +30` = 0 | Daily cron | Security |
| 15 | Orchestrator LOC limit | `wc -l scripts/vps/orchestrator.sh < 400` | CI commit check | Dev |

**Missing fitness functions (decisions without automated protection):**
- No check that GitHub repo URLs in `projects.json` are valid (if `github_repo` field is set)
- No check that `CLAUDE_CODE_CONFIG_DIR` per-project dirs are not shared between projects
- No check that Codex does not write to `~/.claude/` directories

---

## References

- [Neal Ford — Building Evolutionary Architectures](https://evolutionaryarchitecture.com/)
- [Martin Fowler — Fitness Functions](https://martinfowler.com/bliki/FitnessFunction.html)
- [Claude Code #29158 — ~/.claude.json corruption (335 events)](https://github.com/anthropics/claude-code/issues/29158)
- [Claude Code #30348 — Cross-session contamination](https://github.com/anthropics/claude-code/issues/30348)
- [Claude Code #29576 — Memory regression v2.1.62](https://github.com/anthropics/claude-code/issues/29576)
- [Codex CLI vs Claude Code 2026 — Benchmarks](https://smartscope.blog/en/generative-ai/chatgpt/codex-vs-claude-code-2026-benchmark/)
- [Codex CLI Sandbox Flags Explained](https://www.vincentschmalbach.com/how-codex-cli-flags-actually-work-full-auto-sandbox-and-bypass/)
- [Building Nexus-Agents: Multi-Model Orchestration](https://williamzujkowski.github.io/posts/building-nexus-agents-what-i-learned-creating-a-multi-model-ai-orchestration-system/)
- [Trail of Bits — Prompt Injection to RCE](https://blog.trailofbits.com/2025/10/22/prompt-injection-to-rce-in-ai-agents/)
- [Martin Fowler — Strangler Fig Application](https://martinfowler.com/bliki/StranglerFigApplication.html)
