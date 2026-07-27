"""Regression tests for console_safe (2026-07-27).

`spec_operator.py force-done <project> <ID> '<reason>'` wrote the lifecycle YAML,
then raised UnicodeEncodeError printing its own success line, and exited 1. The
mutation had already landed; only the report failed. A wrapper reading the exit
code would conclude the operator action did not happen.

Root cause: on Windows `sys.stdout` defaults to the ANSI code page (cp1251 on this
machine). The status arrow `→` and any Cyrillic in the operator-supplied reason are
unencodable there, and the default codec policy is `strict`.

These tests drive a real cp1251 stream rather than mocking the encoder — mocking
would assert that our mock does not raise, which is not the property under test.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import console_safe  # noqa: E402

# The exact payload that broke the tool: an arrow plus a Cyrillic reason.
BREAKING_TEXT = "operator: BUG-460 → done (reason=superseded by BUG-464 — та же работа)"


def _cp1251_stream() -> io.TextIOWrapper:
    """A strict cp1251 text stream — what a Windows console actually hands Python."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1251", errors="strict")


class TestTheBugItself:
    def test_strict_cp1251_stream_raises_without_the_fix(self):
        """Characterization: prove the failure mode is real before asserting the fix."""
        stream = _cp1251_stream()
        with pytest.raises(UnicodeEncodeError):
            stream.write(BREAKING_TEXT)
            stream.flush()

    def test_enable_makes_the_same_write_survive(self, monkeypatch):
        stream = _cp1251_stream()
        monkeypatch.setattr(sys, "stdout", stream)
        console_safe.enable()
        # Must not raise — that is the whole contract.
        print(BREAKING_TEXT)
        sys.stdout.flush()

    def test_output_still_carries_the_ascii_payload(self, monkeypatch):
        """Degrading is fine; losing the spec id and status is not."""
        stream = _cp1251_stream()
        monkeypatch.setattr(sys, "stdout", stream)
        console_safe.enable()
        print(BREAKING_TEXT)
        sys.stdout.flush()
        written = stream.buffer.getvalue().decode("utf-8", errors="replace")
        assert "BUG-460" in written
        assert "done" in written


class TestEnableIsSafe:
    def test_idempotent(self, monkeypatch):
        monkeypatch.setattr(sys, "stdout", _cp1251_stream())
        console_safe.enable()
        console_safe.enable()
        print("twice is fine — →")

    def test_stream_without_reconfigure_is_skipped(self, monkeypatch):
        """pytest capture and detached streams must not turn into a crash."""

        class NoReconfigure:
            def write(self, _s):
                return 0

            def flush(self):
                pass

        monkeypatch.setattr(sys, "stdout", NoReconfigure())
        console_safe.enable()  # must not raise

    def test_stderr_is_protected_too(self, monkeypatch):
        stream = _cp1251_stream()
        monkeypatch.setattr(sys, "stderr", stream)
        console_safe.enable()
        print(BREAKING_TEXT, file=sys.stderr)
        sys.stderr.flush()

    def test_never_raises_on_closed_stream(self, monkeypatch):
        stream = _cp1251_stream()
        stream.close()
        monkeypatch.setattr(sys, "stdout", stream)
        console_safe.enable()  # must not raise


class TestEveryOperatorCliCallsIt:
    """A CLI that prints repo text and forgets `enable()` reintroduces the bug.

    Checked structurally rather than by invoking each tool: the failure is a missing
    call, and a missing call is exactly what source inspection catches cheaply.
    """

    CLIS = [
        "spec_operator.py",
        "recover_false_reconciliation.py",
        "recover_bootstrap_as_done.py",
        "lifecycle_audit.py",
        "migrate_backlog_to_lifecycle.py",
        "spec_verify.py",
        "audit_digest.py",
        "openclaw-artifact-scan.py",
    ]

    @pytest.mark.parametrize("name", CLIS)
    def test_cli_enables_console_safe(self, name):
        source = (SCRIPT_DIR / name).read_text(encoding="utf-8")
        assert "import console_safe" in source, f"{name} does not import console_safe"
        assert "console_safe.enable()" in source, f"{name} never calls console_safe.enable()"

    def test_console_safe_stays_a_leaf(self):
        """Called first thing in main() — it must not drag in half the tree."""
        source = (SCRIPT_DIR / "console_safe.py").read_text(encoding="utf-8")
        for forbidden in ("import lifecycle", "import db", "import callback", "import gate_logic"):
            assert forbidden not in source, f"console_safe must not {forbidden}"
