# Architecture Changelog

Full history of architectural changes. Updated by `documenter` agent.

---

## [2026-02-22] — v3.9

### Added
- **EDD (Eval-Driven Development)** — structured evaluation criteria system with 3 assertion types (deterministic, integration, llm-judge)
- **eval-judge agent** — rubric-based LLM output scoring with 5 dimensions
- **Agent Prompt Eval Suite** — golden datasets (`test/agents/{agent}/golden-NNN.{input,output,rubric}.md`) for testing agent prompt quality
- **autopilot-state.mjs** — JSON state tracking for autopilot phase/task progress
- **spark-state.mjs** — 8-phase state tracking for Spark sessions
- **test-wrapper.mjs** — Smart Testing with scope protection and test selection
- **eval-judge.mjs** — CLI parser for extracting eval criteria from specs

### Changed
- **Spark feature mode** — outputs `## Eval Criteria` instead of `## Tests`, with structured DA→EC mapping
- **Devil scout** — structured `## Eval Assertions` with DA-N/SA-N table IDs instead of freeform edge cases
- **Tester agent** — integrated eval criteria testing (deterministic + integration + llm-judge)
- **6 multi-agent skills** — migrated to ADR-007/008/009/010 zero-read pattern (caller-writes, background fan-out, orchestrator zero-read)
- **Autopilot task loop** — integrated regression capture step after debug loops
- **Spec validation hooks** — dual-detection for Eval Criteria (priority) and Tests (fallback)

### Architecture Impact
- **ADR-007** — Caller-writes pattern: subagents can't reliably write files, caller writes from response
- **ADR-008** — Background fan-out: `run_in_background: true` prevents context flooding (6 agents × 15K = 90K → 300 tokens)
- **ADR-009** — Background ALL steps: sequential foreground agents accumulate in orchestrator context
- **ADR-010** — Orchestrator zero-read: TaskOutput returns full JSONL (~70K+), collector subagent reads + summarizes
- **ADR-011** — Enforcement as Code: JSON state files + hooks + hard gates for process enforcement
- **ADR-012** — Eval Criteria over freeform Tests: structured format provides measurable, repeatable quality gates

### Decisions
- EDD pipeline: Spark (8 phases) → Devil (DA-N) → Facilitator (DA→EC) → Autopilot → Tester (EC validation)
- Golden datasets structure: input/output/rubric triad per agent for eval-as-judge scoring
- Backward compat: dual-detection in hooks (Eval Criteria priority, Tests fallback)
- Zero-read pattern industry match: LangGraph state reducers, CrewAI output_file, AutoGen nested chats

---

## [2026-02-14] — v3.7

### Added
- `bug-hunt agents`: 10 specialized agents for multi-perspective bug analysis
  - 6 persona agents (Sonnet): code-reviewer, security-auditor, ux-analyst, junior-developer, software-architect, qa-engineer
  - 2 framework agents (Opus): toc-analyst, triz-analyst
  - 1 validator (Opus): finding triage and deduplication
  - 1 solution-architect (Opus): sub-spec creation with Impact Tree

### Changed
- Bug Hunt integrated into Spark as a mode (no longer standalone skill)
- Umbrella specs: `ai/features/BUG-XXX/` directory pattern for complex bugs

### Architecture Impact
- New multi-phase pipeline: 6 Sonnet → 2 Opus → 1 Opus → N Opus
- Sub-spec pattern enables independent parallel fixes
- Backlog entry = 1 per umbrella (sub-specs tracked internally)

### Decisions
- Bug Hunt uses subagents (Task tool) instead of Agent Teams for reliability
- TOC + TRIZ replace Red Team + Systems Thinker for deeper root cause analysis
- Sonnet for personas (better analysis than Haiku), Opus for frameworks (deep reasoning)

---

## [2026-01-05] — v1.4

### Added
- `seller/tools`: Autonomous error handling with retry logic (FTR-213)
  - 3 retry attempts with exponential backoff
  - Fallback to human escalation after failures

### Architecture Impact
- New dependency: seller → infra/notifications (for escalation)
- Added circuit breaker pattern to external API calls

### Decisions
- ADR-004: Circuit breaker over simple retry (not yet documented)

---

## [2025-12-15] — v1.3

### Changed
- `billing`: Extracted from campaigns into separate domain (FTR-150)
  - transactions table moved to billing ownership
  - campaigns now calls billing.check_balance() instead of direct DB

### Architecture Impact
- New domain boundary: campaigns → billing (one-way dependency)
- Breaking change: campaigns no longer has direct transaction access

### Decisions
- [ADR-002: Separate billing domain](../decisions/002-billing-domain.md)

---

## [2025-12-01] — v1.2

### Added
- `seller`: LLM-based agent for seller interactions (FTR-100)
  - Natural language interface via Telegram
  - Tool-based architecture (12 tools)
  - Prompt versioning system

### Architecture Impact
- New domain: seller (depends on: billing, campaigns, infra/llm)
- New infra component: infra/llm for OpenAI integration

### Decisions
- [ADR-003: LLM agent for seller](../decisions/003-llm-agent.md)

---

## [2025-11-15] — v1.0

### Added
- Initial architecture setup
  - 4 layers: shared → infra → domains → api
  - 3 domains: campaigns, buyer, billing (inside campaigns)
  - PostgreSQL via Supabase

### Architecture Impact
- Foundation established
- Import direction enforced: left-to-right only

### Decisions
- [ADR-001: Supabase instead of raw Postgres](../decisions/001-supabase.md)

---

## Format Reference

```markdown
## [YYYY-MM-DD] — vX.X

### Added/Changed/Fixed/Removed
- `domain/component`: description (TASK-ID)
  - Details if significant

### Architecture Impact
- What changed for the system

### Decisions
- ADR-XXX: Title (link if exists)
```
