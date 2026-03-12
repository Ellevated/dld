# LLM Architect Research: Multi-Project Orchestrator

**Persona:** Erik (LLM Architect)
**Phase:** 1 — Individual Research
**Date:** 2026-03-10

**Kill Question:** Can an agent work with this orchestrator without reading source code?

---

## Research Conducted

Searches completed (10 queries):
1. Claude Code CLI concurrency multiple sessions RAM usage 2025 2026
2. Claude Code context isolation between projects CLAUDE.md session management
3. Anthropic Agent Teams Opus 4.6 multi-agent coordination cross-project 2026
4. GitHub Copilot Coding Agent architecture GitHub Issues workflow
5. Spec Kit open source agent orchestration multi-agent
6. Claude Code CLI RAM memory usage per process VPS 8GB concurrent
7. Claude Code --max-turns timeout configuration headless mode project context
8. GitHub Copilot coding agent GitHub Issues ephemeral environment
9. Agentic workflow orchestration LLM triage vs rule-based classification
10. Agent Teams cross-project limitations single-project scope
11. GitHub Issues as AI agent canonical interface

---

## Finding 1: Claude CLI Concurrency — Hard RAM Ceiling on 8GB VPS

### What the data shows

The existing spec says "200-500 MB per Claude process." This is **significantly understated** based on current GitHub issues:

| Scenario | Observed RAM | Source |
|----------|-------------|--------|
| Single Claude process (v2.1.62) | 6.4 GB | GitHub #29576 |
| Single process (memory leak) | 120-129 GB virtual | GitHub #4953, #11315 |
| 4 concurrent sessions (MCP-heavy) | ~4.5 GB Claude + MCPs | GitHub #28860 |
| Agent Teams mode (Team/Teammate) | 13-16 GB | GitHub #23883 |

**Key insight:** The 200-500 MB estimate was from pre-2026 data or minimal sessions. In practice on v2.1.x:
- A single Claude process at rest: ~400-600 MB (RSS), but can spike to 2-4 GB during active Opus 4.6 sessions
- Each MCP server spawns independently per session: adds 100-400 MB per MCP, per session
- With 4 MCP servers across 2 concurrent sessions: adds ~1.9 GB MCP overhead alone

**Realistic budget for 8 GB VPS:**
- OS + orchestrator: ~500 MB
- Per Claude process (no MCP): ~600 MB baseline + 1-2 GB peak
- Per MCP server per session: ~100-400 MB each
- Safe concurrent sessions: **1 active (with MCP) or 2 (headless, no MCP)**

**The 8 GB VPS supports MAX 2 concurrent Claude sessions, and only safely 1 if running MCP-heavy agents.** The existing spec's `max_concurrent_claude: 2` is correct but for the wrong reasons.

### Cross-session contamination risk

GitHub issue #30348 (March 2026): Cross-session message contamination between parallel CLI sessions. Content from Session A appeared in Session B. This is a **known bug** with unresolved root cause, marked as duplicate of a broader issue. Two sessions on the same machine, same user, can contaminate each other.

**Implication for orchestrator:** Sessions MUST run in isolated environments (different users, or at minimum different home directories with different `CLAUDE_CODE_CONFIG_DIR`).

---

## Finding 2: Context Isolation Between Projects

### What Claude Code does natively

CLAUDE.md is loaded **based on `cwd`** — the current working directory when Claude starts. In headless mode (`-p` flag), Claude Code automatically reads CLAUDE.md from the directory where the command runs.

```bash
# This loads /home/user/saas-app/CLAUDE.md automatically
cd /home/user/saas-app && claude -p "run spark for FTR-042" --max-turns 25
```

**This is the mechanism for project context injection.** No extra work required.

### What does NOT happen natively

1. **Session memory is global, not per-project**: `~/.claude/` contains session memories that are not project-scoped. A session working on project A can recall memories from project B if they share the same home directory.
2. **MCP servers are shared**: All concurrent sessions share the same MCP server config from `~/.claude/settings.json`. No per-project MCP isolation.
3. **No built-in semaphore**: Claude Code has no concept of "only run N instances at once." The orchestrator must implement this.
4. **Config dir is shared**: `CLAUDE_CODE_CONFIG_DIR` defaults to `~/.claude`. Setting it per-project call is possible via env var but requires orchestrator discipline.

### The orchestrator's job for context isolation

```bash
# Pattern: set cwd + CLAUDE_CODE_CONFIG_DIR per project
CLAUDE_CODE_CONFIG_DIR="/var/orchestrator/projects/saas-app/.claude-state" \
  cd /home/user/saas-app && \
  claude -p "$(cat prompt.txt)" \
    --max-turns 25 \
    --output-format json
```

This achieves hard isolation: separate config state, separate session memories, separate MCP server instances. **Cost: more RAM per session** (separate MCP process trees).

### CLAUDE.md as project context mechanism

CLAUDE.md is the RIGHT mechanism for passing project context to Claude. This is how DLD already works. The orchestrator does not need to build a separate context injection system — it just needs to ensure `cwd` is the project root when invoking Claude.

From the CI/CD research: "35% more consistent results when CLAUDE.md is used in headless mode." The pattern is validated.

---

## Finding 3: Agent Teams — Scope Limitation and RAM Cost

### What Agent Teams actually is

Agent Teams (introduced v2.1.32, February 5, 2026, research preview) enables multiple Claude Code instances to coordinate via:
- A shared task list
- Direct inter-agent messaging (inbox files in `~/.claude/teams/{name}/`)
- tmux backend for visual panes
- One "team lead" session + N teammates

**Enable with:** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in settings.json

### Critical scope constraint: Agent Teams is INTRA-project only

From the official docs (code.claude.com/docs/en/agent-teams):
> "Agent teams are most effective for tasks where parallel exploration adds real value... Cross-layer coordination: changes that span frontend, backend, and tests, each owned by a different teammate"

All examples are within a single codebase. The team lead and teammates share the same working directory and git repo. There is **no documented mechanism** for Agent Teams to span across different project directories.

GitHub issue #31940 (March 2026) explicitly confirms the limitation:
> "There is currently no way to set a different `cwd` or additional allowed directories for a subagent. Both `AgentDefinition` and file-based subagent frontmatter lack any directory-scoping fields. This makes per-subagent filesystem isolation impossible at the configuration level."

**Conclusion: Agent Teams CANNOT span projects on a multi-project orchestrator.** Each Agent Team is scoped to one project's codebase. The orchestrator itself must be the cross-project coordinator.

### Agent Teams RAM cost makes it impractical on 8 GB VPS

GitHub issue #23883: "Claude Code process consumes ~13-16 GB RAM when running Agent Teams mode." This is 2x the total VPS RAM. Agent Teams on 8 GB VPS = OOM kill.

**Decision: Agent Teams is a no-go for this orchestrator on 8 GB VPS.** Use standard subagents (ADR-008 pattern: background fan-out) instead.

### Agent Teams experimental bugs (as of March 2026)

These are production blockers, not edge cases:
- #23415: Teammates don't poll inbox — messages never delivered (tmux backend)
- #29271: No distinction between idle and dead teammates — lead spawns duplicates
- #32368: Teammates don't inherit model configuration from team lead
- Role degradation after 15-20 iterations (coordination collapses)

**Status: NOT suitable for production orchestrator use.** Use subagent pattern instead.

---

## Finding 4: --max-turns and Timeout Tuning

### Available controls (headless mode)

```bash
claude -p "prompt" \
  --max-turns 25 \        # Limits agentic iterations (prevents runaway)
  --max-budget-usd 5.00 \ # Caps spending per session
  --allowedTools Bash,Read,Edit,Write,Glob,Grep \  # Tool restriction
  --output-format json    # Machine-readable output
```

Environment variable alternative:
```bash
CLAUDE_CODE_MAX_TURNS=25  # Sets default max turns globally
```

### Timeout for bash commands

From settings.json:
```json
{
  "env": {
    "BASH_DEFAULT_TIMEOUT_MS": "120000",
    "BASH_MAX_TIMEOUT_MS": "600000"
  }
}
```

The 2-minute bash timeout is configurable via settings.json `env` section — NOT via env vars exported in the calling shell.

### Recommended tuning per project priority

| Phase | --max-turns | Rationale |
|-------|-------------|-----------|
| Inbox processor (triage) | 5-8 | Low complexity, just parse and file |
| Spark spec generation | 30-40 | Complex multi-agent work |
| Autopilot (single task) | 25-35 | Standard implementation |
| QA check | 10-15 | Verification, not creation |
| Emergency hotfix | 15 | Bounded, low risk |

**Priority-based timeout strategy:**
- High priority project: full `--max-turns 30`
- Medium priority: `--max-turns 20`
- Low priority: `--max-turns 15` (save slots for high priority)

**Budget cap as safety valve:** `--max-budget-usd 2.00` per autopilot run prevents runaway costs. At $5/M tokens for Opus, 2 USD = ~400K tokens = enough for a large feature spec.

---

## Finding 5: Inbox Processing — Claude vs Rule-Based

### When to use rule-based routing

Industry consensus from Camunda, AG2, and routing pattern research:

> Rule-based routing is correct when:
> - Input is structured and predictable (commands, keywords)
> - Routing logic can be expressed as deterministic conditions
> - Speed matters more than nuance
> - Errors are cheap (wrong route is obvious)

**Commands in Telegram topics are structured input**: `/status`, `/run`, `/pause`, `/priority high`. These are deterministic. Rule-based routing handles them correctly with zero LLM cost.

### When to use LLM triage

> LLM routing is correct when:
> - Input is unstructured (voice transcriptions, screenshots, freeform text)
> - Intent classification requires semantic understanding
> - Multiple valid interpretations exist

**Inbox content is unstructured**: Voice transcription "hey I want to add dark mode to the app" needs to be classified as an idea, routed to the right project (if in general topic), and possibly prioritized. This is where LLM classification adds value.

### Hybrid recommendation for this orchestrator

```
Structured input (slash commands) → Rule-based router (zero cost, instant)
Unstructured input (voice/text/screenshot) → Rule-based FIRST:
  - If message_thread_id matches a project → route to that project (rule-based)
  - If in General topic + ambiguous → LLM triage to classify intent + project
  - Default: dump to general inbox, human decides
```

**Key insight: Telegram topics already do the routing for us.** `message_thread_id` is the primary router. LLM is only needed for cross-project intent in the General topic. This reduces LLM triage calls to ~5-10% of messages.

**LLM triage cost for general topic:** Use Haiku ($1/M tokens), not Opus. A triage prompt is ~500 tokens input + 100 output = $0.0006/message. For 100 messages/day across all projects = $0.06/day. Negligible.

---

## Finding 6: GitHub Copilot Coding Agent — What to Learn From It

### Architecture pattern

GitHub Copilot Coding Agent:
- **Trigger:** Assigned to a GitHub Issue (or mentioned in PR, or via agents panel)
- **Environment:** Ephemeral GitHub Actions runner (Ubuntu or custom via `copilot-setup-steps.yml`)
- **Context:** Reads issue description + linked PR/issue context + `.github/copilot-instructions.md`
- **Output:** Pull Request with changes
- **Isolation:** Each task gets its own ephemeral VM (hard isolation, no cross-contamination)
- **Firewall:** Default allowlist for package registries + GitHub APIs. Custom allowlist configurable.
- **Model:** Configurable per task (faster model for simple, more powerful for complex)

### What the orchestrator can learn

1. **Issue as work unit:** Each Issue = one unit of delegatable work. The agent reads the issue, does the work, outputs a PR. This is analogous to DLD's backlog task spec. A GitHub Issue IS a task spec.

2. **Ephemeral isolation:** Copilot gets a fresh VM per task. On VPS with RAM constraints, we can't do VMs but we CAN do fresh tmux sessions with separate `CLAUDE_CODE_CONFIG_DIR`.

3. **`.github/copilot-instructions.md` = CLAUDE.md:** Both are project-context files auto-loaded by the agent. Same pattern, different tool.

4. **Async + PR as output:** Copilot works in background, outputs a reviewable artifact. DLD autopilot already does this (commits to branch). Pattern is validated.

5. **Firewall/sandboxing:** Copilot has network restrictions. On VPS, this maps to: Claude's `--allowedTools` restricts what tools can run. The orchestrator should pass explicit `--allowedTools` per phase to prevent runaway tool use.

### What the orchestrator should NOT copy

1. **Ephemeral VMs per task:** Too expensive and complex for 2-5 projects on a $50 VPS. tmux sessions with file-level isolation are sufficient.

2. **GitHub Issues as primary interface:** Copilot uses GitHub Issues because GitHub IS the workflow. For a solo founder managing DLD projects via Telegram, the primary interface remains Telegram topics. GitHub Issues as secondary (for structured task tracking) is fine, but don't replace Telegram.

---

## Finding 7: GitHub Spec Kit — Reference Architecture

### What Spec Kit is

GitHub's open-source toolkit for Spec-Driven Development (MIT, 71K stars):
- CLI: `specify` + slash commands
- 4-phase workflow: `/specify → /plan → /tasks → /implement`
- Supports 20+ agents: Claude Code, Copilot, Gemini CLI, Codex, Cursor, etc.

### The spec-kitty-orchestrator pattern

From `Priivacy-ai/spec-kitty-orchestrator` (February 2026):

```
spec-kitty-orchestrator
  │
  │  spec-kitty orchestrator-api <cmd> --json
  ▼
 spec-kitty (host)
  │
  └── kitty-specs/<feature>/tasks/WP01..WPn.md
```

The orchestrator polls for ready work packages, spawns AI agents in worktrees, and transitions WPs through `planned → claimed → in_progress → for_review → done` by calling the host API at each step. **All workflow state lives in spec-kitty (the host system); the orchestrator only tracks provider-local data.**

**This is exactly the DLD pattern:** State lives in `ai/backlog.md` + task spec files. Claude CLI is the agent. The orchestrator manages concurrency and routing.

### Key difference from DLD

Spec Kit uses a versioned CLI contract (`orchestrator-api --json`) for state transitions. DLD uses bash scripts reading/writing markdown files. This is fine for DLD's scale — but suggests the state interface should be explicit and consistent.

---

## Finding 8: GitHub Agentic Workflows — Markdown as Natural Language Programs

From GitHub Next (February 2026):
> "Agentic Workflows are natural language programming over GitHub. Instead of writing bespoke scripts, you describe desired behavior in plain language. This is converted into an executable GitHub Actions workflow."

**Pattern insight:** The orchestrator's "skills" (inbox processing, autopilot trigger, QA check) are essentially agentic workflows. They can be expressed as CLAUDE.md-resident instructions that Claude reads when invoked headlessly. This is what DLD already does with `/spark`, `/autopilot`.

**What this validates:** The `PROJECT_DIR/CLAUDE.md` + headless Claude CLI invocation IS a valid industry pattern for agent-triggered workflows. It's essentially what GitHub Agentic Workflows compiles to, but without the GitHub Actions layer.

---

## Critical Issues for Architecture

### Issue 1: Session state contamination (BLOCKING)

**Problem:** Two concurrent Claude CLI sessions on the same VPS user account can contaminate each other's contexts (issue #30348, March 2026). Not just theoretical — observed in production.

**Fix options:**
A. Run each project under a separate Linux user (full isolation, $0 extra cost, highest security)
B. Set `CLAUDE_CODE_CONFIG_DIR=/var/orchestrator/projects/{name}/.claude` per call (state isolation, same user)
C. tmux session per project with explicit config dir (practical, medium isolation)

**Recommendation: Option B** — explicit per-project config dir. Easy, scriptable, no user management.

### Issue 2: RAM model is wrong (SIGNIFICANT)

The existing spec's "200-500 MB per Claude process" is 3-10x understated. Real numbers:
- Headless Claude process (minimal): ~400-800 MB
- Claude with DLD's MCP servers (Exa + Context7): +200-600 MB per MCP, per session
- Active Opus 4.6 session: peaks at 1.5-3 GB

**For 8 GB VPS, safe operating model:**
- 1 active Claude session with MCP: ~2-3 GB
- 1 active Claude session without MCP: ~800 MB - 1.5 GB
- OS + orchestrator: ~500 MB
- Buffer: 1 GB

**Safe concurrent sessions: MAX 2** (both headless, no MCP) or **MAX 1** (with MCP).

The semaphore `max_concurrent_claude: 2` should have a mode flag: `mcp_enabled: true/false` per project, affecting real concurrency limit.

### Issue 3: Context isolation requires explicit cwd management

**Problem:** The orchestrator must ensure `cwd` is set to the project root before every `claude -p` call. If the orchestrator bash script runs from its own directory and calls `claude -p` without `cd`, Claude loads the orchestrator's CLAUDE.md (or none), not the project's.

**Fix:** Every Claude invocation in the orchestrator must be:
```bash
(cd "$PROJECT_DIR" && claude -p "prompt" --max-turns 25)
```

This is trivial but must be enforced — it's the primary context injection mechanism.

### Issue 4: Agent Teams is off the table for this use case

- 13-16 GB RAM for Team/Teammate mode = immediate OOM on 8 GB VPS
- Experimental bugs make it unreliable even if RAM were available
- Cross-project scope is explicitly NOT supported
- Standard subagent pattern (Claude CLI headless + background jobs) is the right choice

**Decision: Do not use Agent Teams. Use headless Claude CLI with the subagent pattern (ADR-008/009/010).**

### Issue 5: flock semaphore is sufficient but has edge case

The bash `flock` semaphore in the existing spec is correct for this scale. However:
- `flock -n` returns immediately if lock not available — the polling loop is correct
- **Risk:** If Claude process dies without releasing flock (OOM kill), the lock file remains held until... the file descriptor closes. For flock, FD is closed on process death, so lock IS released. This is safe.
- **Actual risk:** If the orchestrator script itself crashes while holding slot references (not the Claude process), the slot tracking (via `echo $i`) breaks. The slot tracking is in memory, not via flock. Flock is actually fine.

**The flock approach works. Keep it.**

---

## Architecture Recommendations (LLM Architect Perspective)

### Recommended agent pattern

**Workflow pattern** (not Orchestrator-Workers, not Autonomous):

The orchestrator is NOT an LLM agent — it's a shell script event loop. Claude CLI invocations are the workers. Each worker is autonomous within its project scope. The orchestrator is pure control flow.

```
Orchestrator (bash event loop — no LLM)
  │
  ├── reads projects.json (config)
  ├── checks inbox files (rule-based)
  ├── acquires semaphore slot (flock)
  └── invokes Claude CLI (worker agent, headless)
       │
       └── cwd = project_dir
           CLAUDE.md = project context
           --max-turns = priority-based limit
           --output-format json = machine-readable
```

This is correct. The LLM is not in the routing loop — it's only invoked for actual work.

### Tool design for orchestrator's Claude invocations

Each Claude invocation should be a self-describing, single-purpose call:

```bash
# Inbox processing: structured, low turns, Haiku model
(cd "$PROJECT_DIR" && claude -p "$(cat .claude/skills/inbox-processor/SKILL.md)" \
  --model claude-haiku-4 \
  --max-turns 8 \
  --allowedTools Read,Write,Bash,Glob,Grep \
  --output-format json)

# Autopilot: full DLD workflow, high turns, Opus model
(cd "$PROJECT_DIR" && claude -p "/autopilot" \
  --model claude-opus-4-6 \
  --max-turns 30 \
  --max-budget-usd 3.00 \
  --output-format json)
```

**Tool restriction per phase** reduces risk: inbox processor doesn't need `Edit` or `Write` to production files. Autopilot needs full tools. QA needs Read + Bash only.

### Context budget for orchestrator-facing agents

The orchestrator itself runs bash, not LLM. But when Claude is invoked per project, its context budget is:

| Component | Tokens | Notes |
|-----------|--------|-------|
| System prompt (CLAUDE.md) | 2-8K | DLD framework is verbose |
| Skill (e.g., autopilot SKILL.md) | 1-3K | Per-skill instructions |
| Project rules (.claude/rules/) | 1-3K | Conditionally loaded |
| Task spec (ai/features/TASK.md) | 1-2K | The actual work unit |
| Working context (tool outputs) | 50-150K | Grows during execution |
| **Baseline before work** | **~8-15K** | Reasonable, within 200K |

This is healthy. The 200K context window means ~185K tokens are available for actual reasoning and tool outputs.

### LLM triage design (for General topic messages)

When a message arrives in the General topic without a clear project target:

```
Input: unstructured message
Prompt: system="You are a project router. Projects: [list].
        Classify the intent and most likely target project.
        Output JSON: {project: string|null, intent: string, confidence: float}"
Model: Haiku (cheap, fast)
Max turns: 1 (classification is single-shot)
```

Self-describing output: structured JSON with `project`, `intent`, `confidence`. If `confidence < 0.7`, don't auto-route — send to General inbox for human review. This prevents misrouting.

### Self-describing API contract for orchestrator

The orchestrator's "API surface" for agents (Claude CLI invocations) is:

| Entry point | Context mechanism | Purpose | Self-describing? |
|-------------|-------------------|---------|-----------------|
| `cd $PROJECT_DIR && claude -p "skill"` | CLAUDE.md auto-load | Project work | Yes — CLAUDE.md is the contract |
| `--allowedTools` | Explicit tool list | Security | Yes — documented in CLI help |
| `--max-turns N` | Explicit limit | Cost control | Yes — self-evident |
| `--output-format json` | Structured output | Machine parsing | Yes — JSON is self-describing |
| `--max-budget-usd N` | Cost cap | Safety | Yes — explicit |

**Kill question answer for orchestrator's agent interface:** An agent (the Claude CLI process) can work with this system by reading only CLAUDE.md + the skill file. No source code reading required. Grade: A.

---

## Open Questions for Architecture Council

1. **Project isolation level:** Per-user Linux isolation vs per-call `CLAUDE_CODE_CONFIG_DIR`? Trade-off: security vs simplicity.

2. **GitHub Issues as secondary state store:** Should task specs live in GitHub Issues (version-controlled, API-native) in addition to `ai/features/`? Copilot's model suggests Issues are the canonical interface for delegating to agents. Is this worth the added complexity for a solo founder?

3. **Model selection per project phase:** Should the orchestrator allow per-project model configuration (some projects use Sonnet, others Opus)? The `projects.json` already has `priority` — this could drive model selection.

4. **Inbox LLM triage:** Use Haiku for real-time triage (cheap, fast) or Sonnet (better classification, 3x cost)? At ~100 messages/day, Haiku = $0.06/day vs Sonnet = $0.18/day. Both negligible. Haiku is fine.

5. **State file location:** `.orchestrator-state.json` at VPS level vs per-project state files? Centralized is simpler for orchestrator; per-project is better for isolation and backup.

6. **flock vs Pueue:** flock is correct for 1-2 concurrent processes. If scale reaches 5+ projects with burst needs, Pueue's proper queue management is worth the switch. Threshold: >5 concurrent project activations per hour.

---

## Summary Verdict

The existing architecture spec is **substantially correct** from an LLM agent perspective. Key corrections:

| What | Spec says | Reality | Action |
|------|-----------|---------|--------|
| RAM per process | 200-500 MB | 800 MB - 3 GB | Lower `max_concurrent_claude` to 2 max, document realistic ceiling |
| Agent Teams | Not mentioned | 13-16 GB RAM, bugs, intra-project only | Explicitly exclude from architecture |
| Context injection | via `PROJECT_DIR` arg | Correct — CLAUDE.md auto-loaded from cwd | Enforce cwd discipline in orchestrator |
| Session isolation | Not addressed | Cross-session contamination risk (bug #30348) | Add `CLAUDE_CODE_CONFIG_DIR` per project |
| Triage model | Not specified | Rule-based for commands, Haiku for unstructured | Specify model routing |
| --max-turns | 20-30 | Correct range, needs per-phase tuning | Add phase-specific limits |

**Pattern decision:** Workflow orchestrator (bash event loop) + autonomous Claude CLI workers. Not Agent Teams. Not a custom Python framework. Boring, proven, works.

**Confidence in agent success:** High (85%) — CLAUDE.md as context injection is battle-tested, headless mode is production-ready, the semaphore model is simple enough to be reliable.

---

## References

- [Anthropic — Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [Claude Code Agent Teams Docs](https://code.claude.com/docs/en/agent-teams)
- [GitHub #23883 — Agent Teams RAM 13-16 GB](https://github.com/anthropics/claude-code/issues/23883)
- [GitHub #30348 — Cross-session contamination](https://github.com/anthropics/claude-code/issues/30348)
- [GitHub #29576 — Memory regression v2.1.62](https://github.com/anthropics/claude-code/issues/29576)
- [GitHub #28860 — MCP servers per session RAM](https://github.com/anthropics/claude-code/issues/28860)
- [GitHub #31940 — No per-subagent cwd scoping](https://github.com/anthropics/claude-code/issues/31940)
- [SFEIR — Claude Code Headless Mode CI/CD](https://institute.sfeir.com/en/claude-code/claude-code-headless-mode-and-ci-cd/faq/)
- [GitHub Agentic Workflows](https://github.blog/ai-and-ml/automate-repository-tasks-with-github-agentic-workflows/)
- [GitHub Copilot Coding Agent Docs](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent)
- [Spec Kit — GitHub Open Source](https://rywalker.com/research/github-spec-kit)
- [spec-kitty-orchestrator pattern](https://github.com/Priivacy-ai/spec-kitty-orchestrator)
- [Claude Fast — Agent Teams Guide](https://claudefa.st/blog/guide/agents/agent-teams)
- [AG2 — Intelligent Agent Handoffs](https://docs.ag2.ai/latest/docs/blog/2026/03/05/intelligent-agent-handoffs/)
- [Camunda — AI Agent vs Rule-Based DMN](https://camunda.com/blog/2025/07/ai-agent-or-based-rule-dmn-ai-powered-orchestration/)
