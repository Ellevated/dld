# TECH-223 — advisory findings

| File:line | Finding | Suggested action |
|-----------|---------|------------------|
| scripts/vps/.env.example | рычаг HEADLESS_BACKGROUND_TASKS не задекларирован (конвенция: рычаги раннера там не перечисляются) | решить конвенцию для рычагов раннера |
| scripts/metrics/bg_turn_endings.py:78 | load_runs повторяет фильтр run_metrics.load_runs | вынести общий загрузчик с result_preview в run_metrics |
| scripts/vps/runner_cli.py:137 | Exa: fork-субагенты и тул Workflow фонят и при CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1 (#73453, #69030); Workflow не в deny-листе | проверить на EXP-013, при рецидиве bg_killed — добавить Workflow |
