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

## 2026-05-20: During ARCH-187

**Context:** Я создал спеку ARCH-187 (P0 × R1) и добавил блок `⚠️ ACTION REQUIRED: HUMAN REVIEW BEFORE AUTOPILOT`, сославшись на CLAUDE.md routing matrix.
**I proposed:** Блокирующий маркер для ручного отпуска P0×R1 спек в autopilot.
**User corrected:** "убери эту метку, зачем она"
**Why:** Метка блокирует автономное исполнение без явной пользы — founder доверяет autopilot обработать риск, а не ручному gating.
**Rule:** НЕ добавлять `ACTION REQUIRED` / `HUMAN REVIEW` маркеры в спеки автоматически по матрице рисков. Только если пользователь явно попросил.

## 2026-05-26: During ARCH-196

**Context:** Phase 1 Question 2 — backlog.md role/writer
**I proposed:** 3 варианта (render-only view, manual writer queue, выкинуть backlog)
**User corrected:** "я руками не лажу и не смотрю, главное чтобы ты не путался. выкидывать беклог подкладывая другую сущность вместо него - это менять шило на мыло."
**Why:** Founder не читает backlog глазами. Backlog существует ТОЛЬКО как инструмент для LLM (spark/autopilot) не путаться. Замена сущности (отдельный CLI/Telegram view) — это шило на мыло, не решение.
**Rule:** Backlog.md — это work queue + state view ДЛЯ LLM, не для human. Дизайн оптимизируем под "spark/autopilot не сбиваются", а не под "красивый readable файл". Не предлагать выкидывать backlog с заменой на другие human-facing artefacts.

## 2026-05-26: During ARCH-196 — Symptom 1 ROOT CAUSE identified

**Context:** Phase 1 Question 4 — что за "3 раза spark не закоммитил"
**Founder reported:** "бля ну нашли уже все и закомитили, как ты теперь следы эти найдешь? это же работа со спарк в интерактиве, он просто говорит спека готова (а сам не комитил ее) я просто его просил закомитить. раньше он сам это делал"
**Root cause:** spark/completion.md в текущей версии имеет конфликт инструкций:
- "## Auto-Commit + Push (MANDATORY)" говорит коммитить автоматически
- "## Output → If running interactively (Skill tool): Write spec file when spec is complete, then ask about autopilot handoff." говорит спросить пользователя
LLM в interactive mode выбирает "ask user" → commit пропущен.
**Rule:** Auto-commit MANDATORY должен быть unconditional. Никаких "ask about handoff" в interactive — handoff к autopilot он автоматический через orchestrator. Если interactive — после commit СКАЗАТЬ что спека закоммичена + pushed, без вопросов.
