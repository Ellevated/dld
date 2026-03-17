# External Research: AI-First Economic Prioritization Model

Scout: External Best Practices
Feature: TECH-152 — Switch DLD from human-centric effort estimation to AI-first economic model
Date: 2026-03-17

---

## Key Findings

### 1. WSJF Collapses to Pure Cost of Delay When Effort Is Constant

Don Reinertsen's original WSJF formula is `Cost of Delay / Job Duration`. SAFe adapted it as `Cost of Delay / Job Size`. The mathematical implication is clear: **when AI agents make job size effectively constant ($1-5 per task), WSJF degenerates to pure Cost of Delay ranking**.

This is not a theoretical edge case — it is the correct application of the formula. Reinertsen himself emphasizes that the purpose of WSJF is economic sequencing, and when the denominator is constant, the formula simplifies to sorting by the numerator alone.

Similarly, RICE (`Reach x Impact x Confidence / Effort`) collapses to `R x I x C` when effort is constant. The effort denominator was always a proxy for "scarce human time" — remove that scarcity and the formula simplifies to pure value scoring.

**Implication for DLD:** Replace all WSJF/RICE calculations in council, architect, and spark with pure Cost of Delay / Value Impact scoring. The "Job Size" and "Effort" fields become metadata for cost tracking, not prioritization inputs.

Sources:
- Reinertsen, D. "The Practical Science of Prioritization" (2013 workshop, na.eventscloud.com)
- agility-at-scale.com/safe/lpm/wsjf-weighted-shortest-job-first/ (Feb 2026)
- Jason Yip, "Problems I have with SAFe-style WSJF" (Medium, Mar 2024) — notes that WSJF's value is specifically in the CoD/Duration trade-off; remove duration and you get pure CoD ranking
- jpalmer.dev/2021/03/prioritizing-with-cost-of-delay — demonstrates how CoD alone helps teams stop deprioritizing tech debt

### 2. OpenAI "Harness Engineering" Validates the Zero-Manual-Code Model

OpenAI published their "Harness Engineering" methodology (Feb 11, 2026): a team built a production product with **0 lines of manually-written code**, reaching 1M LOC in 5 months. Key principles:

- **"Humans steer. Agents execute."** — the human role is designing environments, shaping intent, and building feedback systems
- 3 engineers initially, averaging 3.5 PRs/person/day; throughput *increased* as team grew to 7
- Built in ~1/10th the time of manual coding
- Every line — application logic, tests, CI config, docs, internal tooling — written by Codex agents

Martin Fowler's Thoughtworks analysis of Harness Engineering (Feb 17, 2026) emphasizes: the human role shifts from "writing code" to "building the harness" — the constraints, tests, CI, and feedback loops that make agent output reliable.

**Implication for DLD:** The DLD orchestrator already implements this pattern. The key insight is that in harness engineering, **refactoring and testing are the harness itself** — they should have the highest priority, not lowest. They are the infrastructure that makes all other agent work reliable.

Sources:
- openai.com/index/harness-engineering/ (Feb 11, 2026, Ryan Lopopolo)
- martinfowler.com/articles/exploring-gen-ai/harness-engineering.html (Birgitta Boeckeler, Feb 17, 2026)
- infoq.com/news/2026/02/openai-harness-engineering-codex/ (Feb 21, 2026)
- humanlayer.dev/blog/skill-issue-harness-engineering-for-coding-agents (Mar 12, 2026) — "it's not a model problem, it's a configuration problem"

### 3. "Zero Marginal Cost" Software Economics Is Now an Active Research Field

A 2026 academic paper "The New Software Cost Curve under Agentic AI" (Wasim Haque, Scientific Research, DOI: 10.4236/JSEA.2026.191001) directly addresses how agentic AI bends the software cost curve, analyzing development economics when agents handle the full lifecycle (plan, generate, test, iterate).

Michael Ulin's "When Software Costs Hit Zero" (Feb 22, 2026) analyzes the first, second, and third-order effects: "When the marginal cost of building software approaches zero, and autonomous agents can operate that software on your behalf, you don't get a more efficient version of today. You get a fundamentally different system."

**Key economic shifts identified across sources:**
1. **Implementation cost becomes negligible** — the bottleneck moves to requirements clarity and architectural decisions
2. **Tech debt "interest rate" plummets** — David Poll (LinkedIn, Aug 2025): "When code becomes 10x cheaper to write AND rewrite, the interest rate on tech debt plummets. The cost of that future refactor? It might be trivial."
3. **The constraint shifts from "how many devs" to "how clear is the spec"** — Cursor's Michael Truell (Feb 26, 2026): "Cursor is no longer primarily about writing code. It is about helping developers build the factory that creates their software."

**Implication for DLD:** The economic model should treat implementation as a commodity input ($1/task). All decision-making energy should focus on: (a) What to build (value/CoD), (b) How clear is the spec, (c) Quality of the harness (tests, CI, architecture).

Sources:
- academia.edu/161249877 — "The New Software Cost Curve under Agentic AI" (Haque, 2026)
- whimseylabs.substack.com/p/when-software-costs-hit-zero (Ulin, Feb 2026)
- linkedin.com/posts/depoll — tech debt equation changing (Poll, Aug 2025)
- cursor.com/blog/third-era (Truell, Feb 2026)

### 4. AI-Native Teams Already Operate This Way

Multiple real-world examples of teams that have adopted AI-first development with changed prioritization:

**Pane (Doozy):** Two founders, 300K LOC, zero engineers. 3-6 AI agents running in parallel across git worktrees. Their pipeline: `/discussion -> /plan -> /implement -> /prepare-pr`. Priority is purely "what matters to users next" — effort is never a factor because agents handle it.

**AI Coding Agencies (2026):** "Shipping real production code with multi-agent systems, charging clients $500-$5,000 per project while spending $5-$30 on AI API costs." Prioritization is purely by client value and deadline — implementation cost is a rounding error.

**Zylos Research (Mar 2026):** "72% of enterprise AI projects involve multi-agent architectures (up from 23% in 2024), and every major AI coding platform ships multi-agent capabilities."

**Implication for DLD:** These teams have implicitly adopted pure-CoD prioritization by eliminating effort from consideration. DLD should make this explicit in its framework.

Sources:
- runpane.com/blog/ai-native-development-workflow (Parsa, Mar 6, 2026)
- betonai.net/how-to-build-an-ai-coding-agency-in-2026 (Nik Sai, Mar 8, 2026)
- zylos.ai/research/2026-03-09-multi-agent-software-development-ai-native-teams (Mar 2026)

### 5. The Tech Debt Counter-Argument Is Real But Solvable

There is a legitimate concern: Thomas H. (LinkedIn, Jan 2026) warns of a "2026 Developer Crisis" — not a shortage of devs, but a surplus of bad AI-generated code. Ruslan Mashatov (LinkedIn, Feb 2026) notes "in high-debt systems, a significant share of engineering effort shifts from feature development to maintenance."

However, this validates the DLD approach: **if refactoring and testing are cheap (agent-executed), they should be done aggressively and continuously, not deferred**. The crisis comes from teams that used AI to generate code but kept the old prioritization model that deprioritizes cleanup.

CircleCI launched "Chunk AI agent" (Jan 2026) specifically for continuous AI-driven refactoring — treating it as a background process, not a prioritized task.

**Implication for DLD:** Refactoring and testing tasks should be treated as "always-on background processes" rather than backlog items competing for priority. They are infrastructure, not features.

Sources:
- linkedin.com/posts/henningtl (Thomas H., Jan 2026)
- linkedin.com/posts/ruslan-mashatov (Mashatov, Feb 2026)
- circleci.com/blog/refactor-your-codebase-with-circleci-chunk-ai-agent (Jan 2026)

---

## Sources

| # | Source | Date | Key Contribution |
|---|--------|------|------------------|
| 1 | OpenAI, "Harness Engineering" | Feb 2026 | 0 manual code, 1M LOC, humans steer agents execute |
| 2 | Martin Fowler / Thoughtworks, "Harness Engineering" analysis | Feb 2026 | Human role = building the harness (tests, CI, constraints) |
| 3 | Reinertsen, "Practical Science of Prioritization" | 2013 | Original WSJF: CoD/Duration — constant duration = pure CoD |
| 4 | Haque, "New Software Cost Curve under Agentic AI" | 2026 | Academic analysis of AI agent development economics |
| 5 | Ulin, "When Software Costs Hit Zero" | Feb 2026 | First/second/third-order effects of zero marginal cost software |
| 6 | Pane/Doozy, "Two Founders, 300k Lines, Zero Engineers" | Mar 2026 | Real AI-native team, effort never a factor in prioritization |
| 7 | Cursor, "The Third Era" | Feb 2026 | "Building the factory that creates software" |
| 8 | Zylos Research, "Multi-Agent Software Development" | Mar 2026 | 72% enterprise AI projects use multi-agent (up from 23%) |
| 9 | HumanLayer, "Skill Issue: Harness Engineering" | Mar 2026 | "Not a model problem, it's a configuration problem" |
| 10 | Poll, "Tech Debt Equation Changing" | Aug 2025 | Tech debt interest rate plummets when rewrite is cheap |
| 11 | Jason Yip, "Problems with SAFe-style WSJF" | Mar 2024 | WSJF's value is CoD/Duration trade-off; remove duration = pure CoD |
| 12 | jpalmer.dev, "Prioritizing with Cost of Delay" | 2021 | CoD helps teams stop deprioritizing tech debt |
| 13 | CircleCI, "Chunk AI Agent" | Jan 2026 | Continuous AI-driven refactoring as background process |
| 14 | InfoQ, "Harness Engineering" analysis | Feb 2026 | Industry coverage of OpenAI's methodology |
| 15 | Bet on AI, "AI Coding Agency Blueprint" | Mar 2026 | $5-30 AI cost per $500-5000 project — effort is rounding error |

---

## Recommendations

### R1: Replace WSJF with Pure Cost of Delay Ranking

Since implementation effort is effectively constant ($1-5/task via autopilot), WSJF = CoD/Effort simplifies to CoD. All prioritization in spark, council, architect, and devil's advocate should rank by:

1. **Revenue impact** — how much money is lost per week without this?
2. **Time criticality** — does value decay if delayed? (market window, competitive pressure)
3. **Risk reduction** — does this prevent a catastrophic failure?

Remove "effort", "story points", "job size" from all priority formulas. Keep them as cost-tracking metadata only.

### R2: Elevate Refactoring and Testing to "Harness Infrastructure"

Following OpenAI's Harness Engineering model, tests, CI, and architectural constraints are **the harness** — the infrastructure that makes agent output reliable. They should:

- Never compete with features for priority
- Run as continuous background processes (like CircleCI Chunk)
- Be triggered automatically after every feature implementation
- Have their own dedicated autopilot slots (1 of 5 slots for continuous refactoring)

### R3: Replace Human Capacity Language with AI Economics

All decision-making prompts in council, architect, and devil's advocate should use AI-centric costs:

| Old (Human) | New (AI-First) |
|-------------|----------------|
| "Team is busy for 2 weeks" | "5 parallel slots available now" |
| "This is a 3-sprint effort" | "This is $3-15 in API costs" |
| "We can't afford the refactoring" | "Refactoring costs $5, not doing it costs $X/week in CoD" |
| "Too complex for this sprint" | "Break into 5 parallel tasks, done in 1 cycle" |
| "Tech debt is acceptable trade-off" | "Tech debt interest > refactoring cost; fix now" |

### R4: Adopt "Spec Clarity" as the New Bottleneck Metric

When implementation is cheap, the bottleneck shifts to **how clear the spec is**. This aligns with Cursor's "third era" insight and OpenAI's harness engineering. Priority should also weight:

- Spec completeness (can an agent execute this without ambiguity?)
- Test coverage of acceptance criteria (is the harness ready?)
- Dependency clarity (are blockers identified?)

A well-specified low-CoD task should rank above a vaguely-specified high-CoD task, because the vague task will burn cycles on agent confusion.

### R5: Implement "Always-Refactor" Policy

Based on the tech debt crisis evidence (Thomas H., Mashatov), adopt a policy where:

- Every feature completion triggers an automatic refactoring pass
- TECH tasks are never deprioritized below P1; they are infrastructure
- The council/devil's advocate should argue *for* refactoring by default, not against it
- Budget 1 of 5 autopilot slots permanently for refactoring/testing

This directly implements the "Zen of AI Coding" principles: "Code is cheap", "Refactoring easy", "Tech debt is shallow."
