"""Self-heal пуша lifecycle: грязное дерево и конфликт в ai/backlog.md.

Оба сценария взяты из аварии 2026-08-24, когда оркестратор стоял по dowry
16 часов и по memyselfandi 17 дней: авто-rebase отказывался работать при любых
посторонних правках в дереве, а единственный конфликт (две записи в одну
таблицу backlog) сваливал его в abort.

Каждый инвариант проверяется обеими половинами: механизм должен срабатывать
там, где должен, и НЕ срабатывать там, где не должен.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import lifecycle_push  # noqa: E402

ROW_QUEUED = "| BUG-479 | queued | bug |  | [spec](features/BUG-479.md) |"
ROW_BLOCKED = "| BUG-479 | blocked | bug |  | [spec](features/BUG-479.md) |"
ROW_NEW = "| FTR-480 | queued | ftr |  | [spec](features/FTR-480.md) |"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


@pytest.fixture()
def repo_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Локальный клон + origin, уже разошедшиеся ровно как в аварии.

    origin: spark дописал строку FTR-480.
    local:  callback перевёл BUG-479 в blocked (коммит только по backlog).
    """
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)

    repo = tmp_path / "repo"
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    _git(repo, "checkout", "-q", "-b", "develop")

    ai = repo / "ai"
    ai.mkdir()
    backlog = ai / "backlog.md"
    backlog.write_text(f"# Backlog\n\n{ROW_QUEUED}\n", encoding="utf-8")
    _git(repo, "add", "ai/backlog.md")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "push", "-q", "origin", "develop")

    # origin уезжает вперёд: новая спека в той же таблице
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True)
    _git(other, "config", "user.email", "spark@example.com")
    _git(other, "config", "user.name", "spark")
    _git(other, "checkout", "-q", "develop")
    (other / "ai" / "backlog.md").write_text(
        f"# Backlog\n\n{ROW_QUEUED}\n{ROW_NEW}\n", encoding="utf-8"
    )
    _git(other, "add", "ai/backlog.md")
    _git(other, "commit", "-q", "-m", "spec(FTR-480): filed")
    _git(other, "push", "-q", "origin", "develop")

    # локально callback двигает статус — коммит остаётся непереданным
    backlog.write_text(f"# Backlog\n\n{ROW_BLOCKED}\n", encoding="utf-8")
    _git(repo, "add", "ai/backlog.md")
    _git(repo, "commit", "-q", "-m", "lifecycle(BUG-479): blocked")
    _git(repo, "fetch", "-q", "origin")
    return repo, origin


# --- merge_backlog_conflict: чистая функция ---------------------------------


def test_merge_keeps_our_status_and_carries_the_new_row():
    text = (
        "# Backlog\n\n"
        "<<<<<<< HEAD\n"
        f"{ROW_QUEUED}\n{ROW_NEW}\n"
        "=======\n"
        f"{ROW_BLOCKED}\n"
        ">>>>>>> abc123 (lifecycle(BUG-479): blocked)\n"
    )
    merged = lifecycle_push.merge_backlog_conflict(text)
    assert merged is not None
    assert ROW_BLOCKED in merged, "статус, который поставил callback, обязан выжить"
    assert ROW_NEW in merged, "строку, которую знает только origin, нельзя потерять"
    assert ROW_QUEUED not in merged, "устаревший статус не должен остаться вторым"
    assert "<<<<<<<" not in merged and ">>>>>>>" not in merged


def test_merge_refuses_a_conflict_that_is_not_a_table():
    """Мёртвая половина: проза внутри конфликта — не наше дело."""
    text = (
        "<<<<<<< HEAD\n"
        "Какой-то текст, который никто не обещал разруливать построчно.\n"
        "=======\n"
        f"{ROW_BLOCKED}\n"
        ">>>>>>> abc123\n"
    )
    assert lifecycle_push.merge_backlog_conflict(text) is None


def test_merge_returns_none_when_there_is_no_conflict():
    assert lifecycle_push.merge_backlog_conflict(f"# Backlog\n\n{ROW_BLOCKED}\n") is None


# --- _rebase_onto_origin: живой git -----------------------------------------


def test_rebase_survives_conflict_and_unrelated_dirty_files(repo_pair):
    """Живая половина: и конфликт в таблице, и чужие правки в дереве."""
    repo, _ = repo_pair
    junk = repo / "notes.md"
    junk.write_text("черновик человека, к спекам отношения не имеет\n", encoding="utf-8")

    assert lifecycle_push._rebase_onto_origin(str(repo), "develop") is True

    merged = (repo / "ai" / "backlog.md").read_text(encoding="utf-8")
    assert ROW_BLOCKED in merged
    assert ROW_NEW in merged
    assert "<<<<<<<" not in merged
    assert junk.read_text(encoding="utf-8").startswith("черновик"), (
        "autostash обязан вернуть незакоммиченную работу человека"
    )
    state = subprocess.run(
        ["git", "status", "--porcelain=2", "--branch"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "rebase" not in state.lower(), "rebase не должен остаться незавершённым"


def test_rebase_refuses_when_the_dirty_file_is_the_backlog_itself(repo_pair):
    """Мёртвая половина: правка в файле, который rebase сам перепишет."""
    repo, _ = repo_pair
    backlog = repo / "ai" / "backlog.md"
    backlog.write_text(
        backlog.read_text(encoding="utf-8") + "\n<!-- ручная правка -->\n", encoding="utf-8"
    )

    assert lifecycle_push._rebase_onto_origin(str(repo), "develop") is False
    assert "<!-- ручная правка -->" in backlog.read_text(encoding="utf-8"), (
        "отказавшись, self-heal не имеет права трогать чужую правку"
    )


def test_rebase_refuses_when_a_local_commit_touches_code(repo_pair):
    """Мёртвая половина: ahead-коммит не только про lifecycle → руками."""
    repo, _ = repo_pair
    (repo / "app.py").write_text("print('code')\n", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-q", "-m", "feat: code commit")

    assert lifecycle_push._rebase_onto_origin(str(repo), "develop") is False
