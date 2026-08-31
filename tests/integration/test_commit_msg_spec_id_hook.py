"""Аудит 30.08.2026, причина 1 — хук commit-msg на реальном `git commit`.

Юнит-тесты хука живут в `test/scripts/commit-msg-spec-id.test.mjs` и проверяют
его логику. Здесь проверяется другое и более важное: что git **вызывает** его.
Ровно на этом стыке гейт и молчал — правило было написано в промптах, а
исполняться было некому.

Сценарии:
  A: subject без spec-id при выставленном CLAUDE_CURRENT_SPEC_PATH — коммит не создан
  B: тот же subject без переменной — коммит проходит (человек коммитит руками)
  C: subject со spec-id — коммит проходит
  D: `.git-hooks/commit-msg` работает из worktree (autopilot живёт именно там)

Без моков (ADR-013): настоящий git, настоящий bash, настоящий node.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GIT_HOOKS_DIR = PROJECT_ROOT / ".git-hooks"
GUARD_MJS = PROJECT_ROOT / ".claude" / "hooks" / "commit-msg-spec-id.mjs"

SPEC_ID = "TECH-189"
SPEC_PATH = f"ai/features/{SPEC_ID}-2026-08-30-slug.md"


def _has_node() -> bool:
    return shutil.which("node") is not None


def _bash() -> str | None:
    """Path to a bash that actually runs, or None.

    Same probe as test_worktree_hook_blocks.py: on Windows `shutil.which` finds
    the WSL relay stub, which resolves and then fails at exec time.
    """
    exe = shutil.which("bash")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "-c", "exit 0"], capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return exe if r.returncode == 0 else None


BASH = _bash()

pytestmark = pytest.mark.skipif(
    not _has_node() or BASH is None,
    reason="commit-msg hook needs real node and a working bash",
)


def _git(repo: Path, *args: str, check: bool = True, env: dict | None = None):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
        # Явная кодировка обязательна: под Windows text=True берёт cp1251 и
        # падает UnicodeDecodeError на первой же кириллице в выводе хука.
        encoding="utf-8",
        errors="replace",
        env={**os.environ, **(env or {})},
    )


def _init_repo(tmp_path: Path) -> Path:
    """Минимальный репозиторий с реальными `.git-hooks/commit-msg` и гардом."""
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")

    hooks_dir = repo / ".git-hooks"
    hooks_dir.mkdir()
    shutil.copy(GIT_HOOKS_DIR / "commit-msg", hooks_dir / "commit-msg")
    (hooks_dir / "commit-msg").chmod(0o755)

    claude_hooks = repo / ".claude" / "hooks"
    claude_hooks.mkdir(parents=True)
    shutil.copy(GUARD_MJS, claude_hooks / "commit-msg-spec-id.mjs")
    (claude_hooks / "commit-msg-spec-id.mjs").chmod(0o755)

    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "config", "core.hooksPath", str(hooks_dir))
    return repo


def _commit(tree: Path, msg: str, env: dict | None = None):
    base_env = {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@test.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@test.com",
        "CLAUDE_CURRENT_SPEC_PATH": "",
        "DLD_SPEC_SUBJECT_UNCHECKED": "",
    }
    base_env.update(env or {})
    return subprocess.run(
        ["git", "-C", str(tree), "commit", "-q", "-m", msg],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, **base_env},
    )


def _stage_change(tree: Path, name: str = "work.txt") -> None:
    (tree / name).write_text("работа\n", encoding="utf-8")
    _git(tree, "add", name)


def _head_subject(tree: Path) -> str:
    return _git(tree, "log", "-1", "--format=%s").stdout.strip()


def test_a_commit_without_spec_id_is_rejected(tmp_path: Path) -> None:
    """Спека выполняется, subject её не объявляет — git не создаёт коммит."""
    repo = _init_repo(tmp_path)
    _stage_change(repo)

    result = _commit(repo, "chore: уборка", env={"CLAUDE_CURRENT_SPEC_PATH": SPEC_PATH})

    assert result.returncode != 0, "хук обязан отбить коммит"
    assert SPEC_ID in result.stderr
    assert _head_subject(repo) == "init", "коммит не должен был появиться"


def test_b_manual_commit_is_untouched(tmp_path: Path) -> None:
    """Без CLAUDE_CURRENT_SPEC_PATH хук не вмешивается в ручную работу."""
    repo = _init_repo(tmp_path)
    _stage_change(repo)

    result = _commit(repo, "chore: уборка")

    assert result.returncode == 0, result.stderr
    assert _head_subject(repo) == "chore: уборка"


def test_c_commit_with_spec_id_passes(tmp_path: Path) -> None:
    """Subject объявляет спеку — гейт реализации такой коммит увидит."""
    repo = _init_repo(tmp_path)
    _stage_change(repo)

    result = _commit(repo, f"feat({SPEC_ID}): работа", env={"CLAUDE_CURRENT_SPEC_PATH": SPEC_PATH})

    assert result.returncode == 0, result.stderr
    assert _head_subject(repo) == f"feat({SPEC_ID}): работа"


def test_d_hook_works_from_a_worktree(tmp_path: Path) -> None:
    """Автопилот коммитит из worktree — там хук обязан работать так же.

    Тот же класс поломки, что TECH-194 C2 у pre-commit: относительный
    core.hooksPath разрешается относительно .git/worktrees/<name>/ и хук
    оказывается мёртв ровно там, где идёт вся работа.
    """
    repo = _init_repo(tmp_path)
    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", str(wt), "-b", f"feature/{SPEC_ID}")
    _stage_change(wt)

    rejected = _commit(wt, "chore: уборка", env={"CLAUDE_CURRENT_SPEC_PATH": SPEC_PATH})
    assert rejected.returncode != 0, "из worktree хук тоже обязан отбивать"

    accepted = _commit(wt, f"fix({SPEC_ID}): работа", env={"CLAUDE_CURRENT_SPEC_PATH": SPEC_PATH})
    assert accepted.returncode == 0, accepted.stderr
    assert _head_subject(wt) == f"fix({SPEC_ID}): работа"
