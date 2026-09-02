# scripts/vps/tests/test_orchestrator_ci_gate.py
"""CI stop-the-line gate (2026-09-02): dispatch holds while <project>-ci.status = fail.

Why: awardybot reflect R100/R101 — six specs went `done` on top of a 60-hour red
develop because the orchestrator never looked at the CI watchdog's verdict.
"""

from unittest.mock import patch

import orchestrator
import orchestrator_ci_gate


def _project(tmp_path, spec_id="TECH-1481", body="# spec\n"):
    features = tmp_path / "ai" / "features"
    features.mkdir(parents=True, exist_ok=True)
    (features / f"{spec_id}-dummy.md").write_text(body, encoding="utf-8")
    return str(tmp_path)


def _state(tmp_path, monkeypatch, status=None, red_since=None, gate_off=False):
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    monkeypatch.setattr(orchestrator_ci_gate, "CI_STATE_DIR", state)
    if status is not None:
        (state / "awardybot-ci.status").write_text(status + "\n", encoding="utf-8")
    if red_since is not None:
        (state / "awardybot-ci.red_since").write_text(red_since, encoding="utf-8")
    if gate_off:
        (state / "awardybot-ci.gate_off").write_text("", encoding="utf-8")
    return state


class TestCiRedSkipReason:
    def test_no_state_file_fails_open(self, tmp_path, monkeypatch):
        pd = _project(tmp_path)
        _state(tmp_path, monkeypatch)
        assert orchestrator_ci_gate.ci_red_skip_reason("awardybot", pd, "TECH-1481") is None

    def test_green_passes(self, tmp_path, monkeypatch):
        pd = _project(tmp_path)
        _state(tmp_path, monkeypatch, status="ok")
        assert orchestrator_ci_gate.ci_red_skip_reason("awardybot", pd, "TECH-1481") is None

    def test_red_holds_and_names_red_since(self, tmp_path, monkeypatch):
        pd = _project(tmp_path)
        _state(tmp_path, monkeypatch, status="fail", red_since="2026-08-31 12:10")
        reason = orchestrator_ci_gate.ci_red_skip_reason("awardybot", pd, "TECH-1481")
        assert reason is not None
        assert "awardybot" in reason
        assert "2026-08-31 12:10" in reason

    def test_red_but_gate_off_passes(self, tmp_path, monkeypatch):
        pd = _project(tmp_path)
        _state(tmp_path, monkeypatch, status="fail", gate_off=True)
        assert orchestrator_ci_gate.ci_red_skip_reason("awardybot", pd, "TECH-1481") is None

    def test_red_but_bypass_spec_passes(self, tmp_path, monkeypatch):
        pd = _project(tmp_path, body="# fix CI\n\nci-gate: bypass\n")
        _state(tmp_path, monkeypatch, status="fail")
        assert orchestrator_ci_gate.ci_red_skip_reason("awardybot", pd, "TECH-1481") is None

    def test_other_project_state_does_not_leak(self, tmp_path, monkeypatch):
        pd = _project(tmp_path)
        _state(tmp_path, monkeypatch, status="fail")
        assert orchestrator_ci_gate.ci_red_skip_reason("dowry", pd, "TECH-1481") is None


class TestQueuedAfterCiGate:
    def test_red_keeps_only_bypass_spec(self, tmp_path, monkeypatch):
        pd = _project(tmp_path, "TECH-1481")
        _project(tmp_path, "TECH-1490", body="# repair\nci-gate: bypass\n")
        _state(tmp_path, monkeypatch, status="fail")
        queued = [{"spec_id": "TECH-1481"}, {"spec_id": "TECH-1490"}]
        with patch.object(orchestrator.lifecycle, "list_by_status", return_value=queued):
            kept = orchestrator_ci_gate.queued_after_ci_gate("awardybot", pd)
        assert [r["spec_id"] for r in kept] == ["TECH-1490"]

    def test_red_holds_everything_when_no_bypass(self, tmp_path, monkeypatch):
        pd = _project(tmp_path, "TECH-1481")
        _state(tmp_path, monkeypatch, status="fail")
        queued = [{"spec_id": "TECH-1481"}]
        with patch.object(orchestrator.lifecycle, "list_by_status", return_value=queued):
            assert orchestrator_ci_gate.queued_after_ci_gate("awardybot", pd) == []

    def test_green_keeps_order(self, tmp_path, monkeypatch):
        pd = _project(tmp_path, "TECH-1481")
        _project(tmp_path, "TECH-1482")
        _state(tmp_path, monkeypatch, status="ok")
        queued = [{"spec_id": "TECH-1481"}, {"spec_id": "TECH-1482"}]
        with patch.object(orchestrator.lifecycle, "list_by_status", return_value=queued):
            assert orchestrator_ci_gate.queued_after_ci_gate("awardybot", pd) == queued

    def test_scan_queued_reads_through_the_gate(self, tmp_path, monkeypatch):
        """scan_queued must consume the gated list: red CI + no bypass → no dispatch."""
        pd = _project(tmp_path, "TECH-1481")
        _state(tmp_path, monkeypatch, status="fail")
        queued = [{"spec_id": "TECH-1481"}]
        with patch.object(orchestrator.lifecycle, "list_by_status", return_value=queued):
            with patch("orchestrator._select_dispatchable_spec") as select:
                assert orchestrator.scan_queued("awardybot", pd) is False
        select.assert_not_called()


class TestModuleInvariants:
    """Same structural invariants TestSplitStructuralInvariants keeps for the other
    orchestrator_* siblings — kept here because test_orchestrator.py is at its LOC ratchet."""

    def test_file_under_loc_limit(self):
        from pathlib import Path

        path = Path(orchestrator_ci_gate.__file__)
        assert len(path.read_text(encoding="utf-8").splitlines()) <= 400

    def test_never_imports_the_facade(self):
        from pathlib import Path

        for line in Path(orchestrator_ci_gate.__file__).read_text(encoding="utf-8").splitlines():
            s = line.strip()
            assert not (s.startswith("import orchestrator ") or s == "import orchestrator")
            assert not s.startswith("from orchestrator import")
