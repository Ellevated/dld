# scripts/vps/tests/test_check_loc_limit.py
"""The LOC gate must fail on new debt and on stale permission, not just print.

A size limit that lives only in `.claude/rules/architecture.md` is a request. Four files
grew past it anyway — callback.py to 1438 lines, orchestrator.py to 1078, db.py to 602,
claude-runner.py to 912 — and each cost a spec of its own to cut back (TECH-212, TECH-215,
TECH-216, TECH-213). `check-loc-limit.sh` is the version of that rule that runs.

Three behaviours are worth a test, and all three have a way of quietly not working:
  1. a NEW file over the limit fails the gate
  2. a file listed in the baseline does NOT fail — the debt register is honoured
  3. a baselined file that came back under the limit ALSO fails — a stale entry is
     standing permission for the next regression to hide behind

ADR-013: no mocks. Real files in a tmp tree, real `bash`, real exit codes.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

VPS_DIR = Path(__file__).resolve().parent.parent
SCRIPT = VPS_DIR / "check-loc-limit.sh"


def _bash() -> str | None:
    """A bash that can run a Windows-path script.

    `shutil.which("bash")` on a Windows host finds WSL's stub first, and that one
    answers every invocation with `execvpe(/bin/bash) failed` — a failure that reads
    like a broken script rather than a wrong interpreter. Git Bash is the one the repo
    is developed against, so prefer it explicitly and let $BASH override.
    """
    from_env = os.environ.get("BASH")
    if from_env and Path(from_env).exists():
        return from_env
    for candidate in (
        r"C:\Program Files\Gitinash.exe",
        r"C:\Program Files (x86)\Gitinash.exe",
    ):
        if Path(candidate).exists():
            return candidate
    found = shutil.which("bash")
    if found and "system32" in found.lower():  # WSL stub
        return None
    return found


BASH = _bash()

pytestmark = pytest.mark.skipif(BASH is None, reason="no usable bash on this host")


def write_lines(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"# line {i}\n" for i in range(count)), encoding="utf-8")


def run(tree: Path, baseline: Path | None = None, **env_extra) -> subprocess.CompletedProcess:
    # Inherit the real environment: on Windows a bash started with a hand-built env
    # loses SYSTEMROOT/TEMP and dies with "invalid file descriptor" on its first
    # process substitution — a failure that looks like a bug in the script under test.
    env = dict(os.environ)
    if baseline is not None:
        env["LOC_LIMIT_BASELINE"] = str(baseline)
    env.update({k: str(v) for k, v in env_extra.items()})
    return subprocess.run(
        [BASH, str(SCRIPT), str(tree)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_clean_tree_passes(tmp_path):
    write_lines(tmp_path / "small.py", 10)
    empty_baseline = tmp_path / "baseline.txt"
    empty_baseline.write_text("# nothing baselined\n", encoding="utf-8")

    result = run(tmp_path, empty_baseline)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "LOC limit OK" in result.stdout


def test_new_file_over_the_limit_fails(tmp_path):
    write_lines(tmp_path / "fat.py", 401)
    empty_baseline = tmp_path / "baseline.txt"
    empty_baseline.write_text("", encoding="utf-8")

    result = run(tmp_path, empty_baseline)

    assert result.returncode == 1, result.stdout
    assert "fat.py" in result.stdout
    assert "new" in result.stdout


def test_tests_get_the_larger_ceiling(tmp_path):
    """600 for tests, 400 for code — a 500-line suite is fine, a 500-line module is not."""
    write_lines(tmp_path / "tests" / "test_big.py", 500)
    write_lines(tmp_path / "module.py", 500)
    empty_baseline = tmp_path / "baseline.txt"
    empty_baseline.write_text("", encoding="utf-8")

    result = run(tmp_path, empty_baseline)

    assert result.returncode == 1
    assert "module.py" in result.stdout
    assert "test_big.py" not in result.stdout


def test_baselined_file_is_allowed_to_stay_over(tmp_path):
    fat = tmp_path / "legacy.py"
    write_lines(fat, 700)
    baseline = tmp_path / "baseline.txt"
    # The gate strips the repo root from the path it reports; with an explicit tree
    # argument outside the repo the relative form is the absolute one.
    baseline.write_text(f"{fat} 700\n", encoding="utf-8")

    result = run(tmp_path, baseline)

    assert result.returncode == 0, result.stdout + result.stderr


def test_baselined_file_that_grew_fails(tmp_path):
    fat = tmp_path / "legacy.py"
    write_lines(fat, 750)
    baseline = tmp_path / "baseline.txt"
    baseline.write_text(f"{fat} 700\n", encoding="utf-8")

    result = run(tmp_path, baseline)

    assert result.returncode == 1, result.stdout
    assert "grew past its baseline" in result.stdout


def test_stale_baseline_entry_fails(tmp_path):
    """A file back under the limit must lose its baseline line, or it shields the next one."""
    slim = tmp_path / "legacy.py"
    write_lines(slim, 100)
    baseline = tmp_path / "baseline.txt"
    baseline.write_text(f"{slim} 700\n", encoding="utf-8")

    result = run(tmp_path, baseline)

    assert result.returncode == 1, result.stdout
    assert "Stale baseline" in result.stdout


def test_repo_tree_is_clean_against_its_own_baseline():
    """The live check: scripts/vps as it stands must pass with the committed baseline."""
    result = subprocess.run([BASH, str(SCRIPT)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
