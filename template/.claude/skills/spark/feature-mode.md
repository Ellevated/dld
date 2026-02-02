# Feature Mode — Spark

Self-contained protocol for Feature Mode execution. Extract from SKILL.md.

---

## Purpose

Transform raw feature ideas into executable specs through:
1. Socratic Dialogue (5-7 deep questions)
2. Research (Exa + Context7)
3. Structured specification

**When to use:** New features, user flows, architecture decisions.

**Not for:** Bugs (use bug-mode.md), hotfixes <5 LOC.

---

## Socratic Dialogue

For NEW features — ask 5-7 deep questions. One at a time!

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

**Rules:**
- Ask ONE question at a time — wait for answer
- Don't move to design until key questions are answered
- If user says "just do it" — ask 2-3 minimum clarifying questions anyway
- Capture insights for spec

---

## Research Templates

Use these templates when invoking scout research.

### Feature / New Functionality

```yaml
Task tool:
  description: "Scout: {feature_name} best practices"
  subagent_type: "scout"
  max_turns: 8
  prompt: |
    MODE: quick
    QUERY: "Best practices for {feature_essence} in {tech_stack}. How to implement {pattern}? Common pitfalls, recommended approach, production-ready patterns."
    TYPE: pattern
    DATE: {current date}
```

### Prompt / Agent Change

```yaml
Task tool:
  description: "Scout: {prompt_aspect} patterns"
  subagent_type: "scout"
  max_turns: 8
  prompt: |
    MODE: quick
    QUERY: "Best practices for {prompt_aspect} in LLM agent systems. How to structure {specific_element}. Production patterns 2024-2026."
    TYPE: pattern
    DATE: {current date}
```

### Architecture Decision

```yaml
Task tool:
  description: "Scout: {decision} research"
  subagent_type: "scout"
  max_turns: 12
  prompt: |
    MODE: deep
    QUERY: "{option_A} vs {option_B} for {use_case} in {tech_stack}. Production experience, trade-offs, performance benchmarks."
    TYPE: architecture
    DATE: {current date}
```

**How to fill `{placeholders}`:**
- `{feature_essence}` — core of what we're building (e.g., "retry queue", "rate limiting", "webhook handler")
- `{tech_stack}` — our stack (e.g., "Python aiogram 3", "PostgreSQL", "FastAPI")
- `{pattern}` — specific pattern if known (e.g., "exponential backoff", "circuit breaker")
- `{prompt_aspect}` — what aspect of prompt (e.g., "output format enforcement", "agent reliability", "tool selection")

---

## Deep Research

**Trigger:** After dialogue (Phase 3), when approach is narrowed. MANDATORY for deep mode.

```yaml
Task tool:
  description: "Scout deep: {refined_topic}"
  subagent_type: "scout"
  max_turns: 15
  prompt: |
    MODE: deep
    QUERY: "{confirmed_approach} implementation in {tech_stack}. Step-by-step pattern, code structure, edge cases. {specific_context_from_dialogue}."
    TYPE: pattern
    DATE: {current date}
```

**How to fill from dialogue context:**
- Use the approach user confirmed in Phase 3
- Include specific terms from discussion
- Narrow to the exact pattern/library chosen

---

## Scout Results Integration

- **Phase 3 questions** MUST reference Scout findings: "Found [X] in [source]. Fits us?"
- **Phase 5 approaches** MUST cite Scout sources: "Approach 1: [Name] (based on [Scout source])"
- **Phase 8 plan** MUST include Scout URLs in Research Sources section
- If Scout found nothing useful — note it and proceed with own analysis

---

## Feature Spec Template

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

## Definition of Done

### Functional
- [ ] Feature works as specified
- [ ] All tasks from Implementation Plan completed

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

---

## LLM-Friendly Architecture Checks

Quick checklist before creating spec:
- [ ] Files < 400 LOC (600 for tests)
- [ ] New code in `src/domains/` or `src/infra/`, NOT legacy folders
- [ ] Max 5 exports per `__init__.py`
- [ ] Imports follow: shared → infra → domains → api

---

## Completion Checklist

Before marking Feature Mode complete:

1. [ ] **ID determined** — not guessed, scanned backlog
2. [ ] **Uniqueness verified** — grep backlog didn't find this ID
3. [ ] **Spec file created** — ai/features/FTR-XXX-YYYY-MM-DD-name.md
4. [ ] **Entry added to backlog** — in `## Queue` section
5. [ ] **Status = queued** — ready for autopilot
6. [ ] **Function overlap check** — grep other queued specs
7. [ ] **Auto-commit done** — `git add ai/ && git commit` (no push!)

---

## Output

```yaml
status: complete | needs_discussion | blocked
spec_path: ai/features/FTR-XXX.md  # file MUST exist
handoff: autopilot | council | blocked
```
