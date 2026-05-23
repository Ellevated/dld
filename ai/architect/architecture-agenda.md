# Architecture Retrofit — Agenda

**Date:** 2026-05-23
**Mode:** Retrofit (brownfield)
**Trigger:** Incident — 15 fake-done lifecycle flips + 4 связанных бага одной волны → 5-я итерация фиксов callback/lifecycle/orchestrator контура за месяц.
**Primary input:** `ai/audit/deep-audit-report.md` (85 findings от 6 персон)
**Scope:** `scripts/vps/` контур + связанные hooks, тесты, спеки workflow
**Out of scope:** managed-проекты бизнес-логика (awardybot/wb/dowry domain code), Claude SDK internals, pueue/git CLI.
**Founder constraint:** «надоели заплатки, хочу архитектурный пересмотр» — НЕ очередной 8-rule patch, а структурная декомпозиция.

---

## AS-IS Summary (из Deep Audit)

### Architecture reality

- `callback.py` — **1374 LOC (3.4× лимит)**, 36 функций, 7+ ответственностей (gate, writer, parser, audit, circuit-breaker, dispatcher, backlog render).
- `lifecycle.py` — 602 LOC (1.5× лимит), две почти идентичные 80-LOC функции atomic-write (для yaml + для произвольного файла).
- `orchestrator.py` — 667 LOC (1.7× лимит), три независимых функции pueue-query.
- `db.py` — 531 LOC, 23 функции в плоском файле, нет schema versioning.
- 19 bare `except Exception` в callback.py (ADR-004 разрешает только в hooks/).
- `_load_env` / `_setup_logging` / `_pueue_add` / `_SPEC_ID_RE` дублированы в 2-3 модулях.
- Не существует `common.py` или shared util layer.

### Data reality

**3 хранилища "status" без consistency contract:**
1. `ai/lifecycle/{spec_id}.yaml` (HEAD) — декларированный SoT (ADR-023)
2. `ai/backlog.md` (WT) — должен быть render, по факту читается `bootstrap_new_specs` как authoritative
3. spec body + zombie `DLD-CALLBACK-MARKER` в 23 файлах — фоссилы pre-ADR-186

**Структурные дыры в lifecycle yaml:**
- `started_at` всегда null (verify_status_sync делает queued→done минуя in_progress)
- `allowed_files_hash` всегда null (мёртвое поле, нет writers)
- `priority: p3` живёт в 4 файлах, render_backlog не знает → молча исчезают
- `transitions: []` у 175 из 177 yaml (migration не записала историю)
- `blocked_reason` free-text, 6+ форматов от 7+ writers

**SQLite:**
- Нет `PRAGMA user_version` / schema migrations table
- `_MIGRATIONS_APPLIED` — process-global флаг, ресет на рестарт
- Нет retention на task_log, callback_decisions, sdk_post_result_errors
- Нет индексов на hot queries (task_log.pueue_id, night_findings.(project_id,status))
- `cost_usd REAL` (float) в sdk_post_result_errors — нарушает ADR-001

### Tech debt hotspots (Coroner)

- **`_atomic_write` WT-sync race** — `checkout-index --force` читает из main index, но private GIT_INDEX_FILE удалён в finally → стейл blob → 13 D файлов сегодня
- **Best-effort failure swallowing** — 3 callsite (WT-sync, push, file write) на 3 разных log level (warning/debug/warning); push на DEBUG = невидимо в INFO
- **No timeout** на 8 git plumbing вызовов в `_atomic_write` — любой может зависнуть под `_write_lock` блокируя весь callback
- **Зомби-валидаторы**: spec_lint.py валидирует DLD-CALLBACK-MARKER которые ARCH-186 удалил; pre-commit hook вызывает; `template/.claude/skills/spark/completion.md:46` требует маркеры → каждый Spark-spec будет malformed

### Integration landscape

**External touchpoints:**
- pueue CLI (5 callsites в orchestrator, 6 в callback)
- git CLI porcelain (pull, fetch, log, status) + git plumbing (8 ops в lifecycle)
- claude_agent_sdk
- openclaw/Hermes (event_writer)
- SQLite local
- /proc/meminfo (RAM gate)
- systemd

**Multi-project deployment gap:**
- DLD-репо имеет `.git-hooks/pre-commit` + `.claude/hooks/pre-commit-lifecycle-guard.mjs`
- НИ ОДИН из 3-х проверенных репо (dld/awardybot/dowry) не имеет `core.hooksPath=.git-hooks` → guard мёртв **везде**, даже в DLD
- 10 managed projects (awardybot, wb, dowry, nexus, plpilot, gipotenuza, memyselfandi, mishkinlyap, dowry-mc, dld) не имеют ни hooks, ни guard
- Нет скрипта `register-project.sh` или подобного провижионинга
- `TELEGRAM_BOT_TOKEN` коммитнут открытым текстом в `scripts/vps/.env` (git-tracked, не в `.gitignore`)

### Pattern conflicts

- **Identity contract**: ADR-023 «callback — единственный writer», по факту 6 writers (callback, orchestrator.bootstrap, orchestrator.reconcile [подписан callback — ложь], spec_operator, migrate [через `Path.write_text()` в обход CAS], pre-commit hook).
- **Commit subject convention**: cefaa55 ужесточил `_subject_implements` под canonical `feat(SPEC):` scope; awardybot/dowry пишут `feat(domain): ... (SPEC Task N)` — 460 коммитов vs 176. Gate систематически возвращает false-blocked.
- **Status namespace**: 3 представления (yaml HEAD, backlog.md WT, spec body) без контракта sync.
- **Error handling**: callback.py docstring `INVARIANT: Always exit 0` vs lifecycle.py `raise LifecycleWriteRaceError` — два философии в одном callgraph.
- **Test mocking**: ADR-013 «no mocks in integration tests», но `_is_done_on_develop` мокается в `test_callback_already_merged.py` — основной gate в реальном end-to-end не тестируется.

### Missing elements

- **`scripts/vps/tests/` (~100 тестов lifecycle/orchestrator/bootstrap) НЕ В CI** — `pyproject.toml:19 testpaths=["tests"]`, регрессионная сетка для lifecycle/orchestrator невидима
- Coverage gate только на callback.py ≥65%; lifecycle.py (602 LOC) и orchestrator.py (667 LOC) — никакого gate
- Регрессионные тесты на **5 сегодняшних багов** — 0 (или PARTIAL)
- Нет global autouse DB-isolation fixture в `tests/conftest.py` — любой новый тест без `tmp_db` пишет в prod-DB
- Нет `assert_clean_lifecycle_tree` теста на запуск orchestrator при дёрти WT
- Нет deployment механизма для managed-проектов (hooks, конвенции)
- Нет formalized ADR linking — ADR-018 → 023 → 024 нигде не размечены как «деактивирует X»
- Нет mod-level docstring для callback.py объясняющего его 7 ролей

### ADR Chain Reality

| ADR | Дата | Что декларировал | Что выжило | Что не выжило |
|---|---|---|---|---|
| ADR-018 | 2026-03 | Callback пишет markdown DLD-CALLBACK-MARKER | SUPERSEDED ADR-023 | spec_lint.py + template/completion.md всё ещё ссылаются |
| ADR-023 | 2026-05-16 | Lifecycle SoT = git per-spec YAML; callback — единственный writer; never touches WT | atomic write CAS, write_lifecycle ALLOWED_WRITERS | render-disabled NOTE без replacement; 6 writers по факту; WT sync stale-blob bug |
| ADR-024 | 2026-05-20 | claude-runner exit_code контракт + identity enforcement | exit_code logic OK; sdk_post_result_errors telemetry | identity hook не задеплоен нигде |

---

## Per-Persona Retrofit Focus

### Eric (Domain Architect) — DDD

**Key question:** Какие **bounded contexts** реально существуют в `scripts/vps/`, где границы нарушены?

**Specifics:**
- callback.py имеет 7 ответственностей — это монолит или 7 разных contexts втиснутых в один файл?
- Где **ubiquitous language** разваливается? (status vs phase vs verdict vs decision; gate vs guard vs rule vs check; writer vs author vs by vs identity)
- Должен ли «lifecycle» быть отдельным bounded context от «dispatch»? От «audit»? От «render»?
- Что такое spec_operator.py концептуально — operator UI? Admin context? Должен ли он импортировать `callback._reset_circuit_cli` (т.е. cross-context private API call) или это unbounded coupling?
- Какой aggregate root для «spec lifecycle»? Сейчас он размазан по yaml + DB + markdown + git history.
- Bootstrap vs dispatch — это одна операция или две разные модели?

**Output:** `ai/architect/research-domain.md` — bounded contexts (AS-IS) + предлагаемые границы (TO-BE) + violations с file:line.

### Martin (Data Architect) — DDIA

**Key question:** Где SoR для каждой data entity, где split brain, как починить data flow?

**Specifics:**
- «Status» имеет 3 representations — какая из них SoR? Можем ли мы убить 2 из 3 без потери функций?
- `started_at` структурно сломано — переписать lifecycle state machine так, чтобы это было невозможно
- `allowed_files_hash` мёртвое — удалить или реализовать
- Идемпотентность migrate_backlog_to_lifecycle.py — нужен либо version-aware migration, либо «одноразовый» tag в коде что блокирует повторный запуск
- DB: schema versioning через PRAGMA, миграции через flyway-подобную систему, retention для unbounded таблиц, индексы на hot queries
- `blocked_reason` — enum vs free-text trade-off
- backlog.md как render — должен либо генерироваться detereministically каждый раз (и тогда manual edits **запрещены**), либо быть SoT (и тогда yaml вторичен) — но не «оба» как сейчас
- transitions: [] для 175 yaml — теряем audit trail; восстановимо из git log lifecycle*.yaml?

**Output:** `ai/architect/research-data.md` — data architecture TO-BE + миграция schema + retention policies.

### Charity (Ops) — Honeycomb

**Key question:** Как узнать что система сломалась в prod ДО того, как накопилось 8 жертв bootstrap-flip?

**Specifics:**
- Сегодня инцидент произошёл в 11:17 утра — был замечен ~16:00. 5 часов прод-trouble без алерта. Что должно было сигналить?
- `_push_best_effort` на DEBUG → multi-machine convergence ADR-023 ломается невидимо. Какие метрики/SLO?
- Circuit breaker есть, но это binary signal. Нужны **leading indicators** (демоут rate, gate-rejection rate, WT-stale frequency).
- `bootstrap_new_specs` пишет 13 yaml за 30 секунд — это event который должен был отправить alert «mass bootstrap detected». Threshold?
- Audit log JSONL есть, но никто его не читает в реальном времени. Нужен dashboard?
- 8 git plumbing вызовов без timeout — hang detection. Health check endpoint?
- `assert_clean_lifecycle_tree` упадёт на старте, но это уже incident. Можно ли **prevent** dirty WT?

**Output:** `ai/architect/research-ops.md` — observability TO-BE (metrics, logs, alerts, dashboards, SLOs).

### Bruce (Security) — Threat Modeling

**Key question:** Какова реальная attack surface, что **уже** скомпрометировано?

**Specifics:**
- `TELEGRAM_BOT_TOKEN` в git history открытым текстом — токен **публичный**, надо ротировать (уже incident, не потенциальный)
- `pre-commit-lifecycle-guard` не работает нигде — identity enforcement декларативный, не операционный. Любой агент в любом проекте может писать lifecycle yaml в обход.
- `spec_operator.py` принимает `by="operator"` без аутентификации — кто угодно с filesystem access может стать «operator»
- callback пишет audit JSONL в `SCRIPT_DIR/callback-audit.jsonl` — этот файл влияет на orchestrator decisions (через `scan_queued` anti-recency check). Tampering vector?
- pueue daemon — у него есть аутентификация? Любой пользователь на VPS может класть задачи?
- DB_PATH может указывать в чужое место (то самое отравление prod-DB сегодня) — это **integrity attack** на decision-making system, не просто devex
- Threat model для multi-project orchestrator: проект A может ли через спецификацию повлиять на проект B? (Rule 8 в cefaa55 пытается это закрыть, но это runtime gate, не структурная изоляция)

**Output:** `ai/architect/research-security.md` — threat model + STRIDE по контуру + список already-compromised + mitigation TO-BE.

### Neal (Evolutionary) — Fitness Functions

**Key question:** Где drift УЖЕ произошёл, что откатывать vs принимать, какие fitness functions защитили бы каждое решение?

**Specifics:**
- 5 итераций фиксов в одном контуре за месяц — это **structural drift**. Fitness function на «LOC per file»? «Functions per module»? «Cycle of regression rate»?
- ADR-018 → 023 → 024 — каждая ADR частично деактивирует предыдущую, но без формального tracking. Нужна ли ADR-deprecation policy?
- `spec_lint.py` валидирует мёртвый формат — кто должен был это поймать? Fitness function «no zombie validators»?
- callback.py растёт линейно с каждой инцидентом — fitness function «module growth rate per quarter»?
- Какие изменения **acceptable**, какие — drift? («Добавить try/except в callback» vs «вынести gate в отдельный модуль»)
- Architectural fitness function от Ford: how to автоматически проверять что callback.py НЕ владеет 7 responsibilities?
- Roll back vs accept: spec_lint.py (rollback), backlog.md auto-render (decide), DLD-CALLBACK-MARKER (rollback)
- Каждый предыдущий «фикс контура» открывал следующую проблему — есть закономерность, можно ли её формализовать как anti-pattern?

**Output:** `ai/architect/research-evolutionary.md` — drift map + fitness functions (CODE-ready, не prose) + rollback/accept decisions.

### Dan (DX / Pragmatist) — Boring Tech

**Key question:** Стоит ли вообще держать текущий стек, где dev pain?

**Specifics:**
- Innovation tokens used: SQLite + git as DB (ADR-023) + pueue + custom CAS via plumbing + private GIT_INDEX_FILE + claude_agent_sdk + circuit-breaker + 8-rule gate + multi-project orchestration. **Сколько здесь экзотики?**
- "Git as DB" (ADR-023) — это интересный paradigma, но он подарил bug №3 (stale main index race). Pragmatic question: было бы проще оставить SQLite как SoR для status?
- Custom pueue callback contract — что если просто pueue+ Python script + cron? Что мы теряем?
- spec_operator.py — нужен ли он вообще, если **операторов** в системе нет (Claude SDK не нуждается в operator UI; человек делает через git напрямую)?
- Three-layer status (yaml + backlog + spec body) — можем ли свести к одному?
- Custom 8-rule gate — может ли gate быть просто «есть merge commit на develop с этим SPEC-ID»? Без 8 rules?
- Boring alternative для каждого: existing tools (git hooks via pre-commit framework, alembic for SQL migrations, prometheus_client для observability)
- pre-commit framework vs кастомные hooks — boring choice
- Каждое решение в этом контуре было «innovative» — нужно ли это для VPS orchestrator, который реально просто dispatcher?

**Output:** `ai/architect/research-dx.md` — innovation tokens audit + boring alternatives + recommended stack (keep/swap/remove).

### Erik (LLM Architect) — Agent Patterns

**Key question:** Могут ли агенты работать с этим кодом, что им мешает?

**Specifics:**
- callback.py 1374 LOC — это влезает в context window, но **может ли coder-агент понять 7 ответственностей** не прочитав весь файл?
- `verify_status_sync` 202 LOC — фактически один tool с 5 rules. Должен ли gate быть отдельным tool с **structured output**?
- 19 bare `except Exception` — агент не может различить «expected fail» от «bug». Нужны typed errors.
- `_subject_implements` — это **классификатор**. Должен ли он быть structured-output prompt-based, а не regex-based? (текущий regex упускает 460/636 коммитов в awardybot — accuracy ~28%)
- bootstrap_new_specs читает markdown — это парсинг неструктурированного текста. Должен быть **schema-validated input**, не regex.
- Agent retrieval: если coder-агент работает над callback.py, что в контексте? Сейчас — весь файл. Что должно быть — interface + relevant slice?
- Context budget: spec для callback включает 7 ADR + 11 TECH + 3 ARCH + 2 BUG references. Total context overhead ~3000 LOC только для прочтения. Можно ли это сжать?
- `_emit_audit` 12 args — agent unfriendly. Structured payload (dict/dataclass) лучше.
- Tools для агентов: должен ли быть CLI `vps-orch status SPEC-ID` который агент вызывает вместо чтения SQLite напрямую?

**Output:** `ai/architect/research-llm.md` — agent ergonomics audit + recommended tool design.

### Fred (Devil's Advocate) — Conceptual Integrity

**Key question:** Что если все наши предположения о коде неправильны? Что если переписать с нуля?

**Specifics:**
- Conceptual integrity (Brooks): **кто solely responsible** за integrity callback-контура? Сейчас — никто. Каждое incident-driven fix добавляет правило без global review.
- 8-rule design — это «сложность от добавления правил». Что если есть **0-rule design**?
- Rewrite hypothesis: «оркестратор просто запускает Claude SDK задачи, callback просто помечает результат, gate — это GitHub Actions, не custom». Что мы потеряем при rewrite?
- Если bootstrap_new_specs **удалить** — что сломается? (спека добавляется через Spark, который сам пишет lifecycle yaml — нужен ли second writer?)
- Если callback **не делает gate**, а просто записывает «autopilot finished, exit_code=X» — gate может быть **отдельный demon** который читает события и решает. Coupling меньше.
- Если render_backlog **удалить** — backlog.md просто `git log --grep=lifecycle()` + jq? Или вообще не нужен (lifecycle yaml сам по себе read-able)?
- Если spec_operator **удалить** — кто-нибудь когда-нибудь его использовал в реальном workflow? Может это yagni?
- Identity enforcement через `by=` — это **honor system** (любой может написать `by="callback"`). Реальная identity — это git author email + signed commits. Может, переписать identity через git трейлеры?
- Circuit-breaker — нужен ли он, если bootstrap не существует и gate надёжен?
- **Самое радикальное:** что если callback вообще удалить, и заменить на git post-merge hook на origin/develop, который автоматически переводит спеки в done? (это требует push к origin происходит атомарно с work)
- contradicting assumption: «pueue + callback paradigm» — это правильный паттерн или legacy от того, что когда-то была bash-based orchestration?

**Output:** `ai/architect/research-devil.md` — rewrite-from-scratch alternative + kill questions per существующая ADR + Evaporating Cloud для главного конфликта (incremental fix vs full rewrite).

---

## Process

- **Phase 2 (Research):** 8 параллельных background-агентов, каждый пишет `research-{role}.md`. Min 5 queries, 2 deep research per persona. Quote-before-claim mandatory.
- **Phase 3 (Cross-critique):** 8 параллельных, каждый видит **анонимные** 7 чужих research (метки A-G), отвечает agree/disagree + gaps + ranking.
- **Phase 4 (Synthesis):** opus synthesizer строит 2-3 архитектурных альтернатив. Каждая включает delta from AS-IS + migration steps + risks.
- **Phase 5 (Presentation):** Founder выбирает (НЕТ auto-decide в retrofit).
- **Phase 6 (Iterate):** R2 (минимум 2 раунда, максимум 3).
- **Phase 7 (Write):** 6 файлов system-blueprint + migration-path.md.
- **Phase 8 (Reflect):** upstream signals для Board.

## Anti-patterns to avoid in this session

- ❌ Очередной «8-rule», «10-rule» redesign. Каждое новое правило — новый failure mode.
- ❌ Patch на конкретные 5 сегодняшних багов без структурного пересмотра.
- ❌ Сохранять «3 представления статуса» «потому что migration рисково» — это и есть корень.
- ❌ Trust ADR-018→023→024 цепочки как разумный design — это reactive layers, не intentional architecture.
- ❌ Считать что pre-commit hook «работает» — он не работает нигде.

## What success looks like (для R1 minimum)

- Чёткое разделение bounded contexts (3-5 модулей вместо 1 god-module)
- Single Source of Record для status (один из трёх, не «синхронизация трёх»)
- Identity enforcement, который реально работает (либо через git signed commits, либо удалить как фикцию)
- bootstrap_new_specs либо удалён, либо unified с verify_status_sync через общий gate
- Test architecture: ВСЕ тесты в CI, autouse DB isolation, регрессионный bank
- Multi-project deployment: один скрипт регистрирует проект, hooks едут с ним
- Migration path: waves с зависимостями, каждый item — одна Spark spec
- Fitness functions, защищающие от повторения 5-итераций паттерна
