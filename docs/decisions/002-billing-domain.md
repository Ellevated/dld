# ADR-002: Separate billing domain

**Status:** Accepted
**Date:** 2025-11-20
**Deciders:** Architecture team

---

## Context

Initially, billing logic (transactions, balance, payouts) was part of the `campaigns` domain. As the system grew, we observed:

1. **Coupling:** Changes to campaign logic required changes to billing code
2. **Testing complexity:** Campaign tests needed billing mocks
3. **Cognitive load:** Single domain had too many responsibilities
4. **Reusability:** Other domains (seller, buyer) needed billing functions

## Decision

Extract **billing** into a separate domain with its own:
- Entities (Transaction, Balance, Payout)
- Services (create_transaction, get_balance, process_payout)
- Repository (transactions table ownership)

## Rationale

Following Domain-Driven Design principles:
- **Single Responsibility:** Each domain handles one business capability
- **Bounded Context:** Billing has its own ubiquitous language
- **Independence:** Can evolve separately from campaigns

### Alternatives Considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|--------------|
| Keep in campaigns | No refactoring needed | Growing complexity | Not sustainable |
| Microservice | Complete isolation | Operational overhead | Premature optimization |
| Shared module | Simple extraction | Not a true domain | Would grow into another monolith |

## Consequences

### Positive
- Clear ownership of billing logic
- Easier testing (mock one domain, not many)
- Multiple domains can use billing services
- Team can work in parallel

### Negative
- Cross-domain transactions require coordination
- Additional abstraction layer
- Initial migration effort

### Risks
- Circular dependencies if not careful
- Data consistency across domain boundaries

---

## Migration Notes

1. Created `src/domains/billing/`
2. Moved transactions table ownership
3. Updated campaigns to call billing services
4. Deprecated old imports with warnings

---

## Related
- Feature: FTR-150
- Other ADRs: —
