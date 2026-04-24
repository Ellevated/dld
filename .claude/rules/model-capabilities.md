# Model Capabilities (Claude Opus 4.7)

Reference for agents about current model capabilities.
Last updated: 2026-04-24

---

## Active Model: Claude Opus 4.7

**Released:** April 16, 2026
**Model ID:** `claude-opus-4-7`
**Pricing:** $5/$25 per million tokens (input/output)

---

## Key Capabilities

| Feature | Value | Notes |
|---------|-------|-------|
| Context window | 200K standard, 1M beta | Beta: $10/$37.50 for >200K |
| Max output tokens | 128K | Doubled from 64K in Opus 4.5 |
| Adaptive thinking | Default | Model decides when/how much to think |
| Effort levels | low / medium / high / xhigh / max | Controls thinking depth |
| Fast mode | 2.5x faster output | Research preview, `/fast` toggle |
| Prompt caching | Automatic | 5-min default; set `ENABLE_PROMPT_CACHING_1H=1` for 1h TTL |

---

## Effort Routing Strategy

Agents should operate at different effort levels based on task complexity:

| Agent Role | Model | Recommended Effort | Rationale |
|------------|-------|-------------------|-----------|
| planner | opus | xhigh | Deep analysis, drift detection, long-horizon agentic |
| council experts | opus | xhigh | Expert-level architectural decisions, adversarial |
| debugger | opus | high | Root cause analysis requires deep thinking |
| review (Code Quality Gate) | sonnet | xhigh | Critical commit gate. SWE-bench: Opus 87.6% / Sonnet 80.8% — the 7pp gap is on end-to-end coding, not on deduplication/LOC/anti-pattern checks where Sonnet + strict checklist + `checks_performed` evidence gap closes. 12× cheaper on Max compute and runs once per task = massive saving. Prompt hardened 2026-04-24 with reviewer-discipline section. |
| solution-architect (bughunt) | opus | high | Fix design needs careful reasoning |
| triz toc-analyst, triz-analyst | opus | high | System-level contradiction/constraint resolution |
| coder | sonnet | medium | Pattern-following coding (Sonnet 4.6 = 80.8% SWE-bench, 5x cheaper) |
| scout | sonnet | high | Research quality matters, but knowledge tasks favor Sonnet |
| tester | sonnet | medium | Execution-focused, smart-testing logic |
| spec-reviewer | sonnet | medium | Checklist verification, not creative |
| eval-judge | sonnet | high | Rubric-based LLM output evaluation |
| bughunt personas (6) | sonnet | medium | Read + describe from specialized perspectives |
| bughunt spec-assembler | sonnet | high | Structured assembly with ID protocol |
| bughunt validator | sonnet | high | Triage requires good judgment |
| audit/synthesizer | sonnet | xhigh | Merges 6 persona reports — needs deep synthesis (changed 2026-04-24) |
| synthesizers (board, triz) | sonnet | high | Merge/format structured output — Opus overkill (changed 2026-04-24) |
| council-synthesizer, facilitators (architect/board/spark) | sonnet | medium | Process keeper / orchestration |
| documenter | haiku | low | Structured release notes, shaped by CHANGELOG template (changed 2026-04-24) |
| bughunt scope-decomposer | haiku | low | File listing and zone grouping (changed 2026-04-24) |
| bughunt findings-collector | haiku | low | Normalization, no reasoning (changed 2026-04-24) |
| bughunt report-updater | haiku | low | Structured update, clear patterns (changed 2026-04-24) |
| triz data-collector | sonnet | medium | Pure data extraction (shell + aggregation) |
| ~~diary-recorder~~ | haiku | low | DEPRECATED: inline in task-loop Step 6.5 (ADR-007). If used: haiku. |

**2026-04-24 rationale:** Opus 4.7 on structured merge/format tasks (synthesizers)
showed overthinking + cost without quality gain. Sonnet 4.6 benchmarks tighter
on knowledge/merge tasks and costs 5x less. Haiku 4.5 handles format-heavy
subagents (scope decomposition, findings collection, doc updates) at 95%
quality of Sonnet at 3x lower cost. See ADR-019.

---

## Breaking Changes from Opus 4.6

| What | Impact | Action |
|------|--------|--------|
| `thinking` parameter changed | Incompatible format vs 4.6 | Not used by DLD claude-runner — safe |
| `temperature` / `top_p` behavior tuned | Drift on deterministic prompts | Not used by DLD claude-runner — safe |

## Breaking Changes from Opus 4.5

| What | Impact | Action |
|------|--------|--------|
| Prefilling removed | `400` error on assistant prefills | Use structured outputs or system prompts |
| `output_format` deprecated | Will stop working | Use `output_config.format` instead |
| `interleaved-thinking` header | No longer needed | Remove beta header |

---

## What Agents Should Know

1. **Adaptive thinking is automatic** — no need to request "think harder"
2. **128K output** — can generate comprehensive plans in single pass
3. **1M context (beta)** — large codebases can fit entirely in context
4. **Context compaction** — server-side, enables infinite conversations
5. **Agent Teams** — research preview, direct agent-to-agent messaging
6. **Prompt caching is automatic** — set `ENABLE_PROMPT_CACHING_1H=1` on the runner to extend TTL to 1 hour (useful for long council/bughunt sessions)

---

## Model Routing (SSOT in agent frontmatter)

| Model | Use For | Cost |
|-------|---------|------|
| opus | Complex reasoning, planning, review, council | $5/$25 |
| sonnet | Standard implementation, research, testing, orchestration | $3/$15 |
| haiku | Quick checks, simple formatting | $1/$5 |

**Rule:** Model is defined ONCE in agent frontmatter `model:` field.
Never hardcode model in skill dispatch — use `subagent_type` only.
