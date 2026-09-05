"""Tests for scripts/check-experiments.py — the gate that makes somebody look.

The gate's whole value is that it fails. A gate that only ever passes is indistinguishable
from no gate, and that is exactly the state it was written to replace: four months of
changes nobody measured.

EC-1: an open experiment past its date fails
EC-2: an open experiment before its date passes
EC-3: an experiment with no deadline at all fails — that is how one gets forgotten
EC-4: a closed experiment with no verdict fails
EC-5: a closed experiment with a verdict passes
EC-6: missing required fields fail
EC-7: a missing directory is not an error (a fresh clone, a downstream project)
"""

import datetime
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_experiments", REPO / "scripts" / "check-experiments.py"
)
check_experiments = importlib.util.module_from_spec(_spec)
sys.modules["check_experiments"] = check_experiments
_spec.loader.exec_module(check_experiments)

TODAY = datetime.date(2026, 9, 5)

FIELDS = {
    "id": "EXP-999",
    "title": "test",
    "opened": "2026-09-01",
    "status": "open",
    "metric": "p50_min",
    "baseline": "p50_min=136",
    "expected": "p50_min <= 100",
}


def write_experiment(tmp_path: Path, name="exp.md", **overrides) -> Path:
    fields = {**FIELDS, **overrides}
    lines = [f"{k}: {v}" for k, v in fields.items() if v is not None]
    path = tmp_path / name
    path.write_text("---\n" + "\n".join(lines) + "\n---\n\nbody\n", encoding="utf-8")
    return path


def problems_for(tmp_path: Path, **overrides) -> list:
    write_experiment(tmp_path, **overrides)
    experiments = [check_experiments.parse_front_matter(p) for p in sorted(tmp_path.glob("*.md"))]
    return check_experiments.check([e for e in experiments if e], TODAY)


class TestDeadlines:
    def test_overdue_fails(self, tmp_path):
        """EC-1."""
        problems = problems_for(tmp_path, check_after_date="2026-09-04")
        assert [p["kind"] for p in problems] == ["overdue"]

    def test_due_today_fails(self, tmp_path):
        """The deadline is the day you look, not the day after."""
        problems = problems_for(tmp_path, check_after_date="2026-09-05")
        assert [p["kind"] for p in problems] == ["overdue"]

    def test_future_date_passes(self, tmp_path):
        """EC-2."""
        assert problems_for(tmp_path, check_after_date="2026-09-30") == []

    def test_no_deadline_fails(self, tmp_path):
        """EC-3: an open experiment with no deadline is how one gets forgotten."""
        problems = problems_for(tmp_path)
        assert [p["kind"] for p in problems] == ["no_deadline"]

    def test_unparsable_date_fails(self, tmp_path):
        problems = problems_for(tmp_path, check_after_date="через две недели")
        assert [p["kind"] for p in problems] == ["bad_date"]

    def test_run_threshold_reached_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(check_experiments, "runs_since", lambda _: 20)
        problems = problems_for(tmp_path, check_after_runs="15", check_after_date="2026-12-01")
        assert [p["kind"] for p in problems] == ["enough_runs"]

    def test_run_threshold_not_reached_passes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(check_experiments, "runs_since", lambda _: 3)
        assert problems_for(tmp_path, check_after_runs="15", check_after_date="2026-12-01") == []

    def test_uncountable_runs_do_not_pass_silently(self, tmp_path, monkeypatch):
        """No logs (CI) → the run threshold cannot be judged, so the date must carry it.

        Treating "cannot count" as "not due yet" is the one failure a gate must not have.
        """
        monkeypatch.setattr(check_experiments, "runs_since", lambda _: None)
        problems = problems_for(tmp_path, check_after_runs="15", check_after_date="2026-09-01")
        assert [p["kind"] for p in problems] == ["overdue"]


class TestVerdicts:
    @pytest.mark.parametrize("status", ["confirmed", "refuted", "inconclusive", "abandoned"])
    def test_closed_without_verdict_fails(self, tmp_path, status):
        """EC-4: closing an experiment without saying what the numbers showed."""
        problems = problems_for(tmp_path, status=status, check_after_date="2026-12-01")
        assert [p["kind"] for p in problems] == ["closed_without_verdict"]

    def test_closed_with_verdict_passes(self, tmp_path):
        """EC-5."""
        assert (
            problems_for(tmp_path, status="refuted", verdict="timeout_rate 50% -> 48%, no move")
            == []
        )

    def test_unknown_status_fails(self, tmp_path):
        problems = problems_for(tmp_path, status="in progress", check_after_date="2026-12-01")
        assert [p["kind"] for p in problems] == ["bad_status"]


class TestRequiredFields:
    def test_missing_expected_fails(self, tmp_path):
        """EC-6: a hypothesis with no threshold cannot be checked against anything."""
        problems = problems_for(tmp_path, expected=None, check_after_date="2026-12-01")
        assert problems[0]["kind"] == "incomplete"
        assert "expected" in problems[0]["detail"]

    def test_missing_baseline_fails(self, tmp_path):
        problems = problems_for(tmp_path, baseline=None, check_after_date="2026-12-01")
        assert "baseline" in problems[0]["detail"]


class TestFrontMatter:
    def test_no_front_matter_returns_none(self, tmp_path):
        path = tmp_path / "plain.md"
        path.write_text("# just a document\n", encoding="utf-8")
        assert check_experiments.parse_front_matter(path) is None

    def test_unterminated_front_matter_returns_none(self, tmp_path):
        path = tmp_path / "broken.md"
        path.write_text("---\nid: EXP-1\nno closing fence\n", encoding="utf-8")
        assert check_experiments.parse_front_matter(path) is None


class TestCli:
    def test_missing_directory_is_not_an_error(self, tmp_path, capsys):
        """EC-7: a fresh clone has no experiments yet — that is not a failure."""
        assert check_experiments.main(["--dir", str(tmp_path / "nope")]) == 0

    def test_exit_1_on_problem(self, tmp_path):
        write_experiment(tmp_path, check_after_date="2026-01-01")
        assert check_experiments.main(["--dir", str(tmp_path)]) == 1

    def test_exit_0_when_clean(self, tmp_path):
        write_experiment(tmp_path, check_after_date="2099-01-01")
        assert check_experiments.main(["--dir", str(tmp_path)]) == 0

    def test_repo_experiments_are_wellformed(self):
        """The real directory must parse — a typo here disarms the gate silently."""
        exp_dir = REPO / "ai" / "experiments"
        files = [p for p in exp_dir.glob("*.md") if p.name != "README.md"]
        assert files, "no experiments on disk"
        for path in files:
            fm = check_experiments.parse_front_matter(path)
            assert fm is not None, f"{path.name}: no front matter"
            missing = [k for k in check_experiments.REQUIRED if not fm.get(k)]
            assert not missing, f"{path.name}: missing {missing}"
