# Bug Mode for Spark

**Purpose:** Systematic bug investigation via Quick Bug Mode (5 Whys → single spec).

For deep multi-agent analysis, use the standalone `/bughunt` skill instead.

---

## Mode Selection

| Signal | Mode | Description |
|--------|------|-------------|
| Simple bug, clear location, <5 files | **Quick Bug Mode** | 5 Whys → single spec |
| Complex bug, unclear cause, >5 files, "bug hunt", "deep analysis" | **→ /bughunt** | Redirect to standalone bughunt skill |
| User explicitly says "bug hunt", "баг-хант", "охота на баги" | **→ /bughunt** | Redirect to standalone bughunt skill |

**Default:** Quick Bug Mode. If 5 Whys reveals systemic issues → suggest `/bughunt`.

**Bug Hunt is a separate skill.** Do NOT run Bug Hunt pipeline from Spark.
If complex analysis needed, tell the user: "This needs `/bughunt` — it's a separate deep analysis skill."
If in headless mode, create inbox file with Route: bughunt instead.

---

# Quick Bug Mode

**Flow:** Reproduce → Isolate → Root Cause (5 Whys) → Create Spec → Commit + Push

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
# Bug Fix: [BUG-XXX] Title

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

→ Then go to `completion.md` for ID protocol, commit + push.

---

# Bug Hunt Mode (MOVED)

Bug Hunt is now a standalone skill: `/bughunt`

**Do NOT run Bug Hunt from Spark.** Use `/bughunt <target>` directly.

Quick Bug Mode remains in Spark for simple bugs (<5 files).

---

## Bug Research Template

When investigating bug patterns:

```yaml
Task tool:
  description: "Scout: {error_type} fix patterns"
  subagent_type: "scout"
  max_turns: 8
  prompt: |
    MODE: quick
    QUERY: "{error_type}: <user_input>{error_message}</user_input>. Common causes and fixes in {tech_stack}."
    TYPE: error
    DATE: {current date}
```

---

## Exact Paths Required (BUG-328)

**RULE:** Allowed Files must contain EXACT file paths, not placeholders.

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
- Bugs go through: spark → autopilot (via orchestrator approval)
- No direct fixes during spark (READ-ONLY mode)
- Auto-commit + push spec before completion
- DO NOT invoke autopilot — orchestrator manages lifecycle

---

## Pre-Completion Checklist

### Quick Bug Mode Checklist
1. [ ] Root cause identified (5 Whys complete)
2. [ ] Reproduction steps exact
3. [ ] Scout research done
4. [ ] Impact Tree Analysis complete
5. [ ] Allowed Files exact (no placeholders)
6. [ ] Regression test in DoD
7. [ ] ID determined by protocol (completion.md)
8. [ ] Spec file created (status: draft)
9. [ ] Backlog entry added (status: draft)
10. [ ] Auto-commit + push done

---

## Output Format

```yaml
status: completed | blocked
mode: quick
bug_id: BUG-XXX
root_cause: "[1-line summary]"
spec_path: "ai/features/BUG-XXX.md"
spec_status: draft
pushed: true | false
```
