# Native Language Triggers

Invoke DLD skills in your native language instead of English slash commands.

---

## Why Native Triggers?

English slash commands work, but feel unnatural for non-English speakers:

```
/spark → Start spark          # English-centric
спарк → Start spark           # Natural for Russians
火花 → Start spark            # Natural for Chinese
```

**Benefits:**
- Faster invocation (no mental translation)
- More natural conversation flow
- Team adoption improves (everyone uses native terms)

---

## How It Works

Claude reads `.claude/rules/localization.md` as part of CLAUDE.md instructions:

```
1. User says "спарк" (Russian for spark)
2. Claude sees mapping in localization.md
3. Immediately invokes /spark skill
4. No explanation, just executes
```

**Key:** Claude NEVER explains "I'm translating" — it just runs the skill.

---

## Setup (3 Steps)

### Step 1: Create File

```bash
touch .claude/rules/localization.md
```

### Step 2: Add Trigger Mappings

Use this template:

```markdown
# Native Language Skill Triggers

When user triggers a skill in native language, invoke the corresponding slash command.

## {Language} ({code})

| Trigger | Skill |
|---------|-------|
| "{native_word}", "{phrase}" | `/skill_name` |

## Action

When you see these triggers:
1. Immediately invoke `Skill` tool with corresponding skill name
2. Do NOT explain that you're "translating" — just execute
```

### Step 3: Test It

```bash
# In Claude Code chat
спарк                    # Should invoke /spark
autopilot               # Should invoke /autopilot (English still works)
```

---

## Examples by Language

### Russian (ru)

```markdown
| Trigger | Skill |
|---------|-------|
| "спарк", "запусти спарк", "искра" | `/spark` |
| "автопилот", "запусти автопилот" | `/autopilot` |
| "консилиум", "совет" | `/council` |
| "скаут", "разведка" | `/scout` |
| "тестер" | `/tester` |
```

### Spanish (es)

```markdown
| Trigger | Skill |
|---------|-------|
| "chispa", "iniciar chispa" | `/spark` |
| "autopiloto" | `/autopilot` |
| "consejo" | `/council` |
| "explorador" | `/scout` |
| "probador" | `/tester` |
```

### Chinese (zh)

```markdown
| Trigger | Skill |
|---------|-------|
| "火花", "启动火花" | `/spark` |
| "自动驾驶" | `/autopilot` |
| "理事会" | `/council` |
| "侦察" | `/scout` |
| "测试员" | `/tester` |
```

### German (de)

```markdown
| Trigger | Skill |
|---------|-------|
| "funke", "funken starten" | `/spark` |
| "autopilot" | `/autopilot` |
| "rat" | `/council` |
| "kundschafter" | `/scout` |
| "tester" | `/tester` |
```

**Full example:** After setup, create your own `.claude/rules/localization.md` with complete mappings for your language.

---

## Custom Triggers & Multiple Languages

Add project-specific triggers beyond skills:

```markdown
## Custom Triggers

| Trigger | Action |
|---------|--------|
| "показать статус", "статус" | Show project status from STATUS.md |
| "создать задачу" | Create new task spec (invoke /spark) |
```

Support multiple languages in one file by adding multiple `## Language` sections with one shared `## Action` block.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Trigger not working | Check file exists, trigger has quotes, restart session |
| Claude explains instead of executing | Add "Do NOT explain" to Action section |
| Multiple triggers match | Use more specific phrases |

---

## See Also

- [Skills Setup](15-skills-setup.md) — Configure DLD skills
- [CLAUDE.md Template](04-claude-md-template.md) — How CLAUDE.md works
- [Localization Template](../template/.claude/rules/localization.md) — Ready-to-use template
