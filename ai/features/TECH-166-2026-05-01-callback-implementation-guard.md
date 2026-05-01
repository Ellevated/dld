---
id: TECH-166
type: TECH
status: done
priority: P1
risk: R1
created: 2026-05-01
---

# TECH-166 — Callback Implementation Guard (git-diff verification before mark-done)

**Status:** done
**Priority:** P1
**Risk:** R1 (cross-cutting — затрагивает все проекты под orchestrator)

---

## Problem

`callback.py::verify_status_sync(target="done")` сейчас доверяет только `pueue exit_code=0` (per ADR-018) при автопромоушене статуса спеки и `ai/backlog.md` в `done`. Это допускает ложные `done`:

**Live precedent (2026-05-01):** awardybot/FTR-896 был помечен `done` коммитом `e89e161a`, при этом `grep -r "product_name" src/api/v2/admin src/api/v2/seller` дал **0 совпадений** — реализация не выполнена. Спека `Allowed Files` перечисляла 8 путей; из этих 8 ни один не получил content-изменений, но autopilot выполнил один из задач спеки (доковая правка / тест-only / no-op) и вышел `0`.

**Корневая причина:** `pueue success ≠ feature implemented`. Autopilot может закоммитить doc-only / test-only / unrelated change и выйти с `exit_code=0`. Callback верит коду выхода и стампует `done` в спеке + backlog + пушит в `develop`. Дальше задача "пропадает" из видимости — оркестратор её больше не подхватит, фича остаётся не сделанной.

**Blast radius:** все проекты под VDS orchestrator (awardybot, dowry, gipotenuza, plpilot, wb). Этот баг уже один раз материализовался, и в backlog есть пометка "ложно помечен done callback'ом, возвращён в queued" — но callback её перетирает на следующем цикле.

---

## Goal

Перед промоушеном спеки в `done` — проверять **факт реализации** через git: были ли коммиты, затрагивающие пути из секции `## Allowed Files` спеки, в окне с момента старта задачи. Если коммитов нет — статус идёт в `blocked` с reason="no implementation commits", вместо `done`.

**Non-goals:**
- Не оцениваем качество кода (это работа QA / review агентов).
- Не считаем LOC / не требуем минимума изменений (1 коммит в 1 allowed-файле = валидно).
- Не меняем семантику `blocked`/`failed` — только закрываем дыру в `done`.
- Не трогаем resync-логику (v3.15.6/7/8) — guard работает ДО неё.

---

## Blueprint Reference

Не применимо — TECH-задача в инфраструктуре оркестратора (`scripts/vps/`), вне business blueprint.

ADR ссылки:
- ADR-018 (Callback status enforcement) — этот fix дополняет, не отменяет.
- ADR-011 (Enforcement as Code) — git log = детерминированный SSOT факта работы, в духе ADR.

---

## Approach

### Сигнал из спеки: парсинг `## Allowed Files`

Все спеки уже имеют секцию `## Allowed Files` с явным списком путей (convention с TECH-157+; см. `template/.claude/skills/spark/`). Парсер: regex по строкам вида `` `path/to/file.ext` `` (backticked path в bullet/numbered list), от заголовка `## Allowed Files` до следующего `^## `.

Если секция отсутствует — guard **не блокирует** (degrade open: legacy спеки без allowlist). Логируем warning. Это сознательный trade-off: false-positive хуже false-negative для inflight legacy задач.

### Окно проверки: `task_log.started_at`

`db.get_task_by_pueue_id(pueue_id)` уже возвращает `started_at` (ISO8601 UTC). Используем его как нижнюю границу: `git log --since="<started_at>" --pretty=%H -- <allowed_paths...>`.

Верхняя граница не нужна — `git log` идёт от HEAD назад.

### Guard placement

В `verify_status_sync()`, новая ветка **до** `_resync_backlog_to_spec` и до auto-fix:

```python
if target == "done" and spec_file:
    if not _has_implementation_commits(project_path, spec_file, started_at):
        log.warning("STATUS_SYNC: %s — no commits touching allowed files since %s, "
                    "demoting done → blocked (no_implementation)", spec_id, started_at)
        # переписываем target на blocked + добавляем reason в спеку
        target = "blocked"
        _append_blocked_reason(spec_file, "no_implementation_commits")
```

После этого существующая auto-fix логика штатно проставит `blocked` в spec+backlog и вызовет `_git_commit_push`.

### Сигнатура callback chain

`verify_status_sync` сейчас принимает `(project_path, spec_id, target)`. Нужно протащить `started_at` или `pueue_id`, чтобы guard мог вычислить окно. Минимально-инвазивно: добавить `pueue_id: int | None = None` в сигнатуру, и в guard'е поднимать `started_at` через `db.get_task_by_pueue_id`. Default `None` сохраняет совместимость с местами, где callback вызывается без pueue context (если такие есть; проверить grep по callsites).

Если `pueue_id is None` или `started_at` не извлекается — guard degrades open (логирует, пропускает проверку). Это безопасно: hard-block только когда есть достоверные данные.

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `scripts/vps/callback.py` — добавить `_parse_allowed_files()`, `_has_implementation_commits()`, `_append_blocked_reason()`; расширить `verify_status_sync()` сигнатуру + guard-ветку; обновить callsite на L706.
2. `tests/unit/test_callback_implementation_guard.py` — **NEW** unit-тесты на парсер + guard (с tmpdir git repo).

**Forbidden:** `scripts/vps/db.py` (read-only использование существующего `get_task_by_pueue_id`), `scripts/vps/orchestrator.py` (не меняем), `pueue.yml` (не меняем — `pueue_id` уже в args).

---

## Tests

### Unit (deterministic)

**EC-1: parser — typical spec**
Дано: спека с `## Allowed Files` и 5 backticked путями.
Ожидаем: список из 5 строк, относительные пути.

**EC-2: parser — no Allowed Files section**
Дано: legacy спека без секции.
Ожидаем: `None` (sentinel "degrade open").

**EC-3: parser — section present but empty**
Дано: `## Allowed Files\n\n## Tests`.
Ожидаем: пустой список → guard трактует как "explicit empty, treat as no-impl" → block. (Edge: ловит спеки-заглушки.)

**EC-4: guard — commits touching allowed files exist**
Дано: tmpdir git repo, спека с allowed=`["src/foo.py"]`, коммит на `src/foo.py` после `started_at`.
Ожидаем: `_has_implementation_commits() == True`.

**EC-5: guard — only doc commits, no allowed-file touches**
Дано: коммит на `README.md` после `started_at`, allowed=`["src/foo.py"]`.
Ожидаем: `False` → guard demotes to blocked.

**EC-6: guard — commit before started_at**
Дано: коммит на `src/foo.py` ДО `started_at`.
Ожидаем: `False` (окно фильтрует).

**EC-7: guard — started_at None / pueue_id missing**
Ожидаем: `True` (degrade open, не блокируем).

### Integration

**EC-8: full callback flow with no-impl autopilot**
Симуляция: pueue success, спека с allowed=`["src/x.py"]`, никаких коммитов в окне.
Ожидаем: после `verify_status_sync(..., target="done", pueue_id=N)` — спека становится `blocked` (не `done`), в спеке появляется `**Blocked Reason:** no_implementation_commits`, backlog синхронизирован в `blocked`, `_git_commit_push` отработал.

**EC-9: regression — happy path не сломан**
Симуляция: pueue success, есть коммит на allowed-file.
Ожидаем: `done` проставлен в spec+backlog, поведение идентично pre-fix.

**EC-10: regression — blocked-overwrite-protection (v3.15.5/6) сохранена**
Симуляция: спека уже `blocked`, callback пытается ставить `done`.
Ожидаем: guard срабатывает первым, но существующая защита (`spec is blocked, skipping auto-fix to done`) тоже срабатывает; result — `blocked` сохранён, `_resync_backlog_to_spec` вызван. Ни одна защита не "съедает" другую.

### LLM-judge

Не применимо (полностью детерминированный fix).

---

## Tasks

### Task 1 — Parser `_parse_allowed_files(spec_path: Path) -> list[str] | None`

- Открыть spec_path, найти `## Allowed Files` (case-insensitive).
- Вытащить все backticked paths до следующего `^## ` или EOF.
- Регулярка: `` r"`([^`\n]+\.(?:py|sh|md|sql|yml|yaml|json|toml|js|ts|tsx|jsx))`" `` (расширения — расширяемый allowlist; начать с `.py`/`.sh`/`.md`/`.sql`/`.yml`).
- Возврат: `None` если секция не найдена; `[]` если найдена но пустая; `list[str]` иначе.

### Task 2 — Implementation guard `_has_implementation_commits(project_path: str, allowed: list[str], started_at: str) -> bool`

- Если `allowed is None` → return `True` (degrade open).
- Если `allowed == []` → return `False` (explicit empty = treat as no-impl).
- `git -C <project_path> log --since="<started_at>" --pretty=%H -- <allowed...>` через `subprocess.run`.
- `True` если stdout не пустой; `False` иначе.
- Любая ошибка subprocess → log warning, return `True` (degrade open).

### Task 3 — Reason annotation `_append_blocked_reason(spec_file: Path, reason: str)`

- Дописать `**Blocked Reason:** <reason>` в спеку рядом с `**Status:**`. Если уже есть — заменить.
- Idempotent.

### Task 4 — Wire into `verify_status_sync`

- Добавить параметр `pueue_id: int | None = None`.
- В начале (после spec_file lookup, до существующих guard-веток): если `target == "done"` и есть `pueue_id` и `spec_file` — поднять `started_at` через `db.get_task_by_pueue_id`, парсить allowed, вызвать guard. Если `False` — `target = "blocked"`, `_append_blocked_reason(..., "no_implementation_commits")`.
- Существующие ветки (blocked-skip-done, done-skip-blocked, auto-fix) идут после без изменений.

### Task 5 — Update callsite (L706)

- Передать `pueue_id` в `verify_status_sync`. Все остальные callsites — grep, обновить или оставить дефолтом.

### Task 6 — Tests

- `tests/unit/test_callback_implementation_guard.py` с EC-1..EC-7 + EC-10.
- `tests/integration/test_callback_no_impl_demote.py` с EC-8, EC-9 (tmpdir + sqlite + fake spec/backlog).

### Task 7 — Update ADR-018

- В `.claude/rules/architecture.md` дописать пометку: "ADR-018 расширён TECH-166 — implementation guard перед mark-done через git log по Allowed Files".

---

## Eval Criteria

| ID | Type | Description |
|----|------|-------------|
| EC-1 | deterministic | Parser извлекает paths из стандартной `## Allowed Files` |
| EC-2 | deterministic | Parser возвращает `None` для legacy спек без секции |
| EC-3 | deterministic | Parser отличает empty section от missing section |
| EC-4 | deterministic | Guard True при наличии коммита на allowed-file в окне |
| EC-5 | deterministic | Guard False при коммитах ТОЛЬКО на не-allowed файлах |
| EC-6 | deterministic | Guard False при коммитах до `started_at` |
| EC-7 | deterministic | Guard True при отсутствии `started_at`/`pueue_id` (degrade open) |
| EC-8 | integration | Full callback demotes done→blocked при no-impl, пишет reason |
| EC-9 | integration | Happy path с реальным impl коммитом ставит done без регрессии |
| EC-10 | integration | Защита от overwrite blocked→done (v3.15.6) совместима с новым guard |

**Pass threshold:** 10/10.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Спеки без `## Allowed Files` (legacy) ложно демотятся | Degrade open: `None` → пропуск guard. Только explicit empty section блокирует. |
| Autopilot работает в worktree, коммиты приходят в develop позже | `started_at` берётся из `task_log` (момент диспатча), `git log` смотрит уже смерженный develop. После merge fast-forward в callback — коммиты на месте. Если merge ещё не произошёл к моменту callback (race) — false demote. **Mitigation:** callback и так ждёт `pueue` finish, autopilot пушит ДО `exit 0`. Race маловероятна. Если проявится — добавить retry с backoff (out of scope этой спеки). |
| Allowed-files в спеке указаны неточно (autopilot правил file X, не вошедший в allowlist) | Это уже нарушение Spark-контракта (`Explicit Allowlist` принцип). Guard правильно блокирует — операторская проверка вытащит расхождение. |
| `_git_commit_push` после demote триггерит callback повторно | Существующая дедупликация по pueue_id обработает. Проверить: callback не вызывает себя на свой commit (commit message паттерн `chore(callback)`). |

---

## Action Required

Нет — все решения локальны, без founder ACK.

---

## Reference

- Live case: awardybot/FTR-896, commit `e89e161a` (false done), запись в `~/projects/awardybot/ai/backlog.md` строка FTR-896 ("ложно помечен done авто-callback'ом").
- callback.py:491 `verify_status_sync()` — точка интеграции guard.
- ADR-018 (`.claude/rules/architecture.md`) — текущая семантика callback enforcement.
- v3.15.5/6/7/8 commits (e0b6b90, 204ded1, 73219a9, f1f0238) — недавние правки status-sync, с которыми не должны конфликтовать.
