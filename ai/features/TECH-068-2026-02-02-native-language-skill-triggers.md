# Tech: [TECH-068] Native Language Skill Triggers Documentation

**Status:** done | **Priority:** P2 | **Date:** 2026-02-02

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
3. `template/ai/installation-guide.md` — modify: секция локализации (CORRECTED from ai/installation-guide.md)
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

## Detailed Implementation Plan

### Codebase Drift Check (2026-02-02)

**Verified:**
- `docs/15-skills-setup.md` — EXISTS, 322 lines, no localization section yet
- `template/.claude/rules/` — EXISTS (directory with architecture.md, dependencies.md, domains/_template.md)
- `template/ai/installation-guide.md` — EXISTS (271 lines, can be modified)
- `ai/installation-guide.md` — DOES NOT EXIST (spec was wrong about TECH-066 dependency)

**Docs numbering:** Highest is `21-mcp-troubleshooting.md`, so `22` is correct.

**Reference:** Working localization already exists at `/Users/desperado/dev/dld/.claude/rules/localization.md` (25 lines) — use as template basis.

---

### Task 1: Create docs/22-native-language-triggers.md

**Files:**
- Create: `docs/22-native-language-triggers.md`

**Context:**
Main documentation explaining native language triggers for DLD users. Provides setup instructions, examples in multiple languages, and copy-paste templates.

**Step 1: Create the documentation file**

```markdown
# Native Language Skill Triggers

Call DLD skills in your native language instead of slash commands.

---

## Why Native Triggers?

Slash commands like `/spark` and `/autopilot` are English-centric. Native speakers often want to invoke skills naturally:

- Russian: "спарк", "запусти автопилот"
- Spanish: "ejecuta spark", "piloto automatico"
- Chinese: "启动spark", "自动驾驶"

Claude Code can understand these triggers when properly configured.

---

## How It Works

Claude reads all `.md` files in `.claude/rules/` at the start of each conversation. By adding a `localization.md` file with trigger mappings, Claude learns to recognize native language phrases and invoke the corresponding skills.

```
User: "спарк"
Claude: [internally] → matches trigger → invokes /spark
```

---

## Setup (3 Steps)

### Step 1: Create the localization file

```bash
touch .claude/rules/localization.md
```

### Step 2: Add your language triggers

Copy the template below and customize for your language:

```markdown
# Native Language Skill Triggers

When user triggers a skill in native language, invoke the corresponding slash command.

## [Your Language]

| Trigger | Skill |
|---------|-------|
| "your word for spark" | `/spark` |
| "your word for autopilot" | `/autopilot` |
| "your word for council" | `/council` |
| "your word for audit" | `/audit` |
| "your word for scout" | `/scout` |
| "your word for reflect" | `/reflect` |

## Action

When you see these triggers:
1. Immediately invoke `Skill` tool with corresponding skill name
2. Do NOT explain that you're "translating" — just execute
```

### Step 3: Test it

```
You: спарк (or your trigger word)
Claude: [activates /spark skill]
```

---

## Examples by Language

### Russian (ru)

```markdown
## Russian (ru)

| Trigger | Skill |
|---------|-------|
| "спарк", "запусти спарк", "искра" | `/spark` |
| "автопилот", "запусти автопилот" | `/autopilot` |
| "консилиум", "совет", "созови консилиум" | `/council` |
| "аудит", "проверь код" | `/audit` |
| "скаут", "разведка", "исследуй" | `/scout` |
| "рефлект", "рефлексия" | `/reflect` |
| "тестер", "запусти тесты" | `/tester` |
| "кодер" | `/coder` |
| "планнер", "план" | `/planner` |
| "ревью", "проверь" | `/review` |
```

### Spanish (es)

```markdown
## Spanish (es)

| Trigger | Skill |
|---------|-------|
| "chispa", "ejecuta spark", "inicia spark" | `/spark` |
| "piloto automatico", "autopiloto" | `/autopilot` |
| "consejo", "reunion de expertos" | `/council` |
| "auditoria", "revisa codigo" | `/audit` |
| "explorador", "investigar" | `/scout` |
| "reflexion", "reflexionar" | `/reflect` |
```

### Chinese (zh)

```markdown
## Chinese (zh)

| Trigger | Skill |
|---------|-------|
| "启动spark", "火花", "点子" | `/spark` |
| "自动驾驶", "自动执行" | `/autopilot` |
| "委员会", "专家会议" | `/council` |
| "审计", "代码检查" | `/audit` |
| "侦察", "研究" | `/scout` |
| "反思", "总结" | `/reflect` |
```

### German (de)

```markdown
## German (de)

| Trigger | Skill |
|---------|-------|
| "funke", "starte spark" | `/spark` |
| "autopilot", "automatisch" | `/autopilot` |
| "rat", "expertenrat" | `/council` |
| "pruefung", "code pruefen" | `/audit` |
| "erkunden", "recherche" | `/scout` |
| "reflektieren" | `/reflect` |
```

---

## Custom Triggers

You can add project-specific triggers beyond skills:

```markdown
## Project-Specific

| Trigger | Action |
|---------|--------|
| "review PR", "check PR" | `/review` |
| "run tests", "test it" | `/tester` |
| "deploy", "ship it" | run deployment script |
```

---

## Multiple Languages

You can support multiple languages in one file:

```markdown
# Native Language Skill Triggers

## Russian (ru)

| Trigger | Skill |
|---------|-------|
| "спарк" | `/spark` |

## Spanish (es)

| Trigger | Skill |
|---------|-------|
| "chispa" | `/spark` |

## Action

When you see any of these triggers:
1. Immediately invoke `Skill` tool with corresponding skill name
2. Do NOT explain that you're "translating" — just execute
```

---

## Troubleshooting

### Trigger not recognized

1. Check `.claude/rules/localization.md` exists
2. Verify exact spelling in trigger table
3. Restart Claude Code session (rules load at start)

### Wrong skill activated

1. Make trigger more specific (add context words)
2. Use quotes around multi-word triggers

### Works sometimes, not always

Claude matches triggers heuristically. For reliability:
- Use distinctive words (not common words)
- Include the skill name transliterated (e.g., "спарк" not just "искра")

---

## See Also

- [Skills Setup Guide](15-skills-setup.md) — Full skills documentation
- [Template localization.md](https://github.com/Ellevated/dld/blob/main/template/.claude/rules/localization.md) — Ready-to-use template
```

**Acceptance Criteria:**
- [ ] File created at `docs/22-native-language-triggers.md`
- [ ] Contains Why, How, Setup sections
- [ ] Examples in 4+ languages (Russian, Spanish, Chinese, German)
- [ ] Copy-paste template included
- [ ] Links to skills-setup.md
- [ ] Troubleshooting section

---

### Task 2: Create template/.claude/rules/localization.md

**Files:**
- Create: `template/.claude/rules/localization.md`

**Context:**
Template file for new DLD projects. Users copy this and customize for their language. Should be minimal but complete.

**Step 1: Create the template file**

```markdown
# Native Language Skill Triggers

When user triggers a skill in native language, invoke the corresponding slash command.

<!--
HOW TO USE:
1. Copy this file to your .claude/rules/ folder
2. Replace [Your Language] with your language name
3. Add trigger words in your language
4. Delete this comment block
-->

## [Your Language]

| Trigger | Skill |
|---------|-------|
| "your word for spark", "alternative" | `/spark` |
| "your word for autopilot" | `/autopilot` |
| "your word for council" | `/council` |
| "your word for audit" | `/audit` |
| "your word for scout" | `/scout` |
| "your word for reflect" | `/reflect` |
| "your word for review" | `/review` |
| "your word for tester" | `/tester` |
| "your word for coder" | `/coder` |
| "your word for planner" | `/planner` |

## Action

When you see these triggers:
1. Immediately invoke `Skill` tool with corresponding skill name
2. Do NOT explain that you're "translating" — just execute
```

**Acceptance Criteria:**
- [ ] File created at `template/.claude/rules/localization.md`
- [ ] Contains placeholder structure
- [ ] Includes HTML comment with usage instructions
- [ ] Lists all standard skills
- [ ] Action section explains behavior

---

### Task 3: Update docs/15-skills-setup.md

**Files:**
- Modify: `docs/15-skills-setup.md:306-322` (Common Issues section)

**Context:**
Add reference to native language triggers documentation and add a new troubleshooting entry.

**Step 1: Add new section before "Common Issues"**

Insert after line 303 (after Testing section, before Common Issues):

```markdown
---

## Native Language Triggers

Call skills in your native language instead of slash commands.

**Quick Setup:**
1. Create `.claude/rules/localization.md`
2. Add trigger mappings for your language
3. Claude recognizes native phrases

**Example (Russian):**
```
User: "спарк"
Claude: [activates /spark]
```

See [Native Language Triggers](22-native-language-triggers.md) for full documentation and examples in multiple languages.

---
```

**Step 2: Add to Common Issues section**

Add after line 321 (after "Council not reaching consensus"):

```markdown

### Native triggers not working
See [Native Language Triggers](22-native-language-triggers.md) — check localization.md exists.
```

**Acceptance Criteria:**
- [ ] New "Native Language Triggers" section added before Common Issues
- [ ] Link to docs/22-native-language-triggers.md
- [ ] Brief example included
- [ ] Common Issues updated with troubleshooting entry

---

### Task 4: Update template/ai/installation-guide.md [CORRECTED]

**Files:**
- Modify: `template/ai/installation-guide.md:152-153` (Component Matrix section)

**Context:**
The spec originally referenced `ai/installation-guide.md` which doesn't exist. The correct file is `template/ai/installation-guide.md`. Add localization as a component in the tier matrix.

**Step 1: Add localization row to Component Matrix**

Insert after line 152 (after "Custom Rules" row):

```markdown
| Localization | - | Template | Template |
```

**Step 2: Add Localization section after Cherry-Pick Installation**

Insert after line 194 (after "Add Hooks" section):

```markdown

### Add Localization (Native Language Triggers)

For non-English users who want to invoke skills in their native language:

```bash
# Copy localization template
cp template/.claude/rules/localization.md .claude/rules/

# Edit with your language triggers
# See docs/22-native-language-triggers.md for examples
```

**When to recommend:**
- User's system language is not English
- User communicates in non-English language
- User explicitly asks about native language support
```

**Acceptance Criteria:**
- [ ] Component Matrix includes Localization row
- [ ] New "Add Localization" section in Cherry-Pick Installation
- [ ] LLM-readable recommendation criteria
- [ ] Links to documentation

---

### Execution Order

```
Task 1 (docs/22-native-language-triggers.md)
    ↓
Task 2 (template/.claude/rules/localization.md)
    ↓
Task 3 (docs/15-skills-setup.md)
    ↓
Task 4 (template/ai/installation-guide.md)
```

**All tasks can execute sequentially.** No external dependencies (TECH-066 was incorrectly referenced — the file exists at `template/ai/installation-guide.md`).

---

### Research Sources

- Working implementation: `/Users/desperado/dev/dld/.claude/rules/localization.md` (25 lines, Russian example)
- No external research needed (documentation-only task)

---

## Definition of Done

### Functional
- [x] Russian user can write "спарк" and Claude invokes `/spark`
- [x] Template includes localization.md for new projects
- [x] Documentation explains setup in <5 minutes

### Documentation
- [x] docs/22-native-language-triggers.md exists
- [x] Examples in 4 languages (Russian, Spanish, Chinese, German)
- [x] Template rule ready for copy-paste

### Technical
- [x] No code changes (docs only)
- [x] Works with current Claude Code

---

## Autopilot Log

**Date:** 2026-02-02
**Duration:** ~15 min

### Execution Summary

1. **PHASE 0:** Worktree created at `.worktrees/TECH-068`
2. **PHASE 1:** Planner validated spec, found drift (ai/installation-guide.md → template/ai/installation-guide.md)
3. **Tasks executed:**
   - Task 1: Created `docs/22-native-language-triggers.md` (164 lines)
   - Task 2: Created `template/.claude/rules/localization.md` (33 lines)
   - Task 3: Updated `docs/15-skills-setup.md` (added section + troubleshooting)
   - Task 4: Updated `template/ai/installation-guide.md` (added component + section)
4. **Reviews:**
   - Spec review: PASS
   - Code quality: Fixed broken link in See Also section

### Files Created/Modified

| File | Action | Lines |
|------|--------|-------|
| docs/22-native-language-triggers.md | created | 165 |
| template/.claude/rules/localization.md | created | 33 |
| docs/15-skills-setup.md | modified | +22 |
| template/ai/installation-guide.md | modified | +18 |
