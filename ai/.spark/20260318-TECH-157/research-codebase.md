# Codebase Research — Add Immediate OpenClaw Wake After Pending-Event Write

## Existing Code

### Reusable Modules

| Module | File:line | Description | Reuse how |
|--------|-----------|-------------|-----------|
| `$CALLBACK_LOG` redirect pattern | scripts/vps/pueue-callback.sh:275 | `2>>"$CALLBACK_LOG" \|\| { echo WARN ... }` — fail-safe stderr redirect to log | Use identical pattern for wake call |
| `\|\| true` fail-safe wrapper | scripts/vps/pueue-callback.sh:102,117 | Every risky op wrapped with `\|\| true` to keep callback non-fatal | Wrap `openclaw system event` with `\|\| true` |
| `command -v` guard pattern | scripts/vps/pueue-callback.sh:113 | `if command -v pueue &>/dev/null` — check binary before calling | Apply same guard for `openclaw` |

### Similar Patterns

| Pattern | File:line | Description | Similarity |
|---------|-----------|-------------|------------|
| notify.py fail-safe call | scripts/vps/pueue-callback.sh:273-281 | Calls external Python script with `\|\|` error handler and `$CALLBACK_LOG` redirect | Identical structure for openclaw wake call |
| pueue dispatch with `&>/dev/null` | scripts/vps/pueue-callback.sh:369-375 | `pueue add ... 2>/dev/null && { echo OK } \|\| { echo WARN }` | Optional verbosity pattern |
| PATH prepend for venv | scripts/vps/pueue-callback.sh:52 | `export PATH="${SCRIPT_DIR}/venv/bin:$PATH"` — ensures local binaries resolve | openclaw lives in `~/.npm-global/bin`, which is in PATH via `.bashrc` but may not be in systemd environment |

**Recommendation:** Use `command -v openclaw` guard + `openclaw system event --mode now` (not `gateway wake` — that subcommand does not exist). Wrap with `2>>"$CALLBACK_LOG" || true`. Inject `~/.npm-global/bin` into PATH at callback init if not already present.

---

## Critical Finding: Wrong CLI Command in Inbox Spec

**The inbox spec (`20260318-openclaw-wake-on-cycle-complete.md`) specifies:**
```bash
openclaw gateway wake --mode now
```

**This command does NOT exist.** `openclaw gateway` has no `wake` subcommand (verified against installed version 2026.3.13).

**The correct command is:**
```bash
openclaw system event --mode now
```

`openclaw system event` accepts `--mode (now|next-heartbeat)` and triggers a heartbeat/wake cycle on the running gateway.

**Binary location:** `/home/dld/.npm-global/bin/openclaw`
**PATH in systemd:** `.bashrc` exports `~/.npm-global/bin:$PATH` but systemd units do not source `.bashrc`. The callback must either use the full path or prepend `~/.npm-global/bin` to PATH.

---

## Impact Tree Analysis

### Step 1: UP — Who uses changed code?

```bash
grep -r "pueue-callback" . --include="*.sh" --include="*.yml" --include="*.md"
# Results: 6 files
```

| File | Line | Usage |
|------|------|-------|
| scripts/vps/setup-vps.sh | pueue.yml template | Registered as pueue callback via `callback: "...pueue-callback.sh {{ id }} '{{ group }}' '{{ result }}'"` |
| scripts/vps/db.py | header comment | Listed as dependent (CLI: `python3 db.py callback`) |
| .claude/rules/dependencies.md | 79 | Documents pueue-callback.sh in dependency graph |
| ai/.spark/20260318-TECH-156/research-devil.md | 7, 25, 94-96 | References Step 6.8 line numbers specifically |
| ai/.spark/20260318-tech-xxx/research-codebase.md | multiple | References pueue-callback.sh in impact tree |
| ai/inbox/done/20260318-openclaw-wake-on-cycle-complete.md | 10-15 | Source inbox spec for this feature (already processed) |

### Step 2: DOWN — What does it depend on?

| Dependency | File | Function |
|------------|------|----------|
| db.py | scripts/vps/db.py | `get_project_state(project_id)` — lookup project path |
| notify.py | scripts/vps/notify.py | `python3 notify.py <project_id> <msg>` CLI |
| pueue CLI | PATH | `pueue status --json`, `pueue log`, `pueue add` |
| openclaw CLI | `~/.npm-global/bin/openclaw` | `openclaw system event --mode now` (new dependency) |

### Step 3: BY TERM — Grep key terms

```bash
grep -rn "openclaw" . --include="*.sh" --include="*.py"
# Results: 3 files in scripts/vps/
```

| File | Line | Context |
|------|------|---------|
| scripts/vps/pueue-callback.sh | 291-326 | Step 6.8 — writes pending-events, where wake call will be added |
| scripts/vps/openclaw-artifact-scan.py | 84-86 | Reads `ai/openclaw/pending-events/` and `processed-events/` |
| scripts/vps/tests/test_artifact_scan.py | 14 | Tests for artifact scan module |

```bash
grep -rn "system event\|gateway wake\|--mode now" . --include="*.sh" --include="*.py" --include="*.md"
# Results: 0 — no existing usage of openclaw system event in codebase
```

No existing usage of `openclaw system event` anywhere in the codebase. This is a net-new call.

### Step 4: CHECKLIST — Mandatory folders

- [x] `tests/**` — `scripts/vps/tests/test_artifact_scan.py` (72 LOC). No tests for pueue-callback.sh itself (bash, not Python). No test coverage change required.
- [x] `db/migrations/**` — N/A, no database schema change.
- [x] `ai/glossary/**` — N/A, no domain terminology change.

### Step 5: DUAL SYSTEM check

N/A — not changing data source. The event file write mechanism is unchanged. We are adding a second notification channel (openclaw wake) that is additive to the existing cron fallback, not replacing it.

---

## Affected Files

| File | LOC | Role | Change type |
|------|-----|------|-------------|
| scripts/vps/pueue-callback.sh | 410 | Pueue completion callback — main change target | modify |
| scripts/vps/openclaw-artifact-scan.py | 146 | Reads pending-events written by callback | read-only (no change) |
| scripts/vps/tests/test_artifact_scan.py | 72 | Unit tests for artifact scan | read-only (no change) |

**Total:** 1 file modified, 410 LOC (change is ~3-5 lines inside existing `if` block).

---

## Reuse Opportunities

### Import (use as-is)
- `$CALLBACK_LOG` variable — already defined at line 30, use directly in `2>>"$CALLBACK_LOG"` redirect
- `|| true` pattern — consistent with all other fail-safe calls in the script

### Pattern (copy structure, not code)
- notify.py call block (lines 273-281) — exact pattern: command with `2>>"$CALLBACK_LOG" || { echo WARN ... >&2 }` wrapper
- `command -v` guard (line 113) — check binary existence before invoking

---

## Git Context

### Recent Changes to Affected Areas

```bash
git log --oneline -10 -- scripts/vps/pueue-callback.sh
```

| Date | Commit | Author | Summary |
|------|--------|--------|---------|
| 2026-03-18 | 2c9d35a | Ellevated | feat(orchestrator): silence intermediate Telegram notifications for cycle skills |
| 2026-03-18 | a214790 | Ellevated | Revert "fix(orchestrator): silence all intermediate notifications" |
| 2026-03-18 | 6b16f6a | Ellevated | fix(orchestrator): silence all intermediate notifications — north-star compliance |
| 2026-03-18 | 3ca3e21 | Ellevated | fix(orchestrator): BUG-155 cycle e2e reliability v2 — 4 bugs fixed + smoke test |
| 2026-03-18 | 99d8ba7 | Ellevated | fix(orchestrator): TECH-154 cycle e2e reliability — 4 breaks fixed |
| 2026-03-18 | e7d619d | Ellevated | fix(orchestrator): always dispatch reflect after autopilot |
| 2026-03-17 | 9462cc7 | Ellevated | openclaw: add hybrid artifact wake flow |

**Observation:** Файл активно менялся сегодня (5 коммитов за 18 марта). Коммит `9462cc7` добавил Step 6.8 (именно блок, куда вставляем wake). Коммит `a214790` — revert предыдущей попытки — свидетельствует о нестабильности: нужно быть аккуратным с позиционированием кода внутри `if` блока.

---

## Exact Insertion Point

Step 6.8 блок (lines 295-326 в текущей версии):

```bash
# строка 324 — закрывающий EOF heredoc
EOF
    fi   # ← строка 325: закрывает if [[ -n "$PROJECT_PATH_FOR_EVENT" ...
fi       # ← строка 326: закрывает if [[ "$STATUS" == "done" || ...
```

Вставить **после строки 324 (EOF) и до строки 325 (`fi`)** — внутри блока `if [[ -n "$PROJECT_PATH_FOR_EVENT" && ... ]]`, то есть строго после того, как `$EVENT_FILE` был записан:

```bash
        # Wake OpenClaw immediately — no cron lag
        openclaw system event --mode now 2>>"$CALLBACK_LOG" || true
```

**Важно:** `openclaw` находится в `~/.npm-global/bin/`. В systemd PATH эта директория не добавляется автоматически (`.bashrc` не sourced). Надёжнее использовать полный путь или добавить к PATH в начале callback:

```bash
# В секции Environment (после строки 52):
export PATH="${HOME}/.npm-global/bin:${PATH}"
```

Либо прямо в строке wake:

```bash
        "${HOME}/.npm-global/bin/openclaw" system event --mode now 2>>"$CALLBACK_LOG" || true
```

---

## Risks

1. **Risk:** `openclaw` не в PATH systemd-сервиса
   **Impact:** wake-команда молча падает (`|| true`), cron fallback продолжает работать, но немедленного wake не происходит
   **Mitigation:** Использовать полный путь `${HOME}/.npm-global/bin/openclaw` или добавить `export PATH="${HOME}/.npm-global/bin:${PATH}"` в секцию Environment callback (после строки 52)

2. **Risk:** Inbox-спека содержит несуществующую команду `openclaw gateway wake --mode now`
   **Impact:** Если имплементировать дословно — команда не найдена, wake не срабатывает
   **Mitigation:** Использовать правильную команду `openclaw system event --mode now` (верифицировано против установленного openclaw 2026.3.13)

3. **Risk:** Gateway не запущен (openclaw gateway offline)
   **Impact:** `openclaw system event` вернёт ошибку подключения, уйдёт в `|| true`, wake не произойдёт
   **Mitigation:** Это допустимо — cron fallback обеспечивает eventual pickup. Ошибка логируется в CALLBACK_LOG.

4. **Risk:** Файл активно менялся сегодня (revert `a214790`)
   **Impact:** Конфликт при merge или неожиданное взаимодействие со свежими изменениями
   **Mitigation:** Изменение строго аддитивное (3 строки внутри существующего `if`-блока), не затрагивает логику notify/skip
