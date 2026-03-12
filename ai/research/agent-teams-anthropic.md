# Agent Teams (Anthropic, Opus 4.6) — Research

**Date:** 2026-02-12
**Status:** Research preview (experimental)
**Flag:** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`

---

## What Is It

Agent Teams позволяет нескольким Claude Code сессиям работать **параллельно** с inter-agent messaging. В отличие от subagents (Task tool), teammates — полноценные сессии с собственным контекстом, которые **общаются друг с другом**, а не только с оркестратором.

## Architecture

```
Lead Agent (Team Lead)
    ├── creates team at ~/.claude/teams/{team-name}/
    ├── defines tasks in shared task list
    ├── teammates claim tasks via file locking
    │
    ├── Teammate 1 (Coder) ──── Mailbox ────┐
    ├── Teammate 2 (Tester) ─── Mailbox ────┤
    ├── Teammate 3 (Reviewer) ── Mailbox ───┤
    └── Teammate 4 (DevOps) ─── Mailbox ────┘
                                             │
                                    Inter-agent messaging
                                    (direct, not through lead)
```

### Key Difference: Subagents vs Agent Teams

| Aspect | Subagents (Task tool) | Agent Teams |
|--------|----------------------|-------------|
| Context | Subagent gets subset from parent | Each teammate has FULL own context |
| Communication | Only parent ↔ child | Any teammate ↔ any teammate |
| Lifecycle | Created and destroyed per task | Persistent for team duration |
| Cost | Efficient (subset context) | Expensive (full context per teammate) |
| Coordination | Parent orchestrates | Self-organizing via task list + mailbox |
| Resume | Parent can resume subagent | Cannot resume teams |
| Best for | Focused single tasks | Complex parallel collaboration |

## How Inter-Agent Messaging Works

1. **Mailbox system:** Each teammate has a mailbox at `~/.claude/teams/{team-name}/`
2. **Messages:** Teammates can send messages to specific other teammates
3. **Task list:** Shared task list with claiming mechanism
4. **File locking:** Tasks use file locking to prevent double-claiming
5. **No file locking for edits:** If two teammates edit same file — last write wins

## Proof at Scale: C Compiler

[Official Anthropic case study](https://www.anthropic.com/engineering/building-c-compiler):
- **16 agents** working in parallel
- **2000 sessions** over the project
- **2 billion input tokens**
- **$20K API cost**
- **100K lines** of C compiler code
- Result: Working C compiler built autonomously

## Setup

```bash
# Enable experimental feature
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1

# Start team lead
claude --team my-project-team

# Lead creates teammates via Task tool with team parameters
# Teammates auto-start in split panes (tmux/iTerm2)
```

Requires: tmux or iTerm2 for split-pane monitoring.

## Cost Analysis

| Setup | Token Cost | Monthly Estimate |
|-------|-----------|-----------------|
| Single agent (current DLD) | 1x | ~$50-100/dev |
| 3-agent team (sonnet) | ~3x | ~$150-300/dev |
| 5-agent team (opus) | ~5-10x | ~$500-1000/dev |
| 16-agent team (opus, C compiler scale) | ~20x+ | $20K project |

Token cost scales **linearly** with team size (each teammate = full context window).

## Limitations (Known Issues)

1. **Cannot resume:** `/resume` and `/rewind` don't work for teams — teams are ephemeral
2. **No file locking for edits:** Two teammates editing same file = last write wins
3. **Session coordination bugs:** Known issues with task handoff timing
4. **Monitoring:** Requires tmux/iTerm2 for visibility into teammate work
5. **Cost:** 3-5x more tokens than single-session for same work
6. **Experimental:** May change or break between Claude Code versions

## When to Use (vs Subagents)

**Use Agent Teams when:**
- Tasks are genuinely parallelizable (independent modules)
- Agents need to COMMUNICATE (ask questions, clarify, challenge)
- Complex multi-layer refactoring
- Competing hypothesis debugging (multiple agents investigate different theories)
- Cross-domain code review (agents challenge each other's findings)

**Keep Subagents when:**
- Tasks have clear sequential dependencies
- Each task is focused and independent
- Token budget matters
- Production workflow (stability over features)
- 90% of current DLD autopilot use cases

## Comparison with Alternatives

| Framework | Approach | Strengths | Weaknesses |
|-----------|----------|-----------|------------|
| **Claude Agent Teams** | Native Claude Code, mailbox messaging | Deep Claude integration, simple setup | Experimental, expensive, ephemeral |
| **AutoGen** | Conversation-based multi-agent | Mature, flexible conversation patterns | Requires separate scaffolding, not Claude-native |
| **CrewAI** | Role-based teams with task handoffs | Intuitive role model, good docs | Less flexible than LangGraph |
| **LangGraph** | State-machine orchestration | Strong guarantees, production-ready | Complex setup, steep learning curve |

## Relevance to DLD v2

### Hybrid Approach (Recommended)

```
DLD v2 Autopilot:
├── Phase 1 (Planning): Subagent (planner, opus:max)
│   └── Single focused task, no collaboration needed
│
├── Phase 2 (Execution): Agent Teams IF complex, Subagents IF simple
│   ├── Simple task (1 file change): Subagent coder → tester → review
│   └── Complex task (multi-file, cross-domain):
│       └── Agent Team:
│           ├── Coder (writes code)
│           ├── Tester (prepares tests in parallel)
│           ├── Reviewer (watches code quality in real-time)
│           └── All communicate via mailbox
│
└── Phase 3 (Finishing): Subagent (DevOps, commit/push)
    └── Mechanical process, no collaboration needed
```

### TOC Application to Agent Teams

**Constraint in Agent Teams:** Mailbox message latency + token cost

**Exploit:**
- Use sonnet for most teammates (cheaper)
- opus only for lead + reviewer
- Minimize cross-agent messages (batch updates)

**Subordinate:**
- Don't use Agent Teams for tasks that work fine with subagents
- Reserve for genuinely parallel work

---

## Sources

- [Building a C compiler with parallel Claudes](https://www.anthropic.com/engineering/building-c-compiler) — Official Anthropic
- [Agent Teams Official Docs](https://code.claude.com/docs/en/agent-teams) — Primary reference
- [Opus 4.6 Launch](https://www.anthropic.com/news/claude-opus-4-6) — Anthropic
- [TechCrunch Coverage](https://techcrunch.com/2026/02/05/anthropic-releases-opus-4-6-with-new-agent-teams/)
- [Setup Guide](https://darasoba.medium.com/how-to-set-up-and-use-claude-code-agent-teams-and-actually-get-great-results-9a34f8648f6d) — Medium
- [Tasks to Swarms](https://alexop.dev/posts/from-tasks-to-swarms-agent-teams-in-claude-code/) — alexop.dev
- [Multi-Agent Comparison](https://brlikhon.engineer/blog/multi-agent-orchestration-langgraph-vs-crewai-vs-autogen-for-enterprise-workflows)
- [Cost Management](https://docs.anthropic.com/en/docs/claude-code/costs) — Anthropic
