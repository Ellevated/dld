"""Fleet-wide rate-limit pause marker: window, atomic writes, CLI guard (TECH-226).

`run-agent.sh` calls `fleet_pause.py --check` on every claude launch, so the
marker path (`fleet_pause.MARKER`) is patched per test rather than passed as a
default argument — the module reads the global at call time.
"""

import json
import logging
import re
import sys
import threading
from pathlib import Path

import pytest

VPS_DIR = Path(__file__).resolve().parent.parent
if str(VPS_DIR) not in sys.path:
    sys.path.insert(0, str(VPS_DIR))

import fleet_pause  # noqa: E402
import runner_ratelimit  # noqa: E402


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


def test_five_threads_one_alert(monkeypatch):
    calls = []
    lock = threading.Lock()

    def fake_notify(*args, **kwargs):
        with lock:
            calls.append(args)

    monkeypatch.setattr(runner_ratelimit.event_writer, "notify", fake_notify)
    now = 2_000_000.0
    barrier = threading.Barrier(5)

    def worker():
        barrier.wait()
        runner_ratelimit.on_rejected(
            {"resets_at": now + 1800, "rate_limit_type": "five_hour"}, "p:autopilot", now=now
        )

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(calls) == 1
    assert fleet_pause.active_pause(now=now)["until"] == now + 1800


def test_unknown_reset_pauses_one_hour(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        runner_ratelimit.event_writer, "notify", lambda *a, **k: captured.setdefault("text", a[3])
    )
    now = 3_000_000.0
    runner_ratelimit.on_rejected(
        {"resets_at": None, "rate_limit_type": None}, "p:autopilot", now=now
    )
    assert fleet_pause.active_pause(now=now)["until"] == now + 3600
    assert "время сброса неизвестно" in captured["text"]


def test_seven_day_text_has_weekday_and_days(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        runner_ratelimit.event_writer, "notify", lambda *a, **k: captured.setdefault("text", a[3])
    )
    now = 4_000_000.0
    resets_at = now + 2 * 86400 + 14 * 3600
    runner_ratelimit.on_rejected(
        {"resets_at": resets_at, "rate_limit_type": "seven_day"}, "p:autopilot", now=now
    )
    text = captured["text"]
    assert "2 д 14 ч" in text
    assert re.search(r"(пн|вт|ср|чт|пт|сб|вс) \d\d\.\d\d", text)


def test_on_rejected_swallows_notify_exception(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("hermes down")

    monkeypatch.setattr(runner_ratelimit.event_writer, "notify", boom)
    now = 5_000_000.0
    runner_ratelimit.on_rejected(
        {"resets_at": now + 1800, "rate_limit_type": "five_hour"}, "p:autopilot", now=now
    )
    # no exception propagated; the pause window is still recorded
