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
