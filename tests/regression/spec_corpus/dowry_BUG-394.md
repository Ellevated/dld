# Bug Fix: [BUG-394] Parser backfill never starts for already-parsed groups (87% stuck)

**Status:** done | **Priority:** P1 | **Date:** 2026-04-30

---

## Symptom

Из 152 active seller-групп **133 (87%) имеют `history_cursor_at IS NULL`** при `last_parsed_at IS NOT NULL` — backfill для них никогда не запускался и не запустится. Исторический контекст по этим группам (когда селлеры задавали ключевые вопросы, какие проблемы поднимали полгода назад) не догоняется. Это критично для outreach.

**Прод-цифры (2026-04-28):**

| Метрика | Значение |
|---------|----------|
| Active seller-групп | 152 |
| `history_cursor_at = NULL` (backfill never started) | 133 (87%) |
| `history_cursor_at` set (backfill running) | 19 |
| Oldest cursor (longest backfill) | 2026-01-04 (4 месяца, 1000 msgs/run × 2 runs/day) |
| Уникальных групп parsed за 24ч | 113 (46 seller + 67 buyer) |
| Уникальных групп parsed за 7д | 122 |

113 в сутки vs 122 в неделю → одни и те же ~120 групп парсятся снова и снова, история по 133 застрявшим не нагоняется.

---

## Root Cause (5 Whys Result)

**Why 1:** Почему backfill не догоняет историю?
→ В 87% групп `history_cursor_at IS NULL` — backfill-pass пропускается.

**Why 2:** Почему `history_cursor_at` остаётся NULL?
→ `parse_single_group` записывает cursor **только** при `is_first_parse=True` (когда `last_parsed_at IS NULL`).

**Why 3:** Почему cursor не устанавливается при последующих проходах?
→ Логика в `tg_parser_connection.py:282-291`:
```python
is_first_parse = not group.get("last_parsed_at")
new_cursor = cursor_dt  # default: keep current (= NULL!)

if is_first_parse and fresh_msgs:
    new_cursor = _oldest_message_date(fresh_msgs)
elif is_first_parse and not fresh_msgs:
    new_cursor = None
# else: NO branch for "not first_parse AND cursor IS NULL" → cursor остаётся NULL навсегда
```

**Why 4:** Почему cursor у этих 133 групп изначально NULL?
→ Гипотезы (нужна верификация на одной группе):
  (a) Группы парсились ДО внедрения backfill-логики (исторический deploy).
  (b) Первый парс уложился в `is_first_parse=True AND not fresh_msgs` → `new_cursor=None` записан явно (`history` пустая на момент первого прохода).
  (c) Race condition: `last_parsed_at` обновился, а `history_cursor_at` нет (ошибка во время update_metadata).

**Why 5:** Почему нет автоматического kickstart для таких групп?
→ Код not designed для recovery — предполагает что `is_first_parse=True` всегда корректно проинициализирует cursor. Edge case "уже парсилась + cursor пустой" не предусмотрен.

**ROOT CAUSE:** `parse_single_group` не имеет ветки kickstart для случая `last_parsed_at IS NOT NULL AND history_cursor_at IS NULL`. 133 группы навсегда застряли в этом состоянии.

---

## Reproduction Steps

```sql
-- DEV/PROD
SELECT
  COUNT(*) FILTER (WHERE history_cursor_at IS NULL AND last_parsed_at IS NOT NULL) AS stuck,
  COUNT(*) FILTER (WHERE history_cursor_at IS NOT NULL) AS running,
  COUNT(*) AS total
FROM dowry.distribution_groups
WHERE health_score = 'active' AND group_type = 'seller';
-- Expected: stuck → 0 после фикса
-- Got:      stuck = 133 / total = 152 (87%)
```

После следующих 14 дней (28 запусков парсера, 4×/день):
- Expected: `stuck < 20` (большинство пройдут pass или закроются как пустые)
- Got: `stuck` остаётся ~133 (никогда не уменьшается)

---

## Fix Approach

### 1. Backfill kickstarter в `parse_single_group`

Добавить ветку для случая «группа уже парсилась, но cursor пустой»:

```python
# tg_parser_connection.py — в блоке вычисления new_cursor (после строки 291)

if is_first_parse and fresh_msgs:
    new_cursor = _oldest_message_date(fresh_msgs)
elif is_first_parse and not fresh_msgs:
    new_cursor = None
elif not is_first_parse and cursor_dt is None:
    # KICKSTART: группа уже парсилась, но cursor пустой → запустить backfill с last_parsed_at
    last_parsed = _parse_iso_dt(group.get("last_parsed_at"))
    if last_parsed and last_parsed > history_start_dt:
        new_cursor = last_parsed
        logger.info("Group '%s': kickstart backfill from last_parsed_at=%s",
                    group_name, last_parsed.isoformat())
    else:
        new_cursor = None  # уже на history_start, нечего бэкфилить
```

### 2. One-shot SQL backfill для 133 застрявших групп

Миграция `supabase/migrations/NNN_kickstart_backfill_cursor.sql`:

```sql
-- migrate:up
UPDATE dowry.distribution_groups
SET history_cursor_at = last_parsed_at
WHERE history_cursor_at IS NULL
  AND last_parsed_at IS NOT NULL
  AND health_score = 'active'
  AND last_parsed_at > '2026-01-01'::timestamptz;

-- migrate:down
-- One-shot backfill — rollback не нужен.
SELECT 1;
```

Это разблокирует 133 группы немедленно (не ждать 14 дней естественного прогрева через kickstart code).

### 3. Empty-history detection (already correct, добавить только observability)

Текущий код (строки 332-333) корректно закрывает cursor при пустом backfill-pass:
```python
else:  # backfill_msgs пустой
    new_cursor = None  # backfill complete
```

Добавить логирование `INFO`-уровня: `Group '%s': backfill empty, cursor closed` — чтобы видеть в логах сколько групп завершают backfill.

### 4. Backfill speed boost для caught-up групп

В `parse_single_group` — если fresh-pass принёс мало сообщений (group caught up to live):

```python
# После fresh-pass, перед backfill-pass
caught_up = len(fresh_msgs) < 100  # threshold: если fresh < 100, group в основном на live
backfill_max = max_messages * 2 if caught_up else max_messages

# затем при вызове _fetch_messages для backfill:
backfill_msgs, backfill_users = await _fetch_messages(
    tg_client, entity, tg_group_id, backfill_cursor, backfill_max
)
```

Эффект: 4-месячный backfill завершится за ~2 месяца вместо 4.

### 5. Метрики backfill в `IntelligenceParserResult`

Добавить поля в `models.py`:

```python
@dataclass
class IntelligenceParserResult:
    groups_ok: int = 0
    groups_error: int = 0
    messages_saved: int = 0
    users_upserted: int = 0
    # NEW:
    groups_backfill_active: int = 0       # сколько групп в этом проходе имели backfill-pass
    groups_backfill_kickstarted: int = 0  # сколько групп запустили kickstart-ветку
    groups_backfill_completed: int = 0    # сколько групп закрыли cursor (пустая история / достигнут history_start)
    avg_history_lag_days: float = 0.0     # средний возраст cursor по активным группам
```

Проброс в heartbeat (`intelligence_jobs.py:run_intelligence_parsing` уже использует `result` — добавить поля в payload).

`GroupParseResult` тоже расширить — `backfill_kickstarted: bool = False`, `backfill_completed: bool = False` — чтобы runner мог агрегировать.

---

## Impact Tree Analysis

### Step 1: UP — кто вызывает `parse_single_group`?

```bash
grep -rn "parse_single_group\|IntelligenceParserResult" src/
```

- `src/domains/intelligence/tg_parser_runner.py:parse_groups_with_account` — основной caller
- `src/domains/intelligence/tg_parser.py:TGIntelligenceParser.run` — оркестратор
- `src/api/scheduler_jobs/intelligence_jobs.py:run_intelligence_parsing` — entry point heartbeat

Все эти 3 файла нужно обновить для проброса новых полей.

### Step 2: DOWN — что зависит от изменений в моделях?

- `IntelligenceParserResult` импортируется в `tg_parser.py`, `tg_parser_runner.py`, `intelligence_jobs.py`
- `GroupParseResult` импортируется только в `tg_parser_connection.py`, `tg_parser_runner.py`
- Расширение dataclass — backward compatible (новые поля с defaults)

### Step 3: BY TERM — grep по всему проекту

| File | Line | Status | Action |
|------|------|--------|--------|
| `src/domains/intelligence/tg_parser_connection.py` | 282-336 | needs fix | Добавить kickstart-ветку, speed boost, observability log |
| `src/domains/intelligence/models.py` | 54-71 | extend | Добавить поля backfill metrics в обоих dataclasses |
| `src/domains/intelligence/tg_parser_runner.py` | 35+ | propagate | Агрегировать backfill_kickstarted/completed из GroupParseResult |
| `src/domains/intelligence/tg_parser.py` | 102+ | propagate | Передать счётчики в IntelligenceParserResult |
| `src/api/scheduler_jobs/intelligence_jobs.py` | 270+ | heartbeat | Добавить новые метрики в heartbeat payload |
| `supabase/migrations/<NNN>_kickstart_backfill_cursor.sql` | new | create | One-shot UPDATE для 133 застрявших групп |
| `tests/unit/domains/intelligence/test_tg_parser_connection.py` | new/extend | tests | Регресс-тест на kickstart-ветку |

### Verification

- [ ] Все callers `parse_single_group` идентифицированы (3: runner, parser, jobs)
- [ ] `IntelligenceParserResult` consumers идентифицированы (3 файла) — все будут обновлены
- [ ] Allowed Files покрывает весь Impact Tree
- [ ] Миграция включена явно

---

## Research Sources

- Internal prod analysis (2026-04-28) — пользовательский диагностический drilldown по `distribution_groups`
- TECH-381 (`features/TECH-381-2026-04-19-intelligence-parsing-overlap-tuning.md`) — прецедент heartbeat-метрик `backfill_remaining`, можно повторить паттерн
- BUG-383 — установил SSOT парсера (`TGIntelligenceParser`); фикс применяется к нему
- ADR-002 (Result pattern) — новые поля в dataclass соблюдают существующий паттерн

---

## Allowed Files

1. `src/domains/intelligence/tg_parser_connection.py` — kickstart-ветка, speed boost, observability log
2. `src/domains/intelligence/models.py` — расширение `IntelligenceParserResult` и `GroupParseResult`
3. `src/domains/intelligence/tg_parser_runner.py` — агрегация backfill-счётчиков per account
4. `src/domains/intelligence/tg_parser.py` — суммирование в финальный `IntelligenceParserResult`
5. `src/api/scheduler_jobs/intelligence_jobs.py` — проброс новых полей в heartbeat
6. `supabase/migrations/<NNN>_kickstart_backfill_cursor.sql` — one-shot UPDATE для 133 застрявших
7. `tests/unit/domains/intelligence/test_tg_parser_connection.py` — регресс-тест на kickstart

**ВАЖНО:** `src/domains/intelligence/tg_parser_distribution.py` — НЕ ТРОГАТЬ (scarce-first работает корректно, нагрузка 5-34/аккаунт).

---

## Tests

### Test 1: Kickstart ветка для застрявшей группы (unit)

```python
# tests/unit/domains/intelligence/test_tg_parser_connection.py

@pytest.mark.asyncio
async def test_parse_single_group_kickstarts_stuck_backfill(monkeypatch):
    """Группа уже парсилась (last_parsed_at NOT NULL), но cursor=NULL → kickstart должен установить cursor=last_parsed_at."""
    group = {
        "id": "uuid-1",
        "group_url": "https://t.me/test",
        "name": "test",
        "last_parsed_at": "2026-04-15T00:00:00+00:00",
        "history_cursor_at": None,  # <-- застрявшая
        "health_score": "active",
    }
    # ... mock _fetch_messages → fresh_msgs = [<5 messages>]
    # ... mock save_messages_batch, upsert_users, db_client

    result = await parse_single_group(group, ..., history_start="2026-01-01", ...)

    assert result.ok is True
    # Проверить что update_metadata получил history_cursor_at = last_parsed_at
    # Backfill-pass запустился во ВТОРОМ pass с cursor = last_parsed_at
```

### Test 2: Empty backfill закрывает cursor (unit, regression)

```python
@pytest.mark.asyncio
async def test_parse_single_group_closes_cursor_on_empty_backfill():
    """Backfill вернул 0 messages → new_cursor=None (cursor закрыт, история догнана)."""
    group = {
        "id": "uuid-2",
        "history_cursor_at": "2026-02-01T00:00:00+00:00",
        "last_parsed_at": "2026-04-29T00:00:00+00:00",
        ...
    }
    # ... mock fresh-pass возвращает [3 msgs], backfill-pass возвращает []

    result = await parse_single_group(group, ...)

    # Проверить что update_metadata.history_cursor_at = None
```

### Test 3: Speed boost при caught-up группе (unit)

```python
@pytest.mark.asyncio
async def test_parse_single_group_doubles_max_messages_when_caught_up():
    """Если fresh-pass < 100 messages → backfill использует max_messages × 2."""
    # ... mock fresh-pass → 50 msgs (< 100 = caught up)
    # ... spy на _fetch_messages для backfill-pass

    result = await parse_single_group(group, ..., max_messages=1000, ...)

    # _fetch_messages для backfill-pass должен был быть вызван с max_messages=2000
```

### Test 4: Метрики в результате (unit)

```python
@pytest.mark.asyncio
async def test_parser_result_aggregates_backfill_metrics():
    """IntelligenceParserResult.groups_backfill_kickstarted считается корректно."""
    # ... mock 3 группы: 1 застрявшая (kickstart), 1 running, 1 completed
    parser = TGIntelligenceParser(...)
    result = await parser.run()

    assert result.groups_backfill_kickstarted == 1
    assert result.groups_backfill_active == 1
    assert result.groups_backfill_completed == 1
```

### Test 5: SQL миграция корректна (manual, run on DEV first)

```sql
-- DEV: проверить before/after
SELECT COUNT(*) FROM dowry.distribution_groups
WHERE history_cursor_at IS NULL AND last_parsed_at IS NOT NULL AND health_score='active';
-- before: ~133, after: 0
```

---

## Definition of Done

- [ ] Kickstart-ветка добавлена в `parse_single_group`
- [ ] One-shot миграция применена на DEV (затем PROD через CI) — 133 застрявшие группы получили `history_cursor_at = last_parsed_at`
- [ ] Speed boost для caught-up групп реализован (fresh < 100 → backfill_max × 2)
- [ ] `IntelligenceParserResult` и `GroupParseResult` расширены полями метрик
- [ ] Heartbeat в `run_intelligence_parsing` пробрасывает `groups_with_backfill`, `groups_backfill_kickstarted`, `groups_backfill_completed`, `avg_history_lag_days`
- [ ] Регресс-тесты (4 unit) написаны и проходят
- [ ] `./test fast` зелёный
- [ ] **Метрика успеха через 14 дней:** `history_cursor_at IS NULL` для активных seller-групп **< 20** (сейчас 133)
- [ ] **Метрика успеха через 24ч после миграции:** все 133 группы — либо cursor set, либо closed (никаких NULL при last_parsed_at NOT NULL)

---

## Notes

- Связано с **TECH-392** (Discovery → Joins coverage) и **проблемой #1 (Joins gap, 660 групп без аккаунтов)** — но решается **независимо**:
  - Joins = фронтальная экспансия (открыть 660 новых)
  - Backfill kickstart = вглубь по уже открытым 152
- Scarce-first distribution в `tg_parser_distribution.py` **НЕ ТРОГАЕМ** — работает корректно (5-34 групп/аккаунт)
- После фикса 4-месячные backfill'и (типа группы с cursor 2026-01-04) ускорятся до ~2 месяцев за счёт speed boost

---

## Drift Log

**Checked:** 2026-05-01 12:00 UTC
**Result:** light_drift (line numbers shifted, precedent migration found)

### Changes Detected
| File | Change Type | Action Taken |
|------|-------------|--------------|
| `src/domains/intelligence/tg_parser_connection.py` | line numbers shifted (spec: 282-336, actual: 281-336) | AUTO-FIX: updated below |
| `src/domains/intelligence/models.py` | line numbers shifted (spec: 54-71, actual: 53-78) | AUTO-FIX: updated below |
| `src/api/scheduler_jobs/intelligence_jobs.py` | heartbeat line range (spec: 270+, actual: 270-391) | AUTO-FIX: updated below |
| `supabase/migrations/20260407000001_distribution_groups_history_cursor.sql` | precedent migration found | NOTE: similar UPDATE was applied 2026-04-07; 133 stuck groups appeared AFTER (groups with `last_parsed_at` set after 2026-04-07 hit empty-history branch first parse) |
| `tests/unit/domains/intelligence/test_tg_parser_connection.py` | does not exist | NEW FILE in plan |

### References Updated
- Task 1: `tg_parser_connection.py:282-291` → `tg_parser_connection.py:281-291` (the `is_first_parse` line is 282 in spec, but actual is 282, kickstart inserts after line 291)
- Task 5 migration filename: `<NNN>_kickstart_backfill_cursor.sql` → `20260430000001_kickstart_backfill_cursor.sql` (latest existing: `20260429000002`)
- Task 3 line range: `models.py:54-71` → `models.py:53-78` (`GroupParseResult` at 53-61, `IntelligenceParserResult` at 64-78)

### Solution Verified
- Spec approach is sound. Precedent migration `20260407000001_distribution_groups_history_cursor.sql` did same UPDATE pattern at column-add time. New stuck groups accumulated since (likely from `is_first_parse=True AND not fresh_msgs` branch on freshly-imported groups whose recent edge is empty).
- No external library research needed — pure intra-domain refactor.

---

## Implementation Plan

> Coder MUST follow tasks in order. Each task is one logical change with concrete file:line refs and code snippets. Run `./test fast` after EACH task — must remain green.

### Task 1: Add kickstart branch to `parse_single_group`

**Files:**
- Modify: `src/domains/intelligence/tg_parser_connection.py:281-292` (extend cursor decision branch)

**Context:**
Current code only sets `new_cursor` when `is_first_parse=True`. Stuck groups (`last_parsed_at NOT NULL AND history_cursor_at IS NULL`) fall through with `new_cursor = cursor_dt = None`, never starting backfill. Add explicit kickstart branch.

**What to change:**
After line 291 (`new_cursor = None  # First parse, no messages`), add `elif` branch for the stuck-group recovery case. `history_start_dt` is already computed at line 259.

**Code snippet (replace lines 281-292):**
```python
        # Determine new history_cursor_at for this group
        is_first_parse = not group.get("last_parsed_at")
        cursor_dt = _parse_iso_dt(group.get("history_cursor_at"))
        new_cursor: datetime | None = cursor_dt  # default: keep current
        backfill_kickstarted = False  # Task 4: aggregate signal

        if is_first_parse and fresh_msgs:
            # First parse ever — set cursor to oldest message so next pass continues deeper
            new_cursor = _oldest_message_date(fresh_msgs)
        elif is_first_parse and not fresh_msgs:
            # First parse, no messages — history is empty, no backfill needed
            new_cursor = None
        elif not is_first_parse and cursor_dt is None:
            # BUG-394 KICKSTART: group already parsed but cursor was never set
            # → recover by seeding cursor from last_parsed_at so backfill runs next pass.
            last_parsed = _parse_iso_dt(group.get("last_parsed_at"))
            if last_parsed and last_parsed > history_start_dt:
                new_cursor = last_parsed
                backfill_kickstarted = True
                logger.info(
                    "Group '%s': BUG-394 kickstart backfill from last_parsed_at=%s",
                    group_name,
                    last_parsed.isoformat(),
                )
            else:
                # last_parsed_at <= history_start → already at boundary, nothing to backfill
                new_cursor = None
```

**Acceptance:**
- [ ] `./test fast` green
- [ ] No new file > 400 LOC (current file is 403 lines; this adds ~12 lines, gets close to limit but OK)
- [ ] grep confirms `backfill_kickstarted` is the ONLY new local variable here (used in Task 4)

---

### Task 2: Speed boost for caught-up groups

**Files:**
- Modify: `src/domains/intelligence/tg_parser_connection.py:293-302` (compute `backfill_max` before backfill `_fetch_messages` call)

**Context:**
For groups already at the live edge (fresh-pass < 100 msgs), double the backfill batch size to halve the time-to-completion. 4-month backfill → ~2 months.

**What to change:**
After computing `backfill_cursor` (line 294), compute `backfill_max` based on fresh count, then pass it to `_fetch_messages` instead of `max_messages`.

**Code snippet (replace lines 293-302):**
```python
        # --- Pass 2: History backfill ---
        backfill_cursor = new_cursor if is_first_parse else cursor_dt
        # BUG-394 speed boost: if group is caught up to live (fresh < 100), double backfill batch
        caught_up = len(fresh_msgs) < 100
        backfill_max = max_messages * 2 if caught_up else max_messages
        backfill_completed = False  # Task 4: aggregate signal
        backfill_active = backfill_cursor is not None and backfill_cursor > history_start_dt

        if backfill_cursor and backfill_cursor > history_start_dt:
            backfill_msgs, backfill_users = await _fetch_messages(
                tg_client,
                entity,
                tg_group_id,
                backfill_cursor,
                backfill_max,
            )
```

**Acceptance:**
- [ ] `./test fast` green
- [ ] `caught_up` boolean correctly computed BEFORE backfill call
- [ ] `backfill_max` is `max_messages * 2` when `len(fresh_msgs) < 100`
- [ ] `backfill_active` and `backfill_completed` declared (used in Task 4)

---

### Task 3: Mark `backfill_completed` and extend `GroupParseResult`

**Files:**
- Modify: `src/domains/intelligence/tg_parser_connection.py:325-336, 368-372` (set flag + populate result)
- Modify: `src/domains/intelligence/models.py:53-61` (extend dataclass)

**Context:**
Result must carry kickstart/active/completed signals so runner can aggregate per-account, then parser per-run, then heartbeat per-job.

**3a. Extend `GroupParseResult` (models.py lines 53-61):**

```python
@dataclass
class GroupParseResult:
    """Result of parsing a single group."""

    ok: bool
    messages_saved: int = 0
    users_upserted: int = 0
    error: Optional[str] = None
    stop: bool = False
    # BUG-394: backfill telemetry
    backfill_active: bool = False       # had a cursor > history_start at start of this run
    backfill_kickstarted: bool = False  # cursor was NULL but last_parsed_at set → seeded
    backfill_completed: bool = False    # cursor was closed (None) this run
```

**3b. In `tg_parser_connection.py`, set `backfill_completed=True` wherever `new_cursor = None` is assigned in the backfill branches (lines 325, 333, 336):**

Replace:
```python
                if oldest and oldest > history_start_dt:
                    new_cursor = oldest
                else:
                    new_cursor = None  # reached history_start — backfill complete
```
with:
```python
                if oldest and oldest > history_start_dt:
                    new_cursor = oldest
                else:
                    new_cursor = None  # reached history_start — backfill complete
                    backfill_completed = True
```

Replace:
```python
            else:
                new_cursor = None  # no more messages — backfill complete
```
with:
```python
            else:
                new_cursor = None  # no more messages — backfill complete
                backfill_completed = True
                logger.info("Group '%s': backfill empty, cursor closed", group_name)
```

Replace:
```python
        elif backfill_cursor and backfill_cursor <= history_start_dt:
            new_cursor = None  # already at or past history_start
```
with:
```python
        elif backfill_cursor and backfill_cursor <= history_start_dt:
            new_cursor = None  # already at or past history_start
            backfill_completed = True
```

**3c. Populate the result (lines 368-372):**

Replace:
```python
        return GroupParseResult(
            ok=True,
            messages_saved=total_saved,
            users_upserted=total_users,
        )
```
with:
```python
        return GroupParseResult(
            ok=True,
            messages_saved=total_saved,
            users_upserted=total_users,
            backfill_active=backfill_active,
            backfill_kickstarted=backfill_kickstarted,
            backfill_completed=backfill_completed,
        )
```

**Acceptance:**
- [ ] `./test fast` green
- [ ] All three new fields default to `False` (backward compat with existing tests)
- [ ] grep `backfill_completed = True` finds 3 occurrences in tg_parser_connection.py

---

### Task 4: Aggregate counters in runner → parser → heartbeat

**Files:**
- Modify: `src/domains/intelligence/models.py:64-78` (extend `IntelligenceParserResult`)
- Modify: `src/domains/intelligence/tg_parser_runner.py:130-139` (sum counters in account loop)
- Modify: `src/api/scheduler_jobs/intelligence_jobs.py:351-388` (log + heartbeat payload)

**Context:**
Runner accumulates into `IntelligenceParserResult` (mutable, in-place). Parser already returns it. Heartbeat reads it and writes log + scheduler_heartbeats stats.

**4a. Extend `IntelligenceParserResult` (models.py lines 64-78):**

```python
@dataclass
class IntelligenceParserResult:
    """Result of a full intelligence parsing run."""

    groups_ok: int = 0
    groups_error: int = 0
    messages_saved: int = 0
    users_upserted: int = 0
    members_upserted: int = 0
    flood_wait: bool = False
    # TECH-381: observability metrics
    wall_time_seconds: float = 0.0
    flood_waits: int = 0
    accounts_used: int = 0
    errors: list[str] = field(default_factory=list)
    # BUG-394: backfill metrics
    groups_backfill_active: int = 0       # groups with cursor > history_start at start of run
    groups_backfill_kickstarted: int = 0  # groups whose cursor we seeded from last_parsed_at
    groups_backfill_completed: int = 0    # groups whose cursor was closed (None) this run
```

**4b. Aggregate in runner (tg_parser_runner.py, after line 132 in the `if group_result.ok` block):**

Replace:
```python
            if group_result.ok:
                result.groups_ok += 1
                result.messages_saved += group_result.messages_saved
                result.users_upserted += group_result.users_upserted
            else:
```
with:
```python
            if group_result.ok:
                result.groups_ok += 1
                result.messages_saved += group_result.messages_saved
                result.users_upserted += group_result.users_upserted
                # BUG-394: aggregate backfill telemetry
                if group_result.backfill_active:
                    result.groups_backfill_active += 1
                if group_result.backfill_kickstarted:
                    result.groups_backfill_kickstarted += 1
                if group_result.backfill_completed:
                    result.groups_backfill_completed += 1
            else:
```

**4c. Heartbeat payload (intelligence_jobs.py, lines 351-388):**

Update the `logger.info("Intelligence parsing stats: ...")` block (lines 350-366) to include the three new fields. Replace the format string and args:

```python
        logger.info(
            "Intelligence parsing stats: groups_total=%d, groups_ok=%d, groups_error=%d, "
            "messages_saved=%d, users_upserted=%d, wall_time_seconds=%.1f, "
            "flood_waits=%d, accounts_used=%d, backfill_remaining=%d, uncovered_groups=%d, "
            "overlap_minutes=%d, "
            "groups_backfill_active=%d, groups_backfill_kickstarted=%d, groups_backfill_completed=%d",
            result.groups_ok + result.groups_error,
            result.groups_ok,
            result.groups_error,
            result.messages_saved,
            result.users_upserted,
            result.wall_time_seconds,
            result.flood_waits,
            result.accounts_used,
            backfill_remaining,
            uncovered_groups,
            overlap_minutes,
            result.groups_backfill_active,
            result.groups_backfill_kickstarted,
            result.groups_backfill_completed,
        )
```

Update the `record_heartbeat` stats dict (lines 376-388) to include three new keys:

```python
                stats={
                    "groups_total": result.groups_ok + result.groups_error,
                    "groups_ok": result.groups_ok,
                    "groups_error": result.groups_error,
                    "messages_saved": result.messages_saved,
                    "users_upserted": result.users_upserted,
                    "wall_time_seconds": result.wall_time_seconds,
                    "flood_waits": result.flood_waits,
                    "accounts_used": result.accounts_used,
                    "backfill_remaining": backfill_remaining,
                    "uncovered_groups": uncovered_groups,
                    "overlap_minutes": overlap_minutes,
                    # BUG-394
                    "groups_backfill_active": result.groups_backfill_active,
                    "groups_backfill_kickstarted": result.groups_backfill_kickstarted,
                    "groups_backfill_completed": result.groups_backfill_completed,
                },
```

**Note:** `tg_parser.py` does NOT need changes — `parser.run()` already returns the same `result` object that the runner mutates in place (see `tg_parser.py:111` `result = IntelligenceParserResult()` then passed by reference into `_parse_groups_with_account`).

**Acceptance:**
- [ ] `./test fast` green
- [ ] grep `groups_backfill_kickstarted` finds it in models.py (1), runner (1), intelligence_jobs.py (2: log + heartbeat)
- [ ] No changes needed in `tg_parser.py` (verified: passes result by reference)

---

### Task 5: SQL one-shot kickstart migration

**Files:**
- Create: `supabase/migrations/20260430000001_kickstart_backfill_cursor.sql`

**Context:**
Latest migration is `20260429000002_tg_account_retire_cascade_trigger.sql`. Next timestamp: `20260430000001`. One-shot UPDATE for the 133 stuck groups — unblocks them on PROD immediately, no waiting 14 days for the in-code kickstart to organically catch them.

**Schema verification (BUG-394 column check via TECH-265):**
- `dowry.distribution_groups.history_cursor_at TIMESTAMPTZ` — added by `20260407000001_distribution_groups_history_cursor.sql`
- `dowry.distribution_groups.last_parsed_at TIMESTAMPTZ` — exists (used since 2026-02-14)
- `dowry.distribution_groups.health_score TEXT` — exists with values `'pending' | 'active' | 'inactive'`

**File content:**
```sql
-- migrate:up
-- Migration: BUG-394 — kickstart history backfill for 133 stuck distribution_groups
-- Feature: BUG-394
--
-- Symptom: 87% of active seller groups have history_cursor_at IS NULL while last_parsed_at IS NOT NULL.
-- The parser code path that seeds the cursor only fires on first parse (last_parsed_at IS NULL).
-- Once the in-code kickstart (Task 1) ships, future runs heal organically; this migration heals
-- the existing 133 in one shot so we don't wait 14+ days for natural recovery.
--
-- Safety:
--  - Bounded by last_parsed_at > '2026-01-01' (skip ancient ghosts).
--  - Only touches NULL→last_parsed_at; never overwrites a non-NULL cursor.
--  - Idempotent: re-running is a no-op (WHERE filters NULL).

UPDATE dowry.distribution_groups
SET history_cursor_at = last_parsed_at
WHERE history_cursor_at IS NULL
  AND last_parsed_at IS NOT NULL
  AND health_score = 'active'
  AND last_parsed_at > '2026-01-01'::timestamptz;

-- migrate:down
-- One-shot data backfill — rollback would require knowing which rows we touched
-- (we did not log them). Manual reversal possible by setting history_cursor_at = NULL
-- for groups whose history_cursor_at == last_parsed_at AND no backfill messages have
-- been collected since. Out of scope for automated down. No-op:
SELECT 1;
```

**Validation before commit:**
```bash
squawk supabase/migrations/20260430000001_kickstart_backfill_cursor.sql
# Expected: pass (DML on filtered subset, no schema change, no destructive op)
```

**Acceptance:**
- [ ] File exists at `supabase/migrations/20260430000001_kickstart_backfill_cursor.sql`
- [ ] Contains `-- migrate:up` and `-- migrate:down` markers
- [ ] All table refs use `dowry.` prefix
- [ ] `./test fast` validates migration format (per FTR-060)
- [ ] Squawk lint passes

---

### Task 6: Unit tests for kickstart + speed-boost + completed flags

**Files:**
- Create: `tests/unit/domains/intelligence/test_tg_parser_kickstart.py`

**Context:**
Existing `test_tg_parser_backfill.py` tests pure helpers (`_oldest_message_date`, `_parse_iso_dt`). For `parse_single_group` we need full Telethon mocks (entity, iter_messages, save/upsert). Pattern: mock the storage layer + Telethon iteration with `AsyncMock`.

**Code (≤600 LOC for tests):**
```python
"""Tests for BUG-394 kickstart, speed boost, and backfill completion telemetry."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.intelligence.models import GroupParseResult, RawTGMessage
from src.domains.intelligence.tg_parser_connection import parse_single_group


def _make_msg(tg_id: int, date: datetime, text: str = "hello world") -> RawTGMessage:
    return RawTGMessage(
        tg_message_id=tg_id,
        tg_group_id=100,
        tg_user_id=200,
        message_text=text,
        message_date=date,
    )


@pytest.fixture
def mock_storage(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Patch storage layer so parse_single_group has no DB side-effects."""
    monkeypatch.setattr(
        "src.domains.intelligence.tg_parser_connection.save_messages_batch",
        AsyncMock(side_effect=lambda _c, msgs, _g: len(msgs)),
    )
    monkeypatch.setattr(
        "src.domains.intelligence.tg_parser_connection.upsert_users",
        AsyncMock(side_effect=lambda _c, users, _m: len(users)),
    )
    monkeypatch.setattr(
        "src.domains.intelligence.tg_parser_connection.upsert_group_members",
        AsyncMock(return_value=0),
    )
    return {}


def _build_tg_client(fresh_msgs: list, backfill_msgs: list) -> MagicMock:
    """Build a fake Telethon client whose iter_messages returns fresh then backfill."""
    client = MagicMock()
    client.get_entity = AsyncMock(return_value=MagicMock(id=12345))

    call_count = {"n": 0}

    def _iter(entity, offset_date, limit):  # noqa: ARG001
        call_count["n"] += 1
        msgs = fresh_msgs if call_count["n"] == 1 else backfill_msgs

        async def _gen():
            for m in msgs:
                fake = MagicMock()
                fake.id = m.tg_message_id
                fake.date = m.message_date
                fake.message = m.message_text
                fake.sender_id = m.tg_user_id
                fake.reply_to = None
                fake.media = None
                fake.views = None
                fake.forwards = None
                # MessageService check uses isinstance — return a non-MessageService MagicMock
                fake.__class__ = type("RealMsg", (), {})
                # User isinstance check: provide a sender that satisfies it
                sender = MagicMock(spec_set=object)
                sender.id = m.tg_user_id
                sender.username = "u"
                sender.first_name = "F"
                sender.last_name = "L"
                fake.sender = sender
                yield fake

        return _gen()

    client.iter_messages = _iter
    return client


@pytest.mark.asyncio
async def test_kickstart_seeds_cursor_for_stuck_group(mock_storage) -> None:
    """BUG-394: group with last_parsed_at set but history_cursor_at=NULL → seed cursor from last_parsed_at."""
    last_parsed = "2026-04-15T00:00:00+00:00"
    group = {
        "id": "uuid-1",
        "group_url": "https://t.me/test",
        "name": "stuck-group",
        "last_parsed_at": last_parsed,
        "history_cursor_at": None,  # stuck
        "health_score": "active",
    }

    # 5 fresh msgs (caught-up: < 100), no backfill yet (cursor not set when fetch runs)
    fresh = [
        _make_msg(i, datetime(2026, 4, 28, 12, i, tzinfo=timezone.utc))
        for i in range(5)
    ]
    # On first run, backfill_cursor = cursor_dt = None (kickstart sets *new_cursor*, not the
    # backfill_cursor used this pass). So no backfill iteration this run.
    client = _build_tg_client(fresh_msgs=fresh, backfill_msgs=[])
    db = MagicMock()
    db.table.return_value.update.return_value.eq.return_value.execute = AsyncMock()

    pool = MagicMock()
    account = MagicMock(id="acc-1")

    result = await parse_single_group(
        group, client, account, db, pool,
        history_start="2026-01-01",
        hours_back=24,
        max_messages=1000,
    )

    assert result.ok is True
    assert result.backfill_kickstarted is True
    # update_metadata was called with history_cursor_at = last_parsed
    upd_call = db.table.return_value.update.call_args
    payload = upd_call.args[0]
    assert "history_cursor_at" in payload
    assert payload["history_cursor_at"] == "2026-04-15T00:00:00+00:00"


@pytest.mark.asyncio
async def test_speed_boost_doubles_backfill_when_caught_up(mock_storage) -> None:
    """BUG-394: fresh < 100 → backfill _fetch_messages called with limit = max_messages*2."""
    group = {
        "id": "uuid-2",
        "group_url": "https://t.me/test",
        "name": "caught-up",
        "last_parsed_at": "2026-04-29T00:00:00+00:00",
        "history_cursor_at": "2026-02-01T00:00:00+00:00",
        "health_score": "active",
    }
    fresh = [_make_msg(i, datetime(2026, 4, 29, 12, i, tzinfo=timezone.utc)) for i in range(50)]
    backfill = [_make_msg(100 + i, datetime(2026, 1, 30, i, 0, tzinfo=timezone.utc)) for i in range(3)]

    client = _build_tg_client(fresh, backfill)
    # Spy iter_messages limits
    limits: list[int] = []
    orig_iter = client.iter_messages

    def _spy(entity, offset_date, limit):
        limits.append(limit)
        return orig_iter(entity, offset_date=offset_date, limit=limit)

    client.iter_messages = _spy

    db = MagicMock()
    db.table.return_value.update.return_value.eq.return_value.execute = AsyncMock()
    pool = MagicMock()
    account = MagicMock(id="acc-1")

    await parse_single_group(
        group, client, account, db, pool,
        history_start="2026-01-01",
        hours_back=24,
        max_messages=1000,
    )

    # Two iter_messages calls: fresh (1000) + backfill (2000 because caught-up)
    assert len(limits) == 2
    assert limits[0] == 1000  # fresh-pass uses base
    assert limits[1] == 2000  # backfill-pass doubled


@pytest.mark.asyncio
async def test_backfill_completed_on_empty_history(mock_storage) -> None:
    """Backfill returns 0 messages → backfill_completed=True, cursor closed (None)."""
    group = {
        "id": "uuid-3",
        "group_url": "https://t.me/test",
        "name": "draining",
        "last_parsed_at": "2026-04-29T00:00:00+00:00",
        "history_cursor_at": "2026-02-01T00:00:00+00:00",
        "health_score": "active",
    }
    fresh = [_make_msg(1, datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc))]
    client = _build_tg_client(fresh, backfill_msgs=[])
    db = MagicMock()
    db.table.return_value.update.return_value.eq.return_value.execute = AsyncMock()
    pool = MagicMock()
    account = MagicMock(id="acc-1")

    result = await parse_single_group(
        group, client, account, db, pool,
        history_start="2026-01-01",
        hours_back=24,
        max_messages=1000,
    )

    assert result.ok is True
    assert result.backfill_completed is True
    upd_payload = db.table.return_value.update.call_args.args[0]
    assert upd_payload.get("history_cursor_at") is None  # cursor closed


@pytest.mark.asyncio
async def test_no_kickstart_when_already_running(mock_storage) -> None:
    """Group with cursor already set → no kickstart, normal backfill flow."""
    group = {
        "id": "uuid-4",
        "group_url": "https://t.me/test",
        "name": "running",
        "last_parsed_at": "2026-04-29T00:00:00+00:00",
        "history_cursor_at": "2026-03-01T00:00:00+00:00",  # already set
        "health_score": "active",
    }
    fresh = [_make_msg(i, datetime(2026, 4, 29, 12, i, tzinfo=timezone.utc)) for i in range(3)]
    backfill = [_make_msg(100 + i, datetime(2026, 2, 28, i, 0, tzinfo=timezone.utc)) for i in range(2)]
    client = _build_tg_client(fresh, backfill)
    db = MagicMock()
    db.table.return_value.update.return_value.eq.return_value.execute = AsyncMock()
    pool = MagicMock()
    account = MagicMock(id="acc-1")

    result = await parse_single_group(
        group, client, account, db, pool,
        history_start="2026-01-01",
        hours_back=24,
        max_messages=1000,
    )

    assert result.ok is True
    assert result.backfill_kickstarted is False  # cursor was already set
    assert result.backfill_active is True  # cursor > history_start


def test_group_parse_result_new_fields_default_false() -> None:
    """GroupParseResult new BUG-394 fields default to False (backward compat)."""
    r = GroupParseResult(ok=True)
    assert r.backfill_active is False
    assert r.backfill_kickstarted is False
    assert r.backfill_completed is False


def test_intelligence_parser_result_new_counters_default_zero() -> None:
    """IntelligenceParserResult new BUG-394 counters default to 0."""
    from src.domains.intelligence.models import IntelligenceParserResult

    r = IntelligenceParserResult()
    assert r.groups_backfill_active == 0
    assert r.groups_backfill_kickstarted == 0
    assert r.groups_backfill_completed == 0
```

**Acceptance:**
- [ ] File created at `tests/unit/domains/intelligence/test_tg_parser_kickstart.py`
- [ ] All 6 tests pass: `pytest tests/unit/domains/intelligence/test_tg_parser_kickstart.py -v`
- [ ] No mocks of DB rows beyond service-boundary AsyncMocks (ADR-014: storage layer is the boundary, OK to mock here)
- [ ] `./test fast` green

---

### Execution Order

```
Task 3 (extend dataclasses, no logic change) ┐
Task 1 (kickstart branch) ───────────────────┤
Task 2 (speed boost) ────────────────────────┼──→ Task 4 (aggregate runner→heartbeat)
Task 3 setters in connection.py (3b, 3c) ────┘
Task 5 (SQL migration, parallel) ───────────────→ deploy after Task 1-4 land
Task 6 (tests) ──────────────────────────────────→ run after Tasks 1-4 (must pass)
```

**Linear safe order for coder:**
1. Task 3a (extend dataclasses) — no behavior change, safe to land first
2. Task 1 (kickstart branch in connection.py)
3. Task 2 (speed boost in connection.py)
4. Task 3b+3c (set new flags in connection.py result)
5. Task 4 (aggregate in runner + heartbeat)
6. Task 6 (tests for the whole chain)
7. Task 5 (SQL migration — independent, can land in same commit)

### Dependencies

- Task 1, 2, 3b, 3c all touch `tg_parser_connection.py` — coder MUST keep `caught_up`/`backfill_active`/`backfill_kickstarted`/`backfill_completed` local variables in scope across the function body.
- Task 4 depends on Task 3a fields existing in dataclass.
- Task 6 depends on Tasks 1-4 (otherwise tests fail).
- Task 5 (SQL) is independent of code changes — applies on next CI run.

### File LOC Budget Check

- `tg_parser_connection.py`: currently 403 lines (already over 400 limit). Adding ~25 lines (Task 1+2+3) takes it to ~428. **OK** because the file is documented as TECH-343 split — review whether to split again is out of scope for BUG-394; flag as warning.
- `models.py`: 195 lines + 6 lines = 201. OK.
- `tg_parser_runner.py`: 158 lines + 6 = 164. OK.
- `intelligence_jobs.py`: 579 lines + ~9 = 588. Already over 400 — flag as warning, no further split required for BUG-394.
- New test file: target ≤300 LOC. Above snippet is ~190 LOC. OK.
