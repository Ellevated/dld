# FTR-882 — Гибкий SLA: истечение в 00:00 МСК "до ребаланса"

**Status:** done
**Priority:** P1
**Date:** 2026-04-29
**Type:** FTR

---

## Problem

SLA дедлайны на шагах слота (особенно PICKUP) рассчитываются жёстко по часам:
`deadline = assigned_at + N_hours`. Байер взял слот в 14:00 — дедлайн в 14:00+2d.
Если товар пришёл утром, а байер идёт забирать после работы в 19:00-20:00 — не успевает,
слот сбрасывается, байер в минусе. Для multi-day шагов (PICKUP, RECEIPT, UGC_TEXT, UGC_PUBLISHED)
дедлайн на час внутри рабочего дня — UX anti-pattern: справедливая единица — calendar day, а не clock time.

**Kill question:** если не делаем — через 3 месяца SLA violations на PICKUP продолжают накапливаться,
доля expired_assigned растёт, drain rate кампаний деградирует, байеры теряют доверие к платформе.

---

## Solution

Для multi-day шагов: дедлайн = **первая полночь по МСК (00:00 МСК = 21:00 UTC), наступающая
строго после момента `from_time + N_hours`**. Это даёт байеру "конец дня", а не "тот же час".

Дедлайн всегда наступает в 21:00 UTC — за **6 часов** до `rebalance-daily` (03:00 UTC).
Freed slots попадают в очередной утренний цикл перераспределения.

**Per-step policy (snap vs no-snap):**

| Step | SLA (minutes) | Calendar snap? | Reason |
|------|--------------|----------------|--------|
| SEARCH | 30 | NO | Sub-hour — snap смысла нет |
| ORDER | 60 | NO | Sub-hour — snap смысла нет |
| PICKUP (standard) | 7d = 10080 | YES | Multi-day, physical pickup |
| PICKUP (eta2) | 2d = 2880 | YES | Multi-day, physical pickup |
| RECEIPT | 3d = 4320 | YES | Multi-day |
| UGC_TEXT (standard) | 5d = 7200 | YES | Multi-day |
| UGC_TEXT (eta2) | 3d = 4320 | YES | Multi-day |
| UGC_PHOTO | 1d = 1440 | YES | Calendar day |
| UGC_VIDEO | 2d = 2880 | YES | Multi-day |
| UGC_PUBLISHED (standard) | 5d = 7200 | YES | Multi-day |
| UGC_PUBLISHED (eta2) | 3d = 4320 | YES | Multi-day |

**Short-SLA steps (SEARCH, ORDER) используют старую логику без изменений.**

---

## Approaches

### Approach A: Snap to next midnight MSK after N hours (SELECTED — founder's proposal + scout synthesis)

```python
def snap_to_midnight_msk(nominal: datetime) -> datetime:
    """Snap nominal deadline to next 00:00 MSK >= nominal.

    Russia uses fixed UTC+3 (no DST since 2014) — zoneinfo not required.
    MSK constant already in src/shared/timezone.py.
    """
    from src.shared.timezone import MSK, utc_to_msk
    nominal_msk = utc_to_msk(nominal)
    # Next calendar midnight: replace time with 00:00, add 1 day
    next_midnight_msk = nominal_msk.replace(
        hour=0, minute=0, second=0, microsecond=0
    ) + timedelta(days=1)
    return next_midnight_msk.astimezone(UTC)
```

**Trade-off:** +fairness для байеров, небольшой дополнительный hold для селлера (до 23h 59min).
**Late-night edge case:** заказ в 23:01 МСК + 2d window → номинальный дедлайн 23:01+2d → snap на
следующую полночь = 3 calendar дня. Это приемлемо: физически байер не потерял — он ждёт
ровно 2 полных дня + максимум 59 минут до следующей полуночи.

### Approach B: Fixed grace buffer (NOT SELECTED)

`deadline = from_time + N_hours + 6h`. Проще, но:
- Не выравнивает на понятную для байера метку (00:00)
- Нотификации шлются в непредсказуемые часы
- Нет синхронизации с rebalance

### Approach C: Business hours only (NOT SELECTED)

Считать только 9:00-21:00 МСК. Сложность несоразмерна выгоде, непривычно для маркетплейса.

### Approach D: Увеличить N на 25% (NOT SELECTED)

Тупо +N часов везде. Решает проблему для середины дня, не решает для вечерних заказов.

---

## Implementation Plan

### Task 1: Добавить `snap_to_midnight_msk()` в `src/shared/timezone.py`

**File:** `src/shared/timezone.py`

Добавить функцию `snap_to_midnight_msk(nominal: datetime) -> datetime`:
- Принимает datetime (UTC или tz-aware)
- Возвращает первую 00:00 МСК строго ПОСЛЕ `nominal`
- Экспортировать в `__all__`

Алгоритм:
```python
def snap_to_midnight_msk(nominal: datetime) -> datetime:
    if nominal.tzinfo is None:
        nominal = nominal.replace(tzinfo=UTC)
    nominal_msk = nominal.astimezone(MSK)
    # Next midnight = same date + 1 day at 00:00
    next_midnight_msk = (nominal_msk + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return next_midnight_msk.astimezone(UTC)
```

**Note:** `(nominal_msk + timedelta(days=1)).replace(...)` корректнее чем `.replace(...) + timedelta(days=1)` — избегает edge case когда `nominal_msk.hour == 0, minute == 0` (совпадение с полуночью).

### Task 2: Добавить `SLA_CALENDAR_SNAP_STEPS` + `sla_use_calendar_snap()` в `Timers`

**File:** `src/infra/config/timers.py`

```python
# Steps where calendar-day snapping applies (multi-day only)
SLA_CALENDAR_SNAP_STEPS = frozenset({
    SlotStep.PICKUP,
    SlotStep.RECEIPT,
    SlotStep.UGC_TEXT,
    SlotStep.UGC_PHOTO,
    SlotStep.UGC_VIDEO,
    SlotStep.UGC_PUBLISHED,
})

@staticmethod
def sla_use_calendar_snap(step: SlotStep) -> bool:
    """Whether to snap deadline to next 00:00 MSK for this step.

    Only applies to multi-day steps. TEST_MODE: returns False
    (preserves fast E2E cycle — physical pickup not acceleratable anyway).
    """
    if settings.is_test_mode:
        return False
    return step in SLA_CALENDAR_SNAP_STEPS
```

### Task 3: Обновить `_calculate_deadline()` в `src/domains/campaigns/services/slot_lifecycle.py`

**File:** `src/domains/campaigns/services/slot_lifecycle.py`

Текущий код:
```python
def _calculate_deadline(step, from_time=None, is_eta2=False):
    if from_time is None:
        from_time = utc_now()
    deadlines = get_step_deadlines_minutes(is_eta2)
    minutes = deadlines.get(step, 1440)
    return from_time + timedelta(minutes=minutes)
```

Новый код:
```python
def _calculate_deadline(step, from_time=None, is_eta2=False):
    if from_time is None:
        from_time = utc_now()
    deadlines = get_step_deadlines_minutes(is_eta2)
    minutes = deadlines.get(step, 1440)
    nominal = from_time + timedelta(minutes=minutes)
    if Timers.sla_use_calendar_snap(step):
        from src.shared.timezone import snap_to_midnight_msk  # lazy import
        return snap_to_midnight_msk(nominal)
    return nominal
```

**Also update:** `slot_validation.py:calculate_step_deadline()` — это тот же паттерн, нужно убедиться, что оба места используют одинаковую логику (grep `calculate_step_deadline`).

### Task 4: Обновить тест `src/infra/config/timers_test.py`

Добавить тесты для `sla_use_calendar_snap()`:
- PICKUP, RECEIPT, UGC_TEXT, UGC_PHOTO, UGC_VIDEO, UGC_PUBLISHED → True (prod)
- SEARCH, ORDER → False (prod)
- Any step → False (TEST_MODE)

### Task 5: Создать unit-тесты для `snap_to_midnight_msk()`

**File:** `tests/shared/test_timezone.py` (новый или существующий)

Обязательные кейсы (см. Eval Criteria).

### Task 6: Обновить интеграционный тест SLA checker

**File:** `src/domains/campaigns/services/sla_checker_test.py`

Убедиться что тест с fake `now()` покрывает сценарий "дедлайн в 21:01 UTC, проверка в 21:05 UTC — слот сбрасывается".

### Task 7: Обновить `slot_validation.py:calculate_step_deadline` (УТОЧНЕНО planner-ом)

**File:** `src/domains/campaigns/services/slot_validation.py:101-111`

**Что обнаружено в коде (planner re-read):**
- `calculate_step_deadline` (строки 101-111) — это **независимая копия** логики `_calculate_deadline` (НЕ делегат)
- Экспортируется через `slot_machine.calculate_deadline = staticmethod(calculate_step_deadline)` в `slot_machine.py:73`
- В production коде НЕ вызывается напрямую — production использует `_calculate_deadline` через `assign_slot_to_buyer` / `advance_slot_step`
- Единственный потребитель: `src/domains/campaigns/slot_machine_test.py::TestDeadlines` (3 теста)
- Циклический импорт `slot_validation → slot_lifecycle` НЕВОЗМОЖЕН (`slot_lifecycle.py:32` уже импортирует `slot_validation.py`)

**Решение:** дублировать snap-логику в `calculate_step_deadline` идентично с `_calculate_deadline`:

```python
def calculate_step_deadline(
    step: SlotStep,
    from_time: datetime | None = None,
    is_eta2: bool = False,
) -> datetime:
    """Calculate deadline for a step (with end-of-day MSK snap for multi-day steps, FTR-882)."""
    if from_time is None:
        from_time = utc_now()
    deadlines = get_step_deadlines_minutes(is_eta2)
    minutes = deadlines.get(step, 1440)
    nominal = from_time + timedelta(minutes=minutes)
    # FTR-882: snap multi-day deadlines to next 00:00 MSK
    from src.infra.config.timers import Timers  # noqa: PLC0415 — lazy import to avoid cycle
    if Timers.sla_use_calendar_snap(step):
        from src.shared.timezone import snap_to_midnight_msk  # noqa: PLC0415
        return snap_to_midnight_msk(nominal)
    return nominal
```

**Compatibility check (planner-verified):**
- `slot_machine_test.py::test_calculate_deadline_from_specific_time` — uses naive `datetime(2025, 1, 1, 12, 0, 0)` with SEARCH step. SEARCH не в SLA_CALENDAR_SNAP_STEPS → snap не применяется → naive остаётся naive → тест проходит без правок.
- `slot_machine_test.py::test_eta2_deadlines_different` — uses naive start_time с PICKUP. PICKUP в SLA_CALENDAR_SNAP_STEPS → snap применяется к обеим сторонам (`is_eta2=False` и `is_eta2=True`) → обе стороны UTC-aware → сравнение `eta2_deadline <= normal_deadline` работает (aware vs aware) → тест проходит без правок.
- `slot_machine_test.py::test_calculate_deadline_from_now` — uses default `from_time=None` → `utc_now()` aware → SEARCH без snap → aware + 30min → aware. Сравнение `deadline > utc_now()` aware vs aware → OK.

**Вывод:** `slot_machine_test.py` НЕ требует изменений (НЕ в Allowed Files). Все 3 теста сохранят работоспособность.

### Task 8: Migration (активные слоты — НЕ пересчитывать)

**Решение:** Новая логика применяется ТОЛЬКО к слотам, которые будут ассайнены ПОСЛЕ деплоя.
Активные in-flight слоты сохраняют текущие дедлайны. Причины:
1. Байер уже знает свой дедлайн (уведомлён)
2. Retroactive shift = неожиданное изменение для всех сторон
3. Нет данных о том, что в текущих active слотах дедлайн "несправедлив"

**Документировать в changelog:** "SLA calendar snap applies to newly assigned slots only".

**Если нужен backfill** (founder решает отдельно): `scripts/admin/backfill_sla_calendar_snap.py`
(по аналогии с `scripts/admin/backfill_eta2_deadlines.py` — dry-run + CSV + notification).
Этот файл НЕ входит в основной деплой этой фичи.

---

## Allowed Files

Файлы, которые МОЖНО изменить:

```
src/shared/timezone.py                                      # Task 1: add snap_to_midnight_msk
src/shared/timezone_test.py                                 # Task 5: unit tests for new function
src/infra/config/timers.py                                  # Task 2: SLA_CALENDAR_SNAP_STEPS + sla_use_calendar_snap
src/infra/config/timers_test.py                             # Task 4: tests for sla_use_calendar_snap
src/domains/campaigns/services/slot_lifecycle.py            # Task 3: _calculate_deadline update
src/domains/campaigns/services/slot_validation.py           # Task 7: check calculate_step_deadline
src/domains/campaigns/services/sla_checker_test.py          # Task 6: integration SLA checker test
```

**НЕ трогать:**
- `supabase/migrations/20260125190126_rebalance_cron_schedule.sql` — rebalance cron
- `supabase/migrations/` — любые другие файлы (нет schema-изменений для этой фичи)
- `src/domains/campaigns/services/sla_checker.py` — логика checker не меняется, только deadline
- `src/domains/campaigns/services/sla_checker_reminders.py` — reminder logic не меняется
- `src/domains/campaigns/services/slot_machine.py` — фасад, не меняется
- `tests/regression/` и `tests/contracts/` — запрещено

---

## Eval Criteria

### EC-1: Unit — базовый snap (утренний заказ)
**Source:** devil scout DA-1 (edge: утро vs вечер)
```
Input: from_time = 2026-04-29 14:00 UTC (17:00 MSK), step=PICKUP, is_eta2=True
N_hours = 2*24 = 48h
nominal = 2026-05-01 14:00 UTC (17:00 MSK)
Expected snap: 2026-05-01 21:00 UTC (= 00:00 MSK 2026-05-02)
```
Assert: `_calculate_deadline(PICKUP, from_time, is_eta2=True) == datetime(2026, 5, 1, 21, 0, tzinfo=UTC)`

### EC-2: Unit — snap для ночного заказа (anti-fairness edge)
**Source:** devil scout DA-2 (заказ в 23:01 МСК)
```
Input: from_time = 2026-04-29 20:01 UTC (23:01 MSK), step=PICKUP, is_eta2=True
N_hours = 48h
nominal = 2026-05-01 20:01 UTC (23:01 MSK)
Expected snap: 2026-05-01 21:00 UTC (= 00:00 MSK 2026-05-02) — НЕ на сутки больше
```
Assert: result.date() in UTC == date(2026, 5, 1) AND result.hour == 21

### EC-3: Unit — snap НЕ применяется для SEARCH/ORDER
**Source:** codebase scout (sub-hour steps)
```
Input: from_time = now, step=SEARCH
Expected: deadline = from_time + 30 minutes (без snap)
```
Assert: `_calculate_deadline(SEARCH, from_time) == from_time + timedelta(minutes=30)`

### EC-4: Unit — snap перед полуночью (from_time в 23:59 МСК)
**Source:** devil scout DA-3 (edge: заказ прямо перед полуночью)
```
Input: from_time = 2026-04-29 20:59 UTC (23:59 MSK), step=PICKUP, is_eta2=True
N_hours = 48h
nominal = 2026-05-01 20:59 UTC (23:59 MSK)
Expected snap: 2026-05-01 21:00 UTC — snap только на 1 минуту вперёд (следующая полночь МСК)
```
Assert: `snap_to_midnight_msk(nominal) == datetime(2026, 5, 1, 21, 0, tzinfo=UTC)`

### EC-5: Unit — snap в TEST_MODE отключён
**Source:** codebase scout (TEST_MODE contract)
```
In TEST_MODE: Timers.sla_use_calendar_snap(SlotStep.PICKUP) == False
Expected: deadline = from_time + 2880 minutes (без snap)
```
Assert: с `settings.is_test_mode=True` → deadline не снаппится

### EC-6: Integration — SLA checker корректно сбрасывает слот с end-of-day дедлайном
**Source:** codebase scout (sla_checker_test.py pattern)
```
Setup: slot с deadline=2026-05-01 21:00:00 UTC, status=IN_PROGRESS
Run check_violations() с now=2026-05-01 21:05:00 UTC (5 минут после дедлайна)
Expected: handle_breach() вызван, slot.status → CANCELLED
```
TDD: интеграционный тест с fake clock (уже есть паттерн в sla_checker_test.py)

### EC-7: Integration — rebalance cron не затронут
**Source:** devil scout DA-4 (rebalance interaction)
```
Verify: SELECT cron.job WHERE jobname='rebalance-daily' → schedule = '0 3 * * *' (не изменился)
```
Assert: регрессионный тест — schema.sql содержит `'0 3 * * *'` для `rebalance-daily`

### EC-8: Notification — reminder отправляется за корректное время до нового дедлайна
**Source:** codebase scout (BUG-865 reminders)
```
Slot с end-of-day deadline (21:00 UTC). T2 = 80% elapsed.
Reminder должен отправляться за ~20% window до 21:00 UTC.
Expected: `sla_reminder_t2` event создаётся, deadline в payload = 21:00 UTC.
```
Assert: payload['deadline'] ends with '21:00:00+00:00'

---

## Rebalance Interaction

**ЯВНАЯ ГАРАНТИЯ:**

```
Дедлайн (00:00 МСК = 21:00 UTC)
    | SLA checker срабатывает каждые 5 минут
    | Слот сбрасывается в 21:00-21:05 UTC
    | 6 часов запаса
rebalance-daily (03:00 UTC = 06:00 МСК)
    | Видит освобождённый слот
    | Включает в утренний цикл перераспределения
```

SLA checker (`sla_checker.check_violations()`) запускается периодически через `run_periodic()`,
вызываемый из `src/api/telegram/main.py` (background task). Интервал: 5 минут в prod.
Слот, дедлайн которого наступил в 21:00, будет обнаружен и отменён не позднее 21:05 UTC.
До 03:00 UTC — 5 часов 55 минут запаса.

**НЕ требует изменений в:**
- `rebalance-daily` cron
- `rebalance_all_campaigns()` RPC
- `rebalance_campaign_atomic()` миграция

---

## Blueprint Reference

| Source | Section | Relevance |
|--------|---------|-----------|
| `ai/glossary/campaigns.md` | SlotStep, Diagnostics Playbook | Step lifecycle, slot buckets |
| `.claude/rules/domains/campaigns.md` | "Hardcoded timers — use Timers service" | Constraint: все таймеры через Timers |
| `.claude/rules/domains/campaigns.md` | "Skip event creation" | При изменении deadline — SlotEvent не нужен (deadline меняется только при assign/advance, события там уже создаются) |
| `.claude/rules/crons.md` | rebalance-daily | НЕ ТРОГАТЬ: `0 3 * * *` |
| `src/shared/timezone.py` | MSK constant | Reuse existing UTC+3 constant |
| ADR-003 | Async everywhere | Все новые публичные функции — async если нужно IO |
| ADR-018 | CONCURRENTLY migrations | Не применимо — нет schema changes |

**Cross-cutting rules applied:**
- Money in kopecks: не применимо (временные расчёты)
- Timers service: соблюдён — новая логика добавляется через Timers, не hardcode
- TEST_MODE: `sla_use_calendar_snap()` возвращает False в тестах — E2E цикл сохраняется
- Import direction: `shared.timezone` <- `infra.config.timers` <- `domains.campaigns` — корректно

---

## Migration Plan

**Нет schema migration.** Колонка `deadline` в таблице `slots` остаётся как есть.

1. **Деплой:** новая логика в Python-коде — следующий rolling deploy
2. **Активные слоты:** дедлайны НЕ пересчитываются — только новые assignments
3. **Backfill (опционально, отдельная задача):** `scripts/admin/backfill_sla_calendar_snap.py`
   — создать отдельной задачей если founder решит пересчитать текущие PICKUP-слоты

---

## Definition of Done

- [ ] `snap_to_midnight_msk()` добавлена в `src/shared/timezone.py` и экспортирована
- [ ] `Timers.sla_use_calendar_snap()` добавлен, `SLA_CALENDAR_SNAP_STEPS` определён
- [ ] `_calculate_deadline()` в `slot_lifecycle.py` использует snap для eligible steps
- [ ] `slot_validation.py:calculate_step_deadline` проверен/обновлен (single source of truth)
- [ ] Все 8 Eval Criteria пройдены (unit + integration + notification)
- [ ] TEST_MODE: E2E тесты проходят без изменений (snap отключён в тестах)
- [ ] `./test fast` — lint + unit: green
- [ ] `./test` — full suite: green
- [ ] rebalance cron не изменён (verify via `SELECT * FROM cron.job WHERE jobname='rebalance-daily'`)
- [ ] Commit: `feat(campaigns): FTR-882 SLA calendar snap — deadline snaps to 00:00 MSK for multi-day steps`

---

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Late-night order: 3 calendar days instead of 2 | LOW | Acceptable: max extra = 59 min. User gets more time, not less. |
| TEST_MODE E2E breaks | LOW | `sla_use_calendar_snap()` returns False in TEST_MODE |
| Short-step snap (SEARCH/ORDER) | NONE | Excluded from snap by design |
| Active slot deadline changes unexpectedly | NONE | No retroactive recalculation |
| Rebalance sees expired slots too late | NONE | 6h gap between 21:00 UTC and 03:00 UTC rebalance |
| Reminder timestamps shift | LOW | BUG-865 reminders read `deadline` column directly — auto-updated for new slots |
| BUG-865 reminders fire later relative to step start | LOW | T1/T2 still computed as `elapsed/total_window` from `step_advanced` event. Window растягивается при snap (макс +24h), пропорционально. Линейность сохранена, просто абсолютные T1/T2 отметки сдвигаются вместе с deadline. |
| BUG-864 backfill race | NONE | Backfill уже произошёл с старой логикой (deadline + 7d). Новая логика применяется ТОЛЬКО к assignments после деплоя (см. Migration Plan). Active слоты с старыми deadlines не трогаем. |
| `slot_machine_test.py` не в Allowed Files и упадёт от Task 7 | NONE | Planner-verified: все 3 теста (`TestDeadlines.*`) сохраняют работоспособность с новой логикой (см. Task 7 compatibility check). |
| Duplicate snap logic в 2 файлах (slot_lifecycle + slot_validation) | LOW | DRY violation, но рефакторинг невозможен из-за уже существующего circular import (`slot_lifecycle → slot_validation`). Зеркальная логика в обоих местах = sync invariant. Тесты на оба места ОБЯЗАТЕЛЬНЫ. |

---

## Drift Log

**Checked:** 2026-04-29 (planner pass)
**Result:** no_drift

### Changes Detected

| File | Change Type | Action Taken |
|------|-------------|--------------|
| (none) | (no drift detected — spec is fresh, written today, codebase unchanged) | — |

### References Updated

- Task 7 description clarified: `calculate_step_deadline` is independent copy (not delegate of `_calculate_deadline`). Mirror snap logic instead of delegate. See updated Task 7 spec above.
- Compatibility analysis added for `slot_machine_test.py::TestDeadlines` (NOT in Allowed Files, but planner-verified compatible).

---

## Plan Validated (2026-04-29)

Planner re-read codebase 2026-04-29 — drift = **none**, plan is executable as-is with one Task 7 clarification.

### Codebase verification

| Check | Result |
|-------|--------|
| `src/shared/timezone.py:MSK` constant | EXISTS (line 25) |
| `src/shared/timezone.py:utc_to_msk()` | EXISTS (line 37) |
| `src/shared/timezone_test.py` | EXISTS (120 LOC, has TestUtcToMsk class to extend) |
| `src/infra/config/timers.py:Timers` class | EXISTS, has `is_test_mode` flag check pattern (lines 28, 33, etc.) |
| `src/infra/config/timers.py:Timers.get_step_deadlines_minutes()` | EXISTS (line 112), returns `dict[SlotStep, int]` |
| `src/infra/config/timers_test.py` | EXISTS (41 LOC, has TestSLAReminderThresholds — pattern to follow) |
| `src/domains/campaigns/services/slot_lifecycle.py:_calculate_deadline()` | EXISTS (lines 56-67), accepts `(step, from_time=None, is_eta2=False)` |
| `src/domains/campaigns/services/slot_validation.py:calculate_step_deadline()` | EXISTS (lines 101-111) — duplicate of _calculate_deadline (NOT delegate) |
| `src/domains/campaigns/services/sla_checker_test.py` | EXISTS (600 LOC, has fake-clock pattern via `patch(...).is_test_mode`) |
| `src/shared/enums.py:SlotStep` enum | All 8 expected values present (UNASSIGNED, SEARCH, ORDER, PICKUP, RECEIPT, UGC_TEXT, UGC_PHOTO, UGC_VIDEO, UGC_PUBLISHED, DONE) |
| `supabase/migrations/20260125190126_rebalance_cron_schedule.sql` | EXISTS, schedule = `'0 3 * * *'` (UNCHANGED, MUST NOT be touched) |
| `Timers.sla_check_interval_minutes()` (`5` minutes prod, `1` minute TEST_MODE) | CONFIRMED (line 138) |
| `BUG-864 backfill_eta2_deadlines.py` | EXISTS in `scripts/admin/` — already executed, irrelevant to FTR-882 |

### Task 7 clarification (UPDATED in plan above)

Spec said "проверить, оборачивает ли calculate_step_deadline в slot_lifecycle". Planner found:
- `calculate_step_deadline` is INDEPENDENT COPY of `_calculate_deadline` (not delegate)
- Cannot delegate (would create circular import — `slot_lifecycle.py:32` already imports from `slot_validation.py`)
- Production never calls `calculate_step_deadline` directly; only `slot_machine_test.py` uses it
- **Action:** mirror snap logic in `calculate_step_deadline` identically. Tests confirmed compatible.

### Execution Order (planner-confirmed)

```
Task 1 (snap_to_midnight_msk in timezone.py) ──┐
                                               ├─→ Task 3 (_calculate_deadline) ──┐
Task 2 (Timers.sla_use_calendar_snap)         ──┘                                  ├─→ Task 6 (sla_checker_test.py integration)
                                                                                    │
                                                  Task 7 (calculate_step_deadline) ─┘

Task 4 (timers_test.py) — depends on Task 2
Task 5 (timezone_test.py) — depends on Task 1
Task 8 (Migration plan — doc only) — depends on nothing
```

**Independent (can be parallel):** Tasks 1, 2, 8.
**Sequential (after Tasks 1+2):** Task 3, Task 7 (mirror).
**Test tasks (after impl):** Tasks 4, 5, 6.

### Eval Criteria coverage matrix

| EC | Task | Coverage status |
|----|------|----------------|
| EC-1 (basic snap PICKUP+eta2 17:00 MSK) | Task 5 + Task 3 | unit test in `timezone_test.py` + integration via `_calculate_deadline` |
| EC-2 (late-night snap 23:01 MSK) | Task 5 | unit test in `timezone_test.py` |
| EC-3 (SEARCH no-snap) | Task 4 + Task 5 | unit `Timers.sla_use_calendar_snap(SEARCH)==False` + `_calculate_deadline(SEARCH)` |
| EC-4 (snap before midnight 23:59 MSK) | Task 5 | unit test in `timezone_test.py` |
| EC-5 (TEST_MODE disabled) | Task 4 | unit `Timers.sla_use_calendar_snap()==False` when `is_test_mode=True` |
| EC-6 (SLA checker breach at 21:00) | Task 6 | integration test in `sla_checker_test.py` with fake clock |
| EC-7 (rebalance cron unchanged) | — | Acceptance via Definition of Done (`SELECT cron.job WHERE jobname='rebalance-daily'`). No new test needed — spec forbids touching that migration. |
| EC-8 (reminder payload includes 21:00 UTC deadline) | Task 6 (extension) | integration in `sla_checker_test.py` — extend existing `TestSLACheckerReminders` to assert `deadline.endswith('21:00:00+00:00')` |

**EC-7 Note:** EC-7 не требует нового кода или теста — это assertion в DoD. Если planner или coder создают тест для EC-7, добавлять в `tests/regression/` запрещено (см. .claude/CLAUDE.md). Достаточно ручной проверки SQL после деплоя.

### Plan size & scope checks

- Files modified: **7** (within Allowed Files, all listed correctly)
- Tasks: **8** (≤10 limit OK)
- Per-task LOC estimate:
  - Task 1: ~12 LOC (function + export)
  - Task 2: ~20 LOC (frozenset + static method)
  - Task 3: ~5 LOC change
  - Task 4: ~30 LOC tests
  - Task 5: ~60 LOC tests (4 EC scenarios)
  - Task 6: ~50 LOC test
  - Task 7: ~10 LOC change (mirror)
  - Task 8: 0 LOC (doc-only, migration plan note)

### Plan: ready for autopilot

No COUNCIL escalation needed. No HUMAN review needed (R1 contained, P1 single-domain).
Routing: P1×R1 → AUTO per Impact×Risk matrix.
