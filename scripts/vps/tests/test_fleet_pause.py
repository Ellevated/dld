"""Fleet-wide rate-limit pause marker: window, atomic writes, CLI guard (TECH-226).

`run-agent.sh` calls `fleet_pause.py --check` on every claude launch, so the
marker path (`fleet_pause.MARKER`) is patched per test rather than passed as a
default argument — the module reads the global at call time.
"""

import json
import logging
import sys
from pathlib import Path

import pytest

VPS_DIR = Path(__file__).resolve().parent.parent
if str(VPS_DIR) not in sys.path:
    sys.path.insert(0, str(VPS_DIR))

import fleet_pause  # noqa: E402


@pytest.fixture(autouse=True)
def _marker(tmp_path, monkeypatch):
    monkeypatch.setattr(fleet_pause, "MARKER", tmp_path / ".rate-limited-until")


def test_set_pause_opens_window():
    now = 1_000_000.0
    assert fleet_pause.set_pause(now + 1800, "five_hour", "x", now=now) is True
    pause = fleet_pause.active_pause(now=now)
    assert pause["until"] == now + 1800


def test_repeat_in_open_window_does_not_reopen_or_shrink():
    now = 1_000_000.0
    assert fleet_pause.set_pause(now + 1800, "five_hour", "x", now=now) is True
    assert fleet_pause.set_pause(now + 1200, "five_hour", "x", now=now) is False
    assert fleet_pause.active_pause(now=now)["until"] == now + 1800
    assert fleet_pause.set_pause(now + 2400, "five_hour", "x", now=now) is False
    assert fleet_pause.active_pause(now=now)["until"] == now + 2400


def test_expired_marker_is_absent_and_reopens():
    now = 1_000_000.0
    fleet_pause.MARKER.write_text(json.dumps({"until": now - 1}))
    assert fleet_pause.active_pause(now=now) is None
    assert fleet_pause.set_pause(now + 600, "five_hour", "x", now=now) is True


def test_garbage_marker_is_absent_with_warning(caplog):
    fleet_pause.MARKER.write_text("{not json")
    with caplog.at_level(logging.WARNING, logger="fleet_pause"):
        assert fleet_pause.active_pause() is None
    assert any(r.levelname == "WARNING" for r in caplog.records)


def test_cli_check(capsys):
    assert fleet_pause.main(["--check"]) == 0

    now = fleet_pause.time.time()
    fleet_pause.set_pause(now + 1800, "five_hour", "x", now=now)

    rc = fleet_pause.main(["--check"])
    assert rc == 75
    out = json.loads(capsys.readouterr().out)
    assert out["skipped"] == "fleet_paused"
    assert "until" in out
