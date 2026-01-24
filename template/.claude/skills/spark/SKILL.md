---
name: spark
description: Idea generation and specification with Exa research and structured dialogue
agent: .claude/agents/spark.md
---

# Spark — Idea Generation & Specification

Transforms raw ideas into specs via Exa research + structured dialogue.

**Activation:** `spark`, `spark quick`, `spark deep`

## When to Use
- New feature, user flow change, architecture decision
- New tool or prompt modification
- **Bug fix** — after diagnosing cause, before fix

**Don't use:** Hotfixes <5 LOC (fix directly), pure refactoring without spec

## Principles
1. **READ-ONLY MODE** — Spark NEVER modifies files (except creating spec in `ai/features/` and `ai/diary/`)
2. **AUTO-HANDOFF** — After spec is ready, auto-handoff to autopilot (no manual "plan" step)
3. **Research-First** — Search Exa + Context7 before designing
4. **AI-First** — Can we solve via prompt change?
5. **Socratic Dialogue** — Ask 5-7 deep questions before designing
6. **YAGNI** — Only what's necessary
7. **Explicit Allowlist** — Spec must list ONLY files that can be modified
8. **Learn from Corrections** — Auto-capture user corrections to diary


## Status Ownership

**See CLAUDE.md#Task-Statuses** for canonical status definitions.

**Key point:** Spark owns `queued` status. Plan subagent adds tasks but doesn't change status.

## Mode Detection

Spark operates in two modes:

| Trigger | Mode | Method |
|---------|------|--------|
| "new feature", "add", "want", "create feature", "create spec", "write specification", "make feature" | **Feature Mode** | Socratic Dialogue |
| "bug", "error", "crashes", "doesn't work" | **Bug Mode** | 5 Whys + Reproduce |

## Socratic Dialogue (Feature Mode)

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

## 5 Whys + Systematic Debugging (Bug Mode)

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

## Allowed Files
1. `path/to/file.py` — fix location
2. `path/to/test.py` — add regression test

## Definition of Done
- [ ] Root cause fixed
- [ ] Original test passes
- [ ] Regression test added
- [ ] No new failures
```

### Bug Mode Rules

- ⛔ **NEVER guess the cause** — investigate first!
- ⛔ **NEVER fix symptom** — fix root cause!

### Exact Paths Required (BUG-328)

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
- ⛔ **NEVER skip reproduction** — must have exact steps!
- ✅ **ALWAYS create spec** — Autopilot does the actual fix
- ✅ **ALWAYS add regression test** — in spec's DoD

## Execution Style (No Commentary)

When invoking spark for bugs:
- ✅ "Running spark for BUG-XXX"
- ❌ "This is BUG, not feature, but since you asked for spec..."
- ❌ "This is not a Spark task, but since you asked..."

**Rule:** Don't comment on the process — just execute. Bugs go through spark → plan → autopilot.

## STRICT RULES

**During Spark phase:**
- READ files — allowed
- SEARCH/GREP — allowed
- CREATE spec file in `ai/features/` — allowed
- WRITE to `ai/diary/` — allowed (corrections capture)
- MODIFY any other file — **FORBIDDEN**

**If task is not suitable for Spark:**
- Hotfix <5 LOC → fix directly without spec
- Pure refactoring without user request → ask user first

## Auto-Capture Corrections (MANDATORY)

When user corrects you during Spark dialogue — capture the learning!

**Detection:** User says something that contradicts/corrects your assumption

**Action:**
1. Acknowledge: "Got it, noted: [brief rule]"
2. Append to `ai/diary/corrections.md`:
```markdown
## YYYY-MM-DD: During TYPE-XXX

**Context:** [what we were discussing]
**I proposed:** [what I suggested]
**User corrected:** [what user said]
**Why:** [reason if given]
**Rule:** [generalized learning in imperative form]
```

**Examples of corrections to capture:**
- "No, that's not how it works for us" → capture how it actually works
- "This is too complex, make it simpler" → capture simplicity preference
- "Always use X instead of Y" → capture tool/pattern preference
- "This already exists in Z" → capture existing solution location

**Goal:** Build project memory. Same mistakes won't repeat.

**In resulting spec:**
- Must include `## Allowed Files` section with explicit list
- Files NOT in allowlist — **FORBIDDEN** to modify during implementation
- Autopilot/Coder must refuse to touch files outside allowlist

## UI Event Completeness (REQUIRED for UI features)

If creating UI elements with callbacks/events — fill this table in spec:

| Producer (keyboard/button) | callback_data | Consumer (handler) | Handler File in Allowed Files? |
|---------------------------|---------------|-------------------|-------------------------------|
| `start_keyboard()` | `guard:start` | `cb_guard_start()` | `onboarding.py` ✓ |

**RULE:** Every `callback_data` MUST have a handler in Allowed Files!

- No handler = No commit (Autopilot will block)
- If handler file missing from Allowed Files — add it or explain why not needed
- This prevents orphan callbacks (BUG-156 post-mortem)

## LLM-Friendly Architecture Checks

**See CLAUDE.md#Forbidden-CI-enforced and CLAUDE.md#Structure** for architecture rules.

Quick checklist before creating spec:
- Files < 400 LOC (600 for tests)
- New code in `src/domains/` or `src/infra/`, NOT legacy folders
- Max 5 exports per `__init__.py`
- Imports follow: shared → infra → domains → api


## Research Phase (via Scout)

Use Scout subagent for external research:
- Library/framework questions
- Best practices
- Architecture patterns

**Call:**
```yaml
Task tool:
  subagent_type: "scout"
  prompt: |
    QUERY: {question}
    TYPE: library | pattern | architecture
```

See `.claude/agents/scout.md` for details.


## ID Determination Protocol (MANDATORY)

Before creating spec — determine next ID:

1. **Determine type:** FTR | BUG | SEC | REFACTOR | ARCH | TECH
2. **Scan backlog:** Open ai/backlog.md
3. **Find all IDs of type:** Use pattern TYPE-\d+
4. **Take maximum:** Sort numbers, take max
5. **Add +1:** Next ID = max + 1

**Example:**
- Backlog contains: FTR-179, FTR-180, FTR-181
- Next ID: FTR-182

**FORBIDDEN:** Guessing ID or using "approximately next".

## Impact Tree Analysis (MANDATORY)

Before creating plan:

1. Identify key terms/files being changed
2. Execute Impact Tree Analysis:
   - UP: `grep -r "from.*{module}" . --include="*.py"`
   - BY TERM: `grep -rn "{term}" . --include="*.py" --include="*.sql" --include="*.ts" --include="*.md"`
   - CHECKLIST: check tests/, migrations/, edge functions/, glossary/
3. ALL found files include in Allowed Files
4. If grep by old term > 0 → add cleanup task
5. Check glossary — need to add new terms?

**FORBIDDEN:**
- Grep only in one folder
- Skip tests/ in analysis
- Mark done if grep by old term > 0

## Process (7 Phases)

**See `.claude/agents/spark.md`** for detailed phases.

Summary: Context → Exa Research → Clarify → Deep Search → Approaches → Design → Spec

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

## Spec Template

```markdown
# Feature: [FTR-XXX] Title
**Status:** queued | **Priority:** P0/P1/P2 | **Date:** YYYY-MM-DD

## Why
## Context

---
## Scope
In scope: ... | Out of scope: ...

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

## Allowed Files
**ONLY these files may be modified during implementation:**
1. `path/to/file1.py` — reason
2. `path/to/file2.py` — reason
3. `path/to/file3.py` — reason

**New files allowed:**
- `path/to/new_file.py` — reason

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

## Environment

<!-- Smart defaults: adjust based on your stack -->
nodejs: false
docker: false
database: false

## Approaches
### Approach 1: [Name] (based on [source])
Source: URL | Summary: ... | Pros/Cons: ...

### Selected: [N]
Rationale: ...

## Design
User Flow: ... | Architecture: ... | DB: ...

## Implementation Plan
### Research Sources
- [Pattern](url) — description

### Task 1: [Name]
Type: code | Files: create/modify | Pattern: [url] | Acceptance: ...

### Execution Order
1 → 2 → 3

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

## Autopilot Log
```

## Pre-Completion Checklist (BLOCKING)

⛔ **DO NOT COMPLETE SPARK** without checking ALL items:

1. [ ] **ID determined by protocol** — not guessed!
2. [ ] **Uniqueness check** — grep backlog didn't find this ID
3. [ ] **Spec file created** — ai/features/TYPE-XXX-YYYY-MM-DD-name.md
4. [ ] **Entry added to backlog** — in `## Queue` section
5. [ ] **Status = queued** — spec ready for autopilot!
6. [ ] **Function overlap check** (ARCH-226) — grep other queued specs for same function names
   - If overlap found: merge into single spec OR mark dependency
7. [ ] **Auto-commit done** — `git add -A && git commit` (no push!)

If any item not done — **STOP and do it**.

### Backlog Entry Verification (BLOCKING — BUG-358)

After creating spec file, **VERIFY** backlog entry exists:

```bash
# 1. Run verification
grep "{TASK_ID}" ai/backlog.md

# 2. If NOT found → ADD NOW (don't proceed!)
# Edit ai/backlog.md → add entry to ## Queue table

# 3. Re-verify
grep "{TASK_ID}" ai/backlog.md
# Must show the entry!

# 4. Only then → complete spark
```

⛔ **Spark without backlog entry = DATA LOSS!**
Autopilot reads ONLY backlog — orphan spec files are invisible to it.

### Status Sync Self-Check (SAY OUT LOUD — BUG-358)

When setting status in spec, **verbally confirm**:

```
"Setting spec file: Status → queued"       [Write/Edit spec]
"Setting backlog entry: Status → queued"   [Edit backlog]
"Both set? ✓"                              [Verify match]
```

⛔ **One place only = desync = autopilot won't see the task!**

### Backlog entry format:
```
| ID | Task | Status | Priority | Feature.md |
|----|------|--------|----------|------------|
| FTR-XXX | Task name | queued | P1 | [FTR-XXX](features/FTR-XXX-YYYY-MM-DD-name.md) |
```

### Status on Spark exit:
| Situation | Status | Reason |
|-----------|--------|--------|
| Spark completed fully | `queued` | Autopilot can pick up |
| Spec created but interrupted | `draft` | Autopilot does NOT take draft |
| Needs discussion/postponed | `draft` | Left for refinement |

## Backlog Format (STRICT)

**Structure of ai/backlog.md — immutable:**

```
## Queue          ← single task table
## Statuses       ← status reference
## Archive        ← link to archive
## Ideas          ← link to ideas.md
```

**FORBIDDEN:**
- Creating new sections/tables
- Grouping tasks by categories
- Adding headers like "## Tests" or "## Legacy"

**When adding entry:**
1. Open `ai/backlog.md`
2. Find `## Queue` section
3. Add row to **end** of table (before `---`)
4. DO NOT create new sections

**Why:** LLM gets confused with multiple tables and doesn't know where to add new entries. One table = one place = no confusion.

## Auto-Commit (MANDATORY before handoff!)

After spec file is created and backlog updated — commit ALL changes locally:

```bash
# 1. Stage ALL changes (spec, backlog, diary, docs, screenshots, etc.)
git add -A

# 2. Commit locally (NO PUSH!)
git commit -m "docs: create spec ${TASK_ID}"
```

**Why `git add -A`:**
- Captures everything: spec, backlog, diary, docs, screenshots
- Saves work from other agents (scout, manual edits)
- .gitignore protects from junk (.env, __pycache__)

**Why NO push:**
- CI doesn't trigger (saves money)
- Spec validation doesn't fail
- Commit is protected locally — won't be lost
- Autopilot will push everything at the end of PHASE 3

**When:** ALWAYS before asking "Run autopilot?"

## Auto-Handoff to Autopilot

After Spec is complete — auto-handoff to Autopilot. No manual "plan" step!

**Flow:**
1. Spec saved to `ai/features/TYPE-XXX.md`
2. Ask user: "Spec ready. Run autopilot?"
3. If user confirms → invoke Skill tool with `skill: "autopilot"`
4. If user declines → stop and let user decide

**Announcement format:**
```
Spec ready: `ai/features/TYPE-XXX-YYYY-MM-DD-name.md`

**Summary:**
- [2-3 bullet points what will be done]

Run autopilot?
```

**What happens in Autopilot:**
- Plan Subagent creates detailed tasks
- Fresh Coder/Tester/Reviewer subagents per task
- Auto-commit after each task
- All in isolated worktree branch

**Exception: Council first**
If task is complex/controversial (architecture change, >10 files, breaking change):
```
Spec ready, but recommend Council review before implementation.
Reason: [why controversial]

Run council?
```

## Output

### If running as subagent (Task tool — no user interaction):
⛔ **MUST use Write tool to create spec file BEFORE returning!**
⛔ **MUST use Edit tool to add backlog entry BEFORE returning!**

Returning spec_path without creating file = DATA LOSS (subagent context dies).

### If running interactively (Skill tool):
Write spec file when Phase 7 complete, then ask about autopilot handoff.

### Return format:
```yaml
status: complete | needs_discussion | blocked
spec_path: ai/features/TYPE-XXX.md  # file MUST exist
handoff: autopilot | council | blocked
```
