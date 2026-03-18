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
4. [ ] **Entry added to backlog** — in active tasks table
5. [ ] **Status = queued** — spec ready for orchestrator pickup!
6. [ ] **Function overlap check** (ARCH-226) — grep other queued specs for same function names
   - If overlap found: merge into single spec OR mark dependency
7. [ ] **Auto-commit done** — `git add ai/ && git commit` (no push!)

If any item not done — **STOP and do it**.

---

## Post-Write Verification (MANDATORY — BUG-358)

After BOTH spec file and backlog entry are written, verify consistency:

```bash
# 1. Verify backlog entry exists
grep "{TASK_ID}" ai/backlog.md

# 2. If NOT found → ADD NOW (don't proceed!)
# Edit ai/backlog.md → add entry to active tasks table

# 3. Re-verify
grep "{TASK_ID}" ai/backlog.md
# Must show the entry!

# 4. Only then → continue to auto-commit
```

⛔ **Spark without backlog entry = DATA LOSS!**
Autopilot reads ONLY backlog — orphan spec files are invisible to it.

---

## Status Sync Self-Check (SAY OUT LOUD — BUG-358)

When setting status in spec, **verbally confirm**:

```
"Setting spec file: Status → queued"        [Write/Edit spec]
"Setting backlog entry: Status → queued"    [Edit backlog]
"Both set? ✓"                               [Verify match]
```

⛔ **One place only = desync = orchestrator won't find the task!**

### Backlog entry format:
```
| ID | Task | Status | Priority | Risk | Feature.md |
|----|------|--------|----------|------|------------|
| FTR-XXX | Task name | queued | P1 | R2 | [FTR-XXX](features/FTR-XXX-YYYY-MM-DD-name.md) |
```

### Status on Spark exit:
| Situation | Status | Reason |
|-----------|--------|--------|
| Spark completed fully | `queued` | Ready for orchestrator pickup |
| Spec created but interrupted | `queued` | Orchestrator will pick up on next cycle |
| Needs discussion/postponed | `queued` | Left for refinement, orchestrator holds until slot available |

---

## Backlog Format (STRICT)

**When adding entry:**
1. Open `ai/backlog.md`
2. Find the ACTIVE tasks table (above the `## DONE` section)
3. Add row to **end** of active table (last row before `---` or `## DONE`)
4. DO NOT create new sections or tables

**FORBIDDEN:**
- Creating new sections/tables
- Grouping tasks by categories
- Adding headers like "## Tests" or "## Legacy"

---

## File Naming Conventions

| Mode | Pattern | Example |
|------|---------|---------|
| Feature | `FTR-XXX-YYYY-MM-DD-name.md` | `FTR-089-2026-02-15-diagram-skill.md` |
| Quick Bug | `BUG-XXX-YYYY-MM-DD-name.md` | `BUG-082-2026-02-08-push-ambiguity.md` |
| Bug Hunt report | `BUG-XXX-bughunt.md` | `BUG-084-bughunt.md` |
| Bug Hunt grouped | `BUG-XXX.md` | `BUG-087.md` |

Bug Hunt grouped specs omit date/name for brevity (auto-generated, many at once).

---

## Bug Hunt Mode Output

Bug Hunt creates a READ-ONLY report + standalone grouped specs:

```
ai/features/
├── BUG-XXX-bughunt.md   ← report (READ-ONLY index, NOT in backlog)
├── BUG-YYY.md            ← standalone spec: Group 1 (queued)
├── BUG-ZZZ.md            ← standalone spec: Group 2 (queued)
└── ...
```

### Report (NOT in Backlog)

The report is a READ-ONLY index of what was found. It does NOT go into backlog.
File naming: `BUG-XXX-bughunt.md` (the XXX is the report ID, not a task ID).

### Grouped Specs (IN Backlog)

Each group gets its OWN sequential ID and its OWN backlog entry:

```
| BUG-085 | Hook safety fixes | queued | P0 | [BUG-085](features/BUG-085.md) |
| BUG-086 | Missing references | queued | P1 | [BUG-086](features/BUG-086.md) |
| BUG-087 | Prompt injection | queued | P1 | [BUG-087](features/BUG-087.md) |
```

### ID Protocol for Grouped Specs

1. Report gets an ID (e.g., BUG-084) — used only for the report filename
2. Find global max ID in backlog (e.g., max is BUG-084)
3. Each group gets NEXT sequential ID: BUG-085, BUG-086, BUG-087, etc.
4. Each grouped spec is a standalone, independently executable spec

### Autopilot Handoff

Each grouped spec runs independently through autopilot:
```
BUG-085 → Planner → Coder → Tester → done
BUG-086 → Planner → Coder → Tester → done
...
```

Each spec is fully independent. User can run autopilot on any single spec.

---

## Headless Mode: Write SpecID to Inbox File (MANDATORY)

When running in headless mode (inbox-originated), write the spec ID back to the
originating inbox file so the pipeline can map inbox labels to real spec IDs.

After spec is created and BEFORE auto-commit:

1. Check env var: `CLAUDE_CURRENT_SPEC_PATH`
2. If set and file exists at that path:
   - Append line: `**SpecID:** {TASK_ID}` to the file
   - This enables pueue-callback.sh to resolve real spec_id for QA dispatch

Example:
```bash
# The inbox done file at CLAUDE_CURRENT_SPEC_PATH gets:
**SpecID:** TECH-157
```

**Why:** Without this, QA dispatch after autopilot can't find the spec file
because the pueue task label contains the inbox filename, not the spec ID.

---

## Auto-Commit + Push (MANDATORY)

After spec file is created and backlog updated — commit and push:

```bash
# 1. Stage spec-related changes only (explicit paths, not entire ai/ directory)
git add "ai/features/${TASK_ID}"* ai/backlog.md 2>/dev/null

# 2. Commit
# Note: If ai/ is in .gitignore, git add is a no-op (expected)
git diff --cached --quiet || git commit -m "docs: create spec ${TASK_ID}"

# 3. Push to develop (orchestrator pulls from remote)
git push origin develop
```

**Why push:** Orchestrator runs on VPS — needs specs on remote to pull and process.

**Why `git add ai/` (not `-A`):**
- Only commits spec, backlog, diary — controlled files
- Protects from accidental credential commits
- .gitignore is defense-in-depth, not primary protection

**Bug Hunt mode:** Uses its own commit pattern from `bug-mode.md` (explicit file list instead of `ai/`).

### CI Protection

Projects MUST have `ai/**` in `.github/workflows` `paths-ignore`.
Otherwise each spark push triggers CI on documentation-only changes.

```yaml
# .github/workflows/ci.yml
on:
  push:
    paths-ignore:
      - 'ai/**'
      - '*.md'
```

---

## Completion — No Handoff

After spec is committed and pushed, Spark is DONE. No autopilot handoff.

**Flow:**
1. Spec saved to `ai/features/TYPE-XXX-YYYY-MM-DD-name.md` with status `queued`
2. Committed + pushed to develop
3. Orchestrator detects queued spec on next cycle
4. Autopilot picks it up

**Announcement format (interactive mode only):**
```
Spec ready: `ai/features/TYPE-XXX-YYYY-MM-DD-name.md`

**Summary:**
- [2-3 bullet points what will be done]

Spec is queued. Orchestrator will hand it to autopilot.
```

**DO NOT invoke `/autopilot`.** Orchestrator manages the lifecycle.

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
spec_path: ai/features/TYPE-XXX-YYYY-MM-DD-name.md  # file MUST exist
spec_status: queued  # always queued — orchestrator picks up on next cycle
pushed: true | false
```
