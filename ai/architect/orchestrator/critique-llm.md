# LLM Systems Architecture Cross-Critique

**Persona:** Erik (LLM Architect)
**Phase:** 2 — Peer Review
**Date:** 2026-03-10

---

## Pre-Review: Multi-LLM Research (PRIMARY NEW QUESTION)

Before reviewing peers, I need to address the founder's new Multi-LLM question since none of the peers covered it in Phase 1 (it arrived as a Founder Addendum). I researched this specifically for this critique.

### How Codex CLI Works

**Invocation and auth:**

```bash
# Non-interactive (headless) mode — the key for orchestration
OPENAI_API_KEY="sk-..." \
  codex exec "fix the billing webhook retry logic" \
  --sandbox workspace-write \
  --json

# Equivalent to Claude Code's headless mode:
ANTHROPIC_API_KEY="sk-..." \
  claude -p "fix the billing webhook retry logic" \
  --output-format json
```

Auth is via `OPENAI_API_KEY` env var (no interactive login needed for orchestration). The `codex exec` command is the headless equivalent of Claude Code's `-p` flag. It was added specifically because the community requested it for orchestration use cases (GitHub Issue #4219, closed as implemented).

Output: `stdout` = final agent message, `stderr` = streaming progress. With `--json` flag, stdout becomes JSON Lines (JSONL) — machine-readable, parseable by orchestrator.

**Context injection — AGENTS.md (the CLAUDE.md equivalent):**

Codex has `AGENTS.md` — functionally identical to `CLAUDE.md`. Discovery chain:
1. Global: `~/.codex/AGENTS.md` (or `AGENTS.override.md`)
2. Project: walk from git root to `cwd`, read one `AGENTS.md` per directory
3. Merge: concatenated top-down, deeper files override shallower

This is the SAME mechanism as CLAUDE.md. The orchestrator just needs to run `codex exec` from the project root (`cwd = project_dir`) and Codex auto-loads `AGENTS.md`. **No separate context injection needed.**

**Resource profile on Linux/VPS:**

Codex CLI is written in Rust (rewritten from TypeScript in late 2025). Base process is significantly lighter than Claude Code's Node.js process:
- Codex baseline: ~80-150 MB RSS (Rust binary, no JVM/V8 overhead)
- Claude Code baseline: ~400-800 MB RSS (Node.js + Electron dependencies)

However, Codex has a documented memory leak in non-interactive mode (GitHub #9345, #13314 — still open as of March 2026). In repeated `codex exec` invocations, memory is not fully reclaimed. Pattern of use matters: single long-running session vs. many short invocations.

**For an orchestrator running `codex exec` per task:** Memory accumulates until process exits. Each invocation should be a separate process (not a persistent daemon). This is fine — same pattern as Claude Code.

**Sandbox model:**

```bash
# Default: read-only sandbox
codex exec "analyze the code"

# Allow writes (needed for autopilot-equivalent):
codex exec --sandbox workspace-write "implement FTR-042"
# OR
codex exec --full-auto "implement FTR-042"  # equivalent to --dangerously-skip-permissions in Claude

# Run in Docker for hard isolation:
# Codex has a pre-built Docker image (Diatonic-AI/codex-cli-docker-mcp)
docker run -e OPENAI_API_KEY=$KEY codex-cli codex exec "..."
```

### Can Claude and Codex Work on the SAME Project?

**Answer: Yes, with isolation requirements.**

Both tools use the same filesystem. They can read and modify the same project files. The orchestrator must ensure they do NOT run concurrently on the same project (file conflicts, git conflicts). This means the semaphore must be per-project, not just per-slot:

```
Shared semaphore pool:
  - Slot 1: [project=saas-app, engine=claude]
  - Slot 2: [project=side-project, engine=codex]

INVALID:
  - Slot 1: [project=saas-app, engine=claude]
  - Slot 2: [project=saas-app, engine=codex]  ← CONFLICT
```

Project-level mutex (not just global count) is required for safe multi-LLM on the same project.

**The `agent-mux` open-source project** (nickoak.com, February 2026) solves this exact problem: cross-engine subagent routing between Claude Code and Codex CLI. One JSON contract, any engine. This is the industry-validated pattern for Claude + Codex interop.

### Task Routing Strategy: Claude vs Codex

Based on the research (Scopir, February 2026; 365i January 2026; agent-mux design doc):

| Task Type | Recommended Engine | Why |
|-----------|-------------------|-----|
| Planning, architecture, `/spark` | Claude (Opus) | Better orchestration, prompt mastery, multi-step reasoning |
| Raw code implementation | Codex (GPT-5.4) | "Surgical code changes", precise executor at high reasoning |
| Code review / audit | Codex (GPT-5.4 xhigh reasoning) | Reads code like a lawyer reads contracts |
| QA, test writing | Either (Codex slightly faster/cheaper) | Similar quality |
| Inbox triage | Claude Haiku | Lower cost, Anthropic ecosystem |
| Cross-file refactoring | Claude | Better at understanding broader context |

**Two routing models to choose from:**

**Option A — Task-level routing** (within same project):
```
Orchestrator decides per-task which engine:
  - TECH-055 (implement function) → codex exec
  - ARCH-012 (redesign module) → claude -p "/architect"
  - FTR-042 (full feature) → claude -p "/autopilot"
```

**Option B — Project-level routing** (different projects get different engines):
```
projects.json:
  { "name": "saas-app", "engine": "claude", ... }
  { "name": "side-project", "engine": "codex", ... }
```

**My recommendation: Start with Option B (project-level routing).**

Reasons:
1. AGENTS.md and CLAUDE.md have different syntax/conventions. Maintaining both per project doubles the context maintenance burden.
2. Project-level routing is simpler to orchestrate — the semaphore model stays the same, just substituting `claude` with `codex exec` in the runner.
3. Task-level routing requires the orchestrator to classify tasks before routing — adds LLM cost to triage and risk of misrouting.
4. Once the system is stable on Option B, you can graduate to task-level routing within a single project.

### Claude Output → Codex Input (and vice versa)

**Yes, with file IPC.**

This is the ADR-007 pattern applied cross-engine:
```
Claude generates spec → writes to ai/features/FTR-042.md
Orchestrator reads completion signal (file gate)
Orchestrator invokes: codex exec "implement the spec in ai/features/FTR-042.md"
Codex reads spec, implements code
```

Neither engine needs to know about the other. The file system is the protocol. This is already how the DLD pattern works internally (orchestrator → claude → files → next claude call). The same pattern extends to cross-engine.

**What does NOT work:** Piping Claude stdout directly to Codex stdin. Both tools produce verbose streaming output with progress indicators mixed into content. JSON output mode (`--output-format json` / `--json`) helps but the schemas are different. File IPC is the clean pattern.

### Concurrency: Separate Semaphore Pools or Shared?

**Recommendation: Shared pool, separate slots by engine type.**

```json
{
  "max_concurrent_claude": 1,
  "max_concurrent_codex": 1,
  "max_concurrent_total": 2
}
```

Why separate limits per engine:
- Claude and Codex have different RAM profiles (Claude: 800MB-3GB; Codex: 150MB-500MB)
- You can safely run 1 Claude + 1 Codex concurrently on 8GB VPS
- You cannot safely run 2 Claude sessions on 8GB VPS

Why shared total limit:
- Prevents GPU/API rate limit exhaustion
- Keeps orchestrator logic simple

**SQLite `claude_slots` table** (from peer Martin's proposal) should be extended:
```sql
CREATE TABLE agent_slots (
    slot_id         INTEGER PRIMARY KEY,
    engine          TEXT CHECK (engine IN ('claude', 'codex')),
    project_id      TEXT,
    acquired_at     TIMESTAMPTZ,
    pid             INTEGER
);
INSERT INTO agent_slots (slot_id, engine) VALUES (1, 'claude'), (2, 'codex');
```

This replaces the generic slot table with an engine-aware one.

### Does Codex Run in Docker or Bare Metal?

**Both are supported. Docker is strongly recommended for Codex specifically.**

Unlike Claude Code which has no official Docker image, Codex has:
- Official documentation for Docker deployment (`Diatonic-AI/codex-cli-docker-mcp`)
- `OPENAI_API_KEY` injected via Docker secrets (no file leakage)
- Built-in sandbox model (`--sandbox workspace-write`) that maps cleanly to Docker volume mounts
- The `--dangerously-bypass-approvals-and-sandbox` flag is explicitly documented for "isolated CI runner or container" use

**Practical recommendation for this orchestrator:**

Given that the founder already runs Docker containers for projects on the VPS:

```
VPS Architecture:
  Orchestrator (bare metal bash process)
    ├── Claude Code sessions: bare metal, per-project user isolation (Bruce's recommendation)
    └── Codex sessions: Docker containers, one per invocation
        └── docker run --rm \
              -v /home/projects/saas-app:/workspace \
              -e OPENAI_API_KEY=$KEY \
              codex-cli \
              codex exec --sandbox workspace-write "..."
```

This gives:
- Claude: existing bare metal setup, per-user isolation as Bruce recommends
- Codex: Docker isolation at OS level, no user management overhead
- Project directory mounted as Docker volume — Codex reads/writes the real project files

**RAM impact of Docker Codex:**
- Docker daemon overhead: ~200MB (shared across containers)
- Codex CLI process inside container: ~150-400MB
- Total per Codex invocation: ~200-400MB extra vs bare metal

This is substantially less than a Claude session. On 8GB VPS:
- 1 Claude session: 800MB-3GB
- 1 Codex Docker session: 150-400MB
- OS + orchestrator: 500MB
- Viable to run 1 Claude + 1 Codex concurrently

**Infrastructure Topology (same VPS answer):**

Running on the same VPS as project Docker containers is viable IF:
- RAM budget accounts for project containers (each likely 200-500MB for Node/Python apps)
- Claude is limited to 1 concurrent session (not 2) when Docker containers are running
- Total VPS RAM should be 16GB minimum (same as Charity's ops recommendation)

Cost comparison:
- 1 VPS (16GB): Hetzner CX41 ~€15.90/mo — everything on one machine
- 2 VPS (1x8GB orchestrator + 1x8GB projects): ~€16-20/mo — same cost, better isolation

The single-VPS approach is reasonable at 2-5 projects. Split VPS if any project container requires guaranteed RAM or if Claude regularly OOMs.

### Cost Comparison: Claude vs Codex per Task Type

| Task | Model | Typical Tokens | Cost per Task |
|------|-------|----------------|---------------|
| Inbox triage | Claude Haiku | 1K in / 200 out | ~$0.001 |
| Feature spec (/spark) | Claude Opus | 20K in / 5K out | ~$0.22 |
| Feature implementation (autopilot) | Claude Opus | 50K in / 15K out | ~$0.63 |
| Feature implementation | GPT-5.4 Codex | ~50K in / 15K out | ~$0.75-1.20 |
| Code review | GPT-5.4 xhigh | 10K in / 2K out | ~$0.15-0.30 |

**GPT-5.4 pricing:** ~$10/M input, $30/M output (approximate, check current pricing). Claude Opus: $5/M input, $25/M output.

For raw implementation, Codex is slightly MORE expensive than Claude Opus at current pricing. The value is not cost — it's quality on specific task types. Use Codex for the tasks where it genuinely outperforms Claude, not as a cost optimization.

---

## Peer Analysis Reviews

### Analysis A (Ops / Charity)

**Agreement:** Agree

**Reasoning from LLM agent perspective:**

Peer A is the most credible source of production RAM data. The correction of "200-500 MB per Claude process" to "2-16 GB in extended runs" is critical. This matches my own research (GitHub issues #29576, #4953, #23883). Every other peer that accepts the 200-500 MB figure is building on a false foundation.

The RAM-aware semaphore (`acquire_claude_slot` with `MemAvailable` check) is exactly the right mechanism. The pattern:
```bash
free_ram_kb=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
```
is the correct primitive. No LLM cost, no guessing.

The three-layer dead man's switch (orchestrator heartbeat + per-project check + Telegram bot liveness) is well-designed. The specific insight to call the heartbeat at END of loop (not start) is sophisticated — it catches hung loops that would otherwise look healthy.

The `KillMode=control-group` in systemd unit is the correct answer to orphan Claude processes. This is not just an ops nice-to-have — it prevents RAM leaks from accumulating over hours.

**Missed gaps:**
- No discussion of Multi-LLM (Codex) RAM profile. Codex baseline is ~150-400 MB vs Claude's 800 MB+. This changes the RAM budget calculation significantly.
- VPS sizing recommendation (16GB minimum) assumes Claude-only. With Docker containers for projects running concurrently, 16GB is still the floor but the margin is tighter.
- No mention of per-engine concurrency limits. The semaphore needs to be engine-aware, not just global count.

---

### Analysis B (Devil's Advocate / Fred)

**Agreement:** Partially Agree

**Reasoning from LLM agent perspective:**

Peer B asks the right kill question: "why are we building this at all right now?" The anti-pattern identification (anti-pattern #2: "This helps you, not your customers") is correct and should be the loudest voice in the room.

The tmux + two terminal windows alternative for 2-3 projects is genuinely viable for the attended-founder use case. The spec never explicitly states whether this is for unattended 3am execution or attended management.

The Pueue recommendation is correct for the concurrency management problem. flock has the documented failure modes Peer B identifies.

However, Peer B's critique loses credibility in the sections that feel like ideological purity rather than pragmatic analysis:

- Calling the bash orchestrator a "load-bearing shell script" anti-pattern is valid, but then recommending "a 50-line Python script that reads projects.json and calls Pueue" — that is still custom orchestration code. The complexity doesn't disappear, it moves.
- The five-state-stores inconsistency claim overstates the problem. `message_thread_id` in Telegram is not a "state store" — it is a routing key. That is not equivalent to `.orchestrator-state.json`.
- No mention of the Multi-LLM question despite it being explicitly listed as a new primary question.

From an LLM agent perspective: Peer B correctly identifies that the API contract (what commands can an agent execute? what is the interface?) is undefined. This is my core concern — if an agent needs to interact with the orchestrator, the interface must be self-describing.

**Missed gaps:**
- Zero coverage of Multi-LLM orchestration, Codex CLI, or cross-engine coordination.
- No analysis of what the orchestrator's API surface looks like from an agent's perspective (kill question for my role).
- The "why build this" critique is valid but does not help the council decide HOW to build it when the decision to build has already been made.

---

### Analysis C (Domain / Eric)

**Agreement:** Agree

**Reasoning from LLM agent perspective:**

Peer C's kill question answer is the most important sentence in any peer analysis: the business-language description test. Forcing the domain out of implementation language reveals four real contexts: Portfolio, Inbox, Pipeline, Notification.

The "orchestrator is an APPLICATION SERVICE, not a domain concept" is precisely correct from an LLM systems perspective. This directly answers my kill question for Phase 7: an agent can understand the system from tool descriptions IF those tool descriptions map to domain concepts (Portfolio.activate, Pipeline.run_phase) rather than technical primitives (claude -p, flock, message_thread_id).

The Anti-Corruption Layer (ACL) pattern for Telegram is the right architecture. `topic_id → RoutingKey → Project.id` — the domain never sees Telegram concepts. This means if Codex replaces Claude in some projects, the Pipeline context handles it transparently (the engine is a Pipeline implementation detail).

The Steward Agent pattern (one agent per bounded context) maps exactly to how I would design the LLM layer:
- Portfolio Steward: handles scheduling decisions, concurrency budget
- Pipeline Steward: handles DLD lifecycle per project
- Inbox Steward: handles classification and routing

However, Peer C stays entirely in the domain modeling space and does not cross into practical implementation. The bounded contexts are clean but there is no guidance on how they map to actual Claude CLI invocations.

**Missed gaps:**
- No discussion of how bounded contexts map to agent context windows. Each context should have its own CLAUDE.md section — the context budget implications matter.
- No treatment of Multi-LLM. The ACL pattern extends naturally to this: `ClaudeAdapter` and `CodexAdapter` both implement `ExecutionAdapter`. This is worth calling out.
- The `topic_id` leak critique is valid but no migration path is given. Projects already in production have `topic_id` baked in.

---

### Analysis D (DX / Dan)

**Agreement:** Partially Agree

**Reasoning from LLM agent perspective:**

Peer D's Pueue recommendation is the strongest practical suggestion in all peer analyses. The feature comparison table (Pueue vs Task Spooler vs flock) is definitive. Pueue eliminates ~300 LOC of custom bash and makes the orchestrator's state introspectable without SSH.

The `pueue status --json` insight is valuable for my role: machine-readable state means an agent can query orchestrator status without reading implementation. This directly improves the agent-friendliness of the system.

The 3-day build plan is realistic and targets the right scope. The explicit time-box ("if it takes longer, something is over-engineered") is the right discipline for tooling that does not generate revenue.

The GitHub Issues deferral is correct. For v1, file-based inbox + Telegram routing is sufficient. The `github_repo` optional field in `projects.json` is the right escape hatch.

However, Peer D does not address the Multi-LLM question at all — a significant omission given it is listed as a primary new question. Pueue handles this naturally: `pueue group add saas-app-codex` as a separate group from `pueue group add saas-app-claude`, with separate parallelism limits matching each engine's RAM profile.

**Missed gaps:**
- Multi-LLM is completely absent. Pueue's group model would handle Claude and Codex as separate groups with different `pueue parallel --group` limits.
- No discussion of how Pueue's job logs relate to agent context. The `pueue log <id>` output needs to be agent-readable, not just human-readable.
- The "don't make Telegram a pseudo-terminal" warning is correct but needs a concrete enforcement mechanism. Recommend a command allowlist in the bot handler.

---

### Analysis F (Security / Bruce)

**Agreement:** Partially Agree

**Reasoning from LLM agent perspective:**

The STRIDE threat model is correctly prioritized. The `from_user.id` whitelist (not group membership) is the right fix — simple, two-hour implementation, eliminates the most likely attack vector.

The prompt injection analysis is the most important security finding in the entire peer set. Trail of Bits' research (RCE via argument injection, October 2025) directly applies here: voice transcriptions, GitHub Issue descriptions, and web content all flow into agent prompts. The XML structural separation pattern:
```
<inbox_item>
{user_content}
</inbox_item>
```
is the current Anthropic-recommended defense. This prevents injected instructions from being interpreted as system-level commands.

Per-project Unix user isolation for cross-project secret leakage is correct in principle. However, the operational cost (10 minutes per project setup, sudo configuration) may exceed the risk for a solo founder with 2-5 projects where the primary threat is self-inflicted (prompt injection from external content), not adversarial cross-project access.

The local Whisper recommendation is correct and non-negotiable. Voice notes from a founder about business strategy absolutely must not leave the VPS.

**Missed gaps from LLM agent perspective:**
- No analysis of Multi-LLM security implications. Codex with `--full-auto` or `--dangerously-bypass-approvals-and-sandbox` has a larger attack surface than Claude's `--allowedTools` restriction. The orchestrator should use Codex in Docker (sandboxed filesystem) instead of bare metal to contain blast radius.
- The `--allowedTools` parameter for Claude CLI (which I documented in Phase 1) is not mentioned. Tool restriction per phase is a defense-in-depth mechanism that complements the user isolation approach.
- The AGENTS.md injection vector is not mentioned: if an attacker can write to the project's `AGENTS.md`, they can inject instructions that affect every subsequent Codex session. This is a Codex-specific attack surface.

---

### Analysis G (Evolutionary / Neal)

**Agreement:** Agree

**Reasoning from LLM agent perspective:**

The fitness function approach is the right framework for evolutionary architecture. The concrete implementations (inbox-latency-check.sh, semaphore-check.sh, liveness-check.sh) are the difference between "we care about this property" and "we will know when this property breaks."

The `claude-runner.sh` escape hatch is exactly the right architectural move. Wrapping Claude CLI invocation in a single file costs 30 minutes and preserves options for:
- Claude Code's native multi-project support if Anthropic ships it
- Codex CLI substitution for specific task types
- Any future CLI tool

This is high-value reversibility at near-zero cost. I would extend this: `agent-runner.sh` with an `--engine claude|codex` parameter. Same escape hatch, Multi-LLM ready.

The scaling inflection points (3-4 projects: RAM, 5-6 projects: loop cycle time, 8+ projects: bash complexity) are pragmatic and concrete. These are the right triggers, and having them documented prevents "just one more feature" from pushing the system past an unchecked inflection.

The strangler fig migration path (Phase 0: add projects.json with 1 project, run in parallel, 48h fitness gate) is the correct risk management approach.

**Missed gaps:**
- No Multi-LLM fitness functions. The fitness function suite should include: "engine assignment never conflicts on same project simultaneously" and "Codex Docker container starts and exits cleanly within timeout."
- The `claude-runner.sh` insight does not extend to `agent-runner.sh`. This should be explicit given the Multi-LLM question.
- The hot-reload fitness function (`hot-reload-test.sh`) assumes polling a local HTTP endpoint for status. This endpoint does not exist in the current spec. The test is testing something that has not been built.

---

### Analysis H (Data / Martin)

**Agreement:** Agree

**Reasoning from LLM agent perspective:**

Martin's SQLite recommendation over `.orchestrator-state.json` is the most important architectural fix in the entire peer set, second only to the RAM correction from Peer A.

The GitHub Issue #29158 reference (335 corruptions in 7 days from concurrent JSON writes) is the exact evidence needed. The orchestrator daemon writes state every 60-300 seconds. Multiple concurrent Claude processes update slot state simultaneously. JSON file + concurrent writers = corruption. SQLite WAL mode + `busy_timeout = 5000` handles this correctly.

The SQLite semaphore (replacing flock) is particularly valuable for Multi-LLM:
```sql
CREATE TABLE agent_slots (
    slot_number INTEGER PRIMARY KEY,
    engine TEXT,  -- 'claude' or 'codex'
    project_id TEXT,
    acquired_at TIMESTAMPTZ,
    pid INTEGER
);
```
This gives:
- Atomic slot acquisition across Claude and Codex processes
- Introspectable state (Telegram `/status` reads from DB, not `/tmp/`)
- Crash recovery (pid check on startup to clear stale slots)
- Engine-aware concurrency limits

The inbox file naming convention (`20260310-143022-voice.ogg`, `-voice.txt`, `-idea.md`) is self-describing. An agent reading the inbox knows the file types from the names alone — this passes the LLM-ready test.

The `projects.json` stays JSON (human-config, rare writes) while runtime state moves to SQLite (daemon-writes, frequent) is the correct SSOT separation.

**Missed gaps:**
- The `usage_ledger` table should include `engine TEXT` column to track Claude vs Codex costs separately. This is a one-line addition that enables per-engine cost analysis.
- The Multi-LLM question is not addressed at the data layer. The `agent_slots` table design above resolves this.
- The `inbox_items` completeness invariant ("write components first, write `-idea.md` last") is correct but does not address concurrent bot handlers processing two simultaneous messages. A Telegram message_id lock mechanism is needed.

---

## Ranking

**Best Analysis:** H (Data Architect / Martin)

**Reason:** Martin correctly identified the most dangerous implementation flaw in the current spec: `.orchestrator-state.json` race condition confirmed by production evidence (GitHub #29158). The SQLite migration path is concrete, complete, and immediately actionable. The entity relationship model is clean and the data flow diagram makes the system legible to any subsequent engineer. The SSOT designation for every entity eliminates the "five state stores" problem that Peer B identified but did not solve.

**Second best:** A (Ops / Charity)

**Reason:** Corrects the RAM model with production evidence, provides the most complete ops runbook, and the semaphore + systemd design is production-ready.

**Worst Analysis:** B (Devil's Advocate / Fred)

**Reason:** The "why build this at all" critique is valid but does not answer the architecture question. When the founding decision has been made to build, the devil's advocate role is to find flaws in HOW to build, not to relitigate WHETHER to build. More critically, Peer B provides the least actionable output: the critique surfaces contradictions but resolves none of them. The recommendation is "50-line Python script + Pueue" without detailing how Telegram routing, inbox processing, or Multi-LLM would work at that scale.

---

## Revised Position

**Revised Verdict:** The existing architecture spec needs significant corrections before implementation. The peer analyses together surface all the blockers. No single peer missed everything — they each caught what their expertise illuminated.

**Change Reason (from my Phase 1 analysis):**

My Phase 1 findings remain valid. The major additions from peer review:

1. **SQLite over JSON for runtime state** (Martin). I missed this in Phase 1. The `.orchestrator-state.json` race condition is real and the SQLite fix is correct.

2. **Pueue as job queue** (Dan). My Phase 1 dismissed the flock semaphore as "correct but with edge cases." Pueue is a better primitive and eliminates custom semaphore code entirely.

3. **Bounded contexts clarify agent design** (Eric). The ACL pattern for external tools (Telegram, Claude CLI) is the right frame. I had this implicitly in my Phase 1 tool design recommendations but Eric made it explicit.

4. **Per-project Unix user isolation** (Bruce). I had `CLAUDE_CODE_CONFIG_DIR` per project as Option B in Phase 1. Bruce's per-user isolation is stronger and extends naturally to Codex.

**Final LLM Recommendation for This Round:**

The architecture for the Multi-Project Orchestrator should be:

1. **Agent pattern:** Workflow orchestrator (bash/Python event loop, no LLM in the routing path) + autonomous Claude CLI workers per project + optional Codex workers for specific task types. NOT Agent Teams.

2. **Context injection:** `cwd = project_dir` for CLAUDE.md auto-load. Same pattern for Codex with `AGENTS.md`. Both MUST be maintained per project. The orchestrator's job is to ensure correct `cwd` per invocation.

3. **Concurrency:** Pueue with separate groups per project + engine-aware parallelism limits (`pueue parallel --group saas-app-claude 1`, `pueue parallel --group saas-app-codex 1`). Total cap: 2 concurrent agents max on 8GB VPS (1 Claude + 1 Codex).

4. **State:** SQLite for all daemon-written state. JSON for human-written config.

5. **Multi-LLM:** Start with project-level routing (Option B). Add `engine: "claude" | "codex"` field to `projects.json`. Use `agent-runner.sh` as the single invocation point with engine-switching logic.

6. **Codex in Docker:** Run Codex sessions inside Docker containers (mounted project volume). Run Claude sessions bare metal with per-user isolation (Bruce's P1 recommendation). This gives different isolation strategies matching each tool's security model.

7. **Context budget:** CLAUDE.md + AGENTS.md should both be kept under 5K tokens. The DLD framework CLAUDE.md is verbose (~8K tokens) — this is acceptable given 200K context window. Codex uses GPT-5.4 with 1M context — even less concern.

8. **Self-describing interface:** The orchestrator must expose `pueue status --json` output (or equivalent) as the agent-readable state interface. Any agent should be able to determine system state from a single JSON query, without SSH.

---

## Note on Phase 7 Step 4

The full LLM-Ready Check gate (Phase 7, Step 4) will address:
- Final tool design quality scores per agent/API endpoint
- Context budget analysis per agent
- API contract completeness (OpenAPI or equivalent)
- Eval strategy validation
- Blocking issues summary

This Phase 2 critique is input to synthesis. The findings above, especially Multi-LLM routing, Codex Docker deployment, and the engine-aware semaphore design, should be incorporated into the synthesized architecture before Phase 7 gate.

---

## References

- [Anthropic — Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [OpenAI Codex CLI Non-Interactive Mode](https://developers.openai.com/codex/noninteractive/)
- [AGENTS.md Open Standard — Linux Foundation / Agentic AI Foundation](https://developertoolkit.ai/en/codex/quick-start/agents-md/)
- [Codex CLI: The Definitive Technical Reference](https://blakecrosley.com/guides/codex)
- [agent-mux: Cross-Engine Subagents for Claude Code and Codex CLI](https://www.nickoak.com/posts/agent-mux/)
- [Multi-Agent Orchestration for Developers in 2026 — Scopir](https://scopir.com/posts/multi-agent-orchestration-parallel-coding-2026/)
- [Codex CLI Memory Leak Issue #9345](https://github.com/openai/codex/issues/9345)
- [Codex CLI Non-Interactive Mode Issue #4219](https://github.com/openai/codex/issues/4219)
- [Codex CLI in Docker — Diatonic-AI](https://github.com/Diatonic-AI/codex-cli-docker-mcp)
- [Evaluating AGENTS.md — arXiv 2602.11988](https://arxiv.org/html/2602.11988v1) — AGENTS.md reduces task success vs no context file; keep it minimal
- [Trail of Bits: Prompt Injection to RCE](https://blog.trailofbits.com/2025/10/22/prompt-injection-to-rce-in-ai-agents/)
- [PuzldAI — Multi-LLM Orchestration Framework](https://github.com/MedChaouch/Puzld.ai) — commercial reference
- [Claude Code #29158 — ~/.claude.json corruption](https://github.com/anthropics/claude-code/issues/29158)
- [Claude Code #30348 — Cross-session contamination](https://github.com/anthropics/claude-code/issues/30348)
