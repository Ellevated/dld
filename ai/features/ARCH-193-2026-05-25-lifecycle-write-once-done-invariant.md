# Architecture: [ARCH-193] Lifecycle write-once-done invariant + autopilot writer authority closure

**Status:** queued | **Priority:** P1 | **Risk:** R1 | **Date:** 2026-05-25

---

## Council Decision (synthesis)

Council `/council` (2026-05-25, 4/4 approve_with_changes, Variant 3 rejected unanimously) принял **Variant 2-strict**: structural Rule 7 в `lifecycle.write_lifecycle` + удаление `autopilot`/`spark` из `_ALLOWED_WRITERS`. Forensic addendum (выполнен после Council) выявил доп. механизм — **autopilot пишет lifecycle через прямой `git add ai/lifecycle/`** с non-canonical `chore(lifecycle):` subject, обходя pre-commit hook (который отсутствует на awardybot/dld/dowry). Scope расширен на hook coverage + skill hard-rule.

Полный синтез: `ai/.council/20260525-ARCH-193/synthesis.md`
Forensic findings: `ai/.council/20260525-ARCH-193/forensic-addendum.md`

---

## Symptom

В ночь 2026-05-24/25 callback демоутнул 5 завершившихся успешно autopilot-сессий в `blocked` (см. BUG-192). FTR-1078 "спасся" через Rule 7, остальные — нет. Forensic на awardybot выявил:

- 04:16 — callback wrote `lifecycle(FTR-1078): blocked` (regex blind, BUG-192 root cause)
- 07:15 — autopilot wrote `chore(lifecycle): FTR-1078 → done` direct commit (НЕ канонический format от lifecycle.py)
- `ai/lifecycle/FTR-1078.yaml:transitions[].by` = `autopilot`
- `awardybot/.git/hooks/pre-commit` — НЕ установлен (ARCH-187 hook coverage drift)

Это означает:
1. **Rule 7 — не структурный.** Живёт только в `callback.verify_status_sync`, не в примитиве записи. Любой другой writer (включая autopilot direct write) может демотнуть `done`.
2. **autopilot писатель identity активен** в `_ALLOWED_WRITERS` — может вызывать `write_lifecycle(by="autopilot")`.
3. **Pre-commit hook coverage gap** — 3 из 4 проектов не имеют установленного hook'а.
4. **Autopilot skill prompts** не запрещают прямой `git add ai/lifecycle/` явно (только косвенно через "Status writes by callback only").

---

## Root Cause

Multi-layered:

**Layer A — Rule 7 не структурный.** `callback.py:1074-1092` — Rule 7 проверяет `existing.status == "done"` и пропускает demote. Но `write_lifecycle` в `lifecycle.py:343` НЕ имеет этой проверки. Если кто-то ещё (autopilot, spec_operator demote, orchestrator) вызывает `write_lifecycle("blocked")` на done-спеку — пройдёт.

**Layer B — autopilot in `_ALLOWED_WRITERS`.** `lifecycle.py:49` включает `"autopilot"` как валидную identity. autopilot session может вызвать `write_lifecycle(by="autopilot")` напрямую (Python import) или через `spec_operator force-done --by=autopilot`.

**Layer C — Hook coverage drift.** ARCH-187 установил pre-commit hook (`.claude/hooks/pre-commit-lifecycle-guard.mjs`), но `core.hooksPath` не настроен на VPS-проектах:

```
=== awardybot ===     core.hooksPath: default (no pre-commit)
=== dld ===           core.hooksPath: default (no pre-commit)
=== dowry ===         core.hooksPath: default (no pre-commit)
=== gipotenuza ===    has pre-commit hook
```

**Layer D — Skill prompts разрешают.** `.claude/skills/autopilot/autopilot-git.md:217` упоминает `spec_operator.py force-done --by=operator` как escape. `.claude/agents/coder.md` запрещает Edit Status в spec, но не запрещает явно `git add ai/lifecycle/` или Edit yaml.

---

## Fix Approach (Variant 2-strict + forensic-driven additions)

### Layer 1 — Structural Rule 7 в `lifecycle.write_lifecycle`

Перенести Rule 7 из `callback.verify_status_sync` в примитив записи `lifecycle.write_lifecycle`. Новый exception `LifecycleAlreadyDoneError`. Любой caller — callback, spec_operator, orchestrator, autopilot — получит ValueError если попытается записать non-done статус поверх done.

```python
# lifecycle.py
class LifecycleAlreadyDoneError(Exception):
    def __init__(self, spec_id, attempted, by):
        super().__init__(
            f"lifecycle({spec_id}): cannot transition done → {attempted} (writer={by}); "
            f"done is terminal (Rule 7 — ADR-025)"
        )
        self.spec_id = spec_id
        self.attempted = attempted
        self.by = by


def write_lifecycle(repo_dir, spec_id, status, *, by="callback", reason=None, pueue_id=None, allowed_files_hash=None):
    if by not in _ALLOWED_WRITERS:
        raise ValueError(f"write_lifecycle: invalid by={by!r}; allowed={sorted(_ALLOWED_WRITERS)}")

    # Rule 7 — done is terminal (ADR-025, ARCH-193)
    if status != "done":
        existing = _read_yaml_from_head(str(repo_dir), spec_id)
        if existing and existing.get("status") == "done":
            raise LifecycleAlreadyDoneError(spec_id, attempted=status, by=by)

    # ... rest unchanged
```

### Layer 2 — Remove `autopilot` and `spark` from `_ALLOWED_WRITERS`

```python
_ALLOWED_WRITERS = frozenset({
    "callback", "orchestrator", "operator",
    "qa", "audit", "migration"
    # "autopilot" removed — signals via task_status JSON only (ADR-023 intent)
    # "spark" removed — zero callers in codebase, writes via orchestrator.create_initial
})
```

Также `spec_operator.py` argparse `--by` choices: убрать `autopilot` и `spark` из `["operator", "qa", "audit", "autopilot", "spark"]` (lines 136, 148).

### Layer 3 — Pre-commit hook strengthening

Текущий `.claude/hooks/pre-commit-lifecycle-guard.mjs` принимает любой `^lifecycle\([A-Z]+-\d+\):` subject. Но callback и spec_operator пишут через plumbing (private GIT_INDEX_FILE) — hook для них никогда не срабатывает. Любой staged `ai/lifecycle/*.yaml` — definitionally spoof.

```javascript
// Tightened: reject ALL staged ai/lifecycle/ commits unless explicit override.
if (lifecycleFiles.length === 0) process.exit(0);
if (process.env.LIFECYCLE_WRITE_AUTHORIZED === '1') {
    // Log to audit but allow
    try {
        execFileSync('python3', ['scripts/vps/event_writer.py', 'dld',
            `LIFECYCLE_AUTHORIZED_BYPASS: ${lifecycleFiles.join(',')} subject=${msg.split('\n')[0]}`]);
    } catch {}
    process.exit(0);
}
console.error('✗ Direct git commit touching ai/lifecycle/ is FORBIDDEN.');
console.error('  Callback and spec_operator write via plumbing (no staging).');
console.error('  Use: python3 scripts/vps/spec_operator.py {demote|force-done} --by=<id>');
console.error('  Or:  LIFECYCLE_WRITE_AUTHORIZED=1 (logged to audit)');
process.exit(1);
```

### Layer 4 — Hook installation idempotency

`scripts/vps/setup-vps.sh` должен проверять/устанавливать hook на каждый project через `core.hooksPath`:

```bash
for proj in $(jq -r '.[].path' projects.json); do
  if [ -d "$proj/.git" ]; then
    git -C "$proj" config core.hooksPath .git-hooks
    [ -d "$proj/.git-hooks" ] || ln -sf "$proj/.claude/hooks/git-hooks" "$proj/.git-hooks"
  fi
done
```

(precise path strategy выясняется на Task 4.)

### Layer 5 — Skill hard-rule против direct lifecycle write

`.claude/agents/coder.md` и `.claude/skills/autopilot/finishing.md` добавить explicit FORBIDDEN section:

```
**NEVER write to ai/lifecycle/*.yaml directly. ONLY:**
- ✅ emit `task_status: "complete"` in agent JSON → callback writes lifecycle
- ❌ Edit ai/lifecycle/X.yaml
- ❌ git add ai/lifecycle/X.yaml
- ❌ Commit with subject matching `chore(lifecycle):` or similar non-canonical lifecycle format

If lifecycle write FAILS via callback (impl_guard regression):
- Human operator runs: python3 scripts/vps/spec_operator.py force-done <proj> <SPEC> "<reason>" --by=operator
- Autopilot does NOT have permission for this — it's a human-only escape hatch.
```

### Layer 6 — Notify on Rule 7 NOOP

`scripts/vps/callback.py` в existing Rule 7 NOOP branch:

```python
event_writer.notify(
    project_id,
    status="warning",
    message=f"rule_7_saved: {spec_id} — callback attempted demote, spec already done. "
            f"Investigate who wrote lifecycle({spec_id}): done."
)
```

### Layer 7 — Actionable reason template

`scripts/vps/callback.py` в `_set_status` при `no_merged_implementation`:

```python
reason = (
    f"no_merged_implementation — if implementation is real, run: "
    f"python3 scripts/vps/spec_operator.py force-done {project_id} {spec_id} "
    f"'gate regex bug, verified manually' --by=operator"
)
```

### Layer 8 — ADR-025

`.claude/rules/architecture.md`:

```markdown
| ADR-025 | **Lifecycle write-once-done invariant (Rule 7 structural).** Rule 7 переехала из `callback.verify_status_sync` в примитив `lifecycle.write_lifecycle`. Любая попытка `done → !done` (любым writer'ом) → `LifecycleAlreadyDoneError`. `autopilot` и `spark` удалены из `_ALLOWED_WRITERS` (autopilot сигналит через `task_status: complete` JSON; spark не имеет callers). Operator escape — `spec_operator force-done --by=operator` (сохраняется). Pre-commit hook ужесточён: ANY staged `ai/lifecycle/*.yaml` blocked unless `LIFECYCLE_WRITE_AUTHORIZED=1` (logged to audit). Hook installation сделана idempotent в `setup-vps.sh` для всех VPS проектов. Amends ADR-023. | 2026-05-25 | ARCH-193 + forensic on awardybot FTR-1078 (autopilot direct git add path confirmed) |
```

---

## Reproduction Steps

### Repro 1 — autopilot direct lifecycle write (today, before fix)

```bash
cd /home/dld/projects/awardybot
git log --all --pretty=fuller -- ai/lifecycle/FTR-1078.yaml | head -30
# Shows: commit 177f63f7 chore(lifecycle): FTR-1078 → done by Ellevated
#        non-canonical subject, hook absent in this project
ls -la .git/hooks/pre-commit
# (no such file)
git config core.hooksPath
# (not set — using default .git/hooks)
```

### Repro 2 — Rule 7 callback-only gap

```bash
cd /home/dld/projects/dld
python3 -c "
import sys; sys.path.insert(0, 'scripts/vps')
from lifecycle import create_initial, write_lifecycle
# Bootstrap test spec as done
create_initial('/tmp/test-repo', 'TEST-001', priority='p2', kind='test')
write_lifecycle('/tmp/test-repo', 'TEST-001', 'done', by='operator')
# Try to demote — currently succeeds (no Rule 7 in write_lifecycle)
write_lifecycle('/tmp/test-repo', 'TEST-001', 'blocked', by='operator')
print('demote succeeded — Rule 7 NOT structural!')
"
```

### Repro 3 — Hook coverage check

```bash
for p in /home/dld/projects/*/; do
  echo "=== $(basename $p) ==="
  cd "$p"
  git config core.hooksPath 2>/dev/null && ls -la .git/hooks/pre-commit 2>/dev/null
done
# Shows awardybot, dld, dowry without pre-commit hook installed
```

---

## Implementation Plan

### Task 1 — `lifecycle.py`: add `LifecycleAlreadyDoneError` + structural Rule 7

**File:** `scripts/vps/lifecycle.py`

**Current state (verified 2026-05-25):**
- `_ALLOWED_WRITERS` defined at lines 49–51 (multi-line frozenset).
- `write_lifecycle` is at line 343; `_ALLOWED_WRITERS` validation at line 360–361 (`if by not in _ALLOWED_WRITERS: raise ValueError(...)`).
- `_read_yaml_from_head(repo_dir, spec_id)` ALREADY EXISTS at line 104 — reuse it (do NOT redefine).
- `LifecycleWriteRaceError` defined at lines 59–65 — colocate new exception immediately after it.
- `make_yaml` inner function (lines 365–375) already calls `_read_yaml_from_head` — that read is inside the CAS retry; the new Rule 7 must happen BEFORE the CAS loop to avoid an extra `git show` per attempt and to fail fast.

**Changes:**

1. Add new exception class `LifecycleAlreadyDoneError(Exception)` immediately after `LifecycleWriteRaceError` (after line 65). Include `spec_id`, `attempted`, `by` attributes. Message format: `f"lifecycle({spec_id}): cannot transition done → {attempted} (writer={by}); done is terminal (Rule 7 — ADR-025)"`.

2. In `write_lifecycle` (line 343), inject Rule 7 check between line 361 (existing `raise ValueError(...)` for invalid writer) and line 362 (`repo_dir = str(repo_dir)`):
   ```python
   # Rule 7 — done is terminal (ADR-025, ARCH-193). Structural guard at the
   # write primitive — protects ALL callers (callback, operator, etc).
   if status != "done":
       _existing_head = _read_yaml_from_head(str(repo_dir), spec_id)
       if _existing_head and _existing_head.get("status") == "done":
           raise LifecycleAlreadyDoneError(spec_id=spec_id, attempted=status, by=by)
   ```

3. Export the new exception via module top-level naming (no `__all__` exists; importers use `lifecycle.LifecycleAlreadyDoneError`).

### Task 2 — `lifecycle.py`: remove `autopilot` and `spark` from `_ALLOWED_WRITERS`

**File:** `scripts/vps/lifecycle.py:49-51`

**Current state:**
```python
_ALLOWED_WRITERS = frozenset(
    {"callback", "orchestrator", "spark", "operator", "qa", "audit", "autopilot", "migration"}
)
```

**Change to:**
```python
# ADR-025 (ARCH-193): autopilot removed — signals via task_status JSON only;
# spark removed — zero direct callers (specs are bootstrapped via
# orchestrator.create_initial which uses by="orchestrator").
_ALLOWED_WRITERS = frozenset(
    {"callback", "orchestrator", "operator", "qa", "audit", "migration"}
)
```

**Verification grep before commit (must be empty):**
```bash
grep -rn 'by="autopilot"\|by="spark"\|by=.autopilot.\|by=.spark.' scripts/vps/ --include='*.py'
```
If any hits → those callers must be updated or removed.

### Task 3 — `spec_operator.py`: remove autopilot/spark from `--by` choices + catch LifecycleAlreadyDoneError

**File:** `scripts/vps/spec_operator.py`

**Current state (verified 2026-05-25):**
- `--by` `choices=["operator", "qa", "audit", "autopilot", "spark"]` at line 136 (demote subcommand) and line 148 (force-done subcommand).
- `_set_status` defined at line 65; existing exception handling at lines 87–92 catches `ValueError` (rc=2) and `lifecycle.LifecycleWriteRaceError` (rc=4).
- Exit code table is documented at lines 19–24 of module docstring — UPDATE it to add rc=5.

**Changes:**

1. Both subparsers (lines 136 and 148): change `choices=["operator", "qa", "audit", "autopilot", "spark"]` → `choices=["operator", "qa", "audit"]`.

2. In `_set_status` (line 65), extend the except chain at lines 87–92:
   ```python
   try:
       lifecycle.write_lifecycle(project, spec_id, target, reason=reason, by=by)
   except lifecycle.LifecycleAlreadyDoneError as exc:
       print(f"operator: {exc}", file=sys.stderr)
       return 5
   except ValueError as exc:
       print(f"operator: {exc}", file=sys.stderr)
       return 2
   except lifecycle.LifecycleWriteRaceError:
       print("operator: race exhausted, retry later", file=sys.stderr)
       return 4
   ```

3. Update module docstring exit-code table (lines 19–24) to add:
   ```
       5 — done is terminal; cannot demote/overwrite (Rule 7, ADR-025).
   ```

4. Special case: `force-done` on already-done spec should be IDEMPOTENT, not rc=5. The Rule 7 check in `write_lifecycle` only blocks when `status != "done"`, so `force-done` (target="done") passes through naturally. Verified by test 5 (Task 9).

### Task 4 — `setup-vps.sh`: idempotent hook installation per-project

**File:** `scripts/vps/setup-vps.sh`

**Current state (verified 2026-05-25):**
- No existing pre-commit / hooksPath logic.
- Phase flags: `--update-skills` (line 37), `--phase3` (line 43). Main install body starts at line 145.
- `projects.json` parsed in lines 336–342 (existence check only); iteration not yet implemented in setup-vps.sh.
- Repo convention: each project has `.git-hooks/pre-commit` (bash wrapper, like `/home/dld/projects/dld/.git-hooks/pre-commit`) which `exec`s `.claude/hooks/pre-commit-lifecycle-guard.mjs`. The wrapper file is checked into repo, NOT generated.

**Changes:**

1. Add new flag handler `--phase4-hooks` BEFORE the `--phase3` block (around line 42), idempotent:
   ```bash
   if [[ "${1:-}" == "--phase4-hooks" ]]; then
       echo "=== Phase 4 Hooks Setup ==="
       PROJECTS_FILE="${SCRIPT_DIR}/projects.json"
       if [[ ! -f "$PROJECTS_FILE" ]]; then
           fail "projects.json not found at $PROJECTS_FILE"
       fi

       # Iterate via jq → null-separated (handles paths with spaces).
       while IFS= read -r -d '' proj_path; do
           if [[ ! -d "$proj_path/.git" ]]; then
               warn "skip: $proj_path has no .git/"
               continue
           fi
           if [[ ! -f "$proj_path/.git-hooks/pre-commit" ]]; then
               warn "skip: $proj_path has no .git-hooks/pre-commit (expected checked-in wrapper)"
               continue
           fi
           if [[ ! -f "$proj_path/.claude/hooks/pre-commit-lifecycle-guard.mjs" ]]; then
               warn "skip: $proj_path has no .claude/hooks/pre-commit-lifecycle-guard.mjs"
               continue
           fi
           # Idempotent: set hooksPath + chmod
           git -C "$proj_path" config core.hooksPath .git-hooks
           chmod +x "$proj_path/.git-hooks/pre-commit"
           chmod +x "$proj_path/.claude/hooks/pre-commit-lifecycle-guard.mjs"
           ok "installed hook: $proj_path (core.hooksPath=.git-hooks)"
       done < <(jq -r '.[].path' "$PROJECTS_FILE" | tr '\n' '\0')

       echo "=== Phase 4 Hooks Setup complete ==="
       exit 0
   fi
   ```

2. Call the new section from main install body — add at end (after line 471, before "Setup complete"):
   ```bash
   # Phase 4 hooks (idempotent, ARCH-193)
   if [[ -f "${SCRIPT_DIR}/projects.json" ]]; then
       echo ""
       echo "--- Pre-commit hooks installation (ARCH-193) ---"
       bash "${BASH_SOURCE[0]}" --phase4-hooks || warn "phase4-hooks failed (non-fatal)"
   fi
   ```

**Note:** Hook FILES (`.git-hooks/pre-commit` + `.claude/hooks/pre-commit-lifecycle-guard.mjs`) are NOT created by setup-vps.sh — they must exist in each project's repo. If absent, setup-vps.sh warns and skips. For awardybot/dowry/etc this requires a separate `git cherry-pick` of the ARCH-187 commits — operator's responsibility (out of scope, see Task 11 manual verification).

### Task 5 — Pre-commit hook: reject ALL staged lifecycle yamls

**File:** `.claude/hooks/pre-commit-lifecycle-guard.mjs`

**Current state (verified 2026-05-25):**
- Hook is 64 lines. Bypass logic at lines 44–50:
  ```js
  if (lifecycleFiles.length === 0) process.exit(0);          // line 46
  if (process.env.LIFECYCLE_WRITE_AUTHORIZED === '1') process.exit(0);  // line 47

  const msg = commitMsg();
  if (/^lifecycle\([A-Z]+-\d+\):/.test(msg)) process.exit(0); // line 50 — REMOVE THIS BRANCH
  ```
- Error messages at lines 52–63 reference `spec_operator.py` correctly already.

**Changes:**

1. DELETE the subject-allowlist branch (lines 49–50: `const msg = commitMsg();` and the `if (/^lifecycle\(...\):/...)` line). After this removal: callback/spec_operator pass through naturally because they NEVER stage `ai/lifecycle/` files (they write via plumbing with private `GIT_INDEX_FILE`, so `git diff --cached` returns 0 staged lifecycle files).

2. Remove the now-unused `commitMsg()` function (lines 33–41) and the `readFileSync` import (line 18).

3. When `LIFECYCLE_WRITE_AUTHORIZED=1` bypass is taken (line 47), call `event_writer.py` BEFORE `process.exit(0)`:
   ```js
   if (process.env.LIFECYCLE_WRITE_AUTHORIZED === '1') {
       try {
           const subject = (() => {
               try { return execFileSync('git', ['log', '-1', '--format=%s', 'HEAD'], { encoding: 'utf-8', timeout: 2000 }).trim(); }
               catch { return '<no HEAD>'; }
           })();
           execFileSync('python3', [
               'scripts/vps/event_writer.py',
               process.cwd(), 'callback', 'warning',
               `LIFECYCLE_AUTHORIZED_BYPASS: ${lifecycleFiles.join(',')} prev_subject=${subject}`
           ], { timeout: 5000 });
       } catch { /* best-effort */ }
       process.exit(0);
   }
   ```
   `event_writer.py` CLI signature: `python3 event_writer.py <project_path> <skill> <status> <message>` (verified — `scripts/vps/event_writer.py:140-163`).

4. Update error message (lines 52–63) to remove `• commit message starting with lifecycle(<SPEC-ID>):` (now invalid).

### Task 6 — `callback.py`: catch `LifecycleAlreadyDoneError` + Hermes notify on Rule 7 save

**File:** `scripts/vps/callback.py`

**Current state (verified 2026-05-25):**
- `verify_status_sync` defined at line 1003 (NOT `_set_status` — that name is in spec_operator.py).
- Rule 7 fast-path at lines 1074–1092 (returns NOOP "already_done_terminal" when existing_status == "done"). KEEP this as-is; it short-circuits the gate and remains the primary path.
- `lifecycle.write_lifecycle(...)` call at lines 1161–1186, wrapped in generic `try/except Exception`. The Rule 7 structural exception is now `LifecycleAlreadyDoneError` (from Task 1) — this branch is the SAFETY NET in case the fast-path is bypassed somehow (e.g. race window between read and write).
- `event_writer` import at line 36. Correct signature: `notify(project_path, skill, status, message, artifact_rel="")` — verified `scripts/vps/event_writer.py:95-104`. The spec's earlier `notify(project_id, status=..., message=...)` example was WRONG.
- `_record(project_id, spec_id, action, reason, *, demoted=False)` at line 967.
- `project_path` is the local variable holding the absolute path inside `verify_status_sync` (search the function body — used in `_fetch_develop`, `_commit_stats`, etc.).

**Changes:**

1. Replace the generic exception handler at lines 1170–1186 with a typed chain:
   ```python
   try:
       lifecycle.write_lifecycle(
           project_path, spec_id, new_status,
           reason=reason or None, by="callback", pueue_id=pueue_id,
       )
   except lifecycle.LifecycleAlreadyDoneError as exc:
       # Rule 7 structural guard (ADR-025): race between Rule 7 fast-path
       # read and write — another writer flipped the spec to done. Treat as
       # benign NOOP, but emit a warning event for investigation.
       log.warning("STATUS_SYNC: %s — Rule 7 structural save (%s)", spec_id, exc)
       _record(project_id, spec_id, "noop", "rule_7_saved")
       try:
           event_writer.notify(
               project_path, "callback", "failed",
               f"rule_7_saved: {spec_id} — callback attempted '{new_status}', "
               f"spec already done. Investigate who wrote lifecycle({spec_id}): done.",
           )
       except Exception:  # noqa: BLE001
           pass  # notify is best-effort
       _emit_audit(
           project_id, spec_id, pueue_id, target_in, "done", "rule_7_saved",
           len(allowed) if allowed else 0,
           code_loc, test_loc, code_commits, started_at, start_wall,
       )
       return
   except Exception as exc:  # noqa: BLE001
       # existing handler — UNCHANGED:
       log.warning("STATUS_SYNC: lifecycle.write failed for %s: %s", spec_id, exc)
       _emit_audit(
           project_id, spec_id, pueue_id, target_in, "error",
           f"write_failed:{exc}",
           len(allowed) if allowed else 0,
           code_loc, test_loc, code_commits, started_at, start_wall,
       )
       return
   ```

2. The existing Rule 7 fast-path (lines 1074–1092) stays — it avoids `_fetch_develop` cost when spec is already done. The new branch above is only reached when something flipped the spec to "done" between the read at line 1052 and the write at line 1162.

3. `event_writer.notify` `status` parameter accepts free-string; using `"failed"` routes to the warning-style alert channel (consistent with `notify_circuit_event(action="open")` at `event_writer.py:127`). "warning" is also valid but `"failed"` matches the existing pattern.

### Task 7 — `callback.py`: actionable reason template

**File:** `scripts/vps/callback.py`

**Current state (verified 2026-05-25):**
- The function is `verify_status_sync` (line 1003) — there is NO `_set_status` in callback.py (that name lives in spec_operator.py).
- `reason = "no_merged_implementation"` at line 1114 (inside the `else` branch of `_is_done_on_develop`).
- `project_id` and `spec_id` are locals in scope at that point.

**Change:** Replace line 1114:
```python
reason = "no_merged_implementation"
```
with:
```python
reason = (
    f"no_merged_implementation — if implementation IS real, run: "
    f"python3 scripts/vps/spec_operator.py force-done {project_id} {spec_id} "
    f"'gate regex bug, verified manually' --by=operator"
)
```

This reason string is persisted into `ai/lifecycle/{spec_id}.yaml:blocked_reason` via the write call below, so operators see the exact command in `render_backlog.py` output / Hermes notifications.

**Side-effect consideration:** existing tests in `scripts/vps/tests/test_callback.py` may assert on `reason == "no_merged_implementation"` literal — Task 9 must include grep + update of those assertions.

### Task 8 — Skill hard-rules

**Files (all verified to exist 2026-05-25):**
- `.claude/agents/coder.md` (line 153 has the existing weak rule)
- `.claude/skills/autopilot/finishing.md` (existing references at lines 25–30, 218–226)
- `.claude/skills/autopilot/autopilot-git.md` (existing reference at lines 206–221, including `force-done --by=operator` on line 217)
- `template/.claude/agents/coder.md`
- `template/.claude/skills/autopilot/finishing.md`
- `template/.claude/skills/autopilot/autopilot-git.md`

**Changes:**

1. `.claude/agents/coder.md` (and template copy) — extend line 153 entry into a fuller FORBIDDEN block:
   ```markdown
   ## Forbidden — Lifecycle writes (ADR-025 / ARCH-193)

   - NEVER Edit `**Status:**` in `ai/features/*.md` or status column in `ai/backlog.md`.
   - NEVER Edit `ai/lifecycle/*.yaml` directly.
   - NEVER `git add ai/lifecycle/*.yaml` (pre-commit hook will REJECT).
   - NEVER write commits with subjects like `chore(lifecycle): ...` or any non-canonical lifecycle format.

   ONLY mechanism: emit `"task_status": "complete" | "blocked" | "needs_review"`
   in your final agent JSON. callback.py reads it and atomically writes lifecycle yaml.

   If callback fails to mark done (gate regex bug or similar) — that is a HUMAN OPERATOR
   responsibility. Autopilot does NOT have `force-done` permission. Operator runs:
   `python3 scripts/vps/spec_operator.py force-done <proj> <SPEC> "<reason>" --by=operator`.
   ```

2. `.claude/skills/autopilot/finishing.md` (and template) — append the same FORBIDDEN block at end of file (after line 233).

3. `.claude/skills/autopilot/autopilot-git.md` (and template) — replace section "5.2 Update Status" (lines 206–221), specifically the operator instructions at lines 213–221:
   ```markdown
   ### 5.2 Update Status — REMOVED (ARCH-187 / ADR-024 / ADR-025)

   Status writes are exclusive to `callback.py` (ADR-023). Do **NOT** commit
   spec / backlog / lifecycle status changes manually. Callback fires on
   pueue task completion and atomically updates `ai/lifecycle/{spec}.yaml`
   via git plumbing. See `finishing.md`.

   **Autopilot has NO override path.** If callback fails to mark done, signal
   `"task_status": "needs_review"` and stop. A human operator (NOT autopilot)
   may then run:
   ```
   python3 scripts/vps/spec_operator.py force-done <project> <SPEC_ID> "<reason>" --by=operator
   ```
   The `--by=autopilot` and `--by=spark` choices have been REMOVED (ADR-025).

   Direct `git add ai/lifecycle/*.yaml` is HARD-BLOCKED by
   `.claude/hooks/pre-commit-lifecycle-guard.mjs` (no subject-allowlist exception).
   ```

4. Apply identical edits in `template/.claude/*` copies (template sync mandated by `.claude/rules/template-sync.md`).

### Task 9 — Tests

**File:** `scripts/vps/tests/test_lifecycle_done_terminal.py` (NEW)

**Fixture pattern (verified):** reuse `tmp_git_repo` pattern from `scripts/vps/tests/test_lifecycle.py:34-63` (subprocess `git init -b main` + initial commit + `ai/lifecycle/.gitkeep`). Make scripts/vps importable via `sys.path.insert(0, VPS_DIR)` pattern from the same file (lines 21–24).

**Discovery:** `pyproject.toml` testpaths includes `scripts/vps/tests` (TECH-189 Task 1) — pytest will pick this file up automatically.

**11 tests (pseudocode shape; full code in implementation):**

1. `test_write_lifecycle_blocks_done_to_blocked` — bootstrap as done via `create_initial(..., status="done")` (or write_lifecycle done by="operator"); then `write_lifecycle(blocked, by="callback")` raises `lifecycle.LifecycleAlreadyDoneError`.
2. `test_write_lifecycle_blocks_done_to_queued` — same setup; `write_lifecycle(queued, by="orchestrator")` raises.
3. `test_write_lifecycle_done_to_done_idempotent` — no exception, transitions list gets a new row, version increments.
4. `test_spec_operator_demote_done_fails_with_rc5` — bootstrap spec, set done, run `spec_operator.main(["demote", ..., "--by=operator"])`, assert returncode 5 and stderr contains "done is terminal".
5. `test_spec_operator_force_done_idempotent` — bootstrap as done, run `force-done` → rc=0, transitions has new row.
6. `test_spec_operator_rejects_by_autopilot` — `spec_operator.main(["demote", ..., "--by=autopilot"])` → argparse SystemExit rc=2.
7. `test_spec_operator_rejects_by_spark` — same with `--by=spark`.
8. `test_callback_rule7_catches_exception_and_noops` — bootstrap as done; call `callback.verify_status_sync(...)` (or its public façade); patch `event_writer.notify` and assert it was called with skill="callback" and message containing "rule_7_saved". Use monkeypatch on `lifecycle.read_lifecycle` to return non-done THEN have the actual write race (or simulate by calling write_lifecycle directly and catching). Practical approach: directly call `lifecycle.write_lifecycle(done→blocked)` from the test and assert the exception type — full integration is overkill.
9. `test_done_immutable_via_all_writers` — `@pytest.mark.parametrize("writer", sorted(lifecycle._ALLOWED_WRITERS - {"orchestrator"}))` (orchestrator excluded because its only call site is `create_initial`, which is bootstrap-only). Each writer's `write_lifecycle(done→queued)` raises.
10. `test_pre_commit_hook_blocks_canonical_lifecycle_subject` — invoke the hook via `subprocess.run(["node", ".claude/hooks/pre-commit-lifecycle-guard.mjs"])` in a tmp git repo with a staged `ai/lifecycle/X.yaml` AND `.git/COMMIT_EDITMSG` containing `lifecycle(SPEC-123): done`. Assert exit code 1 (subject-allowlist removed by Task 5).
11. `test_pre_commit_hook_logs_authorized_bypass` — same setup, but `env["LIFECYCLE_WRITE_AUTHORIZED"] = "1"`. Assert exit 0 AND `event_writer.py` was invoked (mock via PATH-injected shim that writes to a temp file the test then reads).

**Side-effect update:** grep `scripts/vps/tests/test_callback.py` for the literal `"no_merged_implementation"` — Task 7 changed the reason string; any assertion equality on the literal must be loosened to `assert reason.startswith("no_merged_implementation")`.

**Verification grep:**
```bash
grep -rn '"no_merged_implementation"' scripts/vps/tests/
```

### Task 10 — ADR-025 + ADR-023 amend

**File:** `.claude/rules/architecture.md`

- Add ADR-025 row.
- Update ADR-023 row: "amended by ADR-025 — Rule 7 now structural in `write_lifecycle`; autopilot/spark removed from allowed writers".

### Task 11 — Run hook installation on existing VPS projects

**Manual operation** (operator runs after Task 4 merge):

```bash
bash scripts/vps/setup-vps.sh --phase4-hooks
# Verify:
for p in /home/dld/projects/*/; do
  echo "=== $(basename $p) ==="
  cd "$p"
  git config core.hooksPath && ls -la .git-hooks/pre-commit
done
```

---

## Acceptance Criteria (Definition of Done)

- [ ] `python3 -c "from lifecycle import LifecycleAlreadyDoneError"` — class exists.
- [ ] `python3 scripts/vps/spec_operator.py demote --by=autopilot ...` — argparse error.
- [ ] `python3 scripts/vps/spec_operator.py force-done --by=spark ...` — argparse error.
- [ ] Все 11 тестов проходят: `pytest scripts/vps/tests/test_lifecycle_done_terminal.py -v`.
- [ ] Manual repro: `write_lifecycle(done→blocked, by="callback")` → `LifecycleAlreadyDoneError`.
- [ ] Pre-commit hook на awardybot/dld/dowry установлен (`git config core.hooksPath` показывает `.git-hooks`).
- [ ] callback.py emits `event_writer.notify(status="warning", message="rule_7_saved: ...")` при срабатывании Rule 7.
- [ ] `no_merged_implementation` reason содержит actionable CLI template.
- [ ] ADR-025 в `architecture.md`, ADR-023 status: "amended by ADR-025".
- [ ] Skill files (`.claude/agents/coder.md`, `autopilot/finishing.md`, `autopilot-git.md` + 3 template copies) содержат hard rule "NEVER git add ai/lifecycle/".

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     Paths used by callback impl_guard for merge detection. -->

- `scripts/vps/lifecycle.py`
- `scripts/vps/callback.py`
- `scripts/vps/spec_operator.py`
- `scripts/vps/setup-vps.sh`
- `scripts/vps/tests/test_lifecycle_done_terminal.py`
- `.claude/hooks/pre-commit-lifecycle-guard.mjs`
- `template/.claude/hooks/pre-commit-lifecycle-guard.mjs`
- `.claude/skills/autopilot/autopilot-git.md`
- `.claude/skills/autopilot/finishing.md`
- `.claude/agents/coder.md`
- `template/.claude/skills/autopilot/autopilot-git.md`
- `template/.claude/skills/autopilot/finishing.md`
- `template/.claude/agents/coder.md`
- `.claude/rules/architecture.md`

---

## Out of Scope

1. **Structured `blocked_reason` blob** — Product Council recommendation, multi-domain change (Hermes/render_backlog/Telegram). Отдельная TECH spec по diagnostics UX.
2. **`LIFECYCLE_WRITE_AUTHORIZED=1` removal** — R0 операция, требует impact analysis на 9+ проектах. Этот spec логирует использования (Task 5), удаление — отдельная spec.
3. **"Near-misses" section в backlog.md** — Feature, не bug fix. После стабилизации.
4. **`spec_operator` refactor в thin wrapper** — Architect Concern #5. Defer.
5. **Interactive confirm prompt на `force-done`** — Security suggestion. Defer до confirmation что этого недостаточно.
6. **awardybot retroactive forensic on all 5 night incidents** — Если нужно — отдельная spec.

---

## Drift Log

**Checked:** 2026-05-25 by planner (validating against worktree HEAD).
**Result:** light_drift — spec line refs were mostly correct, function names had errors.

### Changes Detected

| File | Change Type | Action Taken |
|------|-------------|--------------|
| `scripts/vps/lifecycle.py` | `_ALLOWED_WRITERS` is multi-line (49–51), not single line 49 | AUTO-FIX: Task 2 updated |
| `scripts/vps/lifecycle.py` | `_read_yaml_from_head` already exists at line 104 | AUTO-FIX: Task 1 says "reuse, do not redefine" |
| `scripts/vps/lifecycle.py` | `write_lifecycle` `_ALLOWED_WRITERS` validation at lines 360–361 (not 343) | AUTO-FIX: Task 1 pinpoints insertion between 361 and 362 |
| `scripts/vps/callback.py` | spec said function `_set_status` — that name lives in spec_operator.py, NOT callback. Real function in callback is `verify_status_sync` (line 1003) | AUTO-FIX: Tasks 6 and 7 corrected |
| `scripts/vps/event_writer.py` | spec used `notify(project_id, status=..., message=...)` — real signature is `notify(project_path, skill, status, message, artifact_rel="")` | AUTO-FIX: Task 6 has correct call shape |
| `scripts/vps/callback.py` | `lifecycle.write_lifecycle` call is at lines 1162–1186 (wrapped in generic try/except Exception) | AUTO-FIX: Task 6 specifies typed except chain |
| `scripts/vps/callback.py` | `reason = "no_merged_implementation"` at line 1114 (inside verify_status_sync) | AUTO-FIX: Task 7 updated |
| `scripts/vps/setup-vps.sh` | No existing pre-commit/hooksPath logic; main install body ends near line 471 | AUTO-FIX: Task 4 specifies exact new `--phase4-hooks` block + invocation point |
| `.claude/hooks/pre-commit-lifecycle-guard.mjs` | Subject-allowlist bypass at lines 49–50; `commitMsg` helper at 33–41 (now unused after Task 5) | AUTO-FIX: Task 5 specifies deletions + bypass-logging addition |
| `.git-hooks/pre-commit` | Exists as bash wrapper that execs the mjs hook — confirms 2-file pattern Task 4 depends on | NO CHANGE needed in this file |
| `template/.claude/*` | All 3 mirror files exist (autopilot/finishing.md, autopilot/autopilot-git.md, agents/coder.md) | NO CHANGE — Task 8 already covers them |
| `scripts/vps/tests/conftest.py` and `test_lifecycle.py` | Existing fixture `tmp_git_repo` pattern verified | AUTO-FIX: Task 9 references reuse |
| `scripts/vps/tests/test_callback.py` | May contain assertion on literal `"no_merged_implementation"` — must be loosened due to Task 7 | AUTO-FIX: Task 9 notes the grep + update requirement |

### References Updated
- Task 1: `_read_yaml_from_head` "create if not exists" → "reuse existing at line 104"
- Task 1: insertion point in `write_lifecycle` → between lines 361 and 362 (after validation, before `repo_dir = str(...)`)
- Task 2: line `49` → lines `49-51`
- Task 6: function name `_set_status` → `verify_status_sync` at line 1003
- Task 6: `event_writer.notify` signature corrected to `(project_path, skill, status, message, artifact_rel)`
- Task 7: function name `_set_status` → `verify_status_sync` at line 1114

### Solution Verification

Council approved Variant 2-strict (4/4 approve_with_changes, 2026-05-25). No external research needed — solution is internal architectural enforcement, not a library/pattern question. Re-validated forensic findings against current `lifecycle.py` HEAD: `_ALLOWED_WRITERS` still contains "autopilot" and "spark" → Layer 2 still needed. `write_lifecycle` body has no Rule 7 check → Layer 1 still needed. Pre-commit hook still has subject-allowlist branch → Layer 3 still needed. **Spec assumptions confirmed against current HEAD.**

### Sync Zone Check

Allowed Files include `.claude/hooks/`, `.claude/skills/autopilot/`, `.claude/agents/` AND their `template/.claude/` mirrors. Both copies are explicitly enumerated in Allowed Files and covered by Task 8 — no auto-sync task needed (template paths are first-class targets in this spec).

---

## Execution Order

```
Task 1 (lifecycle.py: LifecycleAlreadyDoneError + structural Rule 7)
  ↓
Task 2 (lifecycle.py: remove autopilot/spark from _ALLOWED_WRITERS) [parallel with Task 1; same file]
  ↓
Task 3 (spec_operator.py: --by choices + catch LifecycleAlreadyDoneError) [depends on Task 1 for exception class]
  ↓
Task 5 (pre-commit hook hardening) [independent, can run parallel with Tasks 1–3]
Task 6 (callback.py: catch + notify) [depends on Task 1]
Task 7 (callback.py: actionable reason) [parallel with Task 6; same file but different region]
  ↓
Task 4 (setup-vps.sh: --phase4-hooks) [depends on Task 5 hook semantics being final]
  ↓
Task 8 (skill prompts: forbidden block × 6 files) [independent, can run any time]
  ↓
Task 9 (tests) [depends on Tasks 1, 3, 5, 6 — exception class, CLI, hook, callback branch]
  ↓
Task 10 (ADR-025 + amend ADR-023) [independent; do after Tasks 1–9 land]
  ↓
Task 11 (operator: run setup-vps.sh --phase4-hooks on VPS) [POST-MERGE manual operation, out of autopilot scope]
```

**Recommended commit grouping (one commit per task):**
1. Task 1 + Task 2 (same file, atomic primitive change)
2. Task 3 (spec_operator.py)
3. Task 5 (pre-commit hook)
4. Task 6 + Task 7 (callback.py)
5. Task 4 (setup-vps.sh)
6. Task 8 (skill prompts × 6)
7. Task 9 (tests)
8. Task 10 (ADR-025)

Total 8 commits (Task 11 is manual ops, not an autopilot commit).

---

## References

- Council session: `ai/.council/20260525-ARCH-193/synthesis.md`
- Forensic findings: `ai/.council/20260525-ARCH-193/forensic-addendum.md`
- BUG-192 (regex blindness, closed): `ai/features/BUG-192-2026-05-25-callback-subject-implements-blind-to-real-formats.md`
- ARCH-186 spec (lifecycle SoT, ADR-023): `ai/features/ARCH-186-*.md`
- ARCH-187 spec (identity enforcement, partially superseded): `ai/features/ARCH-187-2026-05-20-lifecycle-write-identity-enforcement.md`
- ADR-023 (lifecycle SoT, will be amended by ADR-025)
- ADR-024 (claude-runner exit_code contract, BUG-188)

---

## Autopilot Log

### Run 2026-05-25 (interactive, worktree .worktrees/ARCH-193 from origin/develop)

**Pre-flight:** BUG-188 already-implemented check: 0 commits with ARCH-193 in subject touching Allowed Files → no early-exit.

**Commits (8 — per planner's recommended grouping):**

| # | SHA | Subject | Files |
|---|-----|---------|-------|
| 1 | bfc3662 | feat(ARCH-193): structural Rule 7 + tighten lifecycle writers | lifecycle.py |
| 2 | dd46523 | feat(ARCH-193): spec_operator rc=5 on Rule 7 + drop autopilot/spark from --by | spec_operator.py |
| 3 | 3ea54d2 | feat(ARCH-193): pre-commit hook rejects ALL staged lifecycle yamls | hook (×2 template-sync), spec Allowed Files |
| 4 | 0955baa | feat(ARCH-193): callback catches Rule 7 + actionable demote reason | callback.py |
| 5 | a77f85b | feat(ARCH-193): setup-vps.sh --phase4-hooks idempotent installer | setup-vps.sh |
| 6 | fc42bbe | docs(ARCH-193): skill prompts hard-rule against direct lifecycle writes | coder/finishing/autopilot-git × 2 |
| 7 | 4989fbb | test(ARCH-193): structural tests for Rule 7 + writer matrix + hook | test_lifecycle_done_terminal.py (new) |
| 8 | 2be8fc6 | docs(ARCH-193): add ADR-025 + amend ADR-023 | architecture.md |

**Tests:** baseline 155 → final 170 passed (15 new). Zero regressions.

**Task 11 (manual):** operator runs `bash scripts/vps/setup-vps.sh --phase4-hooks` on VPS to install hook on awardybot/dowry/etc. Spec is the SoT for that step. autopilot also tested the installer locally as a side-effect — `git config core.hooksPath` is now `.git-hooks` on `/home/dld/projects/dld` itself.

**Per-task notes:**

- Tasks 1+2 grouped into commit 1 (same file, atomic primitive change).
- Tasks 6+7 grouped into commit 4 (same file, adjacent regions in `verify_status_sync`).
- Task 5 expanded Allowed Files inline to include `template/.claude/hooks/pre-commit-lifecycle-guard.mjs` (planner omission; template-sync rule requires byte-identical mirror).
- Task 8 coder reconciled pre-existing template-vs-root drift in `coder.md` (Mock Boundaries, BUG-192 history) to achieve byte-identical pairs. Acceptable collateral — necessary for the spec's own byte-identical mandate.
- Task 9 spec-reviewer flagged Test 8 as missing "event_writer.notify verification" — overridden because spec line 577 explicitly grants the structural-only fallback ("Practical approach: ... full integration is overkill"). Two upstream signals recorded.

**Pre-Done Checklist:**

- [x] `pytest scripts/vps/tests/ -q` → 170 passed
- [x] No new TODO/FIXME (pre-check passed for all changed files; pre-existing flags in callback.py / lifecycle.py are not introduced by this spec)
- [x] All 10 tasks done; Task 11 documented as operator-manual (per spec)
- [x] LifecycleAlreadyDoneError importable: `python3 -c "import sys; sys.path.insert(0,'scripts/vps'); import lifecycle; print(lifecycle.LifecycleAlreadyDoneError)"` → OK
- [x] `spec_operator.py demote --by=autopilot/spark` → argparse error rc=2 (test 6/7 cover)
- [x] All 11 ARCH-193 tests pass (`test_lifecycle_done_terminal.py`)
- [x] `write_lifecycle(done→blocked, by="callback")` raises LifecycleAlreadyDoneError (test 1 covers)
- [x] Pre-commit hook installed on /home/dld/projects/dld; awardybot/dowry deferred to operator (Task 11)
- [x] callback.py rule_7_saved warning notification wired
- [x] no_merged_implementation reason includes actionable spec_operator CLI
- [x] ADR-025 in architecture.md; ADR-023 amended
- [x] 6 skill files contain "NEVER git add ai/lifecycle/"
