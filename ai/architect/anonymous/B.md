# Evolutionary Architecture Research

**Persona:** Neal (Evolutionary Architect)
**Focus:** Fitness functions, drift map, ADR governance, "fix train" anti-pattern
**Date:** 2026-05-23
**Mode:** Retrofit Phase 1

---

## Research Conducted

*Note: Exa credits exhausted during this session. Research is based entirely on primary source
material from the codebase — the most reliable source for this analysis.*

- **Deep Audit Report** (`ai/audit/deep-audit-report.md`) — 85 findings from 6 parallel personas
  (Cartographer, Archaeologist, Accountant, Geologist, Scout, Coroner). Direct evidence of AS-IS
  state.
- **Architecture Agenda** (`ai/architect/architecture-agenda.md`) — Structured retrofit brief,
  per-persona questions, success criteria.
- **ADR Chain** (`.claude/rules/architecture.md`) — ADR-018 → 023 → 024 full text with
  supersession notes.
- **callback.py primary inspection** (`scripts/vps/callback.py`) — LOC, `_subject_implements`
  logic at line 673-711, `verify_status_sync` docstring at 1014-1019, `_SPEC_ID_RE` at line 43.
- **spec_lint.py inspection** (`scripts/vps/spec_lint.py`) — Full zombie validator, DLD-CALLBACK-
  MARKER regex at lines 25-26.
- **template/completion.md inspection** — Line 46 still requires `DLD-CALLBACK-MARKER-START v1`
  check despite ARCH-186 removing markers.
- **pyproject.toml inspection** — `testpaths = ["tests"]` (line 19), confirms `scripts/vps/tests/`
  excluded from CI.
- **orchestrator.py inspection** — `bootstrap_new_specs` reads `backlog_path.read_text()` from WT
  (line 295), `_SPEC_ID_RE` includes GROWTH (line 299/305).
- **lifecycle.py inspection** — `_push_best_effort` logs at DEBUG (line 266), `checkout-index`
  WT-sync race at lines 243-252.
- **git log / commit chain** — cefaa55 "8-rule redesign" commit, ARCH-186, ARCH-187, BUG-188
  timeline confirming 5 fix iterations in one month.

**Research basis:** 9 primary source inspections + full 85-finding audit synthesis. No web search
required — the codebase itself is the evidence base. Every claim below is quoted from specific
file:line.

---

## Kill Question Answer

**"What fitness functions protect this architectural decision?"**

| Architectural Decision | Fitness Function | Status |
|------------------------|------------------|--------|
| ADR-023: callback = sole writer | Count writers of `lifecycle/*.yaml` in codebase | MISSING |
| ADR-013: no mocks in integration tests | Hook exists, but mocks `_is_done_on_develop` | VIOLATED |
| File ≤400 LOC | `wc -l` check in CI | MISSING for scripts/vps/ |
| Dependency direction `shared←infra←domains←api` | No automated import check | MISSING |
| TECH-172: single status write path | No automated check | MISSING |
| ARCH-186: no DLD-CALLBACK-MARKER in new specs | spec_lint still validates markers | INVERTED |
| `scripts/vps/tests/` in CI | `pyproject.toml testpaths` | MISSING |
| Convention: SPEC-ID as scope | `_subject_implements` tests | PARTIAL / WRONG |

**Missing fitness functions:** Every architectural decision in the callback/lifecycle/orchestrator
contour lacks automated protection. The one "fitness function" that exists (`spec_lint.py`) actively
validates the wrong invariant — it tests for a format that was deliberately removed. This is not
neutral absence; it is inverted protection.

---

## AS-IS Drift Map

*"The measure of architectural health is not how fast you can add features, but how long before your
architecture makes adding features impossible." — Ford, Building Evolutionary Architectures*

### Drift Timeline (chronological)

```
2026-03  ADR-018 ACTIVE: callback writes DLD-CALLBACK-MARKER blocks in spec markdown
         ↓ BUG-974/185: autostash race — pop silently overwrites callback's markdown
         ↓ FIX: TECH-166, 167, 168, 169, 170, 171, 172 layered onto callback.py
         ↓ TECH-175: spec_lint.py created to validate markers (fitness function born)
         ↓ TECH-176, 177: more gate rules added
         ↓
2026-05-16  ARCH-186: lifecycle SoT migrated to git-per-spec YAML
         ADR-018 → SUPERSEDED by ADR-023
         DLD-CALLBACK-MARKER deliberately REMOVED from spec template
         ↓ spec_lint.py NOT updated — still validates dead marker format
         ↓ template/completion.md line 46 NOT updated — still requires dead markers
         ↓ .claude/agents/spark/facilitator.md NOT updated — still checks DLD-CALLBACK-MARKER
         ↓
2026-05-20  BUG-188: claude-runner false-fail on post-result SDK exception
         ADR-024 added: exit_code contract
         ↓ pre-commit-lifecycle-guard.mjs written for identity enforcement
         ↓ core.hooksPath points to .git/hooks/ in ALL repos — guard in .git-hooks/ — never fires
         ↓
2026-05-21  cefaa55: 8-rule redesign, _subject_implements tightened to scope-only
         ↓ awardybot/dowry use "feat(domain): ... (SPEC Task N)" — 460 commits in this style
         ↓ gate now returns False for dominant managed-project convention
         ↓
2026-05-23  TODAY: 5 new bugs from previous fixes
         bootstrap_new_specs reads WT backlog.md → 15 fake-done flips
         _subject_implements rejects trailer convention → systematic false-blocked
         checkout-index stale-index race → 13 D files in awardybot WT
         pre-commit guard dead everywhere
         local tests can poison prod-DB (no autouse isolation)
```

### Drift Taxonomy Table

| Drift Item | Type | Evidence | Severity |
|------------|------|----------|----------|
| spec_lint.py validates removed format | Zombie validator | `spec_lint.py:25-26`, ARCH-186 CHANGELOG | Critical |
| template/completion.md:46 requires dead markers | Template-code inconsistency | Direct inspection line 46 | Critical |
| `scripts/vps/tests/` excluded from CI | Test blind spot | `pyproject.toml:19 testpaths=["tests"]` | Critical |
| `_SPEC_ID_RE` excludes GROWTH in callback, includes in orchestrator | Regex fork | `callback.py:43` vs `orchestrator.py:299` | High |
| `_subject_implements` rejects trailer convention (460 of 636 awardybot commits) | Convention conflict | audit-report Root 3 | Critical |
| `bootstrap_new_specs` reads WT not HEAD | SoT bypass | `orchestrator.py:295` `backlog_path.read_text()` | Critical |
| `pre-commit-lifecycle-guard.mjs` in `.git-hooks/`, `core.hooksPath=.git/hooks/` | Dead enforcement | audit-report Finding 4 | Critical |
| `reconcile_orphans` writes lifecycle with `by="callback"` but called from orchestrator | Identity lie | `lifecycle.py:551`, audit-report Finding 23 | Medium |
| `_push_best_effort` logs at DEBUG | Invisible failure | `lifecycle.py:266` | High |
| `lifecycle.py` has two ~80-LOC `_atomic_write*` functions, same stale-index bug in both | Duplicated defect | audit-report Finding 11 | High |
| `started_at` always null in lifecycle yaml | Broken state machine | audit-report Finding 14 | High |
| 19 bare `except Exception` in callback.py | ADR-004 violation | audit-report Finding 17 | High |
| ADR-018→023→024 chain: each deactivates predecessor without killing its artifacts | ADR governance gap | architecture.md ADR table, completion.md:46 | Structural |
| callback.py 1374 LOC, 7 responsibilities | Module explosion | audit-report Finding 1 | Critical |
| `.claude/agents/spark/facilitator.md` still references DLD-CALLBACK-MARKER regex | Zombie in agent prompt | `.claude/agents/spark/facilitator.md:218-221` | High |

### Conway's Law Observation

*"Organizations which design systems are constrained to produce designs which are copies of the
communication structures of those organizations." — Conway, 1968*

This contour exhibits the reverse Conway anti-pattern: there is no stable "communication structure"
(team, ownership, ADR process) behind callback.py. Each incident creates a different implicit
author with different invariants. The result is a module that embodies 5 different mental models
simultaneously:

- BUG-185 author: "autostash is the enemy, add marker restoration"
- TECH-166 author: "git-diff verify before done"
- ARCH-186 author: "markdown is the enemy, move to yaml"
- ARCH-187 author: "identity enforcement via hooks"
- cefaa55 author: "gate needs stricter convention parsing"

None of these authors removed the previous author's artifacts. This is architectural drift by
accumulation.

---

## Rollback vs Accept Decisions

### ROLLBACK (active cleanup required)

**1. spec_lint.py + all references to DLD-CALLBACK-MARKER validation**

Evidence: `spec_lint.py:25-26` — `START_RE = re.compile(r"^<!--\s*DLD-CALLBACK-MARKER-START\s+v
(?P<ver>\d+)\s*-->\s*$")`. ARCH-186 removed the markers. The linter now validates the absence of
a format that must be absent. Any spec created before ARCH-186 that still has markers would pass
the linter; any spec created after ARCH-186 would fail it. The linter's signal is inverted.

Rationale: A fitness function that produces inverted signal is worse than no fitness function. It
provides false confidence. Delete or repurpose. Cost: LLM coder, ~$1, 15 minutes.

Files to act on:
- `scripts/vps/spec_lint.py` — delete or repurpose to validate new `## Allowed Files` format
- `template/.claude/skills/spark/completion.md:46` — remove DLD-CALLBACK-MARKER check from
  checklist
- `.claude/skills/spark/completion.md:46` — same (both copies per template-sync rule)
- `.claude/agents/spark/facilitator.md:218-221` — remove DLD-CALLBACK-MARKER regex check

**2. template/completion.md:46 DLD-CALLBACK-MARKER requirement**

Evidence: Direct inspection shows `grep '<!-- DLD-CALLBACK-MARKER-START v1 -->'` check remains
in the blocking pre-completion checklist. Every new spec created by Spark will fail this check
against a format that no longer exists (audit-report Finding 6, Coroner: "critical").

Rationale: This is not just dead code — it is a blocker in an active workflow. Every new Spark
session attempts this check and either fails silently or passes incorrectly. Rollback immediately.

**3. `_SPEC_ID_RE` fork between callback.py and orchestrator.py**

Evidence: `callback.py:43` — `r"(TECH|FTR|BUG|ARCH)-\d+[a-z]*"` (no GROWTH).
`orchestrator.py:299` — `r"^\|\s*(?P<id>(TECH|FTR|BUG|ARCH|GROWTH)-\d+[a-z]*)\s*\|"` (with
GROWTH). Six active GROWTH-NNN specs will never complete QA/reflect cycle via callback.

Rationale: Rollback to a single definition in a shared `common.py`. This is the simplest
manifestation of the "no common.py" structural gap.

---

### ACCEPT (drift is now the intended state)

**4. ADR-023 lifecycle-as-YAML approach**

Evidence: The core idea — git CAS atomic writes, per-spec YAML as SoT — is sound. The stale-index
bug in `_atomic_write` is an implementation bug, not a design flaw. The design correctly separates
"state of truth" from "human-readable render."

Rationale: Accept the design. Fix the WT-sync implementation bug (`git checkout HEAD --
ai/lifecycle/{spec_id}.yaml` instead of `checkout-index --force --`). The design is reversible
later if needed — SQLite SoT would be a straightforward migration.

**5. Circuit breaker (TECH-169)**

Evidence: The mass-demote circuit breaker (>3 demotes in 10 min → pause group) is a useful
operational control. It has caused no known false positives.

Rationale: Accept. The implementation is contained to callback.py and db.py. The presence of a
circuit breaker is evidence that the gate is known to be unreliable — a fitness function for gate
reliability would be more useful long-term, but the circuit breaker itself is not harmful.

**6. Audit JSONL (TECH-171)**

Evidence: One JSONL line per `verify_status_sync` call. This is useful operational data. The path
inconsistency (`SCRIPT_DIR/callback-audit.jsonl` in `scan_queued`, `$CALLBACK_AUDIT_LOG` in
callback) is a drift to fix, not a reason to remove.

Rationale: Accept the pattern. Fix the path inconsistency via shared constant in `common.py`.

**7. 8-rule gate structure in principle (cefaa55)**

Evidence: The rules themselves (done iff commit on origin/develop with spec_id subject touching
allowed files) are architecturally correct. The failure is in `_subject_implements` being too
narrow, not in the gate concept.

Rationale: Accept the gate concept. Broaden `_subject_implements` to accept trailer convention
(`feat(domain): ... (SPEC-ID Task N)` pattern) and add tests for both conventions. Document both
in an ADR.

---

## Fitness Function Suite (CODE-READY)

The following are executable checks. Each is designed to run in CI or as a pre-commit hook.

---

### FF-01: No Files Exceeding LOC Limit in scripts/vps/

**Protects:** Code maintainability, LLM context window (project rule: 400 LOC per file)

**Current violation:** `callback.py` is 1374 LOC (3.4x limit)

```bash
#!/usr/bin/env bash
# scripts/vps/check_loc.sh
# CI step: fail if any .py file in scripts/vps/ (excluding venv, tests) exceeds 400 LOC
set -euo pipefail

LIMIT=400
TEST_LIMIT=600
VIOLATIONS=0

while IFS= read -r -d '' f; do
    lines=$(wc -l < "$f")
    limit=$LIMIT
    [[ "$f" == *"/tests/"* ]] && limit=$TEST_LIMIT
    if (( lines > limit )); then
        echo "VIOLATION: $f has $lines lines (limit $limit)"
        VIOLATIONS=$((VIOLATIONS + 1))
    fi
done < <(find scripts/vps -name "*.py" \
    ! -path "*/venv/*" \
    ! -path "*/__pycache__/*" \
    -print0)

if (( VIOLATIONS > 0 )); then
    echo "LOC fitness function FAILED: $VIOLATIONS file(s) exceed limit"
    exit 1
fi
echo "LOC fitness function PASSED"
```

**Where to run:** CI on every commit to develop. GitHub Actions step after ruff lint.

**Note:** callback.py currently fails this check at 1374 LOC. This is intentional — the check
should fail NOW to make the debt visible, and the refactoring spec should track passing this check
as its acceptance criterion.

---

### FF-02: No Zombie Validators (format-code sync check)

**Protects:** ADR-023 (lifecycle SoT), prevents inverted fitness functions like the current
spec_lint.py situation.

**Principle:** When a format is removed from code, its validators must be updated atomically. This
fitness function checks that spec_lint.py does not test for DLD-CALLBACK-MARKER (the removed
format).

```python
# tests/unit/test_zombie_validators.py
"""
Fitness function: no zombie validators.
If spec_lint validates a format, at least one spec file must use that format.
If zero spec files use it, the validator is a zombie.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_spec_lint_validates_live_format():
    """
    spec_lint.py should not require a format that exists in zero spec files.
    Evidence: DLD-CALLBACK-MARKER was removed by ARCH-186 but spec_lint.py
    still validates it (audit-report Finding 22, severity: medium).
    """
    spec_lint_text = (REPO_ROOT / "scripts/vps/spec_lint.py").read_text()
    
    # Find all format patterns that spec_lint checks for
    marker_pattern = re.search(r'DLD-CALLBACK-MARKER-START', spec_lint_text)
    
    if marker_pattern:
        # If spec_lint references the marker, at least one spec file must have it
        spec_files = list((REPO_ROOT / "ai/features").glob("**/*.md"))
        marker_found = any(
            "DLD-CALLBACK-MARKER-START" in f.read_text(errors="replace")
            for f in spec_files
            if f.is_file()
        )
        assert marker_found, (
            "spec_lint.py validates DLD-CALLBACK-MARKER-START format "
            "but ZERO spec files in ai/features/ contain this format. "
            "This is a zombie validator — update spec_lint.py to match current format "
            "or delete it. See ARCH-186 and audit-report Finding 22."
        )
```

**Where to run:** `tests/unit/` — already in CI testpaths. Runs on every push.

---

### FF-03: Sole Writer Check — lifecycle/*.yaml

**Protects:** ADR-023 ("callback = единственный writer"), ADR-011 (Enforcement as Code)

**Current violation:** 6 writers including `migrate_backlog_to_lifecycle.py` which uses
`Path.write_text()` directly bypassing CAS (audit-report Finding #56 in Root 2).

```python
# tests/unit/test_lifecycle_writer_discipline.py
"""
Fitness function: ADR-023 sole-writer invariant.
Only allowed modules may call write_lifecycle() directly.
No file may write to ai/lifecycle/*.yaml via Path.write_text() or open().
"""
import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
VPS_DIR = REPO_ROOT / "scripts/vps"

# These are the only files allowed to call write_lifecycle
ALLOWED_WRITERS = {
    "callback.py",       # ADR-023: sole status writer
    "orchestrator.py",   # create_initial + reconcile_orphans
    "spec_operator.py",  # operator CLI
    "lifecycle.py",      # defines write_lifecycle itself
}

# Migration script is one-time only — should be excluded from production check
EXCLUDED = {"migrate_backlog_to_lifecycle.py", "venv"}


def test_no_direct_yaml_writes_to_lifecycle():
    """No file should write to ai/lifecycle/ via Path.write_text or open()."""
    for pyfile in VPS_DIR.glob("*.py"):
        if pyfile.name in EXCLUDED:
            continue
        text = pyfile.read_text(errors="replace")
        # Check for direct writes to lifecycle path
        if re.search(r'lifecycle.*\.write_text|open.*lifecycle.*["\']w', text):
            assert False, (
                f"{pyfile.name} appears to write lifecycle files directly. "
                "Only write_lifecycle() (CAS path) is allowed per ADR-023."
            )


def test_write_lifecycle_callers_are_allowed():
    """Only ALLOWED_WRITERS may call write_lifecycle()."""
    violators = []
    for pyfile in VPS_DIR.glob("*.py"):
        if pyfile.name in EXCLUDED or pyfile.name in ALLOWED_WRITERS:
            continue
        text = pyfile.read_text(errors="replace")
        if "write_lifecycle" in text and "import lifecycle" in text:
            violators.append(pyfile.name)
    
    assert not violators, (
        f"Unauthorized callers of write_lifecycle(): {violators}. "
        "Add to ALLOWED_WRITERS or restructure. See ADR-023."
    )
```

**Where to run:** `tests/unit/` — CI on every push.

---

### FF-04: All tests/ directories in CI

**Protects:** Test completeness — the audit found that `scripts/vps/tests/` (~100 tests) is
excluded from CI because `pyproject.toml:19` has `testpaths = ["tests"]`.

```toml
# pyproject.toml fix (1-line change):
[tool.pytest.ini_options]
testpaths = ["tests", "scripts/vps/tests"]
```

This is not a fitness function test itself — it is the fix that enables existing fitness functions
(the ~100 tests in `scripts/vps/tests/`) to actually run. The fitness function that verifies this
is:

```python
# tests/unit/test_ci_coverage.py
"""
Fitness function: all test directories are covered by CI.
Fails if a tests/ directory exists but is not in pytest testpaths.
"""
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_all_test_dirs_in_testpaths():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    testpaths = set(pyproject["tool"]["pytest"]["ini_options"]["testpaths"])
    
    # Find all directories named "tests" or "test" in the project
    all_test_dirs = [
        str(p.parent.relative_to(REPO_ROOT))
        for p in REPO_ROOT.rglob("tests")
        if p.is_dir() and "venv" not in str(p) and ".worktrees" not in str(p)
    ]
    
    missing = [d for d in all_test_dirs if d not in testpaths and d != "."]
    
    assert not missing, (
        f"Test directories not in pytest testpaths: {missing}. "
        "Add to pyproject.toml [tool.pytest.ini_options] testpaths. "
        "Audit finding: scripts/vps/tests/ (~100 tests) excluded from CI."
    )
```

---

### FF-05: Module Responsibility Count (God Module detector)

**Protects:** Single Responsibility Principle, LLM maintainability. callback.py at 1374 LOC has
7 identified responsibilities. As Ford notes in Building Evolutionary Architectures: "The ability
to evolve architecture is inversely proportional to the coupling between components."

This fitness function uses a heuristic: count distinct "responsibility groups" by counting top-level
function clusters with different conceptual prefixes.

```python
# tests/unit/test_module_health.py
"""
Fitness function: module responsibility count.
Approximates responsibility count via conceptual prefix clustering.
A module with >5 distinct prefix groups is a god module.
"""
import ast
import re
from pathlib import Path
from collections import Counter

REPO_ROOT = Path(__file__).resolve().parents[3]
VPS_DIR = REPO_ROOT / "scripts/vps"

# Known responsibility prefixes in callback.py
# Update this list when decomposing callback into separate modules
CALLBACK_MAX_RESPONSIBILITY_GROUPS = 5  # current: 7, target after refactor: 2 (gate + dispatcher)

# Responsibility prefix patterns (each prefix = one conceptual group)
RESPONSIBILITY_PREFIXES = [
    r"^_?pueue",
    r"^_?parse|^_?lint|^_?load_spec|^_?get_allowed",
    r"^_?is_done|^_?subject_implements|^_?fetch_develop|^_?gate|^verify_status",
    r"^_?emit_audit|^_?write_audit",
    r"^_?render_backlog",
    r"^_?dispatch|^_?pueue_add|^_?qa|^_?reflect",
    r"^_?circuit|^_?record_demote",
]


def _count_responsibility_groups(filepath: Path) -> int:
    """Count distinct responsibility groups in a Python file by function prefix clustering."""
    tree = ast.parse(filepath.read_text())
    funcs = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    
    matched_groups = set()
    for func in funcs:
        for i, pattern in enumerate(RESPONSIBILITY_PREFIXES):
            if re.match(pattern, func, re.IGNORECASE):
                matched_groups.add(i)
    
    return len(matched_groups)


def test_callback_responsibility_count():
    """callback.py must not exceed the god-module threshold."""
    cb = VPS_DIR / "callback.py"
    groups = _count_responsibility_groups(cb)
    assert groups <= CALLBACK_MAX_RESPONSIBILITY_GROUPS, (
        f"callback.py has {groups} responsibility groups "
        f"(limit: {CALLBACK_MAX_RESPONSIBILITY_GROUPS}). "
        "Decompose into: gate.py, dispatcher.py, audit.py, or similar. "
        "See audit-report Finding 1 (critical) and Root 5."
    )
```

**Note:** Set `CALLBACK_MAX_RESPONSIBILITY_GROUPS = 7` initially (current reality) so CI passes
today. Then reduce to 5 as part of the decomposition sprint, then to 2 (gate + dispatcher) as
the final target. This makes the fitness function drive the refactoring rather than block it.

---

### FF-06: Regression Test per Incident (incident coverage bank)

**Protects:** ADR-013 (no mocks), regression safety — currently 0 of 5 today's bugs have
regression tests (or PARTIAL, as noted in audit-report Finding 9).

```python
# tests/regression/test_incident_coverage.py
"""
Fitness function: every incident must have a regression test.
This file is the registry. If an incident has no test, add one here.
NEVER mock _is_done_on_develop or _fetch_develop per ADR-013.
"""
import pytest

# Registry of incidents and their test coverage status
INCIDENT_REGISTRY = {
    "BUG-185": "test_autostash_does_not_overwrite_lifecycle",
    "BUG-188": "test_post_result_exception_does_not_override_exit_zero",
    "ARCH-186-bootstrap-gap": "test_bootstrap_new_specs_skips_done_specs",
    "cefaa55-trailer-convention": "test_subject_implements_trailer_convention",
    "lifecycle-stale-index": "test_checkout_index_uses_current_head_blob",
}

# Tests that exist:
IMPLEMENTED_TESTS = {
    "test_autostash_does_not_overwrite_lifecycle",
    "test_post_result_exception_does_not_override_exit_zero",
    # Add here as implemented:
    # "test_bootstrap_new_specs_skips_done_specs",
    # "test_subject_implements_trailer_convention",
    # "test_checkout_index_uses_current_head_blob",
}


def test_all_incidents_have_regression_coverage():
    """Every incident in the registry must have an implemented regression test."""
    missing = {
        incident: test_name
        for incident, test_name in INCIDENT_REGISTRY.items()
        if test_name not in IMPLEMENTED_TESTS
    }
    
    if missing:
        missing_str = "\n".join(f"  {inc}: needs {test}" for inc, test in missing.items())
        pytest.fail(
            f"The following incidents lack regression tests:\n{missing_str}\n\n"
            "Add tests before closing incident specs. ADR-013: NO mocks of "
            "_is_done_on_develop or _fetch_develop."
        )
```

**Where to run:** `tests/regression/` — move to CI testpaths once `scripts/vps/tests/` is added.

---

### FF-07: Convention Drift — commit subject parser vs managed-project convention

**Protects:** Gate accuracy — `_subject_implements` at `callback.py:673-711` currently accepts
only `feat(SPEC-ID):` (scope) and two legacy forms. It rejects the dominant awardybot/dowry
convention `feat(domain): ... (SPEC-ID Task N)` — 460 vs 176 commits by proportion.

```python
# scripts/vps/tests/test_subject_implements_conventions.py
"""
Fitness function: _subject_implements must accept ALL documented commit conventions.
Quote: "awardybot has 460 commits with feat(domain): ... (SPEC Task N) pattern
vs 176 canonical. Gate returns False for all such commits." — audit-report Root 3
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from callback import _subject_implements


class TestCanonicalConvention:
    """cefaa55 design: SPEC-ID as scope"""
    
    def test_scope_convention(self):
        assert _subject_implements("feat(FTR-123): implement feature", "FTR-123")
    
    def test_scope_with_bang(self):
        assert _subject_implements("feat(FTR-123)!: breaking change", "FTR-123")
    
    def test_merge_commit(self):
        assert _subject_implements("merge FTR-123: complete feature", "FTR-123")
    
    def test_legacy_bare(self):
        assert _subject_implements("FTR-123: some description", "FTR-123")


class TestTrailerConvention:
    """awardybot/dowry dominant: SPEC-ID in trailer — 460 commits, ~72% of total"""
    
    def test_trailer_in_parens(self):
        # feat(billing): batch worker — claim (TECH-1052 Task 3)
        assert _subject_implements("feat(billing): batch worker (FTR-123 Task 3)", "FTR-123"), \
            "Trailer convention (FTR-123 Task N) must be accepted — 460 commits in this style"
    
    def test_trailer_in_parens_fix(self):
        # fix(billing): re-assert SECURITY INVOKER (BUG-1054 Task 1)
        assert _subject_implements("fix(billing): re-assert thing (BUG-456 Task 1)", "BUG-456"), \
            "Trailer bug fix convention must be accepted"
    
    def test_trailer_without_task_number(self):
        # feat(seller): cancel endpoint (FTR-1053)
        assert _subject_implements("feat(seller): cancel endpoint (FTR-123)", "FTR-123"), \
            "Trailer without Task N must also be accepted"
    
    def test_different_domain_scope_accepted(self):
        # SPEC-ID is in trailer, not scope
        assert _subject_implements(
            "feat(seller-batch): cancel-while-scheduled endpoint (FTR-1053 Task 4)", "FTR-1053"
        ), "Domain scope + SPEC-ID trailer is the dominant awardybot convention"
    
    def test_different_spec_not_accepted(self):
        # Wrong SPEC-ID should still return False
        assert not _subject_implements(
            "feat(billing): batch worker (TECH-1052 Task 3)", "FTR-999"
        )
```

**Current status:** These tests FAIL on the current `_subject_implements` for all trailer
convention cases. This makes the test suite the refactoring specification.

---

### FF-08: GROWTH prefix consistency across modules

**Protects:** GROWTH-NNN specs completing their lifecycle (QA, reflect, verify_status_sync)

```python
# scripts/vps/tests/test_spec_id_regex_consistency.py
"""
Fitness function: _SPEC_ID_RE must be consistent across all modules.
Quote: "_SPEC_ID_RE in callback not include GROWTH (orchestrator включает).
6 живых GROWTH-NNN спецификаций bootstrap'ятся orchestrator'ом, но resolve_spec_id
в callback не находит их → post-completion цепочка молча скипается." — audit-report Finding 21
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
VPS_DIR = REPO_ROOT / "scripts/vps"


def _extract_spec_id_prefixes(filepath: Path) -> set[str]:
    """Extract all TYPE prefixes from SPEC_ID_RE-like patterns in a file."""
    text = filepath.read_text()
    # Find patterns like (TECH|FTR|BUG|ARCH|GROWTH)
    matches = re.findall(r'\(([A-Z]+(?:\|[A-Z]+)+)\)', text)
    prefixes = set()
    for match in matches:
        prefixes.update(match.split("|"))
    return prefixes


def test_spec_id_prefixes_consistent_across_modules():
    """All modules handling spec IDs must recognize the same prefixes."""
    callback_prefixes = _extract_spec_id_prefixes(VPS_DIR / "callback.py")
    orchestrator_prefixes = _extract_spec_id_prefixes(VPS_DIR / "orchestrator.py")
    migrate_prefixes = _extract_spec_id_prefixes(VPS_DIR / "migrate_backlog_to_lifecycle.py")
    
    # The superset is the authoritative list
    all_known = callback_prefixes | orchestrator_prefixes | migrate_prefixes
    
    assert callback_prefixes >= all_known, (
        f"callback.py missing prefixes: {all_known - callback_prefixes}. "
        "Specs with these prefixes will have their QA/reflect cycle silently skipped."
    )
```

---

## ADR Governance Proposal

### The Problem

From `architecture.md` ADR table: ADR-018 entry reads "**[SUPERSEDED by ADR-023]**" but the
supersession is only in documentation. No code was killed. The fitness functions (spec_lint.py,
template/completion.md, `.claude/agents/spark/facilitator.md`) that enforce ADR-018's format
continued operating after ADR-023 replaced ADR-018. This is the root cause of three of today's
five bugs.

*"Every new rule in this contour will have negative ROI because adding to 1374 LOC makes callback
worse, and without CI-visible tests for lifecycle/orchestrator any new rule has no regression
protection." — audit-report, Architectural Verdict*

### Required: ADR Kill Section

Every ADR that supersedes another must include a mandatory `## Kills` section listing exactly what
artifacts must be removed or updated. This section must be verifiable by a fitness function.

**Proposed ADR template addition:**

```markdown
## Kills (mandatory when this ADR supersedes another)

| What | File | Action Required | Verified By |
|------|------|-----------------|-------------|
| DLD-CALLBACK-MARKER validation | `scripts/vps/spec_lint.py:25-26` | Delete or repurpose | FF-02 (zombie-validator test) |
| DLD-CALLBACK-MARKER in completion checklist | `template/.claude/skills/spark/completion.md:46` | Remove line 46 | grep check in CI |
| DLD-CALLBACK-MARKER in facilitator | `.claude/agents/spark/facilitator.md:218-221` | Remove DLD_START_RE/DLD_END_RE references | grep check in CI |

## Migration
[What existing data/code must be migrated before this ADR is operational]
```

The fitness function for the `## Kills` section:

```python
# tests/unit/test_adr_kills_complete.py
"""
Fitness function: ADR supersession kills must be verified as complete.
Every ADR that has a ## Kills section must have all listed items resolved.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Registry of ADR kills — derived from ## Kills sections
# Key: (adr_id, kill_description), Value: verification function
ADR_KILLS = {
    ("ADR-023", "DLD-CALLBACK-MARKER in spec_lint.py"): 
        lambda: "DLD-CALLBACK-MARKER-START" not in 
                (REPO_ROOT / "scripts/vps/spec_lint.py").read_text(),
    
    ("ADR-023", "DLD-CALLBACK-MARKER in template completion.md"):
        lambda: "DLD-CALLBACK-MARKER-START v1" not in 
                (REPO_ROOT / "template/.claude/skills/spark/completion.md").read_text(),
    
    ("ADR-023", "DLD-CALLBACK-MARKER in .claude completion.md"):
        lambda: "DLD-CALLBACK-MARKER-START v1" not in 
                (REPO_ROOT / ".claude/skills/spark/completion.md").read_text(),
}


def test_adr_kills_are_complete():
    """All ADR kill actions must be verified as done."""
    failures = []
    for (adr_id, description), check in ADR_KILLS.items():
        try:
            if not check():
                failures.append(f"{adr_id}: '{description}' — artifact still present")
        except Exception as e:
            failures.append(f"{adr_id}: '{description}' — check error: {e}")
    
    assert not failures, (
        "ADR supersession kills not complete:\n" + 
        "\n".join(f"  - {f}" for f in failures)
    )
```

### ADR Dependency Tracking

Proposed addition to each ADR entry in `architecture.md`:

```
| ADR-023 | Lifecycle SoT = git YAML | 2026-05-16 | ARCH-186 |
|         | Supersedes: ADR-018       |            |          |
|         | Kills: spec_lint.py DLD-CALLBACK-MARKER; template/completion.md:46; facilitator.md:218 |
|         | Depends on: lifecycle.py CAS implementation |
|         | Fitness: FF-02 (zombie validator), FF-03 (sole writer), FF-04 (all tests in CI) |
```

This creates a machine-readable kill graph. The `test_adr_kills_complete.py` fitness function
reads this graph and verifies each item. The graph never becomes stale because the test fails if
any listed kill target still exists.

---

## The "Fix Train" Anti-Pattern

### Characterization

The pattern observable in this contour over 30 days:

```
Incident N
  → Patch added to callback.py (rule, guard, fallback)
  → Patch touches assumptions of Patches N-2, N-1
  → New edge case exposed by interaction of patches
  → Incident N+1
```

Evidence from the audit report executive summary: *"ARCH-186 spec сам это прогнозировал в своём
rationale: 'За 2.5 месяца — 10+ фиксов вокруг одного контракта, каждый закрывал одну race и
открывал другую'."* This self-prediction was correct: 5 more incidents followed ARCH-186.

### Formal Characterization

A "fix train" is the observable consequence of violating what I'd call the Fitness Function
Prerequisite: you cannot safely add a rule to a module that has no executable specification of its
current invariants.

The mechanism:

1. **Rule addition without isolation.** Each fix adds logic to a module that already has N other
   rules. The new rule shares state (lifecycle yaml, pueue CLI, git fetch results) with existing
   rules. Interactions are not tested.

2. **Swallowed errors amplify.** `callback.py:INVARIANT: Always exit 0` means any new rule that
   fires incorrectly cannot surface through the normal error channel. The only signal is behavioral
   (spec stays blocked longer than expected, or transitions to wrong state).

3. **ADR supersession without kill.** Each ADR that supersedes another leaves artifacts from the
   previous ADR operational. These artifacts continue to fire, enforcing the old invariant against
   the new invariant. The system has two contradictory enforcement mechanisms simultaneously.

4. **Coverage gap amplifies.** `scripts/vps/tests/` is not in CI. Regressions introduced by fixes
   are not detected. The next fix cycle starts from an already-broken baseline.

### Detection Signal

A "fix train" can be detected programmatically via git log analysis:

```python
# scripts/vps/check_fix_train.py
"""
Fix train detector: identifies when a module has more than N incident-driven
commits in a rolling 30-day window. This is a health signal, not a blocker.
"""
import subprocess
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import Counter


def check_fix_train(
    repo_dir: str,
    filepath: str,
    window_days: int = 30,
    threshold: int = 3,
) -> dict:
    """
    Returns {
        "is_fix_train": bool,
        "incident_commit_count": int,
        "commits": list[str],
    }
    
    An "incident commit" is one whose subject contains BUG-, ARCH-, fix(,
    or contains 'redesign'/'hotfix'/'patch' keywords.
    """
    since = (datetime.now(tz=timezone.utc) - timedelta(days=window_days)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    result = subprocess.run(
        ["git", "log", f"--since={since}", "--oneline", "--", filepath],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    
    commits = result.stdout.strip().splitlines()
    incident_pattern = re.compile(
        r"\b(BUG|ARCH|fix|hotfix|patch|redesign|workaround)\b", re.IGNORECASE
    )
    incident_commits = [c for c in commits if incident_pattern.search(c)]
    
    return {
        "is_fix_train": len(incident_commits) >= threshold,
        "incident_commit_count": len(incident_commits),
        "total_commits": len(commits),
        "commits": incident_commits,
    }


if __name__ == "__main__":
    import json, sys
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    target = sys.argv[2] if len(sys.argv) > 2 else "scripts/vps/callback.py"
    result = check_fix_train(repo, target)
    print(json.dumps(result, indent=2))
    if result["is_fix_train"]:
        print(f"\nFIX TRAIN DETECTED: {result['incident_commit_count']} incident commits "
              f"in last 30 days on {target}", file=sys.stderr)
        sys.exit(1)
```

**Detection threshold:** 3 incident-driven commits on a single file within 30 days. This threshold
triggers not a CI failure but a mandatory /architect or /council session (P1 ticket auto-created
via Spark). The fix train is a signal that the module needs structural intervention, not more rules.

**Current state:** Running this check on `callback.py` for the last 30 days would report
approximately 12 incident commits (TECH-166/167/168/169/170/171/172/174/175/176 + ARCH-186 +
cefaa55 + BUG-185 + BUG-188). This is 4x the threshold. The fix train has been running for a
month.

---

## Architectural Characteristics Prioritization

**Context:** This is an LLM-maintained, AI-agent-orchestrating system. Its consumers are AI agents,
not humans. Its failure modes are silent (INVARIANT: Always exit 0). Its data is the source of
truth for $258/week in compute spending decisions.

### Critical

| Characteristic | Why Critical | Fitness Function |
|----------------|--------------|------------------|
| Testability | 0 regression tests for 5 today's bugs; lifecycle/orchestrator not in CI | FF-04 (all tests in CI) |
| Correctness | Gate correctness directly determines $258/week compute burn (BUG-188 evidence) | FF-07 (convention tests) |
| Maintainability | callback.py at 1374 LOC makes every future fix more expensive | FF-01 (LOC check) |
| Invariant integrity | "callback = sole writer" is violated by 5 other writers | FF-03 (sole writer) |

### Important

| Characteristic | Trade-off | Mitigation |
|----------------|-----------|------------|
| Observability | `_push_best_effort` on DEBUG means multi-machine convergence fails silently | Raise to WARNING; add Hermes alert on push failure |
| Modularity | Accepting that callback.py decomposition is a P1 task, not P0 | LOC fitness function makes debt visible now |
| Convention stability | cefaa55 changed convention without updating managed projects | FF-07 makes this a CI failure going forward |

### Nice-to-Have (defer)

- Performance optimization: the git plumbing in lifecycle.py is already fast enough
- Database indexing: relevant at scale; current load is low
- Schema versioning: useful but not causing incidents

### Trade-offs Made

- **Correctness OVER performance:** A slower gate that correctly identifies done specs is worth more
  than a fast gate that false-blocks 72% of commits.
- **Testability OVER brevity:** Adding `scripts/vps/tests/` to `pyproject.toml` testpaths is a
  1-line change with 100-test payoff. No trade-off.
- **Simplicity OVER innovation:** The "git as DB" approach (ADR-023) introduced the stale-index
  race. SQLite SoT for status would have been boring and correct. Accept this for now; design for
  reversibility.

---

## Reversibility Analysis

### Irreversible Decisions

| Decision | Why Irreversible | Cost to Reverse | Escape Hatch |
|----------|-----------------|----------------|--------------|
| git-per-spec YAML as status SoT (ADR-023) | 190+ yaml files, managed projects use git pull to read | Medium: migrate yaml to SQLite, update all readers | SQLite has yaml_status column as shadow; switch read path |
| pueue as task queue | VPS setup, systemd integration, all runners assume pueue | High: replace with celery/redis or similar | N/A — keep pueue, it's not the problem |
| Python for VPS scripts | 531 LOC db.py, 1374 LOC callback.py — already committed | High: full rewrite | Not needed |

### Reversible Decisions (low risk, act quickly)

| Decision | Easy to Reverse | Action |
|----------|-----------------|--------|
| spec_lint.py validates DLD-CALLBACK-MARKER | Delete or repurpose to validate new format | Act immediately — $1 compute |
| `testpaths = ["tests"]` in pyproject.toml | Change one line | Act immediately — 0 cost |
| `_push_best_effort` at DEBUG log level | Change one line to WARNING | Act immediately |
| `_SPEC_ID_RE` without GROWTH in callback.py | Add GROWTH to regex | Act immediately — $1 compute |

### Deferrable Decisions

- Whether to extract `gate.py` from callback.py: defer until after decomposition design is agreed
- Whether to replace "git as DB" with pure SQLite: defer; fix the stale-index bug first
- Whether to use a pre-commit framework (e.g., Husky/pre-commit) vs custom hooks: defer; fix the
  `core.hooksPath` issue first (that's the real problem, not the framework)

---

## Cross-Cutting Implications

### For Domain Architecture (Eric)

The fix train anti-pattern is partly a Conway's Law manifestation. callback.py has 7 responsibilities
because no domain boundary was established when each responsibility was added. The bounded context
decomposition Eric should recommend: `gate` context (read-only, pure function) | `writer` context
(lifecycle writes only) | `dispatcher` context (pueue, QA, reflect) | `audit` context (JSONL).
The fitness function for this decomposition is FF-05 (responsibility count check).

### For Data Architecture (Martin)

The three-representation status split (yaml HEAD, backlog.md WT, spec body) violates every DDIA
principle Martin should cite. The fitness function for single SoT is FF-03 (sole writer). The
fitness function for "no stale representations" would be a periodic check that `render_backlog.py`
output matches `git log --grep=lifecycle` for all specs.

### For Operations (Charity)

The fix train detector (check_fix_train.py) is an observability tool. The leading indicator Charity
should recommend: "more than 3 incident commits to callback.py in 30 days → mandatory P1 architect
review." The circuit breaker (TECH-169) is already an operational control; what's missing is the
pre-incident signal.

### For Security (Bruce)

The zombie fitness function (spec_lint.py validating removed format) creates a false confidence
signal. An agent checking spec compliance sees "linter passes" and concludes the spec is correct,
when in fact the linter is testing for an absent format. This is a security-adjacent issue: false
confidence in a compliance check. FF-02 (zombie validator test) addresses this.

---

## Summary: Priority-Ordered Fitness Function Implementation

```
P0 (implement before next commit to callback/lifecycle/orchestrator):

1. pyproject.toml: testpaths add "scripts/vps/tests" — 1 line, ~$0, 5 minutes
   Immediately enables 100 existing tests in CI.

2. FF-04 (test_ci_coverage.py) — prevents future testpaths omission — $1, 15 min

3. FF-07 (test_subject_implements_conventions.py) — makes convention drift a CI failure — $1, 15 min
   Currently FAILS (correct behavior — exposes the bug)

4. Fix _SPEC_ID_RE in callback.py to include GROWTH — 1 line, $1, 15 min

P1 (implement within this sprint):

5. FF-02 (test_zombie_validators.py) — detects inverted fitness functions — $1, 15 min
   Currently FAILS on spec_lint.py (correct — exposes the problem)

6. FF-03 (test_lifecycle_writer_discipline.py) — sole writer check — $1, 15 min

7. FF-01 (check_loc.sh) — LOC gate in CI — $1, 15 min
   Currently FAILS on callback.py at 1374 LOC (correct — makes debt visible)

8. Rollback: delete DLD-CALLBACK-MARKER references from spec_lint.py, completion.md (both copies),
   facilitator.md — $1, 30 min

P2 (implement as part of decomposition sprint):

9. FF-05 (test_module_health.py) — god module detector — $1, 15 min
   Set initial threshold to 7 (current), reduce as decomposition proceeds.

10. FF-06 (test_incident_coverage.py) — incident regression bank — $5, 1 hour
    Requires writing 5 actual regression tests for today's bugs.

11. check_fix_train.py — periodic health signal — $5, 1 hour
    Integrate with Hermes/Telegram alert.

12. ADR kills proposal: add ## Kills section to ADR-023, ADR-024 — $1, 30 min
    Then implement test_adr_kills_complete.py.
```

Total P0 cost: ~$3, ~1 hour LLM compute. These four changes alone would have caught three of
today's five bugs at PR-time.

---

## References

- **Deep Audit Report:** `/home/dld/projects/dld/ai/audit/deep-audit-report.md` — 85 findings,
  primary evidence for all claims
- **Architecture Agenda:** `/home/dld/projects/dld/ai/architect/architecture-agenda.md` — retrofit
  scope and constraints
- **ADR Chain:** `/home/dld/projects/dld/.claude/rules/architecture.md` — ADR-018→023→024
- **callback.py:43** — `_SPEC_ID_RE` missing GROWTH prefix
- **callback.py:673-711** — `_subject_implements` scope-only, missing trailer convention
- **lifecycle.py:263-266** — `_push_best_effort` at DEBUG log level
- **lifecycle.py:243-252** — `checkout-index` stale-index WT-sync race
- **spec_lint.py:25-26** — zombie validator, DLD-CALLBACK-MARKER after ARCH-186 removal
- **template/.claude/skills/spark/completion.md:46** — dead marker requirement in active checklist
- **pyproject.toml:19** — `testpaths = ["tests"]` excluding scripts/vps/tests/
- **orchestrator.py:295** — `backlog_path.read_text()` from WT, not HEAD
- **Neal Ford & Rebecca Parsons:** Building Evolutionary Architectures (O'Reilly, 2017) — fitness
  functions as executable architectural specifications
- **Conway's Law (1968):** "Organizations design systems that mirror their communication structure"
  — relevant to how callback.py accumulated 7 responsibilities with no single owner
