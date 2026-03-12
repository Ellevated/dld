# Tech: [TECH-075] Template-Root Sync Enforcement System

**Status:** done | **Priority:** P0 | **Date:** 2026-02-02

## Why

Root `.claude/` и `scripts/` отстают от template. Критичные файлы:
- autopilot v3.4 в root vs v3.5 с Ralph Mode в template (-40 строк!)
- task-loop.md отсутствует в root
- setup-mcp.sh и ralph-autopilot.sh отсутствуют в root

**Причина:** Нет автоматического enforcement. Правило `template-sync.md` существует но лежит мёртвым грузом — агенты его не читают при редактировании.

## Context

**Текущий дрифт (template newer than root):**

| File | Template | Root | Diff |
|------|----------|------|------|
| `.claude/skills/autopilot/SKILL.md` | 247 | 207 | -40 строк! |
| `.claude/skills/autopilot/finishing.md` | 164 | 153 | -11 строк |
| `.claude/skills/autopilot/subagent-dispatch.md` | 202 | 200 | -2 строки |
| `.claude/skills/autopilot/task-loop.md` | exists | **MISSING** | — |
| `scripts/setup-mcp.sh` | exists | **MISSING** | — |
| `scripts/ralph-autopilot.sh` | exists | **MISSING** | — |

**Sync Zones (должны быть синхронизированы):**

| Zone | Direction | Notes |
|------|-----------|-------|
| `.claude/` | Bidirectional | Main sync zone |
| `scripts/*.sh` | Bidirectional | Utility scripts |

**НЕ sync zones (ожидаемые расхождения):**

| Zone | Reason |
|------|--------|
| `docs/` | DLD-specific documentation |
| `ai/` content | DLD backlog/specs (only structure syncs) |
| `CLAUDE.md` | Template=placeholder, root=project-specific |
| `.claude/rules/localization.md` | Template=placeholder, root=Russian |

---

## Scope

**In scope:**
1. **Срочный sync:** template → root для всех устаревших файлов
2. **Расширить check-sync.sh:** добавить проверку scripts/
3. **Hook enforcement:** pre_edit.py — при редактировании sync zones напоминание
4. **Planner enforcement:** автоматически добавлять Sync Task если в scope есть sync zones

**Out of scope:**
- CI enforcement (слишком тяжело)
- Автоматический rsync (опасно, теряет кастомизации)
- Sync ai/ content (только структура)

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses affected files?

- [x] `autopilot/SKILL.md` → используется `/autopilot` skill
- [x] `task-loop.md` → referenced in SKILL.md (missing = broken reference!)
- [x] `setup-mcp.sh` → referenced in template/CLAUDE.md, README
- [x] `ralph-autopilot.sh` → referenced in SKILL.md Ralph Mode

### Step 2: DOWN — what do they depend on?

- [x] check-sync.sh → standalone script
- [x] pre_edit.py → utils.py (existing)
- [x] planner.md → standalone agent

### Step 3: BY TERM — grep affected areas

- [x] `grep -rn "task-loop" .claude/` → found in SKILL.md, subagent-dispatch.md
- [x] `grep -rn "ralph" .claude/` → SKILL.md references ralph-autopilot.sh
- [x] `grep -rn "setup-mcp" .` → README.md, template/CLAUDE.md

### Step 4: CHECKLIST

- [x] All sync files identified
- [x] Enforcement points identified (hook, planner)

### Verification

- [x] After implementation: `./scripts/check-sync.sh` shows no unexpected diffs

---

## Allowed Files

**ONLY these files may be modified during implementation:**

### Part 1: Sync (copy from template)
1. `.claude/skills/autopilot/SKILL.md` — REPLACE with template version
2. `.claude/skills/autopilot/finishing.md` — REPLACE with template version
3. `.claude/skills/autopilot/subagent-dispatch.md` — REPLACE with template version
4. `.claude/skills/autopilot/task-loop.md` — **CREATE** (copy from template)
5. `scripts/setup-mcp.sh` — **CREATE** (copy from template)
6. `scripts/ralph-autopilot.sh` — **CREATE** (copy from template)

### Part 2: Enforcement mechanisms
7. `scripts/check-sync.sh` — extend to check scripts/
8. `.claude/hooks/pre_edit.py` — add sync zone reminder
9. `.claude/agents/planner.md` — add automatic Sync Task check
10. `template/.claude/agents/planner.md` — sync planner changes back to template

### Part 3: Documentation
11. `.claude/CUSTOMIZATIONS.md` — update Last Sync date

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Design

### Sync Zone Detection

```python
SYNC_ZONES = [
    ".claude/",      # Skills, agents, hooks, rules
    "scripts/",      # Utility scripts
]

EXCLUDE_FROM_SYNC = [
    ".claude/rules/localization.md",    # DLD-specific (Russian)
    ".claude/rules/template-sync.md",   # DLD meta-rule
    ".claude/rules/git-local-folders.md", # DLD-specific
    ".claude/CUSTOMIZATIONS.md",        # DLD tracking file
    ".claude/settings.local.json",      # Local settings
]
```

### Hook Logic (pre_edit.py)

```python
def check_sync_zone(file_path: str) -> str | None:
    """Returns reminder if file is in sync zone."""
    for zone in SYNC_ZONES:
        if file_path.startswith(zone):
            # Check if file exists in template
            template_path = f"template/{file_path}"
            if os.path.exists(template_path):
                if file_path not in EXCLUDE_FROM_SYNC:
                    return f"⚠️ SYNC ZONE: {file_path}\nRemember to sync with template/ after changes."
    return None
```

### Planner Check

Add to Phase 1.5 (after Drift Check):

```markdown
### Phase 1.6: Sync Zone Check

If ANY file in Allowed Files is in sync zone:
1. Check if template/ has same file
2. If yes AND file will be modified:
   - Add "Sync to template" task at end of Implementation Plan
   - OR add "Sync from template" task if template is newer

**Sync zones:** `.claude/`, `scripts/`
**Exclude:** See CUSTOMIZATIONS.md
```

---

## Implementation Plan

### Research Sources
- [Git pre-commit hooks](https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks) — hook patterns
- [Python pathlib](https://docs.python.org/3/library/pathlib.html) — path matching

### Task 1: Sync autopilot files from template

**Type:** sync
**Files:**
- replace: `.claude/skills/autopilot/SKILL.md`
- replace: `.claude/skills/autopilot/finishing.md`
- replace: `.claude/skills/autopilot/subagent-dispatch.md`
- create: `.claude/skills/autopilot/task-loop.md`

**Steps:**
```bash
cp template/.claude/skills/autopilot/SKILL.md .claude/skills/autopilot/
cp template/.claude/skills/autopilot/finishing.md .claude/skills/autopilot/
cp template/.claude/skills/autopilot/subagent-dispatch.md .claude/skills/autopilot/
cp template/.claude/skills/autopilot/task-loop.md .claude/skills/autopilot/
```

**Acceptance:**
- [ ] `diff .claude/skills/autopilot/SKILL.md template/.claude/skills/autopilot/SKILL.md` = empty
- [ ] task-loop.md exists in root

### Task 2: Copy missing scripts

**Type:** sync
**Files:**
- create: `scripts/setup-mcp.sh`
- create: `scripts/ralph-autopilot.sh`

**Steps:**
```bash
cp template/scripts/setup-mcp.sh scripts/
cp template/scripts/ralph-autopilot.sh scripts/
chmod +x scripts/setup-mcp.sh scripts/ralph-autopilot.sh
```

**Acceptance:**
- [ ] Both scripts exist and are executable
- [ ] `diff scripts/setup-mcp.sh template/scripts/setup-mcp.sh` = empty

### Task 3: Extend check-sync.sh for scripts/

**Type:** code
**Files:**
- modify: `scripts/check-sync.sh`

**Changes:**
Add scripts/ checking after .claude/ checking:

```bash
echo "=== Scripts sync check ==="
for f in template/scripts/*.sh; do
  root_f="${f#template/}"
  if [ ! -f "$root_f" ]; then
    echo "MISSING in root: $root_f"
  else
    if ! diff -q "$f" "$root_f" > /dev/null 2>&1; then
      t_lines=$(wc -l < "$f" | tr -d ' ')
      r_lines=$(wc -l < "$root_f" | tr -d ' ')
      echo "$root_f: template=$t_lines root=$r_lines"
    fi
  fi
done
```

**Acceptance:**
- [ ] `./scripts/check-sync.sh` shows scripts/ section
- [ ] Missing scripts are reported

### Task 4: Add sync zone reminder to pre_edit.py

**Type:** code
**Files:**
- modify: `.claude/hooks/pre_edit.py`

**Changes:**
Add function `check_sync_zone()` and call it in `validate_edit()`.
If file is in sync zone, add warning to output (don't block, just remind).

**Acceptance:**
- [ ] Editing `.claude/agents/planner.md` shows sync reminder
- [ ] Editing `.claude/rules/localization.md` does NOT show reminder (excluded)

### Task 5: Add Sync Zone Check to planner.md

**Type:** prompt
**Files:**
- modify: `.claude/agents/planner.md`

**Changes:**
Add Phase 1.6 "Sync Zone Check" after Drift Check.
If Allowed Files contain sync zone files → add sync task to plan.

**Acceptance:**
- [ ] Planner mentions sync zone check
- [ ] Output format includes `sync_task_added: true | false`

### Task 6: Sync planner changes to template

**Type:** sync
**Files:**
- modify: `template/.claude/agents/planner.md`

**Steps:**
Copy root planner.md to template after Task 5 changes.

**Acceptance:**
- [ ] `diff .claude/agents/planner.md template/.claude/agents/planner.md` = empty

### Task 7: Update CUSTOMIZATIONS.md

**Type:** docs
**Files:**
- modify: `.claude/CUSTOMIZATIONS.md`

**Changes:**
Update "Last Sync" table with current date and TECH-075.

**Acceptance:**
- [ ] Last Sync shows 2026-02-02

### Execution Order

```
Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6 → Task 7
         (sequential — each builds on previous)
```

---

## Definition of Done

### Functional
- [ ] Root autopilot matches template (v3.5 with Ralph Mode)
- [ ] task-loop.md exists in root
- [ ] setup-mcp.sh and ralph-autopilot.sh exist in root
- [ ] check-sync.sh reports scripts/ divergence
- [ ] pre_edit.py shows sync zone reminders
- [ ] Planner auto-adds sync tasks for sync zone files

### Technical
- [ ] All 11 files updated per Allowed Files list
- [ ] `./scripts/check-sync.sh` shows clean (no unexpected diffs)
- [ ] No regressions in existing functionality

### Process
- [ ] Future edits to sync zones get reminder
- [ ] Future plans with sync zone files get sync task

---

## Autopilot Log

**Executed:** 2026-02-02
**Branch:** tech/TECH-075
**Commits:** d5caa62

### Tasks Completed
1. ✅ Sync autopilot files from template (SKILL.md, finishing.md, subagent-dispatch.md)
2. ✅ Copy missing scripts (setup-mcp.sh, ralph-autopilot.sh)
3. ✅ Extend check-sync.sh for scripts/
4. ✅ Add sync zone reminder to pre_edit.py
5. ✅ Add Sync Zone Check to planner.md (Phase 1.6)
6. ✅ Sync planner changes to template
7. ✅ Update CUSTOMIZATIONS.md

### Tests
- 92 passed, 0 failed

### Definition of Done
- [x] Root autopilot matches template (v3.5 with Ralph Mode)
- [x] task-loop.md exists in root
- [x] setup-mcp.sh and ralph-autopilot.sh exist in root
- [x] check-sync.sh reports scripts/ divergence
- [x] pre_edit.py shows sync zone reminders
- [x] Planner auto-adds sync tasks for sync zone files
