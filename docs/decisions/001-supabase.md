# ADR-001: Supabase instead of raw Postgres

**Status:** Accepted
**Date:** 2025-11-15
**Deciders:** Architecture team

---

## Context

The project needed a database solution for storing users, campaigns, transactions, and other business data. We had to choose between:
1. Self-managed PostgreSQL
2. Managed PostgreSQL (AWS RDS, Google Cloud SQL)
3. Supabase (PostgreSQL + extras)

## Decision

Use **Supabase** as the primary database and backend service.

## Rationale

Supabase provides PostgreSQL with additional features that accelerate development:

| Feature | Benefit |
|---------|---------|
| Managed PostgreSQL | No DevOps overhead |
| Row Level Security (RLS) | Security at database level |
| Realtime subscriptions | Live updates without polling |
| Auto-generated REST API | Rapid prototyping |
| Edge Functions | Serverless compute |
| Built-in Auth | User management out of the box |

### Alternatives Considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|--------------|
| Raw PostgreSQL | Full control, no vendor lock-in | DevOps overhead, no extras | Too much maintenance |
| AWS RDS | Managed, reliable | Just database, expensive | Missing developer features |
| Firebase | Great DX, realtime | NoSQL, vendor lock-in | Need relational data |
| PlanetScale | Serverless MySQL | MySQL not PostgreSQL | Team expertise in PostgreSQL |

## Consequences

### Positive
- Faster development with built-in features
- Less infrastructure to manage
- RLS provides defense in depth
- Realtime features without additional setup

### Negative
- Vendor dependency on Supabase
- Some PostgreSQL extensions not available
- Pricing scales with usage

### Risks
- Supabase outage affects entire system
- Migration away would require significant effort

---

## Related
- Feature: Initial architecture setup
- Other ADRs: —
