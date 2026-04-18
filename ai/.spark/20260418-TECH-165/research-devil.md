# Devil's Advocate — TECH-165: Anthropic Pipeline Optimization

## Why NOT Do This?

### Argument 1: setting_sources=[] bugfix — молчаливое изменение контракта
**Concern:** SDK 0.1.60 починил баг: `setting_sources=[]` раньше молча игнорировалось (настройки грузились), теперь реально отключает настройки. В `claude-runner.py:93` мы передаём `setting_sources=["user", "project"]` — это НЕ пустой список, поэтому прямого сломать не должно. Но: внутри Skills (когда spark/autopilot запускает суб-агентов через Task tool), суб-агенты могут наследовать или переопределять `setting_sources`. Если где-то в цепочке суб-агент передавал `setting_sources=[]` как "использовать дефолт" — после апгрейда он получит пустые настройки и перестанет видеть CLAUDE.md и `.claude/` директорию.
**Evidence:** `claude-runner.py:93` — `setting_sources=["user", "project"]` (наш код корректен), но суб-агенты через Task tool не контролируются напрямую из `claude-runner.py`. Они запускаются изнутри claude CLI. Поведение `setting_sources` для вложенных Task вызовов не задокументировано в нашем коде.
**Impact:** High
**Counter:** Перед апгрейдом запустить один autopilot-run с `--verbose` и проверить, что суб-агенты (coder, tester, planner) видят CLAUDE.md. Или сначала апгрейдить в изолированном venv на тестовой задаче.

### Argument 2: thinking bugfix 0.1.57 — silent regression для всех effort=max агентов
**Concern:** До 0.1.57 `thinking: {type: "adaptive"}` неверно конвертировался в `--max-thinking-tokens` вместо правильного флага. То есть сейчас наши 8 агентов с `effort: max` (planner, debugger, council/synthesizer, council/{architect,pragmatist,product,security}, spark/facilitator, architect/facilitator, board/facilitator) работают с неправильно переданными параметрами thinking. После апгрейда они начнут работать "правильно" — что значит другое поведение думания. Агенты, у которых thinking раньше "тихо не работало так как задумано" — могут тратить значительно больше или меньше токенов на thinking. На 3 параллельных autopilot-сессиях это может привести к резкому скачку потребления или, наоборот, к деградации качества reasoning.
**Evidence:** Research doc строка 39: "thinking маппинг — `adaptive`/`disabled` неверно конвертировался в `--max-thinking-tokens` вместо `--thinking`". Все агенты с `effort: max` в `.claude/agents/` затронуты: `planner.md:4-5`, `debugger.md:4-5`, `council/synthesizer.md:4-5`, `council/architect.md:4-5`, `council/pragmatist.md:4-5`, `council/product.md:4-5`, `council/security.md:4-5`, `spark/facilitator.md:4-5`, `architect/facilitator.md:4-5`, `board/facilitator.md:4-5`.
**Impact:** High
**Counter:** Нельзя предотвратить, только мониторить. До апгрейда снять baseline: средний cost_usd и turns для типичного autopilot-run (из logs/). После апгрейда сравнить на первых 3 run.

### Argument 3: Смена model на synthesizer'ах — деградация без алерта
**Concern:** council/synthesizer делает не просто "merge/format" — он разрешает конфликты между экспертами при расхождении 2-2 (своим суждением), выбирает между security-критичными решениями и архитектурными, и пишет `decision: approved | needs_changes | rejected` который идёт в production. Sonnet при effort=high может принять неверное решение в граничных случаях (security vs pragmatism). Самое опасное: деградация качества не видна сразу. Через 2-3 недели в backlog появятся спеки с security holes, которые никто не заметит.
**Evidence:** `council/synthesizer.md:55-70` — Conflict Resolution включает "Security always wins — Viktor's critical issues block" и "2-2 split — Your judgment decides". Это не механическое merge — это суждение под давлением конфликта.
**Impact:** High
**Counter:** Если переводим council/synthesizer на Sonnet — добавить явный output constraint: "при любом security-конфликте всегда выбирай security-verdict". Мониторить первые 5 council-решений вручную.

### Argument 4: Prompt caching на Max-подписке — может вообще не работать
**Concern:** `ENABLE_PROMPT_CACHING_1H` — это env var для Claude Code CLI. Подписка Claude Code Max — это не API, это SaaS UI + CLI tool. Prompt caching в Anthropic API работает на уровне inference запросов и биллится (cache write дороже чем обычный input). На Max-подписке (flat fee) нет per-token cost — значит: а) кэширование может быть уже включено автоматически провайдером, б) ENABLE_PROMPT_CACHING_1H может не иметь эффекта или влиять только на TTL, в) cache_creation_input_tokens / cache_read_input_tokens в ResultMessage.usage могут не возвращаться (так как нет per-token billing). Логировать cache hit rate некуда и незачем.
**Evidence:** `claude-runner.py:139` — `cost_usd = getattr(message, "total_cost_usd", 0.0) or 0.0`. На Max-подписке `total_cost_usd` обычно 0.0 или None. `ResultMessage.usage` (types.py:884) содержит `dict[str, Any] | None` — структура не гарантирована.
**Impact:** High
**Counter:** Перед реализацией prompt caching logging — проверить, что `ResultMessage.usage` содержит cache_read_input_tokens хотя бы в одном тестовом run. Если нет — вся задача по caching monitoring бессмысленна.

### Argument 5: Три изменения одновременно = невозможная диагностика
**Concern:** SDK upgrade + model routing + prompt caching — три независимых источника риска. Если через 3 дня autopilot начнёт выдавать плохие спеки или застревать — невозможно понять причину: thinking bugfix изменил поведение? Sonnet не справляется? Caching сломал system prompt структуру? 3 параллельных сессии + night reviewer = 4 concurrent точки отказа.
**Evidence:** В `scripts/vps/callback.py` нет A/B метрики качества — только exit_code и turns. `log_data` в `claude-runner.py:180-189` логирует `cost_usd` и `turns` но не семантическое качество вывода. Регрессию по качеству обнаружим только когда QA прогонится или человек прочитает спеки.
**Impact:** High
**Counter:** Развернуть поэтапно: сначала SDK (1 неделя мониторинга), потом model routing (1 неделя), потом caching. Или хотя бы разнести SDK upgrade от model changes на 2-3 дня.

---

## Simpler Alternatives

### Alternative 1: Только SDK upgrade, без model routing и caching
**Instead of:** Все три изменения в одной задаче
**Do this:** Отдельная микро-задача TECH-165a: только `pip install --upgrade claude-agent-sdk==0.1.63` + проверка импортов. Остальное — TECH-165b, TECH-165c по результатам мониторинга.
**Pros:** SDK upgrade — реально нужен (thinking bugfix критичен для агентов с effort=max). Изолированный риск R2. Откат: `pip install claude-agent-sdk==0.1.48` за 30 секунд, без git revert.
**Cons:** Не реализует потенциальную экономию от model routing.
**Viability:** High

### Alternative 2: Model routing только для bughunt/validator, без facilitator'ов
**Instead of:** 5 агентов Opus → Sonnet включая synthesizer'ы
**Do this:** Только bughunt/validator: opus → sonnet high (это уже указано в model-capabilities.md как цель, есть фактическое расхождение). Facilitator'ы оставить на opus — они orchestrate multi-step write chains, которые при сбое дорого откатывать.
**Pros:** Минимальный риск. bughunt/validator делает чёткий structured YAML output — проверить качество легко.
**Cons:** Не затрагивает council/synthesizer — там потенциально большая экономия.
**Viability:** High

### Alternative 3: Пропустить prompt caching полностью (на Max-подписке)
**Instead of:** ENABLE_PROMPT_CACHING_1H + переработка system prompts + cache hit logging
**Do this:** Ничего. Max-подписка = flat fee. Экономия токенов не конвертируется в денежную экономию. Вынос динамики из system prompts — значимое рефакторинг всех агентских промптов с риском сломать агентов, которые ожидают дату/task_id в системном промпте.
**Pros:** Ноль риска. Ноль работы. На Max-подписке ROI = 0.
**Cons:** Если перейдём на API-billing в будущем — придётся делать тогда.
**Viability:** High

**Verdict:** Разбить на 3 независимые задачи: TECH-165a (SDK upgrade — R2, делать сейчас), TECH-165b (bughunt/validator model change — R2, после мониторинга SDK), TECH-165c (facilitator'ы + council/synthesizer — R1, с A/B на одной сессии + мониторинг 2 недели). Prompt caching на Max-подписке — SKIP.

---

## Eval Assertions (Structured from Risk Analysis)

### Deterministic Assertions

| ID | Scenario | Input | Expected Behavior | Risk | Priority | Type |
|----|----------|-------|-------------------|------|----------|------|
| DA-1 | SDK upgrade не ломает setting_sources | claude-runner.py после pip install 0.1.63 | Суб-агенты (coder, planner) видят CLAUDE.md и .claude/skills/ | High | P0 | deterministic |
| DA-2 | Thinking bugfix не вызывает timeout | autopilot run с effort=max агентом (planner) после апгрейда | Завершается без timeout (exit_code != 124), turns разумное (<80) | High | P0 | deterministic |
| DA-3 | council/synthesizer на Sonnet разрешает security-конфликт | 2 эксперта approve, security эксперт reject (critical) | decision=needs_changes, blocking_issues содержит security issue | High | P0 | deterministic |
| DA-4 | council/synthesizer на Sonnet при 2-2 split | Architect и Security против Pragmatist и Product | Выдаёт decision с явным reasoning, не "approved" по умолчанию | High | P1 | deterministic |
| DA-5 | bughunt/validator на Sonnet triages 30+ findings | 30 findings от 6 personas, 10+ out of scope | status=accepted, groups_formed 3-8, relevant < 30 (фильтрация работает) | Med | P1 | deterministic |
| DA-6 | architect/facilitator на Sonnet управляет multi-step write | Запуск /architect с реальным business blueprint | 5 subagent write steps завершаются, все 5 output файлов созданы | Med | P1 | deterministic |
| DA-7 | ENABLE_PROMPT_CACHING_1H на Max-подписке | Установить env var, запустить council run | ResultMessage.usage содержит cache_read_input_tokens (иначе фича бессмысленна) | High | P0 | deterministic |
| DA-8 | SDK upgrade не ломает CLIConnectionError/ProcessError import | claude-runner.py:30 импорт _errors | ImportError не возникает (путь к _errors стабилен между версиями) | Med | P0 | deterministic |
| DA-9 | Cost tracking не ломается | autopilot run после апгрейда | ResultMessage.total_cost_usd доступен, log_data['cost_usd'] записывается | Low | P2 | deterministic |

### Side-Effect Assertions

| ID | Affected Component | File:line | Regression Check | Priority |
|----|-------------------|-----------|------------------|----------|
| SA-1 | claude-runner.py импорты SDK | scripts/vps/claude-runner.py:23-30 | `from claude_agent_sdk._errors import CLIConnectionError, ProcessError` не бросает ImportError после апгрейда (путь _errors может измениться) | P0 |
| SA-2 | Pueue callback exit codes | scripts/vps/callback.py | exit_code=2 (CLIConnectionError) и exit_code=3 (ProcessError) по-прежнему маппятся корректно — классы в _errors не переименованы | P0 |
| SA-3 | Night reviewer | scripts/vps/night-reviewer.sh | /audit night skill работает через claude CLI (не SDK) — не затронут SDK upgrade, проверить что CLI version совместима с bundled SDK | P1 |
| SA-4 | model-capabilities.md расхождение | .claude/rules/model-capabilities.md | После смены bughunt/validator: opus→sonnet — обновить таблицу в model-capabilities.md (сейчас там написано opus, будет sonnet) | P1 |

### Assertion Summary
- Deterministic: 9 | Side-effect: 4 | Total: 13

---

## What Breaks?

### Side Effects

| Affected Component | File:line | Why It Breaks | Fix Required |
|--------------------|-----------|---------------|--------------|
| claude-runner.py error handling | scripts/vps/claude-runner.py:30 | `from claude_agent_sdk._errors import CLIConnectionError, ProcessError` — если в 0.1.63 _errors модуль переехал или классы переименованы, ProcessError/CLIConnectionError не поймаются, вместо exit_code=3 будет exit_code=1 через bare Exception | Проверить `_errors.py` в новой версии перед апгрейдом |
| callback.py exit code routing | scripts/vps/callback.py | exit_code=124 (timeout), 2, 3 используются для разного поведения pueue slot release. Если SDK меняет семантику ошибок — неверный release | Добавить тест: запустить намеренно невалидный prompt, убедиться что exit_code=3 |
| Agent effort=max behavior | все 10 агентов с effort=max | thinking bugfix 0.1.57: теперь thinking работает "как задумано" — агенты могут тратить больше времени на thinking → risk TIMEOUT_SECONDS=3600 при сложных задачах | Мониторить turns и duration_ms в logs/ первые 48h после апгрейда |
| model-capabilities.md SSOT | .claude/rules/model-capabilities.md | Таблица описывает bughunt validator как opus, но предложение меняет на sonnet — расхождение SSOT | Обновить одновременно со сменой агента |

### Dependencies at Risk

| Dependency | Type | Risk | Mitigation |
|------------|------|------|------------|
| claude_agent_sdk._errors module path | import | High | Проверить путь в venv/lib/python3.12/site-packages/claude_agent_sdk/_errors.py новой версии (уже есть в 0.1.48, но могут переместить) |
| ResultMessage.total_cost_usd | API contract | Low | Поле объявлено как `float | None` в types.py:884 — стабильно, вряд ли уберут |
| ResultMessage.usage cache fields | API contract | High | На Max-подписке usage может не содержать cache_read_input_tokens — нужно проверить перед реализацией cache logging |
| 3 live autopilot sessions | operational | High | Upgrade venv во время активных pueue задач → текущие задачи продолжат работать со старым SDK (уже загружен в memory), новые запустятся с новым. Нет риска для in-flight. |
| night-reviewer.sh | operational | Low | Использует claude CLI напрямую (не SDK) — не затронут SDK upgrade |

---

## Test Derivation

All test cases are captured in `## Eval Assertions` above as DA-IDs and SA-IDs.
Facilitator maps these to EC-IDs in the spec's `## Eval Criteria` section.

---

## Questions to Answer Before Implementation

1. **Question:** Возвращает ли `ResultMessage.usage` поля `cache_read_input_tokens` и `cache_creation_input_tokens` на Max-подписке?
   **Why it matters:** Если нет — весь блок "prompt caching monitoring" (logging в callback.py) не имеет смысла и создаёт мёртвый код. Проверить: запустить один run с 0.1.63, напечатать `message.usage` из `ResultMessage`.

2. **Question:** Изменился ли путь к `_errors` модулю между 0.1.48 и 0.1.63?
   **Why it matters:** `claude-runner.py:30` импортирует `from claude_agent_sdk._errors import CLIConnectionError, ProcessError`. Если путь изменился — ImportError при старте = все pueue задачи падают с exit_code=1. Проверить: `pip download claude-agent-sdk==0.1.63 --no-deps && unzip ...` и посмотреть структуру папок.

3. **Question:** Как ведут себя in-flight pueue задачи при `pip install --upgrade` в venv во время их работы?
   **Why it matters:** Python загружает `.pyc` в memory при старте процесса. Текущие 3 autopilot-сессии уже загрузили 0.1.48 — upgrade их не затронет. Но если `pip install` обновит bundled CLI binary внутри venv — процесс уже запущенный может потерять доступ к бинарнику (subprocess exec). Проверить: запустить `pip install --upgrade` и `pueue status` одновременно.

4. **Question:** council/synthesizer реально делает "merge/format" или глубокое суждение?
   **Why it matters:** Скаут классифицировал его как "merge/format экспертных заключений — не глубокое мышление". Но `synthesizer.md:55-70` показывает: conflict resolution при 2-2 split — это суждение, не форматирование. Если переведём на Sonnet и случится 2-2 split с security вопросом — качество решения снизится незаметно.

5. **Question:** ENABLE_PROMPT_CACHING_1H влияет на Claude Code CLI на Max-подписке или только на API-based billing?
   **Why it matters:** На Max-подписке нет per-token billing. Env var может либо не иметь эффекта, либо включать кэш без видимого эффекта на качество/скорость, либо ломать структуру запросов. До реализации нужно подтверждение от Anthropic docs или эмпирическая проверка.

---

## Final Verdict

**Recommendation:** Proceed with caution — но ТОЛЬКО если разбить на три независимые задачи с паузой на мониторинг между ними.

**Reasoning:**

SDK upgrade (0.1.48 → 0.1.63) — нужен. Thinking bugfix 0.1.57 реально меняет поведение 10 effort=max агентов — это исправление молчаливого бага, без апгрейда мы живём с неправильно работающим thinking. Риск управляем: откат = `pip install claude-agent-sdk==0.1.48`.

Model routing — частично обоснован. bughunt/validator: смена opus → sonnet закреплена даже в model-capabilities.md как цель — это устранение расхождения документации. Facilitator'ы и council/synthesizer — спорно. Spark/facilitator и board/facilitator действительно process keepers (не принимают решений). Architect/facilitator делает multi-step write chain — риск выше. Council/synthesizer разрешает security-конфликты своим суждением — это не форматирование, Sonnet может ошибаться в граничных кейсах, деградация будет замечена через недели.

Prompt caching на Max-подписке — фундаментально сомнительно. Flat fee = нет денежной экономии. Вынос динамики из system prompts — значимый рефакторинг всех агентов с риском регрессий. Logging cache hit rate может не работать вообще. ROI близок к нулю.

**Conditions for success:**
1. Разбить на TECH-165a (SDK upgrade, R2), TECH-165b (bughunt/validator, R2), TECH-165c (facilitator'ы + council/synthesizer, R1 с мониторингом 2 недели), TECH-165d (prompt caching) — TECH-165d реализовывать только после подтверждения что usage fields доступны на Max-подписке
2. SDK upgrade запускать только между pueue задачами (pueue pause + upgrade + pueue start) — не во время активных сессий
3. После SDK upgrade: 48h мониторинг turns и duration_ms в logs/ перед запуском следующей волны изменений (ищем аномальный рост из-за thinking bugfix)
4. Council/synthesizer перевод на Sonnet — только с ручным ревью первых 5 council-вердиктов
5. Обновить model-capabilities.md синхронно со сменой bughunt/validator
