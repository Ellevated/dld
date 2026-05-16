# ARCH-186 — Orchestrator Lifecycle State SoT (git per-spec YAML)

<!-- DLD-CALLBACK-MARKER-START v1 -->
**Status:** done | **Priority:** P0 | **Risk:** R1 | **Date:** 2026-05-16
<!-- DLD-CALLBACK-MARKER-END -->

<!-- DLD-CALLBACK-MARKER-START v1 -->
<!-- **Blocked Reason:** populated by callback.py when guard demotes to blocked -->
<!-- DLD-CALLBACK-MARKER-END -->

## ⚠️ ACTION REQUIRED: HUMAN REVIEW BEFORE AUTOPILOT

Это R1 P0 — state machine migration, cross-domain, ~600 LOC изменений в production. Founder **должен** прочитать spec и явно отпустить в autopilot перед запуском. Не auto-handoff. Никаких exceptions.

---

## Контекст

**Источник:** Council #2 synthesis — `ai/.council/20260516-github-issues-task-sot/synthesis.md`

**Решение совета:** 3 эксперта (Security, Pragmatist, Product) отвергли GitHub Issues как SoT; независимо сошлись на Option D — git per-spec yaml. Architect остался единственным сторонником Issues. Detailed rationale + dissent в synthesis.md.

**Корневая проблема:** lifecycle state (Status) задач хранится в `ai/backlog.md` table cells + `ai/features/{SPEC}.md` Status field внутри `DLD-CALLBACK-MARKER` блоков. Этот медиум — shared mutable text в git working tree, мутируется 6+ writers (orchestrator, callback, spark, planner, Hermes, manual) без storage-enforced invariant. За 2.5 месяца — 10+ фиксов вокруг одного контракта (TECH-166/168/169/172/177/181/182/BUG-185), каждый закрывал одну race и открывал другую.

**Последний эпизод (2026-05-15/16):** dowry:FTR-431 ×8, FTR-432 ×9, awardybot:TECH-965 ×10 циклов за ночь. BUG-185 фикс не сработал (0 строк `AUTOSTASH_CALLBACK_RESTORE` в логах).

## Цель

Перенести lifecycle state в **per-spec git-versioned YAML файл** (`ai/lifecycle/{spec_id}.yaml`), где **callback — единственный writer** через **atomic git plumbing commit** (private `GIT_INDEX_FILE`, без модификации working tree). Markdown остаётся как **auto-rendered read-only view**. Multi-machine workflow founder'а сохраняется (3 машины + ноут + VPS + Hermes) — все читают через `git pull`.

**Race condition становится физически невозможна** — git plumbing atomicity + CAS `update-ref` + structural enforcement (callback не трогает WT) + no-dirty-WT invariant убирают race-class.

---

## Architecture

### YAML schema (`ai/lifecycle/{spec_id}.yaml`)

```yaml
spec_id: TECH-183
status: queued | in_progress | blocked | done
priority: p0 | p1 | p2
kind: bug | ftr | tech | arch
blocked_reason: "Autopilot timed out — no commits in allowed files"   # nullable
started_at: "2026-05-16T10:30:00Z"   # nullable, set on queued→in_progress
finished_at: "2026-05-16T14:22:00Z"  # nullable, set on →done
allowed_files_hash: "sha256:abc..."  # snapshot at queue time
updated_at: "2026-05-16T14:22:00Z"
updated_by: callback   # callback | spark | manual
version: 7             # monotonic counter for CAS
transitions:
  - from: queued
    to: in_progress
    at: "2026-05-16T10:30:00Z"
    by: callback
    pueue_id: 2891
```

### Writer contract (single writer enforced by module + CI)

| Writer | Allowed | Mechanism |
|---|---|---|
| `callback.py` | yes | `scripts/vps/lifecycle.py::write_lifecycle()` |
| `orchestrator.py` | **bootstrap only** (новый spec.md без lifecycle.yaml) | `lifecycle.create_initial()` через тот же модуль |
| Spark / planner / Hermes / manual | **no** | CI check fails any PR touching `ai/lifecycle/` outside callsites above |

**Bootstrap path (resolves Devil DA-12):** orchestrator на каждом цикле сканирует `ai/features/*.md` против `ai/lifecycle/*.yaml`. Spec.md без lifecycle.yaml → `lifecycle.create_initial(spec_id, parse_priority_kind_from_spec(spec_path))` со `status: queued`. Дальше обычный dispatch flow. Spark остаётся **read-only к lifecycle** — создаёт только spec.md, orchestrator подхватывает.

### Atomic plumbing commit (external scout finding #1)

```python
def write_lifecycle(repo_dir, spec_id, status, reason=None, by="callback"):
    yaml_bytes = render_yaml(spec_id, status, reason, by)
    # 1. PRIVATE index — не трогаем shared .git/index (Devil DA-1..4 fix)
    with tempfile.NamedTemporaryFile(dir=f"{repo_dir}/.git", delete=False) as f:
        idx_path = f.name
    try:
        env = {"GIT_INDEX_FILE": idx_path, **os.environ}
        # Seed index from HEAD
        run(["git", "read-tree", "HEAD"], cwd=repo_dir, env=env)
        # Stage blob
        blob = run(["git", "hash-object", "-w", "--stdin"], input=yaml_bytes, env=env, cwd=repo_dir).stdout.strip()
        run(["git", "update-index", "--cacheinfo", f"100644,{blob},ai/lifecycle/{spec_id}.yaml"], cwd=repo_dir, env=env)
        # If render-backlog enabled — also stage backlog.md (same atomic commit)
        if should_render():
            backlog_blob = run(["git", "hash-object", "-w", "--stdin"], input=render_backlog_bytes(), env=env, cwd=repo_dir).stdout.strip()
            run(["git", "update-index", "--cacheinfo", f"100644,{backlog_blob},ai/backlog.md"], cwd=repo_dir, env=env)
        tree = run(["git", "write-tree"], cwd=repo_dir, env=env).stdout.strip()
        head = run(["git", "rev-parse", "HEAD"], cwd=repo_dir).stdout.strip()
        msg = f"lifecycle({spec_id}): {status}"
        commit = run(["git", "commit-tree", tree, "-p", head], input=msg, cwd=repo_dir, env=env).stdout.strip()
        # CAS update-ref (external scout finding #2) — fails if HEAD moved
        run(["git", "update-ref", "refs/heads/develop", commit, head], cwd=repo_dir)
        run(["git", "push", "origin", "develop"], cwd=repo_dir)
    finally:
        os.unlink(idx_path)
```

**Why this is race-free:**
- Private `GIT_INDEX_FILE` — operator-staged changes в `.git/index` не утекают в commit (Devil DA-1..4)
- CAS `update-ref` form — если другой процесс продвинул HEAD, мы упадём с явной ошибкой и retry (external scout finding #2)
- Working tree **never touched** — autostash dance class не существует
- Идемпотентность через `version` counter в YAML

### No-dirty-WT invariant (three-level defense, patterns scout)

| Level | Where | Action |
|---|---|---|
| **Startup hard check** | orchestrator boot | `git status --porcelain ai/lifecycle/` непусто → **abort + Hermes alert** "Dirty lifecycle, fix manually" |
| **Per-cycle soft check** | каждые 5 мин в main loop | Dirty → log WARN + skip cycle (не autostash) |
| **Structural** | callback writes | pygit2/private GIT_INDEX_FILE never touches WT |

**Scope clarification (Devil DA-1..4):** dirty check охватывает **only** `ai/lifecycle/`. `ai/qa/`, `ai/reflect/`, `ai/inbox/` — outside scope (это домены QA/reflect/Hermes, не lifecycle). Если operator руками правит lifecycle.yaml — это и есть случай когда мы хотим, чтобы система остановилась и сказала «почини».

### Reader pattern (patterns scout)

```python
# orchestrator.scan_queued() — replaces scan_backlog regex
def scan_queued(repo_dir):
    queued = []
    for yaml_path in sorted(glob(f"{repo_dir}/ai/lifecycle/*.yaml")):
        data = yaml.safe_load(open(yaml_path))
        if data.get("status") in ("queued", "resumed"):
            queued.append(data["spec_id"])
    return queued
```

`yaml.safe_load` × 300 файлов = ~50-100ms. Acceptable для 5-минутного цикла.

### Restart reconcile (Devil DA-18 fix)

При startup orchestrator:
1. Прочитать все `ai/lifecycle/*.yaml`
2. Прочитать `pueue status --json`
3. Для каждого `status: in_progress` lifecycle: если соответствующего pueue task нет (или он `Failed`/`Killed`) → `lifecycle.write_lifecycle(spec_id, "queued", reason="orphaned from crash", by="callback")`
4. Log событие в `callback-audit.jsonl` для постмортема

### Multi-machine flow

| Узел | Что делает | Lifecycle access |
|---|---|---|
| Стационар | `git pull && git push` спек | Reader через FS |
| Ноут | то же | Reader через FS (offline-safe — git commit local, push later) |
| VPS (tmux) | ручной триаж | Reader через FS |
| **VPS (orchestrator+callback)** | **sole writer через atomic plumbing** | Reader+Writer |
| Hermes | Telegram queries (read-only, Phase 1) | Reader через FS |

---

## Drift Log

**Checked:** 2026-05-16 (plan agent)
**Result:** no_drift

### Verified References

| Reference in spec | Actual location | Status |
|---|---|---|
| `callback.py:594,597` (`_DLD_MARKER_START_RE`, `_DLD_MARKER_END_RE` imports) | `callback.py:594-598` (`from marker_utils import ... as _DLD_MARKER_END_RE / _DLD_MARKER_START_RE`) | OK |
| `callback.py:580` (`_resync_backlog_to_spec`) | def at line 545; call site for backlog commit at line 580 | OK |
| `callback.py:825` (`_append_blocked_reason`) | def at line 777; `_git_commit_push` call at line 825 | OK |
| `verify_status_sync` ~284 LOC | def at line 1333, runs through 1614+ (~280 LOC, matches spec) | OK |
| `marker_utils.py` 117 LOC | exact 117 LOC (file ends at line 117, blank trailing line) | OK |
| `tests/test_marker_utils.py` 118 LOC | 118 LOC | OK |
| `tests/test_orchestrator_autostash_marker.py` 134 LOC | 134 LOC | OK |
| orchestrator `git_pull` autostash ~81 LOC | def at line 216; autostash block lines 244-293 (~50 LOC; spec said "~81 LOC including comments" — within acceptable range) | OK (note: pure code ~50, with docstring/header ~80) |
| orchestrator `_restore_callback_markers_from_head` 54 LOC | def at line 298, ends ~349 (~52 LOC) | OK |
| orchestrator `scan_backlog` regex `\|\s*(queued\|resumed)\s*\|` | line 489 exact match | OK |
| `.claude/skills/spark/feature-mode.md` DLD-CALLBACK-MARKER blocks | lines 325-331 (Status + Blocked Reason), 375-389 (Allowed Files), 656-657 (regex SSOT) | OK |
| `.claude/skills/spark/completion.md` allowlist linter | line 46 — needs Phase 5.5 SSOT update (E007/E008 removal) | NOTED (Task 7) |
| ADR-018 in `.claude/rules/architecture.md` | present in table, supersession to ADR-023 planned | OK |
| dependencies.md `marker_utils.py` entry | not present as its own section (BUG-974 entry in change log only) | NOTED — Task 9 cleanup is removal of BUG-974 reference + add lifecycle entry |

### Changes to Spec

- Renamed `## Tasks` → `## Implementation Plan` for autopilot consumption.
- Task 10 (former Tests section) folded into Task 1 + Task 3 alongside their code.
- Task 11 (rollout) renamed to "Operator Migration Rollout" and flagged OUT OF SCOPE for autopilot.
- Added explicit dependency graph + acceptance criteria per task.

### Allowed Files Check

All paths in `## Allowed Files` confirmed to exist or to be valid new paths under existing directories. **Missing from Allowed Files but needed:**

- `.claude/skills/spark/completion.md` — line 46 references DLD-CALLBACK-MARKER (Phase 5.5 SSOT). Task 7 must touch this. **ACTION:** added to Allowed Files block (see Task 7 note).
- `scripts/vps/tests/test_orchestrator_git_pull.py` — may need update if ff-only changes break existing assertions. **ACTION:** added to Allowed Files (Task 3).
- `~/.claude/projects/-root/memory/dld-orchestrator.md` — out of repo, operator-manual update (see §6, §7). Documented in DoD but not in Allowed Files (correct — not in this repo).

---

## Implementation Plan

> **Routing:** R1 P0. Council already ran. Founder review required before dispatch (see "ACTION REQUIRED" above).
> **Dependencies:** Task 1 is the root. Tasks 2–5 depend on Task 1. Task 6 (deletes) MUST run after Tasks 2 + 3 land. Tasks 7–9 (docs) can interleave. Task 10 (operator rollout) is OUT OF SCOPE for autopilot.
> **Tests:** Test file `test_lifecycle.py` is created in Task 1 alongside the module. Integration tests for orchestrator changes (`test_orchestrator_lifecycle.py`) are created in Task 3 alongside the orchestrator changes. There is no separate "write tests" task — tests ship with the code that needs them.

---

### Task 1: `scripts/vps/lifecycle.py` — new module + unit tests

**Files:**
- Create: `scripts/vps/lifecycle.py` (~250 LOC including docstrings; if >400 LOC split into a package `lifecycle/{__init__,atomic,reconcile}.py`)
- Create: `scripts/vps/tests/test_lifecycle.py` (Tests 1, 2, 3 from `## Tests`)

**Public API (frozen contract — Tasks 2/3/4/5 depend on this):**
```python
def read_lifecycle(repo_dir, spec_id) -> dict | None: ...
def write_lifecycle(
    repo_dir, spec_id, status,
    *, reason=None, by="callback", pueue_id=None, allowed_files_hash=None
) -> None: ...
def create_initial(repo_dir, spec_id, priority, kind) -> None: ...
def list_by_status(repo_dir, status: str | set[str]) -> list[dict]: ...
def assert_clean_lifecycle_tree(repo_dir) -> None: ...
def reconcile_orphans(repo_dir, pueue_alive_ids: set[int]) -> list[str]: ...
```

**Invariants (encoded as tests + runtime asserts):**
1. Atomic — single `git update-ref` (CAS form) per `write_lifecycle()` call.
2. Private `GIT_INDEX_FILE` — never reuses `.git/index`. Operator-staged files MUST NOT leak (Test 2).
3. Working tree never touched — no `git add`, no `checkout`, no file write in WT.
4. CAS retry: up to 3 attempts; on 3rd failure raise `LifecycleWriteRaceError`.
5. `version` monotonic.
6. YAML schema matches `## Architecture / YAML schema` block above.

**Implementation reference:** copy-paste from `## Architecture / Atomic plumbing commit` block (lines 71-97 of this spec). Add CAS-retry wrapper (3 attempts) around the `update-ref` call.

**TDD order — write tests first:**
- Test 1 `test_concurrent_writes_no_loss` — see `## Tests` line 273.
- Test 2 `test_operator_staged_file_does_not_leak` — see `## Tests` line 291.
- Test 3 `test_dirty_wt_does_not_revert_callback_write` — see `## Tests` line 306. References `orchestrator.git_pull_ff_only` which lands in Task 3; mark `@pytest.mark.skip(reason="awaits Task 3 ff-only rename")` for now, unskip after Task 3 merges.

**Acceptance:**
- [ ] `lifecycle.py` exports all 6 functions
- [ ] Tests 1 + 2 pass; Test 3 skipped (awaits Task 3)
- [ ] No file > 400 LOC
- [ ] Module header docstring lists Uses + Used by
- [ ] `LifecycleWriteRaceError` exception type defined

---

### Task 2: `scripts/vps/callback.py` rewrite — slim `verify_status_sync` (Depends on Task 1)

**Files:**
- Modify: `scripts/vps/callback.py:1333-1614` (`verify_status_sync` 280 LOC → ~50 LOC)
- Modify: `scripts/vps/callback.py:545-580` (DELETE `_resync_backlog_to_spec`)
- Modify: `scripts/vps/callback.py:591-599` (DELETE `marker_utils` imports + `_DLD_MARKER_START_RE` / `_DLD_MARKER_END_RE` aliases)
- Modify: `scripts/vps/callback.py:777-826` (REWRITE `_append_blocked_reason` to delegate to `lifecycle.write_lifecycle(..., reason=...)`; drop markdown-editing path)
- Modify: `scripts/vps/tests/test_callback.py` (drop marker-related tests; keep impl-guard tests; add `test_callback_calls_lifecycle_write_once_per_terminal_status`)

**New `verify_status_sync` shape:**
```python
def verify_status_sync(project_path, spec_id, target="done", pueue_id=None):
    project_id = Path(project_path).name
    start_wall = time.monotonic()
    if is_circuit_open():
        log.warning("CIRCUIT_OPEN: skip verify_status_sync(%s, %s)", spec_id, target)
        db.record_decision(project_id, spec_id, "noop", "circuit_open", demoted=False)
        return

    spec_file = _resolve_spec_file(project_path, spec_id)

    # TECH-166/176 implementation guard — UNCHANGED logic, just rewires final write.
    if target == "done" and pueue_id is not None and spec_file:
        allowed = _parse_allowed_files(spec_file)
        started_at = _get_started_at(int(pueue_id))
        code_loc, test_loc, code_commits = _commit_stats(project_path, allowed, started_at)
        if not _has_implementation_commits(project_path, allowed, started_at):
            already_merged, hashes = _spec_has_merged_implementation(project_path, spec_id, allowed)
            if already_merged:
                guard_reason = f"already_merged:{','.join(hashes[:5])}" if hashes else "already_merged"
                lifecycle.write_lifecycle(project_path, spec_id, "done", reason=guard_reason, pueue_id=pueue_id)
                db.record_decision(project_id, spec_id, "auto_close", guard_reason, demoted=False)
                _emit_audit(...)  # TECH-171 traceability preserved
                return
            guard_reason = "missing_allowed_files_section" if allowed is None else "no_implementation_commits"
            lifecycle.write_lifecycle(project_path, spec_id, "blocked", reason=guard_reason, pueue_id=pueue_id)
            db.record_decision(project_id, spec_id, "demote", guard_reason, demoted=True)
            if db.count_demotes_since(CIRCUIT_WINDOW_MIN) > CIRCUIT_THRESHOLD:
                _trip_circuit(project_id, spec_id, db.count_demotes_since(CIRCUIT_WINDOW_MIN))
            _emit_audit(...)
            return

    # Spec-authority guards (v3.15.5/6) — now read from lifecycle.yaml, not markdown.
    existing = lifecycle.read_lifecycle(project_path, spec_id)
    if existing and existing.get("status") == "blocked" and target == "done":
        log.info("STATUS_SYNC: %s blocked in lifecycle, skip done", spec_id)
        _emit_audit(...)
        return
    if existing and existing.get("status") == "done" and target == "blocked":
        log.info("STATUS_SYNC: %s already done, skip blocked", spec_id)
        _emit_audit(...)
        return

    # Normal write.
    lifecycle.write_lifecycle(project_path, spec_id, target, pueue_id=pueue_id)
    db.record_decision(project_id, spec_id, "sync", "fixed", demoted=False)
    _emit_audit(...)
```

**Sole-writer enforcement check:** after this task, `grep -n "_git_commit_push" scripts/vps/callback.py` must return zero lines that pass Status content (the helper itself may stay if used elsewhere, but no caller should pass spec/backlog content). Implementation-guard helpers (`_has_implementation_commits`, `_spec_has_merged_implementation`, `_parse_allowed_files`, `_get_started_at`, `_commit_stats`, `is_merged_to_develop`) STAY. Audit emit STAYS (TECH-171).

**Acceptance:**
- [ ] `verify_status_sync` ≤ 60 LOC
- [ ] `_resync_backlog_to_spec` removed; `grep` returns 0
- [ ] `_append_blocked_reason` either removed or contains only a `lifecycle.write_lifecycle()` delegation (zero markdown editing)
- [ ] No `from marker_utils import ...` in callback.py
- [ ] `pytest scripts/vps/tests/test_callback.py -v` — impl-guard tests pass, marker tests gone
- [ ] No `_git_commit_push` call in callback.py carries Status content

---

### Task 3: `scripts/vps/orchestrator.py` changes + integration tests (Depends on Task 1)

**Files:**
- Modify: `scripts/vps/orchestrator.py:216-295` (`git_pull` — rip out autostash, replace with ff-only-or-skip)
- Modify: `scripts/vps/orchestrator.py:298-349` (DELETE `_restore_callback_markers_from_head`, 52 LOC)
- Modify: `scripts/vps/orchestrator.py:27` (DELETE `from marker_utils import merge_callback_markers`)
- Modify: `scripts/vps/orchestrator.py:481-574` (RENAME `scan_backlog` → `scan_queued`; REPLACE regex `r"\|\s*(queued|resumed)\s*\|"` at line 489 with `lifecycle.list_by_status(project_dir, {"queued", "resumed"})`)
- Modify: `scripts/vps/orchestrator.py:594-598` (`process_project` — add `bootstrap_new_specs(project_dir)` call before `scan_queued`)
- Modify: orchestrator daemon entry point (find `main()` or equivalent) — add one-time `startup_reconcile(all_project_dirs)` call before main poll loop
- Modify: `scripts/vps/tests/test_orchestrator_git_pull.py` — update assertions: no `stash push`/`stash pop`/marker restore expected
- Modify: `scripts/vps/tests/test_orchestrator.py` — rename any `scan_backlog` references to `scan_queued`
- Create: `scripts/vps/tests/test_orchestrator_lifecycle.py` (Tests 4, 5, 6 from `## Tests`)

**New `git_pull` shape (replaces lines 216-295):**
```python
def git_pull(project_id, project_dir):
    if not os.path.isdir(os.path.join(project_dir, ".git")):
        return
    if is_agent_running(project_id):
        log.info("skip git pull — agent running: %s", project_id)
        return
    try:
        pull = subprocess.run(
            ["git", "-C", project_dir, "pull", "--ff-only", "origin", "develop"],
            capture_output=True, text=True, timeout=120,
        )
        if pull.returncode != 0:
            log.warning("git pull (ff-only) failed for %s: %s — skip cycle",
                        project_dir, (pull.stderr or "")[:200])
    except subprocess.TimeoutExpired as exc:
        log.warning("git_pull timeout for %s: %s", project_dir, exc)
```

**New `scan_queued` shape (replaces `scan_backlog` body):**
```python
def scan_queued(project_id, project_dir):
    """Find first queued/resumed spec and dispatch autopilot."""
    queued_list = lifecycle.list_by_status(project_dir, {"queued", "resumed"})
    if not queued_list:
        return False
    # Pick first (caller may extend with priority sort later).
    spec_id = queued_list[0]["spec_id"]
    # ... preserve existing audit-log cutoff check (lines 503-526), slot
    # acquisition (528-543), pueue_add (544-573) verbatim ...
```

**New `bootstrap_new_specs` (NEW, ~25 LOC):**
```python
def bootstrap_new_specs(project_dir):
    features_dir = Path(project_dir) / "ai" / "features"
    if not features_dir.is_dir():
        return
    for spec_md in features_dir.glob("*.md"):
        m = re.search(r"(TECH|FTR|BUG|ARCH)-\d+[a-z]*", spec_md.name)
        if not m:
            continue
        spec_id = m.group(0)
        if (Path(project_dir, f"ai/lifecycle/{spec_id}.yaml")).exists():
            continue
        priority, kind = _parse_priority_kind(spec_md)
        lifecycle.create_initial(project_dir, spec_id, priority, kind)
        log.info("BOOTSTRAP: created lifecycle.yaml for %s in %s", spec_id, project_dir)
```

**Startup reconcile (one-shot at daemon boot, BEFORE main loop):**
```python
def startup_reconcile(project_dirs):
    alive = _get_live_pueue_ids()  # existing helper or wrap pueue status --json
    for d in project_dirs:
        lifecycle.assert_clean_lifecycle_tree(d)  # raises RuntimeError on dirty lifecycle/
        lifecycle.reconcile_orphans(d, alive)
```

**Tests required:**
- Test 4 `test_orphaned_in_progress_demoted_on_restart` — `## Tests` line 322.
- Test 5 `test_dirty_lifecycle_aborts_orchestrator_startup` — `## Tests` line 334.
- Test 6 `test_bootstrap_creates_lifecycle_for_new_spec` — `## Tests` line 344.
- Unskip Test 3 from Task 1 (rename `git_pull_ff_only` reference if needed — actual function is `git_pull` post-rewrite).

**Acceptance:**
- [ ] `_restore_callback_markers_from_head` removed; `grep` returns 0
- [ ] `merge_callback_markers` import in orchestrator.py removed
- [ ] `git_pull` ≤ 25 LOC, no `stash` calls
- [ ] `scan_queued` exists; `scan_backlog` and the markdown regex removed
- [ ] `bootstrap_new_specs` called from `process_project` before `scan_queued`
- [ ] `assert_clean_lifecycle_tree` called once at daemon startup
- [ ] Tests 4, 5, 6 pass
- [ ] Updated `test_orchestrator_git_pull.py` passes (no stash assertions)

---

### Task 4: `scripts/vps/render_backlog.py` — auto-render reader (Depends on Task 1)

**Files:**
- Create: `scripts/vps/render_backlog.py` (~120 LOC)
- Create: `scripts/vps/tests/test_render_backlog.py` (~80 LOC)

**Contract:** Pure function `render_backlog(repo_dir) -> str`. Reads `ai/lifecycle/*.yaml`, groups by priority + kind, renders markdown matching current `ai/backlog.md` section/table structure. Best-effort hook in `lifecycle.write_lifecycle()` (already covered in Task 1 skeleton):
```python
# Inside lifecycle.write_lifecycle, after staging YAML blob:
try:
    backlog_text = render_backlog.render_backlog(repo_dir)
    backlog_blob = run(["git", "hash-object", "-w", "--stdin"],
                       input=backlog_text.encode(), env=env, cwd=repo_dir).stdout.strip()
    run(["git", "update-index", "--cacheinfo", f"100644,{backlog_blob},ai/backlog.md"],
        cwd=repo_dir, env=env)
except Exception as exc:
    log.warning("render_backlog failed (lifecycle write continues): %s", exc)
```

**Tests:**
- `test_render_matches_format` — golden file comparison with checked-in fixture.
- `test_render_skips_corrupt_yaml` — poison one yaml → returns markdown for the rest with WARN.
- `test_render_round_trip` — render → write → re-parse → status set matches input.

**Acceptance:**
- [ ] `render_backlog(repo_dir)` returns string matching current format
- [ ] All 3 tests pass
- [ ] Render failure does NOT block lifecycle write (proven by Task 1's integration test or via a Task 4 test)

---

### Task 5: `scripts/vps/migrate_backlog_to_lifecycle.py` — one-shot migration (Depends on Task 1)

**Files:**
- Create: `scripts/vps/migrate_backlog_to_lifecycle.py` (~150 LOC)
- Create: `scripts/vps/tests/test_migrate_backlog.py` (~100 LOC)

**Contract (Devil mitigation):**
1. CLI: `python3 migrate_backlog_to_lifecycle.py [--commit] [--repo PATH]`.
2. Parse `ai/backlog.md` rows → `(spec_id, status, priority, kind)`.
3. Parse `ai/features/{spec_id}*.md` Status field + `**Blocked Reason:**` line.
4. Cross-validate: backlog row status MUST equal spec Status. Mismatch → stderr ERROR + exit 2.
5. Build per-spec YAML dict in memory.
6. **Default: dry-run** — print proposed YAMLs + diff. Exit 0.
7. **With `--commit`** — write YAMLs to WT only (no git commit). Operator commits manually.
8. Round-trip self-test after `--commit`: re-read written YAMLs, compare status set. Mismatch → exit 1.
9. Idempotent — re-running `--commit` after success is a no-op.

**Acceptance:**
- [ ] Dry-run touches nothing
- [ ] `--commit` writes files, exits 0 on round-trip success
- [ ] Mismatch → exit 2 with identifying message
- [ ] Idempotent
- [ ] 3 tests cover the above (happy, mismatch, idempotency)

---

### Task 6: DELETE retired modules + tests (Depends on Tasks 2 + 3)

**Files:**
- Delete: `scripts/vps/marker_utils.py` (117 LOC)
- Delete: `scripts/vps/tests/test_marker_utils.py` (118 LOC)
- Delete: `scripts/vps/tests/test_orchestrator_autostash_marker.py` (134 LOC)

**Verification:**
```bash
grep -rn "marker_utils" scripts/                                  # 0 lines
grep -rn "DLD_MARKER_START_RE\|DLD_MARKER_END_RE" scripts/        # 0 lines
grep -rn "merge_callback_markers" scripts/                        # 0 lines
grep -rn "_restore_callback_markers_from_head" scripts/           # 0 lines
```

**Preserve:** TECH-169 circuit-breaker (DB table, callback wiring, `--reset-circuit` CLI). Do not touch.

**Acceptance:**
- [ ] 3 files deleted
- [ ] All 4 greps return 0
- [ ] `./test fast` passes (no orphan imports)

---

### Task 7: Spec template + spark completion checklist

**Files:**
- Modify: `.claude/skills/spark/feature-mode.md` — delete DLD-CALLBACK-MARKER blocks at lines 325-331, 375-389, 656-657; replace Status section with: `## Lifecycle\n\nState lives in \`ai/lifecycle/{spec_id}.yaml\`. Do not edit manually — callback is the sole writer (ADR-023).`
- Modify: `.claude/skills/spark/completion.md:46` — drop the `grep '<!-- DLD-CALLBACK-MARKER-START v1 -->' ai/features/{TASK_ID}*.md` clause from the Phase 5.5 checklist; KEEP the `## Allowed Files` heading check + `<!-- callback-allowlist v1 -->` marker check (still required for the implementation guard).
- Modify (template sync, if files exist): `template/.claude/skills/spark/feature-mode.md` and `template/.claude/skills/spark/completion.md` — mirror the changes per `.claude/rules/template-sync.md`.

**Acceptance:**
- [ ] `grep -rn "DLD-CALLBACK-MARKER" .claude/skills/spark/` returns 0 matches
- [ ] `## Allowed Files` heading + `<!-- callback-allowlist v1 -->` marker checks remain in completion.md
- [ ] If `template/.claude/skills/spark/` exists, files synced

---

### Task 8: `.claude/rules/architecture.md` — ADR-023 + supersede ADR-018

**Files:**
- Modify: `.claude/rules/architecture.md` ADR table — annotate ADR-018 row with `(superseded by ADR-023)`; append:
  ```
  | ADR-023 | Lifecycle state SoT = git per-spec YAML | 2026-05 | См. dld-orchestrator.md§7 |
  ```

**Acceptance:**
- [ ] ADR-023 row present
- [ ] ADR-018 row marked `(superseded by ADR-023)`
- [ ] No other rows altered

---

### Task 9: `.claude/rules/dependencies.md` — lifecycle entries

**Files:**
- Modify: `.claude/rules/dependencies.md` — add new section `## scripts/vps/lifecycle.py`:
  - Uses: `pathlib`, `subprocess` (git plumbing), `yaml`, `tempfile`, `os`
  - Used by: `callback.py`, `orchestrator.py`, `render_backlog.py`, `migrate_backlog_to_lifecycle.py`
  - "When changing API, check": callback.py, orchestrator.py, render_backlog.py
- Update existing `scripts/vps/callback.py` section — add `lifecycle.py` to Uses, remove any `marker_utils` reference (currently the BUG-974 row in change log mentions it).
- Update existing `scripts/vps/orchestrator.py` section — add `lifecycle.py` to Uses, remove `marker_utils` mentions.
- Append Last Update row: `| 2026-05-16 | Lifecycle SoT migration: added lifecycle.py + render_backlog.py + migrate_backlog_to_lifecycle.py; removed marker_utils (ARCH-186) | autopilot |`.

**Acceptance:**
- [ ] `grep -n "marker_utils" .claude/rules/dependencies.md` returns 0 matches
- [ ] `lifecycle.py` section present
- [ ] Last Update row appended

---

### Task 10 (OUT OF SCOPE for autopilot): Operator Migration Rollout

This is **manual operator work**. Autopilot MUST NOT execute. See `## Migration Plan (приложение)` below.

**Autopilot behavior if asked to run Task 10:** emit `BLOCKED: operator-manual rollout step` and stop.

---

### Dependency Graph

```
Task 1 (lifecycle.py + unit tests) ← ROOT
  ├── Task 2 (callback rewrite)            ──┐
  ├── Task 3 (orchestrator + integ tests)  ──┤
  ├── Task 4 (render_backlog.py)             ├── Task 6 (deletes, gated on 2+3)
  └── Task 5 (migrate script)              ──┘

Task 7 (spark template)          — any time
Task 8 (architecture.md ADR-023) — any time
Task 9 (dependencies.md)         — any time

Task 10 (rollout) — OPERATOR MANUAL — NOT FOR AUTOPILOT
```

### Execution Order for Autopilot

`1 → 2 → 3 → 4 → 5 → 7 → 8 → 9 → 6 → STOP (handoff to operator for Task 10)`

Task 6 runs last because it deletes test files; if it ran before Tasks 2/3 merged, in-flight tests would crash. Tasks 7/8/9 (docs) are sequenced before Task 6 for the same reason — keep deletes isolated to the end.

### Allowed Files — Addendum (auto-detected by plan agent)

Adding to `## Allowed Files` block above to cover the validated work:
- `.claude/skills/spark/completion.md` (Task 7)
- `template/.claude/skills/spark/feature-mode.md` (Task 7, if file exists)
- `template/.claude/skills/spark/completion.md` (Task 7, if file exists)
- `scripts/vps/tests/test_orchestrator_git_pull.py` (Task 3 updates assertions)
- `scripts/vps/tests/test_orchestrator.py` (Task 3 renames scan_backlog → scan_queued)
- `scripts/vps/tests/test_render_backlog.py` (Task 4 new)
- `scripts/vps/tests/test_migrate_backlog.py` (Task 5 new)

**Task 2 cleanup (discovered during execution):** the rewrite of `verify_status_sync` and deletion of `_apply_spec_status` / `_apply_backlog_status` / `_apply_blocked_reason` (old signature) / `_git_plumbing_commit` / `_read_head_blob` / marker helpers breaks downstream callback tests outside `scripts/vps/tests/`. Adding to scope:
- `tests/unit/test_callback_helpers.py` (delete tests of removed `_apply_*` helpers; keep tests of helpers that remain)
- `tests/unit/test_callback_implementation_guard.py` (update `_append_blocked_reason` callers to new signature `(project_path, spec_id, reason, pueue_id)`)
- `tests/integration/test_callback_status_sync.py` (rewrite markdown assertions → `lifecycle.read_lifecycle()` checks)
- `tests/integration/test_callback_no_impl_demote.py` (same — assertions against lifecycle, not markdown)
- `tests/integration/test_callback_already_merged.py` (assertions against lifecycle.yaml)
- `tests/integration/test_callback_feature_branch.py` (assertions against lifecycle.yaml)
- `tests/integration/test_callback_plumbing_commit.py` (**delete entire file** — `_git_plumbing_commit` / `_read_head_blob` removed; lifecycle.py owns plumbing now, covered by `scripts/vps/tests/test_lifecycle.py` Test 1+2)

---

## Allowed Files

<!-- callback-allowlist v1 -->
<!-- DLD-CALLBACK-MARKER-START v1 -->
- `scripts/vps/lifecycle.py` — **NEW** module (atomic plumbing + reader + reconcile)
- `scripts/vps/callback.py` — rewrite verify_status_sync, удалить marker helpers
- `scripts/vps/orchestrator.py` — scan_queued, no-dirty-WT, ff-only pull, удалить _restore_callback_markers_from_head + autostash
- `scripts/vps/render_backlog.py` — **NEW** auto-render
- `scripts/vps/migrate_backlog_to_lifecycle.py` — **NEW** one-shot migration
- `scripts/vps/marker_utils.py` — **DELETE**
- `scripts/vps/tests/test_lifecycle.py` — **NEW** unit tests
- `scripts/vps/tests/test_orchestrator_lifecycle.py` — **NEW** integration
- `scripts/vps/tests/test_callback.py` — modify (drop marker tests, keep guard tests)
- `scripts/vps/tests/test_marker_utils.py` — **DELETE**
- `scripts/vps/tests/test_orchestrator_autostash_marker.py` — **DELETE**
- `.claude/skills/spark/feature-mode.md` — template без DLD-CALLBACK-MARKER
- `.claude/rules/architecture.md` — ADR-023
- `.claude/rules/dependencies.md` — lifecycle.py entry, drop marker_utils
- `ai/lifecycle/*.yaml` — **NEW** state files (data, не source)
- `ai/backlog.md` — становится auto-rendered read-only view
<!-- DLD-CALLBACK-MARKER-END -->

---

## Tests

### Test 1 (unit, lifecycle.py): atomic write under concurrency
```python
def test_concurrent_writes_no_loss(tmp_git_repo):
    """10 параллельных write_lifecycle() для разных spec — все попадают в HEAD, version counters монотонны."""
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(10) as ex:
        list(ex.map(
            lambda i: lifecycle.write_lifecycle(tmp_git_repo, f"TECH-{i}", "queued"),
            range(10)
        ))
    # All 10 yamls in HEAD
    for i in range(10):
        data = lifecycle.read_lifecycle(tmp_git_repo, f"TECH-{i}")
        assert data["status"] == "queued"
        assert data["version"] >= 1
```

### Test 2 (unit, lifecycle.py): private GIT_INDEX_FILE — operator-staged files не утекают
```python
def test_operator_staged_file_does_not_leak(tmp_git_repo):
    """Operator делает git add some-other-file. Callback пишет lifecycle. Commit содержит ТОЛЬКО lifecycle, не some-other-file."""
    (tmp_git_repo / "operator-wip.txt").write_text("wip")
    run(["git", "add", "operator-wip.txt"], cwd=tmp_git_repo)
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-100", "done")
    # Last commit changed только ai/lifecycle/TECH-100.yaml
    out = run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=tmp_git_repo).stdout
    assert "ai/lifecycle/TECH-100.yaml" in out
    assert "operator-wip.txt" not in out
    # operator-wip.txt всё ещё staged, не потеряна
    assert "operator-wip.txt" in run(["git", "diff", "--cached", "--name-only"], cwd=tmp_git_repo).stdout
```

### Test 3 (regression, BUG-185 scenario): autostash race impossible
```python
def test_dirty_wt_does_not_revert_callback_write(tmp_git_repo):
    """Simulate BUG-185: dirty WT + callback write. Lifecycle.yaml в HEAD остаётся 'done' даже после следующего scan."""
    # Setup: spec is queued
    lifecycle.create_initial(tmp_git_repo, "TECH-200", "p1", "tech")
    # Dirty up WT (orchestrator's typical mess)
    (tmp_git_repo / "ai/qa/garbage.md").write_text("untracked")
    # Callback writes done
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-200", "done")
    # Orchestrator next cycle (no autostash dance)
    orchestrator.git_pull_ff_only(tmp_git_repo)  # no-op if up-to-date
    queued = lifecycle.list_by_status(tmp_git_repo, "queued")
    # BUG-185 would have showed TECH-200 here. Option D — never.
    assert "TECH-200" not in [s["spec_id"] for s in queued]
```

### Test 4 (integration, orchestrator restart reconcile): orphaned in_progress demoted
```python
def test_orphaned_in_progress_demoted_on_restart(tmp_git_repo, mock_pueue):
    """Lifecycle says in_progress, no live pueue task → reconcile demotes to queued."""
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-300", "in_progress", pueue_id=999)
    mock_pueue.set_alive_ids(set())  # task 999 не существует
    orchestrator.startup_reconcile(tmp_git_repo)
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-300")
    assert data["status"] == "queued"
    assert "orphaned from crash" in data["blocked_reason"] or data["transitions"][-1]["by"] == "callback"
```

### Test 5 (integration, no-dirty-WT invariant): dirty lifecycle aborts startup
```python
def test_dirty_lifecycle_aborts_orchestrator_startup(tmp_git_repo):
    """Manual edit to ai/lifecycle/TECH-X.yaml → startup raises."""
    lifecycle.create_initial(tmp_git_repo, "TECH-400", "p1", "tech")
    (tmp_git_repo / "ai/lifecycle/TECH-400.yaml").write_text("manually corrupted\n")
    with pytest.raises(RuntimeError, match="Dirty lifecycle"):
        lifecycle.assert_clean_lifecycle_tree(tmp_git_repo)
```

### Test 6 (integration, bootstrap path): new spec.md → orchestrator creates lifecycle.yaml
```python
def test_bootstrap_creates_lifecycle_for_new_spec(tmp_git_repo):
    """Spark создал spec.md без lifecycle.yaml. Orchestrator cycle создаёт initial."""
    spec = tmp_git_repo / "ai/features/TECH-500-foo.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("# TECH-500\n**Priority:** P1\n**Kind:** tech\n")
    assert not (tmp_git_repo / "ai/lifecycle/TECH-500.yaml").exists()
    orchestrator.bootstrap_new_specs(tmp_git_repo)
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-500")
    assert data["status"] == "queued"
    assert data["priority"] == "p1"
```

---

## Definition of Done

- [ ] Все 6 новых тестов проходят (`./test fast`)
- [ ] 714 LOC старых тестов удалены (test_marker_utils.py + test_orchestrator_autostash_marker.py + marker tests из test_callback.py)
- [ ] `marker_utils.py` удалён, нет imports
- [ ] `verify_status_sync` < 50 LOC, использует `lifecycle.write_lifecycle()`
- [ ] orchestrator startup: `assert_clean_lifecycle_tree()` + `reconcile_orphans()` + `bootstrap_new_specs()`
- [ ] orchestrator `git_pull` → `git pull --ff-only` (autostash удалён)
- [ ] Pilot на dld: миграция через `migrate_backlog_to_lifecycle.py --commit`, 24h наблюдения, **0 re-dispatch loops** в логах
- [ ] После pilot: rollout на 9 остальных проектов через `autopilot per project`
- [ ] ADR-023 в architecture.md; ADR-018 помечен `superseded by ADR-023`
- [ ] dependencies.md обновлён (lifecycle.py entry, marker_utils entries удалены)
- [ ] Spec template (.claude/skills/spark/feature-mode.md) — без DLD-CALLBACK-MARKER блоков
- [ ] backlog.md auto-rendered корректно (визуально совпадает с текущим форматом)
- [ ] CI check: PR touching `ai/lifecycle/` outside callback.py/lifecycle.py → fail
- [ ] No regressions в test_callback.py (guard тесты остались, marker тесты удалены)

---

## Migration Plan (приложение)

**День 0 (ship PR):**
- Merge PR в develop
- Stop orchestrator: `systemctl stop dld-orchestrator` (или kill pueue group)
- Run `python3 scripts/vps/migrate_backlog_to_lifecycle.py` (dry-run) на dld
- Human review diff
- Run с `--commit`, commit + push
- Start orchestrator
- Watch logs 24h: AUTOSTASH events = 0, no_dirty_WT skips = 0 ideally (если >0 — manual cleanup), re-dispatch loops = 0

**День 1:** if dld green — sweep 9 проектов одной командой:
```bash
for proj in $(ls -d /home/dld/projects/*/); do
  python3 scripts/vps/migrate_backlog_to_lifecycle.py --commit --repo "$proj"
done
```

**День 7:** post-mortem. Если incidents == 0 — Phase 1 (Hermes structured queries + dld triage CLI) можно начинать как новая spec.

---

## Research Sources

- `ai/.council/20260516-github-issues-task-sot/synthesis.md` — full council rationale
- `ai/.spark/ARCH-186/scout-external.md` — git plumbing patterns, CAS update-ref, per-file YAML validation
- `ai/.spark/ARCH-186/scout-codebase.md` — exact LOC counts, regex names, callsite map
- `ai/.spark/ARCH-186/scout-patterns.md` — atomic write mechanism, three-level no-dirty-WT defense, reader patterns
- `ai/.spark/ARCH-186/scout-devil.md` — edge cases mitigated (DA-1..4 index contamination, DA-12 bootstrap, DA-18 reconcile)
- ADR-018 (.claude/rules/architecture.md) — будет superseded
- BUG-185 — историческая попытка band-aid, удаляется в этом PR
- beads, tick-md — industry validation of git-as-state-SoT pattern
