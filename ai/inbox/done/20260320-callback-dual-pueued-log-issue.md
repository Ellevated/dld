# Bug: 20260320-101900
**Source:** openclaw
**Route:** spark
**Status:** processing
---

`extract_agent_output()` в callback.py возвращает пустой skill/preview для всех задач
потому что `pueue log <id> --json` подключается к user pueued socket, а задачи
выполнялись через root pueued socket. Разные socket — задачи не видны.

**Симптомы:**
- callback.py: `agent output: skill= preview_len=0`
- QA и Reflect не задиспатчиваются (нет spec_id, нет skill="autopilot")

**Решение:**
Не использовать `pueue log --json` для чтения вывода. Вместо этого читать
лог-файл напрямую из `scripts/vps/logs/dld-YYYYMMDD-HHMMSS.log`.
`run-agent.sh` уже пишет JSON output в logs/ — callback должен найти
последний лог файл по pueue_id или по времени и вычитать skill/preview оттуда.

**Приоритет:** high — без этого QA/Reflect не работают
