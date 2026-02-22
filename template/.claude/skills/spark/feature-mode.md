# Feature Mode — Spark (8-Phase Protocol)

Self-contained protocol for Feature Mode execution. Extract from SKILL.md.

---

## Purpose

Transform raw feature ideas into executable specs through 8 phases:

```
Collect → Research → Synthesize → Decide → Write → Validate → Reflect → Completion
```

**When to use:** New features, user flows, architecture decisions.

**Not for:** Bugs (use bug-mode.md), hotfixes <5 LOC.

---

## Session Directory

Compute before Phase 2:

```
SESSION_DIR = ai/.spark/{YYYYMMDD}-{spec_id}/
```

---

## State Tracking (Enforcement as Code)

After EACH phase, update the session state file:

```
Write tool → {SESSION_DIR}/state.json
```

**Format:** See `.claude/scripts/spark-state.mjs` for utilities.

**After each phase completes:**
1. Update state.json with phase status = "done" and timestamp
2. For research phase: include `files` array with research file names
3. For decide phase: include `approach` number selected

**This is NOT optional.** Hooks read state.json to validate spec completeness.

---

## FORBIDDEN ACTIONS (ADR-007/008/009/010)

```
⛔ NEVER store scout responses in orchestrator variables
⛔ NEVER pass full scout output in another scout's prompt

✅ ALL scout Task calls use run_in_background: true
✅ Scouts WRITE output to SESSION_DIR files
✅ File gates (Glob) verify scout completion
✅ Orchestrator reads scout files for synthesis (~20K acceptable)
```

---

## Phase 1: COLLECT (Socratic Dialogue)

Two modes depending on feature origin:

### Mode A: Human-Initiated

User started the feature — ask 5-7 deep questions. ONE at a time!

**Question Bank (pick 5-7 relevant):**

1. **Problem:** "What problem are we solving?" (not feature, but pain)
2. **User:** "Who is the user of this function? Seller? Buyer? Admin?"
3. **Current state:** "How is it solved now without this feature?"
4. **MVP:** "What's the minimum scope that delivers 80% of value?"
5. **Risks:** "What can go wrong? Edge cases?"
6. **Verification:** "How will we verify it works?"
7. **Existing:** "Is there an existing solution we can adapt?"
8. **Priority:** "How urgent is this? P0/P1/P2?"
9. **Dependencies:** "What does it depend on? What's blocking?"
10. **Past Behavior:** "Have users tried to solve this themselves? How?"
11. **Kill Question:** "If we do nothing — what happens in 3 months?"

**Rules:**
- Ask ONE question at a time — wait for answer
- Don't move to design until key questions are answered
- If user says "just do it" — ask 2-3 minimum clarifying questions anyway
- Capture insights for scout context

### Mode B: Blueprint-Initiated

Architect/Board assigned this task — read from blueprint, do NOT ask user.

1. Read task description from `ai/blueprint/system-blueprint/`
2. If clarifications needed → dispatch `architect-facilitator` as subagent
   - Architect answers with full system-blueprint context
   - Spark gets clarifications WITHOUT bothering the user
3. Human = 0% involvement (per design doc)

**Output for both modes:** Problem statement captured, ready for scouts.

<HARD-GATE>
DO NOT proceed to Phase 2 until:
- [ ] state.json initialized with initState()
- [ ] state.json updated: collect = done
- [ ] Problem statement clearly captured
Skipping this gate = VIOLATION. No rationalization accepted.
Common rationalization to REJECT: "the feature is obvious, no need for questions"
</HARD-GATE>

---

## Phase 2: RESEARCH (4 Parallel Scouts)

Dispatch 4 isolated scouts in parallel. Each scout gets a frozen snapshot — they do NOT see each other's work.

```yaml
# Scout 1: External (best practices, libraries)
Task tool:
  description: "Spark scout: external research"
  subagent_type: spark-external       # → agents/spark/external.md
  run_in_background: true
  prompt: |
    FEATURE: {feature description}
    BLUEPRINT: [contents of ai/blueprint/system-blueprint/ if exists]
    SOCRATIC INSIGHTS: {key insights from Phase 1}
    Output: research-external.md

# Scout 2: Codebase (existing code, dependencies)
Task tool:
  description: "Spark scout: codebase analysis"
  subagent_type: spark-codebase       # → agents/spark/codebase.md
  run_in_background: true
  prompt: |
    FEATURE: {feature description}
    BLUEPRINT: [contents of ai/blueprint/system-blueprint/ if exists]
    SOCRATIC INSIGHTS: {key insights from Phase 1}
    Output: research-codebase.md

# Scout 3: Patterns (alternatives, trade-offs)
Task tool:
  description: "Spark scout: alternative patterns"
  subagent_type: spark-patterns       # → agents/spark/patterns.md
  run_in_background: true
  prompt: |
    FEATURE: {feature description}
    BLUEPRINT: [contents of ai/blueprint/system-blueprint/ if exists]
    SOCRATIC INSIGHTS: {key insights from Phase 1}
    Output: research-patterns.md

# Scout 4: Devil's Advocate
Task tool:
  description: "Spark scout: devil's advocate"
  subagent_type: spark-devil          # → agents/spark/devil.md
  run_in_background: true
  prompt: |
    FEATURE: {feature description}
    BLUEPRINT: [contents of ai/blueprint/system-blueprint/ if exists]
    SOCRATIC INSIGHTS: {key insights from Phase 1}
    Output: research-devil.md
```

**All 4 scouts run in PARALLEL, ALL background, and do NOT see each other's work.**

If `ai/blueprint/system-blueprint/` exists, ALL scouts receive it as CONSTRAINT.

**⏳ FILE GATE:** Wait for ALL 4 completion notifications, then verify:
```
Glob("{SESSION_DIR}/research-*.md") → must find 4 files
If < 4: launch extractor subagent for missing files (caller-writes fallback, ADR-007)
```

<HARD-GATE>
DO NOT proceed to Phase 3 until:
- [ ] ALL 4 scout completion notifications received
- [ ] Glob confirms 4 research files exist in SESSION_DIR
- [ ] state.json updated: research = done, files = [list of 4 files]
Skipping this gate = VIOLATION. No rationalization accepted.
Common rationalization to REJECT: "this is simple enough to skip research"
</HARD-GATE>

---

## Phase 3: SYNTHESIZE

Read all inputs:
- Problem statement from Phase 1
- 4 research files from Phase 2
- `ai/blueprint/system-blueprint/` (as constraint)

### Build 2-3 Approaches WITHIN Blueprint

For each approach:

| Field | Source |
|-------|--------|
| Summary | Pattern scout + External scout recommendations |
| Affected files | Codebase scout Impact Tree |
| Risks | Devil scout edge cases |
| Test strategy | Devil scout + External scout |
| Blueprint compliance | ✓ or ⚠️ with explanation |

### Rules

- **NO INVENTION** — if scouts didn't find it, it's a gap (note for Phase 7 reflect)
- **Cite sources** — every claim must reference a scout file
- **Conflicts** → apply Evaporating Cloud (what's the underlying assumption?)
- **All approaches must respect blueprint** — if none fit, escalate to ARCHITECT in Phase 4

**Output:** 2-3 approaches ready for Phase 4 decision.

<HARD-GATE>
DO NOT proceed to Phase 4 until:
- [ ] 2-3 approaches documented with pros/cons
- [ ] Every claim cites a scout research file
- [ ] state.json updated: synthesize = done
Skipping this gate = VIOLATION. No rationalization accepted.
Common rationalization to REJECT: "there's only one obvious approach"
</HARD-GATE>

---

## Phase 4: DECIDE

Route based on feature scope, clarity, and risk:

### AUTO (you decide)
- Feature is within blueprint constraints
- Scope is clear from dialogue
- No controversial trade-offs
- Devil scout's verdict is "Proceed"
→ Select best approach, move to Phase 5

### HUMAN (ask user)
- Multiple approaches with no clear winner
- Scope unclear after dialogue
- Devil scout suggests simpler alternative
→ Present 2-3 approaches, user chooses

### COUNCIL (escalate)
- Controversial (Devil scout says "Proceed with caution")
- Cross-domain impact (affects 3+ domains)
- Major architectural decision
→ `/council` (5 experts + cross-critique)

### ARCHITECT (escalate)
- Blueprint gap (domain missing, rule missing)
- Blueprint contradiction (research conflicts with blueprint)
→ Architect updates blueprint → retry from Phase 3

<HARD-GATE>
DO NOT proceed to Phase 5 until:
- [ ] Decision route selected (AUTO/HUMAN/COUNCIL/ARCHITECT)
- [ ] If HUMAN: user has explicitly chosen an approach
- [ ] state.json updated: decide = done, approach = N
Skipping this gate = VIOLATION. No rationalization accepted.
Common rationalization to REJECT: "I already know what the user wants"
</HARD-GATE>

---

## Phase 5: WRITE (Feature Spec Template)

Write spec using selected approach from Phase 4:

```markdown
# Feature: [FTR-XXX] Title
**Status:** queued | **Priority:** P0/P1/P2 | **Date:** YYYY-MM-DD

## Why
[Problem statement from Socratic Dialogue]

## Context
[Background, related features, current state]

---

## Scope
**In scope:** [What we're doing]
**Out of scope:** [What we're NOT doing]

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
- [ ] `grep -r "from.*{module}" . --include="*.py"` → ___ results
- [ ] All callers identified: [list files]

### Step 2: DOWN — what depends on?
- [ ] Imports in changed file checked
- [ ] External dependencies: [list]

### Step 3: BY TERM — grep entire project
- [ ] `grep -rn "{old_term}" . --include="*.py" --include="*.sql"` → ___ results

| File | Line | Status | Action |
|------|------|--------|--------|
| _fill_ | _fill_ | _fill_ | _fill_ |

### Step 4: CHECKLIST — mandatory folders
- [ ] `tests/**` checked
- [ ] `db/migrations/**` checked
- [ ] `ai/glossary/**` checked (if money-related)

### Verification
- [ ] All found files added to Allowed Files
- [ ] grep by old term = 0 (or cleanup task added)

---

## Allowed Files
**ONLY these files may be modified during implementation:**
1. `path/to/file1.py` — reason
2. `path/to/file2.py` — reason
3. `path/to/file3.py` — reason

**New files allowed:**
- `path/to/new_file.py` — reason

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

<!-- Smart defaults: adjust based on your stack -->
nodejs: false
docker: false
database: false

---

## Blueprint Reference

<!-- If ai/blueprint/system-blueprint/ exists, fill this section -->
**Domain:** {which domain from domain-map.md}
**Cross-cutting:** {Money? Auth? Errors? — from cross-cutting.md}
**Data model:** {which entities from data-architecture.md are affected}

---

## Approaches

### Approach 1: [Name] (based on [source])
**Source:** [URL from Scout research]
**Summary:** [Brief description]
**Pros:** [Benefits]
**Cons:** [Drawbacks]

### Approach 2: [Name] (based on [source])
**Source:** [URL]
**Summary:** [Brief description]
**Pros:** [Benefits]
**Cons:** [Drawbacks]

### Selected: [N]
**Rationale:** [Why this approach was chosen]

---

## Design

### User Flow
[Step-by-step user journey]

### Architecture
[Component diagram or description]

### Database Changes
[If applicable: schema changes, migrations needed]

---

## UI Event Completeness (REQUIRED for UI features)

If creating UI elements with callbacks/events — fill this table:

| Producer (keyboard/button) | callback_data | Consumer (handler) | Handler File in Allowed Files? |
|---------------------------|---------------|-------------------|-------------------------------|
| `start_keyboard()` | `guard:start` | `cb_guard_start()` | `onboarding.py` ✓ |

**RULE:** Every `callback_data` MUST have a handler in Allowed Files!

- No handler = No commit (Autopilot will block)
- If handler file missing from Allowed Files — add it or explain why not needed
- This prevents orphan callbacks (BUG-156 post-mortem)

---

## Implementation Plan

### Research Sources
- [Pattern Name](url) — description of what pattern solves
- [Library Docs](url) — API reference for implementation
- [Example](url) — code example that inspired approach

### Task 1: [Name]
**Type:** code | test | migrate
**Files:**
  - create: `path/to/new_file.py`
  - modify: `path/to/existing.py`
**Pattern:** [URL from Research Sources]
**Acceptance:** [How to verify task is complete]

### Task 2: [Name]
**Type:** code | test | migrate
**Files:**
  - modify: `path/to/file.py`
**Pattern:** [URL]
**Acceptance:** [Verification criteria]

### Execution Order
1 → 2 → 3

---

## Flow Coverage Matrix (REQUIRED)

Map every User Flow step to Implementation Task:

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | User clicks menu button | - | existing |
| 2 | Guard shows message + button | Task 1,2,3 | ✓ |
| 3 | User clicks [Start] button | Task 4 | ✓ |
| 4 | Onboarding starts | - | existing |

**GAPS = BLOCKER:**
- Every step must be covered by a task OR marked "existing"
- If gap found → add task or explain why not needed
- Uncovered steps = incomplete spec (Council may reject)

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | {scenario} | {input} | {expected behavior} | deterministic | {devil/user/blueprint} | P0 |
| EC-2 | {edge case} | {input} | {expected} | deterministic | {devil scout} | P0 |
| EC-3 | {boundary} | {input} | {expected} | deterministic | {user requirement} | P1 |

### Integration Assertions (if applicable)

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-N | {preconditions} | {action} | {result} | integration | {source} | P1 |

### LLM-Judge Assertions (if LLM-involved feature)

| ID | Input | Rubric | Threshold | Source | Priority |
|----|-------|--------|-----------|--------|----------|
| EC-N | {prompt/input} | {good output criteria} | 0.8 | {source} | P1 |

### Coverage Summary
- Deterministic: {N} | Integration: {N} | LLM-Judge: {N} | Total: {N} (min 3)

### TDD Order
1. Write test from EC-1 -> FAIL -> Implement -> PASS
2. Continue by priority (P0 first)

---

## Definition of Done

### Functional
- [ ] Feature works as specified
- [ ] All tasks from Implementation Plan completed

### Tests
- [ ] All eval criteria from ## Eval Criteria section pass
- [ ] Coverage not decreased

### E2E User Journey (REQUIRED for UI features)
- [ ] Every UI element is interactive (buttons respond to clicks)
- [ ] User can complete full journey from start to finish
- [ ] No dead-ends or hanging states
- [ ] Manual E2E test performed

### Technical
- [ ] Tests pass (./test fast)
- [ ] No regressions

---

## Autopilot Log
[Auto-populated by autopilot during execution]
```

<HARD-GATE>
DO NOT proceed to Phase 6 until:
- [ ] Full spec written to ai/features/{TASK_ID}-*.md
- [ ] All template sections filled (no {placeholders} remain)
- [ ] state.json updated: write = done
Skipping this gate = VIOLATION. No rationalization accepted.
Common rationalization to REJECT: "I'll fill the remaining sections later"
</HARD-GATE>

---

## Phase 6: VALIDATE

Before marking spec `queued`, run 5 structural validation gates.

### Gate 1: Spec Completeness
```
□ Enough information for implementation?
□ No contradictions with system blueprint?
□ Allowed Files cover all tasks?
□ Edge cases covered?
□ DoD is measurable?
```

### Gate 2: Eval Criteria Gate
```
□ Eval Criteria section filled? (or Tests section for legacy specs)
□ Minimum 3 eval criteria (EC-N rows)?
□ Has edge case from devil's advocate?
□ Coverage Summary present?
□ TDD Order defined?
□ DoD includes tests/eval?
```

### Gate 3: Blueprint Compliance
```
□ Blueprint Reference filled?
□ Cross-cutting rules applied (Money, Auth, Errors)?
□ Data model matches data-architecture.md?
□ Feature respects domain boundaries from domain-map.md?
```

### Gate 4: UI Event Completeness (if UI feature)
```
□ Every callback_data has handler in Allowed Files?
□ No orphan callbacks?
```

### Gate 5: Flow Coverage
```
□ Every User Flow step covered by Implementation Task or marked "existing"?
□ No gaps in flow?
```

**GATE RESULT:** pass / reject with reasons

**If any gate fails →** spec stays `draft`, return to Phase 3 (re-synthesize with feedback).

<HARD-GATE>
DO NOT proceed to Phase 7 until:
- [ ] All 5 validation gates pass
- [ ] state.json updated: validate = done
Skipping this gate = VIOLATION. No rationalization accepted.
Common rationalization to REJECT: "gates are just a formality, spec looks good"
</HARD-GATE>

---

## Phase 7: REFLECT

After spec passes all validation gates, before completion:

### LOCAL Signal
Improvement for next Spark iteration:
- What scouts missed, what worked well
- Which question bank items were most useful

### UPSTREAM Signal
If issues were found during research/synthesis that affect upstream levels:
- Blueprint gap → write upstream signal with target=architect
- Missing cross-cutting rule → write upstream signal with target=architect
- Business question unanswered → write upstream signal with target=board

### PROCESS Signal
Meta-observation about the process itself:
- Did auto-decide work correctly for this feature?
- Was council escalation needed but not triggered (or vice versa)?
- Scout coverage: did any scout find nothing useful?

```yaml
# Only if issues found — don't write empty signals!
Append to ai/reflect/upstream-signals.md:

## SIGNAL-{timestamp}

| Field | Value |
|-------|-------|
| Source | spark |
| Spec ID | {TASK_ID} |
| Target | architect / board |
| Type | gap / contradiction / missing_rule |
| Severity | info / warning / critical |

### Message
{What's missing or wrong in the blueprint}

### Evidence
{Specific finding from scout research}

### Suggested Action
{What Architect/Board should do}
```

<HARD-GATE>
DO NOT proceed to Phase 8 until:
- [ ] Reflect signals written (if any issues found)
- [ ] state.json updated: reflect = done
Skipping this gate = VIOLATION. No rationalization accepted.
Common rationalization to REJECT: "nothing to reflect on"
</HARD-GATE>

---

## Phase 8: COMPLETION

After spec is created and validated → read `completion.md` for:
- ID determination protocol (sequential across ALL types)
- Backlog entry format
- Auto-commit rules
- Handoff to autopilot

After completion: state.json updated: completion = done

---

## Rationalization Pre-emption Table

When you feel tempted to skip a phase, consult this table:

| LLM thinks | Correct action |
|---|---|
| "This is too simple for research" | Research can be short, but must happen. Update state.json. |
| "I already know how to do this" | Knowledge ≠ research. Scout may find a better pattern. |
| "Tests can be written later" | TDD: test BEFORE code. No test = no commit. |
| "This file isn't in Allowed Files, but it's needed" | Add it to the spec. Hook will block otherwise. |
| "There's only one obvious approach" | Document it anyway. Devil's advocate may disagree. |
| "The user said 'just do it'" | Ask 2-3 minimum clarifying questions anyway. |
| "Validation gates are a formality" | Gates catch real issues. Run them honestly. |
| "Nothing to reflect on" | There's always a process signal. Did auto-decide work? |
