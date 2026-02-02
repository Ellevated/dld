# Tech: [TECH-068] Native Language Skill Triggers Documentation

**Status:** queued | **Priority:** P2 | **Date:** 2026-02-02

## Why

DLD skills вызываются через slash-команды (`/spark`, `/autopilot`). Но пользователи на разных языках хотят вызывать их естественно: "запусти спарк", "ejecuta autopilot", "启动spark".

Сейчас Claude не распознаёт эти триггеры без явных инструкций. Нужна документация для пользователей: как настроить native language triggers в своём проекте.

## Context

- Проблема обнаружена в нашей разработке: "спарк" не вызывал `/spark`
- Хотфикс для внутренней разработки: `.claude/rules/localization.md`
- Нужна публичная документация для пользователей DLD

---

## Scope

**In scope:**
- Документация в `docs/` о native language triggers
- Примеры на разных языках (русский, испанский, китайский)
- Добавить в `ai/installation-guide.md` (TECH-066) секцию для LLM-установщика
- Template правило в `template/.claude/rules/`

**Out of scope:**
- Автоматическое определение языка пользователя
- Встроенная поддержка в Claude Code (это feature request к Anthropic)
- Голосовой ввод

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `docs/22-native-language-triggers.md` — new: основная документация
2. `template/.claude/rules/localization.md` — new: шаблон для пользователей
3. `ai/installation-guide.md` — modify: секция локализации (после TECH-066)
4. `docs/15-skills-setup.md` — modify: ссылка на новую документацию

**New files allowed:**
- `docs/22-native-language-triggers.md`
- `template/.claude/rules/localization.md`

**FORBIDDEN:** All other files.

---

## Design

### Документация Structure

```markdown
# docs/22-native-language-triggers.md

## Why Native Triggers?

Slash commands are English-centric. Native speakers want natural invocation.

## How It Works

Claude reads `.claude/rules/` files. Add localization rules there.

## Setup

1. Create `.claude/rules/localization.md`
2. Add trigger mappings for your language
3. Done — Claude now understands native triggers

## Examples by Language

### Russian
| Trigger | Skill |
|---------|-------|
| "спарк", "запусти спарк" | `/spark` |
| "автопилот" | `/autopilot` |
| "консилиум", "совет" | `/council` |

### Spanish
| Trigger | Skill |
|---------|-------|
| "chispa", "ejecuta spark" | `/spark` |
| "piloto automático" | `/autopilot` |
| "consejo" | `/council` |

### Chinese
| Trigger | Skill |
|---------|-------|
| "启动spark", "火花" | `/spark` |
| "自动驾驶" | `/autopilot` |
| "委员会" | `/council` |

## Template

[Copy-paste template for localization.md]

## Custom Triggers

You can add project-specific triggers:
- "review PR" → `/review`
- "check code" → `/audit`
```

### Template Rule

```markdown
# template/.claude/rules/localization.md

# Native Language Skill Triggers

When user triggers a skill in native language, invoke the corresponding slash command.

## [Your Language]

| Trigger | Skill |
|---------|-------|
| "your word" | `/spark` |
| ... | ... |

## Action

When you see these triggers:
1. Immediately invoke `Skill` tool with corresponding skill name
2. Do NOT explain — just execute
```

---

## Implementation Plan

### Task 1: Create docs/22-native-language-triggers.md

**Type:** docs
**Files:** create `docs/22-native-language-triggers.md`
**Acceptance:**
- Explains why native triggers matter
- Setup instructions (3 steps)
- Examples in 3+ languages
- Copy-paste template
- Links to skills-setup.md

### Task 2: Create template/.claude/rules/localization.md

**Type:** docs
**Files:** create `template/.claude/rules/localization.md`
**Acceptance:**
- Empty template with structure
- Comments explaining how to fill
- One example language (English → English, as placeholder)

### Task 3: Update docs/15-skills-setup.md

**Type:** docs
**Files:** modify `docs/15-skills-setup.md`
**Acceptance:**
- Add "Native Language Triggers" section
- Link to new docs/22-native-language-triggers.md
- Brief mention in "Common Issues"

### Task 4: Update ai/installation-guide.md (after TECH-066)

**Type:** docs
**Files:** modify `ai/installation-guide.md`
**Acceptance:**
- Add "Localization" component
- LLM-readable format
- Condition: "when user's system language != English"

### Execution Order

1 → 2 → 3 → 4

**Dependency:** Task 4 depends on TECH-066 completion.

---

## Definition of Done

### Functional
- [ ] Russian user can write "спарк" and Claude invokes `/spark`
- [ ] Template includes localization.md for new projects
- [ ] Documentation explains setup in <5 minutes

### Documentation
- [ ] docs/22-native-language-triggers.md exists
- [ ] Examples in 3+ languages
- [ ] Template rule ready for copy-paste

### Technical
- [ ] No code changes (docs only)
- [ ] Works with current Claude Code

---

## Autopilot Log

*(Filled by Autopilot during execution)*
