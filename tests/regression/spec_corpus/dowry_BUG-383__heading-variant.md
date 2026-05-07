# Bug Fix: [BUG-383] Intelligence pipeline мёртв с 2026-04-07 + парсинг сконцентрирован на 2 из 12 акках

**Status:** done | **Priority:** P0 | **Date:** 2026-04-19

## Symptom

Пользователь: «парсинг держится на 2 перегретых акках (oleg-intelligence 410 групп cooldown, alexandr-parsing 27 групп 11 банов), хотя по спеке должно быть распределено на все 12 живых акков».

Реальность по данным PROD БД:

| Сигнал | Последняя активность |
|--------|----------------------|
| `tg_messages.created_at` MAX | **2026-04-07 13:03** (12 дней назад) |
| `tg_users.updated_at` MAX | **2026-04-07 16:02** |
| `tg_account_groups.synced_at` MAX | **2026-04-07 12:42** |
| `distribution_groups.last_parsed_at` MAX | **2026-04-07 13:03** |
| `distribution_groups.created_at` MAX | **2026-04-07 10:31** |
| Сообщения с `message_date >= 2026-04-08` | **0** |
| `scheduler_heartbeats.intelligence_parsing` | **2026-03-28 03:00** (22 дня) |
| `scheduler_heartbeats.outreach_sender` | **2026-04-01 06:21** (19 дней) |
| `scheduler_heartbeats.analyst_daily` | **2026-04-12 09:30 ERROR** (`invalid uuid "proof_agent"`) |
| `scheduler_heartbeats.hr_director_daily` | 2026-04-12 10:00 (молчит 8 дней) |
| `scheduler_heartbeats.ops_director_daily` | 2026-04-12 10:30 |

**То есть:** intelligence-парсинг физически остановился 2026-04-07, outreach — 2026-04-01, directors — 2026-04-12. Весь inbound-поток данных (лиды из TG групп) мёртв ≥12 дней. BUG-375 (prod-ingestion-health-alerts) ещё не задеплоен — никто не заметил.

При этом:
- `tg_group_activity_morning/afternoon/evening` — свежие (2026-04-19/20) → **SCHED_GROUPS работает**.
- `tg_warming_cycle`, `tg_pool_health_check` — свежие → **SCHED_POOL работает**.
- `ceo_weekly_digest`, `weekly_calibration` — свежие → **SCHED_SYSTEM работает**.

## Root Cause (5 Whys + Data)

**Why 1.** Почему intelligence мёртв?
`scheduler_heartbeats.intelligence_parsing` молчит с 2026-03-28. Commit `0585d66` (2026-04-06, TECH-343 pipeline-cleanup) переименовал все `MARKETING_*_ENABLED` → `SCHED_*` и оставил `SCHED_INTELLIGENCE`, `SCHED_OUTREACH`, `SCHED_DIRECTORS` закомментированными в `deploy/docker-compose.prod.yml` с примечанием `Enable domain groups after DEV testing`. Активированы были только `SCHED_SYSTEM`, `SCHED_POOL`, `SCHED_GROUPS`. Gate в `register_intelligence_jobs()` (`src/api/scheduler_jobs/job_registrars.py:173-226`) проверяет `_env("SCHED_INTELLIGENCE")` → FALSE → registrar вообще не регистрирует джобы.

**Why 2.** Откуда тогда 5253 tg_messages на 04-06 и 8864 на 04-07 (последний всплеск)?
Message_date распределение в этом батче: ~90 % — исторические сообщения 2022-2025 (**backfill Pass 2**), только 31 msg с `message_date = 2026-04-06`. Значит: между 2026-03-28 и 2026-04-07 парсинг ≈11 раз запускался вручную (`python -m src.domains.intelligence.tg_parser` или через `/pipeline`). `with_heartbeat` в ручных запусках не пишет — отсюда молчание. 2026-04-07 16:02 кто-то последний раз запустил вручную и перестал.

**Why 3.** Почему архитектурно парсинг концентрируется на 2 аккаунтах?
Параллельно существуют **два** TG-парсер-пайплайна, и они по-разному выбирают акки:

| Путь | Модуль | Фильтр акков | Покрытие групп |
|------|--------|--------------|----------------|
| `run_tg_pipeline` (marketing) | `src/domains/marketing/pipeline.py` → `TelegramGroupParser` | `purpose=PARSING` **только** | **437 групп** через oleg (410) + alexandr (27) |
| `intelligence_parsing` | `src/domains/intelligence/tg_parser.py` → `TGIntelligenceParser` | `_PURPOSES=(PARSING, OUTREACH)` (tg_parser.py:61) | **699 групп** через все 12 акков |

`TGIntelligenceParser.build_account_assignments()` уже использует scarce-first distribution (FTR-352), но его job `intelligence_parsing` не зарегистрирован (Why 1). Ручные запуски уходят через `marketing.pipeline.run_tg_pipeline` → `TelegramGroupParser(purpose=PARSING)` — отсюда 2 аккаунта.

**Why 4.** Почему `tg_account_groups` содержит memberships всех 12 акков (699 matches), если парсит только 2?
`account_groups_sync` (daily 06:00 UTC) честно синкает dialogs у всех акков (последний sync 2026-04-07 12:42 — тот же «последний ручной запуск»). Членства есть, но `TelegramGroupParser` не читает `tg_account_groups` — он берёт акки напрямую из пула по `purpose=PARSING`. Distribution_groups лежат в отдельной таблице и парсер пробует вступить в них сам, а не использует уже существующие memberships outreach-акков.

**Why 5.** Почему `analyst_daily` упал с `invalid uuid "proof_agent"`?
`src/api/scheduler_jobs/agent_jobs.py` (или analyst-specific) где-то передаёт `agent.name` (строка) в место, где ожидается `agent.id` (UUID). Hypothesis — код типа `get_agent_activity(agent_id=...)` получает `"proof_agent"` вместо UUID из agent registry. Это убило `analyst_daily` и побочно отключило digest. (Требует grep `proof_agent` в scheduler_jobs.)

**Why (bonus).** Почему us-104 нагенерил 39 банов и сидит в cooldown, но всё равно что-то его тыкает (`tg_account_usage` ежедневно пишет `flood_waits>0, messages_sent=0`)?
Какой-то лупер (подозреваемый: `outreach_sender` до 2026-04-01 или `life_simulation` до 2026-03-28) не чекает `status=cooldown` или `cooldown_until > now()` перед попыткой. После того как оба джоба встали — записи в usage должны были прекратиться; если они продолжают идти — есть третий лупер. Требует проверки tg_account_usage за последние 7 дней.

**REAL ROOT CAUSE:**
1. **[P0, код]** Деплой-конфиг: `SCHED_INTELLIGENCE`, `SCHED_OUTREACH`, `SCHED_DIRECTORS` закомментированы в `docker-compose.prod.yml` с 2026-04-06.
2. **[P0, архитектура]** Два параллельных TG-парсера (`marketing.pipeline.run_tg_pipeline` и `intelligence.tg_parser.TGIntelligenceParser`). Первый использует только `PARSING`-акки → single-point-of-failure oleg-intelligence.
3. **[P1, баг]** `analyst_daily` передаёт agent.name как UUID → error с 2026-04-12.
4. **[P2, баг]** us-104 не уважает `status=cooldown` у какого-то лупера (лупер нужно найти).

## Reproduction Steps

1. `select last_run_at, last_run_status, error_message from dowry.scheduler_heartbeats order by last_run_at desc;` — 14 из 25 джобов молчат ≥8 дней.
2. `grep -E "SCHED_(INTELLIGENCE|OUTREACH|DIRECTORS)" deploy/docker-compose.prod.yml` → все 3 закомментированы.
3. `select count(*) from dowry.tg_messages where created_at >= '2026-04-08'` → **0**.
4. Запуск `scripts/pipeline/run_tg_pipeline.py` вручную → в логах только `oleg-intelligence` и `alexandr-parsing` (purpose=parsing фильтр).
5. `select account_id, date, flood_waits, messages_sent from dowry.tg_account_usage where date >= '2026-04-13' order by date desc;` — us-104 строки с `flood_waits>0, messages_sent=0` (лупер не знает про cooldown).

## Evidence Tree

```
Intelligence pipeline dead 12d
│
├── BUG-A [P0, deploy]: SCHED_* flags закомментированы
│     └── deploy/docker-compose.prod.yml: SCHED_INTELLIGENCE/OUTREACH/DIRECTORS missing
│         ⇒ register_intelligence_jobs() gate FALSE
│         ⇒ 14 jobs не регистрируются
│         ⇒ tg_messages inbound мёртв
│
├── BUG-B [P0, arch]: tg_pipeline фильтрует purpose=PARSING
│     └── marketing.pipeline.TelegramGroupParser использует ТОЛЬКО 2 акка
│         ⇒ oleg 410 групп + alexandr 27 = 437 (vs 699 через все 12)
│         ⇒ концентрация → oleg cooldown, alexandr 11 банов
│         └── даже если BUG-A починить — остаётся marketing-путь как дублёр
│
├── BUG-C [P1, code]: analyst_daily uuid error
│     └── "invalid input syntax for type uuid: proof_agent"
│         ⇒ где-то agent.name попадает в agent_id колонку
│
├── BUG-D [P2, code]: us-104 zombie retry loop
│     └── tg_account_usage ежедневные строки с flood_waits>0
│         ⇒ какой-то лупер не проверяет status=cooldown
│
└── BUG-E [P1, ops]: нет heartbeat алертов
      └── BUG-375 (prod-ingestion-health-alerts) ещё queued
          ⇒ 22 дня молчания intelligence_parsing никто не заметил
          ⇒ ждём BUG-375 — НЕ в скоупе этой спеки
```

## Drift Log

**Checked:** 2026-04-20 by planner subagent
**Result:** light_drift

### Changes Detected (vs. spec written 2026-04-19)

| Claim в спеке | Реальность в `develop` (worktree BUG-383) | Action |
|---------------|-------------------------------------------|--------|
| `SCHED_INTELLIGENCE` закомментирован в `deploy/docker-compose.prod.yml` | `SCHED_INTELLIGENCE=true` **УЖЕ ЕСТЬ** в worker service (строка 29) | Partial — Task 1 сужается |
| `SCHED_OUTREACH` закомментирован | `SCHED_OUTREACH=true` **УЖЕ ЕСТЬ** (строка 30) | Partial — Task 1 сужается |
| `SCHED_DIRECTORS` закомментирован | **ОТСУТСТВУЕТ** | Confirmed |
| `SCHED_AGENT_JOBS` не упомянут в спеке | **ОТСУТСТВУЕТ**, но требуется для `analyst_daily/hr_director_daily/ops_director_daily` (см. `src/api/worker_tg_jobs.py:99`) | Add to Task 1 |
| "Task 3: источник proof_agent в `src/api/scheduler_jobs/`" | **НЕТ** — реальный источник в `src/domains/analytics/patterns.py:59,126` | Task 3 пересмотрен |
| "Task 4: guard в какой-то lifecycle-джобе" | Настоящая дыра в `src/infra/telegram/discovery/client_factory.py:32-87` (`get_client_for_account` + `connect_account` не проверяют `status/cooldown_until`) | Task 4 переадресован |

### References Updated

- Task 1: было «раскомментировать 3 переменные» → стало «добавить 2 недостающие (DIRECTORS + AGENT_JOBS)». Две другие уже включены в прошлом деплое (видимо вручную), но heartbeat-анализ говорит что registrars всё равно молчат → расследовать отдельно в smoke-тесте.
- Task 3: файл изменён с `src/api/scheduler_jobs/agent_jobs.py` → `src/domains/analytics/patterns.py`
- Task 4: файл изменён на `src/infra/telegram/discovery/client_factory.py` + data-level retire us-104

---

## Implementation Plan

4 задачи. Порядок: 1 → 2 → 3 → 4 (можно параллелить 2/3, но Task 1 — сначала, иначе остальное не активируется).

---

### Task 1 [P0]: Включить отсутствующие SCHED-флаги в PROD worker

**Type:** deploy-config
**Priority:** P0 (блокирует всё)
**Estimated:** 5 min + deploy

**Files:**
- Modify: `deploy/docker-compose.prod.yml` (worker service, ~lines 25-35)

**Context:**
Текущее состояние worker service env (верифицировано через worktree BUG-383):
```yaml
SCHED_SYSTEM: "true"
SCHED_POOL: "true"
SCHED_GROUPS: "true"
SCHED_INTELLIGENCE: "true"   # уже есть
SCHED_OUTREACH: "true"       # уже есть
SCHED_ENRICHMENT: "true"
SCHED_WB: "true"
SCHED_CONTENT: "true"
SCHED_PROMO: "true"
```

Отсутствуют: `SCHED_DIRECTORS`, `SCHED_AGENT_JOBS`.

Почему DIRECTORS и AGENT_JOBS — отдельные флаги: `register_director_jobs()` (если существует) vs `src/api/worker_tg_jobs.py:99` где `_daily_jobs` (analyst_daily, hr_director_daily, ops_director_daily) гейтятся именно `SCHED_AGENT_JOBS`, а не `SCHED_DIRECTORS`. Grep подтвердит что нужно ОБЕ.

**Steps:**

1. Grep точных флагов-гейтов, чтобы ничего не пропустить:
   ```bash
   grep -rn 'os.getenv.*"SCHED_' src/api/scheduler_jobs/ src/api/worker_tg_jobs.py
   grep -rn '_env.*SCHED_' src/api/scheduler_jobs/job_registrars.py
   ```

2. Добавить в `deploy/docker-compose.prod.yml` в секцию `worker` → `environment:` после `SCHED_OUTREACH`:
   ```yaml
   SCHED_DIRECTORS: "true"
   SCHED_AGENT_JOBS: "true"
   ```

3. Проверить, что SCHED_INTELLIGENCE и SCHED_OUTREACH реально в runtime env прод-контейнера:
   ```bash
   ssh dowry-prod "docker compose -f deploy/docker-compose.prod.yml exec worker env | grep SCHED_"
   ```
   Если они там есть, но `scheduler_heartbeats` всё равно молчат — это отдельный баг (возможно registrars не вызываются из main.py). Зафиксировать в blocked notes Task 1.

4. После merge → pull на prod-VDS → `docker compose -f deploy/docker-compose.prod.yml up -d worker`.

**Smoke-тест (через 15-60 мин после рестарта):**
```sql
select job_name, last_run_at, last_run_status, error_message
from dowry.scheduler_heartbeats
where job_name in (
  'intelligence_parsing','intelligence_analysis','signal_detection','signal_processing',
  'outreach_sender','reply_polling',
  'hr_director_daily','ops_director_daily','analyst_daily'
)
order by last_run_at desc;
```
Все должны быть `last_run_at >= now() - interval '2 hour'`, `last_run_status='success'`.

**Acceptance:**
- [ ] `SCHED_DIRECTORS=true` в worker env в `docker-compose.prod.yml`
- [ ] `SCHED_AGENT_JOBS=true` в worker env в `docker-compose.prod.yml`
- [ ] После деплоя 9 целевых джобов бьют heartbeat в течение часа
- [ ] `tg_messages` получает ≥1 новую запись в течение 4 часов

---

### Task 2 [P0]: Переключить `run_tg_pipeline` на `TGIntelligenceParser` (Variant A)

**Type:** code
**Priority:** P0 (распределяет нагрузку на все 12 акков)
**Estimated:** 30 min code + 1h test

**Files:**
- Modify: `src/domains/marketing/pipeline.py` (метод `run_tg_parsing`, ~line 67-100)
- Test: `tests/unit/domains/marketing/test_pipeline.py` (новый/дополнить существующий)

**Variant Decision: A (inline replace)**

Rationale:
- `run_tg_pipeline` / `LeadPipeline.run_tg_parsing()` имеет **минимум 4 внешних caller-а**:
  1. `src/api/scheduler_jobs/tg_jobs.py:24-43` → `LeadPipeline(client).run_tg_parsing()`
  2. `src/api/http/jobs.py:35` → `JOB_REGISTRY["tg_pipeline"]`
  3. `scripts/run_pipeline_once.py:130-137` → CLI shortcut
  4. `src/api/marketing_scheduler.py:65,144` → re-export
- Variant B (удалить `run_tg_pipeline`) потребует апдейтить все 4 места + тесты → blast radius x4.
- Variant A меняет одну строку внутри метода, сохраняет все API surface, все caller-ы работают как раньше, просто теперь используют scarce-first distribution через `tg_account_groups` для всех 12 акков.

**Current code (pipeline.py:67-100, verified 2026-04-20):**
```python
async def run_tg_parsing(self) -> IntelligenceParserResult:
    """Run TG marketing parsing cycle."""
    parser = TelegramGroupParser()   # ← покрывает только PARSING-purpose акки
    return await parser.run()
```

**Target code:**
```python
async def run_tg_parsing(self) -> IntelligenceParserResult:
    """Run TG marketing/intelligence parsing cycle.

    Uses TGIntelligenceParser with purposes=(PARSING, OUTREACH) for
    scarce-first distribution across all eligible accounts (BUG-383).
    """
    from src.domains.intelligence.tg_parser import TGIntelligenceParser
    parser = TGIntelligenceParser()  # default _PURPOSES=(PARSING, OUTREACH)
    return await parser.run()
```

**Verification grep before change:**
```bash
grep -rn "TelegramGroupParser" src/ tests/ scripts/
grep -rn "run_tg_pipeline\|run_tg_parsing" src/ tests/ scripts/
```
Чтобы увидеть всех, кто импортирует `TelegramGroupParser` напрямую — если кроме `pipeline.py` его никто не использует, можно в рамках Task 2 пометить класс `@deprecated` (но НЕ удалять — это отдельный TECH).

**Unit test:**
```python
# tests/unit/domains/marketing/test_pipeline.py
import pytest
from unittest.mock import AsyncMock, patch
from src.domains.marketing.pipeline import LeadPipeline
from src.domains.intelligence.models import IntelligenceParserResult

class TestRunTgParsingUsesIntelligenceParser:
    """BUG-383 Task 2: run_tg_parsing should use TGIntelligenceParser."""

    @pytest.mark.asyncio
    async def test_run_tg_parsing_instantiates_intelligence_parser(self):
        """run_tg_parsing() must create TGIntelligenceParser, not TelegramGroupParser."""
        fake_result = IntelligenceParserResult(
            groups_ok=0, groups_error=0, messages_saved=0, users_upserted=0
        )
        with patch(
            "src.domains.intelligence.tg_parser.TGIntelligenceParser"
        ) as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.run.return_value = fake_result
            mock_cls.return_value = mock_instance

            pipeline = LeadPipeline(client=None)
            result = await pipeline.run_tg_parsing()

            mock_cls.assert_called_once()  # default purposes=(PARSING, OUTREACH)
            mock_instance.run.assert_awaited_once()
            assert result is fake_result

    @pytest.mark.asyncio
    async def test_run_tg_parsing_does_not_call_telegram_group_parser(self):
        """Regression: старый TelegramGroupParser не должен инстанциироваться."""
        with patch(
            "src.domains.intelligence.tg_parser.TGIntelligenceParser"
        ) as mock_cls, patch(
            "src.domains.marketing.tg_parser.TelegramGroupParser"
        ) as old_cls:
            mock_cls.return_value = AsyncMock(
                run=AsyncMock(return_value=IntelligenceParserResult(0, 0, 0, 0))
            )
            await LeadPipeline(client=None).run_tg_parsing()
            old_cls.assert_not_called()
```

**Rules doc update:**
- `.claude/rules/domains/intelligence.md` — добавить в раздел Domain Patterns:
  > - **SSOT parser:** `TGIntelligenceParser(_PURPOSES=(PARSING, OUTREACH))` — единственный TG-парсер. `marketing.TelegramGroupParser` deprecated (BUG-383).

**Acceptance:**
- [ ] `LeadPipeline.run_tg_parsing()` инстанциирует `TGIntelligenceParser`
- [ ] Unit test выше проходит (pytest)
- [ ] `./test fast` — линтер чист, старых импортов нет
- [ ] После деплоя smoke-test на проде: `select distinct account_id from dowry.tg_messages where created_at >= now() - interval '6 hour'` → **≥8 аккаунтов** (было 2)
- [ ] `.claude/rules/domains/intelligence.md` обновлён

---

### Task 3 [P1]: Починить `analyst_daily` UUID error в `patterns.py`

**Type:** code
**Priority:** P1 (аналитика директора не работает, но не блокирует pipeline)
**Estimated:** 1h code + 1h test

**Files:**
- Modify: `src/domains/analytics/patterns.py` (метод `detect_patterns`, ~lines 45-140)
- Test: `tests/unit/domains/analytics/test_patterns.py` (существует, дополнить)

**Context — root cause:**

Верифицировано в worktree BUG-383:
- `dowry.decisions.agent_id` — **UUID** NOT NULL REFERENCES `agents(id)` (migration `20260124000003_create_decisions.sql`)
- `dowry.escalations.from_agent_id` — **UUID** NOT NULL REFERENCES `agents(id)` (migration `20260124000005_create_escalations.sql`)
- `dowry.agents.agent_class` — **TEXT** (типа `"proof_agent"`, `"analyst_agent"`)

В `src/domains/analytics/patterns.py`:
```python
# Line ~56-63 — BUG
rows = await client.from_("decisions") \
    .select("confidence, outcome, created_at") \
    .eq("agent_id", agent_class) \   # ← агент-строка в UUID-колонку → Postgres error
    .gte("created_at", since_date) \
    .execute()

# Line ~123-130 — SILENT BUG (no error, но возвращает пусто)
esc_rows = await client.from_("escalations") \
    .select("created_at, reason_type") \
    .eq("from_agent", agent_class) \   # ← колонки `from_agent` нет вообще; есть `from_agent_id` UUID
    .execute()
```

Ошибка `invalid input syntax for type uuid: "proof_agent"` падает именно на первом запросе → падает весь `analyst_daily` job → heartbeat=ERROR.

**Fix pattern:** использовать JOIN через `dowry.agents` (как это делают существующие RPC-функции `get_daily_accuracy`, `get_agent_performance` в миграции `20260308000001_recreate_analytics_functions_dowry.sql`).

**Option A (preferred, no migration):** использовать Supabase/PostgREST `select` с nested resource + filter:
```python
rows = await client.from_("decisions") \
    .select("confidence, outcome, created_at, agents!inner(agent_class)") \
    .eq("agents.agent_class", agent_class) \
    .gte("created_at", since_date) \
    .execute()
```
и аналогично для escalations:
```python
esc_rows = await client.from_("escalations") \
    .select("created_at, reason_type, agents!inner(agent_class)") \
    .eq("agents.agent_class", agent_class) \
    .execute()
```
Путь requires `decisions.agent_id → agents.id` FK уже в БД (есть, подтверждено миграцией) и наличие `agents` таблицы в search_path `dowry`.

**Option B (more invasive):** создать новую RPC `get_decisions_for_class(p_agent_class TEXT, p_since TIMESTAMPTZ)` + миграцию. Отложить — не нужно для фикса.

**Steps:**

1. Прочитать `src/domains/analytics/patterns.py` целиком, найти ВСЕ места где `.eq("agent_id", ...)` или `.eq("from_agent", ...)` стоят.
2. Заменить оба запроса на Option A.
3. Добавить защитную логику: если результат пустой (агент не зарегистрирован в `agents` таблице) — вернуть нейтральный `PatternsReport` вместо exception.
4. Прогнать unit-тест:
   ```python
   # tests/unit/domains/analytics/test_patterns.py
   class TestPatternsNoUUIDError:
       """BUG-383 Task 3: detect_patterns accepts agent_class string, not UUID."""

       @pytest.mark.asyncio
       async def test_detect_patterns_with_agent_class_string(self):
           """agent_class='proof_agent' must not produce UUID syntax error."""
           # Given realistic client with dowry.agents having agent_class=proof_agent
           # When detect_patterns("proof_agent", since=...) called
           # Then no exception, returns PatternsReport
           ...
       @pytest.mark.asyncio
       async def test_detect_patterns_unknown_agent(self):
           """Unknown agent_class returns empty PatternsReport, not exception."""
           ...
   ```
5. Run `./test fast` + integration test на dev:
   ```python
   # tests/domains/analytics/test_analyst.py (существует)
   # добавить тест который реально дёргает Supabase клиент на DEV
   ```

**Also:** проверить `src/domains/analytics/anomalies.py` — он уже использует RPC и OK, но grep на всякий:
```bash
grep -rn '\.eq("agent_id"\|\.eq("from_agent"' src/domains/analytics/
```

**Acceptance:**
- [ ] `patterns.py` не содержит `.eq("agent_id", <string>)` ни `.eq("from_agent", <string>)`
- [ ] Unit-тесты для `proof_agent`, `analyst_agent`, `nonexistent_agent` — все зелёные
- [ ] После деплоя: `scheduler_heartbeats.analyst_daily` с `last_run_status='success'` 2 дня подряд
- [ ] В логах нет `invalid input syntax for type uuid`

---

### Task 4 [P2]: Защитить `client_factory.get_client_for_account` от cooldown + retire us-104

**Type:** code + data-level ops
**Priority:** P2 (us-104 спамит банами, но не блокирует других; пул работает)
**Estimated:** 1h code + 30min test + 15min data fix

**Files:**
- Modify: `src/infra/telegram/discovery/client_factory.py` (функции `get_client_for_account`, `connect_account`, ~lines 32-120)
- Test: `tests/unit/infra/telegram/test_cooldown_guard.py` (новый)

**Context — root cause:**

Верифицировано в worktree BUG-383:
- `TGAccountPool.get_client()` (`src/infra/telegram/pool.py:278-344`) использует `get_account()`/`get_account_simple()` которые фильтруют `status=active` и `cooldown_until < now()` — safe.
- RPC `get_available_tg_account` (migration `20260408000001_fix_tg_pool_rpc_warming_and_usage.sql`) тоже корректно фильтрует `status = 'active' AND (cooldown_until IS NULL OR cooldown_until < now())`.
- `parsing_group_joins.run_parsing_joins_cycle` (line 315-321) фильтрует `status=ACTIVE` — safe.
- **НО:** `src/infra/telegram/discovery/client_factory.py::get_client_for_account(account_data: dict)` принимает уже загруженный dict и **НЕ ПРОВЕРЯЕТ** `status` / `cooldown_until`. Он полагается на то, что caller загрузил только живые акки.
- Есть caller (подозреваемый: discovery strategy или manual debug tool) который грузит из БД без cooldown-фильтра и пихает cooldown-акк в `get_client_for_account` → tg_account_usage пишется → флоды умножаются.

**Fix — код:**

Добавить guard в начале `get_client_for_account` и `connect_account`:

```python
# src/infra/telegram/discovery/client_factory.py
from src.shared.errors import AccountInCooldownError  # create if missing

_ACCEPTABLE_STATUSES = {"active", "warming_up"}

def _assert_account_usable(account_data: dict) -> None:
    """Raise AccountInCooldownError if account is not safe to use.

    BUG-383 Task 4: guard for callers passing raw DB rows.
    """
    status = account_data.get("status", "").lower()
    if status not in _ACCEPTABLE_STATUSES:
        raise AccountInCooldownError(
            f"account {account_data.get('id')} in status={status!r}, "
            f"cannot instantiate Telethon client"
        )
    cooldown = account_data.get("cooldown_until")
    if cooldown is not None:
        # cooldown может быть str ISO, datetime или None
        ...  # parse and compare to utcnow()
        if cooldown_dt > datetime.now(timezone.utc):
            raise AccountInCooldownError(...)

@asynccontextmanager
async def get_client_for_account(account_data: dict):
    _assert_account_usable(account_data)   # ← NEW
    # ... существующая логика (encryption, proxy, device_fingerprint, connect)
```

В `src/shared/errors.py` (или domain-specific errors.py) добавить:
```python
class AccountInCooldownError(Exception):
    """Account is in cooldown or banned — refuse to start Telethon client."""
```

**Unit test:**
```python
# tests/unit/infra/telegram/test_cooldown_guard.py
import pytest
from datetime import datetime, timedelta, timezone
from src.infra.telegram.discovery.client_factory import get_client_for_account
from src.shared.errors import AccountInCooldownError

class TestCooldownGuard:
    """BUG-383 Task 4: client_factory.get_client_for_account rejects cooldown accounts."""

    @pytest.mark.asyncio
    async def test_rejects_cooldown_status(self):
        account = {
            "id": "us-104-uuid", "status": "cooldown",
            "cooldown_until": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "session_data": "...", "proxy_url": "http://x",
        }
        with pytest.raises(AccountInCooldownError):
            async with get_client_for_account(account):
                pass

    @pytest.mark.asyncio
    async def test_rejects_banned_status(self):
        account = {"id": "x", "status": "banned", "session_data": "...", "proxy_url": "x"}
        with pytest.raises(AccountInCooldownError):
            async with get_client_for_account(account):
                pass

    @pytest.mark.asyncio
    async def test_rejects_active_with_future_cooldown(self):
        account = {
            "id": "x", "status": "active",
            "cooldown_until": (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
            "session_data": "...", "proxy_url": "x",
        }
        with pytest.raises(AccountInCooldownError):
            async with get_client_for_account(account):
                pass

    @pytest.mark.asyncio
    async def test_accepts_active_with_expired_cooldown(self):
        account = {
            "id": "x", "status": "active",
            "cooldown_until": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            "session_data": "<valid_fernet>", "proxy_url": "socks5://x",
        }
        # не должно бросить AccountInCooldownError (может бросить Telethon error — это ок)
        with pytest.raises(Exception) as exc_info:
            async with get_client_for_account(account):
                pass
        assert not isinstance(exc_info.value, AccountInCooldownError)
```

**Data-level fix (separate from code):**

После того как код гардов задеплоится и cooldown-лупер остановится, вручную retire us-104:

```sql
-- PROD, один раз, через Supabase SQL editor или psql с DATABASE_URL
UPDATE dowry.tg_accounts
SET status = 'retired',
    notes = COALESCE(notes, '') || E'\n[BUG-383 2026-04-20] retired: ban_count=39, concentration burn'
WHERE name = 'us-104' OR id = '<us-104-uuid>';

-- Verify
SELECT id, name, status, ban_count, cooldown_until, notes
FROM dowry.tg_accounts WHERE name = 'us-104';
```

Этот шаг — в runbook-комментарии к PR, не в код. После retire пул игнорирует аккаунт навсегда, последующие разборы лупера не нужны.

**Find hidden caller (optional diagnostic, not in-scope for fix):**
```bash
grep -rn "get_client_for_account\|connect_account" src/ scripts/
```
Если обнаружится caller без cooldown-фильтра (например, скрипт из `scripts/`) — добавить в backlog отдельный TECH на cleanup.

**Acceptance:**
- [ ] `get_client_for_account` и `connect_account` в `client_factory.py` вызывают `_assert_account_usable`
- [ ] `AccountInCooldownError` определён в `src/shared/errors.py` (или `src/infra/telegram/errors.py`)
- [ ] 4 unit-теста в `test_cooldown_guard.py` — зелёные
- [ ] us-104 в БД: `status='retired'`, не появляется в `get_available_tg_account`
- [ ] После 3 дней deploy: `select count(*) from dowry.tg_account_usage where account_id = <us-104> and date >= now()::date - interval '3 days'` → 0

---

### Execution Order

```
Task 1 (deploy-config) ──→ триггерит 14 джобов; после этого обязательно smoke-test
     │
     └──→ Task 2 (code)  ──┐
                           ├──→ merge вместе; Task 3 и Task 4 независимы
          Task 3 (code)  ──┤
                           │
          Task 4 (code)  ──┘
                           │
                           └──→ после merge: data-level retire us-104 (ручная SQL operация)
```

### Dependencies

- Task 1 → блокер для всего остального (без флагов scheduler вообще не видит эти джобы)
- Task 2, 3, 4 — независимы между собой (разные файлы, разные тесты)
- Data-fix us-104 — ТОЛЬКО после мержа Task 4 в prod

### Research Sources

- Миграции локально (worktree `.worktrees/BUG-383`): `20260124000003_create_decisions.sql`, `20260124000005_create_escalations.sql`, `20260308000001_recreate_analytics_functions_dowry.sql`, `20260408000001_fix_tg_pool_rpc_warming_and_usage.sql`
- Code references: `src/domains/marketing/pipeline.py:67-100`, `src/domains/intelligence/tg_parser.py:61,197`, `src/domains/analytics/patterns.py:59,126`, `src/infra/telegram/discovery/client_factory.py:32-120`, `src/infra/telegram/pool.py:148-344`, `src/api/worker_tg_jobs.py:99-107`
- `.claude/rules/domains/intelligence.md` — scarce-first distribution (FTR-352), health_score ≠ join coverage (BUG-354/TECH-355)
- `.claude/rules/domains/tg-pool.md` — LRU + cooldown lifecycle
- Drift Log (above) — SCHED_INTELLIGENCE/OUTREACH уже в prod, missing DIRECTORS + AGENT_JOBS

## Files Allowed to Modify

**In-scope для этой спеки:**
- `deploy/docker-compose.prod.yml` — включить SCHED_* флаги
- `src/domains/marketing/pipeline.py` — переключить на TGIntelligenceParser
- `src/api/scheduler_jobs/agent_jobs.py` (или где сидит analyst_daily) — fix uuid error
- `src/api/scheduler_jobs/job_registrars.py` — если выбран вариант B в Task 2
- `src/domains/intelligence/tg_parser.py` — только если при переключении вылезут несовместимости сигнатур
- `.claude/rules/domains/intelligence.md` — обновить паттерны
- `tests/integration/domains/intelligence/test_tg_parser.py` — смоук-тест что все 12 purpose-матчей работают
- `scripts/pipeline/run_tg_pipeline.py` — если использует старую сигнатуру

**Out-of-scope (НЕ трогать):**
- `src/api/http/*` — никаких изменений API
- `supabase/migrations/*` — схема не меняется
- `src/domains/outreach/*` — отдельная проблема (purpose=outreach акки)
- BUG-375 (prod-ingestion-health-alerts) — закроет отдельный spec

## Tests

### Test 1 [integration, CRITICAL]
**Файл:** `tests/integration/api/scheduler_jobs/test_sched_flags.py`
**Setup:** env `SCHED_ENABLED=true SCHED_INTELLIGENCE=true SCHED_OUTREACH=true SCHED_DIRECTORS=true`.
**Assert:** `register_intelligence_jobs(scheduler)` регистрирует ≥5 джобов (intelligence_parsing, intelligence_analysis, signal_detection, signal_processing, dossier_archiver); `register_outreach_jobs` — ≥2 (outreach_sender, reply_polling); `register_director_jobs` — ≥3 (hr/ops/analyst).

### Test 2 [integration, CRITICAL]
**Файл:** `tests/integration/domains/intelligence/test_full_parsing_distribution.py`
**Setup:** замокать TG пул из 12 акков (2 parsing + 10 outreach), загрузить в `distribution_groups` 100 групп с наложенным distribution через `tg_account_groups` (по 8-40 групп на акк).
**Assert:** после `TGIntelligenceParser(purposes=(PARSING, OUTREACH)).run()`:
- `result.accounts_used >= 10` (ни один акк не должен быть skipped без причины)
- ни один акк не получил >120 групп (scarce-first должен балансировать)
- `result.groups_ok >= 90` (допускаем 10% floodwait/error)

### Test 3 [unit]
**Файл:** `tests/unit/domains/marketing/test_run_tg_pipeline_uses_intelligence.py`
**Assert:** `run_tg_pipeline()` (после фикса) создаёт `TGIntelligenceParser`, не `TelegramGroupParser`. Проверить через monkeypatch `TGIntelligenceParser.__init__` → `called=True` с `purposes=(PARSING, OUTREACH)`.

### Test 4 [unit]
**Файл:** `tests/unit/api/scheduler_jobs/test_analyst_daily_uuid.py`
**Input:** агент с `id=UUID(...), name="proof_agent"`.
**Assert:** джоб `analyst_daily` выполняется без `invalid input syntax for type uuid`. Нет строк где `agent.name` передаётся в параметр типа UUID.

### Test 5 [unit, regression]
**Файл:** `tests/unit/infra/telegram/test_cooldown_guard.py`
**Setup:** us-104 в `status=cooldown, cooldown_until=now()+1d`.
**Assert:** любая попытка `pool.get_client(account=us-104)` бросает `AccountInCooldownError`, tg_account_usage НЕ пишется.

## Out-of-Scope Ideas (Backlog)

- **Heartbeat freshness SLO dashboard.** Стандарт: каждый job должен бить heartbeat с interval + 10%. → BUG-375.
- **Retire policy для акков ban_count ≥ 20.** us-104 = 39 банов. Нужен автоматический retire через `lifecycle_jobs`. Отдельная спека.
- **Удалить `TelegramGroupParser` вместе с `purpose=PARSING`-filter-semantikой.** После Task 2 остаётся dead code. Отдельный TECH.
- **PARSING / OUTREACH slices в `TGAccountPurpose`:** сейчас deprecated split. Возможно все акки слить в единый pool с risk_level-разделением. ARCH-задача.

## Risks

1. **После включения `SCHED_OUTREACH` — sender начнёт рассылать.** Queue может быть устаревший. Рекомендую: перед фиксом проверить `dowry.outreach_queue` на записи старше 7 дней и очистить/пометить stale.
2. **Переключение `run_tg_pipeline` на TGIntelligenceParser** может создать нагрузку на все 12 акков разом. Smart offset (`last_parsed_at - 1h`) защищает, но backfill Pass 2 у каждого акка запустится → кратковременный всплеск trafic. Допустимо, floodwait's ретраи в parser уже есть.
3. **analyst_daily uuid fix:** если проблема в хранимой data (где-то в agent_states таблице запись с `agent_id='proof_agent'` строкой), фикс кода не поможет. Нужен data-cleanup.

## Success Criteria

- [ ] Через 24h после merge: все 14 ранее молчавших heartbeats — `last_run_at >= now() - 4h`.
- [ ] `tg_messages.created_at` MAX растёт ежедневно (>500 msg/day).
- [ ] `tg_account_usage` показывает активность ≥8 из 12 акков (не только oleg+alexandr).
- [ ] `analyst_daily` heartbeat `status=success` два дня подряд.
- [ ] `tg_account_usage` для us-104 не содержит новых строк >= 3 дней (cooldown уважается).

## Blueprint Reference

- ADR-105 (TG Account Pool): multi-account distribution — цель этой спеки.
- TECH-343 (pipeline-cleanup, 2026-04-05): источник BUG-A.
- TECH-337 (scheduler-domain-groups): источник SCHED_* флаг-архитектуры.
- FTR-352 (scarce-first distribution): механизм который работает, но не запускается.
- BUG-375 (prod-ingestion-health-alerts, queued): закроет BUG-E, чтобы такое не повторилось.
