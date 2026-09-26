"""dispatch_one refusal and briefing PAUSED line (TECH-226 Task 4/5).

Fleet pause concerns the Claude subscription only — codex/gemini are untouched.
The built-in gate's copy of this refusal left with the builtin path (2026-09-27).
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

VPS_DIR = Path(__file__).resolve().parent.parent
if str(VPS_DIR) not in sys.path:
    sys.path.insert(0, str(VPS_DIR))

import dispatch_one  # noqa: E402
import dispatch_summary  # noqa: E402
import fleet_pause  # noqa: E402

ALLOWLIST_BLOCK = "\n## Allowed Files\n\n<!-- callback-allowlist v1 -->\n- `src/dummy.py`\n"


@pytest.fixture(autouse=True)
def _marker(tmp_path, monkeypatch):
    monkeypatch.setattr(fleet_pause, "MARKER", tmp_path / ".rate-limited-until")


def _write_spec(project_dir, spec_id, body="# S\n" + ALLOWLIST_BLOCK):
    features = Path(project_dir) / "ai" / "features"
    features.mkdir(parents=True, exist_ok=True)
    (features / f"{spec_id}-x.md").write_text(body, encoding="utf-8")


def _open_pause():
    # Production readers call active_pause() with no `now` — real wall-clock time —
    # so the marker must be open against real time, not a fixed epoch like the
    # fleet_pause unit tests use.
    fleet_pause.set_pause(fleet_pause.time.time() + 1800, "five_hour", "probe")


def test_dispatch_one_refuses_when_paused(tmp_path, isolated_db, monkeypatch, capsys):
    import db

    db.seed_projects_from_json([{"project_id": "p", "path": str(tmp_path), "provider": "claude"}])
    _write_spec(tmp_path, "TECH-1")
    _open_pause()

    with patch("orchestrator_slots._pueue_add") as mock_add:
        rc = dispatch_one.dispatch("p", "TECH-1", "autopilot", None, "")

    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert out["reason"].startswith("fleet paused until")
    mock_add.assert_not_called()


def test_dispatch_one_pause_is_claude_only(tmp_path, isolated_db, monkeypatch, capsys):
    import db

    db.seed_projects_from_json([{"project_id": "p", "path": str(tmp_path), "provider": "claude"}])
    _write_spec(tmp_path, "TECH-1")
    _open_pause()
    monkeypatch.setattr(dispatch_one.db, "get_available_slots", lambda p: 0)

    rc = dispatch_one.dispatch("p", "TECH-1", "autopilot", "codex", "")

    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert out["reason"] == "no free codex slot"


def test_briefing_leads_with_paused(isolated_db, monkeypatch):
    monkeypatch.setattr(dispatch_summary, "_run", lambda *a, **k: "")
    _open_pause()

    out = dispatch_summary.render(dispatch_summary.build([])).splitlines()
    lines = [ln for ln in out if ln]

    assert lines[0] == "# Dispatch briefing"
    assert lines[1].startswith("**PAUSED until")


def test_briefing_control_without_pause(isolated_db, monkeypatch):
    monkeypatch.setattr(dispatch_summary, "_run", lambda *a, **k: "")

    out = dispatch_summary.render(dispatch_summary.build([]))

    assert "PAUSED" not in out


def test_render_tolerates_summary_without_paused_key():
    summary = {
        "slots_free": {"claude": 1, "codex": 1, "gemini": 1},
        "provider_health": {},
        "pueue_active": [],
        "projects": [],
        "recent": [],
    }

    out = dispatch_summary.render(summary)

    assert out.startswith("# Dispatch briefing")
