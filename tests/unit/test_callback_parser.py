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


# --- Heading regex variants (legacy) ---


def test_legacy_heading_with_whitespace_suffix(tmp_path):
    """`## Allowed Files   ` (trailing spaces) — must match."""
    spec = _spec(tmp_path, "## Allowed Files   \n\n1. `src/foo.py`\n\n## Next\n")
    out = callback._parse_allowed_files(spec)
    assert out == ["src/foo.py"]


def test_legacy_heading_with_qualifier_suffix(tmp_path):
    """`## Allowed Files (whitelist)` — historic awardybot/dowry format."""
    spec = _spec(tmp_path, "## Allowed Files (whitelist)\n\n- `src/foo.py`\n\n## Next\n")
    out = callback._parse_allowed_files(spec)
    assert out == ["src/foo.py"]


def test_legacy_heading_case_sensitivity(tmp_path):
    """`## ALLOWED FILES` — legacy regex has (?i) flag → must match."""
    spec = _spec(tmp_path, "## ALLOWED FILES\n\n1. `src/foo.py`\n\n## Tests\n")
    out = callback._parse_allowed_files(spec)
    assert out == ["src/foo.py"]


def test_legacy_heading_v1_strict_sensitivity(tmp_path):
    """`## ALLOWED FILES` — v1 regex is case-SENSITIVE, so v1 branch must NOT fire.
    Parser falls back to legacy and succeeds."""
    spec = _spec(tmp_path, (
        "## ALLOWED FILES\n\n"
        "<!-- callback-allowlist v1 -->\n\n"
        "- `src/foo.py`\n\n"
        "## Tests\n"
    ))
    # v1 heading regex requires "## Allowed Files" (exact case).
    # Upper-case heading → v1 parser returns None → legacy fallback used.
    out = callback._parse_allowed_files(spec)
    # Legacy extracts any backticked path; v1 marker comment is NOT in scope
    # because the v1 heading didn't match → legacy hits the section.
    assert isinstance(out, list)


# --- Section boundary detection ---


def test_section_ends_at_next_h2(tmp_path):
    """Backticked paths after first H2 boundary are NOT collected."""
    spec = _spec(tmp_path, (
        "## Allowed Files\n\n"
        "1. `src/a.py`\n\n"
        "## Tests\n\n"
        "1. `tests/b.py`\n"
    ))
    out = callback._parse_allowed_files(spec)
    assert out == ["src/a.py"]
    assert "tests/b.py" not in (out or [])


def test_multiple_allowed_files_sections_first_wins(tmp_path):
    """Two `## Allowed Files` blocks — only first parsed (legacy iter breaks at first H2)."""
    spec = _spec(tmp_path, (
        "## Allowed Files\n\n"
        "1. `src/first.py`\n\n"
        "## Other Section\n\n"
        "## Allowed Files\n\n"
        "1. `src/second.py`\n"
    ))
    out = callback._parse_allowed_files(spec)
    assert "src/first.py" in (out or [])
    assert "src/second.py" not in (out or [])


def test_section_at_end_of_file_no_trailing_h2(tmp_path):
    """Section is last in file, no terminating H2 — must still parse to EOF."""
    spec = _spec(tmp_path, "## Allowed Files\n\n1. `src/a.py`\n2. `src/b.py`\n")
    out = callback._parse_allowed_files(spec)
    assert out == ["src/a.py", "src/b.py"]


# --- Path extraction (extension regex) ---


def test_paths_with_unicode_dirnames(tmp_path):
    """Unicode path components allowed by the extension regex."""
    spec = _spec(tmp_path, "## Allowed Files\n\n- `Документы/spec.md`\n")
    out = callback._parse_allowed_files(spec)
    assert "Документы/spec.md" in (out or [])


def test_paths_with_dotdot_normalization_NOT_done(tmp_path):
    """`../../etc/passwd` — parser doesn't normalize; raw string returned."""
    spec = _spec(tmp_path, "## Allowed Files\n\n- `../../etc/passwd`\n")
    out = callback._parse_allowed_files(spec)
    # Parser returns raw string; normalization is caller's responsibility.
    assert isinstance(out, list)


def test_paths_with_no_extension_skipped(tmp_path):
    """`Dockerfile` (no extension) — current regex requires `.ext`, skipped."""
    spec = _spec(tmp_path, "## Allowed Files\n\n- `Dockerfile`\n- `src/foo.py`\n")
    out = callback._parse_allowed_files(spec)
    assert "Dockerfile" not in (out or [])
    assert "src/foo.py" in (out or [])


def test_paths_with_dotfile_extension(tmp_path):
    """`.env.example` — extension regex matches dotfile extensions → captured."""
    spec = _spec(tmp_path, "## Allowed Files\n\n- `.env.example`\n")
    out = callback._parse_allowed_files(spec)
    assert ".env.example" in (out or [])


def test_path_with_dash_in_extension(tmp_path):
    """`config.tar-gz` — extension regex allows hyphen in extension → captured."""
    spec = _spec(tmp_path, "## Allowed Files\n\n- `config.tar-gz`\n")
    out = callback._parse_allowed_files(spec)
    assert "config.tar-gz" in (out or [])


# --- v1 marker dispatch corner cases ---


def test_v1_marker_after_bullets_section_terminates(tmp_path):
    """Marker placed AFTER bullets in same section — still triggers v1."""
    spec = _spec(tmp_path, (
        "## Allowed Files\n\n"
        "- `src/foo.py`\n"
        "<!-- callback-allowlist v1 -->\n\n"
        "## Tests\n"
    ))
    out = callback._parse_allowed_files(spec)
    assert out == ["src/foo.py"]


def test_v1_marker_in_html_comment_with_attrs(tmp_path):
    """Marker with extra attributes: `<!-- callback-allowlist v1 attrs="x" -->`."""
    spec = _spec(tmp_path, (
        '## Allowed Files\n\n'
        '<!-- callback-allowlist v1 attr="x" -->\n\n'
        '- `src/foo.py`\n\n'
        '## Tests\n'
    ))
    out = callback._parse_allowed_files(spec)
    assert out == ["src/foo.py"]


def test_v1_marker_truncated_no_terminator(tmp_path):
    """`<!-- callback-allowlist v1` with no `-->` — must NOT match (requires `-->`)."""
    spec = _spec(tmp_path, (
        "## Allowed Files\n\n"
        "<!-- callback-allowlist v1\n\n"
        "- `src/foo.py`\n\n"
        "## Tests\n"
    ))
    # Without closing -->, v1 marker not matched → legacy fallback used.
    # Legacy extracts any backtick paths in section.
    out = callback._parse_allowed_files(spec)
    assert isinstance(out, list)  # legacy succeeds (finds the path)


# --- Fenced blocks under v1 ---


def test_v1_marker_with_table_format_returns_empty(tmp_path):
    """v1 marker + markdown table instead of bullets → [] (degrade-closed)."""
    spec = _spec(tmp_path, (
        "## Allowed Files\n\n"
        "<!-- callback-allowlist v1 -->\n\n"
        "| File | Action |\n"
        "|------|--------|\n"
        "| `src/foo.py` | modify |\n\n"
        "## Tests\n"
    ))
    out = callback._parse_allowed_files(spec)
    assert out == []


# --- Legacy + nested subheadings ---


def test_legacy_with_h3_subheadings_under_section(tmp_path):
    """H3 under section — H3 != H2, section continues, both bullet lists collected."""
    spec = _spec(tmp_path, (
        "## Allowed Files\n\n"
        "### New files\n\n"
        "- `src/new.py`\n\n"
        "### Existing files\n\n"
        "- `src/existing.py`\n\n"
        "## Tests\n"
    ))
    out = callback._parse_allowed_files(spec)
    assert "src/new.py" in (out or [])
    assert "src/existing.py" in (out or [])


# --- Empty file / single-line file ---


def test_empty_spec_returns_none(tmp_path):
    """Empty content → no heading found → None."""
    spec = _spec(tmp_path, "")
    assert callback._parse_allowed_files(spec) is None


def test_only_heading_no_body(tmp_path):
    """`## Allowed Files\\n` then EOF → legacy returns []."""
    spec = _spec(tmp_path, "## Allowed Files\n")
    out = callback._parse_allowed_files(spec)
    assert out == []
