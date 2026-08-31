# tests/unit/test_check_domain_imports.py
"""Tests for the import-direction gate.

The rule `shared -> infra -> domains -> api` is the oldest architectural rule in
CLAUDE.md and had no machine check until now — `agents/review.md` instructed the
reviewer to run `scripts/check_domain_imports.py`, which did not exist. These
tests exist so the replacement cannot quietly stop working the same way.

ADR-013: no mocks. Real files in tmp_path, real ast parsing.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_domain_imports.py"

sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_domain_imports import check_file, main  # noqa: E402


def make_src(tmp_path: Path, files: dict[str, str]) -> Path:
    """Build a source tree. Keys are paths under src/, values are file bodies."""
    src = tmp_path / "src"
    for rel, body in files.items():
        target = src / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return src


# --- Allowed directions -----------------------------------------------------

ALLOWED = {
    "api_imports_domains": ("api/routes.py", "from domains.billing import charge"),
    "api_imports_infra": ("api/routes.py", "from infra.db import get_db"),
    "api_imports_shared": ("api/routes.py", "from shared.result import Result"),
    "domains_imports_infra": ("domains/billing/service.py", "from infra.db import get_db"),
    "domains_imports_shared": ("domains/billing/service.py", "from shared.result import Result"),
    "infra_imports_shared": ("infra/db.py", "from shared.result import Result"),
    "same_layer_infra": ("infra/db.py", "from infra.cache import get_cache"),
    "same_layer_shared": ("shared/result.py", "from shared.types import T"),
}


@pytest.mark.parametrize("case", sorted(ALLOWED))
def test_allowed_directions_produce_no_violation(tmp_path, case):
    rel, body = ALLOWED[case]
    src = make_src(tmp_path, {rel: body})
    assert check_file(src / rel, src) == []


# --- Forbidden directions ---------------------------------------------------

FORBIDDEN = {
    "shared_imports_infra": ("shared/result.py", "from infra.db import get_db"),
    "shared_imports_domains": ("shared/result.py", "from domains.billing import charge"),
    "shared_imports_api": ("shared/result.py", "from api.routes import router"),
    "infra_imports_domains": ("infra/db.py", "from domains.billing import charge"),
    "infra_imports_api": ("infra/db.py", "from api.routes import router"),
    "domains_imports_api": ("domains/billing/service.py", "from api.routes import router"),
}


@pytest.mark.parametrize("case", sorted(FORBIDDEN))
def test_forbidden_directions_are_caught(tmp_path, case):
    rel, body = FORBIDDEN[case]
    src = make_src(tmp_path, {rel: body})
    violations = check_file(src / rel, src)

    assert len(violations) == 1, f"{case}: expected exactly one violation"
    assert violations[0].check == "IMPORT_DIRECTION"
    assert violations[0].line == 1


# --- Cross-domain -----------------------------------------------------------


def test_cross_domain_import_is_caught(tmp_path):
    src = make_src(
        tmp_path,
        {"domains/billing/service.py": "from domains.users.models import User"},
    )
    violations = check_file(src / "domains/billing/service.py", src)

    assert len(violations) == 1
    assert violations[0].check == "CROSS_DOMAIN"
    assert "billing" in violations[0].message
    assert "users" in violations[0].message


def test_same_domain_import_is_fine(tmp_path):
    src = make_src(
        tmp_path,
        {"domains/billing/service.py": "from domains.billing.models import Invoice"},
    )
    assert check_file(src / "domains/billing/service.py", src) == []


# --- Import spellings -------------------------------------------------------


def test_plain_import_statement_is_checked(tmp_path):
    """`import domains.billing`, not just `from ... import ...`."""
    src = make_src(tmp_path, {"shared/result.py": "import domains.billing"})
    violations = check_file(src / "shared/result.py", src)

    assert len(violations) == 1
    assert violations[0].check == "IMPORT_DIRECTION"


def test_src_prefixed_absolute_import(tmp_path):
    """Projects write both `domains.x` and `src.domains.x`; both must resolve."""
    src = make_src(tmp_path, {"shared/result.py": "from src.domains.billing import charge"})
    violations = check_file(src / "shared/result.py", src)

    assert len(violations) == 1
    assert violations[0].check == "IMPORT_DIRECTION"


def test_relative_import_up_one_level(tmp_path):
    """`from ..users import x` inside domains/billing is a cross-domain import.

    This is why the check parses instead of grepping: the offending layer name
    never appears in the source line.
    """
    src = make_src(tmp_path, {"domains/billing/service.py": "from ..users import models"})
    violations = check_file(src / "domains/billing/service.py", src)

    assert len(violations) == 1
    assert violations[0].check == "CROSS_DOMAIN"


def test_relative_import_within_own_package_is_fine(tmp_path):
    src = make_src(tmp_path, {"domains/billing/service.py": "from .models import Invoice"})
    assert check_file(src / "domains/billing/service.py", src) == []


def test_relative_import_climbing_past_root_is_ignored(tmp_path):
    """Too many dots is a broken import, not a layering violation."""
    src = make_src(tmp_path, {"shared/result.py": "from ...... import something"})
    assert check_file(src / "shared/result.py", src) == []


# --- Things that must NOT be flagged ---------------------------------------


def test_stdlib_and_third_party_imports_ignored(tmp_path):
    src = make_src(
        tmp_path,
        {
            "shared/result.py": (
                "import os\n"
                "import json\n"
                "from pathlib import Path\n"
                "from fastapi import FastAPI\n"
                "from sqlalchemy.orm import Session\n"
            )
        },
    )
    assert check_file(src / "shared/result.py", src) == []


def test_file_outside_the_layered_tree_is_ignored(tmp_path):
    """A module not in a known layer has no direction to violate."""
    src = make_src(tmp_path, {"utils/helpers.py": "from api.routes import router"})
    assert check_file(src / "utils/helpers.py", src) == []


def test_unparseable_file_does_not_raise(tmp_path):
    src = make_src(tmp_path, {"shared/broken.py": "def oops(:\n    pass\n"})
    assert check_file(src / "shared/broken.py", src) == []


def test_missing_file_does_not_raise(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    assert check_file(src / "shared" / "gone.py", src) == []


def test_multiple_violations_in_one_file_all_reported(tmp_path):
    src = make_src(
        tmp_path,
        {
            "shared/result.py": (
                "from infra.db import get_db\n"
                "from domains.billing import charge\n"
                "from api.routes import router\n"
            )
        },
    )
    violations = check_file(src / "shared/result.py", src)

    assert len(violations) == 3
    assert [v.line for v in violations] == [1, 2, 3]


# --- CLI --------------------------------------------------------------------


def run_cli(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_cli_skips_cleanly_when_no_src_directory(tmp_path):
    """This repo has no src/. A gate that fails where it does not apply gets
    switched off everywhere, so 'not applicable' must exit 0."""
    result = run_cli(tmp_path)

    assert result.returncode == 0
    assert "SKIPPED" in result.stdout


def test_cli_passes_on_a_clean_tree(tmp_path):
    make_src(tmp_path, {"domains/billing/service.py": "from shared.result import Result"})
    result = run_cli(tmp_path)

    assert result.returncode == 0, result.stdout
    assert "PASSED" in result.stdout


def test_cli_fails_and_names_the_file(tmp_path):
    make_src(tmp_path, {"shared/result.py": "from api.routes import router"})
    result = run_cli(tmp_path)

    assert result.returncode == 1
    assert "IMPORT CHECK FAILED" in result.stdout
    assert "IMPORT_DIRECTION" in result.stdout
    assert "result.py" in result.stdout


def test_cli_accepts_explicit_file_list(tmp_path):
    make_src(
        tmp_path,
        {
            "shared/bad.py": "from api.routes import router",
            "shared/good.py": "from shared.types import T",
        },
    )
    result = run_cli(tmp_path, "src/shared/good.py")

    assert result.returncode == 0, result.stdout


def test_cli_json_output(tmp_path):
    import json

    make_src(tmp_path, {"shared/result.py": "from api.routes import router"})
    result = run_cli(tmp_path, "--json")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert len(payload["violations"]) == 1
    assert payload["violations"][0]["check"] == "IMPORT_DIRECTION"


def test_cli_custom_src_root(tmp_path):
    app = tmp_path / "app"
    (app / "shared").mkdir(parents=True)
    (app / "shared" / "result.py").write_text("from api.routes import router", encoding="utf-8")

    result = run_cli(tmp_path, "--src", "app")

    assert result.returncode == 1
    assert "IMPORT_DIRECTION" in result.stdout


def test_main_is_importable_and_returns_exit_code(tmp_path, monkeypatch):
    """The reviewer runs this as a script; keep main() usable as a function too."""
    make_src(tmp_path, {"shared/result.py": "from api.routes import router"})
    monkeypatch.chdir(tmp_path)

    assert main([]) == 1
