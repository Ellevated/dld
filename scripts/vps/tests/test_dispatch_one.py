"""dispatch_one: which spec body it hands the run, and the "no spec body" wall.

The built-in dispatch path used to carry these checks' tests; it was removed on
2026-09-27 and `dispatch_one.py` is the only way a spec runs. `spec_body_files` is
what both the wall and `CLAUDE_CURRENT_SPEC_PATH` (BUG-199) stand on.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

VPS_DIR = Path(__file__).resolve().parent.parent
if str(VPS_DIR) not in sys.path:
    sys.path.insert(0, str(VPS_DIR))

import dispatch_one  # noqa: E402
import orchestrator_queue  # noqa: E402


def _features(root: Path, *names: str) -> Path:
    features = root / "ai" / "features"
    features.mkdir(parents=True, exist_ok=True)
    for name in names:
        (features / name).write_text("# spec\n", encoding="utf-8")
    return features


def _dispatch(project_dir: Path, spec_id: str, add: MagicMock) -> int:
    with (
        patch(
            "dispatch_one.db.get_project_state",
            return_value={"path": str(project_dir), "provider": "claude"},
        ),
        patch("dispatch_one.fleet_pause.active_pause", return_value=None),
        patch("dispatch_one.db.get_available_slots", return_value=1),
        patch("orchestrator_slots.pueue_has_active_label", return_value=False),
        patch("orchestrator_slots.pueue_has_active_spec", return_value=False),
        patch("orchestrator_slots._pueue_add", add),
        patch("orchestrator_queue.record_dispatch"),
    ):
        return dispatch_one.dispatch("p", spec_id, "autopilot", None, "")


class TestSpecBodyFiles:
    def test_dated_slug_suffix_is_found(self, tmp_path):
        """Spec files carry a date+slug suffix; the lookup must still find them."""
        _features(tmp_path, "FTR-0081-2026-07-26-console-scaffold.md")
        found = orchestrator_queue.spec_body_files(str(tmp_path), "FTR-0081")
        assert [p.name for p in found] == ["FTR-0081-2026-07-26-console-scaffold.md"]

    def test_bare_id_file_is_found(self, tmp_path):
        _features(tmp_path, "TECH-7.md")
        found = orchestrator_queue.spec_body_files(str(tmp_path), "TECH-7")
        assert [p.name for p in found] == ["TECH-7.md"]

    def test_longer_id_is_not_this_spec(self, tmp_path):
        """FTR-150 must not pick up FTR-1506's body."""
        _features(tmp_path, "FTR-1506-2026-09-01-other.md", "FTR-150-2026-06-01-mine.md")
        found = orchestrator_queue.spec_body_files(str(tmp_path), "FTR-150")
        assert [p.name for p in found] == ["FTR-150-2026-06-01-mine.md"]

    def test_only_a_longer_id_means_no_body(self, tmp_path):
        _features(tmp_path, "FTR-1506-2026-09-01-other.md")
        assert orchestrator_queue.spec_body_files(str(tmp_path), "FTR-150") == []

    def test_directory_is_not_a_body(self, tmp_path):
        features = _features(tmp_path, "BUG-9-2026-01-01-x.md")
        (features / "BUG-9-assets").mkdir()
        found = orchestrator_queue.spec_body_files(str(tmp_path), "BUG-9")
        assert [p.name for p in found] == ["BUG-9-2026-01-01-x.md"]


class TestNoSpecBodyWall:
    def test_refuses_when_only_a_longer_id_exists(self, tmp_path, capsys):
        _features(tmp_path, "FTR-1506-2026-09-01-other.md")
        add = MagicMock(return_value=7)

        rc = _dispatch(tmp_path, "FTR-150", add)

        assert rc == 2
        assert "no spec body" in json.loads(capsys.readouterr().out)["reason"]
        add.assert_not_called()

    def test_pins_its_own_body_not_the_longer_id(self, tmp_path):
        features = _features(tmp_path, "FTR-1506-2026-09-01-other.md", "FTR-150-2026-06-01-mine.md")
        add = MagicMock(return_value=7)

        assert _dispatch(tmp_path, "FTR-150", add) == 0

        env = add.call_args.kwargs["env"]
        assert env["CLAUDE_CURRENT_SPEC_PATH"] == str(features / "FTR-150-2026-06-01-mine.md")


@pytest.fixture(autouse=True)
def _no_real_db(monkeypatch, tmp_path):
    """Every db call above is patched; point DB_PATH away from the live file anyway."""
    import db

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "unused.db"))
