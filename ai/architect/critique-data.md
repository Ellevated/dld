# Data Architecture Cross-Critique

**Persona:** Martin (Data Architect)
**Phase:** 2 — Peer Review
**Date:** 2026-05-23
**Scope:** scripts/vps/ retrofit — все 7 анонимных анализов

---

## Peer Analysis Reviews

### Analysis A — Operations (Charity lens)

**Agreement:** Agree

**Reasoning from data perspective:**

A правильно идентифицирует трёхслойную проблему хранения статуса как первопричину
observability-кризиса: "Until there is a single source of truth for status, any dashboard
showing spec counts will be potentially wrong and there is no way to know which
representation is authoritative at query time." Это точная формулировка DDIA-принципа
о том, что derived data должна быть явно помечена как производная, а source of record —
однозначно определён.

M-01 (bootstrap_ops_rate) — правильный leading indicator. SLO-4 (bootstrap accuracy)
не может быть надёжно измерен пока bootstrap читает backlog.md из WT вместо HEAD —
это прямое следствие нарушения SoR.

**Missed gaps from data perspective:**

- A не ставит вопрос о retention: `callback-audit.jsonl`, `sdk_post_result_errors`,
  `callback_decisions` растут без bound. В DDIA это называется "unbounded dataset" —
  классическая причина деградации дискового пространства и производительности через
  6-12 месяцев. Конкретные числа: при 200 callbacks/day, каждая JSONL строка ~400 bytes,
  за год = ~28 MB. Не катастрофа, но отсутствие retention policy — это отсутствие policy.
- A не рассматривает консистентность между audit JSONL (на файловой системе) и
  task_log (в SQLite). Это два хранилища одного факта "что произошло с задачей" —
  classic split-brain по DDIA Ch.1 "Reliable, Scalable, and Maintainable".

---

### Analysis B — Evolutionary Architecture (Neal lens)

**Agreement:** Agree

**Reasoning from data perspective:**

B строит drift map через призму fitness functions — это эволюционная архитектура. Но
самый важный data-вывод B звучит точно по DDIA: три представления статуса без sync
contract = "status exists in 3 stores without explicit contract — Lifecycle aggregate
root does not exist as explicit code construct."

FF-03 (sole writer check) — это data invariant, выраженный как code-level test.
Именно так должны работать invariants: не в ADR-документах, а в CI.

Критически важно: B правильно идентифицирует `_SPEC_ID_RE` fork между callback.py и
orchestrator.py как data schema divergence. GROWTH-NNN spec IDs, которые orchestrator
знает, callback не знает — это нарушение ubiquitous language на уровне данных.

**Missed gaps from data perspective:**

- B не анализирует, что `transitions: []` в 175 из 177 lifecycle YAML файлов (audit
  finding #14) означает потерю истории состояний. По DDIA это event sourcing fail:
  если transition history не записывается, мы не можем ответить на вопрос "когда и
  почему spec перешёл из in_progress в done?" Audit trail без истории — это не audit trail.
- FF-06 (incident coverage bank) правильная идея, но B не указывает что regression tests
  должны использовать real git repos, не фиктивные данные — из-за ADR-013.

---

### Analysis C — Domain Architecture (Eric lens)

**Agreement:** Agree

**Reasoning from data perspective:**

C делает самый глубокий data-анализ среди всех peers с DDD-lens. Три key insight с
точки зрения данных:

1. "The aggregate root for spec lifecycle does not exist in this codebase" — это точно
   по DDIA Ch.2 про data models. Aggregate root — это не просто паттерн OOP, это
   constraint: все mutations проходят через один объект, который enforces invariants.
   Сейчас `started_at` always null (найдено в lifecycle.py:155-158) — это доказательство
   отсутствия aggregate invariants.

2. Таблица "Aggregate smeared across four storage media" — это эквивалент DDIA "data
   systems are different, and they don't all give the same guarantees." Конкретно:
   lifecycle YAML (CAS atomic), callback_decisions (SQLite ACID), git log (immutable
   append-only), task_log (SQLite ACID), backlog.md WT (none) — у каждого разная
   consistency guarantee, но нет кода который их синхронизирует.

3. Bootstrap как "polling backlog.md вместо SpecCreated event" — это anti-pattern из
   DDIA Ch.11 "Stream Processing": polling вместо event-driven integration.

**Missed gaps from data perspective:**

- C не рассматривает, как предложенная domain event architecture влияет на forward
  compatibility. `SpecCreated` event должен иметь versioning strategy: что происходит
  если Spark добавит новые поля в spec, а Execution Context работает с старой схемой?
  По DDIA это schema evolution problem.
- C предлагает Author как value object (не строку), но не решает backward compatibility
  с 177 существующими YAML файлами где `updated_by` = строка. Migration strategy
  не описана.

---

### Analysis D — LLM Architect (Erik lens)

**Agreement:** Partially Agree

**Reasoning from data perspective:**

D правильно идентифицирует `_emit_audit` с 12 позиционными аргументами как reliability
problem. С data perspective это важнее, чем кажется: при transposition двух `int`
аргументов (code_loc, test_loc, allowed_count — все один тип) audit log будет
содержать структурно корректные, но семантически неверные данные. Это тихое data
corruption — классический DDIA enemy.

`GateResult` dataclass как structured output — это правильный шаг к schema на data
boundaries между компонентами.

**Partial disagreement:**

D предлагает "signal completion" API где агент явно сигнализирует о завершении с
указанием commit SHA. Это меняет систему записи (SoR) для "work completion":
вместо git log как авторитетного источника, источником становится сигнал от агента.
С data perspective это downgrade: git log cryptographically verifiable, agent signal —
honor system. Если агент галлюцинирует commit SHA, система примет невалидное завершение.
Текущий подход (gate читает git log как SoR) — правильнее.

**Missed gaps from data perspective:**

- D не рассматривает что `vps-orch.py status SPEC-ID` должен читать из единого SoR.
  Если SoR — lifecycle YAML, этот инструмент должен быть read-only wrapper над ним.
  Если SoR мигрирует в SQLite (как предлагает E), инструмент должен читать из SQLite.
  Нет рассуждения о том, как CLI tools изолированы от SoR changes.

---

### Analysis E — DX / Pragmatist (Dan lens)

**Agreement:** Partially Agree

**Reasoning from data perspective:**

E делает самое радикальное data-предложение: убрать lifecycle.py (602 LOC git-plumbing)
и переместить status SoR в SQLite. Innovation token accounting — полезный framework.

Ключевое data-наблюдение E попадает точно: "Three-layer → zero-layer: status lives in
ONE place. Everything else is a render or a human annotation." Это DDIA принцип single
SoR.

SQLite WAL mode для concurrent writes между callback и orchestrator — правильный выбор
для single-machine setup. PRAGMA user_version как schema versioning — действительно
boringly correct.

**Partial disagreement на критически важном вопросе:**

E утверждает: "The multi-machine convergence requirement is theoretical. If it ever
becomes real, SQLite WAL + periodic backup is simpler." Это неправильная оценка риска.

Git как SoR даёт бесплатный audit trail с криптографической верификацией и историей
изменений. SQLite с spec_transitions таблицей может имитировать это, но:
1. SQLite transitions — mutable (можно DELETE). Git commits — immutable.
2. Multi-machine sync через git pull — один команда. SQLite replikation — отдельная
   инфраструктура.
3. Существующие 177 YAML файлов + их git history — это данные, которые стоит сохранить.

Более взвешенный подход: SQLite как primary operational SoR (fast writes, good
concurrency), git как audit log (immutable history, multi-machine sync). Dual-write
в переходный период.

**Missed gaps:**

- E предлагает `git log origin/develop --grep SPEC-ID` как единственный gate rule —
  5 строк. Но --grep ищет по всему commit message включая body. Если в теле коммита
  упомянут FTR-123 как ссылка ("See FTR-123 for context"), это false positive. По
  DDIA это называется "false match" из-за insufficient schema validation. Нужен хотя бы
  `--grep "^feat.*FTR-123\|FTR-123"` с anchored regex.
- Нет описания migration plan для существующих 177 lifecycle YAML файлов в SQLite.
  Expand-contract pattern требует: сначала написать в оба, потом читать из нового,
  потом убрать старое. E предлагает "one-shot migration script" что создаёт risk
  window.

---

### Analysis G — Devil's Advocate (Fred/Brooks lens)

**Agreement:** Partially Agree

**Reasoning from data perspective:**

G делает самое провокационное предложение: gate как отдельный daemon, polling origin/develop
каждые 60 секунд. С data perspective это интересный сдвиг consistency model.

Текущая система: **strong consistency per-callback** (gate вызывается синхронно
при каждом pueue completion, статус устанавливается немедленно).

G предлагает: **eventual consistency** с 60-секундной latency. Spec завершается, callback
отпускает slot и диспатчит QA — но статус ещё не "done". Gate daemon обнаружит это
через ≤60 секунд.

Вопрос: приемлема ли eventual consistency здесь? G аргументирует что да, указывая что
текущая система имеет 5-hour detection latency на bootstrap-flip — что 60 секунд не
деградация. Это верное наблюдение об AS-IS, но не о TO-BE: если callback-gate будет
правильно работать, current latency = 0 (синхронный вызов).

**Missed gaps:**

- G не рассматривает что eventual consistency между gate daemon и QA dispatch создаёт
  temporal inconsistency: QA может запуститься до того как статус обновился до "done".
  Это означает QA работает над spec которая с точки зрения lifecycle всё ещё "in_progress".
  Этот state machine gap требует явного решения.
- G предлагает удалить `updated_by` из YAML и заменить на `git log` для identity.
  С data perspective это downgrade readability: запросить текущий writer теперь требует
  subprocess call, а не чтение поля. DDIA рекомендует денормализацию для read-heavy
  access patterns. Если `updated_by` читается чаще чем пишется — держать его в YAML
  правильно, даже если значение проверяемо через git log.

---

### Analysis H — Security (Bruce lens)

**Agreement:** Partially Agree

**Reasoning from data perspective:**

H рассматривает data integrity через security lens и находит несколько critical data
integrity issues:

1. `callback-audit.jsonl` — tamper-without-detection. Это SoR для anti-recency decisions
   в scan_queued. Если файл может быть модифицирован без обнаружения, то data на основе
   которых принимаются dispatch decisions — ненадёжны. HMAC per line — правильное решение.

2. "orchestrator.py reads backlog.md from dirty WT — active exploit path": это
   security framing того же data integrity bug, который другие personas описывали как
   оперативный риск. H правильно эскалирует это до P0.

3. Multi-project JSONL sharing: "A high-volume project can push old entries beyond the
   200-line scan window." Это data retention bug с security implications. Scan window
   должен быть per-project, не global.

**Partial disagreement:**

H предлагает "git signed commits как identity" — GPG ключ для orchestrator service.
С data perspective это overengineering для текущего threat model (single-tenant VPS,
единственный human operator). DDIA говорит: "don't apply enterprise-level solutions to
startup-scale problems." Process token в systemd environment — достаточно.

**Missed gaps:**

- H не рассматривает data retention risk: `task_log`, `callback_decisions`,
  `sdk_post_result_errors` растут неограниченно. При security breach, большой
  forensic dataset хорош для расследования. Но unbounded growth = performance risk
  и potential disk-based DoS. Нужен explicit retention policy с архивацией.

---

## Convergence: Where Peers Agree

### Конвергенция 1: Three-store status split = root cause

Все 7 анализов явно или неявно идентифицируют трёхслойное хранение статуса как
primary data integrity problem:
- A: "three-store status split means any dashboard will be potentially wrong"
- B: "status exists in 3 stores without sync contract"
- C: "aggregate root for spec lifecycle does not exist"
- E: "three-layer → collapse to one"
- G: "render_backlog became a source, not a view"
- H: "three separate attack surfaces for status manipulation"

**Данная конвергенция — сигнал максимальной уверенности: это Root Issue №1.**

### Конвергенция 2: bootstrap_new_specs читает WT, не HEAD

A, B, C, D, E, G, H — все называют это critical bug. D называет это "unstructured text
parsing as authority source." H называет это "active exploit path." E называет это
"today's bug." Это unanimous verdict.

### Конвергенция 3: callback.py decomposition необходима

Все анализы, включая pragmatist E и skeptic G, приходят к выводу что 1374 LOC
god module должен быть декомпозирован. Divergence только в том, как именно.

### Конвергенция 4: scripts/vps/tests/ не в CI — P0 fix

B, D, E — все называют это критической проблемой. Одна строка в pyproject.toml.

---

## Divergence: Contradictions Between Peers

### Дивергенция 1: SQLite vs Git как SoR для lifecycle status

**E (pragmatist):** SQLite as primary SoR. Kill lifecycle.py, 602 LOC → 5 SQL functions.
"The multi-machine requirement is theoretical."

**G (skeptic):** "ADR-023 should be split: ADR-023a (git yaml as SoT) KEEP; ADR-023b
(private GIT_INDEX_FILE CAS) REPLACE with simpler git add + git commit."

**H (security):** Git CAS approach "is sound for single-machine use."

**Моя оценка:** Настоящая дивергенция — не между git и SQLite, а между тем, кто является
write authority и кто — audit trail. Оптимальная архитектура: SQLite как operational SoR
(fast, concurrent, queryable), git как audit log (immutable, multi-machine). Это не
противоречие, это разделение ответственностей по DDIA Ch.12 "The Future of Data Systems".

### Дивергенция 2: gate — sync callback vs polling daemon

**G (skeptic):** Separate gate daemon, 60-second polling. Clean separation.
"A pure function of git state. No pueue dependency. Independently testable."

**E (pragmatist):** One-rule gate в callback: `git log origin/develop --grep SPEC-ID`.
Keep callback pattern, simplify the rule.

**C (domain):** Gate как Work Verification Context — pure function, no side effects,
called synchronously.

Дивергенция реальная. Polling daemon устраняет coupling но вводит eventual consistency.
Это CAP theorem tradeoff: consistency vs partition tolerance для single-machine setup.

### Дивергенция 3: spec_operator.py — YAGNI vs needed

**E (pragmatist):** "YAGNI — no real user, remove."
**G (skeptic):** "Already dead. Do not resurrect."
**C (domain):** Violation of published language — needs refactoring, not deletion.
**H (security):** force-done bypasses ALL gates — critical security issue.

---

## Ranking: Top 3 Peer Recommendations by Data Leverage

### Rank 1: Analysis E — "Replace lifecycle.py with SQLite"

**Leverage:** Eliminates entire bug class (stale-index race, CAS failure, timeout risk),
reduces 602 LOC к 5 SQL functions, makes bootstrap_new_specs тривиальным (`SELECT`
вместо backlog.md regex parsing). Прямое решение для трёх из пяти сегодняшних инцидентов.

**Data integrity impact:** Максимальный. SQLite WAL transactions = serializable writes
с нативным timeout. Нет git plumbing subprocess calls. Нет checkout-index stale index.

### Rank 2: Analysis C — "Explicit SpecLifecycle aggregate root"

**Leverage:** Enforcement of invariants at the data model level, not в comment/ADR.
`started_at` always null — невозможно если aggregate enforces "set on in_progress transition."
`transitions: []` в 175 yaml — невозможно если aggregate records transitions.

**Data integrity impact:** Высокий. Переводит бизнес-правила из ADR documents в
executable code. Согласно DDIA — invariants должны быть enforced by the data model,
не by convention.

### Rank 3: Analysis B — "ADR Kill Section + FF-03 sole writer test"

**Leverage:** FF-03 (sole writer check) предотвращает будущие нарушения ADR-023 на
уровне CI. ADR Kill Section + `test_adr_kills_complete.py` решает zombie validator
problem системно, а не point-by-point.

**Data integrity impact:** Средний-высокий. Не решает текущие bugs, но предотвращает
следующий класс bugs от zombie enforcement.

---

## Data-Specific: Do Peer Proposals Create New SoR Ambiguity?

### E: SQLite migration — risk window

E предлагает "one-shot migration script" от lifecycle YAML к SQLite. Это creates a
**migration race window**: если migration script запускается пока orchestrator активен,
возможна ситуация где:
- lifecycle YAML уже удалён
- SQLite запись ещё не создана
- Callback читает lifecycle YAML → получает FileNotFoundError → spec stays blocked

**Recommendation:** Expand-contract pattern (DDIA Ch.4 "Encoding and Evolution"):
1. EXPAND: добавить SQLite table, начать dual-write (YAML + SQLite)
2. MIGRATE: backfill всех существующих YAML в SQLite
3. SWITCH: сменить reads на SQLite
4. CONTRACT: убрать YAML writes, затем lifecycle.py

Это zero-downtime migration, не one-shot script.

### G: Gate daemon — eventual consistency breaks state machine

G предлагает gate daemon polling каждые 60 секунд. Это вводит window где:
- spec.lifecycle.status = "in_progress"
- git log origin/develop содержит commit с этим spec_id
- QA dispatch произошёл (callback отработал)
- gate daemon ещё не обновил lifecycle status

Если QA daemon проверяет lifecycle status перед диспатчем, он увидит "in_progress"
и не запустится. Это eventual consistency проблема на state machine boundaries.

**Fix:** QA dispatch должен тригерить немедленный gate check, не ждать следующего
poll cycle. Или: callback остаётся responsible для gate check, polling daemon — только
для "cleanup" missed transitions.

### D: Agent signal_completion API — degrades SoR quality

D предлагает explicit agent signal с commit_sha. Если принять это предложение, SoR
для "work completion" становится двойным: git log (authoritative) + agent signal
(potentially inconsistent). При расхождении — что побеждает? Нет ответа в D.

**Reject this specific proposal.** Git log как SoR for "what's on develop" — не меняем.

---

## Your Addition: One Thing Peers Missed from DDIA Perspective

### Missing: Schema Evolution и Forward Compatibility для lifecycle YAML

Ни один из семи пирс-анализов не рассматривает schema evolution strategy для lifecycle
YAML (или предлагаемой SQLite схемы). Это критический gap.

**Текущее состояние:**

Lifecycle YAML schema определена implicit в lifecycle.py (`LifecycleData` TypedDict).
Нет version field. 177 существующих YAML файлов созданы в разное время. Audit report
находит:
- `started_at` always null (поле существует, но никогда не заполняется)
- `allowed_files_hash` always null (поле существует, никогда не заполняется)
- `transitions: []` в 175/177 файлов (поле существует, не заполняется)

Это признаки **backward-incompatible schema evolution**: поля добавлялись к schema
не обновляя существующие данные. По DDIA Ch.4 "Encoding and Evolution" — это нарушение
forward compatibility: если новый код читает старый YAML и обнаруживает `started_at: null`,
он не знает: "поле было null намеренно" или "этот файл создан старым кодом который не
писал started_at"?

**Что нужно:**

```yaml
# Every lifecycle YAML should have:
schema_version: 2
spec_id: FTR-1053
status: done
started_at: "2026-05-20T10:00:00Z"  # null only if schema_version < 2
finished_at: "2026-05-23T11:00:00Z"
transitions:
  - from: queued
    to: in_progress
    at: "2026-05-20T10:00:00Z"
    by: orchestrator
  - from: in_progress
    to: done
    at: "2026-05-23T11:00:00Z"
    by: callback
```

Readers должны знать: `if schema_version < 2: started_at may be null due to migration gap`.

**Migration strategy (DDIA expand-contract):**

1. **Expand:** Добавить `schema_version: 1` ко всем существующим YAML (one-shot script)
2. **Migrate:** При каждом write через lifecycle.py — upgrade к schema_version: 2
3. **Contract:** После того как все файлы достигли schema_version: 2 — убрать legacy
   null handling из readers

Это стандартный DDIA pattern для schema evolution в document stores. Ни один peer не
предложил его, несмотря на то что все идентифицировали проблему с null полями.

**Если E выбран (SQLite migration):** PRAGMA user_version — правильный механизм E,
но нужна explicit migration history table:

```sql
CREATE TABLE schema_migrations (
    version      INTEGER PRIMARY KEY,
    applied_at   TEXT NOT NULL,
    description  TEXT NOT NULL
);
```

Это позволяет отвечать на вопрос "какие данные были мигрированы, а какие нет" —
критически важно при incremental migration стратегии.

---

## Revised Position

**Revised Verdict:** Changed from Phase 1

**Change Reason:**

E's innovation token analysis убеждает: git-as-DB "bought" us the stale-index race
(Root 4 today), checkout-index bug, _push_best_effort silent failure — это не
implementation bugs, это architectural consequences. G's proposal о "ARCH-186 was right
in direction, wrong in implementation" — правильная формулировка, но недостаточная.
Direction тоже можно улучшить.

B's ADR Kill Section — это данные об архитектурных решениях как first-class entities
в системе. Это мне нравится больше чем я ожидал.

**Final Data Recommendation:**

Трёхступенчатая стратегия по DDIA:

**Ступень 1 — немедленно (0 риска, максимальный ROI):**
- bootstrap_new_specs читает HEAD, не WT (1 строка)
- `_push_best_effort`: DEBUG → WARNING (1 строка)
- GROWTH в `_SPEC_ID_RE` callback.py (1 строка)
- pyproject.toml testpaths (1 строка)
- Добавить `schema_version: 1` ко всем lifecycle YAMLs (one-shot script, ~5 LOC)

**Ступень 2 — SQLite как operational SoR (medium risk, expand-contract):**
- Добавить `spec_lifecycle` + `spec_transitions` tables в db.py (E's schema)
- Dual-write period: пишем в оба, читаем из YAML
- Backfill существующих 177 YAML в SQLite
- Переключить reads на SQLite
- YAML → read-only audit archive, не удалять

**Ступень 3 — SpecLifecycle aggregate (C's proposal, low risk):**
- Explicit aggregate root с enforced invariants
- `started_at` set on `in_progress` transition — обязательный инвариант
- `transitions` записываются при каждом изменении статуса
- Sole writer enforced через FF-03 + CI

Git остаётся как immutable audit log (git history lifecycle YAML commits).
SQLite — operational database. Это DDIA Ch.12 "derived data" pattern:
primary source (SQLite), secondary derived store (git archive).

Aggregate root в C — правильная конечная точка. SQLite в E — правильный
implementation vehicle. Schema versioning — это то что позволит эволюции
схемы без останова системы.

---

## References

- Martin Kleppmann — DDIA Ch.4 (Encoding and Evolution), Ch.11 (Stream Processing),
  Ch.12 (The Future of Data Systems)
- Analysis A: `/home/dld/projects/dld/ai/architect/anonymous/A.md`
- Analysis B: `/home/dld/projects/dld/ai/architect/anonymous/B.md`
- Analysis C: `/home/dld/projects/dld/ai/architect/anonymous/C.md`
- Analysis D: `/home/dld/projects/dld/ai/architect/anonymous/D.md`
- Analysis E: `/home/dld/projects/dld/ai/architect/anonymous/E.md`
- Analysis G: `/home/dld/projects/dld/ai/architect/anonymous/G.md`
- Analysis H: `/home/dld/projects/dld/ai/architect/anonymous/H.md`
- Deep Audit Report: `/home/dld/projects/dld/ai/audit/deep-audit-report.md`
- lifecycle.py: `/home/dld/projects/dld/scripts/vps/lifecycle.py`
- callback.py: `/home/dld/projects/dld/scripts/vps/callback.py`
- orchestrator.py: `/home/dld/projects/dld/scripts/vps/orchestrator.py`
