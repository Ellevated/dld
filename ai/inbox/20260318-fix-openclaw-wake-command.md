# Idea: 20260318-202400
**Source:** openclaw
**Route:** spark
**Status:** new
---

TECH-157 wake не работает: два бага в `pueue-callback.sh`.

**Bug 1:** `timeout 5` убивает openclaw CLI — Node.js cold start занимает ~11 секунд.
**Bug 2:** Команда `openclaw system event --mode now` неверная — требуется `--text <text>`.

**`openclaw gateway wake` не существует** — нет такой субкоманды.

Правильный механизм: `openclaw gateway call` или через REST endpoint.
Проверить через `openclaw gateway call --help`.

Альтернатива — убрать wake совсем из callback, оставить только cron.
Или уменьшить cron интервал до 1-2 минут вместо 5.

Исправить или убрать нерабочий wake-блок из `pueue-callback.sh`.
