# scripts/vps/tests/test_branch_prefix_parity.py
"""Parity between `gate_ancestry._BRANCH_PREFIX` and the tables in the autopilot prompts.

The map "spec type -> branch prefix" is a rule the dispatcher and the prompts must
agree on: `record_dispatch` writes `tech/TECH-9` into `task_log.branch` and the
ancestry gate asks git whether `origin/tech/TECH-9` is an ancestor of develop, while
the autopilot prompt is what actually creates the branch. When the two disagree, the
gate looks for a branch nobody made and reports `no_merged_implementation` on work
that shipped.

They have disagreed. On 2026-08-30 `_BRANCH_PREFIX` carried GROWTH and both prompt
tables did not, so a GROWTH spec would have been branched `task/` and gone invisible
to the gate. Nothing failed; the drift was found by reading (findings-2026-08-30, K3
— third recurrence of "a rule copied into prose diverges from the code").

Prose is not documentation of a dictionary — it is a second implementation. This test
is what makes the copies honest, the same way `test_allowlist_parity.py` binds the
Spark linter to the production parser.

ADR-013: no mocks. Real module import, real prompt files, both trees.
"""

import os
import re
import sys
from pathlib import Path

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import gate_ancestry  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]

# Both trees ship the same two prompts; a fix landing in one only is the defect class
# `rules/template-sync.md` calls the most common one in this repository.
PROMPTS = [
    ".claude/skills/autopilot/worktree-setup.md",
    ".claude/skills/autopilot/autopilot-git.md",
    "template/.claude/skills/autopilot/worktree-setup.md",
    "template/.claude/skills/autopilot/autopilot-git.md",
]

# Matches both table shapes in use:
#   | FTR-   | feature/    |
#   | FTR-XXX | `feature/FTR-XXX` | `.worktrees/FTR-XXX/` |
# The leading `\s*` is not cosmetic: worktree-setup.md indents its table inside a
# numbered step, autopilot-git.md does not.
ROW_RE = re.compile(
    r"^\s*\|\s*([A-Z]{3,6})-[A-Z]*\s*\|\s*`?([a-z]+)/",
    re.MULTILINE,
)


def _pairs_from(path: Path) -> dict:
    return {m.group(1): m.group(2) for m in ROW_RE.finditer(path.read_text(encoding="utf-8"))}


@pytest.mark.parametrize("rel", PROMPTS)
def test_prompt_table_matches_python_map(rel):
    """Every prompt table states exactly the map the dispatcher uses."""
    path = REPO_ROOT / rel
    assert path.is_file(), f"prompt missing: {rel}"

    found = _pairs_from(path)
    assert found, f"no branch-prefix table found in {rel} — did the table shape change?"

    expected = dict(gate_ancestry._BRANCH_PREFIX)
    assert found == expected, (
        f"{rel} disagrees with gate_ancestry._BRANCH_PREFIX.\n"
        f"  prompt: {sorted(found.items())}\n"
        f"  python: {sorted(expected.items())}\n"
        "A type in the code but not the prompt means autopilot creates a branch the "
        "ancestry gate never looks for."
    )


def test_branch_ref_for_agrees_with_the_table():
    """The public function, not just the dict — the prompts describe its output."""
    for kind, prefix in gate_ancestry._BRANCH_PREFIX.items():
        assert gate_ancestry.branch_ref_for(f"{kind}-9") == f"{prefix}/{kind}-9"


def test_unknown_type_is_refused_loudly():
    """An unlisted prefix must raise, not silently fall back to a default branch."""
    with pytest.raises(ValueError):
        gate_ancestry.branch_ref_for("XXX-9")


# --- The same parity, on the projects the orchestrator actually dispatches ----------
#
# The four prompts above live in this repo, so CI covers them. Each downstream project
# carries its own copy of the same two files, and nothing reached those — which is how
# GROWTH came to be in `_BRANCH_PREFIX` and in neither prompt of any of the seven repos
# on 2026-08-31, three weeks after the dict grew the entry.
#
# Point `FLEET_ROOT` at the directory holding the checkouts (e.g. `D:/dev`, or
# `~/projects` on the VPS) and this runs there too. It is opt-in because CI has no
# checkouts to look at; the structural fix is `scripts/check-fleet-drift.py` driving
# `differs` to zero, at which point these files are byte-identical to the ones above.

FLEET_ROOT = os.environ.get("FLEET_ROOT")
DOWNSTREAM_PROMPTS = [
    ".claude/skills/autopilot/autopilot-git.md",
    ".claude/skills/autopilot/worktree-setup.md",
]

# `  ARCH) BRANCH_PREFIX="arch" ;;` — the bash form the table alone does not cover.
BASH_CASE_RE = re.compile(r"^\s*([A-Z]{3,6})\)\s*BRANCH_PREFIX=\"([a-z]+)\"", re.MULTILINE)


def _fleet_projects() -> list[Path]:
    if not FLEET_ROOT:
        return []
    root = Path(FLEET_ROOT)
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and (p / DOWNSTREAM_PROMPTS[0]).is_file())


@pytest.mark.skipif(not FLEET_ROOT, reason="set FLEET_ROOT to check downstream checkouts")
@pytest.mark.parametrize("rel", DOWNSTREAM_PROMPTS)
def test_downstream_prompt_tables_match_python_map(rel):
    projects = _fleet_projects()
    assert projects, f"FLEET_ROOT={FLEET_ROOT} holds no project with {rel}"

    expected = dict(gate_ancestry._BRANCH_PREFIX)
    wrong = {
        p.name: sorted(_pairs_from(p / rel).items())
        for p in projects
        if _pairs_from(p / rel) != expected
    }
    assert not wrong, (
        f"{rel} disagrees with gate_ancestry._BRANCH_PREFIX in: {wrong}\n"
        f"  python: {sorted(expected.items())}\n"
        "A type the dispatcher knows and the prompt does not means autopilot branches "
        "the work somewhere the ancestry gate never looks — a false no_merged_implementation "
        "on a run that already cost money."
    )


@pytest.mark.skipif(not FLEET_ROOT, reason="set FLEET_ROOT to check downstream checkouts")
def test_downstream_bash_case_matches_python_map():
    """The table can be right while the `case` that creates the branch falls through."""
    expected = dict(gate_ancestry._BRANCH_PREFIX)
    wrong = {}
    for project in _fleet_projects():
        text = (project / DOWNSTREAM_PROMPTS[0]).read_text(encoding="utf-8")
        found = {m.group(1): m.group(2) for m in BASH_CASE_RE.finditer(text)}
        if found != expected:
            wrong[project.name] = sorted(found.items())
    assert not wrong, f"autopilot-git.md bash `case` disagrees with the dict in: {wrong}"
