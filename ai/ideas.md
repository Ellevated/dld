# Ideas

Out-of-scope findings, future improvements, and architectural notes.

## Out of Scope from BUG-106 (2026-02-16)

- **Object URL not revoked when file changes during preview** (A-CR-011) — Minor memory leak (50MB over 10 selections); low impact, theoretical concern
- **waitForElement rejection not handled** (A-CR-003) — Merged into F-039 (widget init error UX). Error IS caught, just message is generic.
- **Converted total calculated even when only one currency** (B-CR-009) — Performance micro-optimization; no user-facing bug
- **Redundant currency check when allCurrencies.size === 1** (B-CR-010) — Code clarity issue, not a bug; naming improvement only
- **Unique key uses compound id+date but entries are from expandPayments** (B-CR-014) — Code is actually correct; finding is a documentation suggestion
- **Locale hardcoded to ru-RU breaks international users** (B-QA-004) — PLPilot is a Russian-language app; i18n is a feature request not a bug
- **Relative date labels hardcoded in Russian** (B-QA-029) — Same as above — i18n feature request, not bug for Russian-only app
- **File validation rejects non-JPEG/PNG/WebP even if ACCEPTED_TYPES expands** (A-QA-012) — Hypothetical — ACCEPTED_TYPES is NOT being expanded; code is correct as-is
- **Billing history shows YooKassa payment IDs without redaction** (A-SEC-012) — Low-risk information disclosure; payment IDs alone are not sensitive without API keys
- **Competitor pricing sent to AI without validation could leak business intelligence** (A-SEC-013) — Theoretical concern; user voluntarily inputs this data; AI training opt-out is separate concern
- **YooKassa widget errors logged to console may expose sensitive data** (A-SEC-014) — Console.error logging is standard practice; sensitive data exposure requires malicious browser extension
- **Variable named 'date' but contains Date object, not date string** (C-JR-003) — Naming convention preference, zero user impact
- **Loading state shows only text, no spinner or skeleton (cards)** (C-UX-008) — UI polish, not a bug; text loading indicator is functional
- **Loading state shows only text, no spinner or skeleton (tags)** (C-UX-009) — Same as above; UI polish
- **Tags section hidden when no tags exist** (A-UX-023) — Feature discoverability, not a bug; design decision
- **Form reset on dialog close loses unsaved changes without confirmation** (A-UX-027) — Nice-to-have UX improvement; not a bug — standard dialog behavior
- **Custom period_days allows up to 3650 days (10 years)** (A-JR-006) — Intentional generous limit; not a bug
- **parseCents allows empty whole part like '.50'** (A-JR-017) — Mathematically correct behavior (.50 = $0.50); not a bug
- **parseCents: normalized === '' check is dead code** (A-JR-018) — Dead code, not a bug; defensive programming
- **IIFE in JSX for converted total is hard to debug and test** (B-QA-016) — Code style preference, not a bug
- **daysSince calculation can be negative due to clock changes** (B-QA-019) — Edge case with manual clock manipulation; minor UX impact
- **Monthly summary day selector limited to 28 days** (D-QA-005) — Intentional design to handle February reliably; not a bug
- **Fallback to localStorage breaks multi-device sync** (D-ARCH-004) — Architectural concern about dual-state; not a bug in single-device use
- **No indication of which payment is being refunded** (A-UX-013) — UX improvement; refund targets latest payment which is correct behavior
- **No validation feedback for last_four input** (C-UX-003) — Minor UX polish; Zod validation catches on submit
- **cheapest_regions array rendered without key uniqueness validation** (A-QA-022) — Defensive coding; backend data is unlikely to have duplicate country codes
- **Russian pluralization breaks for numbers 11-14** (B-QA-010) — Finding itself concludes the code IS correct for Russian pluralization

## Out of Scope from BUG-115 (2026-02-17)

- Add hooks-config.json for project-specific allowed/blocked pattern overrides (A-SA-001) — architectural enhancement, not a bug; config system is a new feature
- Support worktree-local .claude/hooks/ directory with fallback to main repo (A-SA-003) — feature request for advanced git worktree workflows; not a defect
- Create hooks-manifest.json for programmatic hook discovery (A-SA-004) — developer tooling improvement; no current user-facing breakage
- Add optional verbose logging mode for hook dispatch debugging (A-SA-007) — observability enhancement; current silent exit is by design (ADR-004 fail-safe)
- Add early guard for empty file_path as defense-in-depth (A-JD-004) — defensive coding improvement; current behavior catches error downstream without data loss


## Epoch-safe идентификация прогонов в task_log (2026-08-24)

Найдено при чистке истории pueue. `pueue_id` используется как идентификатор прогона между тремя
системами (pueue → callback CLI-аргумент → `orchestrator.db`), но он переиспользуемый: pueue не
хранит `next_id`, а считает его как `max(id) + 1`. Обычный `pueue clean` при пустой очереди
откатывает счётчик к нулю — мину взводит рутинная уборка, не авария. Реально случилось в мае 2026:
счётчик сброшен с ~2803 на 186, в `task_log` осталось 45 записей с `finished_at IS NULL`.

Три пути ловят коллизию по-разному (воспроизведено на временной БД 2026-08-24):

1. `db.finish_task` (`db.py:251`) — `UPDATE ... WHERE pueue_id = ? AND finished_at IS NULL` без
   LIMIT: закрывает ОБЕ строки, старая получает статус и `output_summary` чужого прогона.
2. `db.get_task_by_pueue_id` (`db.py:302`) — `ORDER BY id DESC LIMIT 1`. Помогает, только если
   новая строка уже вставлена; в окне между `_pueue_add` и `log_task` её ещё нет → `resolve_label`
   в callback вернёт СТАРЫЙ `project_id`, и результат уедет чужой спеке в чужом проекте.
3. `callback._get_started_at` (`callback.py:588`) — та же выборка задаёт окно implementation
   guard'а; старая строка раскрывает его на месяцы назад.

Гонка в п.2 не теоретическая: 116 из 3032 прогонов (4%) завершались быстрее 3 секунд
(`run-agent.sh:37`, RAM-гейт `exit 78`), а `log_task` идёт после `try_acquire_slot`
(`BEGIN IMMEDIATE`, `busy_timeout=5000`).

Класс уже латали точечно: `ORDER BY id DESC LIMIT 1` добавлен в BUG-164 как ответ на ту же
коллизию — закрыли один путь из трёх. Ещё один точечный LIMIT повторит ту же ошибку.

Предлагаемое направление (не спека, обсудить):
- `finish_task` при закрытии обнуляет `pueue_id` строки (перенос в `pueue_id_hist` для отладки) —
  тогда поиск по `pueue_id` видит только живые прогоны, и пути 2-3 закрываются без фильтров;
- reaper висяков на старте оркестратора (аналог `startup_reconcile`, но для `task_log`) — его
  отсутствие и есть причина, по которой майские 45 строк дожили до августа.

Риск: миграция схемы прод-БД оркестратора = R1. Обходной паллиатив, действующий сейчас: чистить
историю pueue только частично, всегда оставляя задачу с максимальным id, чтобы счётчик не
откатывался (так сделана чистка 2026-08-24: удалено 809 задач старше 30 дней, `state.json`
2.1 МБ → 364 КБ).

## reconcile_if_implemented принимает salvage-дамп за реализацию (2026-08-25)

`orchestrator_queue.reconcile_if_implemented` закрывает queued-спеку как `done`, если в
origin/develop нашёлся коммит, упоминающий spec_id и трогающий файлы из `## Allowed Files`
(`gate_logic.find_implementation_commit`). Проверяется факт коммита, но не его природа.

Между тем `salvage.py` по прямому решению (комментарий в `claude-runner.py:99`: «A dead run is
not lost work: salvage.py pushes the branch either way») пушит незаконченную работу после
таймаута — коммитом вида `wip(BUG-478): salvaged after timeout — not reviewed, not tested`.
Когда такая ветка позже попадает в develop, следующий проход оркестратора видит «реализация
есть» и закрывает спеку.

Замер по всем 10 проектам: через reconcile закрыто **20** спек (awardybot 11, dowry 3,
dowry-mc 3, plpilot 2, wb 1). Из них сомнительных четыре:
- `dowry BUG-477` → закрыт 23.08 по `wip(BUG-477): salvaged after timeout — not reviewed,
  not tested`. Код в коммите есть (tracker.py +140), но он не проходил ни ревью, ни тестов.
  Остаток работы позже оформили отдельной спекой BUG-479 («остаток дрейфа кода и схемы —
  14 мест, продолжение BUG-477»).
- `dowry BUG-478` → закрыт 25.08 по `wip(BUG-478): salvaged after timeout…`, где из
  Allowed Files затронут только `tests/unit/domains/escalations/test_mapper.py` (+428).
  Настоящая реализация — merge `cc1b6897`, а он прямо говорит: «Task 1 — миграция
  escalations.context + mapper (Tasks 2-8 остались)». Спека из 8 задач закрыта на одной.
- `wb FTR-182` → закрыт по коммиту `lifecycle(FTR-182): queued`, то есть по служебной записи
  статуса, а не по коду вообще.
- `dowry BUG-467` → закрыт по коммиту `bc6e10465e`, чьё сообщение не читается в текущем репо.

Отдельно тяжело то, что ошибка необратима: `done` терминален (Rule 7, ADR-025 write-once-done),
`spec_operator.py demote --blocked` отвечает «cannot transition done → blocked». Ложно закрытую
спеку нельзя переоткрыть — остаётся только заводить спеку-продолжение, как сделали с
BUG-477 → BUG-479.

Направление (обсудить, не спека):
- отсеивать по сообщению коммита: `wip(`, `salvaged`, `not reviewed`, `not tested`, `lifecycle(`
  не могут служить доказательством реализации;
- либо требовать, чтобы совпадение было не по любому файлу из Allowed Files, а по коду
  (не только `tests/**` и не только служебные файлы вроде `autopilot-state.json`);
- либо, как минимум, разделить: salvage пушит ветку — но помечает коммит так, чтобы гейт его
  никогда не засчитал (например, префикс, который `find_implementation_commit` исключает).
