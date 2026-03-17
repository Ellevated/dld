# Bug Fix: [BUG-152] Agent SDK venv сломан — fake bash wrapper вместо реального venv

**Status:** done | **Priority:** P0 | **Date:** 2026-03-17

## Why

`scripts/vps/venv/` содержал fake venv — `bin/python3` был bash-скриптом, который просто добавлял `PYTHONPATH` и вызывал системный python3. Нет pip, нет возможности обновить пакеты.

SDK bundled claude binary (2.1.71) разошёлся с системным CLI (2.1.77). Результат: пустые логи, ошибки `--output-format=stream-json requires --verbose`, невозможность запустить агентов.

### Timeline

- **11-15 марта**: SDK работал (283 успешных запуска из 308)
- **15-17 марта**: Claude CLI обновился 2.1.71→2.1.77, bundled binary стал выдавать ошибки
- **17 марта**: Обнаружено при попытке ручного запуска

## Root Cause

При создании venv в setup-vps.sh использовался hand-crafted bash wrapper вместо `python3 -m venv`. Файл `venv/bin/python3`:

```bash
#!/usr/bin/env bash
VENV_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SITE_PACKAGES="$VENV_DIR/lib/python3.12/site-packages"
export PYTHONPATH="$SITE_PACKAGES${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 "$@"
```

Без pip — невозможно обновить пакеты. Без реальной изоляции — PYTHONPATH хак ломается при конфликтах.

## Fix

1. Создан реальный venv: `python3 -m venv venv --clear`
2. Установлены все зависимости через pip: `claude-agent-sdk`, `python-telegram-bot`, `python-dotenv`, `groq`
3. Проверено:
   - SDK imports: OK
   - SDK test call (1 turn): OK, exit_code=0, cost=$0.22
   - Full integration via run-agent.sh: OK
   - notify.py imports: OK

## Verification

```bash
# SDK works
./venv/bin/python3 -c "from claude_agent_sdk import query; print('OK')"

# Full pipeline
./run-agent.sh /home/dld/projects/dld claude qa "test"
# → exit_code: 0, turns: 1
```

## Lessons Learned

29. **Fake venv = tech debt bomb** — bash wrapper в `bin/python3` работает до первого конфликта версий. Без pip невозможно обновить пакеты. Всегда использовать `python3 -m venv`.
30. **Bundled binary drift** — `claude-agent-sdk` 0.1.48 bundled'ит CLI 2.1.71. Если системный CLI обновляется, bundled может отстать. Нужен мониторинг версий или pinning.
