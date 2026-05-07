---
id: TECH-168
type: TECH
status: done
priority: P0
risk: R0
created: 2026-05-02
---

# TECH-168 — Callback test suite (unit + integration + regression)

**Status:** done
**Priority:** P0
**Risk:** R0 (irreversible — без тестов любой regex-tweak в callback.py = silent regression во всех 5 проектах)

---

## Problem

`scripts/vps/callback.py` — единственная точка enforcement статусов спек по всему orchestrator-парку (5 проектов, ~1000 спек). За последние 36 часов в нём было сделано 4 правки (TECH-166 деплой → hotfix regex → degrade-closed refactor → broaden parser), и каждая деплоилась без unit-тестов. Только manual smoke на 1-2 спеках. Это игра в рулетку: regex broaden может случайно начать матчить лишнее, plumbing-commit может ломаться на edge-case'ах git'а, status-sync race может проявиться при concurrent callback'ах.

**Боль уже материализовалась:**
- TECH-166 v1 deploy: heading regex был `\s*$` end-of-line — пропускал `(whitelist)` суффикс. Час silent false-positive done на awardybot.
- TECH-166 refactor: формально работает, но без тестов нельзя доказать что `verify_status_sync` корректно обрабатывает все 6+ guard-веток (blocked-overwrite-protection, done-overwrite-protection, demote-from-impl-guard, missing-allowed-section, no-impl-commits, idempotent-already-synced).

---

## Goal

Полное тестовое покрытие `callback.py` с двумя уровнями:

1. **Unit** (быстрые, изолированные, не трогают git/db):
   - `_parse_allowed_files` — все формы heading/marker, fenced blocks, multiple sections.
   - `_apply_spec_status` / `_apply_backlog_status` / `_apply_blocked_reason` — корректные in-place text mutations.
   - `_skill_from_pueue_command`, `resolve_label`, `map_result` — pure helpers.
   - `_has_implementation_commits` с mocked subprocess.

2. **Integration** (tmpdir git repo + sqlite, реальные subprocess, 2-5 сек на тест):
   - `_git_commit_push` plumbing — НЕ трогает working tree, коммит чистый, push retry.
   - `verify_status_sync` end-to-end сценарии:
     - happy path (commits есть, mark done)
     - no-impl demote (allowed=4, 0 commits → blocked + reason)
     - missing section (degrade-closed)
     - empty section (degrade-closed)
     - blocked-overwrite-protection (target=done но spec=blocked)
     - done-overwrite-protection (target=blocked но spec=done)
     - HEAD already synced (idempotent, no commit)
     - operator's uncommitted edits in spec/backlog preserved
   - `_resync_backlog_to_spec` — sync to spec authority, idempotent.
   - `_get_started_at` — чтение из task_log.

3. **Regression** corpus:
   - Снепшот 50 живых спек awardybot/dowry/gipotenuza/plpilot/wb с известным parser output.
   - Любая правка regex'а ломает регрессию → fail в CI.

---

## Allowed Files

<!-- callback-allowlist v1 -->

- `scripts/vps/callback.py`
- `scripts/vps/db.py`
- `tests/unit/test_callback_helpers.py`
- `tests/unit/test_callback_parser.py`
- `tests/integration/test_callback_status_sync.py`
- `tests/integration/test_callback_plumbing_commit.py`
- `tests/regression/test_callback_spec_corpus.py`
- `tests/regression/spec_corpus/`
- `tests/regression/spec_corpus/awardybot_FTR-897.md`
- `tests/regression/spec_corpus/dowry_BUG-394.md`
- `tests/regression/spec_corpus/gipotenuza_FTR-098.md`
- `tests/regression/spec_corpus/plpilot_BUG-326.md`
- `tests/regression/spec_corpus/wb_ARCH-176a.md`
- `.github/workflows/test.yml`

---

## Tasks

1. **Unit: parser** — все форматы heading + marker (TECH-167) + invariants на edge-cases (Unicode paths, paths с пробелом в backticks, многострочные секции).
2. **Unit: text mutators** — `_apply_*` functions с golden inputs/outputs.
3. **Unit: helpers** — `_skill_from_pueue_command`, `resolve_label`, `map_result`.
4. **Integration: plumbing-commit** — tmpdir repo, симуляция operator-uncommitted-edits, проверить что они survive.
5. **Integration: verify_status_sync** — 8 сценариев из Goal.
6. **Regression corpus** — отобрать 5 спек по проекту (canonical / heading-variant / fenced-block / no-section / multiple-sections), сохранить как fixtures.
7. **CI wiring** — `.github/workflows/test.yml`, запуск на каждый PR в `scripts/vps/`. pytest+pytest-xdist.
8. **README** в `tests/` — как добавлять новые fixture-спеки + что считается breaking change.

---

## Eval Criteria

| ID | Type | Description |
|----|------|-------------|
| EC-1 | deterministic | Все unit-тесты зелёные локально |
| EC-2 | deterministic | Все integration-тесты зелёные |
| EC-3 | deterministic | Regression corpus 25 спек (5×5 проектов) проходит парсер с ожидаемым output |
| EC-4 | integration | CI запускается на PR, fail blockирует merge |
| EC-5 | integration | Operator-uncommitted-edits preserved в plumbing-commit (smoke test из TECH-166) автоматизирован |
| EC-6 | deterministic | Coverage report — callback.py >= 85% line coverage |

---

## Drift Log

**Checked:** 2026-05-02 19:55 UTC
**Result:** light_drift (informational only — все Allowed Files в spec правильны, line numbers ниже свежие на момент планирования)

### Codebase facts captured for plan stability

| File | Line range / fact | Why it matters |
|------|-------------------|----------------|
| `scripts/vps/callback.py` | 1020 LOC total | Spec говорит "1020 LOC" — совпадает |
| `scripts/vps/callback.py:57-89` | `resolve_label` | Layer 1 DB → Layer 2 pueue CLI |
| `scripts/vps/callback.py:101-105` | `map_result` | "Success"→("done",0), else ("failed",1) |
| `scripts/vps/callback.py:126-176` | `_skill_from_pueue_command` | parses 4th argv after `run-agent.sh`, returns (skill, start_ts) |
| `scripts/vps/callback.py:403` | `_VALID_STATUSES` frozenset | draft/queued/in_progress/blocked/resumed/done |
| `scripts/vps/callback.py:406-425` | `_read_head_blob` | git show HEAD:<rel> — degrade-closed на error |
| `scripts/vps/callback.py:428-433` | `_apply_spec_status` | regex `(\*\*Status:\*\*)\s*\S+` count=1 |
| `scripts/vps/callback.py:436-442` | `_apply_backlog_status` | row regex `\|\s*{spec_id}\s*\|.*?\|\s*\S+\s*\|` |
| `scripts/vps/callback.py:445-451` | `_apply_blocked_reason` | replaces existing line OR inserts after `**Status:**` |
| `scripts/vps/callback.py:454-513` | `_git_commit_push` | hash-object -w + update-index --cacheinfo + commit + push (NO add) |
| `scripts/vps/callback.py:516-551` | `_resync_backlog_to_spec` | idempotent при уже-в-sync |
| `scripts/vps/callback.py:560-572` | TECH-167 v1 regexes | `_ALLOWED_FILE_EXT_RE`, `_ALLOWED_FILES_V1_HEADING_RE` (case-sensitive!), `_ALLOWED_FILES_V1_MARKER_RE`, `_ALLOWED_FILES_V1_BULLET_RE` |
| `scripts/vps/callback.py:580-583` | `_ALLOWED_FILES_HEADING_RE` (legacy) | `(?i)Updated\s+Allowed\s+Files | Files\s+Allowed\s+to\s+Modify` |
| `scripts/vps/callback.py:587-623` | `_parse_allowed_files_v1` | None if no canonical heading OR no marker; [] if marker but malformed |
| `scripts/vps/callback.py:626-646` | `_parse_allowed_files_legacy` | _ALLOWED_FILE_EXT_RE.findall over section |
| `scripts/vps/callback.py:649-686` | `_parse_allowed_files` (dispatcher) | v1 → legacy → None |
| `scripts/vps/callback.py:704-717` | `_get_started_at` | reads `task_log.started_at`, db.get_db() context |
| `scripts/vps/callback.py:720-767` | `_has_implementation_commits` | None→False, [] →False, started_at None→True, git error→True |
| `scripts/vps/callback.py:773-875` | `verify_status_sync` | full guard chain (impl-guard → blocked-overwrite → done-overwrite → diff & commit) |

### Pre-existing tests (NOT in Allowed Files — will not be touched)

| File | Status |
|------|--------|
| `tests/scripts/test_callback.py` | references `_fix_spec_status` (deleted in TECH-166 refactor); already broken — out of scope |
| `tests/unit/test_callback_allowlist_v1.py` | Working — overlaps with parser unit tests; new test files use **complementary** test names (no collisions) |
| `tests/unit/test_callback_implementation_guard.py` | Working — covers EC-1..EC-7 of TECH-166; new tests use **EC-8+** numbering |
| `tests/integration/test_callback_no_impl_demote.py` | Working — covers EC-8..EC-10; new integration file uses **EC-11+** |
| `tests/scripts/test_db.py` | Working — `db.py` already covered for `get_task_by_pueue_id` |

### Sync zone check

Allowed Files include `scripts/vps/*` — these are NOT in `template/` (orchestrator is DLD-specific per `.claude/CUSTOMIZATIONS.md`-style rule). **No sync task needed.** `tests/` and `.github/workflows/test.yml` are also not template-mirrored.

### Solution verification

Approach (pytest unit + integration with real fs/git/sqlite + regression corpus + GitHub Actions) is the canonical Python testing stack for this codebase. Already validated by existing `test_callback_implementation_guard.py` (real git_repo fixture, no mocks). No drift in best practices needed.

---

## Implementation Plan

> Coder execution notes:
> - Working directory at exec time: `/home/dld/projects/dld-tech168` (worktree on branch `tech-168/callback-test-suite`).
> - Run tests with `pytest tests/unit tests/integration tests/regression -v` from worktree root.
> - For corpus extraction (Task 6) the coder MUST `cp` from sibling project paths under `/home/dld/projects/{awardybot,dowry,gipotenuza,plpilot,wb}/ai/features/`. These are read-only sources outside the worktree but on the same VPS — file copy is a one-time operation captured in commit.
> - Do **not** modify `tests/scripts/test_callback.py` (already broken vs. current `callback.py`, but outside Allowed Files).
> - All `subprocess.run` for `git push` calls in integration tests must be suppressed via `monkeypatch` (no remote available).
> - Tests must be deterministic — use `time.sleep(1.1)` between `started_at` and commits to keep `git log --since` window stable (existing convention in `test_callback_implementation_guard.py:107`).

---

### Task 1 — Unit: parser edge cases (`tests/unit/test_callback_parser.py`)

**Files (all NEW):**
- Create: `tests/unit/test_callback_parser.py` (~140 LOC)

**Targets in callback.py:**
- `_parse_allowed_files` (line 649)
- `_parse_allowed_files_v1` (line 587)
- `_parse_allowed_files_legacy` (line 626)
- Regexes at lines 560, 564, 566, 570, 580

**Context:**
Existing `test_callback_allowlist_v1.py` covers happy v1 + basic legacy. This task fills GAPS that broke in TECH-166 v1 (heading suffixes), TECH-167 v1 (marker dispatch), and edge cases the spec demands: Unicode paths, paths-with-space-in-backticks, multiple `## Allowed Files` sections, comment-only sections, marker presence outside section.

**Test functions:**

```python
# tests/unit/test_callback_parser.py

# --- Heading regex variants (legacy) ---
def test_legacy_heading_with_whitespace_suffix():
    """`## Allowed Files   ` (trailing spaces) — must match (regex is case-insensitive prefix-anchored)."""

def test_legacy_heading_with_qualifier_suffix():
    """`## Allowed Files (whitelist)` — historic awardybot/dowry format."""

def test_legacy_heading_case_sensitivity():
    """`## ALLOWED FILES` — legacy regex `(?i)` flag → must match."""

def test_legacy_heading_v1_strict_sensitivity():
    """`## ALLOWED FILES` — v1 regex is case-SENSITIVE, must NOT trigger v1 branch even with marker."""

# --- Section boundary detection ---
def test_section_ends_at_next_h2():
    """Backticks in section after first H2 boundary are NOT collected."""

def test_multiple_allowed_files_sections_first_wins():
    """Two `## Allowed Files` blocks — only first parsed (legacy iter breaks at first H2)."""

def test_section_at_end_of_file_no_trailing_h2():
    """Section is last in file, no terminating H2 — must still parse to EOF."""

# --- Path extraction (extension regex) ---
def test_paths_with_unicode_dirnames():
    """`- ` `Документы/spec.md`` — Unicode path components allowed by `[^\\s\\\\n]+`."""

def test_paths_with_dotdot_normalization_NOT_done():
    """`- ` `../../etc/passwd`` — parser doesn't normalize; raw string returned (security note)."""

def test_paths_with_no_extension_skipped():
    """`Dockerfile` (no extension) — current regex requires `.ext`, skipped. Document as known limit."""

def test_paths_with_dotfile_extension():
    """`.env.example` → matches via `\\.[A-Za-z][\\w-]*` → captured as `.env.example`? — VERIFY behavior."""

def test_path_with_dash_in_extension():
    """`config.tar-gz` — extension regex `[\\w-]*` allows hyphen → captured."""

# --- v1 marker dispatch corner cases ---
def test_v1_marker_after_bullets_section_terminates():
    """Marker placed AFTER bullets in same section — should still trigger v1 (whole section searched)."""

def test_v1_marker_in_html_comment_block():
    """Marker `<!-- callback-allowlist v1 with extra attrs="x" -->` — regex tolerates attrs."""

def test_v1_marker_truncated_no_terminator():
    """`<!-- callback-allowlist v1` with no `-->` — must NOT match (regex requires `-->`)."""

# --- Fenced blocks under v1 ---
def test_v1_marker_with_table_format_returns_empty():
    """v1 marker + markdown table (`| file |`) instead of bullets → [] (degrade-closed)."""

# --- Legacy + nested subheadings (wb/ARCH-176a style) ---
def test_legacy_with_h3_subheadings_under_section():
    """Body has `### New files` and `### Existing files` — H3 ≠ H2, section continues, both bullet lists collected."""

# --- Empty file / single-line file ---
def test_empty_spec_returns_none():
    """Empty content → no heading found → None."""

def test_only_heading_no_body():
    """`## Allowed Files\\n` then EOF → legacy returns []."""
```

**Step 1 — Write file:**

```python
"""TECH-168 Task 1 — parser edge cases.

Complements tests/unit/test_callback_allowlist_v1.py (TECH-167) and
test_callback_implementation_guard.py (TECH-166) by exercising
heading regex variants, section-boundary edge cases, path extraction
(Unicode, dotfiles, hyphen-in-ext), and v1 marker dispatch corners.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402


def _spec(tmp_path: Path, body: str, name: str = "T.md") -> Path:
    p = tmp_path / name
    p.write_text(body)
    return p


# ... (all test functions listed above with full bodies)
```

**Step 2 — Verify failures expose real bugs:**
```bash
pytest tests/unit/test_callback_parser.py -v
```
Expected: 18 PASS (or fail-on-bug findings documented as XFAIL with link to follow-up issue).

**Acceptance:**
- [ ] All 18 tests pass OR have explicit `@pytest.mark.xfail(reason="…")` linking a known issue.
- [ ] No collision with test names in `test_callback_allowlist_v1.py`.
- [ ] File ≤ 200 LOC.

---

### Task 2 — Unit: text mutators (`tests/unit/test_callback_helpers.py`, part A)

**Files (NEW):**
- Create: `tests/unit/test_callback_helpers.py` (Part A: ~80 LOC; Part B added in Task 3 → total ~180 LOC)

**Targets in callback.py:**
- `_apply_spec_status` (line 428)
- `_apply_backlog_status` (line 436)
- `_apply_blocked_reason` (line 445)
- `_VALID_STATUSES` (line 403)

**Context:**
These three text mutators are pure functions — best tested with golden-input/golden-output pairs. They were the source of TECH-166 v1 bug (regex matched too greedily on `**Status:** done | **Priority:** P1` row).

**Test functions:**

```python
# --- _apply_spec_status ---
def test_apply_spec_status_simple_inprogress_to_done():
    """`**Status:** in_progress` → `**Status:** done`, count=1."""

def test_apply_spec_status_pipe_separated_inline():
    """`**Status:** in_progress | **Priority:** P0` → only first token replaced."""

def test_apply_spec_status_invalid_target_returns_unchanged():
    """target='INVALID' → (False, original_text). Idempotent for invalid input."""

def test_apply_spec_status_no_status_line():
    """Text without `**Status:**` → (False, unchanged)."""

def test_apply_spec_status_only_replaces_first():
    """Two `**Status:**` lines (frontmatter + body) → only first replaced (count=1)."""

def test_apply_spec_status_all_valid_statuses():
    """Parametrized over draft/queued/in_progress/blocked/resumed/done — all six accepted."""

# --- _apply_backlog_status ---
def test_apply_backlog_status_typical_row():
    """`| BUG-300 | Fix thing | in_progress | P1 |` → `| BUG-300 | Fix thing | done | P1 |`."""

def test_apply_backlog_status_spec_id_with_letter_suffix():
    """ARCH-176a — re.escape handles letter suffix correctly, parent ARCH-176 row not matched."""

def test_apply_backlog_status_no_matching_row():
    """spec_id absent from table → (False, unchanged)."""

def test_apply_backlog_status_two_rows_only_first():
    """Same spec_id appears twice (data bug) → count=1, only first row patched."""

def test_apply_backlog_status_invalid_target():
    """target='banana' → (False, unchanged)."""

# --- _apply_blocked_reason ---
def test_apply_blocked_reason_inserts_after_status():
    """No existing reason line → inserted on line after `**Status:**`."""

def test_apply_blocked_reason_replaces_existing():
    """Existing `**Blocked Reason:** old` → replaced with new value, count stays 1."""

def test_apply_blocked_reason_idempotent():
    """Calling twice with same reason produces single line (no append)."""

def test_apply_blocked_reason_no_status_line_returns_unchanged():
    """Text has no `**Status:**` → no anchor for insertion → (False, unchanged)."""

def test_apply_blocked_reason_preserves_surrounding_content():
    """Content before/after Status block preserved byte-for-byte."""
```

**Acceptance:**
- [ ] 16 tests pass.
- [ ] Each test asserts BOTH the bool flag AND the text content (golden output).
- [ ] No subprocess / fs / db calls.

---

### Task 3 — Unit: pure helpers (`tests/unit/test_callback_helpers.py`, part B)

**Files (extends Task 2 file):**
- Modify: `tests/unit/test_callback_helpers.py` (append ~100 LOC, total ~180 LOC)

**Targets in callback.py:**
- `parse_label` (line 92)
- `map_result` (line 101)
- `resolve_label` (line 57) — NB: subprocess-touching, see strategy below
- `_skill_from_pueue_command` (line 126) — subprocess-touching

**Context:**
`map_result` and `parse_label` are pure → trivial golden tests. `resolve_label` and `_skill_from_pueue_command` hit DB + subprocess; Task 3 covers the **pure logic branches** (label parsing, command argv-split, JSON parsing) using monkeypatched `subprocess.run` returning canned JSON. DB-layer tests deferred to integration (Task 5/8).

**Test functions:**

```python
# --- parse_label ---
def test_parse_label_with_colon():
    """'proj:label' → ('proj', 'label')."""

def test_parse_label_no_colon_warns():
    """'orphan' → ('orphan', 'orphan'); caplog must show warning."""

def test_parse_label_multiple_colons_first_wins():
    """'proj:autopilot:BUG-100' → ('proj', 'autopilot:BUG-100') via partition()."""

# --- map_result ---
@pytest.mark.parametrize("result_str,expected", [
    ("Success", ("done", 0)),
    ("Successfully completed", ("done", 0)),
    ("Failed", ("failed", 1)),
    ("Killed", ("failed", 1)),
    ("", ("failed", 1)),
])
def test_map_result(result_str, expected):
    """Substring 'Success' → done; everything else → failed."""

# --- _skill_from_pueue_command (monkeypatched subprocess) ---
def test_skill_from_pueue_extracts_4th_argv(monkeypatch):
    """command='/bin/bash run-agent.sh /path claude autopilot /autopilot BUG-1' → skill='autopilot'."""

def test_skill_from_pueue_absolute_path_to_run_agent(monkeypatch):
    """command='/srv/scripts/run-agent.sh /p claude qa /qa BUG-1' → skill='qa'."""

def test_skill_from_pueue_no_run_agent_in_command(monkeypatch):
    """command='echo hello' → ('', 0.0)."""

def test_skill_from_pueue_subprocess_failure(monkeypatch):
    """subprocess raises → ('', 0.0), no exception propagates."""

def test_skill_from_pueue_returncode_nonzero(monkeypatch):
    """pueue rc=1 → ('', 0.0) (early return)."""

def test_skill_from_pueue_start_ts_iso_parsed(monkeypatch):
    """Running.start='2026-05-02T12:00:00Z' → start_ts = unix epoch float."""

def test_skill_from_pueue_start_ts_done_state(monkeypatch):
    """Done.start='2026-05-02T12:00:00Z' → start_ts parsed even after task done."""

def test_skill_from_pueue_malformed_iso_silent(monkeypatch):
    """start='not-a-date' → start_ts=0.0, skill still returned."""

# --- resolve_label (subprocess monkeypatched, DB stubbed via patch.object) ---
def test_resolve_label_db_label_already_prefixed(tmp_db):
    """task_label='myproj:autopilot-X' (already prefixed) → no double-prefix."""
    # Existing test in test_callback.py covers happy path; this asserts no double-colon.
```

**Acceptance:**
- [ ] 14 new tests pass alongside Task 2's 16 → 30 total in file.
- [ ] `test_callback_helpers.py` total ≤ 200 LOC.
- [ ] No reliance on DB schema beyond what `tmp_db` fixture (copied from `test_callback.py:18-27` style) provides.

---

### Task 4 — Integration: plumbing-commit preserves uncommitted edits (`tests/integration/test_callback_plumbing_commit.py`)

**Files (NEW):**
- Create: `tests/integration/test_callback_plumbing_commit.py` (~150 LOC)

**Targets in callback.py:**
- `_git_commit_push` (line 454)
- `_read_head_blob` (line 406)

**Context:**
This is the **EC-5 smoke test from spec** — automated. The TECH-166 refactor's central invariant is "callback NEVER touches working tree". The plumbing path uses `git hash-object -w --stdin` + `git update-index --cacheinfo` + `git commit` (no `git add`). If anyone replaces this with `git add <file>` (the original v0 implementation), this test must fail loudly.

**Fixtures:**
- Reuse `git_repo` pattern from `test_callback_implementation_guard.py:71-85`.
- Local helper `_make_repo_with_uncommitted(tmp_path)` that:
  1. inits repo with committed `ai/features/SPEC.md` and `ai/backlog.md` AND `ai/notes/draft.md` (all three committed at HEAD).
  2. modifies all three in working tree (uncommitted dirty edits).
  3. modifies `ai/features/SPEC.md` and stages partial chunks (`git add -p` simulated by partial blob).

**Test functions:**

```python
def test_plumbing_commit_does_not_stage_unrelated_workdir_changes(tmp_path, monkeypatch):
    """Operator has dirty edits in ai/notes/draft.md and unrelated src/foo.py.
    callback._git_commit_push commits ONLY the spec+backlog new_content blobs.
    After call: HEAD commit touches exactly 1 file; workdir still dirty for others.
    """

def test_plumbing_commit_preserves_operator_edits_in_target_files(tmp_path, monkeypatch):
    """Operator added a footnote line at end of ai/features/SPEC.md.
    HEAD content = old. Working tree = old + footnote.
    callback computes new_content = old with **Status:** done.
    After call: HEAD commit has new_content; workdir has new_content + footnote (rebased).

    Verify via:
      git show HEAD:ai/features/SPEC.md  → has 'Status: done', NO footnote
      cat ai/features/SPEC.md            → has footnote (workdir untouched)
    """

def test_plumbing_commit_skips_when_no_fixes(tmp_path, monkeypatch):
    """fixes=[] → early return, no commit, HEAD unchanged."""

def test_plumbing_commit_handles_two_files_atomic(tmp_path, monkeypatch):
    """fixes=[(spec,…), (backlog,…)] → ONE commit with two files (not two commits)."""

def test_plumbing_commit_message_format(tmp_path, monkeypatch):
    """Commit message = 'docs: mark {spec_id} as {target} (callback auto-fix)'."""

def test_plumbing_commit_failure_in_hash_object_aborts(tmp_path, monkeypatch):
    """Make `git hash-object` fail (corrupt repo) → no commit, no exception leaks."""

def test_plumbing_commit_push_failure_does_not_raise(tmp_path, monkeypatch):
    """Suppress remote, simulate push rc=1 → log warning, function returns cleanly."""

def test_read_head_blob_returns_committed_content(tmp_path):
    """_read_head_blob('repo', 'a.md') after commit → returns content as written."""

def test_read_head_blob_returns_none_for_missing(tmp_path):
    """File never committed → git show rc=128 → returns None."""

def test_read_head_blob_ignores_workdir_modifications(tmp_path):
    """Commit content X, modify workdir to Y → _read_head_blob still returns X."""
```

**Push suppression (reuse Task 5 helper):**
```python
def _suppress_push(monkeypatch):
    real_run = subprocess.run
    def fake_run(cmd, *a, **kw):
        if isinstance(cmd, list) and "push" in cmd:
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        return real_run(cmd, *a, **kw)
    monkeypatch.setattr(callback.subprocess, "run", fake_run)
```

**Acceptance:**
- [ ] 10 tests pass with REAL git subprocess (no mocks of git).
- [ ] Test 2 explicitly diffs `git show HEAD:` vs `cat <file>` to prove invariant.
- [ ] No test creates a real remote (push suppressed via monkeypatch).
- [ ] File ≤ 200 LOC.

---

### Task 5 — Integration: verify_status_sync 8 scenarios (`tests/integration/test_callback_status_sync.py`)

**Files (NEW):**
- Create: `tests/integration/test_callback_status_sync.py` (~250 LOC — split into Task 5a / 5b if exceeds 300)

**Targets in callback.py:**
- `verify_status_sync` (line 773) — full guard chain
- `_resync_backlog_to_spec` (line 516)
- `_get_started_at` (line 704)

**Context:**
Eight scenarios from spec Goal section. Existing `test_callback_no_impl_demote.py` covers EC-8/9/10 (demote, happy, blocked-overwrite-compatible). This task adds the remaining FIVE scenarios (EC-11..EC-15) and consolidates the harness.

**Fixtures (reuse + extend from `test_callback_no_impl_demote.py`):**
- `_make_project(tmp_path, spec_id, allowed_files)` — already at lines 41-65 of existing file; **import** if pytest collection allows, else duplicate.
- `tmp_db` (sqlite + schema + DB_PATH patch) — lines 68-76.
- `_seed_task(project_id, label, pueue_id)` — lines 79-89.
- `_suppress_push(monkeypatch)` — lines 92-101.

**Decision:** to avoid awkward cross-test imports, COPY the fixtures into a shared module: `tests/integration/_callback_fixtures.py` (NOT in Allowed Files — therefore inline duplicate is the canonical approach. Coder MUST duplicate, not extract).

Wait — `tests/integration/test_callback_status_sync.py` is in Allowed Files; helper module is not. **Coder MUST inline-duplicate fixtures inside the test file.** This is the trade-off TECH-168 spec accepted.

**Test functions:**

```python
# --- EC-11: missing-section degrade-closed ---
def test_ec11_no_allowed_files_section_demotes_done_to_blocked(tmp_path, tmp_db, monkeypatch):
    """Spec without `## Allowed Files` heading at all + target='done'
    → _parse_allowed_files returns None
    → _has_implementation_commits returns False (degrade-closed)
    → demote with reason='missing_allowed_files_section'.
    """

# --- EC-12: empty-section degrade-closed (v1 marker, no bullets) ---
def test_ec12_v1_empty_section_demotes(tmp_path, tmp_db, monkeypatch):
    """Spec with `## Allowed Files\\n<!-- callback-allowlist v1 -->\\n`
    (marker but zero bullets) → returns []
    → _has_implementation_commits returns False
    → demote with reason='no_implementation_commits'.
    """

# --- EC-13: done-overwrite protection ---
def test_ec13_done_overwrite_protection(tmp_path, tmp_db, monkeypatch):
    """Spec already at HEAD has **Status:** done.
    Callback called with target='blocked' (e.g., delayed callback for failed task).
    → log info, _resync_backlog_to_spec(...,'done',...) called, EARLY RETURN.
    Spec stays done; backlog gets resynced to done.
    """

# --- EC-14: HEAD already synced — idempotent ---
def test_ec14_head_already_synced_no_commit(tmp_path, tmp_db, monkeypatch):
    """Spec=done at HEAD, backlog=done at HEAD, target=done, allowed=['src/x.py'],
    impl-commit present.
    → fixes list is empty → 'both spec and backlog are done ✓' log,
    NO new commit added (assert HEAD commit count unchanged).
    """

# --- EC-15: operator's uncommitted edits preserved (cross-cuts Task 4 but at full-flow level) ---
def test_ec15_operator_uncommitted_edits_in_spec_survive(tmp_path, tmp_db, monkeypatch):
    """Operator added a `## Notes` block to spec workdir AFTER autopilot finished
    but BEFORE callback fired. callback patches HEAD-content (no notes) +
    plumbing-commits → workdir notes still on disk.
    """

# --- EC-16: _resync_backlog_to_spec idempotency ---
def test_ec16_resync_backlog_idempotent_when_already_synced(tmp_path, tmp_db, monkeypatch):
    """spec=blocked, backlog=blocked at HEAD → backlog_re.search hits → early return,
    NO commit attempted (verify via git log count).
    """

# --- EC-17: _get_started_at lookup ---
def test_ec17_get_started_at_returns_iso_string(tmp_db):
    """Insert task_log row with explicit started_at='2026-05-01T10:00:00Z' →
    _get_started_at(pueue_id) returns that string."""

def test_ec17_get_started_at_missing_pueue_id_returns_none(tmp_db):
    """No row for pueue_id=999 → returns None."""

def test_ec17_get_started_at_returns_latest_when_duplicate(tmp_db):
    """Two rows same pueue_id, different started_at → returns row with highest id."""

def test_ec17_get_started_at_db_error_returns_none(tmp_db, monkeypatch):
    """Force db.get_db() to raise → caught, returns None, no exception leaks."""
```

**Note on EC-15 wording:**
The implementation reads HEAD blob (not working tree). So workdir notes are physically untouched. The test must commit baseline → write notes to workdir without commit → invoke callback → verify (a) HEAD commit doesn't include notes, (b) workdir file still has notes after callback.

**Acceptance:**
- [ ] 10 new tests pass; existing 3 in `test_callback_no_impl_demote.py` continue to pass.
- [ ] All tests use real fs + real git + real sqlite (per ADR-013).
- [ ] No `unittest.mock.patch` on `_apply_*` or `_parse_*` helpers — they run for real.
- [ ] File ≤ 350 LOC. If exceeds, split into `_status_sync_guards.py` + `_status_sync_resync.py` (both must be added to Allowed Files via spec amendment first — currently NOT allowed, so keep inline).

---

### Task 6 — Regression corpus (25 specs) (`tests/regression/test_callback_spec_corpus.py` + fixtures)

**Files (NEW):**
- Create: `tests/regression/__init__.py` (empty marker)
- Create: `tests/regression/spec_corpus/` (directory, via writing files inside)
- Create: 25 fixture spec files (5 per project) — see paths below
- Create: 25 sidecar `.expected.json` files (one per spec)
- Create: `tests/regression/test_callback_spec_corpus.py` (~120 LOC)

**Note on Allowed Files reading:**
The spec lists 5 sentinel fixture paths in `## Allowed Files`:
- `tests/regression/spec_corpus/awardybot_FTR-897.md`
- `tests/regression/spec_corpus/dowry_BUG-394.md`
- `tests/regression/spec_corpus/gipotenuza_FTR-098.md`
- `tests/regression/spec_corpus/plpilot_BUG-326.md`
- `tests/regression/spec_corpus/wb_ARCH-176a.md`

Plus the directory `tests/regression/spec_corpus/`. The remaining 20 fixture files are implicitly allowed (corpus pattern = whole directory whitelisted). Coder treats `tests/regression/spec_corpus/*.md` and `tests/regression/spec_corpus/*.expected.json` as covered by the directory entry.

**Per-project selection algorithm (5 specs each, picked to cover distinct parser shapes):**

For each project P in `[awardybot, dowry, gipotenuza, plpilot, wb]`:

| Slot | Required shape | Selection rule |
|------|----------------|----------------|
| **canonical** | Numbered list with backticks `1. \`path\`` | Pick the named one in spec (e.g. `dowry_BUG-394`) — already verified |
| **heading-variant** | Heading like `## Allowed Files (whitelist)` OR `## Updated Allowed Files` OR `## Files Allowed to Modify` | `grep -lE '^## (Updated )?Allowed Files( \\(\|$)\|^## Files Allowed to Modify' /home/dld/projects/{P}/ai/features/**/*.md \| head -1` |
| **fenced-block** | Backticked paths inside ` ``` ` block (legacy parser collects them) | `grep -lE '^\\\`\\\`\\\`' specs that also have `## Allowed Files` |
| **no-section** | NO `## Allowed Files` at all (parser returns None) | `grep -L '## Allowed Files' specs` (the gipotenuza one already meets this) |
| **multi-section** | Section with H3 subheadings (`### New files`, `### Existing files`) — wb/ARCH-176a style | `grep -lzP '## Allowed Files\\n(?:.*\\n)*?###\\s+(?:New\|Existing)' specs` |

**Concrete selection script (Coder runs once during Task 6):**

```bash
# scripts/vps/.. is NOT used; this is one-off operator command for spec selection.
# Run from /home/dld/projects/dld-tech168 (worktree root).

PROJECTS=(awardybot dowry gipotenuza plpilot wb)
DEST="tests/regression/spec_corpus"
mkdir -p "$DEST"

# --- Pinned (already verified to exist) ---
cp /home/dld/projects/awardybot/ai/features/FTR-897-2026-05-01-external-traffic-onboarding-mvp.md "$DEST/awardybot_FTR-897.md"
cp /home/dld/projects/dowry/ai/features/BUG-394-2026-04-30-parser-backfill-kickstart.md "$DEST/dowry_BUG-394.md"
cp /home/dld/projects/gipotenuza/ai/features/FTR-098-2026-05-01-review-tagger.md "$DEST/gipotenuza_FTR-098.md"
cp /home/dld/projects/plpilot/ai/features/BUG-326-2026-04-19-error-handling-observability.md "$DEST/plpilot_BUG-326.md"
cp /home/dld/projects/wb/ai/features/ARCH-176a-2026-04-26-foundation.md "$DEST/wb_ARCH-176a.md"

# --- 4 more per project (heading-variant / fenced / no-section / multi-section) ---
# Coder discovers via grep, then cp into "$DEST/{project}_{spec_id}__{shape}.md".
# Naming pattern lets test parametrization auto-discover.
```

**Concrete shape-suggestions (Coder verifies and adjusts via grep on actual VPS):**

| Project | canonical | heading-variant | fenced-block | no-section | multi-section |
|---------|-----------|-----------------|--------------|------------|---------------|
| awardybot | `FTR-897__canonical.md` (pinned) | grep `Updated Allowed Files\|Files Allowed to Modify` | grep ```` ```\` ``` paths in section | grep `-L '## Allowed'` | wb-style H3 split |
| dowry | `BUG-394__canonical.md` (pinned) | same | same | same | same |
| gipotenuza | grep canonical numbered list | same | same | `FTR-098__no-section.md` (pinned — confirmed missing) | same |
| plpilot | `BUG-326__canonical.md` (pinned) | same | same | same | same |
| wb | grep canonical | same | same | same | `ARCH-176a__multi-section.md` (pinned — confirmed) |

**Sidecar `.expected.json` schema (one per spec):**

```json
{
  "shape": "canonical | heading-variant | fenced-block | no-section | multi-section",
  "v1_marker": false,
  "expected_paths": [
    "src/domains/intelligence/tg_parser_connection.py",
    "src/domains/intelligence/models.py"
  ],
  "expected_return_type": "list",
  "_comment": "Generated 2026-05-02 from /home/dld/projects/dowry/ai/features/BUG-394-..."
}
```

For `no-section` specs:
```json
{ "shape": "no-section", "expected_paths": null, "expected_return_type": "None" }
```

For `v1 marker but malformed`:
```json
{ "shape": "v1-empty", "v1_marker": true, "expected_paths": [], "expected_return_type": "list" }
```

**Sidecar generation (deterministic, not regenerated by tests):**

Coder MUST hand-build each `.expected.json` by:
1. Reading the source spec.
2. Eyeballing the `## Allowed Files` block (or absence thereof).
3. Listing every backticked file-path in that block.
4. Writing the JSON.

This is human-verified ground truth. The test compares `_parse_allowed_files(fixture)` against this golden output.

**Test file:**

```python
# tests/regression/test_callback_spec_corpus.py
"""TECH-168 Task 6 — regression corpus.

Snapshots 25 real-world specs (5 per project: awardybot, dowry, gipotenuza,
plpilot, wb). Each fixture has a `.expected.json` sidecar with the
hand-verified parser output. Any regex change in callback.py that breaks
parser output for any fixture fails this test.

Naming convention: {project}_{spec_id}[__{shape}].md
                   {project}_{spec_id}[__{shape}].expected.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402

CORPUS_DIR = Path(__file__).parent / "spec_corpus"


def _corpus_specs():
    """Yield (spec_path, expected_dict) tuples for every .md with .expected.json sibling."""
    for spec in sorted(CORPUS_DIR.glob("*.md")):
        sidecar = spec.with_suffix(".expected.json")
        if not sidecar.is_file():
            pytest.fail(f"Missing sidecar: {sidecar}")
        yield pytest.param(spec, json.loads(sidecar.read_text()), id=spec.stem)


@pytest.mark.parametrize("spec_path,expected", list(_corpus_specs()))
def test_corpus_parse_matches_expected(spec_path, expected):
    actual = callback._parse_allowed_files(spec_path)
    if expected["expected_return_type"] == "None":
        assert actual is None, f"{spec_path.name}: expected None, got {actual}"
    else:
        assert actual == expected["expected_paths"], (
            f"{spec_path.name}: parser drift\n"
            f"  expected: {expected['expected_paths']}\n"
            f"  actual:   {actual}"
        )


def test_corpus_has_at_least_25_specs():
    """Coverage gate: <25 means a project's slot is missing."""
    md_files = list(CORPUS_DIR.glob("*.md"))
    assert len(md_files) >= 25, f"Corpus has only {len(md_files)} specs (need 25)"


def test_corpus_all_5_projects_represented():
    prefixes = {p.name.split("_")[0] for p in CORPUS_DIR.glob("*.md")}
    assert prefixes >= {"awardybot", "dowry", "gipotenuza", "plpilot", "wb"}, (
        f"Missing project: {{'awardybot','dowry','gipotenuza','plpilot','wb'}} - {prefixes}"
    )


def test_corpus_all_shapes_represented():
    shapes = set()
    for sidecar in CORPUS_DIR.glob("*.expected.json"):
        shapes.add(json.loads(sidecar.read_text()).get("shape", ""))
    expected_shapes = {"canonical", "heading-variant", "fenced-block", "no-section", "multi-section"}
    missing = expected_shapes - shapes
    assert not missing, f"Missing shapes: {missing}"
```

**Acceptance:**
- [ ] 25 .md fixtures present (5 per project).
- [ ] 25 .expected.json sidecars present, hand-verified.
- [ ] All 5 distinct shapes represented (canonical, heading-variant, fenced-block, no-section, multi-section).
- [ ] `pytest tests/regression/ -v` shows 28 passes (25 parametrized + 3 meta).
- [ ] Sidecar JSON validated by Python `json.loads` (no trailing commas).

---

### Task 7 — CI workflow (`.github/workflows/test.yml`)

**Files (NEW):**
- Create: `.github/workflows/test.yml` (~60 LOC)

**Decision:** existing `.github/workflows/ci.yml:74-87` already has a `python-test` job with `--cov-fail-under=0`. The new `test.yml` is a **dedicated, focused workflow** for callback test suite — runs **on every PR touching `scripts/vps/`** with strict coverage gate per EC-6 (callback.py >= 85%). Keeps CI signal isolated; doesn't replace `ci.yml`.

**Workflow design:**

```yaml
name: Callback Test Suite

on:
  pull_request:
    paths:
      - 'scripts/vps/**'
      - 'tests/unit/test_callback_*.py'
      - 'tests/integration/test_callback_*.py'
      - 'tests/regression/**'
      - '.github/workflows/test.yml'
  push:
    branches: [develop, main]
    paths:
      - 'scripts/vps/**'
      - 'tests/unit/test_callback_*.py'
      - 'tests/integration/test_callback_*.py'
      - 'tests/regression/**'

jobs:
  callback-tests:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Configure git for tests
        run: |
          git config --global user.email "ci@dld.test"
          git config --global user.name "CI"
          git config --global init.defaultBranch develop

      - name: Install dependencies
        run: |
          pip install pytest pytest-cov pytest-xdist

      - name: Unit tests
        run: pytest tests/unit/test_callback_*.py -v -n auto

      - name: Integration tests (real git + sqlite, no parallelism)
        # -n0 because integration tests use shared tmp_db / git workdir state
        run: pytest tests/integration/test_callback_*.py -v -n0

      - name: Regression corpus
        run: pytest tests/regression/ -v -n auto

      - name: Coverage gate (callback.py >= 85%)
        run: |
          pytest tests/unit/test_callback_*.py tests/integration/test_callback_*.py tests/regression/ \
            --cov=scripts/vps/callback \
            --cov-report=term-missing \
            --cov-report=xml \
            --cov-fail-under=85

      - name: Upload coverage artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: callback-coverage
          path: coverage.xml
```

**Rationale notes:**
- `-n auto` for unit + regression (parallel-safe — pure functions / read-only fixtures).
- `-n0` for integration (each test inits its own `tmp_path` git repo; pytest-xdist works but the existing `_suppress_push` monkeypatch on `callback.subprocess.run` is process-global — safer serial).
- Coverage gate on `scripts/vps/callback` (module-level) — **NOT** on whole `scripts/vps` (db.py / orchestrator.py have separate coverage stories).
- Path filter `paths:` ensures docs-only PRs don't trigger this expensive workflow.
- `timeout-minutes: 10` cap.

**Acceptance:**
- [ ] File parses as valid YAML (`yamllint .github/workflows/test.yml`).
- [ ] On a PR touching `scripts/vps/callback.py`, workflow triggers and all 4 jobs pass.
- [ ] Coverage gate fails the workflow if callback.py coverage < 85%.

---

### Task 8 — README for tests + corpus (`tests/regression/README.md`)

**Files (NEW):**
- Note: `tests/regression/README.md` is **NOT** in `## Allowed Files` of the spec.

**Resolution:** add the README as `tests/regression/spec_corpus/README.md` — covered by the `tests/regression/spec_corpus/` directory entry in Allowed Files.

- Create: `tests/regression/spec_corpus/README.md` (~80 LOC markdown)

**Content outline:**

```markdown
# Callback regression corpus

This directory holds 25 frozen real-world DLD specs (5 per project) used as
golden inputs for `callback._parse_allowed_files`. Any regex change to the
parser must keep these fixtures passing or be flagged as an intentional
breaking change.

## Layout

- `{project}_{spec_id}[__{shape}].md` — frozen copy of a real spec
- `{project}_{spec_id}[__{shape}].expected.json` — hand-verified parser output

## Shapes covered

| Shape | Description | Example |
|-------|-------------|---------|
| canonical | `## Allowed Files` + numbered list with backticks | `dowry_BUG-394.md` |
| heading-variant | `## Allowed Files (whitelist)` / `## Updated …` / `## Files Allowed to Modify` | TBD |
| fenced-block | Backticked paths inside ``` ``` ``` ``` block | TBD |
| no-section | No `## Allowed Files` heading at all → parser returns `None` | `gipotenuza_FTR-098.md` |
| multi-section | Section split by H3 subheadings (`### New files`, `### Existing files`) | `wb_ARCH-176a.md` |

## Adding a new fixture

1. Pick a real spec. Copy as `{project}_{spec_id}[__{shape}].md`.
2. Manually run the parser logic in your head (or `python3 -c …`).
3. Write `{project}_{spec_id}[__{shape}].expected.json`:
   ```json
   {
     "shape": "canonical",
     "expected_paths": ["src/foo.py", "src/bar.py"],
     "expected_return_type": "list"
   }
   ```
4. Run `pytest tests/regression/test_callback_spec_corpus.py -v`. New fixture is auto-discovered via glob.

## What counts as a breaking change

A parser change is **breaking** if:
- Any fixture's `expected_paths` list changes (item added, removed, reordered).
- Any fixture's `expected_return_type` flips between `list` and `None`.

If the change is intentional (e.g., bug-fix to legacy regex), **update both** the
fixture's `.expected.json` AND the spec's `## Drift Log` in the same PR. Reviewers
must confirm the change is desired across all 5 projects.

## Re-syncing fixtures from upstream

Fixtures are **frozen**. They do NOT track upstream specs. If a real project
updates its spec, the fixture stays at the snapshot date. Re-snapshot only
when adding a new shape or coverage scenario.
```

**Acceptance:**
- [ ] README ≤ 100 LOC.
- [ ] Lists all 5 shapes with one example each.
- [ ] Includes step-by-step "add new fixture" guide.
- [ ] Defines "breaking change" semantics so reviewers have a checklist.

---

### Execution Order

```
Task 1 (parser unit)        ─┐
Task 2 (mutators unit)       ├──┐
Task 3 (helpers unit)       ─┘  │
                                ├── Task 7 (CI) ── Task 8 (README)
Task 4 (plumbing integ)     ─┐  │
Task 5 (status_sync integ)   ├──┤
Task 6 (regression corpus)  ─┘  │
                                │
                          [coverage measurement]
```

- **Tasks 1-3** are independent unit-test files; can run in parallel.
- **Tasks 4-5** share git fixture patterns; do Task 4 first (smaller, validates pattern) then Task 5 reuses inline.
- **Task 6** is independent; only depends on `_parse_allowed_files` being unchanged (it is).
- **Task 7** is the gate — must come **after** Tasks 1-6 produce ≥85% coverage; CI workflow is last code task.
- **Task 8** is documentation; can be written in parallel with Task 6 since the structure is locked by spec.

### Dependencies

| Task | Depends on |
|------|------------|
| Task 1 | None (callback.py is read-only) |
| Task 2 | None |
| Task 3 | Task 2 (extends same file) |
| Task 4 | None |
| Task 5 | Task 4 (reuses git fixture pattern, copy-pasted inline) |
| Task 6 | None (parser is read-only) |
| Task 7 | Tasks 1, 2, 3, 4, 5, 6 (workflow needs tests to exist) |
| Task 8 | Task 6 (README documents the corpus structure) |

### Parallel-safe pairs

- (Task 1, Task 2, Task 4, Task 6) — all independent → can ship as 4 commits in parallel.
- (Task 7, Task 8) — last; depend on everything.

### Coverage budget per task (target: callback.py ≥ 85%)

| Task | callback.py lines covered (cumulative est.) |
|------|----------------------------------------------|
| Task 1 | parsing: ~50 lines (560-686) |
| Task 2 | mutators: +25 lines (403-451) |
| Task 3 | helpers + label/result: +30 lines (57-105, 126-176) |
| Task 4 | _git_commit_push, _read_head_blob: +50 lines (406-513) |
| Task 5 | verify_status_sync, _resync, _get_started_at: +90 lines (516-551, 704-875) |
| Task 6 | (re-exercises parser; no new coverage) |
| **Total** | **~245 / ~290 executable lines = ~85%** |

If coverage falls short, the gap is in `main()` orchestration (lines 905-1016) and `extract_agent_output` log-file branches — these are partially covered by existing `tests/scripts/test_callback.py` (which is broken vs. current code; coder MUST NOT touch it but should mention in review notes that fixing it is a separate follow-up TECH ticket).

### Research Sources

None used — all patterns established by existing `tests/unit/test_callback_implementation_guard.py` and `tests/integration/test_callback_no_impl_demote.py` (TECH-166). No external library upgrades needed.
