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
    """Yield (spec_path, expected_dict) tuples for every .md with .expected.json sibling.

    README.md and similar documentation files (no sidecar) are skipped.
    """
    for spec in sorted(CORPUS_DIR.glob("*.md")):
        if spec.name.upper().startswith("README"):
            continue
        sidecar = spec.with_suffix(".expected.json")
        if not sidecar.is_file():
            pytest.fail(f"Missing sidecar: {sidecar}")
        yield pytest.param(spec, json.loads(sidecar.read_text()), id=spec.stem)


@pytest.mark.parametrize("spec_path,expected", list(_corpus_specs()))
def test_corpus_parse_matches_expected(spec_path, expected):
    """Parser output for each fixture matches its hand-verified .expected.json."""
    actual = callback._parse_allowed_files(spec_path)
    if expected["expected_return_type"] == "None":
        assert actual is None, (
            f"{spec_path.name}: expected None, got {actual!r}"
        )
    else:
        assert actual == expected["expected_paths"], (
            f"{spec_path.name}: parser drift\n"
            f"  expected: {expected['expected_paths']}\n"
            f"  actual:   {actual}"
        )


def test_corpus_has_at_least_25_specs():
    """Coverage gate: <25 means a project slot is missing."""
    md_files = [
        p for p in CORPUS_DIR.glob("*.md")
        if not p.name.upper().startswith("README")
    ]
    assert len(md_files) >= 25, f"Corpus has only {len(md_files)} specs (need >= 25)"


def test_corpus_all_5_projects_represented():
    """Each of the 5 orchestrator projects must have at least one fixture."""
    prefixes = {
        p.name.split("_")[0]
        for p in CORPUS_DIR.glob("*.md")
        if not p.name.upper().startswith("README")
    }
    required = {"awardybot", "dowry", "gipotenuza", "plpilot", "wb"}
    missing = required - prefixes
    assert not missing, (
        f"Missing projects: {missing} (have: {prefixes})"
    )


def test_corpus_all_shapes_represented():
    """All 5 parser-shape categories must appear at least once across the corpus."""
    shapes = set()
    for sidecar in CORPUS_DIR.glob("*.expected.json"):
        shapes.add(json.loads(sidecar.read_text()).get("shape", ""))
    expected_shapes = {
        "canonical",
        "heading-variant",
        "fenced-block",
        "no-section",
        "multi-section",
    }
    missing = expected_shapes - shapes
    assert not missing, f"Missing shapes: {missing} (have: {shapes})"
