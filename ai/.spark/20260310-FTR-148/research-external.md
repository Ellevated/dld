# External Research — FTR-148 Multi-Project Orchestrator Phase 3

## Best Practices

### 1. Gemini CLI Headless Mode via Positional Argument + `--output-format json`

**Source:** [Gemini CLI Headless Mode Reference](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/headless.md)

**Summary:** Gemini CLI automatically enters headless mode when (a) the query is passed as a positional argument without the interactive flag, or (b) stdin is not a TTY. Use `--output-format json` for a single JSON object `{response, stats, error}` or `--output-format stream-json` for JSONL. Exit codes: 0 success, 1 API failure, 42 input error, 53 turn-limit exceeded.

**Why relevant:** gemini-runner.sh on VDS can use `gemini "PROMPT" --output-format json` and parse `response` field with `jq`. Auth must be done once via `NO_BROWSER=true gemini` (merged PR #3713, Jul 2025) which prints an OAuth URL to paste in local browser. After that, credentials persist in `~/.gemini/`. For CI/unattended runs, `GEMINI_API_KEY` env var skips OAuth entirely.

---

### 2. Codex CLI `exec --full-auto` for Non-Interactive Execution

**Source:** [How Codex CLI Flags Actually Work](https://www.vincentschmalbach.com/how-codex-cli-flags-actually-work-full-auto-sandbox-and-bypass/) and [OpenAI Codex docs full text](https://developers.openai.com/codex/llms-full.txt)

**Summary:** `codex exec --full-auto "PROMPT"` runs without approval prompts with `workspace-write` sandbox. Structured JSON output is possible via `--json` flag (exec mode with schema). Session JSONL logs land at `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`. There is NO built-in `--json-log PATH` flag yet (open issue #2288, Aug 2025). True headless non-TTY mode existed as feature request (issue #4219, closed Oct 2025) — status is implemented but no stable streaming JSON comparable to Claude Code. Auth: ChatGPT Pro/Plus subscription via browser sign-in, or `OPENAI_API_KEY` env var for API billing.

**Why relevant:** `codex-runner.sh` already exists in Phase 1. Extending to use `codex exec --full-auto --sandbox workspace-write "PROMPT"` is the correct headless form. Output capture: parse stdout directly (final text to stdout) or glob the newest JSONL rollout file.

---

### 3. Claude Code Skill/CLAUDE.md Resolution Order and Global Skills

**Source:** [Claude Code — Where Skills Live](https://code.claude.com/docs/en/slash-commands) and [Skills and subagents override priority](https://code.claude.com/docs/en/features-overview)

**Summary:** Skills stored at four levels, resolved in strict priority order:

| Priority | Location | Path |
|---|---|---|
| 1 (highest) | Enterprise/Managed | system managed-settings.json |
| 2 | Personal/User | `~/.claude/skills/<name>/SKILL.md` |
| 3 | Project | `.claude/skills/<name>/SKILL.md` |
| 4 | Plugin | `<plugin>/skills/<name>/SKILL.md` (namespaced) |

When same skill name exists at multiple levels, higher priority wins. CLAUDE.md loads identically: `~/.claude/CLAUDE.md` (user global) is loaded first, then project `.claude/CLAUDE.md`, then subdirectory CLAUDE.md files on demand. `.claude/rules/` files load at session start (or on matching file open). Skills at user-scope (`~/.claude/skills/`) are available in every project without any per-project config.

**Why relevant:** Global DLD skills should live at `~/.claude/skills/` on the VDS. Each project's `.claude/skills/` can override a specific skill by name. `~/.claude/CLAUDE.md` acts as the global rules base; project-level CLAUDE.md appends/overrides per the same cascade. This is exactly the architecture needed for "update once, all projects pick up."

---

### 4. Python-Telegram-Bot ConversationHandler for Multi-Step `/addproject`

**Source:** [PTB ConversationHandler v22.5 docs](https://docs.python-telegram-bot.org/en/v22.5/telegram.ext.conversationhandler.html) and [Context7 ConversationHandler example](https://context7.com/python-telegram-bot/python-telegram-bot/llms.txt)

**Summary:** `ConversationHandler` manages multi-step flows via `entry_points` (the `/addproject` command), `states` (dict of step → handlers), and `fallbacks` (e.g., `/cancel`). Each state handler returns the next state integer or `ConversationHandler.END`. State is per-user and per-chat by default. Use `context.user_data` dict to accumulate inputs across steps. **Warning:** PTB docs require `concurrent_updates=False` when using `ConversationHandler`. For registering new bot commands in Telegram's menu, call `await application.bot.set_my_commands([...])` at startup (or after project registration).

**Why relevant:** `/addproject` needs 4–5 steps (project path, git repo, topic_id, provider default, confirm). ConversationHandler is the idiomatic PTB pattern. Existing `telegram-bot.py` (Phase 1) uses PTB v21.9+, the API is stable across v21–v22.

---

### 5. MCP Querying from Shell Scripts via `mcpc` CLI

**Source:** [apify/mcp-cli — mcpc](https://github.com/apify/mcp-cli) and [Introducing mcpc](https://blog.apify.com/introducing-mcpc-universal-mcp-cli-client/)

**Summary:** `mcpc` (v0.1.11, Mar 2026) is a universal CLI MCP client. It maps MCP operations to shell commands, supports stdio and Streamable HTTP, and provides `--json` output for shell/jq integration. Example:

```bash
mcpc connect <server-stdio-cmd>
mcpc tools-call get_project_context project_id:="my-app"
```

Alternative: `mcp-cli` by Philipp Schmid (Jan 2026) — single binary (Bun-compiled), `mcp-cli call <tool> <args>` with JSON output, connection pooling daemon, designed specifically for AI coding agents.

**Why relevant:** Neither `mcpc` nor `mcp-cli` existed when the Nexus MCP server was built. Both are now production-ready for calling Nexus MCP from `orchestrate.sh`. Simpler alternative: Nexus CLI already exposes `bootstrap get-project-context`, `bootstrap get-secret`, etc. — direct CLI calls avoid MCP overhead entirely (no schema loading, no daemon).

---

## Libraries/Tools

| Library | Version | Pros | Cons | Use Case | Source |
|---|---|---|---|---|---|
| `@google/gemini-cli` | latest (v0.7+) | Free with Google account (Gemini 2.5 Pro), open source (97k stars), headless JSON mode, GEMINI_API_KEY env for unattended | Requires one-time OAuth on headless (NO_BROWSER flow), NodeJS runtime | gemini-runner.sh | [github](https://github.com/google-gemini/gemini-cli) |
| `codex` (OpenAI) | latest (Rust, 0.39+) | ChatGPT Pro subscription covers it, `exec --full-auto`, workspace-write sandbox | No clean `--json-log` flag, JSONL logs in date-sharded path, headless TTY issues partially fixed | codex-runner.sh (exists) | [github](https://github.com/openai/codex) |
| `python-telegram-bot` | v21.9+ (v22.5 latest) | Stable ConversationHandler, async, set_my_commands, used in Phase 1 | `concurrent_updates=False` required with ConversationHandler | /addproject flow | [docs](https://docs.python-telegram-bot.org/en/v22.5/) |
| `mcpc` (Apify) | v0.1.11 | Universal MCP client, shell-scriptable, JSON output, stdio + HTTP | Extra dependency, overkill if Nexus CLI suffices | Nexus MCP runtime queries | [github](https://github.com/apify/mcp-cli) |
| `mcp-cli` (Schmid) | v0.3.0 | Single binary, 99% token reduction vs static loading, designed for Claude/Gemini/Codex agents | Bun required, newer/less battle-tested | Dynamic MCP tool calls | [philschmid.de](https://www.philschmid.de/mcp-cli) |
| Bootstrap CLI (Nexus) | existing | Already installed, `get-project-context`, `get-secret`, no MCP overhead | Not MCP protocol — direct CLI only | Nexus runtime queries from bash | existing |

**Recommendation:** For Gemini runner, `@google/gemini-cli` with `GEMINI_API_KEY` is the cleanest path — no OAuth dance on VDS, just `GEMINI_API_KEY=xxx gemini "prompt" --output-format json`. For Nexus runtime queries, use the Nexus `bootstrap` CLI directly (simpler than spinning up mcpc). Reserve `mcpc` for if Nexus exposes capabilities not reachable via CLI.

---

## Production Patterns

### Pattern 1: Provider Dispatch Table in Shell (gabrielkoerich/orchestrator)

**Source:** [gabrielkoerich/orchestrator](https://github.com/gabrielkoerich/orchestrator) — 218 releases, 4 stars (small but production-active)

**Description:** Single bash orchestrator routes tasks to AI CLI agents (`claude`, `codex`, `opencode`) by reading a `provider` field from task metadata. Uses GitHub Issues as task backend with labels for routing. Agents run in isolated git worktrees. The dispatch pattern is a simple `case "$PROVIDER" in claude) ... ;; codex) ... ;; gemini) ... ;; esac` block, with a shared result-capture wrapper.

**Real-world use:** Active production use — 218 releases since Feb 2026. Directly matches the DLD architecture (Pueue + bash + per-task provider).

**Fits us:** Yes — confirms the case-statement dispatch pattern. The per-task `provider` column in SQLite is the right SSOT. `orchestrate.sh` reads `provider` from `task_log`, dispatches to the right runner script.

---

### Pattern 2: Env-Var Auth + Headless Wrapper Script per Provider

**Source:** [Claude Code Bridge (ccb)](https://github.com/bfly123/claude_code_bridge) — 1.1k stars, Claude + Codex + Gemini multi-AI collaboration

**Description:** Separate runner scripts per provider (`claude_runner`, `codex_runner`, `gemini_runner`), each configured via env vars (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`). A shared dispatcher selects runner based on task config. Each runner normalizes output to a common format before writing to a result file.

**Real-world use:** 1.1k stars, actively maintained Feb 2026. Pattern aligns with the existing DLD `claude-runner.sh` / `codex-runner.sh` structure.

**Fits us:** Yes — DLD already has this structure. Adding `gemini-runner.sh` following the same pattern is the low-friction path.

---

### Pattern 3: ConversationHandler with `context.user_data` for Multi-Step Bot Commands

**Source:** [PTB conversationbot example](https://github.com/python-telegram-bot/python-telegram-bot/blob/master/docs/source/examples.conversationbot.rst)

**Description:** Each `/addproject` step stores partial data in `context.user_data` dict. Final step validates all fields, writes to SQLite (or `projects.json`), then calls `await bot.set_my_commands()` to update Telegram's command list. Pattern: `entry_points=[CommandHandler("addproject", start_add)]`, then states for PATH, REPO, TOPIC_ID, PROVIDER, CONFIRM. Cancel fallback cleans `user_data`.

**Real-world use:** Official PTB example, stable since v13. Used by thousands of production bots.

**Fits us:** Yes — `telegram-bot.py` already imports PTB. Adding `ConversationHandler` for `/addproject` is an additive change, no refactor needed.

---

### Pattern 4: Nexus CLI as Runtime SSOT (Direct CLI, Not MCP)

**Source:** [MCP vs CLI article — ayush mittal](https://ayushm4489.medium.com/everyones-using-mcp-i-built-a-cli-instead-here-s-what-i-learned-a0ccc838e411) and [mcp-cli token analysis](https://www.philschmid.de/mcp-cli)

**Description:** For orchestrator shell scripts that need config at runtime (secrets, deploy rules, docker configs), calling a CLI directly (`bootstrap get-project-context PROJECT_ID`) costs ~0 tokens of context overhead vs MCP schema loading (47k tokens for 6 servers). Pattern: shell script calls `bootstrap` → parses JSON stdout with `jq` → uses values inline. MCP is reserved for AI agents that need tool-calling semantics.

**Real-world use:** Cited by multiple production teams switching from MCP to CLI for shell-to-config integration.

**Fits us:** Yes — `orchestrate.sh` calling `bootstrap get-project-context` is simpler and more reliable than setting up `mcpc` as a daemon.

---

## Key Decisions Supported by Research

1. **Decision:** Add `gemini-runner.sh` that calls `gemini "PROMPT" --output-format json` with `GEMINI_API_KEY` env var
   **Evidence:** Gemini CLI headless mode merged Sep 2025 (PR #8564), `GEMINI_API_KEY` skips all OAuth. Auth is a one-time browser step via `NO_BROWSER=true` (merged Jul 2025, PR #3713). JSON output schema is stable with `response`, `stats`, `error` fields.
   **Confidence:** High

2. **Decision:** Codex runner uses `codex exec --full-auto --sandbox workspace-write "PROMPT"` (stdout capture, not JSONL)
   **Evidence:** `--full-auto` is the correct headless mode. No clean `--json-log` flag exists yet (issue #2288 open). Stdout contains the final text response. JSONL logs are in a date-sharded path with no easy session ID mapping. Simplest: capture stdout directly.
   **Confidence:** High

3. **Decision:** Global DLD skills go to `~/.claude/skills/` on VDS, not per-project `.claude/skills/`
   **Evidence:** Official Claude Code docs confirm `~/.claude/skills/<name>/SKILL.md` = user scope, available in all projects. Priority: user > project when same name. Project-level can override specific skills.
   **Confidence:** High (official docs, stable API)

4. **Decision:** Use PTB `ConversationHandler` for `/addproject` multi-step flow, store state in `context.user_data`
   **Evidence:** Official PTB pattern, stable v13–v22. Existing `telegram-bot.py` already uses PTB. No re-architecture needed — additive handler registration.
   **Confidence:** High

5. **Decision:** Nexus runtime queries via direct `bootstrap` CLI calls, not MCP over `mcpc`
   **Evidence:** Static MCP schema loading costs 47k tokens for 6 servers (mcp-cli analysis). Shell scripts don't benefit from MCP's tool-calling semantics. `bootstrap` CLI already exists and outputs JSON. `mcpc` adds a Node.js dependency for no practical gain in this context.
   **Confidence:** High

6. **Decision:** Per-task provider stored as column in SQLite `task_log`, dispatched in `orchestrate.sh` via case statement
   **Evidence:** gabrielkoerich/orchestrator uses identical pattern (GitHub Issues label = provider). DLD already has `run-agent.sh` provider dispatch. Extending existing `run-agent.sh` with `gemini` case is minimal change.
   **Confidence:** High

---

## Research Sources

- [Gemini CLI Headless Mode Reference](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/headless.md) — JSON output schema, exit codes, trigger conditions
- [Gemini CLI NO_BROWSER PR #3713](https://github.com/google-gemini/gemini-cli/pull/3713) — headless OAuth flow for VDS
- [Google Gemini CLI Announcement](https://blog.google/technology/developers/introducing-gemini-cli-open-source-ai-agent) — free GEMINI_API_KEY access
- [OpenAI Codex --full-auto flags explained](https://www.vincentschmalbach.com/how-codex-cli-flags-actually-work-full-auto-sandbox-and-bypass/) — sandbox modes, exec command
- [Codex issue #4219: headless non-interactive mode](https://github.com/openai/codex/issues/4219) — feature closed Oct 2025, confirms current state
- [Codex issue #2288: --json-log flag request](https://github.com/openai/codex/issues/2288) — confirms no clean JSON output flag
- [OpenAI Codex full docs](https://developers.openai.com/codex/llms-full.txt) — `codex exec --full-auto` spec
- [Claude Code — Where Skills Live](https://code.claude.com/docs/en/slash-commands) — user/project/enterprise precedence table
- [Claude Code — Features Overview](https://code.claude.com/docs/en/features-overview) — CLAUDE.md loading order, skill priority hierarchy
- [Claude Code — Settings Scopes](https://code.claude.com/docs/en/settings) — `~/.claude/` user scope definition
- [PTB ConversationHandler v22.5 docs](https://docs.python-telegram-bot.org/en/v22.5/telegram.ext.conversationhandler.html) — multi-step conversation API
- [PTB conversationbot.py example](https://github.com/python-telegram-bot/python-telegram-bot/blob/master/docs/source/examples.conversationbot.rst) — production pattern with states and user_data
- [apify/mcp-cli (mcpc)](https://github.com/apify/mcp-cli) — MCP from shell scripts
- [Introducing mcpc blog post](https://blog.apify.com/introducing-mcpc-universal-mcp-cli-client/) — CLI vs MCP trade-offs
- [mcp-cli by Philipp Schmid](https://www.philschmid.de/mcp-cli) — 99% token reduction analysis, CLI-first MCP pattern
- [MCP vs CLI article](https://ayushm4489.medium.com/everyones-using-mcp-i-built-a-cli-instead-here-s-what-i-learned-a0ccc838e411) — when CLI beats MCP for shell integration
- [gabrielkoerich/orchestrator](https://github.com/gabrielkoerich/orchestrator) — bash multi-provider routing production pattern
- [Claude Code Bridge (ccb)](https://github.com/bfly123/claude_code_bridge) — Claude + Codex + Gemini per-runner architecture
- [Claude Code Settings Reference](https://claudefa.st/blog/guide/settings-reference) — 5-scope hierarchy, project vs user precedence
- [Cross-Vendor Dynamic Model Fusion](https://dalehurley.com/posts/cross-vendor-dmf-paper) — orchestrator routing pattern research
