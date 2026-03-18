# Idea: 20260318-201500
**Source:** openclaw
**Route:** spark
**Status:** new
---

QA dispatch падает с "spec file not found" когда autopilot обрабатывает inbox-задачу
напрямую (TASK_LABEL = `inbox-20260318-XXXXXX`).

**Симптом:** `QA skipped: spec file not found for inbox-20260318-200931`

**Причина:** в `pueue-callback.sh` Step 7 QA dispatch безусловно запускается после
любого autopilot done. Если TASK_LABEL начинается с `inbox-` — это задача без
отдельного spec-файла, QA не может его найти.

**Решение:** в Step 7, перед QA dispatch, проверить что TASK_LABEL соответствует
паттерну `(TECH|FTR|BUG|ARCH)-NNN`. Если нет — пропустить QA (залогировать почему).

```bash
# Skip QA for inbox-tasks (no spec file to validate against)
if [[ ! "$TASK_LABEL" =~ ^(TECH|FTR|BUG|ARCH)-[0-9]+ ]]; then
    echo "[callback] Skipping QA: task_label '${TASK_LABEL}' has no spec file"
else
    # ... existing QA dispatch logic
fi
```

Reflect при этом можно оставить (он не зависит от spec).
