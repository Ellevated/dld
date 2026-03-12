# Research: LLM Subagent File Writing Reliability

**Date:** 2026-02-16
**Status:** COMPLETE
**Triggered by:** Bug Hunt pipeline — 0/36 agent invocations wrote files to disk across 3 iterations

---

## Problem Statement

In Claude Code multi-agent pipeline, subagents spawned via Task tool have Write/Edit tools available but consistently fail to use them for file output. Instead, they return all data in their text response.

**Evidence:**
- Iteration 1: OUTPUT_FILE approach — orchestrator didn't pass path → 0 files
- Iteration 2: Convention-based SESSION_DIR — agents ignored convention → 0 files
- Iteration 3: Spark-side fallback writes from response → 6/6 files

---

## Research Method

4 parallel Exa scouts + Sequential Thinking synthesis:
1. Claude Code subagent file writing patterns
2. LLM agent file-based IPC (2025-2026 SOTA)
3. Anthropic API tool_choice and forced tool use
4. Agent orchestration framework file patterns

---

## Critical Findings

### 1. tool_choice CANNOT solve this in Claude Code

Anthropic API supports `tool_choice: {"type": "tool", "name": "Write"}` — would force Write.

**BUT:**
- `tool_choice` forced modes (any, tool) **DON'T WORK with extended thinking**
- Opus 4.6 uses extended thinking by default → forced tool_choice = ERROR
- Only `auto` and `none` work with extended thinking
- Claude Code Task tool **doesn't expose** tool_choice parameter at all

**Conclusion:** Cannot force Write tool use at API level in Claude Code.

### 2. GitHub Issue #7032 — Known Systemic Bug

Subagents show Write tool calls in output but **files NOT created on disk**.
- Closed as duplicate (Sep 2025), related: #4462, #5178, #5465
- Root cause: subagent execution context file system permissions
- Even IF agents call Write, files may not appear

### 3. Industry Consensus = CALLER-WRITES

| Framework | Pattern |
|-----------|---------|
| **CrewAI** | `output_file` param — **framework** writes files, not agent |
| **LangGraph** | Files in external storage, state holds only reference URL |
| **OpenAI Swarm** | No built-in file I/O. Only context_variables |
| **AutoGen/MS** | Custom functions for file operations |
| **Anthropic Agent Teams** | Shared filesystem, no file artifact abstraction |

**All production frameworks: agents reason → framework persists output.**

### 4. Alternative Approaches (Evaluated and Rejected)

| Approach | Verdict | Reason |
|----------|---------|--------|
| Think Tool | Marginal | 54% improvement but still not guaranteed |
| Programmatic Tool Calling | Inapplicable | Requires API-level code_execution, not Claude Code |
| SubagentStop Hook | Over-engineering | Can reject but can't force; adds complexity |
| Prompt reframing | Insufficient | Issue #7032 means even successful Write may not persist |
| mode: bypassPermissions | Wrong axis | Controls ACCESS not SELECTION |

---

## Solution: Optimistic Agent Write with Caller Fallback

### Pattern

```
Agent receives task + output path
  → Does analysis
  → TRIES to write file (optimistic, via Write tool in tools list)
  → Returns structured response with content

Caller receives response
  → Check: does file exist on disk?
  → YES: Agent wrote it ✓ (bonus path)
  → NO: Caller writes from response content (primary path)
```

### Why This Is Correct

1. Matches CrewAI production pattern (most popular multi-agent framework)
2. Works around GitHub Issue #7032 (subagent Write may silently fail)
3. Works around tool_choice limitation (can't force with extended thinking)
4. Works around Claude Code Task tool limitation (no tool_choice param)
5. Zero data loss — response always contains the content
6. No extra API calls — same single agent invocation

### Implementation in DLD

1. **Rename** "Spark-side fallback" → "Caller-writes pattern" (PRIMARY, not fallback)
2. **Simplify agents** — remove "MANDATORY Write" pressure from prompts
3. **Keep Write tool** in agent tools list — free bonus if they write
4. **Standardize extraction** — create helper for response → structured data → file
5. **Document as ADR-007** — architectural decision, not workaround

---

## ADR-007: Caller-Writes Pattern for Subagent File Output

**Decision:** Subagent file output is handled by the caller (orchestrator/Spark), not by the subagent itself.

**Context:** 3 iterations of attempting to make subagents write files directly failed (0/36 success rate). Research confirms this is a known limitation (GitHub #7032) and that caller-writes is the industry standard pattern (CrewAI, LangGraph, etc.).

**Consequences:**
- Agents focus on reasoning, callers handle I/O
- Response always contains structured data for extraction
- File verification after each agent call (Glob check)
- Write tool remains in agent tools for opportunistic writes

---

## Part 2: Context Flooding in Multi-Agent Fan-Out/Fan-In

### Problem Statement

Caller-writes pattern (Part 1) solves WHO writes files, but not the context flooding problem:

```
6 agents × 5-15K tokens each = 30-90K tokens flooding orchestrator context
10 agents × 5-15K tokens each = 50-150K tokens flooding orchestrator context
```

When parallel subagents return simultaneously, their full responses accumulate in the orchestrator's context window, making downstream operations impossible.

### Research Method

2 parallel Exa scouts + 7-step Sequential Thinking synthesis:
1. Context flooding patterns in multi-agent LLM systems (2025-2026)
2. Claude Code context isolation mechanisms

### Industry Solutions

| Framework | Pattern | How It Works |
|-----------|---------|--------------|
| **LangGraph** | State reducers | `operator.add` — parallel nodes write to shared state, NOT return to parent |
| **Google ADK** | Context compaction | Sliding window + configurable `compaction_interval` |
| **AutoGen/MS** | Nested chats | Information silos — each chat isolated, only summary exits |
| **MIT (Dec 2025)** | Recursive Language Models | Context stored as Python variables in REPL, handles 10M+ tokens |
| **CrewAI** | `output_file` + delegation | Agent writes to file, parent receives only file path |

**Common principle:** Data flows through FILES or STATE, not through parent context.

### Claude Code Specifics

- Task tool responses return **in full** to parent context — no automatic truncation
- `auto-compaction` exists but is **reactive** (triggers when context is already near limit)
- `run_in_background: true` sends agent output to **temp file**, parent gets only `output_file` path (~50 tokens)
- `TaskOutput(block: true)` returns full content to context — defeats the purpose
- `TaskOutput(block: false)` returns only status — keeps context clean

### Solution: Background Fan-Out with File Checkpointing

#### Architecture

```
BEFORE (context flooding):
  Spark → Task(agent1)                    → 15K in context
        → Task(agent2)                    → 15K in context
        → Task(agent3)                    → 15K in context
        → ...6 agents...
  Total: ~90K tokens in Spark context

AFTER (file-based IPC):
  Spark → Task(agent1, run_in_background) → output_file path (~50 tokens)
        → Task(agent2, run_in_background) → output_file path (~50 tokens)
        → Task(agent3, run_in_background) → output_file path (~50 tokens)
        → ...6 agents...
  Total: ~300 tokens in Spark context

  Then: Glob("ai/.bughunt/*.md")          → verify files exist
  Then: Read(file, limit=50)              → selective summary if needed
```

**Context reduction: ~300x** (90K → 300 tokens)

#### Three Principles

1. **Spark IS the orchestrator** — don't delegate to a thin orchestrator subagent. Spark has all tools, interactive session, writes files reliably.

2. **Background = file-based IPC** — `run_in_background: true` redirects output to temp file. Parent gets only the path. No flooding.

3. **File checkpointing between steps** — agents write to convention paths. Downstream agents read from disk. Data NEVER passes through orchestrator context.

#### Implementation Steps

1. **Agents launched with `run_in_background: true`** — parallel, output to temp files
2. **Poll with `TaskOutput(block: false)`** or wait for completion notifications
3. **Glob check** for convention paths (optimistic agent writes)
4. **For missing files** — `Read(output_file)` selectively, extract content, write via caller
5. **Downstream agents** receive file paths in prompt, read from disk directly

#### Why This Is Correct

1. Matches LangGraph state reducer principle (data in state, not in messages)
2. Matches CrewAI `output_file` pattern (framework handles I/O)
3. Native Claude Code feature (`run_in_background` exists today)
4. Zero data loss — output_file always contains full response
5. Composable — works for any fan-out/fan-in pattern

---

## ADR-008: Background Fan-Out for Multi-Agent Pipelines

**Decision:** Multi-agent fan-out stages use `run_in_background: true` with file checkpointing instead of foreground Task calls.

**Context:** Bug Hunt pipeline with 6+ parallel agents flooding orchestrator context (30-90K tokens). Industry research shows all production frameworks use state/file-based IPC, not message passing through parent.

**Consequences:**
- Agents launched in background, output goes to temp files
- Parent context stays at ~300 tokens for 6 agents (vs ~90K)
- File checkpointing between pipeline steps
- Selective Read for missing files only
- Spark acts as direct orchestrator (not thin subagent)

---

## Part 3: Orchestrator Zero-Read Pattern (ADR-010)

**Date:** 2026-02-18
**Triggered by:** Bug Hunt v2 crash — 12 background agents' TaskOutput calls flooded orchestrator context

### Problem Statement

ADR-007/008/009 solved WHO writes files, HOW to launch agents, and WHICH steps need background.
But they missed the critical READ problem: the orchestrator reads agent outputs into its own context, negating all background isolation gains.

**Evidence chain:**
- Run 1 (hooks v1): Steps 0-5 ✅, Step 6 ❌ (accumulated ~50-90K from sequential foreground agents)
- Run 2 (hooks v2): Step 1 collection ❌ (12 TaskOutput calls → context crash)
- GitHub Issue #23463: "Subagent results silently overflow context, causing unrecoverable session crash"
- GitHub Issue #16789: TaskOutput returns FULL JSONL log (~70K+ per agent), not final text
- GitHub Issue #17011: run_in_background output_files may be empty (0 bytes)
- Community skill `agent-context-isolation`: "NEVER use TaskOutput to retrieve results"

### Research Method

5 parallel Exa searches + 11-step Sequential Thinking synthesis:
1. Claude Code multi-agent context limit issues (GitHub issues)
2. LLM agent orchestration fan-out/fan-in patterns (2025-2026)
3. Claude Code Task tool output management
4. Multi-agent context overflow solutions (GitHub)
5. Claude Code background task output patterns (GitHub)

### Root Cause Analysis

The orchestrator's context budget:
```
DLD rules/CLAUDE.md:     ~25K tokens
Spark skill prompt:      ~10K tokens
Conversation history:    ~15K tokens (mkdir, Read, Glob, Write, 12×Task launches)
                         ─────────
Base BEFORE collection:  ~50K tokens
Available headroom:      ~150K tokens (of 200K limit)

12 TaskOutput calls (5-6 completed agents):
Each completed agent:    ~10-20K tokens (full JSONL log per #16789)
5-6 completed × 15K:    ~75-90K tokens
6-7 "still running":    ~1K tokens
                         ─────────
Collection flood:        ~76-91K tokens
Total:                   ~126-141K → approaches limit → CRASH
```

### Three Context Attack Surfaces

| Surface | Description | Our Error |
|---------|-------------|-----------|
| **A. TaskOutput calls** | Returns full JSONL log (~70K+ per agent) | Called 12× in one turn |
| **B. Polling loops** | sleep+ls+TaskOutput(block:false) add turns | Multiple poll cycles |
| **C. Completion notifications** | System-injected turn per agent | Small (~20 tokens each) — NOT the problem |

**Surface A is the killer.** The orchestrator must NEVER call TaskOutput.

### Solution: Orchestrator Zero-Read Pattern

#### Three Hard Rules

**RULE 1: ORCHESTRATOR NEVER READS AGENT OUTPUT**
- ❌ No TaskOutput calls (full JSONL → context flood)
- ❌ No Read of output files (still large)
- ❌ No polling with Bash/sleep/ls (accumulates turns)
- ✅ Only: count completion notifications

**RULE 2: COLLECTOR SUBAGENT PATTERN**
- After ALL agents complete → launch ONE collector in background
- Collector reads output files (via Read tool — agents CAN read)
- Collector produces ONE small summary file (< 5K tokens)
- Orchestrator reads ONLY the summary

**RULE 3: FILE-GATE PROGRESSION**
- Each step writes a gate file (e.g., step1-complete.yaml)
- Next step starts only when gate file exists (Glob check)
- Gate files are SMALL (metadata + file paths only)
- Full data stays in step-specific files, accessed only by downstream agents

#### Complete Pipeline Pattern

```
STEP N: LAUNCH PHASE
  orchestrator → Task(agent1, run_in_background=true) → stores output_path_1
               → Task(agent2, run_in_background=true) → stores output_path_2
               → ...
               → Task(agentN, run_in_background=true) → stores output_path_N
  orchestrator → DO NOTHING (wait for completion notifications)

STEP N+0.5: COLLECTION PHASE
  ← "Agent 1 completed" notification
  ← "Agent 2 completed" notification
  ← ... count until N completions received
  orchestrator → Task(collector, run_in_background=true,
                      prompt="Read these output files: [paths]. Write summary to: gate_file")
  orchestrator → DO NOTHING (wait for collector)

STEP N+1: PROCEED
  ← "Collector completed" notification
  orchestrator → Glob(gate_file) → exists? YES
  orchestrator → Read(gate_file) → small summary (< 5K)
  orchestrator → proceed to next step
```

#### Context Budget After Fix

```
Base:                    ~50K tokens
12 completion notifs:    ~240 tokens
Collector launch:        ~200 tokens
Collector completion:    ~20 tokens
Summary Read:            ~3-5K tokens
                         ─────────
Total:                   ~53-55K tokens (vs ~141K before)
Savings:                 ~60% reduction
```

### Why Previous ADRs Were Insufficient

| ADR | What It Solved | What It Missed |
|-----|----------------|----------------|
| ADR-007 | WHO writes (caller, not agent) | Doesn't address reading |
| ADR-008 | HOW to launch (background) | Assumes orchestrator can read output_files |
| ADR-009 | WHICH steps (ALL of them) | Same assumption: orchestrator reads |
| **ADR-010** | **HOW to read (NEVER directly)** | **Closes the chain** |

The ADR chain: Write (007) → Launch (008) → Scope (009) → Read (010)

### Industry Alignment

| Framework | Read Pattern | Matches ADR-010 |
|-----------|-------------|-----------------|
| LangGraph | State reducers aggregate results | ✅ Orchestrator sees aggregate, not raw |
| CrewAI | output_file + delegation chain | ✅ Framework reads, not orchestrator |
| AutoGen/MS | Nested chats with summary | ✅ Only summary exits the chat |
| Google ADK | Compaction between steps | ✅ Context folded between stages |
| Context-Folding (arXiv:2510.11967) | Sub-trajectory folding | ✅ Intermediate steps collapsed |

### Sources (Part 3)

- [GitHub Issue #23463: Subagent results silently overflow context](https://github.com/anthropics/claude-code/issues/23463)
- [GitHub Issue #16789: TaskOutput should return final result, not full JSONL](https://github.com/anthropics/claude-code/issues/16789)
- [GitHub Issue #17011: run_in_background output files empty](https://github.com/anthropics/claude-code/issues/17011)
- [agent-context-isolation skill](https://claude-plugins.dev/skills/@parcadei/Continuous-Claude-v3/agent-context-isolation)
- [arXiv:2510.11967 — Scaling Long-Horizon LLM Agent via Context-Folding](https://arxiv.org/abs/2510.11967)
- [Microsoft 5 AI Agent Orchestration Patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)
- [Google ADK Multi-Agent Patterns](https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/)
- [17x Error Trap of Bag of Agents](https://towardsdatascience.com/why-your-multi-agent-system-is-failing-escaping-the-17x-error-trap-of-the-bag-of-agents/)
- [Claude Code Sub-Agent Best Practices](https://claudefa.st/blog/guide/agents/sub-agent-best-practices)

---

## Sources

- [GitHub Issue #7032: Subagent Write Tool Not Creating Files](https://github.com/anthropics/claude-code/issues/7032)
- [Anthropic Tool Use Implementation Guide](https://platform.claude.com/docs/en/docs/agents-and-tools/tool-use/implement-tool-use)
- [Anthropic Programmatic Tool Calling](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling)
- [Anthropic Think Tool Engineering](https://www.anthropic.com/engineering/claude-think-tool)
- [Claude Code Sub-agents Docs](https://code.claude.com/docs/en/sub-agents)
- [Claude Agent SDK: Subagents](https://platform.claude.com/docs/en/agent-sdk/subagents)
- [CrewAI Tasks Documentation](https://docs.crewai.com/en/concepts/tasks)
- [LangGraph Persistence Guide](https://fast.io/resources/langgraph-persistence/)
- [Multi-Agent LLM Orchestration (arXiv)](https://arxiv.org/abs/2511.15755)
- [AI Agent Orchestration Patterns - Azure](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)
