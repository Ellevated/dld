"""TECH-175 — unit tests for spec_lint.py and callback marker-aware parser.

Covers EC-1..EC-4 per spec and the callback._parse_allowed_files_marker layer
added in Task 2.  Pattern mirrors test_callback_allowlist_v1.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "vps"))

import callback   # noqa: E402
import spec_lint  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WELL_FORMED = """\
# TECH-XXX
<!-- DLD-CALLBACK-MARKER-START v1 -->
## Allowed Files

<!-- callback-allowlist v1 -->

- `a.py`
- `b/c.py`

<!-- DLD-CALLBACK-MARKER-END -->
"""


def _spec(tmp_path: Path, body: str, name: str = "SPEC-XXX.md") -> Path:
    p = tmp_path / name
    p.write_text(body)
    return p


# ---------------------------------------------------------------------------
# Test 1: EC-1 — well-formed spec with v1 markers, lint returns no errors
# ---------------------------------------------------------------------------

def test_ec1_correct_markers_v1():
    """Well-formed Allowed Files block inside marker pair → lint_spec() == []."""
    assert spec_lint.lint_spec(_WELL_FORMED) == []


# ---------------------------------------------------------------------------
# Test 2: EC-1 — callback marker parser extracts paths from marker block
# ---------------------------------------------------------------------------

def test_ec1_callback_marker_parser_returns_paths():
    """callback._parse_allowed_files_marker() extracts paths from a v1 block."""
    result = callback._parse_allowed_files_marker(_WELL_FORMED)
    assert result == ["a.py", "b/c.py"]


# ---------------------------------------------------------------------------
# Test 3: EC-2 — legacy spec without markers produces LINT_E001_NO_MARKERS
# ---------------------------------------------------------------------------

def test_ec2_legacy_no_markers_lint_warns():
    """Spec without any DLD-CALLBACK-MARKER → LINT_E001_NO_MARKERS reported."""
    text = """\
# TECH-XXX

## Allowed Files

<!-- callback-allowlist v1 -->

- `foo.py`

## Tests
"""
    codes = [e.code for e in spec_lint.lint_spec(text)]
    assert "LINT_E001_NO_MARKERS" in codes


# ---------------------------------------------------------------------------
# Test 4: EC-2 — legacy spec falls back to TECH-167 v1 parser in callback
# ---------------------------------------------------------------------------

def test_ec2_legacy_callback_falls_back_to_v1(tmp_path):
    """No DLD markers → callback._parse_allowed_files() falls through to v1."""
    spec = _spec(tmp_path, """\
## Allowed Files

<!-- callback-allowlist v1 -->

- `scripts/vps/callback.py`
- `tests/unit/test_x.py`

## Tests
""")
    result = callback._parse_allowed_files(spec)
    assert result == ["scripts/vps/callback.py", "tests/unit/test_x.py"]


# ---------------------------------------------------------------------------
# Test 5: EC-3 — unmatched START → LINT_E002 + callback returns [] (degrade-closed)
# ---------------------------------------------------------------------------

def test_ec3_unmatched_start():
    """START without END → LINT_E002_UNMATCHED_START in lint; callback degrades."""
    text = "<!-- DLD-CALLBACK-MARKER-START v1 -->\n## Allowed Files\n- `a.py`\n"
    codes = [e.code for e in spec_lint.lint_spec(text)]
    assert "LINT_E002_UNMATCHED_START" in codes
    assert callback._parse_allowed_files_marker(text) == []


# ---------------------------------------------------------------------------
# Test 6: EC-3 — orphan END → LINT_E003_UNMATCHED_END
# ---------------------------------------------------------------------------

def test_ec3_unmatched_end():
    """END before any START → LINT_E003_UNMATCHED_END."""
    text = "# Spec\n<!-- DLD-CALLBACK-MARKER-END -->\n\n## Allowed Files\n"
    codes = [e.code for e in spec_lint.lint_spec(text)]
    assert "LINT_E003_UNMATCHED_END" in codes


# ---------------------------------------------------------------------------
# Test 7: EC-4 — unknown version in lint → LINT_E005_UNKNOWN_VERSION
# ---------------------------------------------------------------------------

def test_ec4_unknown_version_lint():
    """v9 block → LINT_E005_UNKNOWN_VERSION reported by spec_lint."""
    text = """\
<!-- DLD-CALLBACK-MARKER-START v9 -->
## Allowed Files

<!-- callback-allowlist v1 -->

- `a.py`
<!-- DLD-CALLBACK-MARKER-END -->
"""
    codes = [e.code for e in spec_lint.lint_spec(text)]
    assert "LINT_E005_UNKNOWN_VERSION" in codes


# ---------------------------------------------------------------------------
# Test 8: EC-4 — unknown version in callback → degrade-closed []
# ---------------------------------------------------------------------------

def test_ec4_unknown_version_callback_degrades_closed(tmp_path):
    """Unknown marker version v9 → callback returns [] (degrade-closed)."""
    spec = _spec(tmp_path, """\
<!-- DLD-CALLBACK-MARKER-START v9 -->
## Allowed Files

<!-- callback-allowlist v1 -->

- `a.py`
<!-- DLD-CALLBACK-MARKER-END -->
""")
    assert callback._parse_allowed_files(spec) == []


# ---------------------------------------------------------------------------
# Test 9: EC-3 — ## Allowed Files outside any marker block → LINT_E006
# ---------------------------------------------------------------------------

def test_allowed_files_outside_block_e006():
    """## Allowed Files heading present but not enclosed → LINT_E006."""
    text = """\
# Spec

## Allowed Files

<!-- callback-allowlist v1 -->

- `foo.py`
"""
    codes = [e.code for e in spec_lint.lint_spec(text)]
    assert "LINT_E006_ALLOWED_FILES_OUTSIDE_BLOCK" in codes


# ---------------------------------------------------------------------------
# Test 10: EC-1 — Allowed Files block without inner TECH-167 marker → LINT_E008
# ---------------------------------------------------------------------------

def test_inner_tech167_marker_required_e008():
    """Marker block has ## Allowed Files but no inner callback-allowlist v1 → E008."""
    text = """\
<!-- DLD-CALLBACK-MARKER-START v1 -->
## Allowed Files

- `a.py`
- `b.py`

<!-- DLD-CALLBACK-MARKER-END -->
"""
    codes = [e.code for e in spec_lint.lint_spec(text)]
    assert "LINT_E008_INNER_TECH167_MISSING" in codes
