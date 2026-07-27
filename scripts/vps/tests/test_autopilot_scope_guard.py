"""Tests for BUG-199 autopilot scope guard fixes.

Fix A: prompt structural assertions (doc-lint style).
Fix B: orchestrator autopilot dispatch sets CLAUDE_CURRENT_SPEC_PATH.
Fix C: callback detects out-of-scope files in spec-attributed commits.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent  # scripts/vps/
REPO_ROOT = SCRIPT_DIR.parent.parent  # project root (above scripts/)
sys.path.insert(0, str(SCRIPT_DIR))


# ============================================================================
# Fix A — Prompt structure assertions (doc-lint style)
# ============================================================================


class TestFixAPromptStructure:
    """Verify that SKILL.md and finishing.md contain the structural guards."""

    @pytest.fixture()
    def repo_root(self) -> Path:
        """Locate repository root (above scripts/)."""
        return REPO_ROOT

    def test_skill_md_has_loop_mode_hard_gate(self, repo_root: Path) -> None:
        """SKILL.md must contain the LOOP-MODE-SCOPE-FENCE hard gate."""
        for prefix in (".claude", "template/.claude"):
            skill_path = repo_root / prefix / "skills" / "autopilot" / "SKILL.md"
            if not skill_path.exists():
                pytest.skip(f"{skill_path} not found")
            content = skill_path.read_text(encoding="utf-8")
            assert "LOOP-MODE-SCOPE-FENCE" in content, (
                f"{skill_path}: missing HARD-GATE LOOP-MODE-SCOPE-FENCE"
            )

    def test_skill_md_interactive_mode_guarded(self, repo_root: Path) -> None:
        """Interactive Mode section must explicitly exclude loop mode."""
        for prefix in (".claude", "template/.claude"):
            skill_path = repo_root / prefix / "skills" / "autopilot" / "SKILL.md"
            if not skill_path.exists():
                pytest.skip(f"{skill_path} not found")
            content = skill_path.read_text(encoding="utf-8")
            assert "ONLY active when autopilot is invoked WITHOUT" in content, (
                f"{skill_path}: Interactive Mode section missing loop-mode exclusion guard"
            )

    def test_finishing_md_has_governance_warning(self, repo_root: Path) -> None:
        """finishing.md step 10 must reference governance violation BUG-199."""
        for prefix in (".claude", "template/.claude"):
            fin_path = repo_root / prefix / "skills" / "autopilot" / "finishing.md"
            if not fin_path.exists():
                pytest.skip(f"{fin_path} not found")
            content = fin_path.read_text(encoding="utf-8")
            assert "governance violation" in content.lower(), (
                f"{fin_path}: missing 'governance violation' in Loop Mode Exit Check"
            )

    def test_skill_md_interactive_continue_annotated(self, repo_root: Path) -> None:
        """Interactive Mode 'Continue to next spec' step must be annotated."""
        for prefix in (".claude", "template/.claude"):
            skill_path = repo_root / prefix / "skills" / "autopilot" / "SKILL.md"
            if not skill_path.exists():
                pytest.skip(f"{skill_path} not found")
            content = skill_path.read_text(encoding="utf-8")
            assert "INTERACTIVE ONLY" in content, (
                f"{skill_path}: 'Continue to next spec' missing INTERACTIVE ONLY annotation"
            )


# ============================================================================
# Fix B — Orchestrator autopilot dispatch sets CLAUDE_CURRENT_SPEC_PATH
# ============================================================================


class TestFixBEnvWiring:
    """Verify that scan_queued passes the spec path env var to pueue dispatch."""

    def test_scan_queued_sets_spec_env_in_pueue_add(self) -> None:
        """scan_queued must call _pueue_add with env containing CLAUDE_CURRENT_SPEC_PATH."""
        orch_path = SCRIPT_DIR / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")

        in_scan_queued = False
        found_spec_path_in_env = False
        found_env_in_pueue_add = False

        for line in content.splitlines():
            if "def scan_queued" in line:
                in_scan_queued = True
                continue
            if in_scan_queued:
                if line.strip().startswith("def ") and "scan_queued" not in line:
                    break
                if "CLAUDE_CURRENT_SPEC_PATH" in line and "pueue_env" in line:
                    found_spec_path_in_env = True
                if "env=pueue_env" in line:
                    found_env_in_pueue_add = True

        assert found_spec_path_in_env, (
            "scan_queued must define pueue_env with CLAUDE_CURRENT_SPEC_PATH"
        )
        assert found_env_in_pueue_add, (
            "scan_queued must pass env=pueue_env to _pueue_add"
        )

    def test_claude_runner_forwards_spec_env(self) -> None:
        """claude-runner.py must forward CLAUDE_CURRENT_SPEC_PATH to the agent session."""
        runner_path = SCRIPT_DIR / "claude-runner.py"
        content = runner_path.read_text(encoding="utf-8")
        assert '"CLAUDE_CURRENT_SPEC_PATH"' in content, (
            "claude-runner.py must include CLAUDE_CURRENT_SPEC_PATH in agent env dict"
        )
        assert 'os.environ.get("CLAUDE_CURRENT_SPEC_PATH"' in content, (
            "claude-runner.py must read CLAUDE_CURRENT_SPEC_PATH from os.environ"
        )

    def test_pre_edit_hook_prefers_env_over_branch(self) -> None:
        """pre-edit.mjs must prefer CLAUDE_CURRENT_SPEC_PATH env over inferSpecFromBranch."""
        hook_path = REPO_ROOT / ".claude" / "hooks" / "pre-edit.mjs"
        content = hook_path.read_text(encoding="utf-8")
        assert "process.env.CLAUDE_CURRENT_SPEC_PATH" in content, (
            "pre-edit.mjs must read CLAUDE_CURRENT_SPEC_PATH from env"
        )
        env_pos = content.index("process.env.CLAUDE_CURRENT_SPEC_PATH")
        infer_pos = content.index("inferSpecFromBranch()")
        assert env_pos < infer_pos, (
            "pre-edit.mjs must prefer env var OVER inferSpecFromBranch (env first in ||)"
        )


# ============================================================================
# Fix C — Out-of-scope commit detection in callback
# ============================================================================


def _make_git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with an initial commit."""
    repo = tmp_path / "project"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@test.com"],
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"],
        capture_output=True, check=True,
    )
    (repo / "README.md").write_text("# Test", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "init"],
        capture_output=True, check=True,
    )
    return repo


class TestFixCOutOfScopeDetection:
    """Test _detect_out_of_scope_files from callback.py using real git repos."""

    @pytest.fixture()
    def git_repo(self, tmp_path: Path) -> Path:
        return _make_git_repo(tmp_path)

    def test_no_out_of_scope_when_all_files_in_allowlist(self, git_repo: Path) -> None:
        """Commits touching only allowed files should return empty list."""
        import callback

        allowed = ["src/main.py", "src/utils.py"]
        (git_repo / "src").mkdir(exist_ok=True)
        (git_repo / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
        subprocess.run(["git", "-C", str(git_repo), "add", "."], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(git_repo), "commit", "-m", "feat(FTR-100): add main"],
            capture_output=True, check=True,
        )

        result = callback._detect_out_of_scope_files(
            str(git_repo), "FTR-100", allowed, "2020-01-01"
        )
        assert result == []

    def test_detects_out_of_scope_files(self, git_repo: Path) -> None:
        """Commits touching files outside allowlist should be detected."""
        import callback

        allowed = ["src/main.py"]
        (git_repo / "src").mkdir(exist_ok=True)
        (git_repo / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
        (git_repo / "extra.py").write_text("print('extra')", encoding="utf-8")
        subprocess.run(["git", "-C", str(git_repo), "add", "."], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(git_repo), "commit", "-m", "feat(FTR-100): add main and extra"],
            capture_output=True, check=True,
        )

        result = callback._detect_out_of_scope_files(
            str(git_repo), "FTR-100", allowed, "2020-01-01"
        )
        assert "extra.py" in result

    def test_ignores_non_spec_commits(self, git_repo: Path) -> None:
        """Commits without spec_id in subject should be ignored."""
        import callback

        allowed = ["src/main.py"]
        (git_repo / "extra.py").write_text("print('extra')", encoding="utf-8")
        subprocess.run(["git", "-C", str(git_repo), "add", "."], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(git_repo), "commit", "-m", "chore: unrelated cleanup"],
            capture_output=True, check=True,
        )

        result = callback._detect_out_of_scope_files(
            str(git_repo), "FTR-100", allowed, "2020-01-01"
        )
        assert result == []

    def test_ignores_ai_paths(self, git_repo: Path) -> None:
        """Files under ai/ should not count as out-of-scope."""
        import callback

        allowed = ["src/main.py"]
        (git_repo / "src").mkdir(exist_ok=True)
        (git_repo / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
        (git_repo / "ai").mkdir(exist_ok=True)
        (git_repo / "ai" / "diary.md").write_text("diary entry", encoding="utf-8")
        subprocess.run(["git", "-C", str(git_repo), "add", "."], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(git_repo), "commit", "-m", "feat(FTR-100): add main"],
            capture_output=True, check=True,
        )

        result = callback._detect_out_of_scope_files(
            str(git_repo), "FTR-100", allowed, "2020-01-01"
        )
        assert result == [], "ai/ paths should be excluded from out-of-scope detection"

    def test_empty_allowed_returns_empty(self, git_repo: Path) -> None:
        """Empty or None allowed list should return empty (no false alarms)."""
        import callback

        result = callback._detect_out_of_scope_files(
            str(git_repo), "FTR-100", [], "2020-01-01"
        )
        assert result == []

        result = callback._detect_out_of_scope_files(
            str(git_repo), "FTR-100", None, "2020-01-01"
        )
        assert result == []

    def test_does_not_block_status(self) -> None:
        """Out-of-scope detection must NOT change the status outcome (WARNING only)."""
        import callback
        import inspect

        source = inspect.getsource(callback.verify_status_sync)
        assert "_detect_out_of_scope_files" in source, (
            "verify_status_sync should call _detect_out_of_scope_files"
        )
        # Ensure result is NOT used to set new_status
        for line in source.splitlines():
            if "new_status" in line and "out_of_scope" in line:
                pytest.fail(
                    f"out_of_scope_files must NOT influence new_status: {line.strip()}"
                )


# ============================================================================
# Integration: _emit_audit includes out_of_scope_files
# ============================================================================


class TestAuditIntegration:
    """Verify that _emit_audit accepts and records extra kwargs."""

    def test_emit_audit_with_extra_kwargs(self, tmp_path: Path) -> None:
        """_emit_audit should accept **extra and include them in the JSONL record."""
        import callback

        audit_path = tmp_path / "test-audit.jsonl"
        old_val = os.environ.get("CALLBACK_AUDIT_LOG")
        os.environ["CALLBACK_AUDIT_LOG"] = str(audit_path)
        try:
            callback._emit_audit(
                "test_project",
                "FTR-100",
                42,
                "done",
                "done",
                "ok",
                5,
                100,
                50,
                3,
                "2026-01-01",
                0.0,
                out_of_scope_files=["extra.py", "rogue.js"],
            )
            content = audit_path.read_text(encoding="utf-8")
            record = json.loads(content.strip())
            assert record["out_of_scope_files"] == ["extra.py", "rogue.js"]
            assert record["spec_id"] == "FTR-100"
        finally:
            if old_val is not None:
                os.environ["CALLBACK_AUDIT_LOG"] = old_val
            else:
                os.environ.pop("CALLBACK_AUDIT_LOG", None)

    def test_emit_audit_without_extra_kwargs(self, tmp_path: Path) -> None:
        """_emit_audit without extra kwargs should work as before (no regression)."""
        import callback

        audit_path = tmp_path / "test-audit.jsonl"
        old_val = os.environ.get("CALLBACK_AUDIT_LOG")
        os.environ["CALLBACK_AUDIT_LOG"] = str(audit_path)
        try:
            callback._emit_audit(
                "test_project",
                "FTR-100",
                42,
                "done",
                "done",
                "ok",
                5,
                100,
                50,
                3,
                "2026-01-01",
                0.0,
            )
            content = audit_path.read_text(encoding="utf-8")
            record = json.loads(content.strip())
            assert "out_of_scope_files" not in record
            assert record["spec_id"] == "FTR-100"
        finally:
            if old_val is not None:
                os.environ["CALLBACK_AUDIT_LOG"] = old_val
            else:
                os.environ.pop("CALLBACK_AUDIT_LOG", None)
