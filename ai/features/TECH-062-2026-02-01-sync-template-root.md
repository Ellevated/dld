# Tech: [TECH-062] Sync template/.claude with root .claude

**Status:** done | **Priority:** P1 | **Date:** 2026-02-01

## Why

Code divergence between `template/.claude/` and root `.claude/` causes confusion and lost improvements. Changes are made chaotically in both places without synchronization process.

**Current state:**
- 4 files improved in root but not in template (spark, debugger, skill-writer)
- 4 files improved in template but not in root (reflect, scout)
- 3 files exist only in root (DLD customizations)

## Context

### Two-Layer Model

```
template/.claude/     ← UNIVERSAL template (for all DLD users)
       ↓
   selective sync     ← Cherry-pick best practices (NOT rsync --delete!)
       ↓
.claude/              ← CUSTOMIZED for DLD project development
                        (template + DLD-specific rules)
```

### Key Insight

**Sync ≠ Copy.** Sync means:
1. Review what changed in template
2. Cherry-pick improvements that apply to root
3. Keep DLD-specific customizations intact

### Current Divergence Analysis

**Only in root (DLD customizations — keep):**
| File | Purpose |
|------|---------|
| `rules/localization.md` | Russian skill triggers |
| `settings.local.json` | Local dev settings |
| `skills/scaffold/SKILL.md` | Skill generator |

**Root newer than template (port to template):**
| File | Diff | Improvement |
|------|------|-------------|
| `skills/spark/SKILL.md` | +91 | Mandatory Scout Research Protocol |
| `agents/spark.md` | +34 | Detailed phases |
| `skills/skill-writer/SKILL.md` | +23 | Enhanced format |
| `agents/debugger.md` | +22 | Better debugging flow |

**Template newer than root (port to root):**
| File | Diff | Improvement |
|------|------|-------------|
| `skills/reflect/SKILL.md` | -36 | Better scope/targets format |
| `skills/scout/SKILL.md` | -16 | New Exa tools (deep_researcher) |
| `agents/scout.md` | -7 | Updated tools list |
| `hooks/pre_edit.py` | -6 | Hook improvements |

---

## Scope

**In scope:**
- Define clear sync workflow (template-first for universal, root-only for custom)
- One-time sync: port improvements both directions
- Create tracking file for customizations
- Document the process

**Out of scope:**
- rsync --delete (destructive, loses customizations)
- CI enforcement of identical files
- Changing skill/agent functionality

---

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `template/.claude/skills/spark/SKILL.md` | modify | Port Scout Protocol from root |
| 2 | `template/.claude/agents/spark.md` | modify | Port phase details from root |
| 3 | `template/.claude/skills/skill-writer/SKILL.md` | modify | Port improvements from root |
| 4 | `template/.claude/agents/debugger.md` | modify | Port improvements from root |
| 5 | `.claude/skills/reflect/SKILL.md` | modify | Port from template |
| 6 | `.claude/skills/scout/SKILL.md` | modify | Port new Exa tools from template |
| 7 | `.claude/agents/scout.md` | modify | Port from template |
| 8 | `.claude/hooks/pre_edit.py` | modify | Port from template |
| 9 | `.claude/CUSTOMIZATIONS.md` | create | Track DLD-specific files |
| 10 | `CONTRIBUTING.md` | modify | Document sync workflow |

---

## Design

### Customizations Tracking

Create `.claude/CUSTOMIZATIONS.md`:
```markdown
# DLD Customizations

Files that exist ONLY in root (not in template):

| File | Purpose | Sync? |
|------|---------|-------|
| `rules/localization.md` | Russian triggers | Never |
| `settings.local.json` | Local dev settings | Never |
| `skills/scaffold/SKILL.md` | Skill generator | Consider adding to template |

## Sync Workflow

When improving DLD framework:
1. Make change in `template/.claude/` first
2. Review if change applies to root
3. If yes → cherry-pick to `.claude/`
4. If no → document why in this file

When adding DLD-specific customization:
1. Add only to `.claude/`
2. Document in this file
```

### Sync Workflow (No CI Enforcement)

```
Улучшение DLD-framework:
  1. Edit template/.claude/
  2. Commit: "feat(template): description"
  3. Review: does this apply to our root?
  4. If yes: cherry-pick to .claude/
  5. Commit: "chore: sync from template"

Кастомизация под DLD-проект:
  1. Edit .claude/ only
  2. Add to CUSTOMIZATIONS.md
  3. Commit: "feat(dld): description"
```

### Manual Review Script (Optional)

```bash
# scripts/check-sync.sh
#!/bin/bash
# Shows divergence for review (does NOT enforce)

echo "=== Files only in root (customizations) ==="
comm -23 <(find .claude -type f -name "*.md" -o -name "*.py" | sed 's|^.claude/||' | sort) \
         <(find template/.claude -type f -name "*.md" -o -name "*.py" | sed 's|^template/.claude/||' | sort)

echo ""
echo "=== Files with different line counts ==="
for f in $(find template/.claude -type f \( -name "*.md" -o -name "*.py" \)); do
  root_f="${f#template/}"
  if [ -f "$root_f" ]; then
    t_lines=$(wc -l < "$f")
    r_lines=$(wc -l < "$root_f")
    if [ "$t_lines" != "$r_lines" ]; then
      echo "$root_f: template=$t_lines root=$r_lines"
    fi
  fi
done

echo ""
echo "Review divergence and sync manually if needed."
```

---

## Implementation Plan

### Task 1: Port root improvements → template

**Files:**
- Modify: `template/.claude/skills/spark/SKILL.md`
- Modify: `template/.claude/agents/spark.md`
- Modify: `template/.claude/skills/skill-writer/SKILL.md`
- Modify: `template/.claude/agents/debugger.md`

**Steps:**
1. Diff each file
2. Identify universal improvements (not DLD-specific)
3. Port to template
4. Verify template still works for generic projects

**Acceptance:**
- [ ] Scout Protocol in template spark
- [ ] All universal improvements ported

### Task 2: Port template improvements → root

**Files:**
- Modify: `.claude/skills/reflect/SKILL.md`
- Modify: `.claude/skills/scout/SKILL.md`
- Modify: `.claude/agents/scout.md`
- Modify: `.claude/hooks/pre_edit.py`

**Steps:**
1. Diff each file
2. Port template improvements to root
3. Keep any DLD-specific parts in root

**Acceptance:**
- [ ] New Exa tools in root scout
- [ ] Reflect improvements ported

### Task 3: Create CUSTOMIZATIONS.md

**Files:**
- Create: `.claude/CUSTOMIZATIONS.md`

**Steps:**
1. List all root-only files
2. Document purpose of each
3. Mark sync policy (never/consider)

**Acceptance:**
- [ ] All customizations documented

### Task 4: Create check-sync script

**Files:**
- Create: `scripts/check-sync.sh`

**Steps:**
1. Create script from Design section
2. Make executable
3. Add to Makefile as `make check-sync`

**Acceptance:**
- [ ] Script shows divergence
- [ ] Does NOT fail CI (informational only)

### Task 5: Document in CONTRIBUTING.md

**Files:**
- Modify: `CONTRIBUTING.md`

**Steps:**
1. Add "Template vs Root" section
2. Explain two-layer model
3. Document sync workflow

**Acceptance:**
- [ ] Workflow documented

### Execution Order

Task 1 → Task 2 (можно параллельно) → Task 3 → Task 4 → Task 5

---

## Definition of Done

### Functional
- [ ] All current improvements synced both directions
- [ ] Customizations documented
- [ ] Workflow documented

### Technical
- [ ] No destructive rsync --delete anywhere
- [ ] check-sync.sh is informational, not blocking
- [ ] settings.local.json in .gitignore

### Process
- [ ] Future changes follow documented workflow

---

## Autopilot Log

*(Filled by Autopilot during execution)*
