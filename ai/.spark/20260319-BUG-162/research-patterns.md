# Pattern Research — Orphan Slot Watchdog (BUG-162)

## Context

`compute_slots` в SQLite хранит `pueue_id` активной задачи. Когда pueue-задача исчезает ненормально
(SIGKILL, `pueue reset`, рестарт сервиса, ARCH-161 миграция), `callback.py` не вызывается —
слот остаётся заблокированным навсегда. Оркестратор видит `get_available_slots() == 0` и перестаёт
диспатчить новые задачи.

Текущая схема: `compute_slots(slot_number, provider, project_id, pueue_id, acquired_at)`.
Слот занят когда `project_id IS NOT NULL`. Освобождение — исключительно через `callback.py`.

---

## Approach 1: Proactive Watchdog (сверка с pueue status)

**Source:** [Orphaned RunningTasks entries — Semaphore UI issue #3681](https://github.com/semaphoreui/semaphore/issues/3681)
и [SQLite in Practice (2): Atomic Claims](https://docsaid.org/en/blog/sqlite-job-queue-atomic-claim)

### Description

В начале каждого цикла `process_all_projects()` вызывается `release_orphan_slots()`.
Функция делает `pueue status --json`, собирает множество активных `pueue_id` (Running + Queued),
затем находит в `compute_slots` записи, чьи `pueue_id` в это множество не входят — и освобождает их.
Именно этот подход предложен в inbox-описании задачи.

### Pros

- Детерминированная корректность: слот освобождается ровно тогда, когда задача точно мертва
- Нет ложных срабатываний: Running и Queued задачи защищены от освобождения
- Не требует изменений схемы БД
- Полностью укладывается в существующий цикл оркестратора (300 с)
- Единственный вызов `pueue status --json` покрывает все слоты сразу

### Cons

- Зависимость от доступности pueue CLI: если демон завис или CLI таймаутится, watchdog пропускает цикл
- Если `pueue status` вернул пустой список из-за ошибки парсинга — риск false positive освобождения
  (нужна явная защита: не освобождать если `running_ids` пустое множество)
- При одновременном диспатче нового слота и watchdog-чтении нужна осторожность с транзакциями
  (уже решено через `BEGIN IMMEDIATE` в db.py)

### Compute Cost

**Estimate:** ~$1 (R2: содержится в 2 файлах)
**Why:** Новая функция `release_orphan_slots()` в `orchestrator.py` + вспомогательная в `db.py`.
Один вызов watchdog в начале `main()` цикла. Blast radius: 2 файла, нет изменений схемы,
нет изменений callback. Риск R2 — rollback тривиален.

### Example Source

```python
def get_pueue_running_ids() -> set[int]:
    """Return set of pueue_ids that are Running or Queued. Empty set = CLI error."""
    try:
        r = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(r.stdout)
        return {
            int(tid)
            for tid, task in data.get("tasks", {}).items()
            if isinstance(task.get("status"), dict)
            and ("Running" in task["status"] or "Queued" in task["status"])
        }
    except Exception:
        return set()  # safe: don't release on CLI error


def release_orphan_slots() -> int:
    """Free slots whose pueue tasks are no longer Running/Queued. Returns count released."""
    running_ids = get_pueue_running_ids()
    if not running_ids and ...:  # guard: если CLI упал — пропустить
        return 0
    released = 0
    with get_db(immediate=True) as conn:
        rows = conn.execute(
            "SELECT slot_number, pueue_id FROM compute_slots "
            "WHERE pueue_id IS NOT NULL"
        ).fetchall()
        for row in rows:
            if row["pueue_id"] not in running_ids:
                conn.execute(
                    "UPDATE compute_slots SET project_id=NULL, pid=NULL, "
                    "pueue_id=NULL, acquired_at=NULL WHERE slot_number=?",
                    (row["slot_number"],),
                )
                log.warning("released orphan slot=%d pueue_id=%d",
                            row["slot_number"], row["pueue_id"])
                released += 1
    return released
```

---

## Approach 2: TTL / Lease Auto-Expiry (acquired_at + порог)

**Source:** [SQLite in Practice (3): Save Your Workers — lease+heartbeat pattern](https://docsaid.org/en/blog/sqlite-lease-heartbeat-recovery)
и [Lease Pattern: A Lock With an Expiration Date](https://woodruff.dev/lease-pattern-in-net-a-lock-with-an-expiration-date-that-saves-your-data/)

### Description

В схему добавляется `lease_expires_at` (или используется `acquired_at` + фиксированный TTL).
В начале каждого цикла слоты, у которых `acquired_at < now - TTL`, освобождаются автоматически —
без обращения к pueue. Это классический lease-паттерн из distributed systems: владение временное,
не вечное. Heartbeat-вариант требует, чтобы `callback.py` или `run-agent.sh` периодически обновляли
`lease_expires_at`; без heartbeat — чистый TTL.

### Pros

- Не зависит от pueue CLI: работает даже если `pueued` недоступен
- Простой SQL-запрос без внешних вызовов
- Самодостаточен: не нужно знать ничего о pueue
- Хорошо известный паттерн из Redis/Postgres экосистем

### Cons

- Требует выбора TTL: слишком маленький — ложные срабатывания на длинных задачах (claude runner
  работает до 60 минут); слишком большой — долгое ожидание после краша
- Реальные задачи в этом проекте живут от 15 минут до 1 часа+ → TTL должен быть ≥ 90 мин,
  что даёт окно залипания до 90 минут после краша
- Без heartbeat — бесполезен для задач дольше TTL
- С heartbeat — нужно менять `run-agent.sh` или `claude-runner.py` для регулярного обновления
  `acquired_at`, что значительно расширяет blast radius
- Требует миграции схемы (добавить колонку) или договорённости о семантике `acquired_at`

### Compute Cost

**Estimate:** ~$5 (R1: изменения схемы + несколько файлов)
**Why:** Без heartbeat: изменение `db.py` + `orchestrator.py` + миграция `schema.sql` (~3 файла).
С heartbeat: дополнительно `run-agent.sh` или `claude-runner.py` (~5 файлов, изменение
поведения агентного runner'а). Схемная миграция — R1 по классификации ADR-017.

### Example Source

```python
# Без heartbeat — чистый TTL
TTL_MINUTES = 90

def release_expired_slots() -> int:
    """Release slots older than TTL_MINUTES. Returns count released."""
    with get_db(immediate=True) as conn:
        result = conn.execute(
            "UPDATE compute_slots SET project_id=NULL, pid=NULL, pueue_id=NULL, "
            "acquired_at=NULL "
            "WHERE pueue_id IS NOT NULL AND acquired_at IS NOT NULL "
            "AND acquired_at < strftime('%Y-%m-%dT%H:%M:%SZ', "
            "  datetime('now', '-' || ? || ' minutes'))",
            (TTL_MINUTES,),
        )
        return result.rowcount
```

Источник паттерна: [SQLite lease-heartbeat recovery](https://docsaid.org/en/blog/sqlite-lease-heartbeat-recovery)

---

## Approach 3: Callback-Only Hardening (гарантия доставки callback)

**Source:** [pueue callback not executed — issue #236](https://github.com/Nukesor/pueue/issues/236)
и [Worker Heartbeats and Job Recovery — slepp.ca](https://slepp.ca/2026/02/01/deep-dive-worker-heartbeat/)

### Description

Вместо обнаружения сирот — устранить саму возможность их появления.
Callback в pueue конфигурируется так, чтобы срабатывать при любом завершении задачи (Success, Failure,
Killed). Дополнительно: `run-agent.sh` оборачивается в `trap` на EXIT/SIGTERM/SIGINT для явного
освобождения слота даже при SIGKILL-невозможном сценарии. Плюс: при старте оркестратора —
одноразовый `startup_cleanup()` для задач с `acquired_at` старше времени последнего рестарта сервиса.

### Pros

- Атакует корневую причину, а не симптом
- Не требует периодического polling'а pueue
- Startup cleanup надёжно закрывает gap между рестартами
- Нет false positive риска (startup знает точное время рестарта)

### Cons

- pueue callback **не вызывается при `pueued` SIGKILL** (daemon сам убит) — это документированное
  ограничение, подтверждённое issue #236 и поведением pueue 4.0
- bash `trap` на EXIT не перехватывает SIGKILL (POSIX: нельзя поймать сигнал 9)
- Startup cleanup работает только при рестарте оркестратора, не покрывает случай "оркестратор жив,
  но задача исчезла из pueue без рестарта"
- Комбинирование trap + startup + callback усложняет логику без полного покрытия
- Не решает проблему если `pueued` был `pueue reset`-ован без рестарта оркестратора

### Compute Cost

**Estimate:** ~$5 (R1: изменения в нескольких файлах + тонкая логика)
**Why:** `run-agent.sh` (trap), `callback.py` (проверка состояния), `orchestrator.py`
(startup cleanup). 3-4 файла. Логика trap'ов и startup detection нетривиальна,
требует тестирования edge cases.

### Example Source

```bash
# run-agent.sh — trap для частичного покрытия (кроме SIGKILL)
cleanup() {
    local pueue_id="${PUEUE_TASK_ID:-}"
    if [[ -n "$pueue_id" ]]; then
        python3 "$SCRIPT_DIR/db.py" release-slot "$pueue_id" || true
    fi
}
trap cleanup EXIT SIGTERM SIGINT
```

```python
# orchestrator.py startup — освободить слоты старее момента старта
def startup_cleanup() -> None:
    """On restart: release slots acquired before this process started."""
    start_time = datetime.now(tz=timezone.utc)
    with get_db(immediate=True) as conn:
        conn.execute(
            "UPDATE compute_slots SET project_id=NULL, pid=NULL, pueue_id=NULL, "
            "acquired_at=NULL WHERE pueue_id IS NOT NULL AND acquired_at < ?",
            (start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),),
        )
```

---

## Approach 4: Hybrid — Watchdog + TTL как defense-in-depth

**Source:** [Process Supervision for AI Agents — Zylos Research](https://zylos.ai/research/2026-02-20-process-supervision-health-monitoring-ai-agents)
и [Synchronized Expiration in Distributed Systems — Sahil Kapoor](https://sahilkapoor.com/synchronized-expiration-in-distributed-systems/)

### Description

Первый эшелон: watchdog Approach 1 (сверка с pueue status) как основной механизм.
Второй эшелон: TTL Approach 2 как фоновая страховка — освобождает слоты если watchdog
не смог обратиться к pueue несколько циклов подряд (CLI таймаут, demон завис).
TTL устанавливается агрессивно большим (120+ минут) чтобы не было false positive.
Два независимых механизма, каждый с разными failure modes.

### Pros

- Нет единой точки отказа в механизме защиты
- Watchdog реагирует быстро (5 мин), TTL — страховка на деградацию pueue
- TTL агрессивно большой → нет false positive для длинных задач
- Watchdog покрывает нормальный путь, TTL — катастрофный

### Cons

- Избыточность для текущего масштаба (4 слота, один VPS)
- Два кодовых пути = двойная поверхность для багов
- TTL в 120 минут фактически бесполезен как страховка: проблема обнаруживается через 2 часа
- YAGNI: добавляет сложность которая не нужна пока не доказана недостаточность Approach 1
- Требует изменения схемы (для TTL) + логика watchdog (2x effort Approach 1)

### Compute Cost

**Estimate:** ~$5 (R1: изменения схемы + 3 файла)
**Why:** Approach 1 (~$1) + TTL-колонка в schema.sql + release_expired_slots() в db.py.
Дополнительные $3-4 за интеграцию двух механизмов и их тестирование без взаимного мешания.

### Example Source

```python
def process_all_projects() -> None:
    # Эшелон 1: watchdog (быстрый, точный)
    released = release_orphan_slots()
    if released:
        log.warning("watchdog released %d orphan slots", released)

    # Эшелон 2: TTL fallback (медленный, независимый)
    expired = release_expired_slots(ttl_minutes=120)
    if expired:
        log.warning("TTL released %d expired slots", expired)

    for proj in db.get_all_projects():
        ...
```

---

## Comparison Matrix

| Criteria | Approach 1: Watchdog | Approach 2: TTL | Approach 3: Callback-Only | Approach 4: Hybrid |
|----------|---------------------|-----------------|--------------------------|-------------------|
| Correctness (no false positives) | High | Medium | High | High |
| Recovery speed after crash | High (next cycle, 5 min) | Low (up to TTL, 90+ min) | Medium (startup only) | High |
| Dependency on pueue CLI | Yes (guarded) | No | Partial | Yes + No |
| Schema changes required | No | Yes | No | Yes |
| Files affected | 2 | 3-4 | 3-4 | 4-5 |
| Complexity | Low | Low | Medium | Medium |
| Covers pueued SIGKILL | Yes | Yes | No | Yes |
| Covers `pueue reset` без рестарта | Yes | Yes | No | Yes |
| Covers CLI timeout in watchdog | N/A | Yes | N/A | Yes |
| Compute cost | ~$1 | ~$5 | ~$5 | ~$5 |
| Risk level | R2 | R1 | R1 | R1 |

**Rating scale:** Low / Medium / High

---

## Recommendation

**Selected:** Approach 1 (Proactive Watchdog)

### Rationale

Задача формулирует конкретный failure mode: pueue-задача исчезает, callback не вызывается, слот
залипает. Watchdog атакует этот failure mode напрямую и максимально хирургически. Он работает
точно, быстро (следующий цикл, ≤5 минут), не требует изменений схемы и не затрагивает callback
или runner.

Ключевые факторы:

1. **Скорость реакции.** Watchdog освобождает orphan через 5 минут после краша. TTL потребует 90+
   минут (реальная длина задач в этом проекте достигает 60 мин → TTL должен быть запасным).
   Для orchestrator deadlock это критично: каждые 5 минут — это цена одного пропущенного цикла
   диспатча.

2. **Отсутствие false positives по конструкции.** Watchdog освобождает слот только если задача
   точно не Running и не Queued. Единственный риск — пустой ответ CLI — явно обрабатывается:
   если `running_ids` пустое множество при наличии слотов, цикл пропускается (`guard condition`).
   Semaphore UI issue #3681 подтверждает этот же паттерн как промышленную практику.

3. **Минимальный blast radius.** 2 файла (`orchestrator.py` + `db.py`), нет изменений схемы,
   нет изменений в `callback.py`/`run-agent.sh`. Риск R2 — полностью rollback-able одним коммитом.

### Trade-off Accepted

Мы принимаем зависимость от pueue CLI. Если `pueued` недоступен, watchdog пропускает цикл
(не освобождает слоты) — что является безопасным fallback, лучше false positive. В этой
ситуации оркестратор всё равно не может диспатчить задачи (pueue недоступен), так что
залипший слот не ухудшает ситуацию.

Мы отказываемся от TTL как второго эшелона (Approach 4) — YAGNI. Если в будущем появится
паттерн CLI-недоступности pueue без его смерти (маловероятно на одном VPS), TTL можно добавить
позже как отдельный PR без изменения архитектуры watchdog.

---

## Research Sources

- [SQLite in Practice (2): Atomic Claims — DOCSAID](https://docsaid.org/en/blog/sqlite-job-queue-atomic-claim) — BEGIN IMMEDIATE паттерн, atomic slot claim
- [SQLite in Practice (3): Save Your Workers — DOCSAID](https://docsaid.org/en/blog/sqlite-lease-heartbeat-recovery) — lease+heartbeat schema, TTL паттерн
- [Orphaned RunningTasks entries block tasks forever — Semaphore UI #3681](https://github.com/semaphoreui/semaphore/issues/3681) — watchdog reaper как промышленная практика для task queues
- [Worker Heartbeats and Job Recovery — slepp.ca](https://slepp.ca/2026/02/01/deep-dive-worker-heartbeat/) — ownership record паттерн, partial index для scan
- [pueue callback not executed — issue #236](https://github.com/Nukesor/pueue/issues/236) — подтверждение: callback ненадёжен при неправильной конфигурации pueue state.json
- [Lease Pattern: Lock With Expiration — woodruff.dev](https://woodruff.dev/lease-pattern-in-net-a-lock-with-an-expiration-date-that-saves-your-data/) — почему indefinite locks опасны, lease как альтернатива
- [Process Supervision for AI Agents — Zylos Research](https://zylos.ai/research/2026-02-20-process-supervision-health-monitoring-ai-agents) — defense-in-depth для long-running agent задач
