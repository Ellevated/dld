# Feature: [TECH-067] Planner Mandatory Drift Check

**Status:** done | **Priority:** P1 | **Date:** 2026-02-02

## Why

Specs can become stale between creation and execution. When autopilot picks up a spec from backlog, the codebase may have changed significantly. Currently:
1. Planner CAN skip drift check for "trivial" tasks
2. Even when drift is detected, there's no hard gate — execution continues

This leads to failed implementations because the plan is based on outdated assumptions.

## Context

**Current state:**
- `planner.md` has Phase 1.5 (Codebase Drift Check) marked as MANDATORY
- `planner.md:141` has exception: `SKIP allowed: Trivial changes (<20 LOC), pure config edits`
- Output includes `drift_items: N` but autopilot doesn't act on it

**Desired state:**
- Drift check ALWAYS runs (no skip for trivial)
- Light drift → AUTO-FIX (update spec references automatically)
- Heavy drift → ESCALATE TO COUNCIL
- All drift actions logged in spec's `## Drift Log` section

---

## Scope

**In scope:**
- Remove "SKIP allowed" exception from planner
- Add drift classification (light vs heavy)
- Implement AUTO-FIX for light drift
- Implement COUNCIL escalation for heavy drift
- Add `## Drift Log` section format to spec output
- Update escalation.md with new escalation type
- Sync template/ files

**Out of scope:**
- Changing council workflow
- Adding new council experts
- Diary integration (logging to diary)

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses planner?
- [x] `grep -r "planner" .claude/` → 3 files
- [x] All callers: autopilot/SKILL.md, subagent-dispatch.md, planner/SKILL.md

### Step 2: DOWN — what does planner use?
- [x] Read, Glob, Grep, Edit (existing)
- [x] **NEW:** council escalation path

### Step 3: BY TERM — grep entire project
- [x] `grep -rn "SKIP allowed" .` → 1 result (planner.md:141)
- [x] `grep -rn "drift" .claude/` → 2 files

| File | Line | Status | Action |
|------|------|--------|--------|
| `.claude/agents/planner.md` | 141 | REMOVE | Delete SKIP exception |
| `.claude/agents/planner.md` | 63-95 | MODIFY | Add classification + auto-fix |
| `.claude/skills/planner/SKILL.md` | 40-45 | MODIFY | Update output format |
| `.claude/skills/autopilot/escalation.md` | 7 | ADD | New escalation type |

### Step 4: CHECKLIST — mandatory folders
- [x] `template/**` checked — has copies of all files
- [x] No tests for prompts (markdown only)

### Verification
- [x] All found files added to Allowed Files
- [x] grep by "SKIP allowed" = 1 (will become 0)

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `.claude/agents/planner.md` — main agent prompt, add drift classification + auto-fix logic
2. `.claude/skills/planner/SKILL.md` — skill description, update output format
3. `.claude/skills/autopilot/escalation.md` — add heavy_drift escalation type

**Template sync (must match root):**

4. `template/.claude/agents/planner.md` — sync with root
5. `template/.claude/skills/planner/SKILL.md` — sync with root
6. `template/.claude/skills/autopilot/escalation.md` — sync with root

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Design

### Drift Classification

| Type | Criteria | Action |
|------|----------|--------|
| **none** | All files exist, no significant changes | Continue |
| **light** | Line numbers shifted, functions renamed, files moved, new params added | AUTO-FIX |
| **heavy** | Files/functions deleted, API incompatible, deps removed, >50% files changed substantially | COUNCIL |

### Light Drift AUTO-FIX

Planner automatically updates spec:
1. Updates line number references
2. Updates function/class names
3. Updates file paths
4. Adds note about new parameters

### Heavy Drift COUNCIL Escalation

```yaml
Skill tool:
  skill: "council"
  args: |
    escalation_type: heavy_drift
    spec_path: "{spec_path}"
    drift_report:
      deleted_files: [...]
      incompatible_apis: [...]
      removed_deps: [...]
    question: "Spec assumptions no longer valid. Should we: (a) rewrite spec, (b) adapt approach, (c) reject task?"
```

### Drift Log Format (added to spec)

```markdown
## Drift Log

**Checked:** 2026-02-02 14:30 UTC
**Result:** light_drift | heavy_drift | no_drift

### Changes Detected
| File | Change Type | Action Taken |
|------|-------------|--------------|
| `src/service.py` | lines shifted +15 | AUTO-FIX: updated references |
| `src/utils.py` | function renamed | AUTO-FIX: updated to new name |

### References Updated
- Task 1: `service.py:45-60` → `service.py:60-75`
- Task 2: `get_user()` → `fetch_user()`
```

---

## Implementation Plan

### Research Sources
- [Spec-driven development](https://www.thoughtworks.com/insights/blog/agile-engineering-practices/spec-driven-development-unpacking-2025-new-engineering-practices) — drift detection patterns
- [Semcheck](https://labs.rejot.dev/blog/2025-08-22_spec-driven-development/) — pre-commit spec validation

### Task 1: Remove SKIP exception and add drift classification

**Type:** prompt
**Files:**
- Modify: `.claude/agents/planner.md:97-145`

**Changes:**
1. Delete line 141 (`SKIP allowed: Trivial changes...`)
2. Add drift classification table after Phase 1.5
3. Add AUTO-FIX logic for light drift
4. Add COUNCIL escalation for heavy drift

**Acceptance:**
- [ ] No "SKIP" mention in Phase 1.7
- [ ] Drift classification table present
- [ ] Light drift → auto-fix instructions
- [ ] Heavy drift → council escalation template

### Task 2: Add Drift Log output format

**Type:** prompt
**Files:**
- Modify: `.claude/agents/planner.md:429-451`

**Changes:**
1. Add `## Drift Log` section template
2. Update output yaml to include `drift_action: none | auto_fix | council_escalation`
3. Add `drift_log_added: true | false`

**Acceptance:**
- [ ] Drift Log format documented
- [ ] Output includes drift_action field

### Task 3: Update planner SKILL.md

**Type:** prompt
**Files:**
- Modify: `.claude/skills/planner/SKILL.md:40-76`

**Changes:**
1. Remove mention of skip for trivial tasks
2. Update "What Planner Does" to mention drift classification
3. Update Output section with new fields

**Acceptance:**
- [ ] No skip mentions
- [ ] Drift classification documented
- [ ] Output format matches agent

### Task 4: Add heavy_drift to escalation.md

**Type:** prompt
**Files:**
- Modify: `.claude/skills/autopilot/escalation.md:5-15`

**Changes:**
1. Add `heavy_drift` to Limits table
2. Add to Decision Tree
3. Add Council Escalation template for heavy_drift

**Acceptance:**
- [ ] heavy_drift in Limits table
- [ ] Decision tree includes drift path
- [ ] Escalation template present

### Task 5: Sync template files

**Type:** sync
**Files:**
- Modify: `template/.claude/agents/planner.md`
- Modify: `template/.claude/skills/planner/SKILL.md`
- Modify: `template/.claude/skills/autopilot/escalation.md`

**Changes:**
Copy updated content from root `.claude/` to `template/.claude/`

**Acceptance:**
- [ ] All 3 template files match root versions
- [ ] diff shows no differences after sync

### Execution Order

```
Task 1 → Task 2 → Task 3 → Task 4 → Task 5
         (sequential — each builds on previous)
```

---

## Definition of Done

### Functional
- [ ] Planner ALWAYS runs drift check (no skip for trivial)
- [ ] Light drift triggers AUTO-FIX with spec updates
- [ ] Heavy drift triggers COUNCIL escalation
- [ ] Drift Log section added to spec after check
- [ ] Output includes drift_action field

### Technical
- [ ] All 6 files updated
- [ ] Template files in sync with root
- [ ] No "SKIP allowed" in any file

---

## Autopilot Log

<!-- Autopilot will fill this section -->
