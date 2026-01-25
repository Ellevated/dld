# ADR-003: LLM agent for seller (not FSM)

**Status:** Accepted
**Date:** 2025-12-01
**Deciders:** Architecture team

---

## Context

We needed to build an interface for sellers to manage their campaigns via Telegram. Two approaches were considered:

1. **FSM (Finite State Machine)** — traditional bot with buttons and menus
2. **LLM Agent** — natural language interface powered by GPT-4

Sellers are busy professionals who want to accomplish tasks quickly without learning a complex menu structure.

## Decision

Use an **LLM agent** for the seller interface, not a traditional FSM bot.

## Rationale

| Aspect | FSM Bot | LLM Agent |
|--------|---------|-----------|
| Learning curve | Must learn menu structure | Natural conversation |
| Flexibility | Fixed paths only | Handle any request |
| Edge cases | Need explicit handling | Agent reasons through |
| Development | Add state for each feature | Add tool, agent adapts |
| User experience | Robotic, predictable | Human-like, adaptive |

### Why LLM Works Here

1. **Business domain complexity:** Campaigns have many parameters, hard to fit in menus
2. **User expertise varies:** Some sellers are tech-savvy, some are not
3. **Evolving requirements:** New features don't require new menus
4. **Error handling:** Agent can explain and guide, not just show error codes

### Alternatives Considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|--------------|
| Pure FSM | Predictable, cheap | Rigid, poor UX for complex tasks | Not suitable for domain complexity |
| Hybrid (FSM + LLM) | Best of both | Complexity, inconsistent UX | Added confusion for users |
| Web interface | Rich UI possible | Sellers live in Telegram | Would reduce adoption |

## Consequences

### Positive
- Superior user experience
- Faster feature development
- Handles edge cases gracefully
- Natural language localization

### Negative
- LLM API costs per interaction
- Response latency (2-5 seconds)
- Non-deterministic outputs require guardrails
- Prompt engineering maintenance

### Risks
- LLM hallucinations could cause wrong actions
- API rate limits during peak usage
- Model deprecation requires prompt updates

---

## Mitigations

| Risk | Mitigation |
|------|------------|
| Hallucinations | Tool confirmation before actions, human escalation |
| Latency | Streaming responses, progress indicators |
| Costs | Caching, smaller models for simple queries |
| Determinism | Structured outputs, validation layers |

---

## Related
- Feature: FTR-100
- Other ADRs: ADR-001 (Supabase for data storage)
