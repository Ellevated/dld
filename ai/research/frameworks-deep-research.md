# Deep Research: Thinking Frameworks for AI Agents

**Date:** 2026-02-13
**Context:** Philosophy chat, exploring frameworks beyond TOC for DLD agent system
**Method:** 4 parallel scouts (Exa Deep Research + web search), ~$5 total research cost
**Meta-observation:** We don't know what scouts did inside their contexts (black box problem)

---

## Scout Reports Summary

### Scout 1: TRIZ (Altshuller, 1946)

**Core:** 40 inventive principles derived from 200K+ patent analysis. Resolves contradictions without compromise.

**Key Findings:**
- **AutoTRIZ** (Jiang et al., 2025, Advanced Engineering Informatics) — first fully automated TRIZ + LLM system
- **TRIZ-GPT** (Chen et al., 2024) — CoT prompting for contradiction analysis
- **TRIZ Agents** (Szczepanik & Chudziak, 2025) — multi-agent LLM system for TRIZ. Each agent = specialized TRIZ domain
- **IFR for agents:** "The agents themselves coordinate without coordinator"
- **TRIZ + TOC documented:** Stratton & Mann (2003) — TOC finds WHERE, TRIZ finds HOW

**Software-specific principles:**
| Principle | Software Application |
|-----------|---------------------|
| 1 Segmentation | Monolith → microservices |
| 15 Dynamics | Static config → runtime adaptive |
| 24 Intermediary | Direct access → middleware/proxy |
| 35 Parameter Change | Sync → async, stateful → stateless |

**Physical vs Technical Contradictions:**
- Technical: "Improving A worsens B" → 40 Principles + Contradiction Matrix
- Physical: "X must be A and not-A" → 4 Separation Principles (Time, Space, Condition, Scale)

**Criticism:**
- Learning curve is steep
- Designed for physical engineering, software mapping is nascent
- Most practitioners use simplified TRIZ (principles + matrix), not full ARIZ
- Software TRIZ research is "still in initial phase" (20+ years of discussion)

**Sources:** arxiv.org/abs/2403.13002 (AutoTRIZ), arxiv.org/abs/2408.05897 (TRIZ-GPT), arxiv.org/html/2506.18783v1 (TRIZ Agents)

---

### Scout 2: Cynefin (Snowden)

**Core:** 5 domains based on cause-effect relationship nature.

**Key Findings:**
- **Cynefin for AI bots** (Ilieva et al., 2018) — decision model for AI bots in agile orgs, switching strategies by complexity
- **Incident response mapping** — Clear (runbook) → Complicated (expert diagnosis) → Complex (probe/experiment) → Chaotic (act first)
- **SenseMaker tool** — collects micro-narratives, detects emergent patterns via triads/dyads
- **Boundary dynamics:** "Chaotic Cliff" (complex → chaos) and "Complacency Trap" (over-reliance on best practices)

**Agent routing insight:**
| Domain | Agent Strategy | Example |
|--------|---------------|---------|
| Clear | Rule-based, runbooks | Known error → known fix |
| Complicated | Expert analysis | Performance profiling |
| Complex | Probe → Sense → Respond | Novel bug, safe-to-fail experiments |
| Chaotic | Act → Sense → Respond | Production down, rollback first |

**Criticism:**
- Discrete categories can obscure multi-dimensional reality
- Boundary zones are fuzzy
- Empirical validation limited

**Sources:** Exa Deep Research ($1.38, 121 pages, 31 searches), thecynefin.co, Snowden & Boone HBR 2007

---

### Scout 3: Systems Thinking (Meadows, Forrester)

**Core:** 12 leverage points, stocks/flows/feedback loops, system archetypes.

**Key Findings:**
- **Meadows' 12 Leverage Points** (weakest → strongest):
  12. Constants/parameters (buffer sizes, timeouts)
  11. Buffer sizes
  10. Stock-and-flow structure
  9. Delays
  8. **Negative feedback loops** (circuit breakers, backoff)
  7. **Positive feedback loops** (retry storms, tech debt spiral)
  6. **Information flows** (observability — "meter in front hall")
  5. **Rules of the system** (access control, SLAs)
  4. **Self-organization** (plugin architecture)
  3. **Goals of the system** (speed vs reliability)
  2. **Paradigm/mindset** (waterfall → agile)
  1. **Transcending paradigms** (holding all models lightly)

- **System Archetypes for software:**
  - "Fixes That Fail" — hotfix creates new bugs
  - "Shifting the Burden" — duct tape → ignoring root cause → dependency on workaround
  - "Limits to Growth" — success hits infrastructure limits
  - "Success to the Successful" — popular services get resources, others starve

- **LLMs + Causality research (cutting edge 2024-2026):**
  - Causal Modelling Agents (ICLR 2024) — LLMs + causal graph discovery
  - Language Agents Meet Causality (ICLR 2025) — LLMs + causal world models
  - "Agentic AI Needs Systems Theory" (arXiv 2026-02-14!) — published day after our research
  - AICL Control Loop (Zenodo 2025) — formalized agent reasoning as closed-loop

- **Critical gap:** NO production LLM systems explicitly model stocks/flows/feedback in reasoning

**Criticism:**
- "Systems thinking isn't enough anymore" (2025 critique)
- Humans evolved for immediate thinking, not systemic
- Can lead to analysis paralysis
- "The Systems Fallacy" (Columbia Law 2018) — models can mask political choices

**Sources:** 50+ sources, donellameadows.org, MIT System Dynamics Group, arxiv.org papers

---

### Scout 4: Other Frameworks

**Core:** Judea Pearl's Causal Inference, OODA Loop, Kepner-Tregoe, Morphological Analysis, Bayesian Debugging, Hegelian Dialectics

**Key Findings:**

#### Judea Pearl's Causal Inference (STRONGEST CANDIDATE)
- **do-calculus** — formal mathematical framework for causation (not correlation)
- Pearl's "Ladder of Causation": Association → Intervention → Counterfactual
- Already applied to fault localization: Causal AI for RCA (IBM Research + Instana, Feb 2025)
- "The Seven Tools of Causal Inference" (CACM) — Pearl argues ML is "curve fitting" without causality
- **More rigorous than TOC's CRT** — grounded in formal math, provably correct

#### OODA Loop (John Boyd)
- Observe → Orient → Decide → Act
- **Orient is everything** — where mental models shape observations into decisions
- "Operate inside opponent's decision cycle" → iterate faster than bugs accumulate
- Already used in defense AI systems (2025-2026)

#### Kepner-Tregoe IS/IS-NOT
- 4 dimensions (What/Where/When/Extent) x IS/IS-NOT matrix
- VDA (German automotive) officially recommends for 8D problem-solving
- Forces systematic evidence BEFORE hypothesis
- **Key insight:** contrasts with what DIDN'T happen

#### Morphological Analysis (Fritz Zwicky)
- Systematic exploration of solution space via parameter combinations
- Cross-consistency assessment prevents invalid combinations
- **Zwicky discovered dark matter using this method**
- Underutilized in software engineering

#### Bayesian Debugging
- Bayesian framework unifying Fault Localization and Automated Program Repair (Kang 2023)
- Tractable Fault Localization Models (Nath & Domingos 2015)
- Probabilistic approach to debugging — learned patterns from buggy programs

#### Hegelian Dialectics
- Thesis → Antithesis → Synthesis
- Microsoft Research (2025): "Self-reflecting LLMs: A Hegelian Dialectical Approach"
- Self-dialectical approach for LLM self-reflection
- **DLD Council already implements this pattern** (multiple experts → synthesis)

**Sources:** Pearl CACM, arxiv.org/pdf/2206.05871, kepner-tregoe.com, swemorph.com/pdf/gma.pdf

---

## Cross-Framework Synthesis

### What each framework answers

| Framework | Question | Strength |
|-----------|----------|----------|
| TOC | What is THE constraint? | Focus, simplicity |
| TRIZ | How to resolve THE contradiction? | Innovation, no-compromise |
| Cynefin | What KIND of problem is this? | Domain classification |
| Systems Thinking | What are the feedback LOOPS? | Dynamic understanding |
| Causal Inference | What CAUSES what? | Mathematical rigor |
| OODA | How to ACT faster? | Tempo, adaptation |
| Kepner-Tregoe | What IS and what IS-NOT? | Evidence discipline |
| Morphological Analysis | What COMBINATIONS exist? | Exhaustive search |

### Potential DLD Integration

**Bug detection pipeline (hypothesis):**
1. **Cynefin** classifies problem domain (Clear/Complicated/Complex/Chaotic)
2. **Kepner-Tregoe IS/IS-NOT** structures evidence collection
3. **TOC CRT** identifies root cause chain (UDEs → core conflict)
4. **Causal Inference** validates causal claims mathematically
5. **TRIZ** resolves architectural contradictions
6. **Systems Thinking** checks for unintended feedback loops

**Agent routing (hypothesis):**
- **Clear bugs:** Single agent + runbook → fast
- **Complicated bugs:** Expert agent + KT analysis → thorough
- **Complex bugs:** Multi-agent probe → sense → respond → expensive but necessary
- **Chaotic (production down):** Act first (rollback), analyze later

---

## Meta-Observations

### The Scout Black Box Problem
We sent 4 scouts into isolated contexts. Each:
- Chose their own search queries
- Followed their own reasoning chains
- Decided what to include/exclude in final report
- Has unknown blind spots

**We can't verify coverage.** This is exactly the BUG-477 phenomenon:
- 22 unique issues across 10 runs
- No single run found >50%
- Each scout = one run with one lens

### Cost of This Research
- 4 scouts: ~$5 total (Exa Deep Research: $1.38 for Cynefin alone)
- Human alternative: 2-3 days of reading papers
- ROI: massive if even ONE insight prevents a $20K rework

### What We Don't Know (Known Unknowns)
- How do these frameworks perform when operationalized in LLM prompts?
- Do they compose well or create conflicting instructions?
- Which frameworks actually improve BUG-477 detection rate?
- Is there a framework we haven't found yet? (Unknown unknowns)

---

## Plot Twist: Persona Diversity > Frameworks (Feb 13 evening)

After all the framework research, empirical testing revealed a simpler pattern.

### The Stout Prompt
User's most effective code review prompt (paraphrased):
> "Ты яростный критик опенсорс проектов на гитхаб. Порви этот молодой проект. За каждый найденный баг — бутылка стаута."

No framework. No methodology. Just a **persona with motivation**.

### Why This Works
Changing the persona changes:
1. **Role** — from helpful assistant to aggressive critic
2. **Motivation** — from "help user" to "find bugs" (beer incentive)
3. **Social context** — from collaborative to adversarial
4. **Default LLM behavior** — breaks the agreeable/helpful pattern

### The Real Pattern
```
Run 1: "Яростный критик опенсорс. Стаут за баг."
Run 2: "Параноидальный безопасник."
Run 3: "UX-дизайнер, прошёл весь флоу руками."
Run 4: "Джун, читаешь этот код впервые."
Run 5: "Архитектор, тебя тошнит от связности."
Run 6: "QA, платят за каждый найденный баг."
```

6 personas × $6-10 = $36-60. Maximum coverage through cognitive diversity.

### Frameworks = Explanatory, Not Prescriptive
Frameworks (TOC, TRIZ, Pearl, Cynefin) explain WHY different lenses find different things.
But the OPERATIONAL mechanism is simpler: different personas → different behavior → different bugs found.

### Empirical Evidence (Round 3)
- **v4** (architectural persona) found 7 UDEs: FSM state filters, router priority, missing keyboards
- **Real teammates** (UX persona) found 6 UDEs: blank screen, no CTA, double messages
- **Overlap: 1 out of ~11 unique issues**
- UGC_PUBLISHED blank screen (CRITICAL) found ONLY by teammates, through adversarial challenge

### Open Question
Is pure persona diversity sufficient? Or does adversarial interaction (agent challenges agent) add value beyond parallel independent runs? The UDE-7 discovery suggests interaction matters — but needs more data.

### Experiment #5 (in progress)
Testing persona-based diversity on BUG-477. User running in parallel chat.

---

## Raw Data Locations

Scout conversation logs (jsonl, contain full Exa results):
- TRIZ: `~/.claude/projects/.../subagents/agent-afa26e6.jsonl`
- Cynefin: `~/.claude/projects/.../subagents/agent-a6485a5.jsonl`
- Systems Thinking: `~/.claude/projects/.../subagents/agent-aa32942.jsonl`
- Other Frameworks: `~/.claude/projects/.../subagents/agent-a033d35.jsonl`

Session: `466d5577-ea15-4f91-8016-e40c90d80148`
