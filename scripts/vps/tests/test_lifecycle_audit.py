"""TECH-211 — характеризационные тесты lifecycle_audit.audit_project.

Написаны ДО раскола файла и НЕ правятся ПОСЛЕ (Feathers characterization).
Любое расхождение после Task 3 = регрессия поведения, а не «тест устарел».
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import lifecycle  # noqa: E402
import lifecycle_audit  # noqa: E402


@pytest.fixture()
def repo(tmp_path):
    """Реальный git-репозиторий (приём из test_orchestrator_bootstrap.py:150)."""
    r = tmp_path / "repo"
    r.mkdir()

    def git(*args):
        subprocess.run(["git"] + list(args), cwd=str(r), check=True,
                       capture_output=True, text=True)

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test User")
    # Repo-local config beats a hostile global (e.g. showUntrackedFiles=all,
    # commit.gpgsign=true) so the golden literals below stay valid on any
    # machine (TECH-211 review finding 1).
    git("config", "status.showUntrackedFiles", "normal")
    git("config", "commit.gpgsign", "false")
    (r / "ai" / "lifecycle").mkdir(parents=True)
    (r / "ai" / "lifecycle" / ".gitkeep").write_text("", encoding="utf-8")
    (r / "ai" / "features").mkdir(parents=True, exist_ok=True)
    git("add", ".")
    git("commit", "-m", "init")
    return r


def _of(findings, category):
    return [f for f in findings if f["category"] == category]


def _git(repo_path, *args):
    return subprocess.run(["git"] + list(args), cwd=str(repo_path), check=True,
                          capture_output=True, text=True).stdout.strip()


# ──────────────────────────────────────────────────────────────────────
# One test per category (EC-1) — asserts category AND spec_id AND detail
# ──────────────────────────────────────────────────────────────────────


def test_category_orphan_spec_md(repo):
    spec = repo / "ai" / "features" / "TECH-666-x.md"
    spec.write_text("# TECH-666\n**Status:** queued\n", encoding="utf-8")
    hits = _of(lifecycle_audit.audit_project(str(repo)), "orphan_spec_md")
    assert [(h["spec_id"], h["detail"]) for h in hits] == [
        ("TECH-666", "TECH-666-x.md")
    ]


def test_category_orphan_yaml(repo):
    lifecycle.create_initial(repo, "TECH-555", "p1", "tech")
    hits = _of(lifecycle_audit.audit_project(str(repo)), "orphan_yaml")
    assert [(h["spec_id"], h["detail"]) for h in hits] == [("TECH-555", "no md")]


def test_category_missing_from_backlog(repo):
    lifecycle.create_initial(repo, "TECH-556", "p1", "tech")
    hits = _of(lifecycle_audit.audit_project(str(repo)), "missing_from_backlog")
    assert [(h["spec_id"], h["detail"]) for h in hits] == [("TECH-556", "no row")]


def test_category_bootstrap_as_done(repo):
    lifecycle.create_initial(repo, "TECH-1082", "p2", "tech", status="done")
    hits = _of(lifecycle_audit.audit_project(str(repo)), "bootstrap_as_done")
    assert [(h["spec_id"], h["detail"]) for h in hits] == [
        ("TECH-1082", "status=done, no transitions, no pueue_id, no finished_at")
    ]


def test_category_markdown_status_mismatch(repo):
    lifecycle.create_initial(repo, "TECH-557", "p1", "tech", status="queued")
    spec = repo / "ai" / "features" / "TECH-557-x.md"
    spec.write_text("# TECH-557\n**Status:** done\n", encoding="utf-8")
    hits = _of(lifecycle_audit.audit_project(str(repo)), "markdown_status_mismatch")
    assert [(h["spec_id"], h["detail"]) for h in hits] == [
        ("TECH-557", "md=done yaml=queued")
    ]


def test_category_backlog_status_mismatch(repo):
    lifecycle.create_initial(repo, "TECH-558", "p1", "tech", status="queued")
    (repo / "ai" / "backlog.md").write_text(
        "| ID | status |\n|---|---|\n| TECH-558 | done |\n", encoding="utf-8"
    )
    hits = _of(lifecycle_audit.audit_project(str(repo)), "backlog_status_mismatch")
    assert [(h["spec_id"], h["detail"]) for h in hits] == [
        ("TECH-558", "backlog=done yaml=queued")
    ]


def test_category_backlog_format_unparsed(repo):
    (repo / "ai" / "backlog.md").write_text(
        "| ID | description |\n|---|---|\n"
        "| TECH-559 | this row has nothing parseable as status |\n",
        encoding="utf-8",
    )
    hits = _of(lifecycle_audit.audit_project(str(repo)), "backlog_format_unparsed")
    assert [(h["spec_id"], h["detail"]) for h in hits] == [
        ("TECH-559", "row found but status not extracted")
    ]


def test_category_wt_lifecycle_dirty(repo):
    (repo / "ai" / "lifecycle" / "DIRTY.yaml").write_text("x: 1\n", encoding="utf-8")
    hits = _of(lifecycle_audit.audit_project(str(repo)), "wt_lifecycle_dirty")
    assert len(hits) == 1
    assert hits[0]["spec_id"] == "-"
    assert "DIRTY.yaml" in hits[0]["detail"]


def test_category_wt_features_dirty(repo):
    (repo / "ai" / "features" / "TECH-700-x.md").write_text("# TECH-700\n", encoding="utf-8")
    hits = _of(lifecycle_audit.audit_project(str(repo)), "wt_features_dirty")
    # ai/features/ itself is untracked (no .gitkeep committed at init) → porcelain
    # reports the whole directory, not the individual filename inside it.
    assert [(h["spec_id"], h["detail"]) for h in hits] == [("-", "?? ai/features/")]


def test_category_unauthorized_writer(repo):
    target = repo / "ai" / "lifecycle" / "TECH-777.yaml"
    target.write_text(
        "spec_id: TECH-777\n"
        "status: in_progress\n"
        "priority: p1\n"
        "kind: tech\n"
        "blocked_reason: null\n"
        "started_at: null\n"
        "finished_at: null\n"
        "allowed_files_hash: null\n"
        "updated_at: '2026-05-26T10:00:00Z'\n"
        "updated_by: spark\n"
        "version: 1\n"
        "pueue_id: null\n"
        "transitions:\n"
        "  - {from: queued, to: in_progress, at: '2026-05-26T10:00:00Z', by: spark, pueue_id: null}\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "ai/lifecycle/TECH-777.yaml"], cwd=str(repo), check=True,
                   capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "test: inject unauthorized writer"], cwd=str(repo),
                   check=True, capture_output=True, text=True)
    hits = _of(lifecycle_audit.audit_project(str(repo)), "unauthorized_writer")
    assert [(h["spec_id"], h["detail"]) for h in hits] == [
        ("TECH-777", "by=['spark']")
    ]


def test_category_git_divergence(repo):
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "README.md").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo), check=True,
                   capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "second"], cwd=str(repo), check=True,
                   capture_output=True, text=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/develop", base], cwd=str(repo),
                   check=True, capture_output=True, text=True)

    hits = _of(lifecycle_audit.audit_project(str(repo)), "git_divergence")
    assert [(h["spec_id"], h["detail"]) for h in hits] == [("-", "ahead=1 behind=0")]


def test_category_push_failures_counter(repo):
    (repo / "ai" / ".lifecycle-push-failures").write_text("7", encoding="utf-8")
    hits = _of(lifecycle_audit.audit_project(str(repo)), "push_failures_counter")
    assert [(h["spec_id"], h["detail"]) for h in hits] == [("-", "count=7")]


def test_category_bootstrap_anomaly(repo):
    (repo / "ai" / ".bootstrap-anomaly-count").write_text("1", encoding="utf-8")
    hits = _of(lifecycle_audit.audit_project(str(repo)), "bootstrap_anomaly")
    assert [(h["spec_id"], h["detail"]) for h in hits] == [("-", "count=1")]


def test_category_bootstrap_unparsable(repo):
    (repo / "ai" / ".bootstrap-unparsable-count").write_text("3", encoding="utf-8")
    hits = _of(lifecycle_audit.audit_project(str(repo)), "bootstrap_unparsable")
    assert [(h["spec_id"], h["detail"]) for h in hits] == [("-", "count=3")]


# ──────────────────────────────────────────────────────────────────────
# Golden snapshot — all 14 categories fire in one repo (EC-5)
# ──────────────────────────────────────────────────────────────────────


def test_all_fourteen_categories_golden(repo):
    # orphan_spec_md
    (repo / "ai" / "features" / "TECH-666-x.md").write_text(
        "# TECH-666\n**Status:** queued\n", encoding="utf-8"
    )
    # orphan_yaml
    lifecycle.create_initial(repo, "TECH-555", "p1", "tech")
    # bootstrap_as_done
    lifecycle.create_initial(repo, "TECH-1082", "p2", "tech", status="done")
    # markdown_status_mismatch (+ missing_from_backlog for same sid)
    lifecycle.create_initial(repo, "TECH-557", "p1", "tech", status="queued")
    (repo / "ai" / "features" / "TECH-557-x.md").write_text(
        "# TECH-557\n**Status:** done\n", encoding="utf-8"
    )
    # backlog_status_mismatch
    lifecycle.create_initial(repo, "TECH-558", "p1", "tech", status="queued")
    (repo / "ai" / "features" / "TECH-558-x.md").write_text(
        "# TECH-558\n", encoding="utf-8"
    )
    # backlog: TECH-558 mismatched status, TECH-559 unparsed row
    (repo / "ai" / "backlog.md").write_text(
        "| ID | status |\n|---|---|\n"
        "| TECH-558 | done |\n"
        "| TECH-559 | this row has nothing parseable as status |\n",
        encoding="utf-8",
    )
    # unauthorized_writer
    target = repo / "ai" / "lifecycle" / "TECH-777.yaml"
    target.write_text(
        "spec_id: TECH-777\n"
        "status: in_progress\n"
        "priority: p1\n"
        "kind: tech\n"
        "blocked_reason: null\n"
        "started_at: null\n"
        "finished_at: null\n"
        "allowed_files_hash: null\n"
        "updated_at: '2026-05-26T10:00:00Z'\n"
        "updated_by: spark\n"
        "version: 1\n"
        "pueue_id: null\n"
        "transitions:\n"
        "  - {from: queued, to: in_progress, at: '2026-05-26T10:00:00Z', by: spark, pueue_id: null}\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "ai/lifecycle/TECH-777.yaml"], cwd=str(repo), check=True,
                   capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "test: inject unauthorized writer"], cwd=str(repo),
                   check=True, capture_output=True, text=True)

    # counters
    (repo / "ai" / ".lifecycle-push-failures").write_text("7", encoding="utf-8")
    (repo / "ai" / ".bootstrap-anomaly-count").write_text("1", encoding="utf-8")
    (repo / "ai" / ".bootstrap-unparsable-count").write_text("3", encoding="utf-8")

    # git_divergence
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "README.md").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo), check=True,
                   capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "second"], cwd=str(repo), check=True,
                   capture_output=True, text=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/develop", base], cwd=str(repo),
                   check=True, capture_output=True, text=True)

    # wt_lifecycle_dirty / wt_features_dirty — uncommitted, added last so they
    # do not interfere with the other categories' commits above.
    (repo / "ai" / "lifecycle" / "DIRTY.yaml").write_text("x: 1\n", encoding="utf-8")
    (repo / "ai" / "features" / "TECH-700-x.md").write_text("# TECH-700\n", encoding="utf-8")

    actual = [(f["category"], f["spec_id"], f["detail"])
              for f in lifecycle_audit.audit_project(str(repo))]

    # EXPECTED recorded by running the CURRENT, unmodified lifecycle_audit.py
    # against this exact repo setup (Feathers characterization — not invented).
    EXPECTED = [
        ("orphan_spec_md", "TECH-666", "TECH-666-x.md"),
        ("orphan_spec_md", "TECH-700", "TECH-700-x.md"),
        ("orphan_yaml", "TECH-1082", "no md"),
        ("orphan_yaml", "TECH-555", "no md"),
        ("orphan_yaml", "TECH-777", "no md"),
        ("missing_from_backlog", "TECH-1082", "no row"),
        ("missing_from_backlog", "TECH-555", "no row"),
        ("missing_from_backlog", "TECH-557", "no row"),
        ("missing_from_backlog", "TECH-777", "no row"),
        ("bootstrap_as_done", "TECH-1082", "status=done, no transitions, no pueue_id, no finished_at"),
        ("markdown_status_mismatch", "TECH-557", "md=done yaml=queued"),
        ("backlog_status_mismatch", "TECH-558", "backlog=done yaml=queued"),
        ("backlog_format_unparsed", "TECH-559", "row found but status not extracted"),
        ("wt_lifecycle_dirty", "-", "?? ai/lifecycle/DIRTY.yaml"),
        ("wt_features_dirty", "-", "?? ai/features/"),
        ("unauthorized_writer", "TECH-777", "by=['spark']"),
        ("git_divergence", "-", "ahead=1 behind=0"),
        ("push_failures_counter", "-", "count=7"),
        ("bootstrap_anomaly", "-", "count=1"),
        ("bootstrap_unparsable", "-", "count=3"),
    ]
    assert actual == EXPECTED


# ──────────────────────────────────────────────────────────────────────
# Module surface guard — test_orchestrator_bootstrap.py:513-519 imports
# ──────────────────────────────────────────────────────────────────────


def test_module_surface_stays_importable():
    """test_orchestrator_bootstrap.py:513-519 импортирует эти 4 имени из lifecycle_audit.

    Файл вне Allowed Files — раскол не смеет убрать ни одно из них.
    """
    for name in ("CATEGORIES", "_parse_backlog_columns", "audit_project", "run"):
        assert hasattr(lifecycle_audit, name), name
    assert len(lifecycle_audit.CATEGORIES) == 14


# ──────────────────────────────────────────────────────────────────────
# CLI surface (run())
# ──────────────────────────────────────────────────────────────────────


def test_run_json_shape(repo, tmp_path, capsys):
    lifecycle.create_initial(repo, "TECH-1082", "p2", "tech", status="done")
    pj = tmp_path / "projects.json"
    pj.write_text(json.dumps([{"project_id": "tmp", "path": str(repo)}]), encoding="utf-8")
    rc = lifecycle_audit.run(
        project_filter=None, projects_json=str(pj), json_output=True,
        category_filter=None, quiet=False,
    )
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] >= 1
    assert payload["projects"][0]["project_id"] == "tmp"


def test_run_quiet_shape(repo, tmp_path, capsys):
    pj = tmp_path / "projects.json"
    pj.write_text(json.dumps([{"project_id": "tmp", "path": str(repo)}]), encoding="utf-8")
    rc = lifecycle_audit.run(
        project_filter=None, projects_json=str(pj), json_output=False,
        category_filter=None, quiet=True,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "tmp: 0" in out
    assert "TOTAL: 0" in out


def test_run_text_shape(repo, tmp_path, capsys):
    pj = tmp_path / "projects.json"
    pj.write_text(json.dumps([{"project_id": "tmp", "path": str(repo)}]), encoding="utf-8")
    rc = lifecycle_audit.run(
        project_filter=None, projects_json=str(pj), json_output=False,
        category_filter=None, quiet=False,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "=== lifecycle_audit ===" in out
    assert "Total findings:" in out


def test_run_unknown_category_rc2(tmp_path):
    pj = tmp_path / "projects.json"
    pj.write_text("[]", encoding="utf-8")
    rc = lifecycle_audit.run(
        project_filter=None, projects_json=str(pj), json_output=False,
        category_filter="not_a_real_category", quiet=False,
    )
    assert rc == 2


def test_main_cli_rejects_bad_category():
    """Pins the argparse CLI surface in lifecycle_audit.main() (finding 5).

    main() stays in lifecycle_audit.py after the TECH-211 split; this pins
    that --category is still wired through to run()'s validation without
    needing a real projects.json (the check runs before project loading).
    """
    assert lifecycle_audit.main(["--category", "not_a_real_category"]) == 2


# ──────────────────────────────────────────────────────────────────────
# READ-ONLY contract (EC-7)
# ──────────────────────────────────────────────────────────────────────


def test_audit_writes_nothing(repo):
    """Аудитор не смеет менять ни git-состояние, ни файлы."""
    def porcelain():
        return subprocess.run(["git", "status", "--porcelain"], cwd=str(repo),
                              capture_output=True, text=True).stdout

    lifecycle.create_initial(repo, "TECH-1082", "p2", "tech", status="done")
    (repo / "ai" / ".bootstrap-anomaly-count").write_text("1", encoding="utf-8")
    before_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo),
                                 capture_output=True, text=True).stdout
    before = porcelain()
    lifecycle_audit.audit_project(str(repo))
    assert porcelain() == before
    assert subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo),
                          capture_output=True, text=True).stdout == before_head
