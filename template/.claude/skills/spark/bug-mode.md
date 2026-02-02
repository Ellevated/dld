# Bug Mode for Spark

**Purpose:** Self-contained guide for systematic bug investigation, root cause analysis, and spec creation.

---

## When to Use Bug Mode

**Triggers:**
- User says "bug", "error", "crashes", "doesn't work"
- Test failures without clear solution
- Unexpected behavior in production

**Flow:** Reproduce → Isolate → Root Cause → Create Spec → Handoff to Autopilot

---

## 5 Whys + Systematic Debugging

For BUGS — find ROOT CAUSE before creating spec!

### Phase 1: REPRODUCE

```
"Show exact reproduction steps:"
1. What command/action?
2. What input?
3. What output do we get?
4. What output do we expect?
```

**Get EXACT error output!** Not "test fails" but actual traceback.

### Phase 2: ISOLATE

```
Find problem boundaries:
- When did it start? (last working commit?)
- Where exactly does it fail? (file:line)
- Does it reproduce every time?
- Are there related files?
```

Read files, grep, find the exact location.

### Phase 3: ROOT CAUSE — 5 Whys

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
    QUERY: "{error_type}: {error_message}. Common causes and fixes in {tech_stack}. How others solved similar issues."
    TYPE: error
    DATE: {current date}
```

**How to fill:**
- `{error_type}` — error class (e.g., "SQLAlchemy IntegrityError", "asyncio TimeoutError")
- `{error_message}` — actual error text from logs/traceback
- `{tech_stack}` — your stack (e.g., "Python aiogram 3", "PostgreSQL", "FastAPI")

---

## Deep Research + Results Integration

### When to Do Deep Research

**Trigger:** After initial scout, when fix approach is unclear or complex.

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

**How to fill from investigation:**
- Use the approach determined in Phase 3
- Include specific terms from error messages
- Narrow to the exact pattern/library involved

### Scout Results Integration

- **Root Cause Analysis** MUST reference Scout findings: "Found [X] causes in [source]"
- **Fix Approach** MUST cite Scout sources: "Pattern from [Scout source]"
- **Spec Research Sources** MUST include Scout URLs
- If Scout found nothing useful — note it and proceed with own analysis

See `.claude/agents/scout.md` for Scout internals.

---

## Bug Spec Template

### Phase 4: CREATE BUG SPEC

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

## Research Sources
- [Pattern](url) — description from Scout
- [Fix Example](url) — relevant solution

## Allowed Files
1. `path/to/file.py` — fix location
2. `path/to/test.py` — add regression test

## Definition of Done
- [ ] Root cause fixed
- [ ] Original test passes
- [ ] Regression test added
- [ ] No new failures
```

---

## Exact Paths Required (BUG-328)

**RULE:** Allowed Files must contain EXACT file paths, not placeholders.

```markdown
# ❌ WRONG — CI validation fails
## Allowed Files
1. `db/migrations/YYYYMMDDHHMMSS_create_function.sql`

# ✅ CORRECT — exact timestamp
## Allowed Files
1. `db/migrations/20260116153045_create_function.sql`
```

**For migrations:** Generate timestamp first, then write spec.

```bash
# 1. Create migration (gets timestamp)
# Use your DB tool: alembic, prisma, knex, etc.

# 2. Note exact filename
ls db/migrations/*.sql | tail -1

# 3. Use exact name in spec
```

**Why:** CI validator (`validate_spec.py`) does literal string matching, not pattern recognition.

---

## Bug Mode Rules

**Investigation Rules:**
- ⛔ **NEVER guess the cause** — investigate first!
- ⛔ **NEVER fix symptom** — fix root cause!
- ⛔ **NEVER skip reproduction** — must have exact steps!

**Execution Rules:**
- ✅ **ALWAYS create spec** — Autopilot does the actual fix
- ✅ **ALWAYS add regression test** — in spec's DoD
- ✅ **ALWAYS use Impact Tree** — find all affected files

**Handoff Rules:**
- ✅ Bugs go through: spark → plan → autopilot
- ❌ No direct fixes during spark (READ-ONLY mode)
- ✅ Auto-commit spec before handoff

---

## Execution Style (No Commentary)

When invoking spark for bugs:
- ✅ "Running spark for BUG-XXX"
- ❌ "This is BUG, not feature, but since you asked for spec..."
- ❌ "This is not a Spark task, but since you asked..."

**Rule:** Don't comment on the process — just execute. Bugs go through spark → plan → autopilot.

---

## STRICT READ-ONLY MODE

**During Bug Mode spark phase:**
- READ files — allowed
- SEARCH/GREP — allowed
- CREATE spec file in `ai/features/` — allowed
- WRITE to `ai/diary/` — allowed (corrections capture)
- MODIFY any other file — **FORBIDDEN**

**Exception:**
- Hotfix <5 LOC → fix directly without spec (with user approval)

---

## Pre-Completion Checklist

⛔ **DO NOT COMPLETE BUG MODE** without checking ALL items:

1. [ ] **Root cause identified** — 5 Whys complete, not just symptom
2. [ ] **Reproduction steps exact** — not "test fails" but full traceback
3. [ ] **Scout research done** — error patterns checked
4. [ ] **Impact Tree Analysis** — all affected files found
5. [ ] **Allowed Files exact** — no placeholders (especially migrations)
6. [ ] **Regression test in DoD** — prevents recurrence
7. [ ] **ID determined by protocol** — BUG-XXX incremented correctly
8. [ ] **Spec file created** — ai/features/BUG-XXX-YYYY-MM-DD-name.md
9. [ ] **Entry added to backlog** — in `## Queue` section
10. [ ] **Status = queued** — spec ready for autopilot!
11. [ ] **Auto-commit done** — `git add ai/ && git commit` (no push!)

If any item not done — **STOP and do it**.

---

## Common Bug Patterns

| Pattern | Investigation Focus | Typical Root Cause |
|---------|---------------------|-------------------|
| Test fails intermittently | Race conditions, async timing | Missing await, shared state |
| Migration fails | Schema state, dependencies | Missing constraint, wrong order |
| Function returns None | Control flow, initialization | Missing return, unhandled case |
| Foreign key violation | Data dependencies, order | Missing parent record, wrong cascade |
| Type error | Type assumptions, API changes | Schema drift, missing validation |

**Use Scout to research specific pattern before creating fix approach!**

---

## Output Format

```yaml
status: completed | blocked
bug_id: BUG-XXX
root_cause: "[1-line summary]"
spec_path: "ai/features/BUG-XXX-YYYY-MM-DD-name.md"
research_sources_used:
  - url: "..."
    used_for: "pattern X"
handoff: autopilot | needs_discussion
```

**Next step:** User confirms → auto-handoff to `/autopilot`
