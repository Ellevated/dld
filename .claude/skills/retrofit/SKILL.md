---
name: retrofit
description: Brownfield lifecycle — reassess existing projects through Deep Audit, Architect recovery, Board re-prioritization, and Stabilization.
model: opus
---

# Retrofit — Brownfield Lifecycle Orchestrator

Systematic reassessment of existing projects. Inverted flow: understand code first, then design architecture, then set business priorities.

**Activation:** `/retrofit`, "retrofit", "brownfield", "reassess project"
**Input:** Existing codebase (any state)
**Output:** Blueprints + migration-path.md + stabilized codebase

## When to Use

- **Framework upgrade** -- project started on DLD v1, now v2 exists
- **Pivot** -- business direction changed, code diverges from new goal
- **Bugfix/feature ratio > 1:1** -- more time fixing than building
- **Organic growth** -- implicit decisions accumulated, conventions drifted
- **`/triz` shows systemic constraint** -- diagnostic suggests deep reassessment

**Not for:** New projects (use `/bootstrap`), single features (use `/spark`).

**Analogy:** Vehicle inspection. Not because the car is bad -- because any car requires periodic checks.

---

## Greenfield vs Brownfield: Inverted Order

```
BROWNFIELD (this skill)              GREENFIELD (normal flow)

1. Deep Audit (bottom-up)       1. Bootstrap (top-down)
   "what do we have?"              "what do we want?"
         |                                |
2. Architect Recovery            2. Board
   "document & design"              "business strategy"
         |                                |
3. Board Recovery                3. Architect
   "priorities & direction"          "system architecture"
         |                                |
4. Stabilization                 4. Spark -> Autopilot
   "fix foundations"                 "features one by one"
         |
5. Normal Flow
   "build features"
```

**Why inverted:** In brownfield, code is the ONLY source of truth. You must understand what's built before making business or architecture decisions about it.

---

## Phase Flow

```
/retrofit
    |
    +-- Phase 1: DEEP AUDIT
    |   |-- Run /audit deep (full 6-persona protocol)
    |   +-- EXIT GATE: ai/audit/deep-audit-report.md validated
    |
    +-- Phase 2: ARCHITECT (retrofit mode)
    |   |-- Run /architect with MODE: retrofit
    |   |-- HUMAN CHOOSES architecture alternative
    |   +-- EXIT GATE: system-blueprint/ + migration-path.md validated
    |
    +-- Phase 3: BOARD (retrofit mode)
    |   |-- Run /board with MODE: retrofit
    |   |-- HUMAN CHOOSES strategy
    |   +-- EXIT GATE: business-blueprint.md validated
    |
    +-- Phase 4: HUMAN REVIEW
    |   |-- Present all artifacts
    |   |-- Human: approve / adjust / reject
    |   +-- EXIT GATE: explicit human approval
    |
    +-- Phase 5: STABILIZATION
    |   |-- Execute migration-path.md wave by wave
    |   |-- Each item: /spark -> /autopilot
    |   +-- EXIT GATE: all waves done OR human says "enough"
    |
    +-- Phase 6: NORMAL FLOW
        +-- Blueprints in place -> Spark/Autopilot as greenfield
```

---

## Phase 1: Deep Audit

Delegate to `/audit deep`. This runs the full 6-persona protocol with Phase 0 inventory.

**DO NOT re-implement audit here.** The audit skill handles:
- Phase 0: Codebase inventory (deterministic)
- 6 parallel personas (cartographer, archaeologist, accountant, geologist, scout, coroner)
- Coverage verification gate (>= 80%)
- Synthesis into consolidated report
- Structural validation gate

### Orchestrator Actions

```yaml
1. Ensure ai/audit/ directory exists
2. Invoke: /audit deep
3. Wait for completion
4. Verify gate:
   node .claude/scripts/validate-audit-report.mjs ai/audit/deep-audit-report.md
```

### EXIT GATE

```bash
node .claude/scripts/validate-audit-report.mjs ai/audit/deep-audit-report.md
```

**PASS:** Proceed to Phase 2.
**FAIL:** Report issues to user. Re-run audit or fix manually.

### Present to Human

After audit completes, present summary:
- Total files / LOC / languages
- Top 5 red flags (P0)
- Top 5 tech debt items
- Architecture map overview

Ask: **"Ready to proceed to Architect recovery?"**

---

## Phase 2: Architect (Retrofit Mode)

Architect runs with MODE: retrofit, using deep-audit-report.md as primary input instead of business-blueprint.md.

### ENTRY GATE

```bash
node .claude/scripts/validate-audit-report.mjs ai/audit/deep-audit-report.md
```

Must pass before Architect starts.

### Orchestrator Actions

```yaml
1. Invoke: /architect
   - Architect SKILL.md detects retrofit mode from context
   - Input: ai/audit/deep-audit-report.md
   - Architect runs full 8-phase process internally
2. Architect presents 2-3 architecture alternatives
3. HUMAN CHOOSES (no auto-decide in retrofit)
4. Write chain produces system-blueprint/ + migration-path.md
```

### EXIT GATE

```bash
node .claude/scripts/validate-architect-data.mjs ai/architect/
```

**PASS:** Proceed to Phase 3.
**FAIL:** Re-run write chain or fix specific files.

### Key Retrofit Output: migration-path.md

The ONLY truly new artifact that doesn't exist in greenfield.

```markdown
# Migration Path: AS-IS -> TO-BE

## Wave 1: Foundations
### MP-001: {Title}
**Type:** TECH | ARCH
**Priority:** P0
**Current state:** ...
**Target state:** ...
**Files affected:** ...
**Depends on:** none

## Wave 2: Domain Boundaries (after Wave 1)
### MP-003: {Title}
**Depends on:** MP-001, MP-002

## Exit Criterion
All items done -> AS-IS converged with TO-BE -> normal flow.
```

**Rules:**
- Waves = dependency order. Wave N+1 depends on Wave N.
- Each item = one Spark spec. Granular enough for single autopilot cycle.
- Items use MP- prefix (Migration Path), not FTR/BUG/TECH.

---

## Phase 3: Board (Retrofit Mode)

Board runs with MODE: retrofit, using audit report + system blueprint + migration path as input.

### ENTRY GATE

```bash
node .claude/scripts/validate-architect-data.mjs ai/architect/
```

Must pass before Board starts.

### Orchestrator Actions

```yaml
1. Invoke: /board
   - Board SKILL.md detects retrofit mode from context
   - Input: deep-audit-report.md + system-blueprint/ + migration-path.md
   - Board runs full process internally
2. Board applies KEEP/CHANGE/DROP lens to existing features
3. Board may re-prioritize waves in migration-path.md
4. HUMAN CHOOSES strategy (no auto-decide in retrofit)
5. Write chain produces business-blueprint.md with retrofit extensions
```

### EXIT GATE

```bash
node .claude/scripts/validate-board-data.mjs ai/board/
```

**PASS:** Proceed to Phase 4.
**FAIL:** Re-run write chain or fix specific files.

---

## Phase 4: Human Review

All blueprints and migration path are ready. Present everything for human approval.

### Present to Human

```
RETROFIT REVIEW
===============

1. Deep Audit Summary
   - {key findings}

2. Architecture Decisions
   - {chosen alternative + rationale}
   - migration-path.md: {N} items in {M} waves

3. Board Strategy
   - KEEP: {N} decisions
   - CHANGE: {N} decisions
   - DROP: {N} decisions
   - Investment split: {stabilization}% / {features}%

Files for review:
- ai/audit/deep-audit-report.md
- ai/blueprint/system-blueprint/ (6 files)
- ai/architect/migration-path.md
- ai/blueprint/business-blueprint.md
```

### Human Decision

| Choice | Action |
|--------|--------|
| **Approve** | Proceed to Phase 5 (Stabilization) |
| **Adjust** | Human modifies specific files, then re-approve |
| **Reject architecture** | Back to Phase 2 with feedback |
| **Reject strategy** | Back to Phase 3 with feedback |
| **Abort** | Stop retrofit entirely |

**EXIT GATE:** Explicit human approval (verbal or written).

---

## Phase 5: Stabilization

Execute migration-path.md wave by wave. Each item becomes a Spark spec, then runs through Autopilot.

### Orchestrator Actions

```yaml
For each wave in migration-path.md:
  For each item (MP-XXX) in wave:
    1. /spark (Blueprint-Initiated, Mode B)
       - Spark receives MP-XXX as input
       - Creates feature/tech spec
    2. /autopilot
       - Full pipeline (plan -> code -> test -> review)
       - NO shortcuts, NO batching
    3. Verify: tests pass, no regressions

  Wave N+1 starts ONLY when Wave N is complete.
```

### Feedback Loop

If stabilization uncovers new problems:
- Create new items in migration-path.md
- Signal to Architect if architectural change needed
- Do NOT silently proceed past issues

### EXIT GATE

| Condition | Action |
|-----------|--------|
| All waves complete | Proceed to Phase 6 |
| Human says "enough" | Proceed to Phase 6 (partial retrofit) |
| New architectural issue | Back to Phase 2 (loop) |

---

## Phase 6: Normal Flow

Retrofit complete. Blueprints are in place. Project operates as greenfield.

```
ai/blueprint/system-blueprint/    -- architecture constraints
ai/blueprint/business-blueprint.md -- business constraints
ai/architect/migration-path.md    -- completed (historical record)

Next: /spark -> /autopilot (within blueprint constraints)
```

---

## Anti-Corner-Cutting (6 Levels)

Retrofit stakes are high. One wrong decision can invalidate entire migration.

| Level | Mechanism | Where |
|-------|-----------|-------|
| 1 | **WAIT FOR ALL** | Audit personas, Architect rounds, Board rounds |
| 2 | **File-based gates** | validate-*.mjs scripts between phases |
| 3 | **No auto-decide** | Human ALWAYS chooses in retrofit |
| 4 | **Inventory coverage** | Phase 0 guarantees 100% file discovery |
| 5 | **Quote-before-claim** | Every audit finding cites exact code |
| 6 | **Min operation counts** | Personas have enforced minimums |

### Critical Rule: No Auto-Decide

In greenfield, some skills allow AUTO mode for simple decisions.
In retrofit: **ALWAYS HUMAN.** Every architecture choice, every Board strategy, every migration path approval.

```
!!! RETROFIT RULE: No auto-decide.
Every architecture alternative -> HUMAN CHOOSES.
Every Board strategy -> HUMAN CHOOSES.
Every migration wave completion -> HUMAN APPROVES.
Violation of this rule invalidates retrofit output.
```

---

## Triggers Summary

| Trigger | Source |
|---------|--------|
| `/retrofit` | Explicit user command |
| "retrofit", "brownfield" | Natural language |
| Bugfix/feature > 1:1 | Reflect pipeline signal (future) |
| Major pivot | Board escalation |
| Framework upgrade (v1 -> v2) | User triggers |
| `/triz` systemic constraint | Diagnostic signal |

---

## Output Summary

```
ai/audit/
  codebase-inventory.json     (Phase 0)
  report-*.md                 (6 persona reports)
  deep-audit-report.md        (consolidated)

ai/architect/
  research-*.md               (persona research)
  migration-path.md           (NEW in retrofit)

ai/blueprint/
  system-blueprint/           (6 architecture files)
  business-blueprint.md       (with KEEP/CHANGE/DROP)
```

---

## After Retrofit

```
Blueprints in place -> Normal flow
  /spark for features (within blueprint constraints)
  /autopilot for execution (full pipeline)

If problems recur -> /triz diagnostic -> /retrofit again
```
