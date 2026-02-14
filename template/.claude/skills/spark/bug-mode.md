# Bug Mode for Spark

**Purpose:** Systematic bug investigation with two modes — Quick (5 Whys) and Bug Hunt (multi-agent deep analysis).

---

## Mode Selection

| Signal | Mode | Description |
|--------|------|-------------|
| Simple bug, clear location, <5 files | **Quick Bug Mode** | 5 Whys → single spec |
| Complex bug, unclear cause, >5 files, "bug hunt", "deep analysis" | **Bug Hunt Mode** | Multi-agent pipeline → umbrella spec + sub-specs |
| User explicitly says "bug hunt", "баг-хант", "охота на баги" | **Bug Hunt Mode** | Forced |

**Default:** Quick Bug Mode. Escalate to Bug Hunt if 5 Whys reveals complexity.

---

# Quick Bug Mode

**Flow:** Reproduce → Isolate → Root Cause (5 Whys) → Create Spec → Handoff to Autopilot

## Phase 1: REPRODUCE

```
"Show exact reproduction steps:"
1. What command/action?
2. What input?
3. What output do we get?
4. What output do we expect?
```

**Get EXACT error output!** Not "test fails" but actual traceback.

## Phase 2: ISOLATE

```
Find problem boundaries:
- When did it start? (last working commit?)
- Where exactly does it fail? (file:line)
- Does it reproduce every time?
- Are there related files?
```

Read files, grep, find the exact location.

## Phase 3: ROOT CAUSE — 5 Whys

```
Why 1: Why does the test fail?
  → "Because function returns None"

Why 2: Why does function return None?
  → "Because condition X is not met"

Why 3: Why is condition X not met?
  → "Because variable Y is not initialized"

Why 4: Why is variable Y not initialized?
  → "Because migration didn't add default value"

Why 5: Why didn't migration add default?
  → "Because we forgot when adding the column"

ROOT CAUSE: Migration XXX doesn't have DEFAULT for new column.
```

**STOP when you find the REAL cause, not symptom!**

## Phase 4: CREATE BUG SPEC

Only after root cause is found → create BUG-XXX spec:

```markdown
# Bug: [BUG-XXX] Title

**Status:** queued | **Priority:** P0/P1/P2 | **Date:** YYYY-MM-DD

## Symptom
[What user sees / test failure]

## Root Cause (5 Whys Result)
[The REAL cause, not symptom]

## Reproduction Steps
1. [exact step]
2. [exact step]
3. Expected: X, Got: Y

## Fix Approach
[How to fix the root cause]

## Impact Tree Analysis

### Step 1: UP — who uses?
- [ ] All callers identified: [list files]

### Step 2: DOWN — what depends on?
- [ ] Imports in changed file checked
- [ ] External dependencies: [list]

### Step 3: BY TERM — grep entire project
| File | Line | Status | Action |
|------|------|--------|--------|

### Verification
- [ ] All found files added to Allowed Files

## Research Sources
- [Pattern](url) — description from Scout

## Allowed Files
1. `path/to/file.py` — fix location
2. `path/to/test.py` — add regression test

## Definition of Done
- [ ] Root cause fixed
- [ ] Original test passes
- [ ] Regression test added
- [ ] No new failures
```

→ Then go to `completion.md` for ID protocol and handoff.

---

# Bug Hunt Mode

**Multi-agent deep analysis pipeline.** Use when bug is complex, systemic, or affects many files.

**Cost estimate:** ~$40-70 per full run (6 Sonnet + 2 Opus + 1 Opus validator + N Opus architects)

## Overview

```
Phase 1a: 6 Persona Agents (Sonnet, parallel) → raw findings
Phase 1b: 2 Framework Agents (Opus, parallel) → systemic analysis
Phase 2:  1 Validator Agent (Opus) → filter relevant vs out-of-scope
Phase 3:  N Solution Architects (Opus) → sub-specs per finding
Handoff:  Sequential autopilot for each sub-spec
```

## Phase 1a: Persona Discovery (6 × Sonnet, parallel)

Launch 6 persona agents simultaneously. Each gets a clean context with only the target scope.

```yaml
# Launch ALL 6 in a SINGLE message (parallel Task calls)
Task:
  subagent_type: bughunt-code-reviewer
  model: sonnet
  description: "Bug Hunt: code review"
  prompt: |
    Analyze the following codebase area for bugs from your perspective.
    SCOPE: {user's bug description + affected area}
    TARGET: {target_path}

    Read the code systematically. Return findings in your YAML format.

Task:
  subagent_type: bughunt-security-auditor
  model: sonnet
  description: "Bug Hunt: security audit"
  prompt: |
    [same structure, scope, target]

Task:
  subagent_type: bughunt-ux-analyst
  model: sonnet
  description: "Bug Hunt: UX analysis"
  prompt: |
    [same structure, scope, target]

Task:
  subagent_type: bughunt-junior-developer
  model: sonnet
  description: "Bug Hunt: junior review"
  prompt: |
    [same structure, scope, target]

Task:
  subagent_type: bughunt-software-architect
  model: sonnet
  description: "Bug Hunt: architecture analysis"
  prompt: |
    [same structure, scope, target]

Task:
  subagent_type: bughunt-qa-engineer
  model: sonnet
  description: "Bug Hunt: QA analysis"
  prompt: |
    [same structure, scope, target]
```

**Collect results.** Create a Phase 1a summary with all findings.

## Phase 1b: Framework Analysis (2 × Opus, parallel)

After Phase 1a completes, launch framework agents with the findings summary.

```yaml
Task:
  subagent_type: bughunt-toc-analyst
  model: opus
  description: "Bug Hunt: TOC analysis"
  prompt: |
    ## Phase 1a Findings Summary
    {paste summary of all Phase 1a findings with IDs and titles}

    TARGET: {target_path}

    Build Current Reality Tree from these findings.
    Identify core constraints and causal chains.

Task:
  subagent_type: bughunt-triz-analyst
  model: opus
  description: "Bug Hunt: TRIZ analysis"
  prompt: |
    ## Phase 1a Findings Summary
    {paste summary of all Phase 1a findings with IDs and titles}

    TARGET: {target_path}

    Identify contradictions and ideality gaps.
    Apply inventive principles to find solutions.
```

**Collect results.** Merge into Phase 1a findings.

## Spark Assembles Draft Spec

Spark (Opus) combines all findings into a single umbrella document:

```
ai/features/BUG-XXX/BUG-XXX.md
```

This is a draft with ALL raw findings (typically 60-100).

## Phase 2: Validation & Filtering (1 × Opus)

```yaml
Task:
  subagent_type: bughunt-validator
  model: opus
  description: "Bug Hunt: validate findings"
  prompt: |
    ## Original User Question
    {user's original bug description}

    ## Draft Spec
    {contents of BUG-XXX.md}

    Filter: keep RELEVANT findings, move OUT OF SCOPE to ideas.
    Deduplicate. Verify file references.
```

**Update BUG-XXX.md** with only relevant findings.
**Append out-of-scope ideas** to `ai/ideas.md`.

## Phase 3: Solution Architecture (N × Opus, batched)

For each relevant finding, launch a solution architect agent.

**Batching:** Launch 5-10 at a time to avoid overwhelming the system.

```yaml
# For each relevant finding F-001, F-002, ... F-N:
Task:
  subagent_type: bughunt-solution-architect
  model: opus
  description: "Bug Hunt: spec F-001"
  prompt: |
    ## Finding
    {finding F-001 details}

    ## Context
    Umbrella: BUG-XXX
    Sub-spec number: 01
    Target: {target_path}

    Create sub-spec at: ai/features/BUG-XXX/BUG-XXX-01.md
    Include Impact Tree, research, fix approach.
    Status: queued
```

**Result:** Directory structure:
```
ai/features/BUG-XXX/
├── BUG-XXX.md          ← umbrella (table of contents + summary)
├── BUG-XXX-01.md       ← queued sub-spec
├── BUG-XXX-02.md       ← queued sub-spec
└── ...
```

## Umbrella Spec Template

```markdown
# Bug Hunt: [BUG-XXX] {Title}

**Status:** queued | **Priority:** P0 | **Date:** YYYY-MM-DD
**Mode:** Bug Hunt (multi-agent)
**Cost:** ~${estimated_cost}

## Original Problem
{User's description}

## Executive Summary
- Total findings analyzed: {N_total}
- Relevant (in scope): {N_relevant}
- Out of scope (→ ideas.md): {N_out}
- Duplicates merged: {N_dupes}
- Sub-specs created: {N_specs}

## Sub-Specs

| # | ID | Title | Priority | Status |
|---|-----|-------|----------|--------|
| 1 | BUG-XXX-01 | {title} | P0 | queued |
| 2 | BUG-XXX-02 | {title} | P1 | queued |
| ... | ... | ... | ... | ... |

## Framework Analysis

### TOC (Theory of Constraints)
{Core constraint identified}
{Causal chain summary}

### TRIZ
{Key contradictions}
{Suggested inventive principles}

## Consensus Matrix

| Finding | CR | SEC | UX | JR | ARCH | QA | TOC | TRIZ | Consensus |
|---------|----|----|----|----|------|----|-----|------|-----------|
| F-001   | x  |    |    |    |  x   |    |     |      | 2/8       |
| ...     |    |    |    |    |      |    |     |      |           |

## Execution Plan
Sub-specs will be executed sequentially by Autopilot:
BUG-XXX-01 → BUG-XXX-02 → ... → BUG-XXX-NN
```

## Handoff

After all sub-specs are created:
1. Update umbrella BUG-XXX.md with sub-spec table
2. Add ONE entry to backlog for the umbrella
3. Auto-commit: `git add ai/ && git commit`
4. Ask user: "Bug Hunt complete. {N} sub-specs created. Run autopilot?"
5. If user confirms → autopilot executes sub-specs sequentially

→ Go to `completion.md` for ID protocol and backlog entry.

---

## Bug Research Template

When investigating bug patterns (used in both modes):

```yaml
Task tool:
  description: "Scout: {error_type} fix patterns"
  subagent_type: "scout"
  max_turns: 8
  prompt: |
    MODE: quick
    QUERY: "{error_type}: {error_message}. Common causes and fixes in {tech_stack}."
    TYPE: error
    DATE: {current date}
```

---

## Exact Paths Required (BUG-328)

**RULE:** Allowed Files must contain EXACT file paths, not placeholders.

```markdown
# WRONG — CI validation fails
## Allowed Files
1. `db/migrations/YYYYMMDDHHMMSS_create_function.sql`

# CORRECT — exact timestamp
## Allowed Files
1. `db/migrations/20260116153045_create_function.sql`
```

---

## Bug Mode Rules

**Investigation Rules:**
- NEVER guess the cause — investigate first!
- NEVER fix symptom — fix root cause!
- NEVER skip reproduction — must have exact steps!

**Execution Rules:**
- ALWAYS create spec — Autopilot does the actual fix
- ALWAYS add regression test — in spec's DoD
- ALWAYS use Impact Tree — find all affected files

**Handoff Rules:**
- Bugs go through: spark → plan → autopilot
- No direct fixes during spark (READ-ONLY mode)
- Auto-commit spec before handoff

---

## Pre-Completion Checklist

**Note:** See `SKILL.md` for READ-ONLY rules that apply to all Spark modes.

### Quick Bug Mode Checklist
1. [ ] Root cause identified (5 Whys complete)
2. [ ] Reproduction steps exact
3. [ ] Scout research done
4. [ ] Impact Tree Analysis complete
5. [ ] Allowed Files exact (no placeholders)
6. [ ] Regression test in DoD

### Bug Hunt Mode Checklist
1. [ ] All 6 persona agents completed
2. [ ] TOC + TRIZ framework agents completed
3. [ ] Validator filtered findings
4. [ ] Sub-specs created for all relevant findings
5. [ ] Umbrella spec has sub-spec table
6. [ ] Out-of-scope ideas saved to ai/ideas.md

### Both Modes (from completion.md)
7. [ ] ID determined by protocol
8. [ ] Spec file created
9. [ ] Backlog entry added
10. [ ] Status = queued
11. [ ] Auto-commit done

---

## Output Format

```yaml
status: completed | blocked
mode: quick | bug-hunt
bug_id: BUG-XXX
root_cause: "[1-line summary]"  # Quick mode
findings_count: N                # Bug Hunt mode
subspecs_count: N                # Bug Hunt mode
spec_path: "ai/features/BUG-XXX.md"  # or "ai/features/BUG-XXX/BUG-XXX.md"
research_sources_used:
  - url: "..."
    used_for: "pattern X"
handoff: autopilot | needs_discussion
```

**Next step:** User confirms → auto-handoff to `/autopilot`
