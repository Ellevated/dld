# Codebase Research — BUG-164: callback.py pueue CLI uses wrong socket

## Existing Code

### Reusable Modules

| Module | File:line | Description | Reuse how |
|--------|-----------|-------------|-----------|
| `db.task_log` table | scripts/vps/schema.sql:35 | pueue_id, project_id, task_label, skill уже хранятся вместе | Import directly — позволяет заменить `resolve_label` + `extract_agent_output` на DB lookup |
| `db.finish_task` | scripts/vps/db.py:156 | принимает output_summary — поле есть, но сейчас передаётся None | Extend — claude-runner должен писать summary сюда, не в отдельный log-файл |
| claude-runner log files | scripts/vps/logs/{project}-{timestamp}.log | JSON с полями skill, result_preview, exit_code | Читать напрямую вместо pueue log |

### Similar Patterns

| Pattern | File:line | Description | Similarity |
|---------|-----------|-------------|------------|
| `get_live_pueue_ids` | scripts/vps/orchestrator.py:97 | вызывает `pueue status --json`, тот же потенциальный socket-риск | Та же проблема, но в orchestrator — при изменении callback нужно изменить и это место |
| `is_agent_running` | scripts/vps/orchestrator.py:144 | `pueue status --json` без XDG_RUNTIME_DIR | Та же проблема |
| `_pueue_add` (orchestrator) | scripts/vps/orchestrator.py:220 | subprocess pueue без socket env | Та же проблема |

**Recommendation:** Заменить `pueue log` и `pueue status` в callback.py на чтение из DB + log-файлов claude-runner. Для `pueue add` (dispatch QA/reflect) — передать XDG_RUNTIME_DIR из pueue daemon environment.

---

## Impact Tree Analysis

### Step 1: UP — Who uses changed code?

```bash
grep -r "from.*callback\|import callback" scripts/vps/ --include="*.py"
# Results: 0 direct imports (callback.py вызывается как subprocess из pueue daemon)
```

Callback вызывается напрямую pueue daemon через pueue.yml callback config (не импортируется).

| Trigger | Context |
|---------|---------|
| pueue.yml line 17 | `python3 callback.py {{ id }} '{{ group }}' '{{ result }}'` |

### Step 2: DOWN — What does it depend on?

| Dependency | File | Function |
|------------|------|----------|
| db | scripts/vps/db.py | release_slot, finish_task, update_project_phase, get_project_state |
| event_writer | scripts/vps/event_writer.py | notify() |
| pueue CLI | subprocess | status --json, log --json, add |

### Step 3: BY TERM — Grep key terms

```bash
grep -rn "pueue.*status\|pueue.*log\|subprocess.*pueue" scripts/vps/ --include="*.py"
```

| File | Line | Context |
|------|------|---------|
| scripts/vps/callback.py | 65 | `["pueue", "status", "--json"]` — resolve_label |
| scripts/vps/callback.py | 96 | `["pueue", "log", pueue_id, "--json"]` — extract_agent_output |
| scripts/vps/callback.py | 156 | `["pueue", "status", "--json"]` — is_already_queued |
| scripts/vps/callback.py | 174 | `["pueue", "add", ...]` — _pueue_add |
| scripts/vps/orchestrator.py | 101 | `["pueue", "status", "--json"]` — get_live_pueue_ids |
| scripts/vps/orchestrator.py | 148 | `["pueue", "status", "--json"]` — is_agent_running |
| scripts/vps/orchestrator.py | 222 | `["pueue", "add", ...]` — _pueue_add |

**Итого pueue CLI вызовов:**
- callback.py: 4 функции (resolve_label, extract_agent_output, is_already_queued, _pueue_add)
- orchestrator.py: 3 функции (get_live_pueue_ids, is_agent_running, _pueue_add)

### Step 4: CHECKLIST — Mandatory folders

- [ ] `tests/**` — 0 файлов для vps/ (нет тестов на callback.py)
- [ ] `db/migrations/**` — N/A (SQLite, schema.sql)
- [ ] `ai/glossary/**` — N/A

### Step 5: DUAL SYSTEM check

Не затрагиваем смену источника данных, но есть dual-access к task output:
- **Текущий путь (сломан):** callback.py -> `pueue log <id> --json` -> получает output из pueued
- **Альтернативный путь (рабочий):** callback.py -> `scripts/vps/logs/{project}-{ts}.log` -> читает JSON напрямую

claude-runner.py пишет лог в `LOG_DIR / f"{project_name}-{time.strftime('%Y%m%d-%H%M%S')}.log"` (строка 77).

---

## Affected Files

| File | LOC | Role | Change type |
|------|-----|------|-------------|
| scripts/vps/callback.py | 342 | Pueue callback — resolve label, extract output, dispatch QA/reflect | modify |
| scripts/vps/db.py | 373 | SQLite helpers | read-only (task_log уже достаточен) |
| scripts/vps/schema.sql | 70 | DB schema | read-only |
| scripts/vps/claude-runner.py | 227 | Agent SDK runner, writes logs | read-only |
| scripts/vps/orchestrator.py | 399 | Orchestrator daemon — тоже вызывает pueue status | modify (опционально, те же функции) |
| /home/dld/.config/pueue/pueue.yml | 34 | Pueue daemon config — callback command, socket path | read-only |

**Total:** 2 файла modify, 4 read-only

---

## Reuse Opportunities

### Import (use as-is)

- `db.task_log` query — `SELECT project_id, task_label, skill FROM task_log WHERE pueue_id = ?` — полностью заменяет `resolve_label()`. task_log уже содержит project_id, task_label, skill.
- `db.finish_task(pueue_id, status, exit_code, summary)` — аргумент `summary` уже есть в сигнатуре, но callback передаёт None. Можно передавать preview из log-файла сюда.

### Extend (subclass or wrap)

- `extract_agent_output` — вместо `pueue log --json` читать последний файл из `scripts/vps/logs/` по паттерну `{project_name}-*.log`, sorted by mtime. Файл содержит JSON с `skill` и `result_preview`.

### Pattern (copy structure, not code)

- Как `get_live_pueue_ids` в orchestrator.py возвращает `None` при ошибке и защищает от false-release — такой же "fail-safe None" паттерн нужен в callback при недоступности pueue.

---

## Core Problem Analysis

### Почему `pueue log/status` может подключиться к неправильному socket

Pueue использует Unix socket. Путь к socket определяется через `XDG_RUNTIME_DIR` (по умолчанию `/run/user/<uid>/pueue_<username>.socket`).

**Факты:**
1. Реальный socket: `/run/user/1000/pueue_dld.socket` (найден в системе)
2. Callback вызывается pueue daemon как subprocess
3. В pueue.yml: `runtime_directory: null`, `unix_socket_path: null` — pueue сам определяет путь по XDG_RUNTIME_DIR
4. Systemd user service (`dld-orchestrator.service`) получает `XDG_RUNTIME_DIR=/run/user/1000` автоматически
5. **Проблема:** pueue daemon при запуске callback НЕ обязательно передаёт `XDG_RUNTIME_DIR` в subprocess среду. Это зависит от версии pueue и способа запуска.
6. В pueue.yml: `env_vars: {}` — никаких дополнительных env vars не передаётся callback subprocess

**Вывод:** когда pueue daemon запускает callback.py как subprocess, subprocess может не иметь `XDG_RUNTIME_DIR`, и `pueue` CLI внутри него пытается найти socket в другом месте (например `/tmp/pueue_dld.socket`) — что ведёт к connection refused или подключению к другому pueued instance.

**Подтверждение в логах:** callback-debug.log показывает, что `agent output: skill= preview_len=0` — это именно `extract_agent_output` возвращает `("", "")` потому что `pueue log` не может получить данные.

### Функции callback.py с pueue CLI — полная карта

| Функция | Строки | Команда | Критичность | Риск socket |
|---------|--------|---------|-------------|-------------|
| `resolve_label` | 62-73 | `pueue status --json` | КРИТИЧНО — без label весь callback деградирует | HIGH |
| `extract_agent_output` | 92-121 | `pueue log <id> --json` | Важно — нужно для QA dispatch и events | HIGH |
| `is_already_queued` | 153-168 | `pueue status --json` | Защита от дублей QA/reflect | HIGH |
| `_pueue_add` | 171-187 | `pueue add ...` | Dispatch QA и reflect | HIGH |

**Все 4 функции потенциально затронуты.**

### Почему `resolve_label` не работает через DB

`task_log` содержит `pueue_id`, `project_id`, `task_label`, `skill` — это **уже достаточно** для замены `resolve_label`. Данные записываются в `orchestrator.py:282-283` (`db.try_acquire_slot` + `db.log_task`) до запуска задачи в pueue.

### Почему `extract_agent_output` не работает через log-файлы

claude-runner.py пишет лог по паттерну `{project_name}-{YYYYMMDD-HHMMSS}.log` в `scripts/vps/logs/`. Файл содержит JSON с полями `skill` и `result_preview`. Callback получает `pueue_id`, по которому можно найти `project_id` через DB, а затем последний log-файл этого проекта по mtime.

---

## Git Context

### Recent Changes to Affected Areas

```bash
git log --oneline -5 -- scripts/vps/callback.py scripts/vps/orchestrator.py scripts/vps/db.py scripts/vps/claude-runner.py
```

| Date | Commit | Summary |
|------|--------|---------|
| 2026-03-19 | a848837 | fix(orchestrator): add orphan slot watchdog (BUG-162) |
| 2026-03-19 | a5b603e | fix(runner): increase TIMEOUT 30→60 min |
| 2026-03-18 | 1260381 | fix(runner): increase MAX_TURNS 30→80 |
| 2026-03-18 | 6c18d02 | refactor(orchestrator): radical rewrite ARCH-161 |
| 2026-03-18 | fdcaffb | fix: multi-layer spec_id resolution for QA dispatch (BUG-159) |

**Observation:** ARCH-161 (6c18d02) — радикальный переход с bash на Python, после чего callback.py стал полагаться на `pueue log/status` вместо прямого чтения файлов. BUG-164 — следствие этого архитектурного перехода.

---

## Risks

1. **Risk:** resolve_label через DB может вернуть "unknown" если task не залогирован (race: callback раньше db.log_task)
   **Impact:** label="unknown", весь callback деградирует
   **Mitigation:** db.log_task вызывается в orchestrator.py ДО pueue add (строки 282-283), поэтому к моменту callback задача уже в DB. Race невозможен.

2. **Risk:** log-файл claude-runner может не существовать при ошибке запуска (exit_code=2/3 из SDK)
   **Impact:** extract_agent_output вернёт ("","") — как сейчас
   **Mitigation:** поиск по glob с fallback на ("","") — то же поведение что сейчас

3. **Risk:** _pueue_add в callback (dispatch QA/reflect) тоже использует pueue CLI — socket-проблема останется для dispatch
   **Impact:** QA и reflect не диспатчатся
   **Mitigation:** передать XDG_RUNTIME_DIR явно в subprocess.run() для pueue add. В callback env уже есть XDG_RUNTIME_DIR (подтверждено: printenv внутри pueue task показал XDG_RUNTIME_DIR=/run/user/1000). Для pueue add достаточно передать текущий os.environ.

4. **Risk:** orchestrator.py тоже вызывает pueue status без явного socket env
   **Impact:** orphan slot watchdog и is_agent_running могут ломаться при некоторых условиях запуска
   **Mitigation:** orchestrator запускается через systemd --user, который гарантирует XDG_RUNTIME_DIR. Риск ниже чем для callback, но для полноты можно добавить явную передачу env.
