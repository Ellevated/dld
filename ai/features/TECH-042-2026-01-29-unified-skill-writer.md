# TECH-042: Unified skill-writer (scaffold + claude-md-writer)

**Status:** done | **Priority:** P1 | **Date:** 2026-01-29

## Why

Нарушение SSOT: два скила (scaffold и claude-md-writer) оба на выходе дают "готовый промпт" для agents/skills. Дублирование знаний:
- Оба знают про frontmatter
- Оба знают про структуру секций
- Оба умеют "писать промпт"

Разница только в режиме: CREATE vs UPDATE. Это один инструмент с двумя режимами, не два инструмента.

## Context

**Research (Exa, Jan 2026):**

| Источник | Паттерн | Применение |
|----------|---------|------------|
| Meta-Prompting (comet.com) | LLMs optimize prompts via eval loops | Three-Expert как eval |
| Prompt-Loop Automation (emergentmind.com) | generation → evaluation → refinement | CREATE и UPDATE — один цикл |
| Self-Improving Agents | improvement history tracking | Логирование изменений |
| Context Engineering (Anthropic) | context is finite resource | Лимиты на строки |

**Зависимости найдены:**

| Файл | Упоминает | Частота |
|------|-----------|---------|
| `reflect/SKILL.md` | claude-md-writer | 8 раз |
| `CLAUDE.md` | claude-md-writer, scaffold | 2 раза |
| `docs/15-skills-setup.md` | claude-md-writer | 3 раза |
| `autopilot/SKILL.md` | scaffold | 1 раз |

---

## Scope

**In scope:**
- Объединить scaffold + claude-md-writer → skill-writer
- CREATE mode (новые agents/skills)
- UPDATE mode (оптимизация существующих + CLAUDE.md + rules)
- Research phase через Exa
- Requirements gathering в обоих режимах
- Three-Expert Gate в обоих режимах
- Обновить все зависимости

**Out of scope:**
- Изменение reflect логики (только handoff target)
- Изменение autopilot (только упоминание)

## Impact Tree Analysis

### Step 1: UP — who uses?
- `scaffold` вызывается пользователем через `/scaffold`
- `claude-md-writer` вызывается из reflect и напрямую

### Step 2: DOWN — what depends on?
- reflect → handoff к claude-md-writer
- autopilot → упоминает scaffold

### Step 3: BY TERM
```
grep -rn "scaffold" . → 8 results (template + docs)
grep -rn "claude-md-writer" . → 15 results (template + docs)
```

### Verification
- All found files in Allowed Files ✓

## Allowed Files

**ONLY these files may be modified:**

### Main project (.claude/)
1. `.claude/skills/skill-writer/SKILL.md` — CREATE (новый объединённый)
2. `.claude/skills/scaffold/SKILL.md` — DELETE
3. `.claude/skills/claude-md-writer/SKILL.md` — DELETE
4. `.claude/skills/reflect/SKILL.md` — UPDATE (handoff → skill-writer)
5. `.claude/skills/autopilot/SKILL.md` — UPDATE (/scaffold → /skill-writer)

### Template (template/.claude/)
6. `template/.claude/skills/skill-writer/SKILL.md` — CREATE
7. `template/.claude/skills/scaffold/SKILL.md` — DELETE
8. `template/.claude/skills/claude-md-writer/SKILL.md` — DELETE
9. `template/.claude/skills/reflect/SKILL.md` — UPDATE
10. `template/.claude/skills/autopilot/SKILL.md` — UPDATE

### Documentation
11. `template/CLAUDE.md` — UPDATE (Skills table)
12. `docs/15-skills-setup.md` — UPDATE

**FORBIDDEN:** All other files.

## Environment

nodejs: false
docker: false
database: false

## Design

### Unified skill-writer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      skill-writer                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  РЕЖИМ 1: CREATE                    РЕЖИМ 2: UPDATE         │
│  ─────────────────                  ─────────────────        │
│  "skill-writer create wrapper X"    "skill-writer update Y"  │
│  "skill-writer create agent X"      "/skill-writer" (reflect)│
│  "skill-writer create skill X"                               │
│                                                              │
│  PHASE 1: REQUIREMENTS ──────────────────────────────────   │
│  CREATE: what, who calls, tools, model                       │
│  UPDATE: what to change, why, constraints                    │
│  If not explicit → ASK                                       │
│                           ↓                                  │
│  PHASE 2: RESEARCH (Exa) ────────────────────────────────   │
│  CREATE: similar skills, patterns for type                   │
│  UPDATE: best practices, alternatives                        │
│  Max 3 Exa calls. Skip if trivial.                           │
│                           ↓                                  │
│  PHASE 3: DRAFT ─────────────────────────────────────────   │
│  CREATE: determine type, generate structure, fill content    │
│  UPDATE: read current, identify changes, draft new           │
│                           ↓                                  │
│  PHASE 4: THREE-EXPERT GATE ─────────────────────────────   │
│  Karpathy (redundancy) + Sutskever (constraints) + Murati    │
│  For each line: "If I remove, will output worsen?"           │
│                           ↓                                  │
│  PHASE 5: VALIDATE ──────────────────────────────────────   │
│  Line limits, structure, no duplication, frontmatter         │
│                           ↓                                  │
│  PHASE 6: WRITE ─────────────────────────────────────────   │
│  Write/Update file, report changes                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Unified Scope

| Target | Path | CREATE | UPDATE | Limits |
|--------|------|--------|--------|--------|
| Foundation | `CLAUDE.md` | ✗ | ✓ | < 200 lines |
| Rules | `.claude/rules/*.md` | ✗ | ✓ | < 500 lines |
| Agents | `.claude/agents/*.md` | ✓ | ✓ | Concise |
| Skills | `.claude/skills/*/SKILL.md` | ✓ | ✓ | < 500 lines |

### Merged Knowledge

**От scaffold:**
- Skill Types: wrapper | orchestrator | standalone
- Decision Tree
- Templates (agent, wrapper, orchestrator)
- Validation rules (naming, structure, model, tools)

**От claude-md-writer:**
- Three-Expert Gate
- Documentation Hierarchy
- Prompt Quality Principles
- Anti-Patterns
- Line count limits

**Новое:**
- Requirements gathering (оба режима)
- Research phase (Exa)
- Unified 6-phase process

## Implementation Plan

### Task 1: Create skill-writer/SKILL.md

**Type:** code
**Files:**
- Create: `.claude/skills/skill-writer/SKILL.md`

**Content includes:**
- Frontmatter (name, description, model: opus)
- Activation triggers (create/update modes)
- Scope table (CLAUDE.md, rules, agents, skills)
- 6-phase process
- CREATE mode specifics (types, decision tree, templates)
- UPDATE mode specifics (from reflect, optimization)
- Requirements gathering (both modes)
- Research phase (Exa integration)
- Three-Expert Gate (full)
- Prompt Quality Principles
- Validation rules
- Output format

**Acceptance:**
- [ ] Both CREATE and UPDATE modes documented
- [ ] Requirements gathering in both modes
- [ ] Research phase with Exa
- [ ] Three-Expert Gate embedded
- [ ] All scaffold knowledge preserved
- [ ] All claude-md-writer knowledge preserved
- [ ] < 400 lines (compressed via Three-Expert)

### Task 2: Update reflect/SKILL.md

**Type:** code
**Files:**
- Modify: `.claude/skills/reflect/SKILL.md`

**Changes:**
- Replace all "claude-md-writer" → "skill-writer"
- Update handoff instructions

**Acceptance:**
- [ ] grep "claude-md-writer" = 0 results
- [ ] Handoff points to skill-writer

### Task 3: Update autopilot/SKILL.md

**Type:** code
**Files:**
- Modify: `.claude/skills/autopilot/SKILL.md`

**Changes:**
- Replace "/scaffold" → "/skill-writer create"

**Acceptance:**
- [ ] grep "scaffold" = 0 results

### Task 4: Delete old skills

**Type:** code
**Files:**
- Delete: `.claude/skills/scaffold/SKILL.md`
- Delete: `.claude/skills/claude-md-writer/SKILL.md`

**Acceptance:**
- [ ] scaffold/ directory removed
- [ ] claude-md-writer/ directory removed

### Task 5: Sync template/

**Type:** code
**Files:**
- Create: `template/.claude/skills/skill-writer/SKILL.md`
- Modify: `template/.claude/skills/reflect/SKILL.md`
- Modify: `template/.claude/skills/autopilot/SKILL.md`
- Delete: `template/.claude/skills/scaffold/`
- Delete: `template/.claude/skills/claude-md-writer/`

**Acceptance:**
- [ ] Template matches main .claude/

### Task 6: Update CLAUDE.md

**Type:** code
**Files:**
- Modify: `template/CLAUDE.md`

**Changes:**
- Remove scaffold and claude-md-writer from Skills table
- Add skill-writer with description

**Acceptance:**
- [ ] Skills table updated
- [ ] No orphan references

### Task 7: Update docs

**Type:** code
**Files:**
- Modify: `docs/15-skills-setup.md`

**Changes:**
- Update skill references
- Update examples

**Acceptance:**
- [ ] Documentation consistent

### Execution Order

```
Task 1 (create skill-writer)
    ↓
Task 2 (update reflect) ─┬─ Task 3 (update autopilot)
                         │
    ↓                    ↓
Task 4 (delete old)
    ↓
Task 5 (sync template)
    ↓
Task 6 (CLAUDE.md) ─── Task 7 (docs)
```

---

## Nothing Lost Checklist

### От scaffold:
- [ ] Skill Types (wrapper/orchestrator/standalone)
- [ ] Decision tree for type selection
- [ ] Agent template structure
- [ ] Wrapper skill template structure
- [ ] Orchestrator skill template structure
- [ ] Validation rules (naming, structure, model, tools)
- [ ] Examples (create wrapper, create skill, create agent)
- [ ] Integration instructions (register in CLAUDE.md)

### От claude-md-writer:
- [ ] Three-Expert Gate (Karpathy, Sutskever, Murati)
- [ ] Documentation Hierarchy (5 tiers)
- [ ] 3-Tier System explanation
- [ ] "What Belongs Where" table
- [ ] Prompt Quality Principles
- [ ] Anti-Patterns table
- [ ] Quality Checklist
- [ ] Line count verification (wc -l)

### Новое:
- [ ] Requirements gathering (оба режима)
- [ ] Research phase (Exa integration)
- [ ] Unified 6-phase process

---

## Definition of Done

### Functional
- [ ] CREATE mode: can create agent, skill, wrapper
- [ ] UPDATE mode: can optimize existing prompts
- [ ] Requirements gathering works in both modes
- [ ] Research phase with Exa integrated
- [ ] Three-Expert Gate applied to all output
- [ ] reflect handoff works

### Technical
- [ ] skill-writer/SKILL.md < 400 lines
- [ ] grep "scaffold" across project = 0 (except git history)
- [ ] grep "claude-md-writer" across project = 0 (except git history)
- [ ] All Nothing Lost checklist items verified
- [ ] Template synced with main

### Verification Commands
```bash
# Verify old skills removed
grep -rn "scaffold" . --include="*.md" | grep -v "git"
grep -rn "claude-md-writer" . --include="*.md" | grep -v "git"

# Verify new skill exists
ls -la .claude/skills/skill-writer/
ls -la template/.claude/skills/skill-writer/

# Verify line count
wc -l .claude/skills/skill-writer/SKILL.md
# Expected: < 400
```

## Autopilot Log

<!-- Will be filled during execution -->

