"""event_writer.wake_hermes — the only path a pipeline alert takes to Telegram.

Hermes 2026.8 dropped the top-level `-q` flag. From 2026-08-13 to 2026-09-23 every wake
died on an argparse error that went to DEVNULL, so no autopilot, circuit or reaper alert
reached anyone and nothing said so. These tests pin the invocation, not the agent.

EC-1: the wake uses one-shot `-z`, never `-q`
EC-2: the prompt names the one event file, not the whole pending-events directory
EC-3: the alert target comes from the environment, else the sibling .env, else the home channel
EC-4: output is appended to a log instead of discarded
EC-5: notify() hands the event it just wrote to the wake
"""

import sys
from pathlib import Path

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import event_writer  # noqa: E402


@pytest.fixture
def fake_hermes(tmp_path, monkeypatch):
    """A hermes binary that exists, a captured Popen, and a wake log in tmp."""
    binary = tmp_path / "hermes"
    binary.write_text("#!/bin/sh\n")
    monkeypatch.setenv("HERMES_BIN", str(binary))
    monkeypatch.delenv("HERMES_NOTIFY_TARGET", raising=False)
    monkeypatch.setattr(event_writer, "WAKE_LOG", tmp_path / "logs" / "hermes-wake.log")
    calls = []

    def _popen(args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(event_writer.subprocess, "Popen", _popen)
    return binary, calls


def test_wake_uses_oneshot_flag(fake_hermes, tmp_path):
    """EC-1: `-q` is what Hermes stopped accepting."""
    binary, calls = fake_hermes
    assert event_writer.wake_hermes(str(tmp_path), "autopilot", "failed") is True
    args, _ = calls[0]
    assert args[:2] == [str(binary), "-z"]
    assert "-q" not in args


def test_prompt_names_the_single_event(fake_hermes, tmp_path):
    """EC-2: pending-events is never emptied; pointing at the directory hands the agent history."""
    _, calls = fake_hermes
    event = tmp_path / "ai" / "openclaw" / "pending-events" / "20260923-000000-autopilot.json"
    event_writer.wake_hermes(str(tmp_path), "autopilot", "failed", event)
    prompt = calls[0][0][2]
    assert str(event) in prompt
    assert "status=failed" in prompt


def test_target_from_environment(fake_hermes, tmp_path, monkeypatch):
    """EC-3."""
    _, calls = fake_hermes
    monkeypatch.setenv("HERMES_NOTIFY_TARGET", "telegram:-100123:5")
    event_writer.wake_hermes(str(tmp_path), "qa", "failed")
    assert "telegram:-100123:5" in calls[0][0][2]


def test_target_defaults_to_home_channel(fake_hermes, tmp_path, monkeypatch):
    """EC-3: no variable anywhere — Hermes' own default, not a guess."""
    monkeypatch.setattr(event_writer, "__file__", str(tmp_path / "event_writer.py"))
    assert event_writer._notify_target() == "telegram"


def test_target_read_from_sibling_env_file(tmp_path, monkeypatch):
    """EC-3: cron callers do not load .env, so the module reads the one key itself."""
    monkeypatch.delenv("HERMES_NOTIFY_TARGET", raising=False)
    (tmp_path / ".env").write_text("OTHER=1\nHERMES_NOTIFY_TARGET='telegram:-100999:7'\n")
    monkeypatch.setattr(event_writer, "__file__", str(tmp_path / "event_writer.py"))
    assert event_writer._notify_target() == "telegram:-100999:7"


def test_output_goes_to_the_wake_log(fake_hermes, tmp_path):
    """EC-4: a failing wake leaves a trace."""
    _, calls = fake_hermes
    event_writer.wake_hermes(str(tmp_path), "reflect", "done")
    log = event_writer.WAKE_LOG
    assert log.is_file()
    assert "reflect done" in log.read_text(encoding="utf-8")
    assert calls[0][1]["stdout"] is not None


def test_missing_binary_is_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_BIN", str(tmp_path / "absent"))
    assert event_writer.wake_hermes(str(tmp_path), "autopilot", "done") is False


def test_notify_passes_the_written_event(tmp_path, monkeypatch):
    """EC-5."""
    seen = {}
    monkeypatch.setattr(
        event_writer, "wake_hermes", lambda p, s, st, ev=None: seen.setdefault("event", ev)
    )
    event_writer.notify(str(tmp_path), "autopilot", "failed", "autopilot failed for FTR-1")
    assert seen["event"].is_file()
    assert seen["event"].parent.name == "pending-events"
