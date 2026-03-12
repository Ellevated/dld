# TECH-039: Expand Reflect & Claude-MD-Writer Scope + Three-Expert Gate

**Status:** done | **Priority:** P1 | **Date:** 2026-01-29

## Why

Reflect и claude-md-writer замыкали цикл самоулучшения только на `CLAUDE.md` и `.claude/rules/`. Агенты (`.claude/agents/*.md`) и скилы (`.claude/skills/*/SKILL.md`) оставались за пределами цикла — все улучшения промптов делались вручную.

Это значит: если reflect находит паттерн "planner пропускает drift check" — он мог добавить правило в CLAUDE.md, но НЕ мог обновить сам `planner.md`, где реальный fix нужен.

## Context

Проблема обнаружена при анализе цепочки самоулучшения:

```
diary-recorder → reflect → claude-md-writer → CLAUDE.md + rules/
                                                    ↑
                                              ТОЛЬКО ЭТО (до фикса)
```

Дополнительно применена техника **Three-Expert Quality Gate** (prompt engineering) для оптимизации самих скилов:
1. **Karpathy** — убрать избыточное, что Claude уже знает
2. **Sutskever** — убрать ограничения, мешающие модели; принципы > процедуры
3. **Murati** — убрать friction в UX; упростить где возможно

---

## Scope

**In scope:**
- Расширить scope reflect на agents/skills/dispatch
- Расширить scope claude-md-writer на agents/skills
- Встроить Three-Expert Quality Gate в оба скила
- Оптимизировать промпты обоих скилов (3-expert pruning)

**Out of scope:**
- Изменение diary-recorder (отдельная TECH-038)
- Изменение scaffold
- Автоматический запуск reflect (остаётся ручным через `/reflect`)

## Impact Tree Analysis

### Step 1: UP — who uses?
- `reflect/SKILL.md` вызывается пользователем через `/reflect`
- `claude-md-writer/SKILL.md` вызывается после reflect или напрямую

### Step 2: DOWN — what depends on?
- reflect читает `ai/diary/index.md` и diary entries
- claude-md-writer модифицирует целевые файлы

### Step 3: BY TERM
- `reflect` упоминается в diary-recorder.md (рекомендация запускать)
- `claude-md-writer` упоминается в reflect (handoff)

### Verification
- All found files in Allowed Files ✓

## Allowed Files

**ONLY these files may be modified:**
1. `.claude/skills/reflect/SKILL.md` — расширить scope + 3-expert gate
2. `.claude/skills/claude-md-writer/SKILL.md` — расширить scope + 3-expert gate

**FORBIDDEN:** All other files.

## Environment

nodejs: false
docker: false
database: false

## Design

### Новый scope reflect

| Target | Path | When to Propose |
|--------|------|----------------|
| Project rules | `CLAUDE.md`, `.claude/rules/*.md` | Pattern ≥2 entries |
| Agent prompts | `.claude/agents/*.md` | Agent-specific failure ≥2 |
| Skill prompts | `.claude/skills/*/SKILL.md` | Skill flow issue |
| Dispatch logic | `subagent-dispatch.md` | Dispatch condition problem |

### Новый scope claude-md-writer

| Target | Path | Limits |
|--------|------|--------|
| Foundation | `CLAUDE.md` | < 200 lines |
| Rules | `.claude/rules/*.md` | < 500 lines, `paths:` frontmatter |
| Agent prompts | `.claude/agents/*.md` | Concise, principle-based |
| Skill prompts | `.claude/skills/*/SKILL.md` | Action-oriented, minimal |

### Three-Expert Quality Gate (встроен в оба)

1. **Karpathy:** Redundant? Claude already knows? If removing doesn't hurt — don't add.
2. **Sutskever:** Constraining instead of guiding? Principles > rigid rules.
3. **Murati:** Adding friction? Could be simpler or faster?

### Замкнутый цикл (после фикса)

```
diary-recorder → reflect → claude-md-writer
                   ↓              ↓
              анализ diary    применяет к:
              + Exa research  ├─ CLAUDE.md
              + 3-Expert gate ├─ .claude/rules/
                              ├─ .claude/agents/*.md   ← NEW
                              └─ .claude/skills/*.md   ← NEW
```

## Implementation Plan

### Task 1: Rewrite reflect/SKILL.md

**Type:** code
**Files:**
- Modify: `.claude/skills/reflect/SKILL.md`

**What was done:**
1. Scope таблица расширена на agents/skills/dispatch
2. Process упрощён: 6 шагов → 6 шагов (но компактнее)
3. Step 4: Three-Expert Quality Gate добавлен
4. Убрано: bash хинты, Terminology таблица, "What NOT to Do", дублирующий Quality Checklist, verbose yaml output
5. Результат: 201 → 102 строки (−49%)

**Acceptance:**
- ✅ Scope включает agents/skills
- ✅ Three-Expert Gate встроен
- ✅ Exa research сохранён (Step 2)
- ✅ Строки уменьшены без потери смысла

### Task 2: Rewrite claude-md-writer/SKILL.md

**Type:** code
**Files:**
- Modify: `.claude/skills/claude-md-writer/SKILL.md`

**What was done:**
1. Scope таблица расширена на agents/skills
2. Three-Expert Optimization Gate добавлен как секция
3. Prompt Quality Principles добавлены (front-load, principles > procedures, show > tell)
4. Убрано: 12 bash counting примеров (оставлен принцип), полный CLAUDE.md template (30 строк), полный Rules template, Migration Checklist
5. Результат: 236 → 125 строк (−47%)

**Acceptance:**
- ✅ Scope включает agents/skills
- ✅ Three-Expert Gate встроен
- ✅ Prompt Quality Principles задокументированы
- ✅ Строки уменьшены без потери смысла

### Execution Order

Task 1 → Task 2 (выполнено последовательно)

---

## Definition of Done

### Functional
- [x] reflect scope включает agents, skills, dispatch
- [x] claude-md-writer scope включает agents, skills
- [x] Three-Expert Quality Gate встроен в оба скила
- [x] Prompt Quality Principles задокументированы
- [x] Цикл самоулучшения замыкается на всю систему

### Technical
- [x] reflect: 201 → 102 строки (−49%)
- [x] claude-md-writer: 236 → 125 строк (−47%)
- [x] No regressions in reflect flow
- [x] No regressions in claude-md-writer flow

## Autopilot Log

- 2026-01-29: Implemented manually during session (not via autopilot)
- Analysis: 3-expert technique applied to both skills
- reflect/SKILL.md: 201 → 102 lines, scope expanded to agents/skills
- claude-md-writer/SKILL.md: 236 → 125 lines, scope expanded to agents/skills
