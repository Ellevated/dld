# Pattern Research — FTR-148 Multi-Project Orchestrator Phase 3

---

## Pattern 1: Task-Level Provider Routing

---

### Approach 1A: Static Metadata Routing (provider annotation in spec)

**Source:** [Multi-LLM Routing Strategies — AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/multi-llm-routing-strategies-for-generative-ai-applications-on-aws/)

#### Description
Provider is declared as a field in the task spec YAML/markdown at authoring time: `provider: gemini`. The orchestrator (`run-agent.sh`) reads this field and dispatches accordingly. No runtime decision-making — the human/Spark chooses the provider when writing the spec.

#### Pros
- Zero runtime overhead — dispatch logic is a single `case` statement in bash
- Fully deterministic — no surprises in which CLI runs
- Easy to audit — `grep "provider:" ai/features/` shows every decision
- Works today with the existing `run-agent.sh` dispatcher pattern (Phase 1)

#### Cons
- Author must know provider capabilities at spec-writing time
- Stale routing if a provider goes down or quota is exhausted (no fallback)
- Does not adapt to Claude Max subscription limits (rate-limited periods)
- Spec drift: task type and provider choice can get out of sync over time

#### Complexity
**Estimate:** Easy — 2-4 hours
**Why:** `run-agent.sh` already dispatches to `claude-runner.sh` / `codex-runner.sh`. Add `provider:` field parsing to `orchestrate.sh`, add `gemini-runner.sh`, done. No new components.

#### Example Source
```bash
# orchestrate.sh — read provider from spec frontmatter
PROVIDER=$(grep "^provider:" "$SPEC_FILE" | awk '{print $2}' | tr -d '"')
PROVIDER=${PROVIDER:-claude}  # default

case "$PROVIDER" in
  gemini)  bash scripts/vps/gemini-runner.sh "$PROJECT_ID" "$SPEC_ID" ;;
  codex)   bash scripts/vps/codex-runner.sh  "$PROJECT_ID" "$SPEC_ID" ;;
  claude)  bash scripts/vps/claude-runner.sh "$PROJECT_ID" "$SPEC_ID" ;;
  *)       echo "Unknown provider: $PROVIDER"; exit 1 ;;
esac
```

---

### Approach 1B: Dynamic Routing via Complexity Classifier

**Source:** [Practical Gemini CLI: Intelligent Model Router](https://medium.com/google-cloud/practical-gemini-cli-intelligent-model-router-e01e543ec438) | [AI Agent Model Routing — Zylos Research](https://zylos.ai/research/2026-03-02-ai-agent-model-routing)

#### Description
A lightweight classifier (bash + `jq` or a small Python script) reads the task spec and applies a rubric — complexity score, estimated tool calls, task type keywords — to select the provider before dispatch. Gemini CLI itself uses `gemini-2.5-flash-lite` to classify each prompt before routing to Flash or Pro. The same pattern applies here: a cheap, fast decision layer picks the runner.

#### Pros
- Provider selection scales automatically as task load grows
- Enables cost optimization: simple tasks → Gemini Flash, complex → Claude Opus
- Survives spec drift — routing logic lives in one place, not per-spec
- Can incorporate availability signals (quota check before dispatch)

#### Cons
- Adds latency (classifier runs before task starts)
- Classifier errors route tasks to wrong provider silently
- Requires maintaining the rubric as models evolve
- Overkill for 10 projects / 3 slots: routing variance is minimal at this scale
- Claude Max (subscription) has no cost signal — cost-routing argument is weaker

#### Complexity
**Estimate:** Medium — 8-12 hours
**Why:** Need classifier script, rubric definitions, integration tests proving correct routing, fallback logic when classifier fails. Gemini CLI's own classifier took Google a full sprint to tune.

#### Example Source
```python
# classifier.py — simplified complexity rubric
COMPLEX_KEYWORDS = ["architect", "council", "audit deep", "multi-agent", "migrate"]
SIMPLE_KEYWORDS  = ["doc", "comment", "rename", "format", "release notes"]

def classify(spec_text: str) -> str:
    lower = spec_text.lower()
    score = sum(1 for kw in COMPLEX_KEYWORDS if kw in lower)
    score -= sum(1 for kw in SIMPLE_KEYWORDS if kw in lower)
    if score >= 2:   return "claude"   # heavy reasoning
    elif score >= 0: return "codex"    # balanced
    else:            return "gemini"   # fast/cheap
```

---

### Approach 1C: User-Selected Routing via Telegram

**Source:** [Router-Based Agents — Towards AI](https://pub.towardsai.net/router-based-agents-the-architecture-pattern-that-makes-ai-systems-scale-a9cbe3148482)

#### Description
When the orchestrator picks up a queued task, the Telegram bot sends an inline keyboard: "Run with: [Claude] [Gemini] [Codex]". User taps a button, orchestrator receives callback, dispatches to the selected runner. Selection is stored in SQLite for audit.

#### Pros
- Human stays in full control of provider choice
- No classifier to maintain or tune
- Builds user intuition about which tasks suit which model

#### Cons
- Breaks async automation — every task now requires human attention
- Blocks the slot until user responds (could be hours)
- Defeats the purpose of a background orchestrator
- Does not scale even to 10 projects

#### Complexity
**Estimate:** Medium — 6-8 hours (but wrong tradeoff entirely)
**Why:** Telegram inline keyboards + callback state management + timeout handling. Code is straightforward but the UX is fundamentally broken for background automation.

---

### Comparison Matrix — Pattern 1: Provider Routing

| Criteria | 1A: Static Metadata | 1B: Dynamic Classifier | 1C: User-Selected |
|----------|--------------------|-----------------------|-------------------|
| Complexity | Low | Medium | Medium |
| Maintainability | High | Medium | Low |
| Determinism | High | Low | High |
| Automation fit | High | High | Low |
| Overhead | None | +1-3s per task | Blocks on human |
| Output normalization effort | Low | Low | Low |

---

### Recommendation — Pattern 1

**Selected:** Approach 1A (Static Metadata) with one explicit addition.

**Rationale:**
At 10 projects, 3 compute slots, and a Claude Max subscription (no per-token cost signal), dynamic routing solves a problem we don't have yet. Static metadata keeps the orchestrator as a dumb dispatcher — the right architectural role. The author writing the spec has all context needed to pick the provider: task type, required tools, target codebase.

The one gap in 1A is output normalization. Each CLI outputs differently:

- `claude --print --output-format json` → `{"type":"result","result":"...","session_id":"..."}`
- `gemini --output-format json -p "..."` → `{"response":"...","stats":{...}}`
- `codex --json` → `{"output":"...","usage":{...}}`

This is solved by a per-runner wrapper that normalizes to a common envelope before writing the gate file — not a classifier, just 5 lines of `jq` in each runner script.

**Key factors:**
1. Zero latency overhead — dispatch is a `case` statement
2. Provider choice is a human decision, not a heuristic
3. Extensible: add `gemini-runner.sh` following the existing `claude-runner.sh` pattern

**Trade-off accepted:** If a provider is down, the task fails rather than falling back. Acceptable for v1; add retry-with-fallback in Phase 4 if needed.

---

## Pattern 2: Telegram Project Registration (/addproject)

---

### Approach 2A: Single /addproject Command with Inline Args

**Source:** [python-telegram-bot CommandHandler docs](https://docs.python-telegram-bot.org/en/v22.4/)

#### Description
One command parses all args positionally or via flags: `/addproject /path/to/repo --topic 12345 --provider claude`. Validation runs immediately, success/error returned in one reply.

#### Pros
- Simplest implementation — one handler, one function
- Power-user friendly (copy-paste from shell)
- No conversation state to manage (no timeout/concurrency bugs)
- Easy to script/automate from another bot or CLI

#### Cons
- `/addproject` message is hard to type correctly on mobile
- Zero UX guidance — user must know the exact format
- Validation error messages are per-attempt, not interactive
- Cannot guide user to correct mistakes (e.g., wrong path → dead end)

#### Complexity
**Estimate:** Easy — 2-3 hours
**Why:** Single `MessageHandler` for `/addproject`, `args` parsing, path/git validation, `db.py` insert. No state.

#### Example Source
```python
async def addproject(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # /addproject /home/user/myapp --topic 12345 --provider claude
    parser = parse_args(ctx.args)  # simple argparse-style
    path   = parser.path
    if not os.path.isdir(path):
        return await update.message.reply_text(f"Path not found: {path}")
    if not os.path.isdir(f"{path}/.git"):
        return await update.message.reply_text(f"Not a git repo: {path}")
    # check topic exists in bot
    # insert into db
    await update.message.reply_text(f"Project registered: {parser.name}")
```

---

### Approach 2B: ConversationHandler Multi-Step Wizard

**Source:** [python-telegram-bot ConversationHandler v22.4](https://docs.python-telegram-bot.org/en/v22.4/telegram.ext.conversationhandler.html) | [nestedconversationbot.py example](https://docs.python-telegram-bot.org/en/v21.7/examples.nestedconversationbot.html)

#### Description
`/addproject` starts a conversation. Bot asks one question at a time: (1) project path, (2) display name, (3) Telegram topic ID, (4) default provider. Each step validates the input, shows error + retry on failure, confirms on success. Final step shows a summary with Confirm/Cancel buttons.

#### Pros
- Mobile-friendly: user types simple values one at a time
- Per-step validation with clear error messages and retry
- Cannot submit invalid data (path is validated before asking for name)
- Consistent with UX patterns used in banking/onboarding bots

#### Cons
- `ConversationHandler` requires `concurrent_updates=False` — blocks other updates
- Timeout complexity: what if user starts but doesn't finish? Need `conversation_timeout`
- State persistence needed if bot restarts mid-conversation (add `persistence=True`)
- 4x more code than Approach 2A

#### Complexity
**Estimate:** Medium — 5-8 hours
**Why:** State machine definition, per-step handlers, validation, inline keyboard for confirmation, conversation timeout handling, integration with existing `db.py`. Known edge case: user sends other commands during open conversation (need fallback handlers). See GitHub issue #4707 for known ConversationHandler timeout bug in v21.10.

#### Example Source
```python
PATH, NAME, TOPIC, PROVIDER, CONFIRM = range(5)

async def ask_path(update, ctx):
    await update.message.reply_text("Enter the absolute path to the project:")
    return PATH

async def receive_path(update, ctx):
    path = update.message.text.strip()
    if not os.path.isdir(path) or not os.path.isdir(f"{path}/.git"):
        await update.message.reply_text("Not a valid git repo. Try again:")
        return PATH
    ctx.user_data["path"] = path
    await update.message.reply_text("Project name (display):")
    return NAME

conv = ConversationHandler(
    entry_points=[CommandHandler("addproject", ask_path)],
    states={
        PATH: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_path)],
        NAME: [...],
        TOPIC: [...],
        PROVIDER: [...],
        CONFIRM: [CallbackQueryHandler(do_confirm, pattern="^confirm$"),
                  CallbackQueryHandler(do_cancel, pattern="^cancel$")],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    conversation_timeout=120,
)
```

---

### Approach 2C: Template Form (bot sends template, user edits and replies)

**Source:** [Telegram bot form pattern — community](https://community.latenode.com/t/creating-a-multi-step-conversation-flow-in-a-telegram-bot/10484)

#### Description
Bot sends a pre-filled template message as a code block: user copies it to the reply field, fills in the blanks, and replies. Bot parses the filled template with regex. Used in low-latency bots where conversation state is expensive to manage.

#### Pros
- No conversation state machine
- User sees all fields at once (good for comparing what they've entered)
- Works well for power users who know the schema

#### Cons
- Telegram doesn't support "edit and reply to a specific message" natively on all clients
- Users on mobile will paste the template, edit, and send — fragile UX
- Template parsing with regex is brittle if user reformats the block
- Poor error recovery: one bad field invalidates the whole submission

#### Complexity
**Estimate:** Easy-Medium — 3-4 hours
**Why:** Single handler, regex parse, validation. But edge cases (user reformats template, partial fills) add hidden complexity.

---

### Comparison Matrix — Pattern 2: /addproject

| Criteria | 2A: Single Command | 2B: ConversationHandler | 2C: Template Form |
|----------|-------------------|------------------------|------------------|
| Complexity | Low | Medium | Low-Medium |
| Mobile UX | Poor | High | Medium |
| Validation clarity | Low | High | Low |
| State management risk | None | Medium | None |
| Code volume | ~30 LOC | ~150 LOC | ~60 LOC |
| Extensible (edit project) | Easy | Medium | Hard |

---

### Recommendation — Pattern 2

**Selected:** Approach 2B (ConversationHandler Wizard)

**Rationale:**
The bot is the primary interface for an operator managing 10 projects from a phone. Typing `/addproject /home/dld/projects/openclaw --topic 12345 --provider claude` correctly on mobile is a support ticket waiting to happen. The wizard pattern (used by every production Telegram onboarding flow) prevents invalid submissions at the input layer, not after. The `concurrent_updates=False` constraint is acceptable since this is a single-admin bot.

**Key factors:**
1. Per-step validation catches errors before they propagate to `db.py`
2. Confirm/Cancel step with project summary prevents accidental insertions
3. `conversation_timeout=120` cleans up abandoned wizards automatically

**Trade-off accepted:** 4x more code than 2A. Worth it because bad project registrations (wrong path, wrong topic ID) cause silent failures in task dispatch — debugging those costs more time than writing the wizard.

---

## Pattern 3: Global DLD Skills Distribution

---

### Approach 3A: Native ~/.claude/skills/ Resolution (Claude Code built-in)

**Source:** [Claude Code Global Skills Issue #25209](https://github.com/anthropics/claude-code/issues/25209) | [Project commands override issue #16275](https://github.com/anthropics/claude-code/issues/16275)

#### Description
Place DLD skills in `~/.claude/skills/` (or `~/.claude/commands/`). Claude Code discovers global skills automatically in all projects. Project-level skills in `.claude/skills/` are intended to override globals with the same name.

#### Pros
- Zero setup per project — skills are available everywhere on the VDS immediately
- Skills update once (in `~/.claude/`), all projects benefit
- Native Claude Code behavior, no scripts or symlinks needed

#### Cons
- **Known bug (issue #25209, Feb 2026):** Project-level skills do NOT silently override global ones — both appear in the picker. User must choose between two versions.
- **Known bug (issue #16275, Jan 2026):** Global commands take precedence over project commands in some CC versions — opposite of documented behavior.
- Skill resolution behavior differs between CC versions; treat as unstable API
- No mechanism to pin a project to a specific skill version

#### Complexity
**Estimate:** Easy — 1-2 hours (copy skills to `~/.claude/`)
**Why:** File copy only. But the override conflict bug means you cannot rely on this as a conflict-resolution strategy — projects with custom versions of shared skills will show duplicates.

#### Example Source
```bash
# setup-vps.sh Phase 3 addition
mkdir -p ~/.claude/skills
cp -r ~/dev/dld/.claude/skills/* ~/.claude/skills/
# All 10 projects now see DLD skills globally
# WARNING: project-level overrides will COEXIST, not replace (CC bug #25209)
```

---

### Approach 3B: Symlinks from Projects to Shared Folder

**Source:** [Skills reference $CLAUDE_PROJECT_DIR issue #106](https://github.com/parcadei/Continuous-Claude-v3/issues/106)

#### Description
A canonical skills folder lives at `~/dld-skills/`. Each project's `.claude/skills/` directory contains symlinks to the canonical files. When DLD skills update, all projects pick up changes immediately (no copy needed).

#### Pros
- Single source of truth for skill content (no copy drift)
- Updates propagate instantly to all projects
- Project-level symlinks satisfy Claude Code's path resolution (no CC bugs with paths)
- Can override a specific skill per-project by replacing its symlink with a real file

#### Cons
- Symlinks must be created/updated for each new project (setup step)
- If canonical folder moves or is deleted, all projects break silently
- Confusing for human readers (`.claude/skills/spark` → `~/dld-skills/spark`)
- Referenced path issue (#106): some skills use `$CLAUDE_PROJECT_DIR/.claude/scripts/` which breaks when scripts live in the canonical folder

#### Complexity
**Estimate:** Easy-Medium — 3-5 hours
**Why:** `ln -s` commands in `addproject` flow or a helper script. But the `$CLAUDE_PROJECT_DIR` vs `$CLAUDE_CONFIG_DIR` path confusion (issue #106) requires careful script path design.

#### Example Source
```bash
# Link DLD skills into a project
SKILLS_SOURCE="$HOME/.claude/skills"      # canonical
PROJECT_SKILLS="$PROJECT_PATH/.claude/skills"
mkdir -p "$PROJECT_SKILLS"
for skill_dir in "$SKILLS_SOURCE"/*/; do
    skill_name=$(basename "$skill_dir")
    ln -sfn "$skill_dir" "$PROJECT_SKILLS/$skill_name"
done
```

---

### Approach 3C: setup-vps.sh Copies Skills on Deploy/Update

**Source:** DLD existing pattern (`scripts/vps/setup-vps.sh`)

#### Description
`setup-vps.sh --phase3` copies DLD skills from the DLD repo into `~/.claude/skills/`. A cron job or manual re-run refreshes them when DLD framework updates. Each project uses the global `~/.claude/` location — no per-project setup.

#### Pros
- Explicit: skills are promoted deliberately, not silently
- Easy to version-pin: copy from a specific DLD git tag
- Idempotent: running setup-vps.sh multiple times is safe
- Consistent with the existing VPS setup script pattern in the project

#### Cons
- Skills go stale between updates (operator must remember to run setup)
- Copy drift: `~/.claude/skills/spark` may differ from `dld/.claude/skills/spark`
- No per-project customization path (all projects get the same global copy)

#### Complexity
**Estimate:** Easy — 1-2 hours
**Why:** `rsync` or `cp -r` call added to existing `setup-vps.sh`. Cron entry for periodic refresh is optional.

---

### Comparison Matrix — Pattern 3: Global Skills

| Criteria | 3A: Native ~/.claude/ | 3B: Symlinks | 3C: setup-vps.sh copy |
|----------|----------------------|-------------|----------------------|
| Complexity | Low | Low-Medium | Low |
| Update propagation | Immediate (on file write) | Immediate | Manual |
| Override reliability | Broken (CC bug) | Works | Works |
| Per-project customization | Unreliable | Clean | Not supported |
| Operational risk | CC bug exposure | Broken canonical | Stale skills |

---

### Recommendation — Pattern 3

**Selected:** Approach 3C (setup-vps.sh copy) as primary, with 3A as the runtime delivery mechanism.

**Rationale:**
The `~/.claude/skills/` location is the correct runtime delivery point — Claude Code reads it. The question is how skills get there. Given the CC override bugs (#25209, #16275), we should not rely on project-level symlinks to resolve conflicts. Instead: skills live in `~/.claude/skills/` (global, available everywhere), and `setup-vps.sh --update-skills` refreshes them from the DLD repo on demand.

For the 10-project, single-VDS setup, skill staleness between manual updates is an acceptable risk. The operator controls update timing via the existing VPS management workflow.

**Key factors:**
1. Avoids CC bug exposure from per-project overrides
2. Consistent with existing setup-vps.sh pattern — no new infrastructure
3. `rsync --delete` ensures old skills are removed when renamed in DLD

**Trade-off accepted:** Skills can go stale between DLD framework updates. Mitigation: add `update-skills` step to the Phase 3 VPS setup checklist and the `/upgrade` DLD command.

---

## Pattern 4: Nexus as Runtime SSOT

---

### Approach 4A: Direct CLI Subprocess (`bootstrap get-project-context`)

**Source:** [nexus-agents benchmark: CLI subprocess vs API adapter latency](https://github.com/williamzujkowski/nexus-agents/issues/694) | [Building Nexus-Agents multi-model orchestration](https://williamzujkowski.github.io/posts/building-nexus-agents-what-i-learned-creating-a-multi-model-ai-orchestration-system/)

#### Description
`orchestrate.sh` calls `bootstrap get-project-context <project_id>` before each task dispatch. Parses JSON stdout with `jq`. Nexus CLI handles all data resolution (secrets, project config, provider keys).

#### Pros
- Nexus CLI is already installed on the VDS (global tool)
- No additional server process to manage
- `bootstrap` handles auth, caching, retries internally
- No custom adapter code

#### Cons
- Each call spawns a subprocess: cold-start latency 200-500ms (from nexus-agents benchmark data)
- If Nexus is down or slow, every task dispatch blocks on the timeout
- Subprocess spawn per task × 3 concurrent slots = 3 concurrent CLI processes
- Nexus CLI may not support all query types needed (project metadata vs task metadata)

#### Complexity
**Estimate:** Easy — 2-4 hours
**Why:** One bash function wrapping `bootstrap get-project-context` + `jq` parsing. Fallback: if CLI fails, read cached file.

#### Example Source
```bash
get_nexus_context() {
    local project_id="$1"
    local timeout=5
    context=$(timeout "$timeout" bootstrap get-project-context "$project_id" 2>/dev/null)
    if [ $? -ne 0 ] || [ -z "$context" ]; then
        # Fallback to cached file (Approach 4C)
        context=$(cat "/var/dld/nexus-cache/${project_id}.json" 2>/dev/null || echo "{}")
    fi
    echo "$context"
}
```

---

### Approach 4B: Nexus MCP Server Query via Adapter

**Source:** [Building Nexus-Agents: MCP Foundation](https://williamzujkowski.github.io/posts/building-nexus-agents-what-i-learned-creating-a-multi-model-ai-orchestration-system/)

#### Description
Nexus exposes an MCP server. A Python adapter script queries it via HTTP/stdio before each task. Orchestrator calls the adapter.

#### Pros
- Rich query interface (MCP tools map to structured operations)
- No CLI subprocess overhead if MCP server is kept warm

#### Cons
- MCP server must be running as a daemon on the VDS (new process to manage)
- HTTP overhead if network-bound; stdio MCP requires persistent connection management
- Over-engineered: MCP is designed for LLM↔tool communication, not bash↔data queries
- Failure mode: MCP server crash blocks all task dispatch

#### Complexity
**Estimate:** Hard — 12-20 hours
**Why:** Nexus MCP adapter doesn't exist yet for this use case. Building it requires MCP protocol handling, bash-to-MCP bridge, service management. Maintenance burden disproportionate to benefit.

---

### Approach 4C: Cached File (Nexus writes JSON, orchestrator reads file)

**Source:** [Pipeline Performance: Caching and Optimization — Grizzly Peak](https://www.grizzlypeaksoftware.com/library/pipeline-performance-caching-and-optimization-techniques-08ybeviq)

#### Description
Nexus (or a cron job calling `bootstrap`) writes project context to `/var/dld/nexus-cache/<project_id>.json` periodically (e.g., every 5 minutes, or on project change events). Orchestrator reads this file directly — no subprocess, no network call.

#### Pros
- Zero latency on hot path (file read is microseconds)
- Fully resilient: if Nexus is down, last-known-good cache is used
- Simple: orchestrator is just `jq -r '.provider' /var/dld/nexus-cache/$pid.json`
- Consistent with ADR-011 (state files as SSOT) and ADR-007 (caller-reads pattern)

#### Cons
- Cache staleness window (5 min default): project config changes don't take effect immediately
- Requires a refresh mechanism (cron or event-driven from Nexus CLI hook)
- Cache miss on first run (new project not yet cached)

#### Complexity
**Estimate:** Easy — 3-5 hours
**Why:** Cache writer script (cron + `bootstrap` call), cache reader in `orchestrate.sh`, cache invalidation hook in `addproject` flow. Standard pattern, no exotic dependencies.

#### Example Source
```bash
# nexus-cache-refresh.sh (run by cron every 5 min)
for project_id in $(bootstrap list-projects --ids); do
    bootstrap get-project-context "$project_id" \
        > "/var/dld/nexus-cache/${project_id}.json.tmp" && \
        mv "/var/dld/nexus-cache/${project_id}.json.tmp" \
           "/var/dld/nexus-cache/${project_id}.json"
done

# orchestrate.sh reads cache
NEXUS_CTX=$(cat "/var/dld/nexus-cache/${PROJECT_ID}.json" 2>/dev/null || echo "{}")
PROVIDER=$(echo "$NEXUS_CTX" | jq -r '.provider // "claude"')
```

---

### Approach 4D: Nexus Daemon with REST API

**Source:** (general REST API pattern, no specific source needed)

#### Description
A lightweight Python FastAPI/Flask service wraps Nexus CLI and exposes a REST API. Orchestrator calls `curl http://localhost:8080/projects/$id`.

#### Pros
- Fast queries (no subprocess per call)
- Can add caching, connection pooling, webhooks

#### Cons
- New service to deploy, monitor, restart
- REST API must be implemented and maintained
- Overkill for a single-admin 10-project setup

#### Complexity
**Estimate:** Hard — 15-25 hours

---

### Comparison Matrix — Pattern 4: Nexus Integration

| Criteria | 4A: CLI Subprocess | 4B: MCP Adapter | 4C: Cached File | 4D: REST API |
|----------|-------------------|-----------------|--------------------|--------------|
| Complexity | Low | High | Low | High |
| Latency | 200-500ms/call | ~50ms (warm) | <1ms | ~5ms |
| Resilience | Medium | Low | High | Medium |
| Freshness | Real-time | Real-time | ±5 min | Real-time |
| New infra needed | No | Yes (daemon) | No | Yes (service) |
| Alignment with ADRs | Medium | Low | High | Low |

---

### Recommendation — Pattern 4

**Selected:** Approach 4C (Cached File) with 4A as the cache writer

**Rationale:**
Orchestrator latency is dominated by the LLM run time (minutes), not the context lookup (milliseconds). Spending 500ms on a `bootstrap` subprocess for context that changes hourly is acceptable — but if Nexus is down at 3am when a task fires, the system should not block. The cache file pattern gives both: fast reads on the hot path and full resilience when Nexus is unavailable.

The refresh mechanism (`cron` every 5 minutes calling Approach 4A) keeps the cache fresh without exposing the hot path to subprocess latency. Cache invalidation on `/addproject` (immediate refresh for the new project) eliminates the first-run miss problem.

**Key factors:**
1. Aligns with ADR-011 (state as files) and ADR-007 (caller-reads)
2. Zero latency on the orchestration hot path
3. Resilient to Nexus downtime — last-known-good always available

**Trade-off accepted:** 5-minute staleness window for project config changes. Acceptable: operators making live config changes can manually trigger `nexus-cache-refresh.sh` or wait the window.

---

## Pattern 5: VPS Setup Documentation

---

### Approach 5A: Inline Spec Section (setup instructions in FTR-148 spec)

**Source:** Existing DLD spec pattern (`ai/features/`)

#### Description
The FTR-148 spec document includes a "VPS Setup" section with ordered steps, code blocks, and checkboxes. Operator reads the spec and executes manually.

#### Pros
- Zero new files — setup lives with the feature that needs it
- Easy to keep in sync: spec changes = setup changes in same PR
- Discoverable: anyone reading the spec sees the setup requirements

#### Cons
- Specs are discarded/archived after implementation — setup docs become hard to find
- Markdown checkboxes are not interactive (cannot track which steps completed)
- Cannot be re-run safely (not idempotent)
- Step count for Phase 3 is 15-20 steps — inline spec becomes unwieldy

#### Complexity
**Estimate:** Easy — 1-2 hours (writing)

---

### Approach 5B: Separate Bash Script (setup-vps.sh Phase 3 extension)

**Source:** [Complete Ubuntu VPS Checklist — MassiveGRID](https://massivegrid.com/blog/complete-ubuntu-vps-checklist/) | Existing `scripts/vps/setup-vps.sh` pattern

#### Description
Extend the existing `setup-vps.sh` with a `--phase3` flag. Each step is a bash function: install deps, configure paths, copy skills, create cron jobs, set env vars. The script is idempotent (checks before acting).

#### Pros
- Rerunnable and idempotent — safe to run again after partial failure
- Version-controlled alongside the code it sets up
- Follows existing DLD pattern (setup-vps.sh already exists)
- Easily tested on a fresh Ubuntu 24.04 VM before VDS deployment

#### Cons
- Script complexity grows with each phase (Phase 1+2+3 in one file)
- Bash error handling requires discipline (`set -euo pipefail`, trap)
- Harder to read than a checklist for human-driven setup steps

#### Complexity
**Estimate:** Medium — 4-6 hours
**Why:** Idempotent bash functions for each setup action, conditional checks, error traps. Testing on clean VM adds time but is essential.

#### Example Source
```bash
#!/usr/bin/env bash
set -euo pipefail

phase3_gemini_runner() {
    echo "==> Installing gemini-runner.sh"
    cp scripts/vps/gemini-runner.sh /usr/local/lib/dld/
    chmod +x /usr/local/lib/dld/gemini-runner.sh
}

phase3_skills() {
    echo "==> Syncing DLD skills to ~/.claude/"
    rsync -a --delete .claude/skills/ ~/.claude/skills/
}

phase3_nexus_cache() {
    echo "==> Setting up nexus cache directory"
    mkdir -p /var/dld/nexus-cache
    # Install cron: refresh every 5 min
    (crontab -l 2>/dev/null; echo "*/5 * * * * /usr/local/lib/dld/nexus-cache-refresh.sh") | crontab -
}

case "${1:-}" in
  --phase3) phase3_gemini_runner; phase3_skills; phase3_nexus_cache ;;
  *) echo "Usage: $0 --phase3" ;;
esac
```

---

### Approach 5C: Interactive Setup Wizard (bash script with prompts)

**Source:** [Automate Ubuntu VPS Setup with Ansible](https://massivegrid.com/blog/ansible-automate-ubuntu-vps-setup/) — contrasted with interactive pattern

#### Description
A `wizard.sh` script asks questions interactively: "Enter your Gemini API key:", "Enter Nexus project ID:", confirms choices, and executes setup steps. Tracks progress in a state file.

#### Pros
- Guides operator through setup without reading docs
- Collects secrets interactively (no hardcoded values)
- Progress state file allows resuming interrupted setup

#### Cons
- Cannot be run non-interactively (CI, remote SSH without TTY breaks it)
- Questions become stale as requirements change — maintenance burden
- Adds ~200 LOC for prompting/state tracking on top of the actual setup logic
- For a single-admin system, a wizard is more ceremony than value

#### Complexity
**Estimate:** Hard — 8-12 hours (relative to value delivered)
**Why:** Interactive prompts + state file + resume logic + TTY detection + CI bypass mode. The wizard complexity exceeds the setup complexity it is hiding.

---

### Comparison Matrix — Pattern 5: VPS Setup

| Criteria | 5A: Inline Spec | 5B: Bash Script | 5C: Interactive Wizard |
|----------|----------------|-----------------|----------------------|
| Complexity | Low | Medium | High |
| Rerunnable | No | Yes | Yes |
| Discoverability | Good (in spec) | Good (in scripts/) | Good |
| Idempotent | No | Yes | Partial |
| CI/automation friendly | No | Yes | No |
| Long-term maintainability | Low | High | Low |

---

### Recommendation — Pattern 5

**Selected:** Approach 5B (Bash Script extension) with a brief inline checklist in the spec for context.

**Rationale:**
`setup-vps.sh` already exists in the project. Adding `--phase3` is the natural extension: consistent pattern, idempotent, version-controlled, rerunnable on fresh VDS without reading docs. The inline spec section (5A) should still exist as a 5-line summary pointing to the script — useful for audit and onboarding.

**Key factors:**
1. Idempotent: safe to run after partial failures or on a rebuilt VDS
2. Consistent with existing Phase 1/2 setup scripts
3. CI/automation friendly: can run in a provisioning pipeline without a human

**Trade-off accepted:** More code than a checklist. Worth it: production VDS setups that fail halfway through leave the system in an undefined state. Idempotent scripts recover gracefully.

---

## Full Comparison Matrix (All Patterns)

| Pattern | Selected Approach | Complexity | Key Reason |
|---------|------------------|------------|------------|
| Provider Routing | 1A: Static Metadata | Low | Deterministic, zero overhead, right scale |
| /addproject | 2B: ConversationHandler | Medium | Mobile UX, per-step validation prevents bad registrations |
| Global Skills | 3C: setup-vps.sh copy | Low | Avoids CC override bugs, consistent with existing pattern |
| Nexus Integration | 4C: Cached File | Low | Zero hot-path latency, resilient to Nexus downtime |
| VPS Setup | 5B: Bash Script | Medium | Idempotent, rerunnable, consistent with Phase 1/2 |

---

## Research Sources

- [Automate tasks with Gemini CLI headless mode](https://geminicli.com/docs/cli/tutorials/automation/) — `gemini --output-format json -p "..."` → `jq -r '.response'` normalization pattern
- [Gemini CLI Structured JSON Output issue #8022](https://github.com/google-gemini/gemini-cli/issues/8022) — official JSON schema design for `--output-format json` flag
- [Claude Code --print --output-format=json programmatic mode](https://gist.github.com/JacobFV/2c4a75bc6a835d2c1f6c863cfcbdfa5a) — `{"type":"result","result":"..."}` envelope for claude runner normalization
- [AI Agent Model Routing — Zylos Research (Mar 2026)](https://zylos.ai/research/2026-03-02-ai-agent-model-routing) — taxonomy of routing strategies, cost/quality tradeoff data, static vs dynamic routing comparison
- [Practical Gemini CLI: Intelligent Model Router](https://medium.com/google-cloud/practical-gemini-cli-intelligent-model-router-e01e543ec438) — Gemini's own `classifierStrategy.ts` implementation, PRO/FLASH complexity rubric
- [Multi-LLM Routing Strategies — AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/multi-llm-routing-strategies-for-generative-ai-applications-on-aws/) — static vs dynamic routing patterns with implementation examples
- [python-telegram-bot ConversationHandler v22.4 docs](https://docs.python-telegram-bot.org/en/v22.4/telegram.ext.conversationhandler.html) — multi-step wizard pattern, state machine, timeout handling
- [ConversationHandler timeout bug #4707](https://github.com/python-telegram-bot/python-telegram-bot/issues/4707) — known edge case when conversation spans multiple groups (v21.10)
- [Claude Code global skills override bug #25209](https://github.com/anthropics/claude-code/issues/25209) — project-level skills do NOT silently override global skills (both appear)
- [Project commands precedence bug #16275](https://github.com/anthropics/claude-code/issues/16275) — global commands incorrectly take precedence over project commands in some CC versions
- [Skills reference $CLAUDE_PROJECT_DIR path issue #106](https://github.com/parcadei/Continuous-Claude-v3/issues/106) — symlink approach fails when skills reference `$CLAUDE_PROJECT_DIR` for helper scripts
- [nexus-agents CLI subprocess vs API adapter latency benchmark](https://github.com/williamzujkowski/nexus-agents/issues/694) — 200-500ms cold-start for CLI subprocess, justifies cache-file pattern
- [Building Nexus-Agents multi-model orchestration](https://williamzujkowski.github.io/posts/building-nexus-agents-what-i-learned-creating-a-multi-model-ai-orchestration-system/) — MCP-first vs CLI-first adapter strategies, real-world routing learnings
- [Complete Ubuntu VPS Checklist — MassiveGRID](https://massivegrid.com/blog/complete-ubuntu-vps-checklist/) — 48-step idempotent setup reference for Ubuntu 24.04 VPS production readiness
- [Multi-Model Router Patterns — Grizzly Peak](https://www.grizzlypeaksoftware.com/library/multi-model-architectures-router-patterns-lmlktp56) — Node.js router implementation patterns with static vs dynamic trade-off analysis
