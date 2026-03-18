
---
**Update:** Прямой коммит откатан. Задача идёт через Spark.

**Детали для реализации:**
- В `pueue-callback.sh` Step 6: `SKIP_NOTIFY=true` по умолчанию для всех skills
- Исключение: hard failure (`STATUS=failed` + непустой `SKILL`) — оставить уведомление
- Убрать все существующие частные `SKIP_NOTIFY=true` блоки (reflect, secondary qa, unknown skill, no-skill failed) — они становятся лишними
- Сохранить логику записи в `CALLBACK_LOG` — она нужна для дебага
