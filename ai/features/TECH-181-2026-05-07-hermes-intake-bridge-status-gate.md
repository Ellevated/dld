# TECH-181 — Hermes intake bridge: status gate before Spark

<!-- DLD-CALLBACK-MARKER-START -->
**Status:** done
**Priority:** P1
**Risk:** R1
**Type:** TECH
**Created:** 2026-05-07
**Source:** Hermes Telegram intake (`ai/inbox/20260507-hermes-intake-bridge-status-gate.md`)

## Allowed Files
<!-- callback-allowlist v1 -->
- `scripts/vps/orchestrator.py`
- `scripts/vps/tests/test_orchestrator.py`
- `~/.claude/projects/-root/memory/dld-orchestrator.md`
- `~/.claude/projects/-root/memory/orchestrator-runbook.md`
- `.claude/rules/architecture.md`
- `ai/inbox/README.md`
- `ai/backlog.md`
- `ai/features/TECH-181-2026-05-07-hermes-intake-bridge-status-gate.md`
<!-- DLD-CALLBACK-MARKER-END -->

---

## Business rationale

Hermes заменил OpenClaw как conversational supervisor / intake-слой между Олегом и DLD-пайплайном. Сейчас orchestrator `scan_inbox()` диспатчит **любой** `Status: new` файл прямо в Spark — Spark вынужден угадывать бизнес-намерение из сырой мысли в Telegram. Это ломает разделение ответственности:

- **Hermes** — бизнес-уровень: уточняет требования у Олега, закрывает шум, формирует business-complete brief.
- **Spark** — технический уровень: impact tree, allowed files, тесты, DLD spec format.

Без status-gate Spark тратит автопилотные слоты на noisy/stale items и сам изобретает product strategy (нарушает out-of-scope из intake-доки). Решение — формальный контракт статусов inbox и hard gate в orchestrator.

## Target flow

1. Идея/артефакт появляется в источнике (`ai/inbox/`, QA report, reflect findings, pending event, Telegram-сообщение Олега).
2. Файл создаётся со `Status: draft` (или legacy `new`, см. backcompat).
3. Hermes сканирует draft'ы, приносит Олегу только то, что заслуживает спеки. Шум помечает `stale`/`rejected`.
4. Если бизнес-контекст неполный — Hermes ставит `clarifying`, задаёт вопрос Олегу в Telegram.
5. Когда intake business-complete — Hermes пишет «вопрос понятен, отдал Spark» и переводит файл в `queued`.
6. Orchestrator `scan_inbox()` подхватывает **только** `queued` → диспатчит Spark → переводит в `processing`.
7. По завершении Spark → `done` (через перенос в `inbox/done/`, как сейчас).

## Status contract

| Status | Кто пишет | Eligible for Spark dispatch? |
|--------|-----------|-------------------------------|
| `draft` | author / source-bridge | ❌ |
| `clarifying` | Hermes | ❌ |
| `stale` | Hermes | ❌ |
| `rejected` | Hermes | ❌ |
| `queued` | **Hermes only** | ✅ |
| `processing` | orchestrator (`scan_inbox`) | n/a (in-flight) |
| `done` | orchestrator (после Spark/закрытия) | n/a |

**Hard rule:** orchestrator dispatcher matches **only** `**Status:** queued`. Любой другой статус игнорируется.

## Core technical change

### `scripts/vps/orchestrator.py::scan_inbox`

- Заменить regex `_inbox_new_re = re.compile(r"\*\*Status:\*\*\s*new", ...)` →
  `_inbox_queued_re = re.compile(r"\*\*Status:\*\*\s*queued", ...)`.
- При диспатче переписывать `Status: queued` → `Status: processing` (как сейчас с `new` → `processing`).
- Docstring: `"Scan ai/inbox/ for Status: queued files (Hermes-promoted), dispatch each via pueue."`
- Логирование оставить как есть.

### Backcompat / migration decision

**Решение:** **clean break, no auto-migration**.

Причины:
- Inbox — short-lived очередь, не архив. На момент перехода в `ai/inbox/` обычно ≤5 активных файлов.
- Auto-rewrite `new`→`draft` рискует заглушить файлы, которые Олег уже считает business-complete.
- Hermes как оператор лучше LLM-миграции: посмотрит каждый legacy `new`-файл и осознанно поставит `draft`/`queued`/`stale`.

**Действия:**
1. На момент мерджа: Hermes (или Олег вручную в одну сессию) перебирает все `Status: new` в `ai/inbox/` и проставляет корректный статус.
2. После мерджа orchestrator перестаёт видеть `new` — это ОК, файлы не теряются, просто не диспатчатся, пока Hermes их не переведёт в `queued`.
3. Документация (`ai/inbox/README.md`, если есть; иначе создать) фиксирует новый контракт.

**Не делаем:** automatic regex rewriting `new`→`draft` в orchestrator startup hook. Слишком много false positives (template snippets, archived done/, и т.п.).

## Tests

`scripts/vps/tests/test_orchestrator.py` — добавить:

1. **`test_scan_inbox_dispatches_queued`** — файл с `**Status:** queued` диспатчится, переименовывается в `inbox/done/`, статус в файле становится `processing`. (mock `_pueue_add`).
2. **`test_scan_inbox_ignores_draft`** — файл с `**Status:** draft` НЕ диспатчится, остаётся в `ai/inbox/` без изменений.
3. **`test_scan_inbox_ignores_clarifying_stale_rejected`** — параметризованно для `clarifying`, `stale`, `rejected` — все игнорируются.
4. **`test_scan_inbox_ignores_legacy_new`** — файл со старым `**Status:** new` НЕ диспатчится (regression guard на clean break).
5. **`test_scan_inbox_no_status_field`** — файл без `Status:` поля игнорируется (защита от случайных .md).

## Acceptance criteria

- [ ] `scan_inbox()` regex переключён на `queued`.
- [ ] Файл с `Status: new` НЕ диспатчится (verified via test).
- [ ] Файл с `Status: queued` диспатчится корректно, статус переписывается в `processing`, файл уезжает в `inbox/done/`.
- [ ] Все 5 unit-тестов проходят.
- [ ] `dld-orchestrator.md` обновлён: секция scan_inbox описывает новый контракт + список статусов.
- [ ] `ai/inbox/README.md` (создать, если нет) документирует контракт статусов и роль Hermes.
- [ ] `.claude/rules/architecture.md` — добавить ADR-021: «Hermes intake gate — orchestrator dispatches only `queued` inbox items» (1 строка в таблице ADR).
- [ ] Backlog содержит запись TECH-181.
- [ ] До мерджа: все `Status: new` файлы в текущем `ai/inbox/` вручную приведены к новому контракту (Hermes/operator).

## Rollout / backcompat notes

- **Risk:** R1 — изменение dispatcher contract влияет на все источники inbox (Telegram, QA, reflect). Smoke-тест после deploy: создать тестовый `queued`-файл, убедиться что orchestrator его подхватил в течение одного цикла.
- **Rollback:** revert single commit; regex возвращается к `new`. State files (inbox/done/) совместимы с обеих сторон.
- **Coordination with Hermes:** Hermes должен знать новый контракт **до** мерджа TECH-181, иначе intake-конвейер встанет (никто не пишет `queued`). См. parallel issue в Hermes-репо (out of scope этой спеки).
- **Pending events / QA / reflect bridges:** out of scope здесь — они уже сейчас не пишут в `ai/inbox/` напрямую как `queued`. Если в будущем bridge решит писать в inbox, он должен ставить `draft`, не `queued` (Hermes promotes).

## Out of scope

- Реализация самого Hermes-бота, его Telegram-UX, ledger в `ai/intake/`.
- Auto-migration legacy `new` → `draft`.
- Изменение QA/reflect output paths.
- Reintroducing OpenClaw.

## Impact tree

- **UP (callers):** `process_project()` → `scan_inbox()` — без изменений сигнатуры.
- **DOWN (deps):** regex константа, `_parse_inbox_file`, `_pueue_add` — без изменений.
- **BY TERM:** `grep -r "Status:.*new" scripts/ docs/` после изменения = 0 hits в hot-path кода (template-примеры в `template/` оставляем).
- **CHECKLIST:** tests/, dld-orchestrator.md, architecture.md ADR, ai/inbox/README.md.
- **DUAL SYSTEM:** в момент перехода `new` (старое) и `queued` (новое) сосуществуют только на уровне файлов; код видит только `queued`.

## Blueprint reference

Соответствует north-star DLD orchestrator flow: «inbox → Spark → backlog → autopilot». TECH-181 формализует business-gate на самом первом шаге, который раньше был де-факто открыт.
