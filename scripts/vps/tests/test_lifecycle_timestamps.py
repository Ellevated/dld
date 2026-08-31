"""started_at / finished_at в lifecycle — телеметрия времени прогона.

Аудит отказов оркестратора 30.08.2026, причина 4: «нет телеметрии времени».
Вопрос «почему спеки стали дольше» на тех данных ответа не имел — единственный
замер длительности за всю историю был один (TECH-214, 47,5 мин).

Замер по флоту 31.08.2026: из 183 done-спек за две недели **75 без
`started_at`**. Причина не в том, что отметку не пишут, а в том, что её писали
только на переходе `queued|resumed → in_progress`: спека, поднятая из `blocked`
прямо в работу, теряла начало навсегда. Плюс запись `in_progress` при диспатче
best-effort (`dispatch stands` в orchestrator_queue) — её можно просто потерять.

Отдельный файл, а не дописывание в `test_lifecycle.py`: тот уже 827 строк при
лимите 600 и стоит в `loc-limit-baseline.txt`, гейт падает на его росте.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import lifecycle  # noqa: E402


@pytest.fixture()
def tmp_git_repo(tmp_path):
    """Minimal git repo with one initial commit and ai/lifecycle/ dir."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        r = subprocess.run(
            ["git"] + list(args),
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            raise RuntimeError(f"git {args} failed: {r.stderr.strip()}")
        return r.stdout.strip()

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test User")
    lc_dir = repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True)
    (lc_dir / ".gitkeep").write_text("", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "init")
    return repo


def test_started_at_set_on_in_progress_from_blocked(tmp_git_repo):
    """started_at не зависит от того, ОТКУДА вошли в работу.

    Прежний guard принимал только `queued`/`resumed`, и спека, поднятая из
    `blocked`, доезжала до done со `started_at: null`. Длительность прогона
    нельзя измерить по предыдущему состоянию.
    """
    lifecycle.create_initial(tmp_git_repo, "TECH-505", "p1", "tech")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-505", "blocked", reason="needs human")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-505", "in_progress")

    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-505")

    assert data["started_at"] is not None


def test_started_at_is_not_overwritten_by_a_second_run(tmp_git_repo):
    """Начало — первый вход в работу, а не последний: иначе длительность врёт."""
    lifecycle.create_initial(tmp_git_repo, "TECH-506", "p1", "tech")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-506", "in_progress")
    first = lifecycle.read_lifecycle(tmp_git_repo, "TECH-506")["started_at"]
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-506", "blocked", reason="x")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-506", "in_progress")

    assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-506")["started_at"] == first


def test_done_backfills_started_at_from_the_transition_history(tmp_git_repo):
    """Спека, у которой started_at потерялся, всё равно датируется — по истории.

    Время первого перехода в in_progress — настоящее наблюдение, а не
    выдуманная отметка.
    """
    lifecycle.create_initial(tmp_git_repo, "TECH-507", "p1", "tech")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-507", "in_progress")
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-507")
    run_started = next(t["at"] for t in data["transitions"] if t["to"] == "in_progress")

    # Стереть отметку так, как её теряет сбойный диспатч.
    path = Path(tmp_git_repo) / "ai" / "lifecycle" / "TECH-507.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["started_at"] = None
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_git_repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_git_repo), "commit", "-q", "-m", "lifecycle(TECH-507): scrub"],
        check=True,
        env={**os.environ, "LIFECYCLE_WRITE_AUTHORIZED": "1"},
    )

    lifecycle.write_lifecycle(tmp_git_repo, "TECH-507", "done")

    closed = lifecycle.read_lifecycle(tmp_git_repo, "TECH-507")
    assert closed["started_at"] == run_started
    assert closed["finished_at"] is not None


def test_done_without_any_run_leaves_started_at_empty(tmp_git_repo):
    """Нечего досыпать — поле остаётся пустым. Выдуманная отметка хуже пустой."""
    lifecycle.create_initial(tmp_git_repo, "TECH-508", "p1", "tech")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-508", "done")

    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-508")

    assert data["started_at"] is None
    assert data["finished_at"] is not None


def test_bootstrap_as_done_keeps_both_stamps_empty(tmp_git_repo):
    """Архивная спека закончилась когда-то давно, а не «сейчас».

    Её сигнатура (done ∧ transitions=[] ∧ pueue_id=None ∧ finished_at=None) —
    то, по чему lifecycle_recovery отличает bootstrap-артефакт от настоящей
    работы (ADR-026). Проставить finished_at здесь значит и соврать про время,
    и закрыть путь восстановления.
    """
    lifecycle.create_initial(tmp_git_repo, "TECH-509", "p1", "tech", status="done")

    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-509")

    assert data["started_at"] is None
    assert data["finished_at"] is None
    assert data["transitions"] == []
