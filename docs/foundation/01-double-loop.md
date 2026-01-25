# Double Loop: Two Loops

## Concept

DLD (Double-Loop Development) — an operational model with two loops:

```
┌─────────────────────────────────────────────────────────────────┐
│                    LOOP 1: Autonomous                           │
│                    (Execution Loop)                             │
│                                                                 │
│   backlog → spec → code/tests → dev-deploy → auto-checks       │
│      ↑                                              │           │
│      └──────────────────────────────────────────────┘           │
│                    (without human participation)                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                      ready for UX walkthrough
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    LOOP 2: Human                                │
│                    (Sensemaking Loop)                           │
│                                                                 │
│   UX-test → inconveniences/aha → decisions → new meanings → backlog  │
│      ↑                                              │           │
│      └──────────────────────────────────────────────┘           │
│                    (entrepreneur only)                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Loop 1: Autonomous

**Goal:** Bring a task to dev-result without bothering the human.

**Flow:**
1. Task from backlog
2. Planner clarifies and creates spec
3. Developer implements
4. Tester verifies
5. Supervisor controls
6. Deploy to dev

**Key point:** Human doesn't participate until UX verification.

---

## Loop 2: Human

**Goal:** Generate meanings through live testing.

**Flow:**
1. Entrepreneur tests as a user
2. Catches inconveniences and aha-moments
3. Makes product decisions
4. Forms new tasks → backlog

**Key point:** Entrepreneur is the final UX judge, not a craftsman.

---

## Speed of Changes

DLD solves **speed of changes** — the main pain of the entrepreneur.

| Without DLD | With DLD |
|-------------|----------|
| Idea → weeks → result | Idea → hours → result |
| "Let's discuss" | "Let's verify" |
| Hypotheses in head | Hypotheses in product |
| Fear of changing | Easy to change |

---

## Implementation Quality

DLD brings a feature to the state **"works exactly as intended"**.

Why this matters:
- If feature is bad → visible that **it's a bad idea**
- If feature is good → visible that **it's a good idea**
- No uncertainty "is this a bad idea or bad implementation?"

---

## Minimum Requirements DLD v1

1. **Takes a feature** — from backlog or verbally
2. **Makes implementation** — code + tests
3. **Runs testing** — unit/integration/e2e
4. **Delivers dev-result** — reflecting the intention, not a compromise

---

## Autonomy Boundary

```
Questions for human:
├── "Why this feature?" ← YES (business meaning)
├── "Which UX is better?" ← YES (product decision)
├── "3 or 5 seconds timeout?" ← NO (technical detail)
└── "SQL or NoSQL?" ← NO (technical decision)
```

Planner communicates in the language of **business logic and product**.
Technical details — system's responsibility.

---

## Summary

| Loop | Who | What they do |
|------|-----|--------------|
| Autonomous | Agents | Transform task into working code |
| Human | Entrepreneur | Transform experience into new tasks |

**Next step:** [02-agent-roles.md](02-agent-roles.md) — who's inside the autonomous loop
