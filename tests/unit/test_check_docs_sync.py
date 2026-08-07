# tests/unit/test_check_docs_sync.py
"""Tests for the env-var documentation check.

`agents/review.md` instructed the reviewer to run `scripts/check_docs_sync.py`
while no such file existed, so the "Documentation Sync" gate has never actually
run. These tests pin down what it does now, and — as importantly — what it must
not flag, because a noisy gate gets switched off.

ADR-013: no mocks. Real files in tmp_path, real ast parsing, real subprocess.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_docs_sync.py"

sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_docs_sync import documented_vars, env_vars_in  # noqa: E402


def write(tmp_path: Path, rel: str, body: str) -> Path:
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


def run_cli(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )


# --- Detection: every spelling that reads an env var ------------------------

SPELLINGS = {
    "subscript": 'import os\nTOKEN = os.environ["API_TOKEN"]\n',
    "environ_get": 'import os\nTOKEN = os.environ.get("API_TOKEN")\n',
    "getenv": 'import os\nTOKEN = os.getenv("API_TOKEN")\n',
    "getenv_with_default": 'import os\nTOKEN = os.getenv("API_TOKEN", "fallback")\n',
    "from_os_import_environ": 'from os import environ\nTOKEN = environ["API_TOKEN"]\n',
    "from_os_import_environ_get": 'from os import environ\nTOKEN = environ.get("API_TOKEN")\n',
    "from_os_import_getenv": 'from os import getenv\nTOKEN = getenv("API_TOKEN")\n',
}


def test_every_spelling_is_detected(tmp_path):
    for name, body in SPELLINGS.items():
        f = write(tmp_path, f"{name}.py", body)
        found = [var for _, var in env_vars_in(f)]
        assert "API_TOKEN" in found, f"{name}: not detected"


def test_dynamic_key_is_not_guessed(tmp_path):
    """`os.getenv(name)` names nothing we can check; inventing a finding is worse."""
    f = write(tmp_path, "dyn.py", "import os\n\ndef read(name):\n    return os.getenv(name)\n")
    assert env_vars_in(f) == []


def test_line_numbers_are_reported(tmp_path):
    f = write(tmp_path, "multi.py", 'import os\n\nA = os.getenv("ALPHA")\nB = os.getenv("BETA")\n')
    assert sorted(env_vars_in(f)) == [(3, "ALPHA"), (4, "BETA")]


def test_unparseable_file_does_not_raise(tmp_path):
    f = write(tmp_path, "broken.py", "def oops(:\n")
    assert env_vars_in(f) == []


# --- The env template -------------------------------------------------------


def test_documented_vars_parsing(tmp_path):
    env = write(
        tmp_path,
        ".env.example",
        "# comment line\n"
        "API_TOKEN=\n"
        "DATABASE_URL=postgres://localhost/db\n"
        "# OPTIONAL_FLAG=1\n"
        "export EXPORTED_VAR=x\n"
        "\n"
        "not-a-declaration\n",
    )
    names = documented_vars(env)

    assert {"API_TOKEN", "DATABASE_URL", "EXPORTED_VAR"} <= names
    # A commented-out declaration is still documentation — someone wrote it down.
    assert "OPTIONAL_FLAG" in names


# --- CLI --------------------------------------------------------------------


def test_skips_when_no_env_template(tmp_path):
    """Not every project has one. A gate that fails where it does not apply
    gets switched off everywhere."""
    write(tmp_path, "app.py", 'import os\nX = os.getenv("ANYTHING")\n')
    result = run_cli(tmp_path)

    assert result.returncode == 0
    assert "SKIPPED" in result.stdout


def test_passes_when_documented(tmp_path):
    write(tmp_path, ".env.example", "API_TOKEN=\n")
    write(tmp_path, "app.py", 'import os\nX = os.getenv("API_TOKEN")\n')
    result = run_cli(tmp_path)

    assert result.returncode == 0, result.stdout
    assert "PASSED" in result.stdout


def test_fails_and_names_the_variable(tmp_path):
    write(tmp_path, ".env.example", "API_TOKEN=\n")
    write(tmp_path, "app.py", 'import os\nX = os.getenv("SECRET_KEY")\n')
    result = run_cli(tmp_path)

    assert result.returncode == 1
    assert "SECRET_KEY" in result.stdout
    assert "app.py" in result.stdout


def test_ambient_vars_are_not_demanded(tmp_path):
    """PATH and CI are provided by the runtime. Demanding them is noise."""
    write(tmp_path, ".env.example", "API_TOKEN=\n")
    write(
        tmp_path,
        "app.py",
        'import os\nP = os.getenv("PATH")\nC = os.getenv("CI")\nH = os.environ["HOME"]\n',
    )
    result = run_cli(tmp_path)

    assert result.returncode == 0, result.stdout


def test_same_var_twice_in_a_file_is_one_finding(tmp_path):
    write(tmp_path, ".env.example", "OTHER=\n")
    write(
        tmp_path,
        "app.py",
        'import os\nA = os.getenv("SECRET_KEY")\nB = os.environ["SECRET_KEY"]\n',
    )
    result = run_cli(tmp_path, "--json")

    payload = json.loads(result.stdout)
    assert len(payload["undocumented"]) == 1


def test_test_files_are_excluded_from_the_sweep(tmp_path):
    """Tests set throwaway variables; requiring them in .env.example is wrong."""
    write(tmp_path, ".env.example", "API_TOKEN=\n")
    write(tmp_path, "test_thing.py", 'import os\nX = os.getenv("FIXTURE_ONLY")\n')
    result = run_cli(tmp_path)

    assert result.returncode == 0, result.stdout


def test_explicit_file_list_overrides_the_sweep(tmp_path):
    write(tmp_path, ".env.example", "API_TOKEN=\n")
    write(tmp_path, "bad.py", 'import os\nX = os.getenv("MISSING_ONE")\n')
    good = write(tmp_path, "good.py", 'import os\nX = os.getenv("API_TOKEN")\n')

    assert run_cli(tmp_path, str(good)).returncode == 0
    assert run_cli(tmp_path, "bad.py").returncode == 1


def test_alternate_template_name_is_found(tmp_path):
    write(tmp_path, ".env.sample", "API_TOKEN=\n")
    write(tmp_path, "app.py", 'import os\nX = os.getenv("API_TOKEN")\n')
    result = run_cli(tmp_path)

    assert result.returncode == 0, result.stdout
    assert ".env.sample" in result.stdout


def test_explicit_env_flag(tmp_path):
    write(tmp_path, "config/vars.env", "API_TOKEN=\n")
    write(tmp_path, "app.py", 'import os\nX = os.getenv("API_TOKEN")\n')
    result = run_cli(tmp_path, "--env", "config/vars.env")

    assert result.returncode == 0, result.stdout


def test_all_flag_is_accepted(tmp_path):
    """review.md's checklist spells it `check_docs_sync.py --all`."""
    write(tmp_path, ".env.example", "API_TOKEN=\n")
    write(tmp_path, "app.py", 'import os\nX = os.getenv("API_TOKEN")\n')
    result = run_cli(tmp_path, "--all")

    assert result.returncode == 0, result.stdout


def test_missing_env_flag_argument_is_usage_error(tmp_path):
    result = run_cli(tmp_path, "--env")
    assert result.returncode == 2


def test_json_output_shape(tmp_path):
    write(tmp_path, ".env.example", "API_TOKEN=\n")
    write(tmp_path, "app.py", 'import os\nX = os.getenv("SECRET_KEY")\n')
    result = run_cli(tmp_path, "--json")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["undocumented"][0]["var"] == "SECRET_KEY"
    assert payload["undocumented"][0]["line"] == 2
