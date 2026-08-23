"""BUG-218 — переход queued → in_progress выполняется при диспатче.

Написаны ДО фикса: тесты класса TestDispatchWritesInProgress обязаны падать на
неизменённом orchestrator.py. Тест TestStartupReconcileFailClosed тоже.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import lifecycle  # noqa: E402
import orchestrator  # noqa: E402


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


def _dispatch(repo, spec_id, pueue_id=42):
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
    """
    # `## Allowed Files` в каноничной v1-форме: с 2026-08-23 гейт в
    # orchestrator_queue не диспатчит спеку без него — callback-гейт всё равно
    # заблокировал бы её на приёме, чем бы прогон ни кончился.
    (repo / "ai" / "features" / f"{spec_id}-x.md").write_text(
        "# spec\n\n## Allowed Files\n\n<!-- callback-allowlist v1 -->\n- `src/dummy.py`\n",
        encoding="utf-8",
    )
    with (
        patch("orchestrator.SCRIPT_DIR", repo),
        patch("orchestrator.pueue_has_active_label", return_value=False),
        patch("orchestrator.pueue_has_active_spec", return_value=False),
        patch("orchestrator.db.get_available_slots", return_value=1),
        patch("orchestrator.db.get_project_state", return_value={"provider": "claude"}),
        patch("orchestrator.db.get_provider_capacity", return_value=1),
        patch("orchestrator._pueue_add", MagicMock(return_value=pueue_id)),
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
