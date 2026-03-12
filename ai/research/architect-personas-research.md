# Architect Personas Research — System Architecture Board

**Date:** 2026-02-15
**Purpose:** Research для проектирования уровня Architect в DLD v2

---

## Chosen Personas (7 + Devil + Facilitator)

| # | Role | Worldview Source | Lens | Kill Question |
|---|------|-----------------|------|---------------|
| 1 | Domain Architect | Eric Evans (DDD) | Linguistic boundaries = system boundaries | "Можешь объяснить архитектуру только терминами бизнеса?" |
| 2 | Data Architect | Martin Kleppmann (DDIA) | Data outlives code | "Что является system of record для каждой сущности?" |
| 3 | Ops/Observability | Charity Majors (Honeycomb) | Can't manage what you can't see | "Как ты узнаешь что это сломалось в проде?" |
| 4 | Security Architect | Shift-left / threat modeling | Every system = one exploit from disaster | "Какова модель угроз? Attack surface?" |
| 5 | Evolutionary Architect | Neal Ford (ThoughtWorks) | Design for change, fitness functions | "Какие fitness functions защищают это решение?" |
| 6 | DX/Pragmatist | Dan McKinley (Boring Tech) | Innovation tokens are scarce | "Это бизнес-проблема или инженерное любопытство?" |
| 7 | LLM Architect | Erik Schluntz (Anthropic) | Simplicity > sophistication. Context = RAM | "Может ли агент работать с этим без исходников?" |
| — | Devil's Advocate | Fred Brooks (IBM) | Conceptual integrity or chaos | "Кто единственный отвечает за целостность?" |
| — | Facilitator | Chief Architect | Process, no vote | Agenda + artifacts + gates |

---

## Legendary System Architects (Scout 1)

### Werner Vogels (Amazon CTO)
- "Evolvability must be a requirement from day one"
- Cell-based architecture, complexity as manageable through automation
- Kill: "Will this system be easier to change in 3 years?"

### Joe Armstrong (Erlang Creator)
- "Let it crash — prefer restart over defensive programming"
- Failure is inevitable, isolation is protection
- Supervision hierarchies, process isolation

### Adrian Cockcroft (Netflix Cloud Architect)
- "Build for failure — assume everything will break"
- Chaos engineering pioneer, microservices popularizer
- Kill: "What happens when AWS loses an AZ right now?"

### Leslie Lamport (Turing Award, Distributed Systems)
- "Design systems formally before coding"
- Correctness as mathematical property, TLA+
- Kill: "Can you prove this is correct under all failure modes?"

### Fred Brooks (IBM System/360)
- "Conceptual integrity is THE most important consideration"
- Architecture as vision, not committee. "No Silver Bullet"
- Kill: "Who is the single architect responsible for integrity?"

### Dan McKinley (Etsy/Stripe)
- "Innovation tokens are scarce — spend on business, not infra"
- Kill: "Is this new tech solving a business problem?"
- Source: "Choose Boring Technology"

### Nancy Leveson (MIT Safety)
- "Safety is a system property, not a component property"
- STAMP framework, systems thinking applied to safety
- Kill: "What constraints prevent unsafe states?"

### Barbara Liskov (MIT, Turing Award)
- "Abstraction separates specification from implementation"
- Liskov Substitution Principle, abstract data types
- Kill: "Can this component change without breaking callers?"

### Pat Helland (Microsoft/Amazon)
- "All computing is memories, guesses, and apologies"
- Eventual consistency as reality, immutability
- Kill: "What happens when this replica guesses wrong?"

---

## Expensive Architecture Failures (Scout 2)

| Case | Loss | Missing Perspective |
|------|------|-------------------|
| Knight Capital (2012) | $460M in 45min | Deployment safety, dead code, kill switch |
| Healthcare.gov (2013) | $630M+ | E2E integration owner, load testing |
| TSB Bank (2018) | £400M+ | Data migration testing, config management |
| Southwest Airlines (2022) | $740M | Domain modeling, tech debt accounting |
| Friendster (2006-2011) | Company failure | Data scaling, evolutionary architecture |

### Top Missing Perspectives (from failure analysis)
1. Operations / Production Readiness
2. Integration / End-to-End Ownership
3. Data Architecture & Migration
4. Testing & QA Strategy
5. Performance & Scalability
6. Security
7. Configuration Management
8. Risk & Contingency Planning
9. Technical Debt Management
10. Vendor/Supply Chain Governance

### ARB Best Practices
- AWS: 5-7 core members, keep under 10
- TOGAF: Enterprise Architect (chair), Solution, Security, Data, Ops
- Spotify: Open RFC process, broad participation
- ThoughtWorks: Guidance not command-and-control

---

## Unconventional Architecture Roles (Scout 3)

### Evolutionary Architecture — Neal Ford (ThoughtWorks)
- Fitness functions = automated tests for architecture
- Design for changeability, not just correctness
- Kill: "What fitness functions verify this decision stays correct?"

### DDD — Eric Evans, Vaughn Vernon
- Technical boundaries must align with linguistic boundaries
- Bounded contexts prevent coupling
- Kill: "Can you explain this using only business domain terms?"

### Sociotechnical — Team Topologies (Skelton & Pais)
- Conway's Law: org structure = architecture
- Inverse Conway Maneuver: design teams to match desired architecture
- Kill: "What team structure is required for this architecture?"

### Data Architecture — Martin Kleppmann
- "The truth is the log. The database is a cache."
- Data outlives applications
- Kill: "What's the system of record? How does data flow?"

### Chaos Engineering — Casey Rosenthal (Netflix)
- Design for reversibility and experimentation
- Horizontal scaling, no single points of failure
- Kill: "Can we simulate this failure in production right now?"

### FinOps — FinOps Foundation
- Cost per transaction as architectural decision
- Majority of lifecycle cost determined during architecture phase
- Kill: "What's cost per transaction? How does cost scale?"

### Observability — Charity Majors (Honeycomb)
- Development tool, not just ops
- High-cardinality debugging from day 1
- Kill: "Can devs understand production in business language?"

### API-First — OpenAPI ecosystem
- Contract before code, parallel development
- Auto-generated docs, consumer-driven contract tests
- Kill: "Can frontend and backend work in parallel with stubs?"

---

## LLM Architecture Perspectives (Scout 4)

### Erik Schluntz (Anthropic) — Agent Architecture
- "Simplicity beats sophistication. Start with direct API calls."
- Tool design more important than prompts
- Anti-pattern: premature multi-agent, framework-first
- Source: "Building Effective Agents"

### Anthropic Applied AI Team — Context Engineering
- "Context is finite — find smallest high-signal token set"
- Initializer + Worker pattern for long-running tasks
- Anti-pattern: context bloat, overlapping tools, one-shotting
- Source: "Effective Context Engineering for AI Agents"

### Chip Huyen — GenAI Platform Architecture
- 5 layers: Context → Guardrails → Router → Cache → Logic
- Observability from day 1, not retrofitted
- Anti-pattern: premature orchestration, semantic caching
- Source: "Building a GenAI Platform"

### Eugene Yan — Production LLM Patterns
- Hybrid approaches beat pure methods (BM25 + semantic)
- Task-specific evals, not generic benchmarks
- Anti-pattern: benchmark worship, chat UX as default
- Source: "Patterns for Building LLM-based Systems"

### Jason Liu — Structured Outputs
- Type-first design with automatic validation and retries
- Provider-agnostic from day 1
- Anti-pattern: parsing unstructured text, manual retry logic
- Source: Instructor library

### Hamel Husain — Eval-Driven Development
- Evals earn trust when they mirror human judgment
- Build evals BEFORE features, wired into observability
- Anti-pattern: features before evals, academic benchmarks
- Source: "LLM Evals FAQ"

### Key LLM Architecture Anti-Patterns
1. Framework-first development (Anthropic + Chip Huyen)
2. Premature multi-agent (Anthropic + Harrison Chase)
3. Semantic similarity caching (Eugene Yan + Chip Huyen)
4. Academic benchmark worship (Eugene Yan + Hamel Husain)
5. Context bloat (Anthropic Applied AI + Chip Huyen)
6. Overlapping tool sets (Anthropic Applied AI)
7. Validation as detection vs recovery (Jason Liu)
8. Features before evals (Hamel Husain)
9. One-shotting long tasks (Anthropic)
10. Chat UX as default (Eugene Yan)
