# Feature: [TECH-153] AI-First Economic Model for DLD Framework

**Status:** queued | **Priority:** P1 | **Date:** 2026-03-17

## Why

DLD agents (council, architect, spark, devil) make decisions using human-centric effort estimates ("refactoring takes 3 weeks", "team busy for a sprint"). This systematically distorts prioritization:

- **Refactoring always deprioritized** — "too expensive" when it costs $5-10
- **Testing cut "for economy"** — when it costs $1
- **Priority inflation by effort** — P2 assigned to high-value tasks because "effort is high"
- **False blocking** — "team busy for a week" when 5 parallel slots available

Reality: 1 autopilot task = $1, refactoring = $5-10, 5 parallel slots, founder's hour = $200. WSJF collapses to pure Cost of Delay when effort is constant (Reinertsen). RICE collapses to R×I×C.

## Context

**Research basis (4 scouts, 2026-03-17):**
- OpenAI Harness Engineering (Feb 2026): 0 manual code, 1M LOC, "humans steer, agents execute"
- "Zen of AI Coding" (Aviram, Mar 2026): "Code is cheap", "Refactoring easy", "Tech debt is shallow"
- Haque 2026: "New Software Cost Curve under Agentic AI" — academic analysis
- Codebase scout: **47 findings across 28 files** with human-centric metrics
- Council already has gold-standard LLM-native mindset blocks (council/SKILL.md:37-38)
- 6 agents missing LLM-native mindset blocks entirely

**Selected approach:** Impact + Risk (replace effort with Risk dimension R0/R1/R2)

---

## Scope

**In scope:**
- Replace human-time language (days/hours/weeks/sprints) with AI-cost language ($1/$5/$10) in all affected agents/skills
- Add Risk classification (R0/R1/R2) as second axis alongside Priority (P0/P1/P2)
- Add Impact×Risk routing matrix to Spark Phase 4
- Add LLM-native mindset blocks to 6 agents missing them
- Add AI-First Economic Model rule to CLAUDE.md (both root and template)
- Template changes: add compute-cost language ALONGSIDE human-time (backward compat)
- DLD-specific changes: REPLACE human-time with compute-cost

**Out of scope:**
- Changing P0/P1/P2 severity system (it's sound for triage — KEEP)
- WSJF-AI numerical formula (LLMs bad at consistent numeric scoring)
- Backlog restructuring (categorical sections work fine)
- Business metrics (CAC payback, revenue targets — legitimate business language)
- Project lifecycle stages ("Day 1", "Day 2" — sequencing, not sizing)

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
- All skills that make priority/effort decisions: spark, council, architect, board, audit, planner
- All agents that evaluate trade-offs: pragmatist, architect, security, product, devil, patterns, synthesizer

### Step 2: DOWN — what depends on?
- CLAUDE.md (all agents read this)
- Spec template (autopilot reads this)
- Backlog format (orchestrator reads this)

### Step 3: BY TERM — grep entire project
- "days", "hours", "weeks", "sprint" in agent prompts → 47 findings (see research-codebase.md)

### Step 4: CHECKLIST
- [x] `tests/**` — no test changes needed (prompt-only changes)
- [x] `ai/glossary/**` — N/A
- [x] `db/migrations/**` — N/A

### Verification
- [x] All found files added to Allowed Files
- [x] grep by old terms = 0 after implementation

---

## Allowed Files

**ONLY these files may be modified during implementation:**

### Root .claude/ (DLD-specific — REPLACE human-time)
1. `.claude/agents/architect/synthesizer.md` — replace "X days" effort template with $-cost (F-01, F-03)
2. `.claude/agents/architect/evolutionary.md` — remove "sprint" language, add LLM-native block (F-02, F-38)
3. `.claude/agents/architect/dx.md` — add LLM-native mindset block (F-39)
4. `.claude/agents/board/coo.md` — add LLM-native mindset block, add agent-capacity alongside barrels/ammunition (F-19, F-41)
5. `.claude/agents/board/cmo.md` — add LLM-native mindset block (F-42)
6. `.claude/agents/audit/synthesizer.md` — define S/M/L in compute terms (F-10)
7. `.claude/agents/spark/patterns.md` — replace "time estimate" with compute-cost + add LLM-native block (F-30, F-31, F-43)
8. `.claude/agents/spark/devil.md` — quantify ROI in $ not vague "effort" (F-32, F-33)
9. `.claude/agents/council/synthesizer.md` — standardize effort format to $ (F-11)
10. `.claude/skills/spark/feature-mode.md` — add Impact×Risk routing matrix to Phase 4 (F-24)
11. `.claude/skills/architect/retrofit-mode.md` — replace "small|medium|large" with compute-cost (F-09)
12. `.claude/skills/brandbook/completion.md` — replace "Day 1/2/3" with compute-cost phases (F-07)
13. `.claude/skills/architect/greenfield-mode.md` — "compute capacity" not "team Y" (F-21)
14. `.claude/skills/bootstrap/SKILL.md` — add compute budget alongside hours question (F-04, F-05, F-06)

### Root CLAUDE.md + rules
15. `CLAUDE.md` — add AI-First Economic Model section + Risk Classification Guide + P0/P1/P2 redefinition
16. `.claude/skills/spark/completion.md` — add Risk field to backlog entry format

### template/.claude/ (universal — ADD compute-cost ALONGSIDE human-time)
17. `template/.claude/agents/architect/synthesizer.md` — add compute-cost format alongside days
18. `template/.claude/agents/architect/evolutionary.md` — add LLM-native block
19. `template/.claude/agents/architect/dx.md` — add LLM-native block
20. `template/.claude/agents/board/coo.md` — add LLM-native block
21. `template/.claude/agents/board/cmo.md` — add LLM-native block
22. `template/.claude/agents/audit/synthesizer.md` — define S/M/L in compute terms
23. `template/.claude/agents/spark/patterns.md` — add compute-cost alongside time
24. `template/.claude/skills/spark/feature-mode.md` — add routing matrix
25. `template/.claude/skills/architect/retrofit-mode.md` — add compute-cost alongside T-shirt
26. `template/.claude/skills/brandbook/completion.md` — add compute-cost alongside days
27. `template/.claude/skills/architect/greenfield-mode.md` — add compute capacity
28. `template/.claude/skills/bootstrap/SKILL.md` — add compute budget field
29. `template/CLAUDE.md` — add AI-First Economic Model section (universal version)
30. `template/.claude/skills/spark/completion.md` — add Risk field to backlog format

**FORBIDDEN:** All other files. Files verified clean by codebase scout: autopilot, coder, review, reflect, qa, tester, documenter, scout, rules/architecture.md, rules/dependencies.md.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** DLD framework (meta — skills/agents/rules)
**Cross-cutting:** All skills that make priority or trade-off decisions
**Data model:** No data model changes — prompt-only modifications

---

## Approaches

### Approach 1: Minimal — 1 paragraph in CLAUDE.md (Devil's recommendation)
**Source:** research-devil.md
**Summary:** Add "AI-First Effort Model" paragraph to CLAUDE.md, nothing else
**Pros:** Zero risk, 1 file, 5 minutes
**Cons:** Doesn't fix 47 instances of "X days" baked into agent prompts — CLAUDE.md rule won't override specific instructions

### Approach 2: Impact + Risk Framework (Selected)
**Source:** research-patterns.md, research-codebase.md, research-external.md
**Summary:** Replace effort with Risk (R0/R1/R2), add LLM-native blocks to 6 agents, fix all 47 human-centric instances, add routing matrix
**Pros:** Systematic, catches all instances, council already half-works this way, LLMs good at categorical R0/R1/R2
**Cons:** ~30 files, template backward compat (mitigated: add alongside, not replace in template)

### Approach 3: WSJF-AI numerical formula
**Source:** research-patterns.md Approach 3
**Summary:** Mathematical `WSJF-AI = CoD / Risk Score` with 1-5 scales
**Pros:** Mathematically rigorous
**Cons:** LLMs bad at consistent numeric scoring, agents will game scores, overhead

### Selected: 2
**Rationale:** Council already uses LLM-native cost language (gold standard exists). Approach 2 formalizes and propagates what already works. Risk categories (R0/R1/R2) are natural for LLM categorical judgment. Devil's mitigations incorporated: keep effort as $-cost metadata, template backward compat, priority inflation gate.

---

## Design

### New Concepts

**Risk Classification (R0/R1/R2):**
```
R0 = Irreversible: data loss, schema migration, security exposure, public API break
R1 = High blast radius: 3+ files, cross-domain, external dependency, state machine change
R2 = Contained: 1-2 files, single domain, internal, trivially rollbackable
```

**Impact×Risk Routing Matrix (Spark Phase 4):**

| Impact \ Risk | R0 (Irreversible) | R1 (Blast radius) | R2 (Contained) |
|---|---|---|---|
| P0 | COUNCIL | HUMAN | AUTO |
| P1 | COUNCIL | AUTO | AUTO |
| P2 | HUMAN | AUTO | AUTO |

**AI-First P0/P1/P2 Definitions:**
```
P0 = Blocks revenue, users, or security RIGHT NOW (Cost of Delay: immediate)
P1 = High impact on product quality, including refactoring and testing (Cost of Delay: this week)
P2 = Nice-to-have, doesn't affect metrics this week (Cost of Delay: low)
```

**Key rule:** Implementation effort ($1-50) is NEVER a factor in priority assignment. Priority = pure Impact/Cost of Delay.

**Devil's Mitigations (incorporated):**
1. Keep effort field in spec but as "$1/$5/$10" not "days"
2. Template: ADD compute-cost alongside human-time (backward compat for human teams)
3. Max 5 P0 tasks in backlog simultaneously (priority inflation gate)
4. Refactoring/testing = P1 by default (never deprioritized)

### LLM-Native Mindset Block (standard for all agents making cost decisions)

Copy from council/architect.md (gold standard):
```markdown
## LLM-Native Mindset (CRITICAL!)

❌ "This refactoring would take a team 2-3 sprints"
✅ "Autopilot can refactor this in 2 hours with full test coverage"

Cost reference:
- Simple change (1-3 files): 15 min, ~$1
- Medium change (5-10 files): 1-2 hours, ~$5
- Large change (20+ files): 3-4 hours, ~$15
- Full domain extraction: 1 day, ~$50

NEVER deprioritize based on implementation effort.
Priority = Impact × Cost of Delay, not effort.
```

---

## UI Event Completeness

N/A — no UI elements.

---

## Implementation Plan

### Research Sources
- [OpenAI Harness Engineering](https://openai.com/index/harness-engineering/) — "humans steer, agents execute", tests/CI are the harness
- [Zen of AI Coding](https://nonstructured.com/zen-of-ai-coding/) — "Code is cheap", "Refactoring easy"
- [WSJF in SAFe](https://agility-at-scale.com/safe/lpm/wsjf-weighted-shortest-job-first/) — CoD/JobSize, constant JobSize = pure CoD
- Codebase scout: 47 findings in research-codebase.md

### Task 1: Add AI-First Economic Model to CLAUDE.md
**Type:** code
**Files:**
  - modify: `CLAUDE.md` — add ## AI-First Economic Model section with Risk Classification, P0/P1/P2 redefinition, routing matrix reference
  - modify: `template/CLAUDE.md` — add universal version (mentions both AI and human teams)
**Pattern:** Council SKILL.md lines 37-38 (gold standard LLM-native block)
**Acceptance:** CLAUDE.md contains Risk Classification (R0/R1/R2), AI-first P0/P1/P2 definitions, and "never deprioritize by effort" rule

### Task 2: Add LLM-Native Mindset Blocks to 6 Missing Agents
**Type:** code
**Files:**
  - modify: `.claude/agents/architect/evolutionary.md` — add LLM-native block, remove "sprint" (F-02, F-38)
  - modify: `.claude/agents/architect/dx.md` — add LLM-native block (F-39)
  - modify: `.claude/agents/architect/synthesizer.md` — replace "X days" with $-cost (F-01, F-03, F-40)
  - modify: `.claude/agents/board/coo.md` — add LLM-native block + agent-capacity (F-19, F-41)
  - modify: `.claude/agents/board/cmo.md` — add LLM-native block (F-42)
  - modify: `.claude/agents/spark/patterns.md` — replace "time estimate" with compute-cost + add block (F-30, F-31, F-43)
  - modify: `template/.claude/agents/architect/evolutionary.md`
  - modify: `template/.claude/agents/architect/dx.md`
  - modify: `template/.claude/agents/architect/synthesizer.md`
  - modify: `template/.claude/agents/board/coo.md`
  - modify: `template/.claude/agents/board/cmo.md`
  - modify: `template/.claude/agents/spark/patterns.md`
**Pattern:** `.claude/agents/council/architect.md` lines 39-54 (gold standard)
**Acceptance:** All 6 agents have LLM-native mindset block. No "sprint", "X days", "time estimate" remains. `grep -r "sprint\|X days\|time estimate" .claude/agents/` returns only FORBIDDEN examples.

### Task 3: Fix Effort Language in Skills + Add Routing Matrix
**Type:** code
**Files:**
  - modify: `.claude/skills/spark/feature-mode.md` — add Impact×Risk routing matrix to Phase 4 (F-24)
  - modify: `.claude/skills/spark/completion.md` — add Risk field to backlog entry format
  - modify: `.claude/skills/architect/retrofit-mode.md` — replace "small|medium|large" with compute-cost (F-09)
  - modify: `.claude/skills/architect/greenfield-mode.md` — "compute capacity" not "team Y" (F-21)
  - modify: `.claude/skills/brandbook/completion.md` — compute-cost phases (F-07)
  - modify: `.claude/skills/bootstrap/SKILL.md` — add compute budget alongside hours (F-04, F-05, F-06)
  - modify: `.claude/agents/spark/devil.md` — quantify in $ (F-32, F-33)
  - modify: `.claude/agents/council/synthesizer.md` — standardize to $ (F-11)
  - modify: `.claude/agents/audit/synthesizer.md` — define S/M/L in compute terms (F-10)
  - modify: `template/.claude/skills/spark/feature-mode.md`
  - modify: `template/.claude/skills/spark/completion.md`
  - modify: `template/.claude/skills/architect/retrofit-mode.md`
  - modify: `template/.claude/skills/architect/greenfield-mode.md`
  - modify: `template/.claude/skills/brandbook/completion.md`
  - modify: `template/.claude/skills/bootstrap/SKILL.md`
  - modify: `template/.claude/agents/spark/devil.md`
  - modify: `template/.claude/agents/council/synthesizer.md`
  - modify: `template/.claude/agents/audit/synthesizer.md`
**Pattern:** Council pragmatist.md lines 51-55 (compute-cost reference)
**Acceptance:** `grep -rn "X days\|hours/week\|person-day\|человеко" .claude/ template/.claude/` returns 0 results (excluding FORBIDDEN examples). Routing matrix present in Phase 4.

### Execution Order
1 → 2 → 3

---

## Flow Coverage Matrix (REQUIRED)

| # | Change | Covered by Task | Status |
|---|--------|-----------------|--------|
| 1 | CLAUDE.md AI-First Economic Model | Task 1 | new |
| 2 | template/CLAUDE.md universal version | Task 1 | new |
| 3 | 6 agents get LLM-native mindset blocks | Task 2 | new |
| 4 | "X days"/"sprints" removed from agents | Task 2 | new |
| 5 | Impact×Risk routing matrix in Phase 4 | Task 3 | new |
| 6 | Risk field in backlog format | Task 3 | new |
| 7 | T-shirt sizing defined in compute terms | Task 3 | new |
| 8 | Bootstrap adds compute budget field | Task 3 | new |
| 9 | Devil quantifies ROI in $ | Task 3 | new |

**GAPS:** None. All 47 findings from codebase scout mapped to tasks.

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | No human-time estimates in .claude/ agents | `grep -rn "X days\|hours/week\|person-day" .claude/agents/` | 0 results (excluding FORBIDDEN blocks) | deterministic | codebase scout | P0 |
| EC-2 | No "sprint" language in agents | `grep -rn "sprint" .claude/agents/` | 0 results (excluding FORBIDDEN blocks) | deterministic | codebase scout | P0 |
| EC-3 | All 6 target agents have LLM-native block | `grep -l "LLM-Native Mindset" .claude/agents/architect/evolutionary.md .claude/agents/architect/dx.md .claude/agents/architect/synthesizer.md .claude/agents/board/coo.md .claude/agents/board/cmo.md .claude/agents/spark/patterns.md` | 6 files found | deterministic | codebase scout | P0 |
| EC-4 | Risk classification in CLAUDE.md | `grep "R0.*Irreversible" CLAUDE.md` | Found | deterministic | patterns scout | P0 |
| EC-5 | Routing matrix in spark feature-mode | `grep "Impact.*Risk" .claude/skills/spark/feature-mode.md` | Found | deterministic | patterns scout | P1 |
| EC-6 | Risk field in backlog format | `grep "Risk" .claude/skills/spark/completion.md` | Found | deterministic | patterns scout | P1 |
| EC-7 | Template has compute-cost alongside (not replacing) human-time | `grep -c "compute\|\\$" template/.claude/agents/architect/synthesizer.md` | ≥1 match | deterministic | devil scout | P1 |
| EC-8 | Patterns agent uses compute-cost not "time estimate" | `grep "time estimate" .claude/agents/spark/patterns.md` | 0 results | deterministic | codebase scout | P1 |

### Coverage Summary
- Deterministic: 8 | Integration: 0 | LLM-Judge: 0 | Total: 8

### TDD Order
1. EC-1, EC-2 (grep for old patterns → should find them before fix)
2. EC-3 (check missing blocks → add them)
3. EC-4, EC-5, EC-6 (check new artifacts → add them)
4. EC-7, EC-8 (verify template strategy)

---

## Acceptance Verification (MANDATORY)

### Smoke Checks (process alive)

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Grep finds no human-time patterns | `grep -rn "X days\]\|hours/week\|person-day\|20% of each sprint" .claude/agents/ --include="*.md" \| grep -v FORBIDDEN \| grep -v "❌"` | exit 0, empty output | 10s |

### Functional Checks (business logic)

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | All 6 agents have LLM-native block | None | `for f in .claude/agents/architect/{evolutionary,dx,synthesizer}.md .claude/agents/board/{coo,cmo}.md .claude/agents/spark/patterns.md; do grep -q "LLM-Native Mindset" "$f" && echo "OK: $f" || echo "MISSING: $f"; done` | All 6 show "OK" |
| AV-F2 | CLAUDE.md has Risk Classification | None | `grep -c "R0.*R1.*R2\|Risk Classification" CLAUDE.md` | ≥1 |
| AV-F3 | Routing matrix in Phase 4 | None | `grep -A5 "Impact.*Risk" .claude/skills/spark/feature-mode.md` | Shows P0/P1/P2 × R0/R1/R2 matrix |

### Verify Command (copy-paste ready)

```bash
# Smoke: no human-time patterns
echo "=== AV-S1: Human-time patterns ===" && grep -rn "X days\]\|hours/week\|person-day\|20% of each sprint" .claude/agents/ --include="*.md" | grep -v FORBIDDEN | grep -v "❌" | head -5 && echo "FAIL: found human-time patterns" || echo "PASS"

# Functional: LLM-native blocks
echo "=== AV-F1: LLM-native blocks ===" && for f in .claude/agents/architect/{evolutionary,dx,synthesizer}.md .claude/agents/board/{coo,cmo}.md .claude/agents/spark/patterns.md; do grep -q "LLM-Native Mindset" "$f" && echo "OK: $f" || echo "MISSING: $f"; done

# Functional: Risk Classification
echo "=== AV-F2: Risk Classification ===" && grep -c "R0" CLAUDE.md && echo "PASS" || echo "FAIL"

# Functional: Routing matrix
echo "=== AV-F3: Routing matrix ===" && grep -c "Impact.*Risk" .claude/skills/spark/feature-mode.md && echo "PASS" || echo "FAIL"
```

### Post-Deploy URL
```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [x] AI-First Economic Model added to CLAUDE.md (root + template)
- [x] Risk Classification (R0/R1/R2) defined
- [x] Impact×Risk routing matrix in Spark Phase 4
- [x] 6 agents have LLM-native mindset blocks
- [x] All human-time language replaced in .claude/ agents
- [x] Template has compute-cost alongside human-time (backward compat)
- [x] All tasks from Implementation Plan completed

### Tests
- [x] All eval criteria (EC-1 through EC-8) pass
- [x] Coverage not decreased

### Acceptance Verification
- [x] AV-S1 passes (no human-time patterns)
- [x] AV-F1 passes (all 6 agents have blocks)
- [x] AV-F2 passes (Risk Classification in CLAUDE.md)
- [x] AV-F3 passes (routing matrix present)

### Technical
- [x] No regressions

---

## Autopilot Log
[Auto-populated by autopilot during execution]
