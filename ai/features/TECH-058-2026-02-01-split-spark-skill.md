# Tech: [TECH-058] Split spark/SKILL.md Into Modules

**Status:** done | **Priority:** P3 | **Date:** 2026-02-01

## Why

`spark/SKILL.md` is 736 lines — violates DLD's own 400 LOC rule (skill-writer allows 500, still over). This undermines credibility and makes the file hard to maintain.

## Context

Current spark/SKILL.md is monolithic. Following skill-writer principles:
- **Orchestrator pattern** — Spark dispatches Scout, coordinates flow
- **Single source of truth** — no duplication of completion logic
- **Self-contained modes** — feature/bug modes include their own research templates
- **Minimum files per pass** — 3 files: SKILL.md → mode.md → completion.md

---

## Scope

**In scope:**
- Split spark/SKILL.md into 4 modular files
- Each module under 500 LOC (skill-writer limit)
- Self-contained feature/bug modes with embedded research
- Shared completion.md (no duplication)

**Out of scope:**
- Changing spark behavior
- Adding new modes
- Rewriting prompts from scratch

---

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `template/.claude/skills/spark/SKILL.md` | modify | Reduce to orchestrator |
| 2 | `template/.claude/skills/spark/feature-mode.md` | create | Feature flow + research |
| 3 | `template/.claude/skills/spark/bug-mode.md` | create | Bug flow + research |
| 4 | `template/.claude/skills/spark/completion.md` | create | Shared completion logic |

**New files allowed:**
- `template/.claude/skills/spark/feature-mode.md`
- `template/.claude/skills/spark/bug-mode.md`
- `template/.claude/skills/spark/completion.md`

---

## Design

### New Structure

```
template/.claude/skills/spark/
├── SKILL.md          # ~120 LOC — Orchestrator (mode detection + dispatch)
├── feature-mode.md   # ~350 LOC — Socratic dialogue + research + template
├── bug-mode.md       # ~300 LOC — 5 Whys + research + template
└── completion.md     # ~100 LOC — ID protocol, checklists, handoff (SHARED)
```

### Flow (3 files per pass)

```
Feature: SKILL.md → feature-mode.md → completion.md
Bug:     SKILL.md → bug-mode.md → completion.md
```

### Content Distribution

#### SKILL.md (~120 LOC) — Orchestrator
- YAML frontmatter with semantic triggers
- When to Use / Don't Use
- Principles (8 items)
- Mode Detection table
- Module reference table
- STRICT RULES (read-only mode)
- Output format

#### feature-mode.md (~350 LOC) — Self-contained Feature Flow
From current SKILL.md:
- Socratic Dialogue (lines 63-84)
- Feature research template (lines 327-338)
- Prompt/Agent change template (lines 353-364)
- Architecture decision template (lines 366-377)
- Deep research (lines 388-408)
- Scout Results Integration (lines 411-417)
- Feature spec template (lines 477-573, feature parts)
- UI Event Completeness (lines 286-299)
- Flow Coverage Matrix (lines 461-476)

#### bug-mode.md (~300 LOC) — Self-contained Bug Flow
From current SKILL.md:
- 5 Whys + Systematic Debugging (lines 85-231)
- Bug research template (lines 340-351)
- Deep research (lines 388-408)
- Scout Results Integration (lines 411-417)
- Bug spec template (lines 140-194)
- Impact Tree Analysis (lines 437-454)
- Exact Paths Required (lines 201-231)

#### completion.md (~100 LOC) — Shared (Single Source of Truth)
From current SKILL.md:
- ID Determination Protocol (lines 421-435)
- Pre-Completion Checklist (lines 574-587)
- Backlog Entry Verification (lines 589-608)
- Status Sync Self-Check (lines 610-634)
- Backlog Format (lines 636-658)
- Auto-Commit (lines 660-683)
- Auto-Handoff to Autopilot (lines 685-718)

---

## Implementation Plan

### Task 1: Create feature-mode.md

**Files:** create `template/.claude/skills/spark/feature-mode.md`

**Content:**
1. Header with purpose
2. Socratic Dialogue section
3. Research templates (Feature, Prompt/Agent, Architecture)
4. Deep research + Results integration
5. Feature spec template
6. UI Event Completeness
7. Flow Coverage Matrix

**Acceptance:**
- [ ] feature-mode.md < 500 LOC
- [ ] All feature logic preserved
- [ ] Research templates embedded (not referenced)

### Task 2: Create bug-mode.md

**Files:** create `template/.claude/skills/spark/bug-mode.md`

**Content:**
1. Header with purpose
2. 5 Whys methodology (Reproduce → Isolate → Root Cause)
3. Bug research template
4. Deep research + Results integration
5. Bug spec template with Impact Tree
6. Exact Paths Required rule

**Acceptance:**
- [ ] bug-mode.md < 500 LOC
- [ ] 5 Whys preserved intact (protective section)
- [ ] Research templates embedded

### Task 3: Create completion.md

**Files:** create `template/.claude/skills/spark/completion.md`

**Content:**
1. Header: "Read this AFTER creating spec"
2. ID Determination Protocol
3. Pre-Completion Checklist (BLOCKING)
4. Backlog Entry Verification
5. Status Sync Self-Check
6. Backlog Format (STRICT)
7. Auto-Commit
8. Auto-Handoff to Autopilot

**Acceptance:**
- [ ] completion.md < 200 LOC
- [ ] All checklists preserved (protective sections)
- [ ] No mode-specific content

### Task 4: Refactor SKILL.md to Orchestrator

**Files:** modify `template/.claude/skills/spark/SKILL.md`

**Content to KEEP:**
1. YAML frontmatter (semantic triggers)
2. When to Use / Don't Use
3. Principles
4. Mode Detection
5. STRICT RULES
6. Output format

**Content to REMOVE (moved to modules):**
- Socratic Dialogue → feature-mode.md
- 5 Whys → bug-mode.md
- All research templates → respective modes
- Spec templates → respective modes
- Completion logic → completion.md

**ADD:**
```markdown
## Modules

| Module | When to Read | Content |
|--------|--------------|---------|
| `feature-mode.md` | Mode = Feature | Dialogue + research + template |
| `bug-mode.md` | Mode = Bug | 5 Whys + research + template |
| `completion.md` | After spec created | ID, backlog, commit, handoff |
```

**Acceptance:**
- [ ] SKILL.md < 200 LOC
- [ ] Clear dispatch to modules
- [ ] No duplicated content

### Task 5: Verify LOC Limits

**Commands:**
```bash
wc -l template/.claude/skills/spark/*.md
```

**Acceptance:**
- [ ] SKILL.md < 200 LOC
- [ ] feature-mode.md < 500 LOC
- [ ] bug-mode.md < 500 LOC
- [ ] completion.md < 200 LOC
- [ ] Total < 1400 LOC (was 736)

### Execution Order

```
Task 1 (feature-mode) → Task 2 (bug-mode) → Task 3 (completion) → Task 4 (SKILL.md) → Task 5 (verify)
```

---

## LOC Targets

| File | Current | Target | Max |
|------|---------|--------|-----|
| SKILL.md | 736 | ~120 | 200 |
| feature-mode.md | — | ~350 | 500 |
| bug-mode.md | — | ~300 | 500 |
| completion.md | — | ~100 | 200 |
| **Total** | 736 | ~870 | 1400 |

Note: Total increases slightly due to module headers, but each file is maintainable.

---

## Skill-Writer Compliance

| Rule | Status |
|------|--------|
| Skills < 500 LOC | All files < 500 |
| Single source of truth | completion.md shared |
| Preservation Checklist | 5 Whys, checklists intact |
| Orchestrator pattern | SKILL.md dispatches modes |

---

## Definition of Done

### Functional
- [ ] All spark functionality preserved
- [ ] Feature mode works: SKILL.md → feature-mode.md → completion.md
- [ ] Bug mode works: SKILL.md → bug-mode.md → completion.md

### Technical
- [ ] Every file < 500 LOC (skill-writer limit)
- [ ] Main SKILL.md is orchestrator only
- [ ] No duplicated content between modules
- [ ] No circular references

### Documentation
- [ ] Each module has clear purpose header
- [ ] Module table in SKILL.md

---

## Autopilot Log

### Task 1/6: Create feature-mode.md — 2026-02-02 12:39
- Coder: completed (1 file: feature-mode.md, 347 LOC)
- Tester: skipped (no tests for .md)
- Spec Reviewer: approved (all feature logic preserved)

### Task 2/6: Create bug-mode.md — 2026-02-02 12:39
- Coder: completed (1 file: bug-mode.md, 317 LOC)
- Tester: skipped (no tests for .md)
- Spec Reviewer: approved (5 Whys preserved intact)

### Task 3/6: Create completion.md — 2026-02-02 12:39
- Coder: completed (1 file: completion.md, 199 LOC)
- Tester: skipped (no tests for .md)
- Spec Reviewer: approved (all checklists preserved)

### Task 4/6: Refactor SKILL.md — 2026-02-02 12:43
- Coder: completed (1 file: SKILL.md, 736→152 LOC)
- Tester: skipped (no tests for .md)
- Spec Reviewer: approved (orchestrator pattern implemented)

### Task 5/6: Verify LOC Limits — 2026-02-02 12:44
- Verification: PASSED
  - SKILL.md: 152 LOC (< 200) ✓
  - feature-mode.md: 347 LOC (< 500) ✓
  - bug-mode.md: 317 LOC (< 500) ✓
  - completion.md: 199 LOC (< 200) ✓
  - Total: 1015 LOC (< 1400) ✓

### Task 6/6: Sync to root .claude/ — 2026-02-02 12:44
- Sync: completed (4 files copied)
- Diff: no differences ✓

### Final — 2026-02-02 12:46
- Commit: 451a45b
- Branch: tech/TECH-058
- Status: done
