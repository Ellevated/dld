"""spec_deps: every declared edge — lifecycle `depends_on` ∪ spec header ∪ backlog row.

Regression for 2026-09-23: the dispatcher's briefing read `depends_on` alone and the
built-in gate `depends_on` ∪ backlog, while Spark declares the edge as `**AFTER <ID>**`
in the spec header. dowry BUG-522 (AFTER BUG-521, in progress) was briefed as ready;
awardybot FTR-1531 had already been dispatched before FTR-1530 merged (2026-09-11).

The built-in gate was removed 2026-09-27; its tests went with it. The `declared`
branches it used to cover through `orchestrator_queue._spec_deps` (missing key, bad
shape, legacy backlog edge) moved here, onto `spec_deps.declared` itself.
"""

import logging
import subprocess

import dispatch_summary
import lifecycle
import pytest
import spec_deps


@pytest.fixture()
def repo(tmp_path):
    """Real git repo: read_lifecycle reads HEAD."""

    def git(*args):
        subprocess.run(["git", *args], cwd=str(tmp_path), check=True, capture_output=True)

    git("init", "-b", "develop")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (tmp_path / "ai" / "lifecycle").mkdir(parents=True)
    (tmp_path / "ai" / "lifecycle" / ".gitkeep").write_text("", encoding="utf-8")
    (tmp_path / "ai" / "features").mkdir(parents=True)
    git("add", ".")
    git("commit", "-m", "init")
    return tmp_path


def _spec(repo, name, *header_lines, body_lines=0):
    lines = [f"# Bug Fix: [{name.split('-2026')[0]}] x", "", *header_lines]
    lines += [f"filler {i}" for i in range(body_lines)]
    (repo / "ai" / "features" / f"{name}.md").write_text("\n".join(lines) + "\n", "utf-8")


def _backlog(repo, rows):
    header = "| ID | status | kind | date | desc |\n| --- | --- | --- | --- | --- |\n"
    (repo / "ai" / "backlog.md").write_text(header + "\n".join(rows) + "\n", encoding="utf-8")


def _commit_raw_yaml(repo, spec_id, body):
    """A lifecycle yaml of arbitrary shape — the plumbing writer would never produce it."""
    (repo / "ai" / "lifecycle" / f"{spec_id}.yaml").write_text(body, encoding="utf-8")
    for args in (["add", f"ai/lifecycle/{spec_id}.yaml"], ["commit", "-m", f"raw({spec_id})"]):
        subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


class TestHeaderDeps:
    def test_spark_header_is_an_edge(self, repo):
        _spec(repo, "BUG-522-2026-09-23-x", "**AFTER BUG-521**", "**Priority:** P1")
        assert spec_deps.header_deps(str(repo), "BUG-522") == {"BUG-521"}

    def test_inline_header_and_repo_annotation(self, repo):
        _spec(repo, "FTR-508-2026-09-07-x", "**Priority:** P1 | **AFTER FTR-1511 (AwardyBot)**")
        assert spec_deps.header_deps(str(repo), "FTR-508") == {"FTR-1511"}

    def test_several_edges(self, repo):
        _spec(repo, "BUG-524-2026-09-23-x", "**AFTER BUG-515**", "**AFTER BUG-523**")
        assert spec_deps.header_deps(str(repo), "BUG-524") == {"BUG-515", "BUG-523"}

    def test_only_first_fifteen_lines(self, repo):
        _spec(repo, "FTR-9-2026-01-01-x", body_lines=20)
        path = repo / "ai" / "features" / "FTR-9-2026-01-01-x.md"
        path.write_text(path.read_text("utf-8") + "**AFTER FTR-8**\n", "utf-8")
        assert spec_deps.header_deps(str(repo), "FTR-9") == set()

    def test_lowercase_prose_is_not_a_declaration(self, repo):
        _spec(repo, "FTR-361-2026-07-13-x", "## Status update — after BUG-355 shipped")
        assert spec_deps.header_deps(str(repo), "FTR-361") == set()

    def test_id_prefix_does_not_read_a_longer_id(self, repo):
        _spec(repo, "FTR-435-2026-09-07-x", "**AFTER FTR-426**")
        assert spec_deps.header_deps(str(repo), "FTR-43") == set()
        assert spec_deps.header_deps(str(repo), "FTR-435") == {"FTR-426"}

    def test_no_body_is_empty(self, repo):
        assert spec_deps.header_deps(str(repo), "TECH-1") == set()


class TestDeclared:
    def test_union_of_three_sources(self, repo):
        lifecycle.create_initial(repo, "TECH-519", "p1", "tech", depends_on=["BUG-1"])
        _spec(repo, "TECH-519-2026-09-23-x", "**AFTER BUG-518**")
        _backlog(repo, ["| TECH-519 | queued | tech | 2026-09-23 | x after BUG-2 |"])
        assert spec_deps.declared(str(repo), "TECH-519") == {"BUG-1", "BUG-518", "BUG-2"}

    def test_header_edge_is_logged_with_its_source(self, repo, caplog):
        lifecycle.create_initial(repo, "BUG-522", "p1", "bug")
        _spec(repo, "BUG-522-2026-09-23-x", "**AFTER BUG-521**")
        with caplog.at_level(logging.INFO, logger="orchestrator"):
            assert spec_deps.declared(str(repo), "BUG-522") == {"BUG-521"}
        assert any("deps_via=header" in r.message for r in caplog.records)

    def test_edge_already_in_yaml_is_not_logged(self, repo, caplog):
        lifecycle.create_initial(repo, "BUG-522", "p1", "bug", depends_on=["BUG-521"])
        _spec(repo, "BUG-522-2026-09-23-x", "**AFTER BUG-521**")
        _backlog(repo, ["| BUG-522 | queued | bug | 2026-09-23 | x AFTER BUG-521 |"])
        with caplog.at_level(logging.INFO, logger="orchestrator"):
            assert spec_deps.declared(str(repo), "BUG-522") == {"BUG-521"}
        assert not [r for r in caplog.records if "DEP_VIA" in r.message]

    def test_missing_key_is_empty(self, repo):
        """A record created before TECH-222 has no `depends_on` — no edge, no error."""
        _commit_raw_yaml(repo, "TECH-800", "spec_id: TECH-800\nstatus: queued\n")
        assert spec_deps.declared(str(repo), "TECH-800") == set()

    def test_broken_shape_warns_and_is_ignored(self, repo, caplog):
        """`depends_on` as a string, not a list → WARNING DEP_SHAPE, read as []."""
        _commit_raw_yaml(
            repo, "TECH-801", 'spec_id: TECH-801\nstatus: queued\ndepends_on: "TECH-210"\n'
        )
        with caplog.at_level(logging.WARNING, logger="orchestrator"):
            assert spec_deps.declared(str(repo), "TECH-801") == set()
        assert any("DEP_SHAPE" in r.message for r in caplog.records)

    def test_legacy_backlog_edge_is_read_and_logged(self, repo, caplog):
        """An edge only in the backlog row still counts, and says where it came from."""
        lifecycle.create_initial(repo, "ARCH-209", "p1", "arch")
        _backlog(repo, ["| ARCH-209 | queued | arch | 2026-07-27 | x AFTER TECH-213 |"])
        with caplog.at_level(logging.INFO, logger="orchestrator"):
            assert spec_deps.declared(str(repo), "ARCH-209") == {"TECH-213"}
        assert any("deps_via=backlog" in r.message for r in caplog.records)


class TestBriefingSeesEveryEdge:
    """dispatch_summary is the LLM dispatcher's only input — an edge it omits does not exist."""

    def test_header_dep_in_progress_is_reported(self, repo):
        lifecycle.create_initial(repo, "BUG-521", "p1", "bug", status="in_progress")
        lifecycle.create_initial(repo, "BUG-522", "p1", "bug")
        _spec(repo, "BUG-522-2026-09-23-x", "**AFTER BUG-521**")
        assert dispatch_summary._depends_on(str(repo), "BUG-522") == ["BUG-521=in_progress"]

    def test_backlog_dep_is_reported(self, repo):
        lifecycle.create_initial(repo, "TECH-1244", "p1", "tech")
        lifecycle.create_initial(repo, "ARCH-1246", "p1", "arch")
        _backlog(repo, ["| ARCH-1246 | queued | arch | 2026-06-20 | x AFTER TECH-1244 |"])
        assert dispatch_summary._depends_on(str(repo), "ARCH-1246") == ["TECH-1244=queued"]

    def test_done_dep_is_not_reported_and_foreign_one_is_missing(self, repo):
        lifecycle.create_initial(repo, "FTR-426", "p0", "ftr")
        lifecycle.write_lifecycle(repo, "FTR-426", "done", by="callback")
        lifecycle.create_initial(repo, "FTR-435", "p0", "ftr")
        _spec(repo, "FTR-435-2026-09-07-x", "**AFTER FTR-426**")
        _backlog(repo, ["| FTR-435 | queued | P0 | x after FTR-426, after FTR-1521 (AwardyBot) |"])
        assert dispatch_summary._depends_on(str(repo), "FTR-435") == ["FTR-1521=missing"]

    def test_render_says_waits_on(self, repo):
        lifecycle.create_initial(repo, "BUG-521", "p1", "bug", status="in_progress")
        lifecycle.create_initial(repo, "BUG-522", "p1", "bug")
        _spec(repo, "BUG-522-2026-09-23-x", "**AFTER BUG-521**", "## Allowed Files")
        summary = {
            "slots_free": {},
            "pueue_active": [],
            "recent": [],
            "projects": [
                {
                    "project": "dowry",
                    "live_worktrees": [],
                    "waiting": [
                        {
                            "spec_id": "BUG-522",
                            "status": "queued",
                            "priority": None,
                            "problem": None,
                            "unmet_deps": dispatch_summary._depends_on(str(repo), "BUG-522"),
                        }
                    ],
                }
            ],
        }
        assert "`BUG-522` · queued · waits on BUG-521=in_progress" in dispatch_summary.render(
            summary
        )
