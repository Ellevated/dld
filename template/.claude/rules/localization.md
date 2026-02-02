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

## Spanish (es)

| Trigger | Skill |
|---------|-------|
| "chispa", "crear especificación" | `/spark` |
| "piloto automático", "ejecutar" | `/autopilot` |
| "consejo", "debate" | `/council` |
| "auditoría", "revisar código" | `/audit` |
| "explorador", "investigar" | `/scout` |
| "reflexionar" | `/reflect` |
| "probador", "ejecutar pruebas" | `/tester` |
| "codificador" | `/coder` |
| "planificador" | `/planner` |
| "revisión" | `/review` |

## Action

When you see these triggers:
1. Immediately invoke `Skill` tool with corresponding skill name
2. Do NOT explain that you're "translating" — just execute
