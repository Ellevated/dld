"""BUG-218 — переход queued → in_progress выполняется при диспатче.

Написаны ДО фикса: тесты класса TestDispatchWritesInProgress обязаны падать на
неизменённом orchestrator.py. Тест TestStartupReconcileFailClosed тоже.

TECH-221 — branch_state, three-way reconcile and the continue-dispatch env flag
live here because test_gate_logic.py sits at 598/600 lines.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import callback_sync  # noqa: E402
import gate_ancestry  # noqa: E402
import lifecycle  # noqa: E402
import orchestrator  # noqa: E402
import orchestrator_queue  # noqa: E402


@pytest.fixture()
def tmp_git_repo(tmp_path):
    """Реальный git-репозиторий — приём из test_orchestrator_lifecycle.py:25."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        subprocess.run(
            ["git"] + list(args),
            cwd=str(repo),
            check=True,
            capture_output=True,
            text=True,
        )

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test User")
    (repo / "ai" / "lifecycle").mkdir(parents=True)
    (repo / "ai" / "lifecycle" / ".gitkeep").write_text("", encoding="utf-8")
    (repo / "ai" / "features").mkdir(parents=True, exist_ok=True)
    git("add", ".")
    git("commit", "-m", "init")
    return repo


@pytest.fixture()
def repo_with_origin(tmp_path):
    """local repo + bare origin, develop pushed. Mirrors test_gate_logic.py:72-100."""
    remote, local = tmp_path / "remote", tmp_path / "local"
    subprocess.run(["git", "init", "--bare", "-q", "-b", "develop", str(remote)], check=True)

    def git(*args):
        subprocess.run(["git", *args], cwd=str(local), check=True, capture_output=True)

    local.mkdir()
    git("init", "-q", "-b", "develop")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    git("remote", "add", "origin", str(remote))
    (local / "README.md").write_text("init\n", encoding="utf-8")
    git("add", "README.md")
    git("commit", "-q", "-m", "init")
    git("push", "-q", "origin", "develop")
    return local, git


@pytest.fixture(autouse=True)
def _clear_continue_flag():
    """CLAUDE_CONTINUE_BRANCH is written directly to os.environ by production
    code (orchestrator_queue.reconcile_if_implemented), so monkeypatch cannot
    undo it — a leftover "1" would leak into and mislabel the next test.
    """
    try:
        yield
    finally:
        os.environ.pop("CLAUDE_CONTINUE_BRANCH", None)


def _add_commit(local: Path, git, filename: str, message: str) -> None:
    """Write+add+commit one file. Mirrors test_gate_ancestry.py's _add_commit."""
    path = local / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"content for {filename}\n", encoding="utf-8")
    git("add", filename)
    git("commit", "-q", "-m", message)


def _dispatch(repo, spec_id, pueue_id=42, pueue_add=None):
    """Прогнать scan_queued до конца happy-path на реальном репозитории.

    D8: patch orchestrator.SCRIPT_DIR to the tmp repo — otherwise the
    callback-audit.jsonl guard in scan_queued reads the live worktree's
    scripts/vps/callback-audit.jsonl, which exists here, making the test
    non-hermetic.

    get_provider_capacity is patched even though the `# spec` fixture body has
    no `provider:` line to match: it is unreachable only by accident of the
    fixture text, and db.DB_PATH points at the live orchestrator SQLite. One
    `provider:` line added to the fixture later would silently aim the suite
    at the production database.

    `pueue_add` (TECH-221): optional replacement for the default
    `MagicMock(return_value=pueue_id)` — lets a caller install a capturing
    callable (e.g. to read os.environ at the exact moment `_pueue_add` runs)
    without duplicating the whole patch stack.
    """
    # `## Allowed Files` в каноничной v1-форме: с 2026-08-23 гейт в
    # orchestrator_queue не диспатчит спеку без него — callback-гейт всё равно
    # заблокировал бы её на приёме, чем бы прогон ни кончился.
    (repo / "ai" / "features" / f"{spec_id}-x.md").write_text(
        "# spec\n\n## Allowed Files\n\n<!-- callback-allowlist v1 -->\n- `src/dummy.py`\n",
        encoding="utf-8",
    )
    pueue_add_target = pueue_add if pueue_add is not None else MagicMock(return_value=pueue_id)
    with (
        patch("orchestrator.SCRIPT_DIR", repo),
        patch("orchestrator.pueue_has_active_label", return_value=False),
        patch("orchestrator.pueue_has_active_spec", return_value=False),
        patch("orchestrator.db.get_available_slots", return_value=1),
        patch("orchestrator.db.get_project_state", return_value={"provider": "claude"}),
        patch("orchestrator.db.get_provider_capacity", return_value=1),
        patch("orchestrator._pueue_add", pueue_add_target),
        patch("orchestrator.db.try_acquire_slot"),
        patch("orchestrator.db.log_task"),
        patch("orchestrator.db.update_project_phase"),
        # Непустой allowlist: пустой список — это degrade-closed («секция есть,
        # путей нет»), и с 2026-08-23 гейт диспатча такую спеку не пропускает.
        # Reconcile всё равно не сработает — коммита на develop нет.
        patch("orchestrator.gate_logic.parse_allowed_files", return_value=["src/dummy.py"]),
        patch("orchestrator.gate_logic.fetch_develop", return_value=True),
        patch("orchestrator.gate_logic.find_implementation_commit", return_value=None),
    ):
        return orchestrator.scan_queued("testproject", str(repo))


class TestDispatchWritesInProgress:
    """EC-1..EC-4: диспатч обязан оставить след в lifecycle SoT."""

    def test_status_becomes_in_progress(self, tmp_git_repo):
        """EC-1: после диспатча lifecycle читается как in_progress."""
        lifecycle.create_initial(tmp_git_repo, "TECH-901", "p1", "tech")
        assert _dispatch(tmp_git_repo, "TECH-901") is True
        assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-901")["status"] == "in_progress"

    def test_pueue_id_recorded(self, tmp_git_repo):
        """EC-2: pueue_id попадает в yaml — на нём висит crash recovery."""
        lifecycle.create_initial(tmp_git_repo, "TECH-902", "p1", "tech")
        _dispatch(tmp_git_repo, "TECH-902", pueue_id=1026)
        assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-902")["pueue_id"] == 1026

    def test_started_at_stamped(self, tmp_git_repo):
        """EC-3: lifecycle.py:254-259 наконец срабатывает."""
        lifecycle.create_initial(tmp_git_repo, "TECH-903", "p1", "tech")
        _dispatch(tmp_git_repo, "TECH-903")
        assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-903")["started_at"] is not None

    def test_writer_identity_is_orchestrator(self, tmp_git_repo):
        """EC-4: by=orchestrator — не callback, не spark."""
        lifecycle.create_initial(tmp_git_repo, "TECH-904", "p1", "tech")
        _dispatch(tmp_git_repo, "TECH-904")
        d = lifecycle.read_lifecycle(tmp_git_repo, "TECH-904")
        assert d["updated_by"] == "orchestrator"
        assert d["transitions"][-1]["from"] == "queued"
        assert d["transitions"][-1]["to"] == "in_progress"


class TestWriteFailureNeverUnwindsDispatch:
    """EC-5, EC-6: запись не смеет отменять уже совершённый диспатч.

    `assert_called_once` обязателен, а не украшение. Без него оба теста зелены
    и СЕГОДНЯ (записи нет — side_effect не срабатывает, True возвращается
    тривиально), и после неверного фикса, который поставит write_lifecycle в
    недостижимую ветку или выкинет вовсе. Проверять надо ОБА конца: запись
    состоялась И отказ записи не откатил диспатч.
    """

    def test_cas_race_still_returns_true(self, tmp_git_repo):
        """EC-5: CAS исчерпал ретраи → диспатч всё равно состоялся."""
        lifecycle.create_initial(tmp_git_repo, "TECH-905", "p1", "tech")
        boom = lifecycle.LifecycleWriteRaceError("TECH-905", 5)
        with patch.object(
            orchestrator.lifecycle, "write_lifecycle", side_effect=boom
        ) as mock_write:
            assert _dispatch(tmp_git_repo, "TECH-905") is True
        mock_write.assert_called_once()

    def test_already_done_still_returns_true(self, tmp_git_repo):
        """EC-6: Rule 7 (callback закрыл спеку в гонке) не откатывает диспатч."""
        lifecycle.create_initial(tmp_git_repo, "TECH-906", "p1", "tech")
        boom = lifecycle.LifecycleAlreadyDoneError(
            spec_id="TECH-906", attempted="in_progress", by="orchestrator"
        )
        with patch.object(
            orchestrator.lifecycle, "write_lifecycle", side_effect=boom
        ) as mock_write:
            assert _dispatch(tmp_git_repo, "TECH-906") is True
        mock_write.assert_called_once()


class TestOrphanRecoveryNowWorks:
    """EC-7: сквозной сценарий — диспатч, смерть pueue, восстановление."""

    def test_dispatched_spec_is_reconcilable_after_crash(self, tmp_git_repo):
        """До BUG-218 reconcile_orphans не находил кандидатов НИКОГДА: список
        in_progress был пуст по построению.
        """
        lifecycle.create_initial(tmp_git_repo, "TECH-907", "p1", "tech")
        _dispatch(tmp_git_repo, "TECH-907", pueue_id=777)
        # задача умерла — её id больше не среди живых
        reconciled = lifecycle.reconcile_orphans(tmp_git_repo, pueue_alive_ids=set())
        assert "TECH-907" in reconciled
        assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-907")["status"] == "queued"

    def test_live_task_is_not_demoted(self, tmp_git_repo):
        """Обратная сторона: живую задачу восстановление не трогает."""
        lifecycle.create_initial(tmp_git_repo, "TECH-908", "p1", "tech")
        _dispatch(tmp_git_repo, "TECH-908", pueue_id=778)
        assert lifecycle.reconcile_orphans(tmp_git_repo, pueue_alive_ids={778}) == []
        assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-908")["status"] == "in_progress"


class TestStartupReconcileFailClosed:
    """EC-8, EC-9: get_live_pueue_ids() None vs set() must NOT collapse."""

    def test_pueue_unavailable_demotes_nothing(self, tmp_git_repo):
        """EC-8: get_live_pueue_ids() is None → ни одного демоута.

        Это регрессия, которую вносит сам фикс: `or set()` превращал отказ
        pueue в "живых нет" и снёс бы всю работающую очередь.
        """
        lifecycle.write_lifecycle(tmp_git_repo, "TECH-909", "in_progress", pueue_id=999)
        with (
            patch("orchestrator.get_live_pueue_ids", return_value=None),
            patch(
                "orchestrator.db.get_all_projects",
                return_value=[{"project_id": "t", "path": str(tmp_git_repo)}],
            ),
            patch("orchestrator.lifecycle.assert_clean_lifecycle_tree"),
            patch("orchestrator.cleanup_stale_stashes"),
            patch.object(orchestrator.lifecycle, "reconcile_orphans") as mock_rec,
        ):
            orchestrator.startup_reconcile()
        mock_rec.assert_not_called()
        assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-909")["status"] == "in_progress"

    def test_empty_set_still_reconciles(self, tmp_git_repo):
        """EC-9: пустое множество — это НЕ ошибка. pueue жив и пуст → демоут идёт."""
        lifecycle.write_lifecycle(tmp_git_repo, "TECH-910", "in_progress", pueue_id=998)
        with (
            patch("orchestrator.get_live_pueue_ids", return_value=set()),
            patch(
                "orchestrator.db.get_all_projects",
                return_value=[{"project_id": "t", "path": str(tmp_git_repo)}],
            ),
            patch("orchestrator.lifecycle.assert_clean_lifecycle_tree"),
            patch("orchestrator.cleanup_stale_stashes"),
        ):
            orchestrator.startup_reconcile()
        assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-910")["status"] == "queued"

    def test_integrity_checks_still_run_when_pueue_is_down(self, tmp_git_repo):
        """Пропуск узкий: обе стартовые проверки от pueue не зависят.

        Пиннить надо ОБЕ, а не одну: «узкий пропуск» — это утверждение про
        cleanup_stale_stashes И assert_clean_lifecycle_tree. Проверка только
        второй оставляла бы половину заявления недоказанной.
        """
        with (
            patch("orchestrator.get_live_pueue_ids", return_value=None),
            patch(
                "orchestrator.db.get_all_projects",
                return_value=[{"project_id": "t", "path": str(tmp_git_repo)}],
            ),
            patch("orchestrator.cleanup_stale_stashes") as mock_stashes,
            patch.object(orchestrator.lifecycle, "assert_clean_lifecycle_tree") as mock_assert,
        ):
            orchestrator.startup_reconcile()
        mock_assert.assert_called_once()
        mock_stashes.assert_called_once()


class TestBranchState:
    """EC-1..EC-3: gate_ancestry.branch_state against a real git remote."""

    def test_pushed_branch_is_ahead(self, repo_with_origin):
        """EC-1: branch pushed, 3 commits ahead of develop, develop untouched."""
        local, git = repo_with_origin
        git("checkout", "-q", "-b", "fix/BUG-9")
        for i in range(3):
            _add_commit(local, git, f"f{i}.txt", f"wip {i}")
        git("push", "-q", "origin", "fix/BUG-9")
        git("checkout", "-q", "develop")
        # push already updated refs/remotes/origin/* for this clone — fetch is
        # belt-and-suspenders, kept because branch_state deliberately does not
        # fetch on its own (see its docstring).
        gate_ancestry.fetch_branch(str(local), "BUG-9")

        st = gate_ancestry.branch_state(str(local), "BUG-9")
        assert st.exists is True
        assert st.merged is False
        assert st.ahead == 3
        assert st.behind == 0
        assert st.ref == "fix/BUG-9"

    def test_missing_branch_is_absent(self, repo_with_origin):
        """EC-2: no such branch on origin, and an unknown prefix — no exception."""
        local, _git = repo_with_origin

        st = gate_ancestry.branch_state(str(local), "BUG-404")
        assert st.exists is False

        st_unknown_prefix = gate_ancestry.branch_state(str(local), "NOPE-1")
        assert st_unknown_prefix.exists is False
        assert st_unknown_prefix.ref == ""

    def test_merged_branch_is_ancestor(self, repo_with_origin):
        """EC-3: ff-only merge into develop → merged=True, ahead=0."""
        local, git = repo_with_origin
        git("checkout", "-q", "-b", "fix/BUG-9")
        for i in range(3):
            _add_commit(local, git, f"f{i}.txt", f"wip {i}")
        git("push", "-q", "origin", "fix/BUG-9")
        git("checkout", "-q", "develop")
        git("merge", "-q", "--ff-only", "fix/BUG-9")
        git("push", "-q", "origin", "develop")
        gate_ancestry.fetch_branch(str(local), "BUG-9")

        st = gate_ancestry.branch_state(str(local), "BUG-9")
        assert st.merged is True
        assert st.ahead == 0


class TestDecideStatusNamesTheBranch:
    """EC-4: the grace-retry-exhausted blocked reason names the branch."""

    def test_reason_is_branch_pushed_not_merged(self, repo_with_origin, monkeypatch):
        local, git = repo_with_origin
        git("checkout", "-q", "-b", "fix/BUG-9")
        for i in range(3):
            _add_commit(local, git, f"f{i}.txt", f"wip {i}")
        git("push", "-q", "origin", "fix/BUG-9")
        git("checkout", "-q", "develop")
        # _decide_status sleeps 5s x3 in the grace-retry loop
        # (callback_sync.py:221-228) — not optional to patch out.
        monkeypatch.setattr(callback_sync.time, "sleep", lambda *_: None)

        status, reason, _via = callback_sync._decide_status(
            str(local), "BUG-9", "proj", ["src/x.py"], autopilot_signaled=False
        )
        assert status == "blocked"
        assert reason.startswith("branch_pushed_not_merged:3")
        assert "force-done" not in reason


class TestReconcileThreeWay:
    """EC-5: orchestrator_queue.reconcile's three verdicts against real git."""

    _SPEC_BODY = "# spec\n\n## Allowed Files\n\n<!-- callback-allowlist v1 -->\n- `src/dummy.py`\n"

    def _write_spec(self, local: Path, spec_id: str) -> Path:
        spec_file = local / "ai" / "features" / f"{spec_id}-x.md"
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        spec_file.write_text(self._SPEC_BODY, encoding="utf-8")
        return spec_file

    def test_continue_when_branch_ahead_unmerged(self, repo_with_origin):
        """Branch pushed and ahead of develop, never merged → 'continue'."""
        local, git = repo_with_origin
        spec_file = self._write_spec(local, "BUG-20")
        git("checkout", "-q", "-b", "fix/BUG-20")
        _add_commit(local, git, "unrelated.txt", "wip")
        git("push", "-q", "origin", "fix/BUG-20")
        git("checkout", "-q", "develop")

        assert orchestrator_queue.reconcile(str(local), "BUG-20", spec_file) == "continue"

    def test_done_when_merged_and_touches_allowed_file(self, repo_with_origin):
        """ff-only merge that touched the allowlisted path → 'done'.

        The spec file must be committed to develop BEFORE the branch is cut —
        _base_for_diff's ff-merge fallback bound is the spec's birth commit
        (gate_ancestry.py:_base_for_diff docstring), same setup as
        test_gate_ancestry.py's _spec_birth.
        """
        local, git = repo_with_origin
        spec_file = self._write_spec(local, "BUG-21")
        git("add", "ai/features/BUG-21-x.md")
        git("commit", "-q", "-m", "docs(BUG-21): spec")
        git("push", "-q", "origin", "develop")
        git("checkout", "-q", "-b", "fix/BUG-21")
        _add_commit(local, git, "src/dummy.py", "feat(BUG-21): dummy")
        git("push", "-q", "-u", "origin", "fix/BUG-21")
        git("checkout", "-q", "develop")
        git("merge", "-q", "--ff-only", "fix/BUG-21")
        git("push", "-q", "origin", "develop")

        assert orchestrator_queue.reconcile(str(local), "BUG-21", spec_file) == "done"

    def test_fresh_when_nothing_pushed(self, repo_with_origin):
        """No branch on origin at all → 'fresh'."""
        local, _git = repo_with_origin
        spec_file = self._write_spec(local, "BUG-22")

        assert orchestrator_queue.reconcile(str(local), "BUG-22", spec_file) == "fresh"


class TestContinueDispatchEnvFlag:
    """EC-6: CLAUDE_CONTINUE_BRANCH set on continue, cleared on fresh/done."""

    def test_env_flag_set_and_cleared(self, repo_with_origin):
        local, git = repo_with_origin
        spec_file = local / "ai" / "features" / "BUG-30-x.md"
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        spec_file.write_text(TestReconcileThreeWay._SPEC_BODY, encoding="utf-8")
        git("checkout", "-q", "-b", "fix/BUG-30")
        _add_commit(local, git, "unrelated.txt", "wip")
        git("push", "-q", "origin", "fix/BUG-30")
        git("checkout", "-q", "develop")

        orchestrator_queue.reconcile_if_implemented(str(local), "BUG-30", spec_file)
        assert os.environ["CLAUDE_CONTINUE_BRANCH"] == "1"

        fresh_spec = local / "ai" / "features" / "BUG-31-x.md"
        fresh_spec.write_text(TestReconcileThreeWay._SPEC_BODY, encoding="utf-8")
        orchestrator_queue.reconcile_if_implemented(str(local), "BUG-31", fresh_spec)
        assert "CLAUDE_CONTINUE_BRANCH" not in os.environ

    def test_flag_is_live_at_pueue_add(self, tmp_git_repo):
        """The var must be live in os.environ at the moment `_pueue_add` builds
        `{**os.environ, **env}` (orchestrator_slots.py:197) — the only thing
        the un-editable orchestrator.scan_queued caller lets us prove.
        """
        lifecycle.create_initial(tmp_git_repo, "TECH-911", "p1", "tech")
        seen: dict = {}

        def _capture(*_args, **_kwargs):
            seen["flag"] = os.environ.get("CLAUDE_CONTINUE_BRANCH")
            return 42

        with patch(
            "orchestrator_queue.gate_ancestry.branch_state",
            return_value=gate_ancestry.BranchState("tech/TECH-911", True, False, 3, 0),
        ):
            _dispatch(tmp_git_repo, "TECH-911", pueue_add=_capture)

        assert seen["flag"] == "1"
