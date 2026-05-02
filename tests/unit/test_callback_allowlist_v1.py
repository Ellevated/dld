"""TECH-167 — unit tests for callback.py v1 canonical Allowed Files parser.

Covers EC-1 (canonical), EC-2 (legacy fallback), EC-3 (degrade-closed),
EC-7 (regression on heading variants from awardybot/dowry/gipotenuza/etc).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402


def _spec(tmp_path: Path, body: str, name: str = "TECH-XXX.md") -> Path:
    p = tmp_path / name
    p.write_text(body)
    return p


# --- EC-1: canonical v1 marker → strict parse --------------------------------


def test_ec1_v1_canonical_basic(tmp_path):
    spec = _spec(tmp_path, """\
# TECH-XXX

## Allowed Files

<!-- callback-allowlist v1 -->

- `scripts/vps/callback.py`
- `tests/unit/test_x.py`
- `db/schema.sql` — schema bump

## Tests
""")
    assert callback._parse_allowed_files(spec) == [
        "scripts/vps/callback.py",
        "tests/unit/test_x.py",
        "db/schema.sql",
    ]


def test_ec1_v1_marker_with_inline_comment(tmp_path):
    spec = _spec(tmp_path, """\
## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row -->

- `a.py`
- `b/c.py`

## Next
""")
    assert callback._parse_allowed_files(spec) == ["a.py", "b/c.py"]


def test_ec1_v1_extra_prose_after_marker_is_ignored(tmp_path):
    spec = _spec(tmp_path, """\
## Allowed Files

<!-- callback-allowlist v1 -->

This intro line is fine.

- `x.py`

## End
""")
    assert callback._parse_allowed_files(spec) == ["x.py"]


# --- EC-3: marker present, malformed bullets → degrade-closed ----------------


def test_ec3_v1_marker_no_bullets_returns_empty(tmp_path):
    """v1 marker but zero canonical bullets → [] (caller blocks done)."""
    spec = _spec(tmp_path, """\
## Allowed Files

<!-- callback-allowlist v1 -->

(no files specified yet)

## Next
""")
    assert callback._parse_allowed_files(spec) == []


def test_ec3_v1_marker_paths_in_fence_ignored(tmp_path):
    """Paths inside a fenced code block are NOT bullets → ignored under v1."""
    spec = _spec(tmp_path, """\
## Allowed Files

<!-- callback-allowlist v1 -->

```
src/foo.py
src/bar.py
```

## Next
""")
    assert callback._parse_allowed_files(spec) == []


def test_ec3_v1_marker_numbered_list_ignored(tmp_path):
    """v1 strictly requires `- ` bullets; numbered list does not match."""
    spec = _spec(tmp_path, """\
## Allowed Files

<!-- callback-allowlist v1 -->

1. `foo.py`
2. `bar.py`

## Next
""")
    assert callback._parse_allowed_files(spec) == []


# --- EC-2: legacy spec without marker → fallback parser ----------------------


def test_ec2_legacy_no_marker_uses_old_parser(tmp_path):
    """No v1 marker → fall back to TECH-166 heading-variant parser."""
    spec = _spec(tmp_path, """\
## Allowed Files

1. `scripts/vps/callback.py` — modify
2. `tests/unit/test_x.py` — NEW

## Tests
""")
    assert callback._parse_allowed_files(spec) == [
        "scripts/vps/callback.py",
        "tests/unit/test_x.py",
    ]


def test_ec2_legacy_section_absent_returns_none(tmp_path):
    spec = _spec(tmp_path, "# Spec\n\n## Tests\n\n- foo\n")
    assert callback._parse_allowed_files(spec) is None


# --- EC-7: regression — real-world heading variants still work ---------------


@pytest.mark.parametrize("heading", [
    "## Allowed Files (whitelist)",
    "## Allowed Files (canonical)",
    "## Allowed Files (STRICT)",
    "## Updated Allowed Files",
    "## Files Allowed to Modify",
])
def test_ec7_legacy_heading_variants_regression(tmp_path, heading):
    """awardybot/dowry/gipotenuza heading variants must still parse via legacy."""
    body = (
        f"{heading}\n\n"
        "1. `src/a.py`\n"
        "2. `src/b.py`\n\n"
        "## Tests\n"
    )
    spec = _spec(tmp_path, body)
    assert callback._parse_allowed_files(spec) == ["src/a.py", "src/b.py"]


# --- v1 marker takes precedence over legacy parser ---------------------------


def test_v1_marker_wins_over_legacy_heading(tmp_path):
    """If a spec uses a legacy-style heading suffix BUT also includes the v1
    marker, callback should treat it as v1 strict (no legacy fallback)."""
    spec = _spec(tmp_path, """\
## Allowed Files

<!-- callback-allowlist v1 -->

- `only/this.py`

## Tests

(legacy parser would also have caught `decoy.py` here outside section)
""")
    assert callback._parse_allowed_files(spec) == ["only/this.py"]


# --- v1 marker outside the section: should NOT trigger v1 mode ---------------


def test_v1_marker_outside_section_ignored(tmp_path):
    """Marker must appear INSIDE the ## Allowed Files section to count."""
    spec = _spec(tmp_path, """\
<!-- callback-allowlist v1 -->

## Allowed Files

1. `legacy.py`

## Tests
""")
    # Marker is above the heading → v1 dispatch does not fire → legacy parser
    # picks `legacy.py`.
    assert callback._parse_allowed_files(spec) == ["legacy.py"]


# --- _append_blocked_reason backwards-compat alias (TECH-167 Task 4) ---------


def test_append_blocked_reason_alias_exists():
    """Test 4's alias is callable and accepts (Path, str)."""
    assert callable(getattr(callback, "_append_blocked_reason", None))
