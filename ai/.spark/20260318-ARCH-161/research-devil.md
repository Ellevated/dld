# Devil's Advocate — ARCH-161: Orchestrator Radical Rewrite

## Why NOT Do This?

### Argument 1: Уничтожение работающего Telegram-интерфейса без замены
**Concern:** Предложение удаляет telegram-bot.py и все хендлеры без определённой замены управляющего канала. Команды `/run`, `/status`, `/pause`, `/resume`, `/bindtopic`, `/addproject`, автоапрув задач — всё это перестаёт работать. Фаундер лишается единственного способа взаимодействовать с оркестратором в реальном времени.
**Evidence:** `telegram-bot.py:155` — `auto_approve_start()` вызывается из потока Spark при каждом создании спеки. `telegram-bot.py:321` — `/run` создаёт `.run-now-{project_id}` trigger file. `telegram-bot.py:550` — `handle_voice` и `handle_photo` — живые каналы для inbox. Всё это исчезает.
**Impact:** High
**Counter:** Если удаляем Telegram-бот — нужно ДО удаления определить замену управляющего канала. OpenClaw может читать события, но не отвечает на `/run`. Либо переносим команды в OpenClaw, либо оставляем бота (только урезанную версию), либо принимаем потерю оперативного контроля сознательно.

---

### Argument 2: Нулевой downtime при миграции — нереалистично
**Concern:** Во время перехода будут "лётные" pueue-задачи с лейблом формата `project_id:SPEC-ID`, запущенные старым orchestrator.sh. Новый callback.py будет разобран иначе и/или не найдёт путь к новому pueue-callback пути. Обрыв в середине autopilot = застрявшая задача без release_slot.
**Evidence:** `pueue-callback.sh:57` — `PROJECT_ID="${LABEL%%:*}"` — текущий формат парсинга. `setup-vps.sh:226` — `CALLBACK_LINE` захардкожен в `~/.config/pueue/pueue.yml`. Изменить callback в pueue.yml атомарно нельзя — daemon читает конфиг при старте, не на лету.
**Impact:** High
**Counter:** Нужна процедура миграции: (1) дождаться пустых слотов в pueue, (2) остановить dld-orchestrator, (3) перезаписать callback + запустить новый. Или сохранить совместимость формата лейбла `project_id:SPEC-ID` в новом callback.py — что тривиально.

---

### Argument 3: qa-loop.sh использует db_exec.sh (голый SQL через shell) — именно то, что ADR-017 запрещает
**Concern:** `qa-loop.sh:24` — `DB_EXEC="${SCRIPT_DIR}/db_exec.sh"` и `qa-loop.sh:32` — строковая интерполяция переменной `PROJECT_ID` прямо в SQL. Это ADR-017 violation. Но предложение удаляет `qa-loop.sh` и `db_exec.sh` — значит, нарушение исчезает само собой. Это аргумент ЗА переписывание, но нужно убедиться, что новый callback.py не воспроизведёт тот же паттерн.
**Evidence:** `qa-loop.sh:32`: `"$DB_EXEC" "UPDATE project_state SET phase = 'qa_running'... WHERE project_id = '${PROJECT_ID}';"` — classic SQL injection risk.
**Impact:** Medium (в качестве предупреждения: не воспроизводить в callback.py)
**Counter:** Убедиться, что callback.py использует только `db.py` с параметризованными запросами — ни одного inline SQL.

---

### Argument 4: 5 тестовых файлов проверяют удаляемый код
**Concern:** `test_cycle_smoke.py` (EC-1..EC-7) парсит `telegram-bot.py` и `pueue-callback.sh` напрямую — по именам файлов, по path. `test_notify.py` тестирует `notify.py`. `test_approve_handler.py` тестирует `approve_handler.py`. Все эти тесты сломаются после удаления файлов. Тест-сюит перестанет проходить.
**Evidence:** `test_cycle_smoke.py:40` — `bot_path = Path(VPS_DIR) / "telegram-bot.py"`. `test_cycle_smoke.py:138` — `callback_path = Path(VPS_DIR) / "pueue-callback.sh"`. `tests/run-tests.sh:14` — включает все эти тесты в suite.
**Impact:** High
**Counter:** Перед удалением файлов нужно либо удалить соответствующие тесты, либо переписать их под новые файлы. Нельзя оставить тест-сюит в сломанном состоянии — это нарушает правило "Tests must pass before committing".

---

### Argument 5: night-reviewer.sh вызывает notify.py — без него ночные отчёты уходят в /dev/null
**Concern:** `night-reviewer.sh:215` — `python3 "${SCRIPT_DIR}/notify.py" "${PROJECT_ID}" "${msg}"`. Если `notify.py` удалён, ночные находки перестают доходить до фаундера. Это тихая деградация — ошибок не будет, просто findings молча дропятся.
**Evidence:** `night-reviewer.sh` — в списке файлов "Keep", но вызывает `notify.py` — в списке "Delete". Противоречие в самом предложении.
**Impact:** High
**Counter:** Либо перенести функциональность отправки в night-reviewer.sh (inline urllib, что уже есть в notify.py), либо оставить slim-версию notify.py только для bash-вызовов, либо night-reviewer.sh тоже переводится на Python.

---

## Simpler Alternatives

### Alternative 1: Инкрементальная миграция (shell → Python по одному компоненту)
**Instead of:** Удалить 11 файлов и создать 2 новых за один PR
**Do this:** Заменить `orchestrator.sh` → `orchestrator.py` в Task 1. Заменить `pueue-callback.sh` → `callback.py` в Task 2. Удалить `inbox-processor.sh`, `qa-loop.sh`, `db_exec.sh` в Task 3. Telegram-бот — отдельный вопрос, не блокирует оркестратор.
**Pros:** Каждая задача атомарна. Можно тестировать до деплоя. Rollback стоит одного `git revert`. Не теряем Telegram-управление во время реврайта оркестратора.
**Cons:** Требует 3 отдельных autopilot-задачи вместо одной. Временно сосуществуют старые и новые файлы.
**Viability:** High

### Alternative 2: Оставить telegram-bot.py, удалить только shell-скрипты
**Instead of:** Удалять и telegram-bot.py, и orchestrator.sh
**Do this:** Заменить только orchestrator.sh + pueue-callback.sh → Python. Telegram-бот оставить as-is. notify.py оставить as-is (используется и в night-reviewer.sh, и в боте).
**Pros:** Сохраняет весь Telegram-функционал. Устраняет главную боль — хрупкость bash. Уменьшает scope переписывания с ~2800 LOC до ~1200 LOC.
**Cons:** Telegram-бот остаётся большим (~500 LOC), его тоже хотелось бы упростить.
**Viability:** High

### Alternative 3: Только db_exec.sh + qa-loop.sh (минимальный фикс ADR-017)
**Instead of:** Радикальный реврайт всего
**Do this:** Удалить только `db_exec.sh` и `qa-loop.sh` (заменить вызовы qa на dispatch через pueue из callback), оставить всё остальное.
**Pros:** Устраняет единственный реальный ADR-017 нарушитель. Минимальный риск. ~50 LOC изменений.
**Cons:** Не решает проблему хрупкости bash в orchestrator.sh/inbox-processor.sh.
**Viability:** Medium — половинчатое решение

**Verdict:** Alternative 1 (инкрементальная) — оптимальный путь. Радикальный реврайт оправдан, но только при поэтапном выполнении: сначала оркестратор+callback (без удаления Telegram), затем отдельно решить судьбу telegram-bot.py после появления замены (OpenClaw CLI-команды или headless-режим).

---

## Eval Assertions (Structured from Risk Analysis)

### Deterministic Assertions

| ID | Scenario | Input | Expected Behavior | Risk | Priority | Type |
|----|----------|-------|-------------------|------|----------|------|
| DA-1 | Удалён notify.py, night-reviewer.sh вызывает его | `night-reviewer.sh proj1 proj2` | Fails silently или explicit error | High | P0 | deterministic |
| DA-2 | Обновлён callback в pueue.yml, старые задачи в flight | Pueue задача с label `proj:SPEC-001` завершается во время миграции | Slot освобождён, phase обновлена | High | P0 | deterministic |
| DA-3 | callback.py вызван для уже обработанной задачи (дубль) | `callback.py --id 42` дважды | Идемпотентно: второй вызов — no-op | High | P0 | deterministic |
| DA-4 | db.py заблокирован callback пока orchestrator пишет | Concurrent callback + orchestrator scan | PRAGMA busy_timeout=5000 держит 5с, затем error | Med | P1 | deterministic |
| DA-5 | orchestrator.py: scan_backlog находит spec, который уже in_progress | Backlog: ARCH-161 status=queued, но pueue уже бежит | Не двойной запуск: check pueue status или slot occupied | High | P0 | deterministic |
| DA-6 | git pull падает во время autopilot | `git pull` exit != 0 | orchestrator.py продолжает цикл, не падает | Med | P1 | deterministic |
| DA-7 | pueue down при запуске orchestrator.py | `pueue status` возвращает error | Orchestrator логирует warn, пропускает цикл, не крашится | High | P0 | deterministic |
| DA-8 | SIGTERM во время active dispatch | Pueue задача в середине запуска | Graceful shutdown: slot не "залипает" навсегда | High | P0 | deterministic |
| DA-9 | test_cycle_smoke.py запускается после удаления telegram-bot.py | `pytest scripts/vps/tests/` | Все тесты проходят (удалены или переписаны) | High | P0 | deterministic |
| DA-10 | callback.py вызван для задачи night-reviewer группы | group=night-reviewer | Skip (как сейчас в pueue-callback.sh:75) | Med | P1 | deterministic |
| DA-11 | setup-vps.sh после миграции | Запуск на свежем VPS | dld-orchestrator.service указывает на orchestrator.py, не orchestrator.sh | High | P0 | deterministic |
| DA-12 | db.py: функции add_project, set_project_topic, get_nexus_cache не удалены | grep add_project в оставшихся файлах | 0 вызовов — можно удалить; или caller (admin_handler.py) уже удалён | Med | P1 | deterministic |

### Side-Effect Assertions

| ID | Affected Component | File:line | Regression Check | Priority |
|----|-------------------|-----------|------------------|----------|
| SA-1 | night-reviewer.sh | scripts/vps/night-reviewer.sh:215 | notify.py вызов — заменить или сохранить файл | P0 |
| SA-2 | tests/test_cycle_smoke.py | scripts/vps/tests/test_cycle_smoke.py:40,138 | Парсит telegram-bot.py и pueue-callback.sh по пути | P0 |
| SA-3 | tests/test_notify.py | scripts/vps/tests/test_notify.py:17 | Импортирует notify — упадёт при удалении | P0 |
| SA-4 | tests/test_approve_handler.py | scripts/vps/tests/test_approve_handler.py | Импортирует approve_handler — упадёт при удалении | P0 |
| SA-5 | setup-vps.sh systemd unit | scripts/vps/setup-vps.sh:367,394 | ExecStart для обоих сервисов — нужно обновить оба | P0 |
| SA-6 | setup-vps.sh pueue callback | scripts/vps/setup-vps.sh:226 | CALLBACK_LINE указывает на pueue-callback.sh | P0 |
| SA-7 | openclaw-artifact-scan.py | scripts/vps/openclaw-artifact-scan.py:33,47 | Парсит формат отчётов qa-loop.sh — новый callback.py должен писать тот же формат | P1 |
| SA-8 | db.py _ensure_runtime_schema | scripts/vps/db.py:24 | Держит chat_id migration — нужен ли после удаления Telegram? | P2 |
| SA-9 | .claude/rules/dependencies.md | .claude/rules/dependencies.md (все секции scripts/vps) | 15 компонентов задокументированы — нужна полная перезапись | P1 |

### Assertion Summary
- Deterministic: 12 | Side-effect: 9 | Total: 21

---

## What Breaks?

### Side Effects

| Affected Component | File:line | Why It Breaks | Fix Required |
|--------------------|-----------|---------------|--------------|
| night-reviewer.sh | scripts/vps/night-reviewer.sh:215 | Вызывает `python3 notify.py` — файл удалён | Перенести отправку inline или оставить notify.py |
| test_cycle_smoke.py | tests/test_cycle_smoke.py:40 | `Path(VPS_DIR) / "telegram-bot.py"` — файл удалён | Удалить EC-1 тест или переписать под новый файл |
| test_cycle_smoke.py | tests/test_cycle_smoke.py:138 | `Path(VPS_DIR) / "pueue-callback.sh"` — файл удалён | Удалить EC-2..EC-3,EC-7 тесты или переписать |
| test_notify.py | tests/test_notify.py:17 | `import notify` — файл удалён | Удалить test_notify.py или переписать под callback.py |
| test_approve_handler.py | tests/test_approve_handler.py | Импортирует approve_handler — файл удалён | Удалить тест |
| setup-vps.sh | setup-vps.sh:394 | `ExecStart=...telegram-bot.py` — файл удалён | Убрать dld-telegram-bot.service или переписать unit |
| setup-vps.sh | setup-vps.sh:226 | `CALLBACK_LINE=...pueue-callback.sh` — файл удалён | Заменить на путь к callback.py |
| setup-vps.sh | setup-vps.sh:367 | `ExecStart=...orchestrator.sh` — файл удалён | Заменить на `python3 orchestrator.py` |
| openclaw-artifact-scan.py | openclaw-artifact-scan.py:33,47 | Парсит заголовок `**Status:** passed` и `**Spec:** TECH-xxx` из qa-loop.sh формата | Если callback.py пишет QA report иначе — сканер сломается |
| db.py add_project | db.py:249 | Использовалась только в admin_handler.py (удалён) | Можно удалить функцию из db.py |
| db.py set_project_topic | db.py:274 | Использовалась только в telegram-bot.py (удалён) | Можно удалить |
| db.py get_nexus_cache | db.py:285 | Использовалась только в admin_handler.py (удалён) | Можно удалить |
| db.py get_project_by_topic | db.py:132 | Использовалась telegram-bot.py, photo/voice/approve_handler (удалены) | Можно удалить |
| db.py DEFAULT_CHAT_ID | db.py:19 | Читает TELEGRAM_CHAT_ID из env — нужен ли без Telegram-бота? | Если удаляем notify.py — можно убрать |

### Dependencies at Risk

| Dependency | Type | Risk | Mitigation |
|------------|------|------|------------|
| pueue daemon | API | High | callback.py вызывается pueued — аргументы должны совпадать с конфигом pueue.yml |
| pueue.yml callback config | конфиг | High | Изменение пути callback требует перезапуска pueued |
| systemd units | конфиг | High | Два unit-файла ссылаются на удаляемые файлы |
| night-reviewer.sh | shell → Python | High | Вызывает notify.py — файл в списке удаления |
| openclaw-artifact-scan.py | формат | Medium | Парсит output-формат qa-loop.sh — новый callback должен сохранить формат |
| tests/ (5 файлов) | тесты | High | Тесты сломаются при удалении целевых файлов |
| .env TELEGRAM_* vars | конфиг | Low | Больше не нужны если нет telegram-bot.py; но notify.py их читал |

---

## Test Derivation

Все тест-кейсы зафиксированы в `## Eval Assertions` выше как DA-IDs и SA-IDs.
Facilitator маппит их в EC-IDs в секции `## Eval Criteria` спеки.

---

## Questions to Answer Before Implementation

1. **Question:** Чем заменяется ручное управление оркестратором (команды /run, /status, /pause)?
   **Why it matters:** Без Telegram-бота фаундер теряет оперативный контроль. OpenClaw может читать события, но не умеет принимать команды. Если ответа нет — нельзя удалять telegram-bot.py в этом же PR.

2. **Question:** Нужен ли сохранить notify.py для night-reviewer.sh?
   **Why it matters:** night-reviewer.sh вызывает `python3 notify.py` и явно помечен как "Keep" файл. Удаление notify.py молча сломает ночные отчёты — тихая деградация без ошибок.

3. **Question:** Каков процесс zero-downtime миграции pueue callback?
   **Why it matters:** pueue.yml читается при старте daemon. Замена callback пути требует `pueue kill --wait` (ждать пустых слотов) → обновить конфиг → restart pueued. Если сделать это не атомарно — hanging slots.

4. **Question:** Сохраняет ли новый callback.py формат QA-репортов, совместимый с openclaw-artifact-scan.py?
   **Why it matters:** `openclaw-artifact-scan.py:33,47` парсит конкретный формат `**Status:** passed` и `**Spec:** TECH-xxx`. Если callback.py пишет иначе — OpenClaw перестаёт видеть результаты QA.

5. **Question:** Какие функции db.py можно удалить после удаления Telegram-файлов?
   **Why it matters:** `add_project`, `set_project_topic`, `get_nexus_cache`, `get_project_by_topic` используются только в удаляемых файлах. Оставить мёртвый код в db.py — технический долг. Но удалить без проверки grep = риск скрытых вызовов.

6. **Question:** Как обрабатывать SIGTERM в orchestrator.py во время active dispatch?
   **Why it matters:** Текущий orchestrator.sh использует `trap 'rm -f "$PID_FILE"' EXIT`. Python-версия должна явно обрабатывать сигналы и не оставлять занятые слоты без release.

---

## Final Verdict

**Recommendation:** Proceed with caution

**Reasoning:** Переписывание обосновано — shell-скрипты хрупкие, ADR-017 нарушается в qa-loop.sh, тест-покрытие bash минимально (только .bats без интеграционных), pueue-callback.sh стал монстром в 429 LOC. Python даст лучшую тестируемость, явные исключения, правильный transaction handling. Однако предложение в текущем виде содержит три критических пробела: (1) удаление notify.py при живом night-reviewer.sh, (2) сломанный тест-сюит после удаления telegram-bot.py/pueue-callback.sh, (3) отсутствие плана zero-downtime миграции.

**Conditions for success:**
1. night-reviewer.sh должен получить замену для notify.py ДО его удаления (inline отправка или оставить slim notify.py)
2. Все тесты, парсящие удаляемые файлы (test_cycle_smoke.py, test_notify.py, test_approve_handler.py), должны быть переписаны под новые файлы или удалены с явным обоснованием
3. Миграционная процедура должна быть задокументирована: порядок остановки сервисов, обновления pueue.yml, проверки что слоты пусты перед переключением
4. Telegram-бот: либо оставить в scope как отдельный, минимальный сервис (только команды), либо явно зафиксировать потерю /run, /status как принятое решение
5. Новый callback.py должен писать QA-репорты в том же формате что qa-loop.sh (openclaw-artifact-scan.py парсит `**Status:**` и `**Spec:**` хедеры)
6. Инкрементальная стратегия предпочтительна: Task 1 = orchestrator.py, Task 2 = callback.py, Task 3 = cleanup файлов + тестов
