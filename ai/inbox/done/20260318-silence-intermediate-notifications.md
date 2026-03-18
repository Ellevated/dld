# Idea: 20260318-192300
**Source:** openclaw
**Route:** spark
**Status:** processing
---

Заглушить промежуточные Telegram уведомления от DLD-бота во время цикла.

Сейчас `pueue-callback.sh` шлёт уведомления за каждый шаг: spark, autopilot, QA —
это засоряет чат. Нужно чтобы DLD-бот молчал весь цикл.

**Требуемое поведение:**
- `SKIP_NOTIFY=true` для skills: spark, autopilot, qa (все промежуточные шаги)
- Reflect уже заглушён — оставить как есть
- DLD-бот не шлёт ничего во время цикла
- OpenClaw читает `ai/openclaw/pending-events/` и сам собирает финальный отчёт

**Что НЕ трогать:**
- pending-events файлы — они остаются, OpenClaw их читает
- Логику dispatch QA + Reflect — не менять
- Ошибки (failed tasks) — можно оставить, обсудить отдельно
