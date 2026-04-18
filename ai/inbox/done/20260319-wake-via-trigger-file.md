# Idea: 20260319-191500
**Source:** openclaw
**Route:** spark
**Status:** processing
---

`openclaw system event` не работает с VPS — gateway закрывает соединение (1000).
event_writer.py тратит 23 сек на неудачную попытку при каждом цикле.

**Решение:** убрать wake из event_writer.py, OpenClaw уже читает pending-events
через cron-скан каждые 5 минут — этого достаточно.

Или: уменьшить timeout wake до 5 сек и логировать failure как DEBUG, не WARNING.
Главное — не блокировать callback на 23 секунды при каждом событии.

**Изменение:** в `event_writer.py` функция `wake_openclaw()` — уменьшить timeout
до 5s или убрать вызов из `notify()`.
