# BUG-188 — claude-runner converts successful runs to exit_code=1 on post-ResultMessage SDK exception

**Status:** queued | **Priority:** P0 | **Risk:** R1 | **Date:** 2026-05-20

## Symptom

Серия pueue tasks за 2026-05-19 завершилась `Failed (1)` с одинаковым trace, **несмотря на то что работа фактически выполнена**:

| pueue id | task | turns | cost | hard evidence работа сделана |
|---|---|---|---|---|
| #265 | awardybot:ARCH-1047 | ~43 | ~$3 | cache_hit=0.95, ResultMessage получен |
| #269 | dowry:TECH-434 | 43 | $6.32 | cache_hit=0.95, ResultMessage получен |
| #262 | dowry:BUG-433 | ~43 | ~$5 | то же |

Trace одинаковый:

```
2026-05-19 18:35:25,799 claude-runner ERROR SDK error: Command failed with exit code 1
File "/home/dld/projects/dld/scripts/vps/claude-runner.py", line 153, in run_task
    async for message in query(prompt=prompt, options=options):
File "claude_agent_sdk/_internal/query.py", line 740, in receive_messages
    raise Exception(message.get("error", "Unknown error"))
Exception: Command failed with exit code 1 (exit code: 1)
Error output: Check stderr output for details
2026-05-19 18:35:25,827 claude-runner INFO done project=dowry exit=1 turns=43 cost=$6.32
```

Callback корректно превращает `exit_code=1` в `blocked` (IMPL_GUARD). После этого orchestrator (через retry-loop, см. ARCH-187) подбирает ту же спеку снова, autopilot опять делает всю работу 43 turns, опять exit 1, опять blocked. **Десятки долларов opus-runs впустую на уже сделанной работе.**

## Root Cause (5 Whys)

**Why 1:** Почему `exit_code = 1` в логе, если SDK прислал ResultMessage с `is_error=False`?
→ Потому что после ResultMessage в стрим SDK прилетел `{"type": "error"}`, и `query.py:740` поднял общий `Exception(...)`. Наш except handler (`claude-runner.py:234`) выставил `exit_code = 1` поверх уже корректного значения.

**Why 2:** Почему SDK получает `type: error` после ResultMessage?
→ Точная причина не известна — **stderr субпроцесса CLI теряется**. SDK сообщение содержит только "Check stderr output for details", но `claude-runner.py` ловит `Exception` (не `ProcessError`), у которого `stderr` attribute отсутствует. Возможные причины: rate-limit close на стороне Anthropic API после длинной сессии, expired OAuth mid-run, network blip, CLI cleanup race. Без stderr — гадание.

**Why 3:** Почему наш handler не различает «упало до ResultMessage» и «упало после»?
→ Логика claude-runner.py:152-236 не отслеживает флаг "result_received". Любой `Exception` в `async for query()` цикле → `exit_code = 1`, безусловно. Хотя `turns=43, cost=$6.32, cache_hit=0.95` явно говорят, что **полезная работа уже была выполнена** и `ResultMessage.is_error=False`.

**Why 4:** Почему этот false-positive дорого стоит?
→ Потому что:
1. Callback видит `exit_code=1` → `STATUS_SYNC: writing lifecycle blocked` (правильное поведение для failed).
2. Lifecycle drift (ARCH-187) вытаскивает спеку обратно в queued.
3. Orchestrator ре-диспатчит. Autopilot не идемпотентен — он не проверяет «уже сделано». 43 turns × $6 = $258/неделя на одну зацикленную спеку.

**Why 5:** Почему autopilot не идемпотентен?
→ Потому что autopilot входит в pipeline (planner → coder → tester → reviewer) без early-exit проверки «была ли эта спека уже implemented в feature branch / на develop». Эта проверка существует на стороне **callback** (`verify_status_sync._spec_has_merged_implementation`, TECH-176 auto-close), но **только постфактум** — после того как autopilot уже потратил 43 turns. Должна быть и на старте.

**ROOT CAUSE:** Тройной gap:
1. `claude-runner.py` затирает успешный exit_code на 1 в except handler без проверки факта получения ResultMessage.
2. Stderr субпроцесса CLI теряется — diagnose невозможен.
3. Autopilot не имеет early-exit detection «работа уже сделана» (фронтовая защита, симметричная callback IMPL_GUARD).

## Reproduction Steps

**Воспроизведение факта (live):**

```bash
pueue log 269 --full 2>&1 | grep -E "turns|cost|exit|Fatal|Exception"
# turns=43, cost=$6.32, cache_hit=0.95
# Exception: Command failed with exit code 1
# done project=dowry exit=1 turns=43 cost=$6.3180
```

`turns=43, cost=$6.32, cache_hit=0.95` — это полная отработка. ResultMessage прилетел (иначе `turns` остался бы 0 — см. `claude-runner.py:178`). Но `exit=1`, потому что после ResultMessage SDK бросил Exception.

**Воспроизведение в unit test (план):**

```python
# tests/integration/test_claude_runner_post_result_exception.py
async def test_post_result_exception_does_not_override_success():
    """SDK throws after ResultMessage(is_error=False) → exit_code must remain 0."""
    # Mock query() to yield: AssistantMessage → ResultMessage(is_error=False) → raise Exception
    # Expected: log_data["exit_code"] == 0, not 1
```

## Fix Approach

### Layer 1 — Track `result_received` and `result_is_error` (PRIMARY FIX)

В `claude-runner.py`:

```python
result_received = False
result_is_error = False
# ... existing init ...

try:
    async for message in query(...):
        # ... existing handling ...
        if isinstance(message, ResultMessage):
            result_received = True
            result_is_error = getattr(message, "is_error", False)
            if result_is_error:
                exit_code = 1
            # NOTE: do NOT touch exit_code beyond this point in except handlers
            # if result_received and not result_is_error.
except Exception as e:
    err_str = str(e)
    stderr = getattr(e, "stderr", None) or _capture_subprocess_stderr()  # Layer 2
    if stderr:
        err_str = f"{err_str}\nSTDERR:\n{stderr}"

    if result_received and not result_is_error:
        # Work completed successfully before SDK post-cleanup error.
        # Log as WARNING, keep exit_code=0 (do not override).
        logger.warning(
            "SDK post-ResultMessage exception (work completed): %s",
            err_str[:500],
        )
    else:
        # Genuine failure — work did not complete.
        if "timeout" in err_str.lower():
            exit_code = 124
        else:
            logger.error("SDK error: %s", e, exc_info=True)
            exit_code = 1
        result_text = err_str
```

**Эффект:** task #269 (turns=43, ResultMessage получен, is_error=False) → `exit_code=0`. Callback видит Success → ставит `done`. Цикл retry прерывается.

### Layer 2 — Capture stderr субпроцесса

SDK internals (`claude_agent_sdk._internal.transport.subprocess_cli`) запускает `claude` CLI как subprocess с stderr → pipe. Сейчас stderr читается SDK и **молча drop'ается** при exception (только `ProcessError` сохраняет его в `.stderr` атрибуте).

Подход — обернуть transport:

```python
# claude-runner.py — before query() call:
import io
stderr_buffer = io.StringIO()

# Patch subprocess transport to tee stderr to our buffer
# (или через monkey-patch на `subprocess_cli._read_stderr`)
```

**Альтернатива (более чистая):** SDK 0.1.63 имеет debug callback API. Проверить через context7:
- Есть ли `ClaudeAgentOptions.stderr_callback` или аналог.
- Если есть — использовать.
- Если нет — monkey-patch transport class.

Не критично для основного fix'a (Layer 1), но необходимо для будущих diagnostics.

### Layer 3 — Autopilot early-exit detection (idempotency)

В `.claude/skills/autopilot/SKILL.md` (или в `intake.md` — первый шаг autopilot pipeline) добавить **проверку «работа уже сделана»** перед запуском planner:

```bash
# Pseudocode для autopilot intake step:
SPEC_ID="$1"
ALLOWED_FILES=$(callback._parse_allowed_files spec.md)

# Are all allowed files already modified on develop AFTER spec creation date?
SPEC_CREATED=$(git log --reverse --format=%ai ai/features/${SPEC_ID}*.md | head -1)
RECENT_COMMITS=$(git log --since="$SPEC_CREATED" --all --oneline -- $ALLOWED_FILES | wc -l)

if [ "$RECENT_COMMITS" -gt 0 ]; then
    echo '{"task_status": "complete", "result_preview": "Early-exit: spec already implemented in $(git log --since="$SPEC_CREATED" --all --oneline -- $ALLOWED_FILES | head -3)"}'
    exit 0
fi
```

Это **симметрично** `callback._spec_has_merged_implementation` (TECH-176 auto-close), но на стороне autopilot **до** запуска planner. Спасает 43 turns × $6 per retry.

**Альтернатива (более LLM-friendly):** добавить early-exit инструкцию в autopilot system prompt: "Before invoking /planner, check whether the spec's Allowed Files have commits newer than the spec file itself. If yes — output task_status:complete immediately."

### Layer 4 — Telemetry для будущих SDK exceptions

Если Layer 1 ловит `result_received and post-result Exception`, это сигнал о SDK bug (race в cleanup, или сервер шлёт error после end-of-stream). Залогировать в новой таблице:

```sql
CREATE TABLE IF NOT EXISTS sdk_post_result_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    project_id TEXT NOT NULL,
    task TEXT NOT NULL,
    turns INTEGER,
    cost_usd REAL,
    error_msg TEXT,
    stderr TEXT
);
```

Чтобы при превышении threshold (>5 в день) — алёрт founder'у. Это backup-плоскость на случай если SDK bug рецидивирует или мы что-то прозевали.

## Impact Tree Analysis

### Step 1: UP — кто использует claude-runner.py?

- [x] `scripts/vps/run-agent.sh` — единственный caller, через `pueue add`.
- [x] `scripts/vps/orchestrator.py` — диспатчит pueue tasks через run-agent.sh.
- [x] `scripts/vps/callback.py` — читает exit_code из pueue result, ставит status в lifecycle.

### Step 2: DOWN — от чего зависит claude-runner.py?

- [x] `claude_agent_sdk==0.1.63` — внешний deps. `query()`, `ClaudeAgentOptions`, `ResultMessage`, `AssistantMessage`, `TaskNotificationMessage`.
- [x] `claude_agent_sdk._errors` — `CLIConnectionError`, `ProcessError`.
- [x] CLI binary в venv (`claude_agent_sdk/_bundled/claude`).

### Step 3: BY TERM — grep по проекту

| Term | Files | Action |
|------|-------|--------|
| `exit_code = 1` | claude-runner.py:182, 235 | Добавить condition на result_received |
| `result_received` | (new) | Добавить tracking |
| `_spec_has_merged_implementation` | callback.py | Зеркальная логика для autopilot intake |
| `MAX_TURNS` | claude-runner.py:59 | 120 — НЕ менять (turns=43 < 120, лимит не виноват) |

### Step 4: CHECKLIST — обязательные папки

- [x] `tests/integration/test_claude_runner_*.py` — добавить regression тест на post-result exception
- [x] `tests/integration/test_callback_*.py` — добавить тест что Success exit с post-result exception не демоутит
- [x] `.claude/skills/autopilot/intake.md` (если не существует) — early-exit logic
- [x] `scripts/vps/schema.sql` — добавить `sdk_post_result_errors` table

### Step 5: DUAL SYSTEM

- callback's existing IMPL_GUARD (`_spec_has_merged_implementation`) — постфактум защита.
- Autopilot early-exit (Layer 3) — фронтовая защита.
Обе работают вместе: front-side экономит compute, callback-side подтверждает correctness.

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row. -->

- `scripts/vps/claude-runner.py` — track `result_received` / `result_is_error`, preserve exit_code on post-result exception, capture stderr
- `.claude/skills/autopilot/SKILL.md` — add early-exit detection step before planner invocation
- `template/.claude/skills/autopilot/SKILL.md` — same in template
- `scripts/vps/schema.sql` — add `sdk_post_result_errors` table (Layer 4 telemetry)
- `scripts/vps/db.py` — add `log_sdk_post_result_error()` helper
- `tests/integration/test_claude_runner_post_result_exception.py` — NEW: regression test
- `tests/integration/test_autopilot_early_exit.py` — NEW: idempotency test
- `.claude/rules/architecture.md` — append note about claude-runner exit_code contract

## Tests

### Deterministic (5)

1. Mock `query()` yields: `AssistantMessage` → `ResultMessage(is_error=False, num_turns=43, total_cost_usd=6.32)` → `raise Exception("post-cleanup error")`. Result: `log_data["exit_code"] == 0`, `log_data["turns"] == 43`, `result_preview` contains assistant text.
2. Mock `query()` yields: `raise Exception("init failure")` БЕЗ ResultMessage. Result: `log_data["exit_code"] == 1`, `log_data["turns"] == 0`.
3. Mock `query()` yields: `ResultMessage(is_error=True)`. Result: `log_data["exit_code"] == 1` (genuine failure case).
4. `ProcessError` с stderr поле — stderr попадает в `result_preview`.
5. `Exception` без stderr — Layer 2 stderr capture работает (или graceful fallback).

### Integration (3)

6. Запустить run-agent.sh с mocked SDK который имитирует post-result exception — pueue task завершается Success (exit 0), callback ставит `done` (не blocked).
7. Запустить autopilot intake step на спеке, чьи Allowed Files уже изменены в develop — autopilot выходит с `task_status: complete` в первом turn'е (no planner invocation).
8. Layer 4 telemetry: пост-result exception инкрементирует row в `sdk_post_result_errors`, threshold алёрт работает.

### LLM-Judge (1)

9. Прочитать обновлённый `.claude/skills/autopilot/SKILL.md` — early-exit instruction должна быть однозначной и не допускать "ложного срабатывания" (false skipping когда работа реально нужна). Rubric: чёткое определение "spec already implemented" через коммиты в Allowed Files после spec creation date.

## Definition of Done

- [ ] `claude-runner.py` использует `result_received` / `result_is_error` флаги
- [ ] Post-result exception → log WARNING, не override exit_code=0
- [ ] stderr субпроцесса CLI captured (через transport hook или monkey-patch)
- [ ] Autopilot SKILL.md содержит early-exit step (оба места — `.claude/` и `template/.claude/`)
- [ ] `sdk_post_result_errors` table в schema.sql, `db.py` helper
- [ ] 9 тестов проходят (5 deterministic + 3 integration + 1 LLM-judge)
- [ ] Regression check: тест воспроизводит trace #269 (turns=43, post-result Exception) и получает exit_code=0
- [ ] callback-debug.log не содержит `STATUS_SYNC: ... — writing lifecycle blocked` для tasks с turns≥30, cost≥$1 (signal что false-fails больше нет)
- [ ] `.claude/rules/architecture.md` обновлён — добавлен раздел про claude-runner exit_code contract

## Connection to ARCH-187

BUG-188 закрывает **первичный** failure (false-fail из-за SDK post-result exception). ARCH-187 закрывает **retry-loop pathway** (lifecycle drift, который рекурсивно ре-диспатчит blocked specs). Без обоих:
- Только BUG-188 без ARCH-187: false-fail исчезает, но реальные blocked (от других причин) застрянут в петле.
- Только ARCH-187 без BUG-188: false-fails будут демотать спеки в blocked, и они застрянут навсегда до ручного `spec_operator demote ... queued`.

**Запускать в любом порядке, обе важны.** Если приоритизировать — BUG-188 первым, т.к. он останавливает burning cost моментально.

## Drift Log

Заполняется autopilot'ом при отклонении плана от реальности.
