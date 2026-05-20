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

> **Planner update (2026-05-20):** verified `claude_agent_sdk` source at `e41cbdd4`
> — `ClaudeAgentOptions` exposes a **public** `stderr: Callable[[str], None] | None`
> callback (and a deprecated `debug_stderr` file-like). The transport only pipes
> stderr when `options.stderr is not None`. **No monkey-patch needed.** Layer 2
> reduces to "set `options.stderr=<line collector>` and join captured lines into
> `result_text` on exception". See Task 2.

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

## Implementation Plan

### Drift Notes (Plan agent, 2026-05-20)

| Spec assumption | Reality | Action |
|---|---|---|
| `claude-runner.py:153` loop, `:234` except Exception, `:235` exit_code=1 | Loop at L152-153, except Exception block L224-236, exit_code=1 at L182 (inside `if is_error`) and L235 (Exception handler) | Line numbers in steps below use current state |
| Layer 2 needs monkey-patch of `subprocess_cli` | **SDK 0.1.63 exposes public `ClaudeAgentOptions.stderr: Callable[[str], None]`** (verified against `claude-agent-sdk-python@e41cbdd4`) | Use public API — no monkey-patch. Much smaller blast radius. |
| Layer 4 telemetry needs schema.sql edit + manual ALTER on prod VPS | `scripts/vps/db.py:_ensure_migrations()` already implements lazy idempotent `CREATE TABLE IF NOT EXISTS` pattern (TECH-169 `callback_decisions`) | Mirror that pattern: add to `_ensure_migrations` (auto-applied on first DB open) AND add to `schema.sql` (for fresh VPS) — same as callback_decisions did |
| `.claude/` and `template/.claude/` autopilot SKILL.md identical | They **differ** (different "Context Management" + "Loop Mode" wording) but **"Pre-flight Check" section is identical** | Patch both in Pre-flight Check section (similar diff applied to both) |

### Order & Dependencies

```
Task 1 (Layer 1 core) ─┬─→ Task 4 (wire telemetry) ←─ Task 3 (Layer 4 table+helper)
                       │
Task 2 (Layer 2 stderr)┘

Task 5 (Layer 3 SKILL.md)   — independent, parallel
Task 6 (docs ADR + deps.md) — last, after code merges
```

Task 1 must land first (it changes the exit_code contract; later tasks rely on the
`result_received` flag). Tasks 2 and 5 are independent of 1 mechanically but share
the same file (`claude-runner.py`) for Task 2 — so do 1 → 2 sequentially. Task 3
is purely additive (new table, new helper). Task 4 depends on 1 and 3.

---

### Task 1: Layer 1 — track `result_received` / `result_is_error`, preserve success exit on post-result Exception

**Files:**
- `scripts/vps/claude-runner.py` (modify)
- `tests/integration/test_claude_runner_post_result_exception.py` (NEW)

**Steps:**

1. **Modify `scripts/vps/claude-runner.py`:**

   1.1. Before the `try:` at line 152, add two tracking flags (insert after the existing init block at line 151):

   ```python
       result_received = False
       result_is_error = False
   ```

   1.2. Inside the `if isinstance(message, ResultMessage):` block at line 176, set the flags **before** the existing `is_error` check. New lines (insert immediately after line 176 opening):

   ```python
                   result_received = True
                   result_is_error = bool(getattr(message, "is_error", False))
   ```

   Keep the existing `if is_error: exit_code = 1` (line 180-182) — it remains the source of truth for legitimate ResultMessage(is_error=True).

   1.3. Modify the `except Exception as e:` handler at lines 224-236. After the existing `err_str` / `stderr` extraction (keep that, it handles `getattr(e, "stderr", None)` from `ProcessError`), branch on `result_received and not result_is_error`:

   ```python
       except Exception as e:
           err_str = str(e)
           stderr = getattr(e, "stderr", None)
           if stderr:
               err_str = f"{err_str}\nSTDERR:\n{stderr}"

           if result_received and not result_is_error:
               # BUG-188: SDK threw AFTER successful ResultMessage. Work is done
               # (turns/cost/result_text already captured). Do NOT override
               # exit_code to 1 — that would re-blocked an already-done spec
               # and burn another $5+/run on retry.
               logger.warning(
                   "SDK post-ResultMessage exception (work completed): %s",
                   err_str[:500],
               )
               # exit_code stays 0; result_text already populated
           elif "timeout" in err_str.lower():
               logger.error("SDK init timeout: %s", e)
               exit_code = 124
               result_text = err_str
           else:
               logger.error("SDK error: %s", e, exc_info=True)
               exit_code = 1
               result_text = err_str
   ```

   Note: `result_text` is **not** overwritten in the post-result-success branch; we keep the ResultMessage `result` field captured at line 177.

2. **Write `tests/integration/test_claude_runner_post_result_exception.py`** (NEW file ~150 LOC).

   Pattern from `tests/integration/test_callback_already_merged.py:1-40`: add `scripts/vps` to `sys.path`, import the module, use real fs + pytest. **No mocks of project code** (ADR-013) — but mocking `query()` from the **external** `claude_agent_sdk` is allowed (it's the boundary).

   Four test functions covering deterministic cases #1–#3 from spec:

   - `test_post_result_exception_preserves_success` — async generator yields `AssistantMessage(text="ok")` → `ResultMessage(is_error=False, num_turns=43, total_cost_usd=6.32, result="DONE")` → `raise Exception("Command failed with exit code 1")`. Asserts `log_data["exit_code"] == 0`, `log_data["turns"] == 43`, `log_data["cost_usd"] == 6.32`, `log_data["result_preview"]` non-empty.
   - `test_pre_result_exception_marks_failure` — generator raises Exception immediately (no ResultMessage). Asserts `exit_code == 1`, `turns == 0`.
   - `test_result_message_is_error_true_marks_failure` — generator yields `ResultMessage(is_error=True)` then returns cleanly. Asserts `exit_code == 1`.
   - `test_timeout_exception_uses_exit_124` — generator raises `Exception("Control request timeout: initialize")` before ResultMessage. Asserts `exit_code == 124`.

   Mock via `unittest.mock.patch("claude_runner.query", new=fake_query)` where `fake_query` is an async generator factory.

**Test:**
- `tests/integration/test_claude_runner_post_result_exception.py::test_post_result_exception_preserves_success` — proves the trace-#269 regression: post-result Exception keeps exit_code=0.
- The other three tests guard against regression in the genuine-failure branches.

**Acceptance:**
- All 4 tests pass.
- Reading the diff: the `except Exception` handler has exactly one branch where `exit_code` is **not** assigned to 1 (the `result_received and not result_is_error` warning branch).
- `logger.warning` line contains `"SDK post-ResultMessage exception (work completed)"` literal so grepping `callback-debug.log` for that string yields hits = false-fail-saved count.

---

### Task 2: Layer 2 — capture subprocess CLI stderr via public SDK callback

**Files:**
- `scripts/vps/claude-runner.py` (modify)
- `tests/integration/test_claude_runner_post_result_exception.py` (extend with case #4–#5)

**Steps:**

1. **Modify `scripts/vps/claude-runner.py`:**

   1.1. Before `options = ClaudeAgentOptions(...)` at line 114, initialize a line collector:

   ```python
       stderr_lines: list[str] = []

       def _stderr_collector(line: str) -> None:
           # Cap at 200 lines / ~50KB to bound memory on misbehaving CLI
           if len(stderr_lines) < 200:
               stderr_lines.append(line)
   ```

   1.2. Add to `ClaudeAgentOptions(...)` kwargs (around line 114-135):

   ```python
           stderr=_stderr_collector,
   ```

   1.3. In the `except Exception as e:` handler (modified in Task 1), enrich `err_str` with collected stderr **only if** `getattr(e, "stderr", None)` was empty (i.e., we're not duplicating `ProcessError.stderr`):

   ```python
           err_str = str(e)
           stderr_from_exc = getattr(e, "stderr", None)
           if stderr_from_exc:
               err_str = f"{err_str}\nSTDERR:\n{stderr_from_exc}"
           elif stderr_lines:
               captured = "\n".join(stderr_lines[-100:])  # last 100 lines
               err_str = f"{err_str}\nSTDERR (captured):\n{captured}"
   ```

   Same logic for the `except ProcessError as e:` block at line 216-223 — fallback to `stderr_lines` if `e.stderr` is empty.

2. **Extend test file** with two new tests:

   - `test_stderr_callback_captures_lines` — patch `query` with a generator that calls `options.stderr("line1\n")` / `options.stderr("line2\n")` via injected hook before raising. Assert `log_data["result_preview"]` contains "STDERR (captured)" + "line1" + "line2".
   - `test_process_error_stderr_takes_precedence` — generator raises `ProcessError("boom")` with `.stderr="real-stderr"`; also pushes lines through callback. Assert `result_preview` contains "real-stderr" but NOT "STDERR (captured)" (precedence).

**Test:**
- `test_stderr_callback_captures_lines` — proves Layer 2 fills the diagnostic gap noted in Why-2.
- `test_process_error_stderr_takes_precedence` — proves we don't duplicate stderr when SDK already exposed it.

**Acceptance:**
- Both new tests pass.
- `claude-runner.py` does NOT import any `_internal` module of `claude_agent_sdk` (monkey-patch ban — we use the public `stderr` callback only).
- Memory bound: at most 200 lines / ~50KB in `stderr_lines` regardless of CLI verbosity.

---

### Task 3: Layer 4 — `sdk_post_result_errors` table + `db.log_sdk_post_result_error()` helper

**Files:**
- `scripts/vps/schema.sql` (modify)
- `scripts/vps/db.py` (modify)
- `tests/integration/test_sdk_post_result_errors_telemetry.py` (NEW)

**Steps:**

1. **Modify `scripts/vps/schema.sql`** — append after the `callback_decisions` indexes (after line 88):

   ```sql
   -- BUG-188: SDK post-ResultMessage exception telemetry
   CREATE TABLE IF NOT EXISTS sdk_post_result_errors (
       id           INTEGER PRIMARY KEY AUTOINCREMENT,
       ts           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
       project_id   TEXT NOT NULL,
       task         TEXT NOT NULL,
       turns        INTEGER,
       cost_usd     REAL,
       error_msg    TEXT,
       stderr       TEXT
   );

   CREATE INDEX IF NOT EXISTS idx_sdk_post_result_errors_ts
       ON sdk_post_result_errors(ts);
   ```

2. **Modify `scripts/vps/db.py`:**

   2.1. Extend `_ensure_migrations()` (lines 23-61). After the existing `callback_decisions` CREATE block (line 60), add an idempotent CREATE for the new table — same defensive pattern (`try: ... except OperationalError: pass`):

   ```python
       # BUG-188: sdk_post_result_errors table for SDK post-ResultMessage diagnostics
       try:
           conn.execute(
               "CREATE TABLE IF NOT EXISTS sdk_post_result_errors ("
               "id INTEGER PRIMARY KEY AUTOINCREMENT,"
               "ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),"
               "project_id TEXT NOT NULL,"
               "task TEXT NOT NULL,"
               "turns INTEGER,"
               "cost_usd REAL,"
               "error_msg TEXT,"
               "stderr TEXT"
               ")"
           )
           conn.execute(
               "CREATE INDEX IF NOT EXISTS idx_sdk_post_result_errors_ts "
               "ON sdk_post_result_errors(ts)"
           )
       except sqlite3.OperationalError:
           pass
   ```

   This ensures **existing VPS instances** auto-migrate on first `get_db()` call — no manual ALTER required.

   2.2. After `clear_decisions()` (around line 299), add the helper:

   ```python
   def log_sdk_post_result_error(
       project_id: str,
       task: str,
       turns: int,
       cost_usd: float,
       error_msg: str,
       stderr: Optional[str],
   ) -> int:
       """Record a post-ResultMessage SDK exception (BUG-188).

       Called by claude-runner.py when `result_received and not result_is_error`
       branch fires. Threshold (>5/day) is a downstream concern (operator alert).
       """
       with get_db() as conn:
           cursor = conn.execute(
               "INSERT INTO sdk_post_result_errors "
               "(project_id, task, turns, cost_usd, error_msg, stderr) "
               "VALUES (?, ?, ?, ?, ?, ?)",
               (project_id, task, turns, float(cost_usd or 0.0), error_msg, stderr),
           )
           return cursor.lastrowid or 0
   ```

3. **Write `tests/integration/test_sdk_post_result_errors_telemetry.py`** (NEW, ~80 LOC):

   - `test_log_sdk_post_result_error_inserts_row` — call helper with a tmp DB (set `DB_PATH` env), SELECT * back, assert row matches.
   - `test_table_auto_created_on_first_call` — point `DB_PATH` to a fresh empty file (just `schema.sql` not loaded), call helper, assert no exception + row inserted (proves `_ensure_migrations` self-heals).
   - `test_stderr_column_nullable` — call with `stderr=None`, assert row inserted, `stderr IS NULL`.

**Test:**
- `tests/integration/test_sdk_post_result_errors_telemetry.py::test_table_auto_created_on_first_call` — guarantees no manual SQL ALTER required on prod VPS.

**Acceptance:**
- 3 tests pass.
- `python3 -c "from scripts.vps.db import log_sdk_post_result_error; print(log_sdk_post_result_error.__doc__)"` works (importable).
- `sqlite3 orchestrator.db ".schema sdk_post_result_errors"` shows the table after first helper call.

---

### Task 4: Wire claude-runner.py to log_sdk_post_result_error on post-result Exception

**Files:**
- `scripts/vps/claude-runner.py` (modify)
- `tests/integration/test_claude_runner_post_result_exception.py` (extend)

**Steps:**

1. **Modify `scripts/vps/claude-runner.py`:**

   1.1. At top, add lazy import (db is in the same dir):

   ```python
   try:
       import db as _orch_db
   except ImportError:
       _orch_db = None  # tests/CI without VPS deps run runner without telemetry
   ```

   1.2. In the `except Exception` handler (modified in Task 1+2), inside the `if result_received and not result_is_error:` branch, after `logger.warning(...)`, add:

   ```python
               if _orch_db is not None:
                   try:
                       _orch_db.log_sdk_post_result_error(
                           project_id=project_name,
                           task=task,
                           turns=turns,
                           cost_usd=cost_usd,
                           error_msg=str(e)[:2000],
                           stderr=("\n".join(stderr_lines[-100:]) or None) if stderr_lines else None,
                       )
                   except Exception as log_exc:
                       # Telemetry must never break the runner.
                       logger.warning("Failed to log sdk_post_result_error: %s", log_exc)
   ```

2. **Extend `tests/integration/test_claude_runner_post_result_exception.py`** with one more test:

   - `test_post_result_exception_logs_telemetry_row` — same setup as case #1 (post-result Exception) but with `DB_PATH` pointed at a tmp file. After `run_task` returns, SELECT from `sdk_post_result_errors` — assert exactly 1 row matching `project=<tmp>, turns=43, cost_usd≈6.32`.

**Test:**
- `test_post_result_exception_logs_telemetry_row` — closes the loop from Layer 1 to Layer 4.

**Acceptance:**
- New test passes alongside Task 1's 4 tests and Task 2's 2 tests (7 total in `test_claude_runner_post_result_exception.py`).
- Manual smoke: `DB_PATH=/tmp/x.db python3 -c "import asyncio; from scripts.vps.claude_runner import ..."` — telemetry insert visible in `/tmp/x.db`.

---

### Task 5: Layer 3 — autopilot SKILL.md early-exit instruction (both .claude/ and template/)

**Files:**
- `.claude/skills/autopilot/SKILL.md` (modify)
- `template/.claude/skills/autopilot/SKILL.md` (modify)

**Steps:**

1. **Modify `.claude/skills/autopilot/SKILL.md`** — locate the "## Pre-flight Check" section (lines 176-196). After step 1 (`Status: Must be queued or resumed`), insert a new step 2 (renumber existing 2/3 to 3/4):

   ```markdown
   2. **Already-implemented detection (BUG-188):** Before invoking the Plan Agent,
      check whether the spec's `## Allowed Files` already have implementation commits.

      **Algorithm (LLM-driven, run in current session via Bash tool):**

      a. Read `## Allowed Files` from the spec body. Extract every backticked
         path under a `<!-- callback-allowlist v1 -->` marker (canonical) or any
         backticked path inside the section (legacy fallback). Mirrors
         `callback._parse_allowed_files`.

      b. Get spec file creation time:
         ```bash
         SPEC_CREATED=$(git log --reverse --format=%ai -- "ai/features/${SPEC_ID}"*.md | head -1)
         ```

      c. Check whether any commit since `SPEC_CREATED` (on any branch) both:
         - has `${SPEC_ID}` in its **subject line** (first line) — canonical form,
           e.g. `feat(BUG-188): ...` or `BUG-188 ...`
         - AND touches at least one path in Allowed Files

         ```bash
         git log --all --since="$SPEC_CREATED" --pretty="%h %s" -- $ALLOWED_FILES \
           | grep -E "^[a-f0-9]+ (feat|fix|chore|docs|refactor|test)?\(?${SPEC_ID}\)?[: ]" \
           | head -5
         ```

      d. If 1+ qualifying commits found → **early-exit immediately**:
         - Do NOT dispatch Plan Agent.
         - Do NOT run any tasks.
         - Emit final JSON:
           ```json
           {
             "task_status": "complete",
             "result_preview": "BUG-188 early-exit: spec already implemented in commits {short_hashes}. No re-execution needed."
           }
           ```
         - Exit.

      **Why:** This mirrors `callback._spec_has_merged_implementation` (TECH-176)
      on the **front side** so autopilot does not burn 30+ turns re-doing work that
      callback would auto-close anyway. Saves ~$5/run × every false-fail retry.

      **False-skip protection:** the subject-line regex requires canonical
      `<type>(SPEC-ID):` or `SPEC-ID ` prefix. Bare mentions in commit body /
      cross-references in `Refs:`/`See also:` lines do NOT count (TECH-177 lesson).

   3. **Plan:** Must have `## Implementation Plan` (after PHASE 1)
   4. If plan missing after PHASE 1 → set `blocked`, skip spec
   ```

2. **Apply same change to `template/.claude/skills/autopilot/SKILL.md`** — same "Pre-flight Check" section structure. The two files differ in "Loop Mode" and "Context Management" wording, but Pre-flight Check is structurally identical, so the same diff applies cleanly.

**Test:**
- LLM-Judge eval (spec test #9): a separate review pass over both modified SKILL.md files asks: "Could this instruction cause an autopilot to skip a spec whose work is NOT yet done?" — pass criterion: no.
- Manual sanity: `grep -c "Already-implemented detection" .claude/skills/autopilot/SKILL.md template/.claude/skills/autopilot/SKILL.md` == 2.

**Acceptance:**
- Both SKILL.md files contain the new step 2 block.
- The block explicitly cites TECH-176 / TECH-177 (canonical subject-line regex).
- No code changes — pure prompt update.

---

### Task 6: Documentation — ADR + dependencies update

**Files:**
- `.claude/rules/architecture.md` (modify)
- `.claude/rules/dependencies.md` (modify)

**Steps:**

1. **Modify `.claude/rules/architecture.md`** — append a new row to the ADR table (after ADR-023):

   ```markdown
   | ADR-024 | **claude-runner exit_code contract.** Once `ResultMessage(is_error=False)` is received, the run is considered successful regardless of subsequent SDK exceptions. Post-result exceptions are logged as WARNING (not ERROR) and recorded in `sdk_post_result_errors` for diagnostics, but do NOT override `exit_code=0`. Symmetric front-side guard: autopilot early-exits if Allowed Files have implementation commits newer than spec creation date (mirrors callback `_spec_has_merged_implementation`). | 2026-05 | BUG-188 — false-fail on post-ResultMessage Exception burned $258/week on retries. See spec for trace. |
   ```

2. **Modify `.claude/rules/dependencies.md`:**

   2.1. Update the `scripts/vps/claude-runner.py` "Uses" table — add row:

   ```markdown
   | claude_agent_sdk.ClaudeAgentOptions.stderr | claude_agent_sdk 0.1.63 | public stderr line callback (BUG-188 Layer 2) |
   | db.py | scripts/vps/db.py | log_sdk_post_result_error() (BUG-188 Layer 4) |
   ```

   2.2. Update `scripts/vps/db.py` "Used by" table — add `claude-runner.py` row for `log_sdk_post_result_error()`.

   2.3. Append to `## Last Update`:

   ```markdown
   | 2026-05-20 | BUG-188: claude-runner.py result_received/result_is_error tracking + post-result exception preservation; SDK stderr callback wiring; sdk_post_result_errors table (db.py + schema.sql); autopilot SKILL.md early-exit step | autopilot |
   ```

**Test:**
- `grep -c "ADR-024" .claude/rules/architecture.md` == 1.
- `grep -c "BUG-188" .claude/rules/dependencies.md` >= 3 (claude-runner Uses + db Used by + Last Update).

**Acceptance:**
- ADR-024 row present and references BUG-188.
- `dependencies.md` reflects the new claude-runner → db.py edge.
- `Last Update` row dated 2026-05-20.

---

### Execution Order

```
Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6
       (sequential; T2 builds on T1 in same file;
        T4 needs T1 flags + T3 helper;
        T5 independent but ordered last among code tasks;
        T6 = docs after everything compiles & tests pass)
```

**Commit policy:** one task = one commit. Run `./test fast` before each commit
(at minimum the new test file for that task). The full integration suite runs
in Phase 3.

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
- `tests/integration/test_sdk_post_result_errors_telemetry.py` — NEW: Layer 4 telemetry test (replaces test_autopilot_early_exit.py because Layer 3 is pure prompt — no code, see plan)
- `.claude/rules/architecture.md` — append note about claude-runner exit_code contract
- `.claude/rules/dependencies.md` — update claude-runner.py edges (BUG-188 Layer 2/4)

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
