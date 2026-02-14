# Bug Mode for Spark

**Purpose:** Systematic bug investigation with two modes — Quick (5 Whys) and Bug Hunt (multi-agent deep analysis).

---

## Mode Selection

| Signal | Mode | Description |
|--------|------|-------------|
| Simple bug, clear location, <5 files | **Quick Bug Mode** | 5 Whys → single spec |
| Complex bug, unclear cause, >5 files, "bug hunt", "deep analysis" | **Bug Hunt Mode** | Multi-agent pipeline → report + grouped standalone specs |
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

**Cost estimate:** ~$50-100 per full run (6×N Sonnet personas + 2 Opus frameworks + 1 Opus validator + M Opus architects). N = number of zones (typically 2-4).

## Overview

```
Step 0: Scope Decomposition → split target into 2-4 focused zones
Step 1: Launch 6 Persona Agents PER ZONE (6×N Sonnet, parallel)
Step 2: Collect all persona results → create findings summary
Step 3: Launch TOC + TRIZ Agents (Opus, parallel) with findings summary
Step 4: Collect ALL results → assemble umbrella spec (MUST include Framework Analysis)
Step 5: Launch Validator Agent (Opus) → filter, deduplicate, GROUP into 3-8 clusters
Step 6: Update report with validator results → update Executive Summary
Step 7: Launch M Solution Architects (Opus) → standalone spec per GROUP
```

---

## ALGORITHM — Execute steps in exact order

Each step's output feeds into the next step. You cannot proceed to step N+1
without completing step N, because step N+1 requires step N's output as input.

---

### STEP 0: Scope Decomposition

Wide scope = shallow findings. Narrow scope = deep findings. To get BOTH breadth AND depth
in one run, split the target into focused zones BEFORE launching personas.

**How to decompose:**
1. List the target directory structure (tree, 2 levels deep)
2. Group by functional area (e.g., hooks, skills, agents, scripts, docs, config)
3. Each zone should have 10-30 files — enough for deep analysis, not too many to skim
4. Zones can overlap slightly at boundaries (validator deduplicates later)

**Example decomposition for `template/.claude/`:**
```
Zone A: hooks/ + settings.json       (runtime safety — 10 files)
Zone B: skills/ + agents/            (prompt quality — 25 files)
Zone C: rules/ + CLAUDE.md           (config consistency — 8 files)
```

**Example for full project audit:**
```
Zone A: template/.claude/hooks/ + template/.claude/settings.json
Zone B: template/.claude/skills/ + template/.claude/agents/
Zone C: scripts/ + packages/
Zone D: docs/ + README.md + FAQ.md + COMPARISON.md
```

**Output of Step 0:** List of 2-4 zones, each with a path list and focus description.

If the target is already narrow (<30 files), skip decomposition — use 1 zone.

### STEP 1: Launch 6 Persona Agents PER ZONE

For EACH zone from Step 0, launch ALL 6 personas. All zones run in parallel.

```yaml
# Zone A: hooks + config (6 agents)
Task:
  subagent_type: bughunt-code-reviewer
  model: sonnet
  description: "Bug Hunt: code review [Zone A: hooks]"
  prompt: |
    Analyze the following codebase area for bugs from your perspective.
    SCOPE: {user's bug description}
    ZONE: hooks and runtime safety
    TARGET FILES: {zone A file list}

    Read the code systematically. Return findings in your YAML format.

Task:
  subagent_type: bughunt-security-auditor
  ...same zone A...

Task:
  subagent_type: bughunt-ux-analyst
  ...same zone A...

Task:
  subagent_type: bughunt-junior-developer
  ...same zone A...

Task:
  subagent_type: bughunt-software-architect
  ...same zone A...

Task:
  subagent_type: bughunt-qa-engineer
  ...same zone A...

# Zone B: skills + agents (6 agents)
Task:
  subagent_type: bughunt-code-reviewer
  model: sonnet
  description: "Bug Hunt: code review [Zone B: skills]"
  prompt: |
    ...same structure, zone B files...

# ... repeat for each zone
```

Launch ALL agents (6 × N zones) in a SINGLE message for maximum parallelism.

**Output of Step 1:** Raw findings from 6 perspectives × N zones.

### STEP 2: Create Findings Summary

Collect all persona results from ALL zones. For each finding, record:
ID (prefixed by zone: A-CR-001, B-SEC-003), severity, title, category, zone.
Save as PERSONA_FINDINGS (needed by Step 3).

Note: some findings may appear in multiple zones (boundary overlap). That's OK —
the validator deduplicates in Step 5.

### STEP 3: Launch Framework Agents

Personas find SYMPTOMS. Framework agents find CAUSES and PATTERNS among those symptoms.
Step 5 (validator) requires Framework Analysis section — spec without it is rejected.

Framework agents receive findings from ALL zones — they analyze cross-zone patterns.

Launch TOC + TRIZ with PERSONA_FINDINGS from Step 2:

```yaml
Task:
  subagent_type: bughunt-toc-analyst
  model: opus
  description: "Bug Hunt: TOC analysis"
  prompt: |
    ## Persona Findings Summary
    {PERSONA_FINDINGS — all IDs, titles, severities from Step 2}

    TARGET: {target_path}

    Build Current Reality Tree from these findings.
    Identify core constraints and causal chains.

Task:
  subagent_type: bughunt-triz-analyst
  model: opus
  description: "Bug Hunt: TRIZ analysis"
  prompt: |
    ## Persona Findings Summary
    {PERSONA_FINDINGS — all IDs, titles, severities from Step 2}

    TARGET: {target_path}

    Identify contradictions and ideality gaps.
    Apply inventive principles to find solutions.
```

**Output of Step 3:** TOC constraints + TRIZ contradictions referencing persona findings.

### STEP 4: Assemble Umbrella Spec

Combine ALL results (personas from Step 1 + frameworks from Step 3) into:

```
ai/features/BUG-XXX/BUG-XXX.md
```

The spec MUST contain a `## Framework Analysis` section with TOC and TRIZ subsections.
This is verified by the validator in Step 5 — spec without it is rejected.

### STEP 5: Launch Validator

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
    Group relevant findings into 3-8 coherent groups by functional area.
```

The validator will reject the spec if Framework Analysis is missing (see validator agent prompt).
The validator also GROUPS findings — each group becomes a separate spec for autopilot.

### STEP 6: Update Report

After validator returns:
1. Update BUG-XXX report with validator results (this is a REPORT, not an executable spec)
2. Append out-of-scope ideas to `ai/ideas.md`
3. Update Executive Summary with actual counts:
   - Total findings, relevant count, out-of-scope count, duplicates merged, groups formed
4. Do NOT proceed to Step 7 until Executive Summary has real numbers (not TBD)

### STEP 7: Create Grouped Specs

**Key principle:** Autopilot works best with focused, atomic specs. One spec = one coherent fix
that goes through plan → code → test → review. Packing 29 sub-tasks degrades quality.

For each GROUP from the validator, allocate a separate sequential ID and create a standalone spec.

**ID allocation:** Read ai/backlog.md, find global max ID. Allocate IDs sequentially:
if max is BUG-084, groups get BUG-085, BUG-086, BUG-087, etc.

```yaml
# For each GROUP from validator (e.g., "Hook Safety", "Missing References"):
Task:
  subagent_type: bughunt-solution-architect
  model: opus
  description: "Bug Hunt: spec BUG-085 (Hook Safety)"
  prompt: |
    ## Group: Hook Safety
    Findings in this group:
    {list of findings F-001, F-005, F-006, F-017, F-018, F-027}

    ## Context
    Bug Hunt report: BUG-084
    Spec ID for this group: BUG-085
    Target: {target_path}

    Create a STANDALONE spec at: ai/features/BUG-085.md
    This spec must be independently executable by autopilot.
    Include: Impact Tree, Allowed Files, Definition of Done.
    Status: queued
```

**Result:** Directory structure:
```
ai/features/
├── BUG-084-bughunt.md  ← report (READ-ONLY index, not in backlog)
├── BUG-085.md           ← standalone spec: Hook Safety (queued)
├── BUG-086.md           ← standalone spec: Missing References (queued)
├── BUG-087.md           ← standalone spec: Prompt Injection (queued)
└── ...
```

**Each spec goes independently through autopilot:** plan → code → test → review.

## Bug Hunt Report Template

The report is a READ-ONLY index. It is NOT added to backlog.
Each grouped spec gets its own backlog entry.

```markdown
# Bug Hunt Report: {Title}

**ID:** BUG-XXX (report only, not in backlog)
**Date:** YYYY-MM-DD
**Mode:** Bug Hunt (multi-agent)
**Cost:** ~${estimated_cost}

## Original Problem
{User's description}

## Executive Summary
- Zones analyzed: {N_zones} ({zone_names})
- Total findings analyzed: {N_total}
- Relevant (in scope): {N_relevant}
- Out of scope (→ ideas.md): {N_out}
- Duplicates merged: {N_dupes}
- Groups formed: {N_groups}
- Specs created: {N_specs}

## Grouped Specs

| # | Spec ID | Group Title | Findings | Priority | Status |
|---|---------|------------|----------|----------|--------|
| 1 | BUG-YYY | Hook Safety | F-001, F-005, F-006 | P0 | queued |
| 2 | BUG-ZZZ | Missing References | F-002, F-011, F-012 | P1 | queued |

## Framework Analysis

### TOC (Theory of Constraints)
{Core constraint identified}
{Causal chain summary}

### TRIZ
{Key contradictions}
{Suggested inventive principles}

## Consensus Matrix

| Finding | Zone | CR | SEC | UX | JR | ARCH | QA | TOC | TRIZ | Consensus |
|---------|------|----|----|----|----|----|----|----|------|-----------|
| F-001   | A    | x  |    |    |    | x  |    |    |      | 2/8       |
```

## Handoff

After all grouped specs are created:
1. Save report as `ai/features/BUG-XXX-bughunt.md` (NOT in backlog)
2. Add ONE backlog entry per grouped spec (each with its own sequential ID)
3. Auto-commit: `git add ai/ && git commit`
4. Ask user: "Bug Hunt complete. {N} specs created ({IDs}). Run autopilot?"
5. If user confirms → autopilot picks up specs from backlog independently

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

**Bug Hunt Pipeline Rules:**
- Execute ALL 8 steps (0-7) in order — each step's output is required by the next step
- Step 0 (decomposition) enables depth — wide scope without zones = shallow findings only
- Validator (Step 5) rejects specs missing Framework Analysis — skipping Step 3 means restarting
- If context is too large, SUMMARIZE findings before passing to next step — don't skip the step

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
1. [ ] Scope decomposed into zones (Step 0) — or single zone if <30 files
2. [ ] All 6 persona agents completed PER ZONE (Step 1)
3. [ ] TOC + TRIZ framework agents completed (Step 3)
4. [ ] Draft spec has `## Framework Analysis` section (Step 4)
5. [ ] Validator passed — spec not rejected (Step 5)
6. [ ] Report has actual counts in Executive Summary, not TBD (Step 6)
7. [ ] Grouped specs created — one standalone spec per group (Step 7)
8. [ ] Report has Grouped Specs table with all spec IDs
9. [ ] Out-of-scope ideas saved to ai/ideas.md

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
groups_count: N                  # Bug Hunt mode
spec_ids: [BUG-085, BUG-086, BUG-087]  # Bug Hunt mode — standalone specs
report_path: "ai/features/BUG-XXX-bughunt.md"  # Bug Hunt mode — READ-ONLY report
spec_path: "ai/features/BUG-XXX.md"  # Quick mode
research_sources_used:
  - url: "..."
    used_for: "pattern X"
handoff: autopilot | needs_discussion
```

**Next step:** User confirms → auto-handoff to `/autopilot`
