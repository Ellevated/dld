---
id: TECH-175
type: TECH
status: queued
priority: P2
risk: R2
created: 2026-05-02
---

# TECH-175 — Spark spec template hardening (DO-NOT-REMOVE markers)

**Status:** queued
**Priority:** P2
**Risk:** R2

---

## Problem

Даже после TECH-167 (canonical format + emit-time linter), потенциальные источники format drift'а:

1. Оператор/LLM при манипуляциях со спекой случайно удаляет маркер `<!-- callback-allowlist v1 -->`.
2. Reflect / planner / другой агент перезаписывает секцию своим форматом.
3. Spark v3 в будущем выпустит spec формата v2, не совместимого с v1.

---

## Goal

1. **DO-NOT-REMOVE markers** в спеке:
   ```markdown
   <!-- DLD-CALLBACK-MARKER-START v1 -->
   <!-- callback-allowlist v1: backticked paths only, one per row.
        DO NOT EDIT THIS SECTION manually after autopilot starts.
        Format is parsed by scripts/vps/callback.py — see TECH-167. -->
   ## Allowed Files

   - `path1`
   - `path2`
   <!-- DLD-CALLBACK-MARKER-END -->
   ```

2. **Schema versioning**: маркер несёт версию (`v1`, `v2`...). Callback parser выбирает routine по версии. Несовместимость → degrade-closed.

3. **Pre-commit hook (DLD repo)** для editing спек в `ai/features/`: `git diff` показывает изменения внутри marker — fail with warning "are you sure you want to edit allowlist after spec is queued?"

4. **Spark template — full spec skeleton** с маркерами на всех "владеемых callback'ом" секциях:
   - `<!-- DLD-CALLBACK-MARKER-START v1 -->` `## Allowed Files` `<!-- END -->`
   - `<!-- DLD-CALLBACK-MARKER-START v1 -->` `**Status:**` `<!-- END -->`
   - `<!-- DLD-CALLBACK-MARKER-START v1 -->` `**Blocked Reason:**` `<!-- END -->`

5. **Spec linter** — `scripts/vps/spec_lint.py <spec_path>` проверяет:
   - Маркеры присутствуют и парные.
   - Версии совпадают.
   - Содержимое внутри markers соответствует schema.

---

## Allowed Files

<!-- callback-allowlist v1 -->

- `.claude/skills/spark/feature-mode.md`
- `.claude/skills/spark/completion.md`
- `.claude/agents/spark/facilitator.md`
- `template/.claude/skills/spark/feature-mode.md`
- `template/.claude/skills/spark/completion.md`
- `template/.claude/agents/spark/facilitator.md`
- `scripts/vps/callback.py`
- `scripts/vps/spec_lint.py`
- `.git-hooks/pre-commit`
- `tests/unit/test_spec_lint.py`

---

## Tasks

1. **Template update** — Spark feature-mode.md выпускает спеки с marker'ами.
2. **Callback parser** — recognize markers, парсить **внутри** них; отсутствие markers → fallback на TECH-167 v1 без markers (legacy).
3. **`spec_lint.py`** — standalone CLI.
4. **Pre-commit hook** в DLD repo — non-blocking warning, потому что иногда правки внутри markers легитимны (operator override).
5. **Documentation** в TECH-173 (orchestrator docs) — отдельный раздел про markers schema.
6. **Tests**: парсер на спеке с markers / без / с broken markers.

---

## Eval Criteria

| ID | Type | Description |
|----|------|-------------|
| EC-1 | deterministic | Spec с правильными markers — parsed correctly |
| EC-2 | deterministic | Spec без markers (legacy) — fallback на TECH-167 logic |
| EC-3 | deterministic | Spec с unmatched markers — degrade-closed |
| EC-4 | deterministic | Spec с unknown version (v9) — degrade-closed + warning |
| EC-5 | integration | Pre-commit hook предупреждает на правке внутри markers |
| EC-6 | integration | Spark выпускает spec с правильными markers |

---

## Drift Log

**Checked:** 2026-05-04 UTC
**Result:** no_drift

### Changes Detected
| File | Change Type | Action Taken |
|------|-------------|--------------|
| `scripts/vps/callback.py` | none | TECH-167 v1 parser intact at lines 575–700; safe to extend |
| `.claude/skills/spark/feature-mode.md` | none | Phase 5.5 linter present (lines 617–682), markers schema fits cleanly |
| `.claude/skills/spark/completion.md` | none | Pre-completion checklist already references marker grep |
| `.claude/agents/spark/facilitator.md` | none | Phase 5.5 references `feature-mode.md` regexes — only schema bump required |
| `template/.claude/skills/spark/feature-mode.md` | none | Mirrors root; same edits apply |
| `template/.claude/skills/spark/completion.md` | none | Mirrors root |
| `template/.claude/agents/spark/facilitator.md` | none | Mirrors root |
| `tests/unit/test_callback_allowlist_v1.py` | none | Existing v1 tests must keep passing (regression anchor) |
| `.git-hooks/` | missing dir | NEW — first git-hook in repo, safe to create |
| `scripts/vps/spec_lint.py` | missing | NEW — task creates it |
| `tests/unit/test_spec_lint.py` | missing | NEW — task creates it |

### Notes
- TECH-167 v1 parser is the only existing allowlist-aware code. Backward-compat must be preserved (EC-2).
- callback.py audit-log + circuit-breaker (TECH-169..172) operate AFTER `_parse_allowed_files`; no changes required there.
- Feature-mode Phase 5.5 already has SSOT regexes; we extend them with marker pair regex.
- Spec linter is standalone (no pueue dep), runs in pre-commit and from CLI.

---

## Implementation Plan

### Research Sources
- TECH-167 spec (legacy reference, callback v1 marker baseline) — `ai/features/TECH-167-*.md` (in develop history)
- `tests/unit/test_callback_allowlist_v1.py` — pattern for new spec_lint tests
- `scripts/vps/callback.py` lines 575–700 — TECH-167 v1 parser SSOT

### Marker Schema (SSOT for all tasks)

```
START_RE = ^<!--\s*DLD-CALLBACK-MARKER-START\s+v(?P<ver>\d+)\s*-->\s*$
END_RE   = ^<!--\s*DLD-CALLBACK-MARKER-END\s*-->\s*$
SUPPORTED_VERSIONS = {"1"}        # any other version → degrade-closed
```

A "marker block" is the line range strictly between a START line and the next END line. Markers are **block-level** (occupy their own line, no inline). Sections wrapped by markers (Phase 1 of this task list):

| Wrapped section | Heading anchor inside block |
|------|--------|
| Allowed Files | `## Allowed Files` (must contain TECH-167 `<!-- callback-allowlist v1 -->` marker, unchanged) |
| Status (header) | `**Status:**` line |
| Blocked Reason | `**Blocked Reason:**` line (optional — block tolerated if missing line) |

---

### Task 1: scripts/vps/spec_lint.py (NEW CLI)

**Files:**
- Create: `scripts/vps/spec_lint.py` (~120 LOC)

**Context:** Standalone CLI invoked from pre-commit hook and CI. Validates marker pairing, version, and inner content. Exit 0 = ok, exit 1 = error (machine-parseable codes on stderr).

**Public surface:**
```python
def lint_spec(text: str) -> list[LintError]:    # importable from tests
    ...
def main(argv: list[str]) -> int:               # CLI entry; returns exit code
    ...
```

**Error codes (stderr format `LINT_E0XX path:line message`):**
- `LINT_E001_NO_MARKERS` — spec has no DLD-CALLBACK-MARKER blocks at all (warn-only when `--legacy-ok`, else error)
- `LINT_E002_UNMATCHED_START` — START with no END before EOF or before next START
- `LINT_E003_UNMATCHED_END` — END before any START
- `LINT_E004_NESTED` — START inside an unclosed block
- `LINT_E005_UNKNOWN_VERSION` — `v` ≠ supported set
- `LINT_E006_ALLOWED_FILES_OUTSIDE_BLOCK` — `## Allowed Files` heading present but not enclosed in a marker block
- `LINT_E007_MARKER_BLOCK_EMPTY` — block contains no recognised content
- `LINT_E008_INNER_TECH167_MISSING` — Allowed Files block missing inner `<!-- callback-allowlist v1 -->` marker (back-compat anchor)

**Algorithm sketch:**
```python
def lint_spec(text: str) -> list[LintError]:
    lines = text.splitlines()
    blocks: list[tuple[int, int, str]] = []   # (start_idx, end_idx, version)
    open_start: int | None = None
    open_ver: str | None = None
    errs: list[LintError] = []
    for i, ln in enumerate(lines):
        if m := START_RE.match(ln):
            if open_start is not None:
                errs.append(("LINT_E004_NESTED", i, "marker started inside open block"))
            open_start, open_ver = i, m.group("ver")
            if open_ver not in SUPPORTED_VERSIONS:
                errs.append(("LINT_E005_UNKNOWN_VERSION", i, f"v{open_ver}"))
        elif END_RE.match(ln):
            if open_start is None:
                errs.append(("LINT_E003_UNMATCHED_END", i, ""))
            else:
                blocks.append((open_start, i, open_ver))
                open_start = open_ver = None
    if open_start is not None:
        errs.append(("LINT_E002_UNMATCHED_START", open_start, ""))

    # Allowed Files coverage check
    af_idx = next((i for i, ln in enumerate(lines) if ALLOWED_HEAD_RE.match(ln)), None)
    if af_idx is not None and not _is_inside_any_block(af_idx, blocks):
        errs.append(("LINT_E006_ALLOWED_FILES_OUTSIDE_BLOCK", af_idx, ""))
    # Inner v1 marker present when Allowed Files block exists
    for s, e, _v in blocks:
        body = "\n".join(lines[s+1:e])
        if ALLOWED_HEAD_RE.search(body) and not TECH167_INNER_RE.search(body):
            errs.append(("LINT_E008_INNER_TECH167_MISSING", s, ""))
    if not blocks and not errs:
        errs.append(("LINT_E001_NO_MARKERS", 0, ""))
    return errs


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--legacy-ok", action="store_true",
                        help="downgrade LINT_E001 to warning (legacy specs)")
    args = parser.parse_args(argv)
    rc = 0
    for p in args.paths:
        errs = lint_spec(Path(p).read_text(errors="replace"))
        for code, line, msg in errs:
            stream = sys.stderr if not (args.legacy_ok and code == "LINT_E001_NO_MARKERS") else sys.stdout
            print(f"{code} {p}:{line+1} {msg}".rstrip(), file=stream)
            if stream is sys.stderr:
                rc = 1
    return rc
```

**Acceptance:**
- `python3 scripts/vps/spec_lint.py ai/features/TECH-175-*.md` exits 0 once Task 3 has added markers (CI smoke).
- `python3 scripts/vps/spec_lint.py /tmp/missing-end.md` exits 1, prints `LINT_E002_UNMATCHED_START`.
- File ≤ 200 LOC.

---

### Task 2: scripts/vps/callback.py — marker-aware allowlist parser

**Files:**
- Modify: `scripts/vps/callback.py` (insert ~50 LOC, no deletions)

**Context:** Add a new layer ABOVE `_parse_allowed_files_v1`. If marker pair found and version supported, parse strictly inside. Unknown version → `[]` (degrade-closed). Markers absent → fall through to existing TECH-167 v1 logic (preserves EC-2 legacy fallback).

**Changes:**

1. Add module-level regex constants near other `_ALLOWED_FILES_*` patterns (~line 580):
   ```python
   _DLD_MARKER_START_RE = re.compile(
       r"^<!--\s*DLD-CALLBACK-MARKER-START\s+v(?P<ver>\d+)\s*-->\s*$"
   )
   _DLD_MARKER_END_RE = re.compile(r"^<!--\s*DLD-CALLBACK-MARKER-END\s*-->\s*$")
   _DLD_SUPPORTED_MARKER_VERSIONS = frozenset({"1"})
   ```

2. New helper inserted directly before `_parse_allowed_files_v1` (~line 602):
   ```python
   def _parse_allowed_files_marker(spec_text: str) -> list[str] | None:
       """Marker-aware parser (TECH-175). Returns:
           list[str]: ≥0 paths inside a v1 marker block containing
                      ## Allowed Files (success or empty=degrade-closed).
           None     : no DLD-CALLBACK-MARKER blocks present (caller falls
                      back to TECH-167 v1 / legacy parsers).
       """
       lines = spec_text.splitlines()
       i = 0
       while i < len(lines):
           m = _DLD_MARKER_START_RE.match(lines[i])
           if not m:
               i += 1; continue
           ver = m.group("ver")
           # Find matching END (no nesting allowed; first END wins).
           j = i + 1
           while j < len(lines) and not _DLD_MARKER_END_RE.match(lines[j]):
               j += 1
           if j >= len(lines):
               log.warning("ALLOWED_FILES: unmatched DLD-CALLBACK-MARKER-START at line %d → degrade-closed", i+1)
               return []
           block = lines[i+1:j]
           block_text = "\n".join(block)
           if _ALLOWED_FILES_V1_HEADING_RE.search(block_text):
               if ver not in _DLD_SUPPORTED_MARKER_VERSIONS:
                   log.warning("ALLOWED_FILES: unknown marker version v%s → degrade-closed", ver)
                   return []
               # Reuse v1 strict bullet matcher.
               paths = [m.group(1) for ln in block
                        if (m := _ALLOWED_FILES_V1_BULLET_RE.match(ln))]
               return paths     # may be [] (marker present, no bullets)
           i = j + 1            # block didn't contain Allowed Files; keep scanning
       return None              # no relevant marker blocks
   ```

3. Hook it in `_parse_allowed_files` (replace the body around current line 678):
   ```python
   def _parse_allowed_files(spec_path: Path) -> list[str] | None:
       try:
           text = spec_path.read_text(errors="replace")
       except OSError as exc:
           log.warning("ALLOWED_FILES: read failed for %s: %s", spec_path, exc)
           return None

       # TECH-175: marker-aware first
       marker = _parse_allowed_files_marker(text)
       if marker is not None:
           log.info("ALLOWED_FILES: marker-aware parse for %s → %d path(s)",
                    spec_path.name, len(marker))
           return marker

       v1 = _parse_allowed_files_v1(text)
       if v1 is not None:
           log.info("ALLOWED_FILES: v1 canonical parse for %s → %d path(s)",
                    spec_path.name, len(v1))
           return v1

       legacy = _parse_allowed_files_legacy(text)
       if legacy is not None:
           log.info("ALLOWED_FILES: legacy fallback parse for %s → %d path(s)",
                    spec_path.name, len(legacy))
       return legacy
   ```

**Acceptance:**
- All existing `tests/unit/test_callback_allowlist_v1.py` tests still pass unchanged (no marker → legacy/v1 fallback).
- New tests in Task 5 cover EC-1/EC-3/EC-4.
- Diff ≤ 80 LOC.

---

### Task 3: Spark template — emit specs with marker pairs

**Files:**
- Modify: `.claude/skills/spark/feature-mode.md`
- Modify: `template/.claude/skills/spark/feature-mode.md`
- Modify: `.claude/skills/spark/completion.md`
- Modify: `template/.claude/skills/spark/completion.md`
- Modify: `.claude/agents/spark/facilitator.md`
- Modify: `template/.claude/agents/spark/facilitator.md`

**Context:** Update Phase 5 (template scaffold) and Phase 5.5 (linter regex SSOT) so freshly written specs include outer marker pairs. Mirror to template/.

**3a. feature-mode.md — Phase 5 template scaffold**

Replace the existing `## Allowed Files` block (~lines 368–392) with:

```markdown
<!-- DLD-CALLBACK-MARKER-START v1 -->
## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175. -->

ONLY the files listed below may be modified during implementation.

- `path/to/file1.py` — reason (modify)
- `path/to/file2.py` — reason (modify)
- `path/to/new_file.py` — reason (NEW)
- `tests/path/to/test_file.py` — reason (NEW)

<!-- DLD-CALLBACK-MARKER-END -->
```

Wrap the spec header (Status line) — replace the very top of the template block (~line 324) with:

```markdown
<!-- DLD-CALLBACK-MARKER-START v1 -->
**Status:** queued | **Priority:** P0/P1/P2 | **Date:** YYYY-MM-DD
<!-- DLD-CALLBACK-MARKER-END -->
```

Add an OPTIONAL Blocked Reason scaffold immediately after that block (commented out so it only renders when callback writes it):

```markdown
<!-- DLD-CALLBACK-MARKER-START v1 -->
<!-- **Blocked Reason:** populated by callback.py when guard demotes to blocked -->
<!-- DLD-CALLBACK-MARKER-END -->
```

**3b. feature-mode.md — Phase 5.5 linter SSOT**

Append to the regex SSOT block (~line 626):

```
DLD_START_RE = ^<!--\s*DLD-CALLBACK-MARKER-START\s+v(?P<ver>\d+)\s*-->\s*$
DLD_END_RE   = ^<!--\s*DLD-CALLBACK-MARKER-END\s*-->\s*$
```

Add Algorithm step 2½ (between current 2 and 3): "Verify `## Allowed Files` heading sits inside a `DLD_START_RE … DLD_END_RE` block of supported version (v1). Mismatch → fail `ALLOWLIST_E007_NOT_IN_MARKER_BLOCK`."

Add error codes E007/E008 to the list with same semantics as Task 1's `LINT_E006`/`LINT_E005`.

**3c. completion.md — Pre-completion checklist**

Modify item 6 (line 46) to also grep for the outer marker:

```markdown
6. [ ] **Allowlist Linter passed** (Phase 5.5) — `grep '<!-- callback-allowlist v1' ai/features/{TASK_ID}*.md` returns ≥1 line, `grep '<!-- DLD-CALLBACK-MARKER-START v1 -->' ai/features/{TASK_ID}*.md` returns ≥2 lines (Allowed Files + Status), and `## Allowed Files` heading exists exactly once
```

**3d. facilitator.md — Phase 5.5 step list**

Add to the regex list (~line 217):
```
- DLD_START_RE = ^<!--\s*DLD-CALLBACK-MARKER-START\s+v(?P<ver>\d+)\s*-->\s*$
- DLD_END_RE   = ^<!--\s*DLD-CALLBACK-MARKER-END\s*-->\s*$
- Verify `## Allowed Files` is enclosed in a DLD-CALLBACK-MARKER block with ver in {"1"}.
```

**Acceptance:**
- `diff .claude/skills/spark/feature-mode.md template/.claude/skills/spark/feature-mode.md` shows only DLD-specific extension drift unchanged from before; new section blocks identical.
- Manual: dry-run Spark Phase 5 (mental walk) yields a spec body where every callback-owned section is wrapped.
- Total LOC delta ≤ 70 per file pair.

---

### Task 4: .git-hooks/pre-commit (NEW, non-blocking warning)

**Files:**
- Create: `.git-hooks/pre-commit` (~50 LOC bash, executable)

**Context:** When operator commits changes to `ai/features/*.md`, warn (do NOT block) if any diff hunk falls inside a DLD-CALLBACK-MARKER block. Operator overrides are sometimes legitimate — print warning to stderr but always exit 0.

**Skeleton:**
```bash
#!/usr/bin/env bash
# .git-hooks/pre-commit — TECH-175 spec marker drift warner.
# Activate via: git config core.hooksPath .git-hooks
set -uo pipefail

changed=$(git diff --cached --name-only --diff-filter=ACMR | grep -E '^ai/features/.*\.md$' || true)
[[ -z "$changed" ]] && exit 0

warned=0
while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    # Pull staged hunks only; let spec_lint do structural checks.
    diff_text=$(git diff --cached -U0 -- "$f" || true)
    [[ -z "$diff_text" ]] && continue
    # Cheap heuristic: does ANY '+' or '-' line fall between START and END markers
    # in the staged file? Use python helper from scripts/vps/spec_lint.py.
    if python3 scripts/vps/spec_lint.py --diff-warn "$f" >&2 2>/dev/null; then
        :
    else
        echo "[pre-commit warn] $f: edit touches DLD-CALLBACK-MARKER block." >&2
        echo "                Are you sure? Markers are owned by Spark/callback." >&2
        warned=1
    fi
done <<< "$changed"

# Always exit 0 — warning only.
exit 0
```

**Note:** The `--diff-warn` flag is a tiny addition to Task 1's CLI: when set, spec_lint reads stdin or file and exits 2 if any marker block intersects staged diff hunks (parsed via `git diff --cached -U0`). The hook then prints a friendly warning. Implementation hint:
```python
# spec_lint.py extra path
if args.diff_warn:
    diff = subprocess.check_output(["git", "diff", "--cached", "-U0", "--", path]).decode()
    hits = _diff_intersects_marker_block(diff, lint_spec_blocks(path))
    sys.exit(2 if hits else 0)
```

**Acceptance:**
- Touching a marker block in a staged spec → warning to stderr, exit 0.
- Touching prose outside markers → silent.
- `git config core.hooksPath` documented in commit message and (optionally) wired into `scripts/vps/setup-vps.sh` (out of scope for this spec).

---

### Task 5: tests/unit/test_spec_lint.py (NEW, ~120 LOC)

**Files:**
- Create: `tests/unit/test_spec_lint.py`

**Context:** Cover EC-1..EC-4 plus the new callback parser layer added in Task 2. Pattern after `test_callback_allowlist_v1.py`.

**Test list:**
1. `test_ec1_correct_markers_v1` — well-formed Allowed Files block, `lint_spec()` returns `[]`.
2. `test_ec1_callback_marker_parser_returns_paths` — `callback._parse_allowed_files_marker(text)` returns the 3 paths.
3. `test_ec2_legacy_no_markers_lint_warns` — spec lacks markers entirely; `lint_spec()` returns `[LINT_E001_NO_MARKERS]`; with `--legacy-ok` exit 0.
4. `test_ec2_legacy_callback_falls_back_to_v1` — same spec, `callback._parse_allowed_files()` still finds paths via TECH-167 v1.
5. `test_ec3_unmatched_start` — START without END → `LINT_E002_UNMATCHED_START` AND `callback._parse_allowed_files_marker()` returns `[]` (degrade-closed).
6. `test_ec3_unmatched_end` — orphan END → `LINT_E003_UNMATCHED_END`.
7. `test_ec4_unknown_version_lint` — `v9` block → `LINT_E005_UNKNOWN_VERSION`.
8. `test_ec4_unknown_version_callback_degrades_closed` — `v9` Allowed Files block → callback returns `[]`.
9. `test_allowed_files_outside_block_e006` — heading exists outside any marker block → `LINT_E006_ALLOWED_FILES_OUTSIDE_BLOCK`.
10. `test_inner_tech167_marker_required_e008` — block has Allowed Files but no `<!-- callback-allowlist v1 -->` inner marker → `LINT_E008_INNER_TECH167_MISSING`.

**Skeleton:**
```python
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "vps"))
import callback  # noqa: E402
import spec_lint  # noqa: E402


def test_ec1_correct_markers_v1():
    text = """\
# TECH-XXX
<!-- DLD-CALLBACK-MARKER-START v1 -->
## Allowed Files

<!-- callback-allowlist v1 -->

- `a.py`
- `b/c.py`

<!-- DLD-CALLBACK-MARKER-END -->
"""
    assert spec_lint.lint_spec(text) == []
    assert callback._parse_allowed_files_marker(text) == ["a.py", "b/c.py"]


def test_ec3_unmatched_start():
    text = "<!-- DLD-CALLBACK-MARKER-START v1 -->\n## Allowed Files\n- `a.py`\n"
    codes = [e[0] for e in spec_lint.lint_spec(text)]
    assert "LINT_E002_UNMATCHED_START" in codes
    assert callback._parse_allowed_files_marker(text) == []


def test_ec4_unknown_version_callback_degrades_closed(tmp_path):
    spec = tmp_path / "x.md"
    spec.write_text("""\
<!-- DLD-CALLBACK-MARKER-START v9 -->
## Allowed Files

<!-- callback-allowlist v1 -->

- `a.py`
<!-- DLD-CALLBACK-MARKER-END -->
""")
    assert callback._parse_allowed_files(spec) == []
# ... etc.
```

**Acceptance:**
- `pytest tests/unit/test_spec_lint.py -v` — all 10 cases green.
- File ≤ 250 LOC (test budget).
- No regression: `pytest tests/unit/test_callback_allowlist_v1.py` still passes.

---

### Task 6: Integration verification for EC-5 / EC-6 (manual + scripted)

**Files:**
- No new code; verification artefacts go in commit message + this spec's `## Autopilot Log` section after run.

**Context:** EC-5 and EC-6 are integration-shaped. Two scripted recipes the operator/QA can run.

**EC-5 — pre-commit warning recipe:**
```bash
git config core.hooksPath .git-hooks   # one-time per checkout
# 1. Pick any spec generated under Task 3 conventions
SPEC=$(ls ai/features/TECH-175-*.md | head -n1)
# 2. Edit a path inside the Allowed Files marker block
sed -i 's|`scripts/vps/callback.py`|`scripts/vps/callback.py` # operator override|' "$SPEC"
git add "$SPEC"
git commit -m "test: trigger marker warning"   # expect stderr warning, exit 0
git reset HEAD~1 && git checkout -- "$SPEC"    # cleanup
```

**EC-6 — Spark output recipe:**
```bash
# Run Spark in a sandbox and inspect the produced spec
/spark "test feature: dummy noop"
NEW=$(ls -t ai/features/ | head -n1)
grep -c 'DLD-CALLBACK-MARKER-START v1' "ai/features/$NEW"   # expect 2 or 3
python3 scripts/vps/spec_lint.py "ai/features/$NEW"          # expect exit 0
rm "ai/features/$NEW"  # cleanup
```

**Acceptance:**
- Both recipes documented in commit message of Task 6's commit (final task).
- Operator runs both at QA time; pasted output goes into `## Autopilot Log` section of this spec.

---

### Execution Order

```
Task 1 ─┐
        ├─→ Task 2 ─→ Task 5 ─→ Task 6 (verify)
Task 3 ─┘            ↑
Task 4 ──────────────┘   (depends on Task 1 CLI surface, --diff-warn flag)
```

- **Task 1** first — Task 4 imports its `--diff-warn` mode; Task 5 imports its `lint_spec()` API.
- **Task 2 and Task 3** are independent; can run in parallel.
- **Task 4** waits for Task 1 (needs CLI flag).
- **Task 5** waits for Task 1 + Task 2 (tests both modules).
- **Task 6** is the final verification step.

### Dependencies

- Task 2 → Task 1 only at test time (Task 5 uses both).
- Task 3 ↔ Task 2 are SSOT-coupled: same regex strings appear in feature-mode.md and callback.py. Both must land before any new spec hits autopilot.
- Task 4 depends on Task 1 (hook calls `spec_lint.py --diff-warn`).

### Risk Notes

- **Backward compat (CRITICAL):** `_parse_allowed_files()` MUST still parse legacy specs (no markers) via TECH-167 v1 / legacy paths. Task 5 test #4 anchors this.
- **Degrade-closed semantics:** unknown version OR unmatched markers → empty list, NOT None. This matches existing TECH-167 behavior (marker present + bad bullets = `[]`, see `_parse_allowed_files_v1` final return).
- **Callback audit log:** no schema change; `len(allowed)` already handles `[]` correctly.
- **Pre-commit hook:** must NEVER exit non-zero. ADR-004-style fail-safe.
- **Concurrency:** none — all touched code is per-spec / per-commit, no shared state.

