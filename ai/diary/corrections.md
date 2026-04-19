# Corrections Diary

## 2026-02-16: During Bug Hunt ADR-008 test

**Context:** Testing `run_in_background: true` pattern in Bug Hunt pipeline
**I did:** Edited `template/.claude/` files, then ran test
**User corrected:** "мне кажется у тебя просто какой то кривой скил загрузился?"
**Why:** Template-sync rule: DLD uses `.claude/` at runtime, not `template/.claude/`. Editing template without syncing = test on old code.
**Rule:** ALWAYS sync template → .claude/ BEFORE testing. Verify with `grep` that the change is in the ACTIVE file.

---

## 2026-04-18: During TECH-165 pipeline optimization research

**Context:** Обсуждение оптимизаций из Anthropic research report — раздел P3 включал Batch API (50% скидка) для ночного ревьюера
**I proposed:** Использовать Batch API для ночного ревьюера — стекируется с prompt cache reads, до 95% экономии
**User corrected:** "мы же это гоняем на подписке а не через апи, нам оно не надо"
**Why:** DLD-пайплайн работает через Claude Code CLI на **Max-подписке** (flat fee), а не per-token API billing. Скидки типа Batch API/prompt caching pricing на подписку не распространяются.
**Rule:** При оценке экономии учитывать billing mode. Подписка → API-скидки неприменимы. Оптимизировать нужно **время исполнения** и **качество выхода**, не per-token стоимость. Prompt caching снижает latency (полезно), но не счёт.
**Applies to:** любые будущие рекомендации по cost optimization — сначала спрашивать "мы на подписке или API?"
