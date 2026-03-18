# Tech: [TECH-154] DLD Cycle E2E Reliability — First Full Pass

**Status:** queued | **Priority:** P0 | **Date:** 2026-03-18

## Why

Ни один полный цикл `inbox → spark → queued → autopilot → QA → reflect` не прошёл
от начала до конца без ручного вмешательства. Четыре конкретных разрыва найдены
в ходе сессии 2026-03-18:

1. **QA не находит спеку** — qa-loop.sh запускается без передачи пути к spec-файлу;
   агент спрашивает "что тестировать?" и продолжает без ответа (exit 0 = false pass).
2. **Reflect не запускался** — pueue-callback.sh проверял `PENDING_COUNT` diary/index.md;
   все записи `done` → reflect тихо пропускался после каждого autopilot.
   *Исправлено в e7d619d, но требует верификации.*
3. **QA report статус unknown** — три файла `ai/qa/2026-03-17-tech-*.md` со статусом
   `unknown`; openclaw-artifact-scan.py не может их прочитать.
4. **topic_id NULL для 5 из 6 проектов** — notify.py не знает куда слать уведомления;
   фиксы в 1b358e4 требуют `/bindtopic` в каждом топике.

## Scope

**In scope:**

- `qa-loop.sh`: передавать путь к spec-файлу как аргумент; fallback — fail с `exit 1`
  если спека не найдена (не продолжать вслепую)
- `pueue-callback.sh`: проверить что reflect dispatch работает после e7d619d (smoke test)
- `openclaw-artifact-scan.py`: распознавать формат `2026-MM-DD-spec-id.md` (lowercase, дефисы)
  помимо текущего `YYYYMMDD-HHMMSS-SPEC-ID.md`
- `notify.py` + `/bindtopic`: добавить guard — если topic_id NULL, логировать и fail-close
  (уже частично в 1b358e4, проверить полноту)
- Один интеграционный smoke test: запустить дешёвый autopilot (echo task) и убедиться
  что QA + reflect задиспатчены и дошли до completion

**Out of scope:**

- Перенос QA/Reflect dispatch в orchestrator poll cycle (это TECH-155 если нужно)
- Починка diary записей в awardybot (это проектная задача, не DLD цикл)
- Переработка структуры QA отчётов

---

## Root Cause Analysis

### Разрыв 1: QA вслепую

`qa-loop.sh` вызывается из pueue-callback.sh:
```bash
run-agent.sh "$PROJECT_PATH" "$PROJECT_PROVIDER" "qa" "/qa Проверь изменения после ${TASK_LABEL}"
```

`TASK_LABEL` содержит ID типа `awardybot:autopilot-FTR-702`, но qa-скилл ищет
спеку по ID самостоятельно — и не находит, потому что ID в label не совпадает
с именем файла. Нужно передавать `SPEC_ID` явно.

### Разрыв 2: Reflect пропускался (исправлен e7d619d)

```bash
PENDING_COUNT=$(grep -c '| pending |' "$DIARY_INDEX")
if (( PENDING_COUNT < 1 )); then echo "Skipping reflect" ...
```

Все diary записи `done` → reflect никогда не запускался. Удалено в e7d619d.

### Разрыв 3: artifact-scan не читает legacy QA filenames

Паттерн в `openclaw-artifact-scan.py`:
```python
re.match(r'\d{8}-\d{6}-(.+)\.md', filename)  # только YYYYMMDD-HHMMSS-ID
```

Файлы `2026-03-17-tech-151.md` не матчатся → статус `unknown`.

### Разрыв 4: topic_id NULL

В `db.py` `get_project_by_topic()` принимает только `topic_id`, без `chat_id`.
При нескольких форумах в разных чатах routing ломается.
Частично починено в 1b358e4 + admin_handler.py.

---

## Implementation Plan

### Task 1: Fix qa-loop spec path injection
**Type:** patch | **Files:** `scripts/vps/pueue-callback.sh`, `scripts/vps/run-agent.sh`

- Извлечь `SPEC_ID` из `TASK_LABEL` (regex: `autopilot-(.+)$`)
- Найти spec-файл: `find $PROJECT_PATH/ai/features -name "${SPEC_ID}*.md" | head -1`
- Передать путь в QA prompt: `/qa --spec $SPEC_PATH Проверь изменения после ${TASK_LABEL}`
- Если spec не найден → логировать warn, но продолжать (QA делает best-effort)

### Task 2: Verify reflect dispatch after e7d619d
**Type:** verification | **Files:** `scripts/vps/pueue-callback.sh`

- Проверить логи последнего autopilot completion
- Убедиться что reflect задиспатчен без `Skipping reflect`
- Если нет — добавить дополнительный debug log

### Task 3: Fix artifact-scan QA filename patterns
**Type:** patch | **Files:** `scripts/vps/openclaw-artifact-scan.py`

- Добавить второй паттерн: `re.match(r'\d{4}-\d{2}-\d{2}-(.+)\.md', filename)`
- Нормализовать spec ID: `tech-151` → `TECH-151`
- Тест: убедиться что все 4 QA файла из awardybot распознаются корректно

### Task 4: Smoke test — one full cycle pass
**Type:** test | **Files:** `scripts/vps/tests/test_cycle_smoke.sh` (новый)

- Создать минимальный spec в тестовом проекте
- Запустить autopilot с `echo` командой
- Проверить: QA dispatched → QA report written → reflect dispatched → reflect report written
- Это первый полный e2e pass

---

## Acceptance Criteria

- [ ] `qa-loop.sh` получает путь к спеке или явно логирует "spec not found, QA best-effort"
- [ ] Reflect запускается после autopilot (проверено в pueue log, не только в коде)
- [ ] `openclaw-artifact-scan.py` распознаёт оба формата QA filename без `unknown`
- [ ] Один smoke test проходит полный цикл без ручного вмешательства
- [ ] Все 4 разрыва закрыты или явно задокументированы как won't-fix

---

## Links

- Предыдущая работа: `TECH-151` (north-star alignment, done)
- Commit `e7d619d` — reflect dispatch fix
- Commit `1b358e4` — topic-scoped routing
- Commit `5ece67d` — test layer cleanup
