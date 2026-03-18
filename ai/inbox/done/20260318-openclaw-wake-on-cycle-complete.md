# Idea: 20260318-195300
**Source:** openclaw
**Route:** spark
**Status:** processing
---

После записи pending-event файла в `ai/openclaw/pending-events/` немедленно будить
OpenClaw через `openclaw gateway wake`, не ждать cron-скан (до 5 мин лага).

**Где менять:** `scripts/vps/pueue-callback.sh`, Step 5 (pending-events block).

**Что добавить** сразу после записи `$EVENT_FILE`:
```bash
# Wake OpenClaw immediately so it can report cycle completion without cron lag
openclaw gateway wake --mode now 2>>"$CALLBACK_LOG" || true
```

**Условие:** только если EVENT_FILE был записан (не для каждого callback, только
для autopilot/qa/reflect done events).

**Fallback:** cron-скан остаётся как есть — страховка если wake не прошёл.

**Ожидаемый результат:** OpenClaw получает финальный отчёт в течение секунд
после завершения цикла, не через 5 минут.
