"""Regression tests for CLI resolution in claude-runner (2026-07-26).

`_resolve_cli_path` used to return the first `claude` it found, ordered by PATH.
On the VPS that was a root-owned 2.1.72 binary frozen since March, because pueue
inherits systemd's PATH (`/usr/local/sbin:/usr/local/bin:…`) which has no
`~/.local/bin` — where the installer's self-updating launcher actually lives.

2.1.72 predates Opus 5. Handed `model="claude-opus-5"` it did not error; it ran
claude-opus-4-6 instead. That model has a 200K window rather than 1M, so
autocompact fired every ~155K tokens: 34 compactions in a single 90-minute run,
19.6M cache-read tokens, and a timeout with nothing merged. The pin from commit
77abc39 had never taken effect.

Resolution is now by version, which self-heals regardless of PATH order.

Fake CLIs are real executables printing real version strings — the function
shells out, so mocking subprocess would test nothing (ADR-013).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import runner_cli


@pytest.fixture()
def cli(monkeypatch):
    """Return runner_cli with `_SYSTEM_CLI_FALLBACK` pointed somewhere hermetic."""

    def _point_at(system_fallback: str):
        monkeypatch.setattr(runner_cli, "_SYSTEM_CLI_FALLBACK", system_fallback)
        return runner_cli

    return _point_at


def _fake_cli(directory: Path, version_text: str | None) -> Path:
    """An executable that prints `version_text`, or exits 1 if None."""
    directory.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        path = directory / "claude.cmd"
        body = "@echo off\r\n" + (f"echo {version_text}\r\n" if version_text else "exit /b 1\r\n")
        path.write_text(body, encoding="ascii")
    else:
        path = directory / "claude"
        body = "#!/bin/sh\n" + (f"echo '{version_text}'\n" if version_text else "exit 1\n")
        path.write_text(body, encoding="ascii")
        path.chmod(0o755)
    return path


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Isolate HOME, PATH lookup and the system fallback from the real host."""
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv("CLAUDE_CLI_PATH", raising=False)
    return {"tmp": tmp_path, "home": home, "nowhere": str(tmp_path / "nowhere" / "claude")}


# ---------------------------------------------------------------------------
# The production regression
# ---------------------------------------------------------------------------


def test_newest_wins_over_path_order(env, monkeypatch, cli):
    """The exact VPS shape: stale binary first on PATH, current one elsewhere."""
    stale = _fake_cli(env["tmp"] / "usr-local-bin", "2.1.72 (Claude Code)")
    fresh = _fake_cli(env["tmp"] / "installer", "2.1.220 (Claude Code)")
    monkeypatch.setattr(shutil, "which", lambda _n: str(stale))

    ns = cli(str(fresh))
    path, version = ns._resolve_cli_path()

    assert Path(path).resolve() == fresh.resolve(), "PATH order beat version again"
    assert version == (2, 1, 220)
    assert version >= ns._MIN_CLI_VERSION


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows cannot execute an extensionless file, and the daemon is Linux-only",
)
def test_home_local_bin_slot_is_probed(env, monkeypatch, cli):
    """~/.local/bin/claude is the slot that was being skipped — prove it is read."""
    stale = _fake_cli(env["tmp"] / "usr-local-bin", "2.1.72 (Claude Code)")
    fresh = _fake_cli(env["home"] / ".local" / "bin", "2.1.220 (Claude Code)")
    monkeypatch.setattr(shutil, "which", lambda _n: str(stale))

    ns = cli(str(stale))
    path, version = ns._resolve_cli_path()

    assert Path(path).resolve() == fresh.resolve()
    assert version == (2, 1, 220)


def test_stale_only_still_returns_but_below_floor(env, monkeypatch, cli):
    """One stale install and nothing else: use it, but it must read as too old."""
    stale = _fake_cli(env["tmp"] / "usr-local-bin", "2.1.72 (Claude Code)")
    monkeypatch.setattr(shutil, "which", lambda _n: str(stale))

    ns = cli(env["nowhere"])
    path, version = ns._resolve_cli_path()

    assert Path(path).resolve() == stale.resolve()
    assert version == (2, 1, 72)
    assert version < ns._MIN_CLI_VERSION, "2.1.72 must trip the too-old warning"


def test_path_wins_when_it_is_the_newest(env, monkeypatch, cli):
    """Ordering is by version, not by preferring one location — check both directions."""
    fresh = _fake_cli(env["tmp"] / "usr-local-bin", "2.1.220 (Claude Code)")
    older = _fake_cli(env["tmp"] / "installer", "2.1.100 (Claude Code)")
    monkeypatch.setattr(shutil, "which", lambda _n: str(fresh))

    ns = cli(str(older))
    path, version = ns._resolve_cli_path()

    assert Path(path).resolve() == fresh.resolve()
    assert version == (2, 1, 220)


def test_minor_and_major_compare_numerically(env, monkeypatch, cli):
    """2.1.99 vs 2.1.220: string compare would pick the wrong one."""
    older = _fake_cli(env["tmp"] / "usr-local-bin", "2.1.99 (Claude Code)")
    fresh = _fake_cli(env["tmp"] / "installer", "2.1.220 (Claude Code)")
    monkeypatch.setattr(shutil, "which", lambda _n: str(older))

    ns = cli(str(fresh))
    path, version = ns._resolve_cli_path()

    assert Path(path).resolve() == fresh.resolve()
    assert version == (2, 1, 220)


# ---------------------------------------------------------------------------
# Override and degradation
# ---------------------------------------------------------------------------


def test_explicit_pin_overrides_everything(env, monkeypatch, cli):
    """CLAUDE_CLI_PATH is the operator's escape hatch — never second-guessed."""
    pinned = _fake_cli(env["tmp"] / "pinned", "2.1.150 (Claude Code)")
    newer = _fake_cli(env["tmp"] / "installer", "2.1.220 (Claude Code)")
    monkeypatch.setattr(shutil, "which", lambda _n: None)
    monkeypatch.setenv("CLAUDE_CLI_PATH", str(pinned))

    ns = cli(str(newer))
    path, version = ns._resolve_cli_path()

    assert path == str(pinned)
    assert version == (2, 1, 150)


def test_pin_to_missing_file_falls_through(env, monkeypatch, cli):
    """A stale CLAUDE_CLI_PATH must not blank out resolution entirely."""
    fresh = _fake_cli(env["tmp"] / "installer", "2.1.220 (Claude Code)")
    monkeypatch.setattr(shutil, "which", lambda _n: None)
    monkeypatch.setenv("CLAUDE_CLI_PATH", str(env["tmp"] / "deleted" / "claude"))

    ns = cli(str(fresh))
    path, version = ns._resolve_cli_path()

    assert Path(path).resolve() == fresh.resolve()
    assert version == (2, 1, 220)


def test_unversioned_candidate_is_last_resort(env, monkeypatch, cli):
    """A binary that won't report a version loses to one that will."""
    mute = _fake_cli(env["tmp"] / "mute", None)
    fresh = _fake_cli(env["tmp"] / "installer", "2.1.220 (Claude Code)")
    monkeypatch.setattr(shutil, "which", lambda _n: str(mute))

    ns = cli(str(fresh))
    path, version = ns._resolve_cli_path()

    assert Path(path).resolve() == fresh.resolve()
    assert version == (2, 1, 220)


def test_unversioned_candidate_used_when_alone(env, monkeypatch, cli):
    """Better to hand the SDK a working binary than nothing at all."""
    mute = _fake_cli(env["tmp"] / "mute", None)
    monkeypatch.setattr(shutil, "which", lambda _n: str(mute))

    ns = cli(env["nowhere"])
    path, version = ns._resolve_cli_path()

    assert Path(path).resolve() == mute.resolve()
    assert version is None


def test_no_cli_anywhere_returns_none(env, monkeypatch, cli):
    """(None, None) lets the SDK fall back to its bundled CLI instead of crashing."""
    monkeypatch.setattr(shutil, "which", lambda _n: None)

    ns = cli(env["nowhere"])
    assert ns._resolve_cli_path() == (None, None)


def test_same_binary_reached_twice_is_probed_once(env, monkeypatch, cli):
    """PATH and the fallback often point at one file — don't shell out twice."""
    only = _fake_cli(env["tmp"] / "usr-local-bin", "2.1.220 (Claude Code)")
    monkeypatch.setattr(shutil, "which", lambda _n: str(only))

    ns = cli(str(only))
    calls: list[str] = []
    real = ns._cli_version
    monkeypatch.setattr(ns, "_cli_version", lambda p: (calls.append(p), real(p))[1])

    path, version = ns._resolve_cli_path()

    assert Path(path).resolve() == only.resolve()
    assert version == (2, 1, 220)
    assert len(calls) == 1, f"probed the same binary {len(calls)} times: {calls}"


# ---------------------------------------------------------------------------
# Version parsing
# ---------------------------------------------------------------------------


def test_parses_real_version_banner(env, cli):
    """`claude --version` prints '2.1.220 (Claude Code)'."""
    cli_path = _fake_cli(env["tmp"] / "bin", "2.1.220 (Claude Code)")
    ns = cli(env["nowhere"])
    assert ns._cli_version(str(cli_path)) == (2, 1, 220)


def test_nonzero_exit_yields_no_version(env, cli):
    ns = cli(env["nowhere"])
    assert ns._cli_version(str(_fake_cli(env["tmp"] / "bin", None))) is None


def test_missing_binary_yields_no_version(env, cli):
    """OSError from a nonexistent path must be swallowed, not raised."""
    ns = cli(env["nowhere"])
    assert ns._cli_version(env["nowhere"]) is None
