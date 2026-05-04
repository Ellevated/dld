---
id: TECH-176
type: TECH
status: queued
priority: P1
risk: R1
created: 2026-05-04
---

# TECH-176 — IMPL_GUARD: detect "already merged before started_at" instead of demoting

**Status:** queued
**Priority:** P1
**Risk:** R1 (затрагивает callback decision flow для всех проектов)

---

## Problem

`_has_implementation_commits` в `callback.py` запускает `git log --all --since=<started_at> -- <allowed_files>`. Если работа по спеке **уже была смержена в `develop` ДО** `started_at` текущего autopilot-прогона, лог пуст → guard демоутит `done → blocked` с reason `no_implementation_commits`. Autopilot ничего не пишет, потому что писать нечего → следующий dispatch повторяет цикл.

**Live precedent (2026-05-03):**
- `TECH-169` (circuit-breaker): merged `8d8756a` + merge `66e3800` 02.05. Spec осциллировал `queued ↔ blocked` 4+ цикла, пока его не закрыли руками коммитом `97cf05c` (04.05). Оператор делал `--reset-circuit` 8 раз.
- TECH-170 добавил `git log --all` (видит feature-branches), но `--since=started_at` остался — поэтому случай "merged до started_at" не покрыт.

**Almost-detection уже есть:** callback логирует `STATUS_SYNC: <spec> — spec already done at HEAD, skipping blocked (work likely on feature branch); resync backlog`. Эта ветка срабатывает только если `**Status:**` в `develop:HEAD` уже `done`. Когда оператор флипает `blocked → queued` (для повторного прогона), статус в HEAD = `queued`, и логика проваливается в обычный demote.

---

## Goal

Guard различает три состояния, не два:

| Состояние | Текущая логика | Должно быть |
|---|---|---|
| Коммиты есть в окне `started_at`-now | `done` ✓ | `done` ✓ |
| Коммиты в Allowed Files есть в `develop` целиком, помечены `<spec_id>` в subject/merge | `blocked` (demote) | `done` (auto-close, не demote) |
| Коммитов нет вообще | `blocked` (demote) | `blocked` (demote) ✓ |

**Принцип:** `_has_implementation_commits` отвечает на вопрос «была ли реальная реализация этой спеки», а не «делал ли что-то autopilot за последний прогон».

---

## Allowed Files

<!-- callback-allowlist v1 -->

- `scripts/vps/callback.py`
- `tests/integration/test_callback_already_merged.py`
- `.claude/rules/architecture.md`

---

## Tasks

1. **Добавить helper `_spec_has_merged_implementation(project_path, spec_id, allowed_files) -> bool`** в `callback.py`:
   - `git log --all --oneline --grep="<spec_id>" -- <allowed_files>` — non-empty → `True`.
   - Дополнительно ищет merge-коммиты по pattern `Merge <spec_id>` в subject (для merge-only веток).
   - Возвращает `False` если grep пустой ИЛИ если allowed_files пуст.

2. **Wire в `verify_status_sync`:** перед `_trip_circuit + demote` развилкой — если `_has_implementation_commits` вернул `False` (no commits since started_at), но `_spec_has_merged_implementation` вернул `True` — это **auto-close**:
   - `verdict = "auto_close"` в callback_decisions (новый verdict, `demoted=0`).
   - Спека → `done` (через `_apply_spec_status` + `_apply_backlog_status`).
   - Лог: `IMPL_GUARD: <spec> — already merged in develop (commits: <hashes>) → auto-close to done`.
   - НЕ trip circuit, НЕ записывать demote.

3. **ADR update:** дополнить ADR-018 / TECH-166 примечанием о двух модах guard'а: "implementation activity check" vs "implementation existence check".

4. **Tests** (`tests/integration/test_callback_already_merged.py`):
   - EC-1: tmpdir repo, commit с subject `feat(TECH-XXX): foo` в Allowed Files до `started_at`, autopilot ничего не пишет → spec auto-close to `done`.
   - EC-2: только обычные коммиты без grep-match → demote (текущее поведение).
   - EC-3: merge-коммит `Merge TECH-XXX: ...` → auto-close to `done`.
   - EC-4: regression — TECH-168 test corpus не падает.
   - EC-5: deterministic — verdict='auto_close' пишется в callback_decisions, NOT counted в circuit-breaker threshold.

---

## Eval Criteria

| ID | Type | Description |
|----|------|-------------|
| EC-1 | integration | spec_id в commit subject + 0 коммитов с started_at → auto-close to done |
| EC-2 | integration | merge `Merge TECH-XXX` без других коммитов в Allowed Files → auto-close |
| EC-3 | integration | 0 коммитов вообще + 0 merge → demote (старое поведение) |
| EC-4 | regression | TECH-168 callback test suite зелёный |
| EC-5 | deterministic | verdict='auto_close' в callback_decisions, demoted=0, не triggers circuit |

---

## Out of Scope

- Не меняем `_has_implementation_commits` — он остаётся "activity since started_at".
- Не строим merge-graph аналитику (это отдельный dashboard).
- `--grep="<spec_id>"` использует case-sensitive match; если в кодовой базе пишут `tech-176` lowercase — проблема владельца спеки. Документируем.

---

## Notes

Эта дыра — прямой триггер инцидента 03-04.05.2026, где TECH-169 (сам circuit-breaker) бесконечно демоутился petlей и блокировал claude-runner на 33 часа. Closing this gap делает orchestrator идемпотентным относительно повторных запусков уже-сделанных спек.

---

## Drift Log

**Checked:** 2026-05-04 UTC
**Result:** no_drift

### Changes Detected

| File | Change Type | Action Taken |
|------|-------------|--------------|
| `scripts/vps/callback.py` | none — `_has_implementation_commits` at line 896, `verify_status_sync` at 1158, `_trip_circuit` at 1069, `is_merged_to_develop` at 945 (matches spec assumptions) | none |
| `scripts/vps/db.py` | none — `record_decision(project_id, spec_id, verdict, reason, demoted)` at line 253; `verdict` is plain TEXT (no enum check), so `'auto_close'` is accepted as-is | none |
| `.claude/rules/architecture.md` | none — ADR-018 row (line 91), TECH-166 row (line 94) match spec assumptions | none |

### References Updated

None.

### Notes

- Worktree `dld-TECH-176/tests/integration/` does not yet exist. Test file in this plan is created from scratch using the same conventions as `dld/tests/integration/test_callback_no_impl_demote.py` and `test_callback_feature_branch.py` (real git + real sqlite + monkeypatch on `subprocess.run` to suppress push, fixture `tmp_db` with schema reset).
- `is_merged_to_develop` (callback.py:945) already runs `git log develop --grep <spec_id>` for diagnostic logging only. The new helper `_spec_has_merged_implementation` is stricter: it also requires the commit to touch `## Allowed Files`, runs against `--all` (not just develop), and is used as a **decision input** (not just diagnostic).

---

## Implementation Plan

### Task 1: Add `_spec_has_merged_implementation` helper to `callback.py`

**Files:**
- Modify: `scripts/vps/callback.py:943` — insert new helper between `_has_implementation_commits` (ends ~942) and `is_merged_to_develop` (starts 945).

**Context:**
Current guard `_has_implementation_commits` answers "did autopilot do something during the last run" (window = `started_at`...now). We need a parallel check that answers "is there *any* implementation of this spec already in the repo, regardless of when". The helper greps **all** branches by spec_id in commit subject AND requires those commits to touch one of the spec's `## Allowed Files`.

**Step 1: Write failing test (combined with Task 4 — see EC-1, EC-3 there).**

**Step 2: Add helper.**

Insert after `_has_implementation_commits` returns at line 942, before `def is_merged_to_develop` at line 945:

```python
def _spec_has_merged_implementation(
    project_path: str,
    spec_id: str,
    allowed: list[str] | None,
) -> tuple[bool, list[str]]:
    """True if the repo (any branch) already contains commits implementing spec_id.

    Stricter than `is_merged_to_develop`: a commit only counts if BOTH
        (a) its subject contains spec_id (case-sensitive), AND
        (b) it touches at least one path in `allowed`.

    Catches the "already merged before started_at" gap in the activity-window
    guard (`_has_implementation_commits`):
        - autopilot re-run on a spec that was merged days ago → activity window
          empty, but this helper sees the historical commits → auto-close.

    Returns (matched, hashes):
        matched : bool — True iff at least one qualifying commit exists.
        hashes  : list[str] — short SHAs of qualifying commits (for log line).
                  Empty when matched is False or on error.

    Degrade rules (mirrored from `_has_implementation_commits`):
        spec_id falsy        → (False, [])
        allowed is None      → (False, [])  # no allowlist = can't qualify
        allowed == []        → (False, [])  # explicit empty allowlist
        subprocess error     → (False, [])  # silent — caller falls through
                                            # to demote (existing behaviour)
    """
    if not spec_id or not allowed:
        return (False, [])
    cmd = [
        "git", "-C", project_path, "log", "--all",
        "--grep", re.escape(spec_id),
        "--pretty=%h",
        "--",
        *allowed,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        log.info(
            "MERGED_IMPL_CHECK: git log failed for %s: %s",
            spec_id, exc,
        )
        return (False, [])
    if r.returncode != 0:
        log.info(
            "MERGED_IMPL_CHECK: git log rc=%s stderr=%s",
            r.returncode, r.stderr.strip()[:200],
        )
        return (False, [])
    hashes = [h for h in r.stdout.split() if h]
    return (bool(hashes), hashes)
```

**Acceptance Criteria:**
- [ ] Helper compiles and `python3 -c "import callback"` succeeds.
- [ ] Returns `(False, [])` for empty/None `allowed` and falsy `spec_id`.
- [ ] Uses `--all` (sees feature branches AND develop AND merge commits).
- [ ] Uses `--grep <spec_id>` so subjects like `feat(TECH-XXX): foo` and `Merge TECH-XXX: foo` both match (covers Tasks spec items 1.a + 1.b — `--grep` matches anywhere in the subject).
- [ ] Filters by `-- *allowed` so commits touching only docs/unrelated paths are excluded.
- [ ] Never raises (degrade-silent on subprocess error per `_has_implementation_commits` convention).

---

### Task 2: Wire `auto_close` branch into `verify_status_sync`

**Files:**
- Modify: `scripts/vps/callback.py:1221-1247` — extend the `target == "done"` guard block (currently lines 1221-1257) to take the `auto_close` fork before the demote/circuit fork.

**Context:**
When `_has_implementation_commits` returns `False`, today's code unconditionally demotes (lines 1228-1247). Insert a precheck: if `_spec_has_merged_implementation` returns `True`, log it, record a `verdict='auto_close'` decision (NOT counted as demote), and let `target` stay `"done"` — `verify_status_sync` then proceeds to the normal status-write path and flips spec+backlog to `done`.

**Step 1: Locate insertion point.**

Current code (callback.py:1227-1247):

```python
if not _has_implementation_commits(project_path, allowed, started_at):
    guard_reason = (
        "missing_allowed_files_section" if allowed is None else "no_implementation_commits"
    )
    log.warning(
        "IMPL_GUARD: %s — demoting done → blocked (%s, started_at=%s)",
        spec_id,
        guard_reason,
        started_at,
    )
    _, spec_text = _apply_blocked_reason(spec_text, guard_reason)
    target = "blocked"
    # TECH-169: feed circuit-breaker
    try:
        db.record_decision(project_id, spec_id, "demote",
                           guard_reason, demoted=True)
        count = db.count_demotes_since(CIRCUIT_WINDOW_MIN)
        if count > CIRCUIT_THRESHOLD:
            _trip_circuit(project_id, spec_id, count)
    except Exception as exc:  # noqa: BLE001
        log.warning("CIRCUIT: record/check failed: %s", exc)
```

**Step 2: Replace with auto-close-aware version.**

```python
if not _has_implementation_commits(project_path, allowed, started_at):
    # TECH-176: before demoting, ask "is the work *already* merged?"
    # If yes (commits in Allowed Files mention spec_id on any branch),
    # treat as auto-close — not a guard failure.
    already_merged, merged_hashes = _spec_has_merged_implementation(
        project_path, spec_id, allowed,
    )
    if already_merged:
        log.warning(
            "IMPL_GUARD: %s — already merged in repo (commits: %s) → auto-close to done",
            spec_id,
            ",".join(merged_hashes[:5]),
        )
        guard_reason = "already_merged"
        try:
            db.record_decision(
                project_id, spec_id, "auto_close",
                f"already_merged:{','.join(merged_hashes[:5])}",
                demoted=False,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("CIRCUIT: record_decision(auto_close) failed: %s", exc)
        # Leave target = "done"; flow falls through to the normal
        # status-write path which flips spec+backlog and commits.
    else:
        guard_reason = (
            "missing_allowed_files_section" if allowed is None else "no_implementation_commits"
        )
        log.warning(
            "IMPL_GUARD: %s — demoting done → blocked (%s, started_at=%s)",
            spec_id,
            guard_reason,
            started_at,
        )
        _, spec_text = _apply_blocked_reason(spec_text, guard_reason)
        target = "blocked"
        # TECH-169: feed circuit-breaker
        try:
            db.record_decision(project_id, spec_id, "demote",
                               guard_reason, demoted=True)
            count = db.count_demotes_since(CIRCUIT_WINDOW_MIN)
            if count > CIRCUIT_THRESHOLD:
                _trip_circuit(project_id, spec_id, count)
        except Exception as exc:  # noqa: BLE001
            log.warning("CIRCUIT: record/check failed: %s", exc)
```

**Acceptance Criteria:**
- [ ] When `_has_implementation_commits` returns `False` AND `_spec_has_merged_implementation` returns `(True, hashes)`:
  - log line `IMPL_GUARD: <spec> — already merged in repo (commits: ...) → auto-close to done` is emitted at WARNING.
  - `db.record_decision` is called with `verdict='auto_close'`, `reason='already_merged:<hashes>'`, `demoted=False`.
  - `target` stays `"done"`, `_apply_blocked_reason` is **not** called.
  - `_trip_circuit` is **not** called.
  - Function continues to the existing "Spec-authority guards" block (line 1259+) and the final commit path → spec **Status:** flipped to `done`, backlog row → `done`.
- [ ] When `_has_implementation_commits` returns `False` AND `_spec_has_merged_implementation` returns `(False, _)`:
  - existing demote behaviour preserved exactly (regression of EC-3 in test_callback_no_impl_demote.py and TECH-170 EC-3).
- [ ] `guard_reason` is set in both branches so the eventual `_emit_audit` call (line 1318) carries a non-empty reason. For auto-close, `guard_reason='already_merged'` ends up in the audit JSONL `reason` field.
- [ ] `verdict='auto_close'` rows do NOT contribute to `count_demotes_since` (verified by EC-5: `demoted=False` keeps SQL filter `WHERE demoted=1` from selecting them — see db.py:283).

---

### Task 3: Update ADR-018 / TECH-166 row in `architecture.md`

**Files:**
- Modify: `.claude/rules/architecture.md:91` and `:94` — extend ADR-018 row and TECH-166 row notes.

**Context:**
Document the two-mode guard distinction: "implementation activity check" (window-bounded, demote on miss) vs "implementation existence check" (whole repo, auto-close on hit).

**Step 1: Edit ADR-018 row at line 91.**

Replace:
```markdown
| ADR-018 | Callback status enforcement | 2026-03 | LLM-instructional status updates unreliable (Edit tool miss, context overflow). Callback auto-fixes spec+backlog after pueue completion. Respects `blocked` — won't overwrite to `done`. **Extended TECH-166 (2026-05):** implementation guard. Degrades open on missing data. См. dld-orchestrator.md§5 |
```

With:
```markdown
| ADR-018 | Callback status enforcement | 2026-03 | LLM-instructional status updates unreliable (Edit tool miss, context overflow). Callback auto-fixes spec+backlog after pueue completion. Respects `blocked` — won't overwrite to `done`. **Extended TECH-166 (2026-05):** implementation guard, two modes — *activity check* (`_has_implementation_commits`, window=since `started_at`, miss → demote) and *existence check* (`_spec_has_merged_implementation`, scope=`--all`, hit → auto-close, idempotent for re-runs of already-merged specs, TECH-176). Degrades open on missing data. См. dld-orchestrator.md§5 |
```

**Step 2: Add TECH-176 row after the TECH-174 row (line 101).**

Append after line 101 (`| TECH-174 | Manual spec verification protocol ... |`):

```markdown
| TECH-176 | Guard auto-close path: detect "already merged before started_at" via `_spec_has_merged_implementation` (`--grep <spec_id>` ∩ `-- <allowed>`) | 2026-05 | См. dld-orchestrator.md§6 |
```

**Acceptance Criteria:**
- [ ] ADR-018 row mentions both `_has_implementation_commits` (activity) and `_spec_has_merged_implementation` (existence).
- [ ] New TECH-176 row appended in the same table style.
- [ ] No other rows touched. `grep '| TECH-' .claude/rules/architecture.md | wc -l` == 9 (was 8).

---

### Task 4: Integration tests in `tests/integration/test_callback_already_merged.py`

**Files:**
- Create: `tests/integration/test_callback_already_merged.py`

**Context:**
Worktree's `tests/` directory does not yet exist; pytest auto-discovers from any path. Pattern is identical to `dld/tests/integration/test_callback_no_impl_demote.py` and `test_callback_feature_branch.py` (real git + real sqlite via fixture `tmp_db`, `_suppress_push` monkeypatch, `_head_file` for HEAD reads). Schema reset via `monkeypatch.setattr(db, "_MIGRATIONS_APPLIED", False, raising=False)` (matches TECH-170 test fixture).

**Step 1: Write the test file.**

Create `tests/integration/test_callback_already_merged.py`:

```python
"""TECH-176 — integration tests for verify_status_sync auto-close path.

Auto-close fires when:
  - the activity-window guard (`_has_implementation_commits`) sees zero
    commits since `started_at`, AND
  - `_spec_has_merged_implementation` finds historical commits in the
    repo whose subject mentions the spec_id and that touch the spec's
    Allowed Files.

Real fs + real git + real sqlite (no mocks per ADR-013).
"""

from __future__ import annotations

import logging
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402
import db  # noqa: E402


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def _commit(repo: Path, rel: str, body: str, msg: str) -> None:
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(body)
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", msg)


def _head_file(repo: Path, rel: str) -> str | None:
    r = subprocess.run(
        ["git", "-C", str(repo), "show", f"HEAD:{rel}"],
        capture_output=True, text=True,
    )
    return r.stdout if r.returncode == 0 else None


def _make_project(tmp_path: Path, spec_id: str, allowed_files: list[str]) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "ai" / "features").mkdir(parents=True)
    allowed_block = "\n".join(f"- `{p}`" for p in allowed_files) or "(none)"
    spec_body = f"""# {spec_id}

**Status:** in_progress

## Allowed Files

{allowed_block}

## Tests
"""
    (repo / "ai" / "features" / f"{spec_id}.md").write_text(spec_body)
    (repo / "ai" / "backlog.md").write_text(
        f"| ID | Title | Status | P |\n|---|---|---|---|\n"
        f"| {spec_id} | demo | in_progress | P1 |\n"
    )
    (repo / "README.md").write_text("init\n")
    _git(repo, "add", "README.md",
         f"ai/features/{spec_id}.md", "ai/backlog.md")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "orchestrator.db")
    conn = sqlite3.connect(db_path)
    schema = (SCRIPT_DIR / "schema.sql").read_text()
    conn.executescript(schema)
    conn.close()
    monkeypatch.setattr(db, "_MIGRATIONS_APPLIED", False, raising=False)
    with patch.object(db, "DB_PATH", db_path):
        yield db_path


def _seed_task(project_id: str, label: str, pueue_id: int) -> None:
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            (project_id, "/tmp/ignored"),
        )
        conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, label, "autopilot", "running", pueue_id),
        )


def _suppress_push(monkeypatch):
    real_run = subprocess.run

    def fake_run(cmd, *a, **kw):
        if isinstance(cmd, list) and "push" in cmd:
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(callback.subprocess, "run", fake_run)


def _count_decisions(verdict: str, demoted: int | None = None) -> int:
    with db.get_db() as conn:
        if demoted is None:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM callback_decisions WHERE verdict = ?",
                (verdict,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM callback_decisions "
                "WHERE verdict = ? AND demoted = ?",
                (verdict, demoted),
            ).fetchone()
        return int(row["c"]) if row else 0


# --- EC-1 -------------------------------------------------------------------
# Pre-existing commit with spec_id in subject + zero activity since started_at
# → auto-close to done.

def test_ec1_already_merged_before_started_at_auto_close(tmp_path, tmp_db, monkeypatch, caplog):
    spec_id = "TECH-871"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    # Historical commit with spec_id in subject touching Allowed Files.
    _commit(repo, "src/x.py", "y=1\n", f"feat({spec_id}): real work")
    time.sleep(1.1)
    # Now seed the task — started_at is AFTER the commit above.
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=871)
    # No further commits — activity window is empty.
    _suppress_push(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="callback"):
        callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=871)

    spec_text = _head_file(repo, f"ai/features/{spec_id}.md")
    backlog_text = _head_file(repo, "ai/backlog.md")
    assert spec_text is not None
    assert "**Status:** done" in spec_text, "auto-close should flip to done"
    assert "**Blocked Reason:**" not in spec_text
    assert "**Status:** blocked" not in spec_text
    assert backlog_text is not None
    assert "| done |" in backlog_text
    assert any("already merged" in rec.message and "auto-close" in rec.message
               for rec in caplog.records), "auto-close log line must fire"


# --- EC-2 -------------------------------------------------------------------
# Merge commit (`Merge TECH-XXX: ...`) on an Allowed File, no other activity
# → auto-close to done. Confirms `--grep` matches merge subjects too.

def test_ec2_merge_commit_subject_auto_close(tmp_path, tmp_db, monkeypatch):
    spec_id = "TECH-872"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    # Simulate a squash-merge: commit on develop with "Merge TECH-XXX" subject
    # touching an Allowed File.
    _commit(repo, "src/x.py", "y=2\n", f"Merge {spec_id}: feature branch into develop")
    time.sleep(1.1)
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=872)
    _suppress_push(monkeypatch)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=872)

    spec_text = _head_file(repo, f"ai/features/{spec_id}.md")
    assert spec_text is not None
    assert "**Status:** done" in spec_text


# --- EC-3 -------------------------------------------------------------------
# Regression: zero commits anywhere (even historically) → still demotes.

def test_ec3_no_commits_anywhere_still_demotes(tmp_path, tmp_db, monkeypatch):
    spec_id = "TECH-873"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=873)
    time.sleep(1.1)
    # Only a docs commit; nothing matches grep+allowed.
    _commit(repo, "docs/note.md", "n\n", f"docs: {spec_id} note only")
    _suppress_push(monkeypatch)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=873)

    spec_text = _head_file(repo, f"ai/features/{spec_id}.md")
    backlog_text = _head_file(repo, "ai/backlog.md")
    assert spec_text is not None
    assert "**Status:** blocked" in spec_text
    assert "**Blocked Reason:** no_implementation_commits" in spec_text
    assert backlog_text is not None
    assert "| blocked |" in backlog_text


# --- EC-4 -------------------------------------------------------------------
# Subject mentions spec_id but commit touches only an UNALLOWED path → does
# NOT trigger auto-close (proves the `-- *allowed` filter actually filters).

def test_ec4_grep_matches_but_path_unallowed_demotes(tmp_path, tmp_db, monkeypatch):
    spec_id = "TECH-874"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=874)
    time.sleep(1.1)
    # Subject mentions spec_id but file is NOT in Allowed Files.
    _commit(repo, "docs/random.md", "n\n", f"docs({spec_id}): outside allowlist")
    _suppress_push(monkeypatch)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=874)

    spec_text = _head_file(repo, f"ai/features/{spec_id}.md")
    assert spec_text is not None
    assert "**Status:** blocked" in spec_text, \
        "grep-only match without Allowed Files touch must demote, not auto-close"
    assert "**Blocked Reason:** no_implementation_commits" in spec_text


# --- EC-5 -------------------------------------------------------------------
# Deterministic: auto-close writes verdict='auto_close', demoted=0, NOT counted
# by count_demotes_since (so circuit-breaker is unaffected).

def test_ec5_auto_close_decision_not_counted_by_circuit(tmp_path, tmp_db, monkeypatch):
    spec_id = "TECH-875"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _commit(repo, "src/x.py", "y=1\n", f"feat({spec_id}): historical work")
    time.sleep(1.1)
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=875)
    _suppress_push(monkeypatch)

    # Snapshot demote count before.
    demotes_before = db.count_demotes_since(callback.CIRCUIT_WINDOW_MIN)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=875)

    # 1. auto_close row exists, demoted=0.
    assert _count_decisions("auto_close", demoted=0) == 1, \
        "auto_close decision row missing"
    # 2. No demote row written.
    assert _count_decisions("demote") == 0, \
        "auto_close path must not record demote"
    # 3. count_demotes_since unchanged → circuit threshold not advanced.
    demotes_after = db.count_demotes_since(callback.CIRCUIT_WINDOW_MIN)
    assert demotes_after == demotes_before, \
        "auto_close must not count toward circuit-breaker threshold"
```

**Acceptance Criteria:**
- [ ] File created at `tests/integration/test_callback_already_merged.py`.
- [ ] `pytest tests/integration/test_callback_already_merged.py -v` runs all 5 tests green from the worktree root.
- [ ] EC-1: spec.Status = `done`, backlog row = `done`, log contains "already merged" + "auto-close".
- [ ] EC-2: merge-commit subject (`Merge TECH-872: ...`) auto-closes to done.
- [ ] EC-3 (regression of TECH-166 happy demote): zero qualifying commits → demote to blocked with reason `no_implementation_commits`.
- [ ] EC-4: subject grep match without Allowed Files touch → demotes (proves `-- *allowed` filter active).
- [ ] EC-5: `callback_decisions` has `verdict='auto_close', demoted=0`; `count_demotes_since` unchanged across the call.

---

### Task 5: Run full callback regression suite

**Files:** none (verification only).

**Context:**
Confirm Task 2's wiring change does not regress TECH-166/168/170/171.

**Step 1: From worktree root, run all callback integration tests:**

```bash
cd /home/dld/projects/dld-TECH-176
pytest tests/integration/test_callback*.py -v
```

(If those test files don't yet exist in the worktree, they'll be picked up from the parent `dld/` once branches are merged; for in-worktree validation only `test_callback_already_merged.py` is required.)

**Acceptance Criteria:**
- [ ] All 5 EC tests in `test_callback_already_merged.py` pass.
- [ ] No syntax / import errors (`python3 -c "import sys; sys.path.insert(0, 'scripts/vps'); import callback"` succeeds).
- [ ] `grep -n "_spec_has_merged_implementation" scripts/vps/callback.py | wc -l` == 2 (one definition, one call site).
- [ ] `grep -n "auto_close" scripts/vps/callback.py | wc -l` >= 2 (record_decision verdict + log/reason strings).

---

### Execution Order

```
Task 1 (helper) ──┐
                  ├──> Task 4 (tests) ──> Task 5 (regression run)
Task 2 (wire)   ──┘
Task 3 (ADR docs) — independent, can run in parallel with 1/2/4.
```

Recommended sequential order for the coder: **1 → 2 → 3 → 4 → 5**. Task 4 tests will fail before Task 1+2 are in place (TDD). Task 3 is doc-only and doesn't gate anything.

### Dependencies

- Task 2 depends on Task 1 (calls `_spec_has_merged_implementation`).
- Task 4 tests EC-1, EC-2, EC-5 require Task 1 + Task 2 in place; EC-3, EC-4 should pass before+after (regression).
- Task 5 depends on Tasks 1, 2, 4.
- Task 3 (architecture.md) has no code dependency.

### Research Sources

None — pure refactor of existing internal logic. Patterns mirrored from
`scripts/vps/callback.py` (`is_merged_to_develop`, `_has_implementation_commits`)
and `tests/integration/test_callback_no_impl_demote.py` /
`test_callback_feature_branch.py` (test fixtures).
