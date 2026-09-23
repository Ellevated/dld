# Feature: [TECH-224] Hermes будится по вердикту lifecycle, а не по коду выхода pueue

**Priority:** P1 | **Date:** 2026-09-23 | **Risk:** R1 (callback — порядок шагов единственного писателя статуса)
**Size:** 6 tasks / 9 files.

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

Hermes узнаёт о результате прогона из события, которое пишет callback. Событие пишется из
**кода выхода процесса**, а вердикт по спеке callback выносит позже:

- `callback.py:307-316` — Step 5 `write_event_for_skill(project_path, skill, status, task_label)`,
  где `status` = `map_result(...)` от pueue;
- `callback.py:332-362` — Step 7 `verify_status_sync(...)` уже после этого может перевести спеку
  `in_progress → blocked` (`autopilot_signaled_blocked`, `branch_pushed_not_merged:N ahead`).

Факт 23.09 (`scripts/vps/logs/hermes-wake.log`, `callback-debug.log`):

| Спека | Вердикт callback | Что получил Hermes | Что ответил Hermes |
|---|---|---|---|
| dowry TECH-526 | 15:48:25 `in_progress → blocked (autopilot_signaled_blocked)` | 12:48:20Z `dowry autopilot done` | «Обычное успешное завершение… сообщение в Telegram не отправлял» |
| dowry BUG-523 | 16:46:50 `in_progress → blocked (autopilot_signaled_blocked)` | 13:46:44Z `dowry autopilot done` | «Рядовое успешное завершение… В Telegram ничего не отправлял» |

Хуже: `write_event_for_skill` (`callback.py:190-194`) для автопилота пишет событие **только при
`status == "done"`**. Упавший автопилот (таймаут, exit≠0) не будит Hermes вообще. Блоки и падения —
ровно то, ради чего Hermes существует, — до основателя не доходят; 23.09 их разбирали руками в
интерактивных окнах.

Попутно: артефакт QA берётся как `sorted(p.glob("ai/qa/[0-9]*-*.md"))[-1]` (`callback.py:200`) —
последний **по имени**, не свежий и не свой. Имена QA — `ai/qa/{YYYY-MM-DD}-{area-slug}.md`
(`qa/SKILL.md:543`), в один день сортируются по слагу. Hermes 23.09 дважды получил
«qa-BUG-522 → артефакт FTR-282».

## Context

- Разбор суток: `C:\Users\Oleg\.claude\task-journal\2026-09-23-dld-orch24h.md`.
- Hermes будится снова только с 23.09 (`4e1f493`, `hermes -z`); до этого все пробуждения молча
  падали с 13.08 — поэтому дыра не была видна.
- Соседние спеки: TECH-223 (фон в headless), TECH-225 (распознать лимит подписки, **AFTER
  TECH-224** — правит тот же `callback.py`), TECH-226 (пауза флота до сброса лимита).

---

## Scope

**In scope:**
1. `verify_status_sync` возвращает свой вердикт `(status, reason)` вместо `None` там, где он его
   вынес; `None` — где вердикта нет (circuit open, нет lifecycle-записи, спека уже `done`).
2. Для `skill == "autopilot"` событие пишется **после** Step 7 и несёт вердикт: `done` или
   `blocked` + причина. Одно событие на прогон автопилота.
3. Автопилот, упавший с exit≠0, тоже будит Hermes (вердикт Step 7 для `status == "failed"`).
4. Если вердикта нет (Step 7 бросил исключение или вернул `None`) — событие всё равно пишется,
   со статусом pueue и пометкой «вердикт lifecycle недоступен: <почему>». Молчание — не вариант.
5. QA-артефакт: файл этой спеки (spec_id из `qa-<ID>` в имени, без учёта регистра), свежий по
   mtime; нет такого — самый свежий по mtime. Reflect — самый свежий по mtime.
6. Для `qa`/`reflect`/`spark` порядок не меняется: событие на месте Step 5.
7. `write_event_for_skill` переезжает в новый модуль `callback_event.py` (callback.py 371/400 —
   места под новую логику нет), в `callback.py` остаётся ре-экспорт (контракт TECH-216).

**Out of scope:**
- Текст пробуждения Hermes и его решение слать/не слать Telegram (`event_writer.wake_hermes`) — не
  меняются; Hermes получает правильный `status` и сам решает.
- Дедупликация и шум Hermes (одно пробуждение на прогон — как сейчас).
- Лимит подписки — TECH-225/226.

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
- `grep -rn "write_event_for_skill" scripts/vps tests` → определение `callback.py:190`, вызов
  `callback.py:314`; тестов нет (0 совпадений в `tests/`, `scripts/vps/tests/`).
- `grep -rn "verify_status_sync(" tests scripts/vps` → единственный продакшн-вызов
  `callback.py:354`; 20+ интеграционных тестов вызывают его и **не читают** возвращаемое значение
  (`grep -rn "= callback.verify_status_sync\|assert callback.verify_status_sync" tests` → 0) —
  добавление возврата обратно совместимо.
- `grep -rn "event_writer.notify" scripts/vps` → `callback.py:208`, `callback_sync.py:284`
  (rule_7_saved — не трогаем), `audit_digest.py:184` (не связан).

### Step 2: DOWN
- `event_writer.notify(project_path, skill, status, message, artifact_rel="")` — `event_writer.py:126-135`, сигнатура не меняется.
- `callback_sync._read_existing_status`, `_decide_status`, `_write_status` — `callback_sync.py:255-379`.

### Step 3: BY TERM
- `grep -rn "Step 5\|write_event_for_skill\|event_writer.notify → Hermes" docs/ .claude/rules/` →
  `docs/orchestrator/status-model.md:170` (таблица 7 шагов, текущий неверный порядок),
  `docs/orchestrator/README.md:112-127` (та же схема), `.claude/rules/dependencies.md` раздел callback.
- CI: `.github/workflows/test.yml:72-77` — `--cov` перечисляет модули callback по имени; новый
  `callback_event` надо добавить, иначе он выпадет из покрытия.

| File | Line | Status | Action |
|------|------|--------|--------|
| `scripts/vps/callback.py` | 190-214, 307-316, 332-362 | событие до вердикта; autopilot failed без события | modify |
| `scripts/vps/callback_sync.py` | 304-379 | `-> None` | modify (return verdict) |
| `.github/workflows/test.yml` | 72-77 | список `--cov` | modify |

### Step 4: CHECKLIST
- [x] `tests/**` — новый `tests/integration/test_callback_event_verdict.py` (харнес как в `test_callback_blocked_no_dispatch.py:158-190`: реальный git-репо, реальный lifecycle, `event_writer` перехвачен monkeypatch)
- [x] `scripts/vps/tests/` — новый `test_callback_event_artifact.py` (выбор артефакта)
- [x] `db/migrations/**` — N/A

### Verification
- [x] Все найденные файлы в Allowed Files
- [x] После спеки `grep -n "def write_event_for_skill" scripts/vps/callback.py` = 0 (переехала), `grep -n "write_event_for_skill" scripts/vps/callback.py` ≥ 1 (ре-экспорт + вызов)

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/callback_event.py` — write_event_for_skill + выбор артефакта + сборка события по вердикту (NEW)
- `scripts/vps/callback.py` — ре-экспорт, событие автопилота после Step 7, fallback без вердикта (modify, 371 LOC)
- `scripts/vps/callback_sync.py` — verify_status_sync возвращает (status, reason) | None (modify, 379 LOC)
- `tests/integration/test_callback_event_verdict.py` — main() end-to-end: блок/done/failed/нет вердикта (NEW)
- `scripts/vps/tests/test_callback_event_artifact.py` — выбор артефакта QA/reflect (NEW)
- `.github/workflows/test.yml` — `--cov=callback_event` (modify)
- `docs/orchestrator/status-model.md` — таблица шагов callback (modify)
- `docs/orchestrator/README.md` — схема шагов callback (modify)
- `.claude/rules/dependencies.md` — раздел callback: новый модуль, порядок событий (modify)

**LOC headroom:** `callback.py` 371/400 — после выноса `write_event_for_skill` (~25 строк) в
`callback_event.py` чистый прирост должен быть ≤ 0; `callback_sync.py` 379/400 — изменение ≤ 8
строк (сигнатура + 3–4 `return`), без новой логики внутри.

---

## Environment

nodejs: false
docker: false
database: true   # orchestrator SQLite через tmp_db фикстуру

---

## Blueprint Reference

N/A — в DLD нет `ai/blueprint/system-blueprint/`. Домен: callback оркестратора (`scripts/vps/`).

---

## Historical Risks

<!-- lessons-binding v1 -->

none — `ai/lessons/` пуст (только `.gitkeep`). Близкий прецедент в коде: `callback_sync.py:277-294`
(Rule 7 structural save шлёт своё событие) — его поведение не меняется.

---

## Approaches

### Approach 1: `verify_status_sync` возвращает вердикт; событие автопилота после Step 7
**Source:** research-codebase.md §Risks 1, research-devil.md §Argument 1 (Counter).
**Summary:** Вердикт возвращается тем, кто его вынес; событие строится из него.
**Pros:** нет второго чтения lifecycle (гонка с другим писателем исключена); NOOP-случаи явно
определены; обратно совместимо для 20+ тестов.
**Cons:** +несколько строк в `callback_sync.py` при запасе 21.

### Approach 2: после Step 7 перечитать `lifecycle.read_lifecycle()`
**Summary:** Не трогать `callback_sync`, прочитать статус из git после записи.
**Cons:** гонка «запись → чтение» с конкурирующим писателем (devil Hidden Coupling), и нет
причины блока (transitions не хранят `reason` на запись — research-devil EC-7).

### Selected: 1
**Rationale:** вердикт уже вычислен внутри `verify_status_sync`; вернуть его дешевле и точнее,
чем восстанавливать по косвенным признакам.

---

## Design

### Как сейчас
`callback.main()` (`callback.py:217-367`): Step 4 `extract_agent_output` → **Step 5 событие по
pueue-статусу** → Step 6 QA/reflect → **Step 7 вердикт** (только `skill == "autopilot" and status
in ("done","failed")`, `callback.py:333`). Каждый шаг в своём `try/except`, `main` всегда `exit 0`.

### Как будет
```
Step 4 extract_agent_output
Step 5 событие  — для qa / reflect / spark как раньше (callback_event.write_event_for_skill)
                  для autopilot — НЕ здесь
Step 6 QA/reflect dispatch — без изменений
Step 7 verdict = verify_status_sync(...)       # (status, reason) | None
Step 7b событие автопилота (свой try/except):
        verdict есть  → status = verdict.status ("done"/"blocked"), сообщение
                        "autopilot {status} for {label}: {reason}"
        verdict нет   → status = pueue-статус, сообщение
                        "autopilot {status} for {label} — вердикт lifecycle недоступен: {why}"
```
`why` — `"exception: <тип>"`, `"no_decision"` (verify вернул `None`), `"no_spec_id"`,
`"no_project_path"`. Событие автопилота пишется **ровно один раз** за вызов callback, в том числе
при `status == "failed"` и при падении Step 7.

`verify_status_sync` возвращает:
- `(new_status, reason or "ok")` после успешной записи (`callback_sync.py:370-379`);
- `(new_status, "already_correct")` на NOOP совпадения (`:353-358`);
- `("done", "rule_7_saved")` если `_write_status` поймал Rule 7 — сейчас `_write_status` возвращает
  `False` на обоих путях; различить через аудит нельзя без роста файла, поэтому на `False` вернуть
  `None` (событие скажет «вердикт недоступен»), а Rule 7 и так шлёт своё событие (`:284-290`);
- `None` там, где `_read_existing_status` вернул `None` (`:332-334`).

### Выбор артефакта (`callback_event.py`)
- `qa`: spec_id = `task_label` без префикса `qa-`; кандидаты `ai/qa/[0-9]*-*.md`, сначала те, чьё
  имя содержит spec_id (casefold), среди них — max по `st_mtime`; иначе max по `st_mtime` среди всех.
- `reflect`: `ai/reflect/findings-*.md`, max по `st_mtime` (как `callback_logs.py:44`).

### Database Changes
Нет.

---

## Drift Log

**Checked:** 2026-09-24 against `tech/TECH-224` @ `fc332771`. **Verdict: light drift, fixed in place.**

| # | Spec assumed | Reality | Action |
|---|---|---|---|
| D1 | `bash scripts/check-loc-limit.sh` | gate lives at `scripts/vps/check-loc-limit.sh` (`ci.yml:108`); `scripts/check-loc-limit.sh` does not exist | fixed in plan + Verify Command |
| D2 | harness `test_callback_blocked_no_dispatch.py:59-63, 158-190` | `stub_event_writer` is `:60-64`, `_run_main` is `:151-184`; the harness imports `unittest.mock.patch` (`:24`) — the pre-edit mockBan hook (`.claude/hooks/hooks.config.mjs:102-119`) blocks `unittest.mock` / `@patch` / `mock.patch` in any NEW `tests/integration/` file | new test uses pytest `monkeypatch` only (argv, exit, DB_PATH) |
| D3 | coverage of the new logic via `--cov=callback_event` | `callback.main()` is `# pragma: no cover` (`callback.py:217`) — any branching left in `main` is unmeasured | verdict→event branching lives in `callback_event.autopilot_event`, `main` only passes values |
| D4 | `callback.py` keeps using `event_writer` | its only use is `write_event_for_skill` (`:208`); after the move `import event_writer` (`:44`) is unused → ruff F401. 0 hits for `callback.event_writer` in tests | remove the import |
| D5 | `why = "no_project_path"` produces an event | no project path = no `pending-events/` destination; Step 5 already skips on empty path (`:313`) | log-only, no event; `why` values are `no_spec_id` / `no_decision` / `exception: <Type>` |
| D6 | `write_event_for_skill(..., reason="")` (old Task 2) | `autopilot_event` calls `event_writer.notify` directly — the extra param has no caller | signature stays 4-arg |
| D7 | `dependencies.md`: `callback_sync.py` 349 LOC | 379 before this spec | fixed in Task 6 |
| D8 | `scripts/vps/tests/test_callback_event_artifact.py` runs in CI | CI runs only 2 named files from `scripts/vps/tests/` (`ci.yml:99,109`) — EC-6/EC-7 are local-only gates | warning; `pick_artifact`'s qa path is also exercised in CI by EC-8 |
| D9 | AV-F1 greps `"<spec> autopilot blocked"` | `hermes-wake.log` header is `--- <iso> <project_id> <skill> <status>` (`event_writer.py:109`) — no spec id in it | AV-F1 grep fixed to `<project> autopilot blocked` |
| D10 | template sync for `.claude/rules/dependencies.md` | `rules/template-sync.md` declares root's map deliberately divergent; `template/` is outside Allowed Files | no sync task |

Confirmed unchanged: `callback.py` 371 LOC, `write_event_for_skill` `:190-214`, Step 5 `:307-316`,
Step 7 `:332-362` (`verify_status_sync(` call `:354`); `callback_sync.py` 379 LOC,
`verify_status_sync` `:304-379`, return points `:334` (no status), `:358` (NOOP), `:371`
(write failed); `test.yml` `--cov` list `:72-77`; `status-model.md:164-172`; `README.md:117-128`.
No caller reads `verify_status_sync`'s return (grep for `= …verify_status_sync(` → 0) —
adding one is backward compatible for the 66 call sites in 14 files.

---

## Implementation Plan

### Research Sources
- `scripts/vps/callback_logs.py:44` — mtime selection idiom (`key=lambda f: f.stat().st_mtime`)
- `tests/integration/test_callback_blocked_no_dispatch.py:43-184` — `main()` harness (fixtures, `_make_project`, `_seed_db`, `_run_main`)
- `tests/integration/conftest.py:28-72` — `stub_pueue_bin`
- `scripts/vps/tests/test_orchestrator_in_progress.py:347-363` — real-origin pushed-not-merged setup + `callback_sync.time.sleep` patch
- No external research: stdlib + in-repo patterns only.

### Task 1: Failing end-to-end tests for the autopilot event

**Type:** test
**Files:**
- Create: `tests/integration/test_callback_event_verdict.py`

**Context:** Proves the 23.09 failure (Hermes told "done" on a block, nothing on a crash) against the real `callback.main()`, real git, real sqlite.

**Harness (constraints, not code):**
- Copy `_make_project` / `_seed_db` from `test_callback_blocked_no_dispatch.py:78-148`; `_make_project` gains `with_lifecycle: bool = True` (EC-5 commits no yaml); `_seed_db` takes `skill`.
- `tmp_db`: as `:43-53` but `monkeypatch.setattr(db, "DB_PATH", …)` and `monkeypatch.setattr(db, "_MIGRATIONS_APPLIED", False)`. **No `unittest.mock` import anywhere in the file** (D2).
- `wakes` fixture: `monkeypatch.setattr(event_writer, "wake_hermes", recorder)` where the recorder appends `(skill, status, event_file)` and returns True. `event_writer.write_event` runs for real — assertions read the JSON it wrote. Helper `_events(wakes, skill) -> list[dict]`.
- `_run_main(monkeypatch, pueue_id, result, exit_code, skill, task_status, merged)`: patch `callback.extract_agent_output` → `(skill, "", task_status)`; `gate_logic.fetch_develop` → True; `gate_logic.find_implementation_commit` → `"deadbee" if merged else None`; `callback_sync.time.sleep` → no-op; `sys.argv` = `["callback.py", id, "claude-runner", result]` + `[exit_code]` if given; `sys.exit` → no-op; call `callback.main()`.
- Every test uses `stub_pueue_bin` (conftest). Project dir name == `project_id` (`verify_status_sync` derives it from the path).

**Tests (one line each — name → assertion):**
- EC-1 `test_ec1_signaled_blocked_wakes_blocked` — Success, `task_status="blocked"`, merged → exactly 1 autopilot event, `status == "blocked"`, `"autopilot_signaled_blocked" in message`. Red today: status is `done`.
- EC-2 `test_ec2_done_wakes_once_done` — Success, `"complete"`, merged → exactly 1 autopilot event, `status == "done"`. Green today (regression guard).
- EC-3 `test_ec3_failed_run_pushed_branch_wakes_blocked` — real bare origin (`git init --bare`, push `develop`, branch `tech/<ID>` with 1 commit touching `src/x.py` pushed, back on `develop`); argv `Failed` + `"124"`, `task_status=""`, not merged → exactly 1 autopilot event, `status == "blocked"`, `"branch_pushed_not_merged" in message`. Red today: 0 events.
- EC-4 `test_ec4_step7_raises_still_wakes` — Success, `"complete"`, `monkeypatch.setattr(callback, "verify_status_sync", <raises RuntimeError>)` → `main()` returns, exactly 1 autopilot event, `status == "done"`, `"вердикт lifecycle недоступен: exception: RuntimeError" in message`. Red today.
- EC-5 `test_ec5_no_lifecycle_record_wakes_no_decision` — `with_lifecycle=False`, Success, `"complete"`, merged → exactly 1 autopilot event, `"no_decision" in message`. Red today.
- EC-8 `test_ec8_qa_event_is_step5_only` — task_label `qa-<ID>`, skill `qa`, Success; `callback.verify_status_sync` replaced by a call recorder → recorder empty, `len(wakes) == 1`, that wake is `("qa", "done", …)`. Green today (regression guard).

**Run:** `pytest tests/integration/test_callback_event_verdict.py -v` → `4 failed, 2 passed` (EC-1, EC-3, EC-4, EC-5 fail).

**Acceptance:** EC-1, EC-2, EC-3, EC-4, EC-5, EC-8 written; the four red ones fail on the assertion, not on a harness error.

### Task 2: `verify_status_sync` returns its verdict

**Type:** code
**Files:**
- Modify: `scripts/vps/callback_sync.py:19-20, 304-379`

**Context:** The verdict already exists inside the gate; returning it avoids a second, racy lifecycle read (Approach 1).

**Steps:**
- `:310` → `-> tuple[str, str] | None:`; docstring (`:311-327`) gains one line: returns `(status, reason)` it wrote or found in place, `None` when it reached no verdict.
- `:334` → `return None` (circuit open / no lifecycle / already done).
- `:358` → `return new_status, "already_correct"`.
- `:371` → `return None` (Rule 7 save or write error — `_write_status` does not tell them apart; Rule 7 sends its own event at `:283-290`).
- after `audit.emit(...)` `:375-379` → `return new_status, reason or "ok"`.
- `:19-20` module docstring: "keeps its name, signature and return" → name and signature; returns the verdict since TECH-224.
- Must NOT change: any decision, audit line, `_record`/`note_demote` call, `_write_status`, `_decide_status`.

**Run:** `pytest tests/unit/test_callback_*.py tests/integration/test_callback_*.py tests/regression/ scripts/vps/tests/test_callback.py -q` → all pre-existing pass; Task 1's four still red (main ignores the return). `wc -l scripts/vps/callback_sync.py` ≤ 383.

**Acceptance:** Flow step 2; no existing test edited.

### Task 3: Failing tests for artifact selection

**Type:** test
**Files:**
- Create: `scripts/vps/tests/test_callback_event_artifact.py`

**Context:** Hermes got "qa-BUG-522 → FTR-282 artifact" because selection is by name (`callback.py:200`). `scripts/vps/tests/conftest.py:11-13` puts `scripts/vps` on `sys.path`; set mtimes with `os.utime`.

**Tests:**
- EC-6 `test_ec6_qa_picks_own_spec_file` — `ai/qa/2026-09-23-bug-520-a.md` (older) + `ai/qa/2026-09-23-zzz-other.md` (newer) → `callback_event.pick_artifact(p, "qa", "qa-BUG-520") == "ai/qa/2026-09-23-bug-520-a.md"`; and `pick_artifact(p, "qa", "qa-BUG-52")` returns the zzz file (id must not match as a digit prefix).
- EC-7 `test_ec7_qa_falls_back_to_newest_mtime` — `…-aaa.md` newer than `…-zzz.md`, label `qa-BUG-999` → returns the `aaa` file.

**Run:** `pytest scripts/vps/tests/test_callback_event_artifact.py -v` → 2 errors (`ModuleNotFoundError: callback_event`).

**Acceptance:** EC-6, EC-7 written and red.

### Task 4: `callback_event.py` + autopilot event after the verdict

**Type:** code
**Files:**
- Create: `scripts/vps/callback_event.py` (~70 LOC)
- Modify: `scripts/vps/callback.py:11-13, 38-45, 186-214, 307, 332-362`

**Context:** One autopilot event per run carrying the lifecycle verdict; qa/reflect/spark unchanged in timing.

**`callback_event.py`** — header docstring in the sibling style (`callback_logs.py:1-17`); `SCRIPT_DIR` + `sys.path.insert` + `import event_writer  # noqa: E402`; calls `event_writer.notify` as a module attribute (tests patch `event_writer.wake_hermes`).
- `pick_artifact(project_path: str, skill: str, task_label: str) -> str` — `qa`: spec id = `task_label.removeprefix("qa-")`; candidates `ai/qa/[0-9]*-*.md`; own = names containing the id case-insensitively and NOT followed by a digit; pool = own or all; max by `st_mtime`. `reflect`: `ai/reflect/findings-*.md`, max by `st_mtime`. Anything else or no file → `""`. Returns the path relative to `project_path`.
- `write_event_for_skill(project_path: str, skill: str, status: str, task_label: str) -> None` — body of `callback.py:190-214` moved, two changes only: skill tuple becomes `("qa", "reflect", "spark")` (autopilot's event is `autopilot_event`; docstring says so) and artifact comes from `pick_artifact`. Status gate (`:194`) unchanged.
- `autopilot_event(project_path: str, task_label: str, pueue_status: str, verdict: tuple[str, str] | None, why: str) -> None` — verdict → `notify(path, "autopilot", verdict[0], f"autopilot {verdict[0]} for {task_label}: {verdict[1]}")`; None → `notify(path, "autopilot", pueue_status, f"autopilot {pueue_status} for {task_label} — вердикт lifecycle недоступен: {why}")`. No artifact.

**`callback.py`:**
- `:38-45` — add `import callback_event  # noqa: E402  — Hermes events (TECH-224)` in isort order (after `callback_dispatch`); delete `import event_writer` (D4). `:13` docstring `event_writer: …` → `callback_event: write_event_for_skill, autopilot_event (TECH-224)`.
- `:190-214` — delete the def; next to `:186-187` add `write_event_for_skill = callback_event.write_event_for_skill` (TECH-216 re-export contract; `main` keeps calling it by bare name).
- `:307` — comment: Step 5 is qa/reflect/spark; autopilot's event is Step 7b. Code `:308-316` unchanged.
- Step 7 `:332-362` — inside the existing `if skill == "autopilot" and status in ("done", "failed"):` set `verdict, why = None, "no_spec_id"` before the `try`; capture `verdict = verify_status_sync(...)` (`:354`) followed by `why = "no_decision"`; in the `except` add `why = f"exception: {type(exc).__name__}"`.
- Step 7b — after that `except`, same `if` block, own `try/except Exception` (log.warning): `if project_path: callback_event.autopilot_event(project_path, task_label, status, verdict, why)`.
- Invariants: exactly one `notify(skill="autopilot")` per `main()`; Step 6 untouched; `main` still always exits 0; `callback.py` ends ≤ 371 LOC (net ≤ 0), hard cap 400.

**Run:**
- `pytest tests/integration/test_callback_event_verdict.py scripts/vps/tests/test_callback_event_artifact.py -v` → `8 passed`
- `pytest tests/ scripts/vps/tests/ -q` → green (with `scripts/vps/requirements.txt` installed)
- `bash scripts/vps/check-loc-limit.sh` → exit 0
- `cd scripts/vps && python3 -c "import callback; print(callback.write_event_for_skill.__module__)"` → `callback_event` (AV-S1)
- `grep -n "def write_event_for_skill" scripts/vps/callback.py` → 0 hits; `grep -n "write_event_for_skill" scripts/vps/callback.py` → ≥ 2
- `ruff check scripts/vps tests && ruff format --check scripts/vps tests` (ruff 0.16.1)

**Acceptance:** Task 1 and Task 3 tests green; DoD Functional (blocked + reason reaches Hermes, one event per autopilot run, QA artifact is its own spec's); AV-S1.

### Task 5: CI coverage + orchestrator docs

**Type:** code (ci/docs)
**Files:**
- Modify: `.github/workflows/test.yml:62-64, 72-77`
- Modify: `docs/orchestrator/status-model.md:164-176`
- Modify: `docs/orchestrator/README.md:117-128`

**Steps:**
- `test.yml` — add `--cov=callback_event \` after `--cov=callback_dispatch` (`:74`); comment `:62-64` "six modules" → seven.
- `status-model.md` — row 5 → `callback_event.write_event_for_skill` → Hermes, qa/reflect/spark only; row 7 → `verify_status_sync` → status write, returns `(status, reason)` | None; new row 7b → `callback_event.autopilot_event` → Hermes: status = Step 7 verdict (done / blocked + reason), without a verdict the pueue status + «вердикт lifecycle недоступен: <why>»; exactly one event per autopilot run, exit≠0 included (TECH-224). `:176` signature line gains the return type.
- `README.md` — same three changes in the step list `:122-128`.

**Acceptance:** `grep -n "callback_event" .github/workflows/test.yml` ≥ 1; `grep -n "7b" docs/orchestrator/status-model.md docs/orchestrator/README.md` ≥ 1 each.

### Task 6: Dependency map

**Type:** code (docs)
**Files:**
- Modify: `.claude/rules/dependencies.md:327-349, 358, 434`

**Steps:** `:329-330` callback.py LOC → post-Task-4 `wc -l`; `:332-334` "five flat siblings" → six, `write_event_for_skill` listed as a re-export; module table `:337-342` gains `callback_event.py` | LOC | `pick_artifact`, `write_event_for_skill`, `autopilot_event` (TECH-224) and `callback_sync.py` LOC 349 → actual (D7); `:349` "all six modules" → seven; `:358` event_writer row → via `callback_event`; `:434` event_writer "Used by" `callback.py` → `callback_event.py` (+ `callback_sync.py` Rule 7 save).

**Acceptance:** `grep -c "callback_event" .claude/rules/dependencies.md` ≥ 3; no sync task (D10).

### Execution Order

1 → 2 → 3 → 4 → 5 → 6. Task 2 needs Task 1 in place (it must leave those tests red for the right reason); Task 4 depends on 2 (return value) and 3 (EC-6/7 contract); Tasks 5–6 depend on 4 (final module name and LOC). One commit per task.

**Эксперимент не заводится:** это исправление доставки уведомления, а не изменение того, как
прогоны флота исполняются (промпт, модель, конфиг раннера, политика диспатча). Проверка —
детерминированные EC-1..EC-8 и AV-F1 на первом блоке после выкатки.

---

## Flow Coverage Matrix (REQUIRED)

| # | Шаг | Covered by Task | Status |
|---|-----|-----------------|--------|
| 1 | pueue завершил autopilot, callback стартовал | - | existing |
| 2 | Step 7 выносит вердикт и возвращает его | Task 2 | ✓ |
| 3 | Событие автопилота по вердикту (done / blocked + причина) | Task 1, 4 | ✓ |
| 4 | Упавший автопилот тоже будит Hermes | Task 1, 4 | ✓ |
| 5 | Нет вердикта → событие с пометкой, не тишина | Task 1, 4 | ✓ |
| 6 | QA/reflect получают свой артефакт | Task 3, 4 | ✓ |
| 7 | Hermes читает событие и решает про Telegram | - | existing |

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Автопилот сигналит blocked | pueue Success, `task_status=blocked` в run-логе, гейт видит мерж | ровно одно событие: `skill=autopilot`, `status=blocked`, в сообщении `autopilot_signaled_blocked` | deterministic | incident TECH-526/BUG-523 | P0 |
| EC-2 | Штатный done | pueue Success, `task_status=complete`, ветка слита | одно событие `status=done` | deterministic | regression | P0 |
| EC-3 | Упавший автопилот | pueue Failed (exit 124), ветка запушена, не слита | одно событие `status=blocked`, в сообщении `branch_pushed_not_merged` (раньше событий 0) | deterministic | callback.py:193 | P0 |
| EC-4 | Step 7 бросил исключение | `verify_status_sync` поднимает `RuntimeError` | одно событие со статусом pueue и текстом «вердикт lifecycle недоступен: exception: RuntimeError»; `main` exit 0 | deterministic | devil Argument 1 | P0 |
| EC-5 | Нет вердикта | lifecycle-записи спеки нет (`verify_status_sync` → `None`) | одно событие с пометкой `no_decision` | deterministic | callback_sync.py:332-334 | P1 |
| EC-6 | Свой QA-артефакт | `ai/qa/2026-09-23-bug-520-a.md` (старше) и `2026-09-23-zzz-other.md` (новее), label `qa-BUG-520` | `artifact_rel` = файл bug-520 | deterministic | Hermes «FTR-282» | P1 |
| EC-7 | Нет файла спеки | два QA-файла без spec_id в имени, у «a…» mtime новее, чем у «z…» | выбран «a…» (по mtime, не по имени) | deterministic | callback.py:200 | P1 |
| EC-8 | QA/reflect не ждут Step 7 | skill `qa`, pueue Success | событие пишется, Step 7 не вызывается; число событий = 1 | deterministic | regression | P1 |

### Coverage Summary
- Deterministic: 8 | Integration: 0 (EC-1..EC-5, EC-8 — через реальный `callback.main()` и git) | LLM-Judge: 0 | Total: 8

### TDD Order
1. EC-1, EC-3 → FAIL на текущем коде → Task 1–2 → PASS
2. EC-4, EC-5, EC-2, EC-8
3. EC-6, EC-7

---

## Acceptance Verification (MANDATORY)

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | callback импортируется и ре-экспорт жив | `cd ~/projects/dld/scripts/vps && venv/bin/python3 -c "import callback; print(callback.write_event_for_skill.__module__)"` | `callback_event`, exit 0 | 30s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Первый блок автопилота после выкатки | любой прогон, который callback переведёт в `blocked` | `grep -A3 "<project> autopilot blocked" ~/projects/dld/scripts/vps/logs/hermes-wake.log` | строка события со `status=blocked` и ответ Hermes, не «рядовое успешное завершение» |

### Verify Command (copy-paste ready)

```bash
pip install -r scripts/vps/requirements.txt
pytest tests/integration/test_callback_event_verdict.py scripts/vps/tests/test_callback_event_artifact.py -v
pytest tests/ scripts/vps/tests/ -q
bash scripts/vps/check-loc-limit.sh
ruff check . && ruff format --check .
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] Блок и падение автопилота доходят до Hermes со статусом `blocked` и причиной
- [ ] Ровно одно событие на прогон автопилота
- [ ] QA-событие указывает на артефакт своей спеки
- [ ] All tasks from Implementation Plan completed

### Tests
- [ ] EC-1..EC-8 pass
- [ ] `pytest tests/ scripts/vps/tests/ -q` зелёные (с `scripts/vps/requirements.txt`)

### Acceptance Verification
- [ ] AV-S1 pass; AV-F1 — на первом блоке после выкатки (записать в Autopilot Log)

### Technical
- [ ] ruff 0.16.1 check + format
- [ ] LOC-гейт exit 0 (`callback.py`, `callback_sync.py` ≤ 400)
- [ ] No regressions

---

## Autopilot Log
[Auto-populated by autopilot during execution]
