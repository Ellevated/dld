# ai/inbox/ — intake queue contract (TECH-181)

Inbox — это short-lived очередь сырых идей/артефактов от founder и автоматических
источников (Telegram, QA, reflect findings, pending events). **Hermes** —
conversational supervisor — выступает business-gate'ом между inbox и Spark.

## Status contract

Каждый `*.md` файл в `ai/inbox/` имеет YAML-стиль поле `**Status:** <state>`:

| Status | Кто пишет | Eligible for Spark dispatch? | Описание |
|--------|-----------|-------------------------------|----------|
| `draft` | author / source-bridge | ❌ | Сырая идея, business-context может быть неполным |
| `clarifying` | Hermes | ❌ | Hermes задал уточняющий вопрос Олегу |
| `stale` | Hermes | ❌ | Идея устарела или дубль |
| `rejected` | Hermes | ❌ | Out of scope / решено не делать |
| `queued` | **Hermes only** | ✅ | Business-complete, готово к Spark |
| `processing` | orchestrator | n/a | In-flight (выставляется `scan_inbox`) |
| `done` | orchestrator | n/a | Файл перенесён в `inbox/done/` |

**Hard rule:** orchestrator (`scripts/vps/orchestrator.py::scan_inbox`) дисптачит
**только** файлы с `**Status:** queued`. Любой другой статус игнорируется и
остаётся на диске без изменений.

## Lifecycle

1. Источник (Telegram-сообщение, QA-репорт, reflect-finding и т.п.) создаёт
   файл со `Status: draft`.
2. Hermes сканирует draft'ы, ведёт диалог с Олегом:
   - неполный контекст → `clarifying` + вопрос в Telegram;
   - шум/устарело → `stale` или `rejected`;
   - business-complete → `queued`.
3. Orchestrator `scan_inbox()` подхватывает `queued`, переписывает в
   `processing`, переносит файл в `inbox/done/<name>.md` и диспатчит Spark
   через pueue.
4. Spark создаёт спеку в `ai/features/`, добавляет в `ai/backlog.md`.

## Не делать

- ❌ Писать `Status: queued` напрямую из автоматических bridge'ей (QA, reflect,
  pending events). Все автоисточники пишут `draft`; решение «достоен ли Spark»
  принимает Hermes.
- ❌ Auto-migration `new` → `draft`. TECH-181 — clean break: legacy `new`-файлы
  игнорируются, оператор/Hermes выставляет корректный статус вручную.
- ❌ Использовать inbox как архив. Это short-lived очередь (≤5 активных файлов).

## File format

```markdown
# Short title

**Status:** draft
**Route:** spark            # spark | architect | council | bughunt | qa | reflect | scout
**Source:** telegram        # произвольная метка источника
**Provider:** claude        # optional, default из project_state
**Context:** ...            # optional

---

Тело идеи / brief / описание.
```

## References

- TECH-181 spec: `ai/features/TECH-181-2026-05-07-hermes-intake-bridge-status-gate.md`
- Orchestrator code: `scripts/vps/orchestrator.py::scan_inbox`
- ADR-021 (architecture.md)
