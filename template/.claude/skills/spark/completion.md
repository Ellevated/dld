# Spark Completion Logic

**Read this AFTER creating spec — Shared completion logic for both Feature and Bug modes**

---

## ID Determination Protocol (MANDATORY)

Before creating spec — determine next ID:

1. **Determine type:** FTR | BUG | TECH | ARCH
2. **Scan backlog:** Open ai/backlog.md
3. **Find ALL IDs across ALL types:** Use pattern `(FTR|BUG|TECH|ARCH)-(\d+)`
4. **Take global maximum:** Sort ALL numbers, take max across ALL types
5. **Add +1:** Next ID = TYPE-{max+1}

**Numbering is SEQUENTIAL ACROSS ALL TYPES** (see CLAUDE.md#Backlog-Rules).

**Example:**
- Backlog contains: TECH-079, TECH-080, TECH-081
- New bug → Next ID: **BUG-082** (not BUG-001!)
- New feature → Next ID: **FTR-082**

**FORBIDDEN:** Per-type numbering. Guessing ID. Using "approximately next".

### Concurrency Warning

Sequential ID assignment is NOT atomic. If two spark instances run concurrently:
1. Both read the same max ID from backlog.md
2. Both create specs with the same next ID
3. Git merge conflict or duplicate IDs result

**Prevention:** Run spark from ONE terminal at a time. Do not run spark while autopilot is executing.

---

## Pre-Completion Checklist (BLOCKING)

⛔ **DO NOT COMPLETE SPARK** without checking ALL items:

1. [ ] **ID determined by protocol** — not guessed!
2. [ ] **Uniqueness check** — grep backlog didn't find this ID
3. [ ] **Spec file created** — ai/features/TYPE-XXX-YYYY-MM-DD-name.md
4. [ ] **Entry added to backlog** — in `## Queue` section
5. [ ] **Status = queued** — spec ready for autopilot!
6. [ ] **Function overlap check** (ARCH-226) — grep other queued specs for same function names
   - If overlap found: merge into single spec OR mark dependency
7. [ ] **Auto-commit done** — `git add ai/ && git commit` (no push!)

If any item not done — **STOP and do it**.

---

## Post-Write Verification (MANDATORY)

After BOTH spec file and backlog entry are written, verify consistency:

```bash
# Verify backlog entry exists for this spec
grep "{TASK_ID}" ai/backlog.md
```

**If NOT found (grep returns nothing):**
1. STOP — do not proceed to auto-commit
2. Add the backlog entry NOW (use the format from ## Backlog Entry above)
3. Re-verify with grep
4. Only then continue to auto-commit

**Checklist addition:**
- [ ] Post-write verification: grep confirmed TASK_ID in backlog

---

## Backlog Entry Verification (BLOCKING — BUG-358)

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

---

## Status Sync Self-Check (SAY OUT LOUD — BUG-358)

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

---

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

---

## Umbrella Specs (Bug Hunt Mode)

Bug Hunt creates umbrella specs with sub-specs in a directory:

```
ai/features/BUG-XXX/
├── BUG-XXX.md          ← umbrella (table of contents)
├── BUG-XXX-01.md       ← sub-spec (queued)
├── BUG-XXX-02.md       ← sub-spec (queued)
└── ...
```

### Backlog Entry

ONE entry for the umbrella. Sub-specs are tracked inside the umbrella.

```
| BUG-XXX | Bug Hunt: {title} | queued | P0 | [BUG-XXX](features/BUG-XXX/BUG-XXX.md) |
```

### ID Protocol for Sub-Specs

Sub-specs use the umbrella ID + sequential number: BUG-XXX-01, BUG-XXX-02, etc.
They do NOT get separate backlog entries.

### Autopilot Handoff (Sequential)

Autopilot processes sub-specs in order:
```
BUG-XXX-01 → Planner → Coder → Tester → done
BUG-XXX-02 → Planner → Coder → Tester → done
...
```

Each sub-spec is an independent task. If one fails, others continue.

---

## Auto-Commit (MANDATORY before handoff!)

After spec file is created and backlog updated — commit ALL changes locally:

```bash
# 1. Stage spec-related changes only (explicit paths, not entire ai/ directory)
git add "ai/features/${TASK_ID}"* ai/backlog.md

# 2. Commit locally (NO PUSH!)
git commit -m "docs: create spec ${TASK_ID}"
```

**Why `git add ai/` (not `-A`):**
- Only commits spec, backlog, diary — controlled files
- Protects from accidental credential commits
- .gitignore is defense-in-depth, not primary protection

**Why NO push:**
- CI doesn't trigger (saves money)
- Spec validation doesn't fail
- Commit is protected locally — won't be lost
- Autopilot will push everything at the end of PHASE 3

**When:** ALWAYS before asking "Run autopilot?"

---

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

---

## Output

### If running as subagent (Task tool — no user interaction):
⛔ **MUST use Write tool to create spec file BEFORE returning!**
⛔ **MUST use Edit tool to add backlog entry BEFORE returning!**

Returning spec_path without creating file = DATA LOSS (subagent context dies).

### If running interactively (Skill tool):
Write spec file when spec is complete, then ask about autopilot handoff.

### Return format:
```yaml
status: complete | needs_discussion | blocked
spec_path: ai/features/TYPE-XXX.md  # file MUST exist
handoff: autopilot | council | blocked
```
