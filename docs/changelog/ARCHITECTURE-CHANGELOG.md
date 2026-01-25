# Architecture Changelog

Full history of architectural changes. Updated by `documenter` agent.

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
