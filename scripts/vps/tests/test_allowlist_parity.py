# scripts/vps/tests/test_allowlist_parity.py
"""Parity between the Spark pre-flight linter and the production parser.

Spark checks a freshly written spec's `## Allowed Files` before handing it to
autopilot. That check used to be four regexes written out in prose inside
`skills/spark/feature-mode.md`, applied by the model itself — and it drifted:
`callback.py` gained numbered-list support (TECH-208) and the prompt did not.
Since a linter failure there *deletes the spec file*, the drift turned valid
specs into deleted ones.

The check is now `.claude/scripts/validate-allowlist.mjs`. This test is the
thing that keeps it honest: the linter and the parser must extract the *same
paths* from the same spec, forever. If someone edits one regex, this fails.

Verdict is deliberately NOT compared. The linter is stricter than the parser on
purpose — the parser tolerates silently (a duplicate heading whose second list
is ignored, a spec with no v1 marker falling back to a prose-scraping legacy
reader), and tolerating silently is fine at runtime but wrong at authoring time.
Those asymmetries are asserted explicitly below rather than left implied.

ADR-013: no mocks. Real files, real `node` subprocess, real parser import.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

from gate_logic import (  # noqa: E402
    _parse_allowed_files_v1,
    parse_allowed_files,
    strip_bookkeeping_paths,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
LINTER = REPO_ROOT / ".claude" / "scripts" / "validate-allowlist.mjs"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not on PATH; linter is a Node script"
)


def run_linter(spec_path: Path) -> dict:
    """Run the linter and return its JSON. It always prints one object."""
    proc = subprocess.run(
        ["node", str(LINTER), str(spec_path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.stdout.strip(), f"linter printed nothing (stderr: {proc.stderr})"
    payload = json.loads(proc.stdout)
    payload["_exit"] = proc.returncode
    return payload


def write_spec(tmp_path: Path, body: str, name: str = "SPEC-001-test.md") -> Path:
    spec = tmp_path / name
    spec.write_text(body, encoding="utf-8")
    return spec


MARKER = "<!-- callback-allowlist v1 -->"


def v1_spec(section_body: str) -> str:
    return f"""# Feature: [TECH-001] Parity fixture

## Scope

Whatever.

## Allowed Files

{MARKER}

{section_body}

## Definition of Done

- [ ] done
"""


# --- The cases -------------------------------------------------------------
# Each is a v1 section body. Parity is asserted on every one of them.
V1_CASES = {
    "dash_bullets": """- `src/domains/billing/service.py` — add method (modify)
- `tests/test_billing.py` — cover it (NEW)""",
    # The exact shape that the drifted prompt rejected and the parser accepts.
    "numbered_list": """1. `src/domains/billing/service.py` — add method (modify)
2. `tests/test_billing.py` — cover it (NEW)""",
    "mixed_dash_and_numbered": """- `src/a.py` — one
2. `src/b.py` — two""",
    "no_trailing_prose": """- `src/a.py`
- `src/b.py`""",
    "tabs_instead_of_spaces": "-\t`src/a.py`\t— tab separated",
    "dotted_and_hyphenated_extensions": """- `.env.example` — sample env
- `web/app.module.ts` — angular module
- `infra/main.tf` — terraform""",
    "path_with_dashes_in_name": "- `src/my-module/sub-file.py` — dashes",
    "prose_between_entries": """- `src/a.py` — first

Some explanation naming `callback.py` in passing.

- `src/b.py` — second""",
    "reason_mentions_other_file": "- `src/a.py` — mirrors `src/b.py` logic (modify)",
    "section_ends_at_next_h2": """- `src/a.py` — real entry""",
    "bookkeeping_mixed_in": """- `src/a.py` — implementation
- `ai/backlog.md` — bookkeeping
- `ai/lifecycle/TECH-001.yaml` — bookkeeping""",
    "empty_with_marker": "",
}


@pytest.mark.parametrize("case_name", sorted(V1_CASES))
def test_linter_extracts_same_paths_as_parser(tmp_path, case_name):
    """The whole point: same spec in, same path list out."""
    spec = write_spec(tmp_path, v1_spec(V1_CASES[case_name]))

    parser_paths = parse_allowed_files(spec)
    linter_paths = run_linter(spec)["paths"]

    assert parser_paths is not None, "fixture must be v1-parseable"
    assert linter_paths == parser_paths, (
        f"{case_name}: linter and callback.py disagree.\n"
        f"  parser: {parser_paths}\n"
        f"  linter: {linter_paths}"
    )


def test_numbered_list_is_accepted(tmp_path):
    """TECH-208 regression, stated on its own because it is the drift that bit.

    The prompt-era linter emitted ALLOWLIST_E004 here and deleted the spec.
    """
    spec = write_spec(tmp_path, v1_spec(V1_CASES["numbered_list"]))
    result = run_linter(spec)

    assert result["_exit"] == 0, f"numbered list must pass, got {result['errors']}"
    assert result["paths"] == ["src/domains/billing/service.py", "tests/test_billing.py"]


def test_section_stops_at_next_h2_in_both(tmp_path):
    """A path below the section boundary belongs to neither list."""
    body = v1_spec("- `src/inside.py` — counted") + "\n- `src/outside.py` — must not count\n"
    spec = write_spec(tmp_path, body)

    parser_paths = parse_allowed_files(spec)
    linter = run_linter(spec)

    assert "src/outside.py" not in parser_paths
    assert "src/outside.py" not in linter["paths"]
    assert linter["paths"] == parser_paths


def test_bookkeeping_split_matches_strip_helper(tmp_path):
    """`implementation_paths` must equal what the guard actually keeps."""
    spec = write_spec(tmp_path, v1_spec(V1_CASES["bookkeeping_mixed_in"]))

    parser_paths = parse_allowed_files(spec)
    expected_impl = strip_bookkeeping_paths(parser_paths)
    linter = run_linter(spec)

    assert linter["implementation_paths"] == expected_impl


def test_bookkeeping_only_allowlist_is_rejected(tmp_path):
    """The failure the prompt-era linter had no rule for.

    Every path is bookkeeping, so `strip_bookkeeping_paths` empties the list and
    the implementation guard can never find a commit proving the spec was done.
    The parser is content — it is not the parser's job — so the linter must not be.
    """
    spec = write_spec(
        tmp_path,
        v1_spec("- `ai/backlog.md` — row\n- `ai/lifecycle/TECH-001.yaml` — status"),
    )
    result = run_linter(spec)

    assert result["_exit"] == 1
    assert strip_bookkeeping_paths(parse_allowed_files(spec)) == []
    assert any(e["code"] == "ALLOWLIST_E007_BOOKKEEPING_ONLY" for e in result["errors"])


# --- Asymmetries, asserted rather than assumed ------------------------------


def test_table_rows_are_invisible_to_the_parser_and_blocked_by_the_linter(tmp_path):
    """A stale docs template taught the table shape; the parser sees nothing.

    Parity holds (both extract zero paths). The linter additionally refuses,
    because a spec whose allowlist silently parses to empty is a spec autopilot
    cannot write a single file for.
    """
    spec = write_spec(
        tmp_path,
        v1_spec(
            "| # | File | Reason |\n"
            "|---|------|--------|\n"
            "| 1 | `src/a.py` | modify |\n"
            "| 2 | `src/b.py` | modify |"
        ),
    )

    assert _parse_allowed_files_v1(spec.read_text(encoding="utf-8")) == []
    result = run_linter(spec)

    assert result["paths"] == []
    assert result["_exit"] == 1
    assert any(e["code"] == "ALLOWLIST_E004_UNPARSED_PATH" for e in result["errors"])


def test_missing_marker_defers_in_parser_but_blocks_in_linter(tmp_path):
    """No marker → parser falls back to legacy prose-scraping; a new spec must not.

    The legacy reader exists for specs written before the v1 format. Letting a
    freshly authored spec through on it means paths named in prose become
    writable, which is how the allowlist stops being a boundary.
    """
    spec = write_spec(
        tmp_path,
        """# Feature: [TECH-002] No marker

## Allowed Files

- `src/a.py` — entry

## Definition of Done
""",
    )

    assert _parse_allowed_files_v1(spec.read_text(encoding="utf-8")) is None
    result = run_linter(spec)

    assert result["_exit"] == 1
    assert any(e["code"] == "ALLOWLIST_E003_NO_MARKER" for e in result["errors"])


def test_duplicate_heading_parser_takes_first_linter_refuses(tmp_path):
    """Second list is dead text that reads as live. Parity on paths, not verdict."""
    body = (
        v1_spec("- `src/first.py` — counted")
        + f"""
## Allowed Files

{MARKER}

- `src/second.py` — silently ignored by the parser

## End
"""
    )
    spec = write_spec(tmp_path, body)

    parser_paths = parse_allowed_files(spec)
    result = run_linter(spec)

    assert parser_paths == ["src/first.py"]
    assert result["paths"] == parser_paths
    assert result["_exit"] == 1
    assert any(e["code"] == "ALLOWLIST_E002_DUPLICATE_HEADING" for e in result["errors"])


def test_reason_prose_naming_a_file_is_a_warning_not_an_error(tmp_path):
    """Regression on the linter's own first draft.

    It flagged every backticked name in a reason field as a lost path, which
    made real specs fail on sentences like "imports `gate_logic.parse_allowed_files`".
    Prose names references; only entry-shaped lines can lose an entry.
    """
    spec = write_spec(tmp_path, v1_spec(V1_CASES["reason_mentions_other_file"]))
    result = run_linter(spec)

    assert result["_exit"] == 0
    assert result["paths"] == ["src/a.py"]
    assert any(w["code"] == "ALLOWLIST_W002_EXTRA_PATH_IN_REASON" for w in result["warnings"])


def test_no_heading_at_all_is_usage_level_failure(tmp_path):
    spec = write_spec(tmp_path, "# Feature: [TECH-003] Nothing here\n\n## Scope\n\nnope\n")
    result = run_linter(spec)

    assert result["_exit"] == 1
    assert result["error_code"] == "ALLOWLIST_E001_NO_HEADING"
    assert parse_allowed_files(spec) is None


def test_unreadable_file_exits_two(tmp_path):
    result = run_linter(tmp_path / "does-not-exist.md")
    assert result["_exit"] == 2
    assert result["error_code"] == "ALLOWLIST_E000_UNREADABLE"


# --- Parity against the real corpus ----------------------------------------


def test_parity_on_every_real_v1_spec():
    """The fixtures above are what I thought of. This is what actually shipped."""
    features = REPO_ROOT / "ai" / "features"
    if not features.is_dir():
        pytest.skip("no ai/features/ in this checkout")

    checked = 0
    for spec in sorted(features.glob("*.md")):
        text = spec.read_text(encoding="utf-8", errors="replace")
        if _parse_allowed_files_v1(text) is None:
            continue  # legacy spec: linter implements no legacy reader by design
        checked += 1
        assert run_linter(spec)["paths"] == parse_allowed_files(spec), (
            f"parity broken on real spec {spec.name}"
        )

    assert checked > 0, "no v1 specs found — parity claim would be vacuous"
