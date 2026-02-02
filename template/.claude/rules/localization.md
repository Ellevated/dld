# Native Language Skill Triggers

When user triggers a skill in native language, invoke the corresponding slash command.

<!--
HOW TO USE:
1. Copy this file to your .claude/rules/ folder
2. Replace [Your Language] with your language name (e.g., "Russian (ru)", "French (fr)")
3. Add trigger words in your language for each skill
4. Delete this comment block
5. Optional: Add more languages by duplicating the section
-->

## [Your Language]

| Trigger | Skill |
|---------|-------|
| "your word for spark", "alternative trigger" | `/spark` |
| "your word for autopilot" | `/autopilot` |
| "your word for council" | `/council` |
| "your word for audit" | `/audit` |
| "your word for scout" | `/scout` |
| "your word for reflect" | `/reflect` |
| "your word for tester" | `/tester` |
| "your word for coder" | `/coder` |
| "your word for planner" | `/planner` |
| "your word for review" | `/review` |

## Action

When you see these triggers:
1. Immediately invoke `Skill` tool with corresponding skill name
2. Do NOT explain that you're "translating" — just execute
