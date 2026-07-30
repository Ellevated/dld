# scripts/vps/tests/test_db.py
"""Unit tests for scripts/vps/db.py.

Covers: seed_projects_from_json, log_task, finish_task, try_acquire_slot,
release_slot, get_available_slots, get_project_state, update_project_phase,
callback CLI mode, save_finding, get_new_findings.
"""

import sqlite3
import sys
from pathlib import Path


VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import db


# --- EC-1: seed_projects upsert idempotency ---


class TestSeedProjects:
    def test_seed_upsert_idempotency(self, isolated_db):
        """EC-1: Seeding same project_id twice updates path, no duplicate row."""
        db.seed_projects_from_json(
            [
                {"project_id": "proj1", "path": "/old/path", "topic_id": 5, "provider": "claude"},
            ]
        )
        db.seed_projects_from_json(
            [
                {"project_id": "proj1", "path": "/new/path", "topic_id": 5, "provider": "claude"},
            ]
        )

        conn = sqlite3.connect(str(isolated_db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM project_state WHERE project_id = 'proj1'").fetchall()
        conn.close()

        assert len(rows) == 1, "Should have exactly 1 row after double-seed"
        assert rows[0]["path"] == "/new/path", "Path should be updated on conflict"

    def test_seed_multiple_projects(self, isolated_db):
        """Seeding multiple projects creates all rows."""
        db.seed_projects_from_json(
            [
                {"project_id": "a", "path": "/a", "topic_id": 1, "provider": "claude"},
                {"project_id": "b", "path": "/b", "topic_id": 2, "provider": "codex"},
            ]
        )
        assert db.get_project_state("a") is not None
        assert db.get_project_state("b") is not None
        assert db.get_project_state("a")["provider"] == "claude"
        assert db.get_project_state("b")["provider"] == "codex"

    def test_seed_preserves_existing_topic_binding_when_json_omits_it(self, isolated_db):
        """Reseed must not erase topic binding if projects.json omits it."""
        db.seed_projects_from_json(
            [
                {"project_id": "proj1", "path": "/old/path", "topic_id": 42, "provider": "claude"},
            ]
        )
        db.seed_projects_from_json(
            [
                {"project_id": "proj1", "path": "/new/path", "provider": "claude"},
            ]
        )

        state = db.get_project_state("proj1")
        assert state is not None
        assert state["path"] == "/new/path"
        assert state["topic_id"] == 42


# --- EC-12: log_task creates DB entry ---


class TestLogTask:
    def test_log_task_creates_entry(self, seed_project):
        """EC-12: log_task creates a row with correct values."""
        row_id = db.log_task(
            project_id="testproject",
            task_label="testproject:inbox-20260312",
            skill="spark",
            status="queued",
            pueue_id=42,
        )
        assert row_id is not None
        assert row_id > 0

        conn = sqlite3.connect(str(Path(db.DB_PATH)))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM task_log WHERE id = ?", (row_id,)).fetchone()
        conn.close()

        assert row["project_id"] == "testproject"
        assert row["task_label"] == "testproject:inbox-20260312"
        assert row["skill"] == "spark"
        assert row["status"] == "queued"
        assert row["pueue_id"] == 42

    def test_finish_task(self, seed_project):
        """finish_task marks the task with status, exit_code, finished_at."""
        row_id = db.log_task("testproject", "label", "spark", "queued", pueue_id=99)
        db.finish_task(pueue_id=99, status="done", exit_code=0, summary="ok")

        conn = sqlite3.connect(str(Path(db.DB_PATH)))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM task_log WHERE id = ?", (row_id,)).fetchone()
        conn.close()

        assert row["status"] == "done"
        assert row["exit_code"] == 0
        assert row["output_summary"] == "ok"
        assert row["finished_at"] is not None


# --- EC-2 + EC-3: try_acquire_slot ---


class TestSlotAcquisition:
    def test_acquire_slot_success(self, seed_project):
        """Acquire a free claude slot returns slot_number."""
        slot = db.try_acquire_slot("testproject", "claude", pueue_id=10)
        assert slot is not None
        assert slot in (1, 2), "Should get one of the two claude slots"

    def test_acquire_slot_no_free_slots(self, seed_project):
        """EC-2: All slots occupied returns None, no crash."""
        # Occupy both claude slots
        db.try_acquire_slot("testproject", "claude", pueue_id=10)
        db.try_acquire_slot("testproject", "claude", pueue_id=11)

        result = db.try_acquire_slot("testproject", "claude", pueue_id=12)
        assert result is None

    def test_acquire_slot_concurrent_one_slot(self, isolated_db):
        """EC-3: Two calls for 1 slot -- exactly one gets it."""
        # Seed project first
        db.seed_projects_from_json(
            [
                {"project_id": "p1", "path": "/p1", "topic_id": 1, "provider": "codex"},
            ]
        )
        # codex has exactly 1 slot (slot_number=3)
        slot_a = db.try_acquire_slot("p1", "codex", pueue_id=20)
        slot_b = db.try_acquire_slot("p1", "codex", pueue_id=21)

        results = [slot_a, slot_b]
        assert results.count(None) == 1, "Exactly one call should get None"
        assert results.count(3) == 1, "Exactly one call should get slot 3"

    def test_release_slot(self, seed_project):
        """release_slot frees the slot, returns project_id."""
        db.try_acquire_slot("testproject", "claude", pueue_id=30)
        project_id = db.release_slot(pueue_id=30)
        assert project_id == "testproject"
        # Slot is free again
        assert db.get_available_slots("claude") == 2

    def test_release_nonexistent_slot(self, seed_project):
        """release_slot with unknown pueue_id returns None."""
        assert db.release_slot(pueue_id=999) is None

    def test_get_available_slots(self, seed_project):
        """get_available_slots counts free slots per provider."""
        assert db.get_available_slots("claude") == 2
        assert db.get_available_slots("codex") == 1
        assert db.get_available_slots("gemini") == 1

        db.try_acquire_slot("testproject", "claude", pueue_id=40)
        assert db.get_available_slots("claude") == 1

    def test_get_provider_capacity_ignores_occupancy(self, seed_project):
        """Capacity says whether a provider EXISTS here, not whether it is free."""
        db.try_acquire_slot("testproject", "codex", pueue_id=41)
        assert db.get_available_slots("codex") == 0
        assert db.get_provider_capacity("codex") == 1

    def test_get_provider_capacity_unknown_provider(self, seed_project):
        """A provider nobody configured — the case that used to stall a spec forever."""
        assert db.get_provider_capacity("openai") == 0


# --- project state + phase ---


class TestProjectState:
    def test_get_project_state(self, seed_project):
        """get_project_state returns dict with all columns."""
        state = db.get_project_state("testproject")
        assert state is not None
        assert state["project_id"] == "testproject"
        assert state["path"] == "/tmp/test-project"
        assert state["topic_id"] == 5
        assert state["phase"] == "idle"

    def test_get_project_state_not_found(self, isolated_db):
        """get_project_state returns None for missing project."""
        assert db.get_project_state("nonexistent") is None

    def test_update_project_phase(self, seed_project):
        """update_project_phase changes phase and current_task."""
        db.update_project_phase("testproject", "processing_inbox", "task-label-1")
        state = db.get_project_state("testproject")
        assert state["phase"] == "processing_inbox"
        assert state["current_task"] == "task-label-1"


# --- Note: callback CLI removed in ARCH-161 (moved to standalone callback.py) ---


# --- TECH-212: CLI contract (night-reviewer.sh calls these 7 times) ---

import json
import os
import subprocess

DB_PY = str(Path(__file__).resolve().parent.parent / "db.py")


def _cli(*args):
    """Run `python3 db.py <args>`.

    DB_PATH is inherited from the isolated_db fixture: monkeypatch.setenv
    writes into os.environ, and subprocess.run() with no explicit `env=`
    inherits the current process's environment, so the child process picks
    up the same isolated DB file.
    """
    return subprocess.run(
        [sys.executable, DB_PY, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=os.environ.copy(),
    )


class TestCliContract:
    def test_no_args_prints_usage_to_stderr_exit_1(self, isolated_db):
        r = _cli()
        assert r.returncode == 1
        assert r.stdout == ""
        assert r.stderr == (
            "Usage: python3 db.py <seed|save-finding|get-new-findings"
            "|update-finding-status|update-phase> [args...]\n"
        )

    def test_unknown_command_prints_usage_exit_1(self, isolated_db):
        r = _cli("nope")
        assert r.returncode == 1
        assert "Usage: python3 db.py <seed|save-finding|get-new-findings" in r.stderr

    def test_update_phase_output_and_effect(self, seed_project):
        r = _cli("update-phase", "testproject", "night_reviewing")
        assert r.returncode == 0
        assert r.stdout == "phase: testproject -> night_reviewing\n"
        assert db.get_project_state("testproject")["phase"] == "night_reviewing"

    def test_update_phase_wrong_argc(self, isolated_db):
        r = _cli("update-phase", "onlyone")
        assert r.returncode == 1
        assert r.stderr == "Usage: python3 db.py update-phase <project_id> <phase>\n"

    def test_save_finding_prints_row_id_then_duplicate(self, seed_project):
        first = _cli(
            "save-finding",
            "testproject",
            "fp1",
            "high",
            "medium",
            "src/a.py",
            "10-12",
            "summary text",
            "suggestion text",
        )
        assert first.returncode == 0
        assert first.stdout.strip().isdigit()

        again = _cli(
            "save-finding",
            "testproject",
            "fp1",
            "high",
            "medium",
            "src/a.py",
            "10-12",
            "summary text",
            "suggestion text",
        )
        assert again.returncode == 0
        assert again.stdout == "duplicate\n"

    def test_save_finding_wrong_argc(self, isolated_db):
        r = _cli("save-finding", "testproject")
        assert r.returncode == 1
        assert r.stderr == (
            "Usage: python3 db.py save-finding <project_id> <fingerprint> <severity>"
            " <confidence> <file_path> <line_range> <summary> <suggestion>\n"
        )

    def test_get_new_findings_emits_parseable_json(self, seed_project):
        """Pins night-reviewer.sh:205-211 — jq reads exactly these 7 keys per row
        (`.id`, `.severity`, `.confidence`, `.file_path`, `.line_range`, `.summary`,
        `.suggestion`), each via `jq -r '.x // ""'`. A dropped/renamed column would
        degrade silently to an empty string with no test failure otherwise.
        """
        _cli(
            "save-finding",
            "testproject",
            "fp2",
            "low",
            "high",
            "src/b.py",
            "1",
            "sum2",
            "sug2",
        )
        r = _cli("get-new-findings", "testproject")
        assert r.returncode == 0
        rows = json.loads(r.stdout)
        assert len(rows) == 1
        row = rows[0]
        assert {
            "id",
            "severity",
            "confidence",
            "file_path",
            "line_range",
            "summary",
            "suggestion",
        } <= row.keys()
        assert row["fingerprint"] == "fp2"
        assert row["status"] == "new"
        # Values round-trip from the save-finding positional args (CLI contract):
        # project_id fingerprint severity confidence file_path line_range summary suggestion
        assert row["severity"] == "low"
        assert row["confidence"] == "high"
        assert row["file_path"] == "src/b.py"
        assert row["line_range"] == "1"
        assert row["summary"] == "sum2"
        assert row["suggestion"] == "sug2"

    def test_get_new_findings_empty_is_bare_json_array(self, seed_project):
        r = _cli("get-new-findings", "testproject")
        assert r.returncode == 0
        assert r.stdout == "[]\n"  # night-reviewer.sh:190 compares against "[]"

    def test_update_finding_status_output(self, seed_project):
        created = _cli(
            "save-finding",
            "testproject",
            "fp3",
            "low",
            "low",
            "src/c.py",
            "3",
            "sum3",
            "sug3",
        )
        fid = created.stdout.strip()
        r = _cli("update-finding-status", fid, "reviewed")
        assert r.returncode == 0
        assert r.stdout == f"updated finding {fid} -> reviewed\n"
        assert _cli("get-new-findings", "testproject").stdout == "[]\n"

    def test_update_finding_status_wrong_argc(self, isolated_db):
        r = _cli("update-finding-status", "1")
        assert r.returncode == 1
        assert r.stderr == "Usage: python3 db.py update-finding-status <finding_id> <status>\n"

    def test_seed_reads_json_file_and_reports_count(self, isolated_db, tmp_path):
        payload = tmp_path / "projects.json"
        payload.write_text(
            json.dumps([{"project_id": "p9", "path": "/p9", "provider": "claude"}]),
            encoding="utf-8",
        )
        r = _cli("seed", str(payload))
        assert r.returncode == 0
        assert r.stdout == "seeded 1 projects\n"
        assert db.get_project_state("p9")["path"] == "/p9"

    def test_seed_wrong_argc(self, isolated_db):
        r = _cli("seed")
        assert r.returncode == 1
        assert r.stderr == "Usage: python3 db.py seed <path/to/projects.json>\n"


class TestNightReviewerInlineLookup:
    """Pins night-reviewer.sh:89-95's inline `python3 -c` project lookup — the
    8th call site into db.py that the CLI-only TestCliContract suite misses.
    On failure it logs "project not found or no path" and returns with no
    non-zero exit anywhere, so the night review is skipped silently.
    """

    def test_get_project_state_path_lookup(self, seed_project):
        r = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys; sys.path.insert(0, {VPS_DIR!r}); import db; "
                "print(db.get_project_state('testproject')['path'])",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=os.environ.copy(),
        )
        assert r.returncode == 0
        assert r.stdout.strip() == "/tmp/test-project"


# --- TECH-212: structural contract of the split ---

import ast
import io
import re
import tokenize

import pytest

VPS = Path(VPS_DIR)
LEAF_MODULES = ["db_decisions.py", "db_findings.py", "db_cli.py"]

# EC-1: every name a consumer resolves through `db.` (26 names — connection/slots/
# projects/tasklog that stayed in db.py, plus the delegates to db_decisions/db_findings).
PUBLIC_SURFACE = [
    "get_db",
    "try_acquire_slot",
    "release_slot",
    "get_project_state",
    "get_all_projects",
    "update_project_phase",
    "log_task",
    "finish_task",
    "get_available_slots",
    "get_provider_capacity",
    "get_occupied_slots",
    "get_task_by_pueue_id",
    "seed_projects_from_json",
    "record_decision",
    "count_demotes_since",
    "clear_decisions",
    "log_sdk_post_result_error",
    "log_gate_cycle",
    "get_gate_health",
    "log_classifier_refusal",
    "save_finding",
    "get_new_findings",
    "update_finding_status",
    "get_finding_by_id",
    "get_all_findings",
    "get_projects_for_night_scan",
]


class TestSplitContract:
    def test_public_surface_intact_and_callable(self):
        """EC-1: every name the five consumers bind is present on `db` and callable."""
        assert len(PUBLIC_SURFACE) == 26
        missing = [n for n in PUBLIC_SURFACE if not hasattr(db, n)]
        assert missing == [], f"db lost public names: {missing}"
        not_callable = [n for n in PUBLIC_SURFACE if not callable(getattr(db, n))]
        assert not_callable == [], f"db names became non-callable: {not_callable}"

    def test_from_db_import_get_db_still_works(self):
        """EC-2: orchestrator_monitor.py:95 binds the name, not the module."""
        from db import get_db  # noqa: PLC0415

        assert callable(get_db)

    @pytest.mark.parametrize("name", LEAF_MODULES)
    def test_new_modules_are_leaves(self, name):
        """EC-3: a cycle here would give `python3 db.py` two module objects.

        Walks the AST instead of grepping the source, so a sibling leaf importing
        another leaf by name (e.g. `import db_findings`) can never false-positive
        against an actual `import db` / `from db import ...`.
        """
        tree = ast.parse((VPS / name).read_text(encoding="utf-8"), filename=name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "db", f"{name} does `import db`"
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "db", f"{name} does `from db import ...`"

    @pytest.mark.parametrize("name", ["db.py", *LEAF_MODULES])
    def test_under_loc_limit(self, name):
        """EC-4 + EC-5: 400 LOC is the reason this task exists."""
        loc = len((VPS / name).read_text(encoding="utf-8").splitlines())
        assert loc <= 400, f"{name} is {loc} LOC"

    def test_ensure_migrations_defined_once(self):
        """EC-6: schema init has exactly one home across scripts/vps/*.py."""
        defs = [
            p.name
            for p in VPS.glob("*.py")
            if re.search(r"^def _ensure_migrations", p.read_text(encoding="utf-8"), re.M)
        ]
        assert defs == ["db.py"], f"_ensure_migrations defined in {defs}"

    @pytest.mark.parametrize("name", LEAF_MODULES)
    def test_sql_stays_parameterized(self, name):
        """EC-7 / ADR-017: no SQL verb ever sits inside an f-string's own literal text.

        `ast.JoinedStr` is not enough here: adjacent string-literal concatenation
        (`"SELECT ... " f"AND ... {x}"`) merges into ONE JoinedStr node, so an
        ast.Constant walk would see the plain "SELECT ..." literal as if it were
        f-string content and false-positive on exactly the legitimate case this
        test must tolerate — db_findings.get_projects_for_night_scan builds its
        query as a plain string ("SELECT ...") concatenated with an f-string that
        interpolates only the `?,?,?` placeholder list.

        `tokenize` distinguishes them at the token-stream level: FSTRING_MIDDLE
        tokens are exactly the literal text inside the f-string's own quotes,
        never the adjacent plain STRING token. That isolates the placeholder-list
        f-string ("AND project_id IN (...)", no SQL verb) from a hypothetical
        `f"SELECT * FROM t WHERE id = {x}"` (verb sits in an FSTRING_MIDDLE token).

        Keywords are matched with `\\b` word boundaries: db_cli's
        `f"updated finding {argv[2]} -> {argv[3]}"` (a plain print statement,
        no SQL at all) contains "UPDATED", a substring match on "UPDATE" would
        false-positive there.
        """
        source = (VPS / name).read_text(encoding="utf-8")
        sql_keyword_patterns = [
            re.compile(rf"\b{kw}\b") for kw in ("SELECT", "INSERT", "UPDATE", "DELETE")
        ]
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in tokens:
            if tok.type != tokenize.FSTRING_MIDDLE:
                continue
            upper = tok.string.upper()
            for pattern in sql_keyword_patterns:
                assert not pattern.search(upper), (
                    f"{name}: f-string literal segment contains SQL keyword "
                    f"{pattern.pattern!r}: {tok.string!r}"
                )
        assert "% (" not in source, f"{name}: %-style SQL interpolation found"


class TestDelegatedBehaviourRoundtrip:
    """EC-10: prove the delegates actually commit through the PUBLIC `db.*` seam.

    A delegate that handed over a context-manager instead of a connection would
    silently not commit — these roundtrips would fail at the read-back step.
    """

    def test_record_decision_and_count_window(self, seed_project):
        for i in range(4):
            db.record_decision("testproject", f"TECH-{i}", "demote", "no_impl", demoted=True)
        assert db.count_demotes_since(10) == 4
        assert db.clear_decisions(10) == 4
        assert db.count_demotes_since(10) == 0

    def test_findings_lifecycle_through_delegates(self, seed_project):
        fid = db.save_finding(
            "testproject", "fp-contract", "high", "high", "src/x.py", "1-2", "sum", "sug"
        )
        assert fid is not None
        new = db.get_new_findings("testproject")
        assert any(f["id"] == fid and f["status"] == "new" for f in new)
        db.update_finding_status(fid, "reviewed")
        new_after = db.get_new_findings("testproject")
        assert all(f["id"] != fid for f in new_after)

    def test_classifier_refusal_roundtrip(self, seed_project, isolated_db):
        """The refusal counter has to survive the delegate, or the signal is lost.

        A classifier decline is an HTTP 200, so this row is the only place a
        refused security review is ever counted.
        """
        import sqlite3

        row_id = db.log_classifier_refusal(
            project_id="testproject",
            task="/autopilot TECH-1",
            skill="autopilot",
            model="claude-opus-5",
            category="cyber",
            declines=2,
            fallbacks_served=1,
            unrecovered=1,
            exit_code=4,
            detail='[{"source": "AssistantMessage"}]',
        )
        assert row_id > 0

        conn = sqlite3.connect(str(isolated_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM classifier_refusals WHERE id = ?", (row_id,)).fetchone()
        conn.close()
        assert row["project_id"] == "testproject"
        assert row["category"] == "cyber"
        assert row["declines"] == 2
        assert row["fallbacks_served"] == 1
        assert row["unrecovered"] == 1
        assert row["exit_code"] == 4
        assert row["ts"]

    def test_classifier_refusals_table_created_by_migration(self, isolated_db, monkeypatch):
        """A pre-existing VPS database has no such table — _ensure_migrations adds it.

        The fixture applies schema.sql, so drop the table first to simulate a
        deployed DB created before this change, then force migrations to re-run.
        """
        import sqlite3

        conn = sqlite3.connect(str(isolated_db))
        conn.execute("DROP TABLE IF EXISTS classifier_refusals")
        conn.commit()
        conn.close()

        monkeypatch.setattr(db, "_MIGRATIONS_APPLIED", False)
        db.log_classifier_refusal(
            project_id="p",
            task="t",
            skill=None,
            model=None,
            category=None,
            declines=1,
            fallbacks_served=0,
            unrecovered=1,
            exit_code=4,
            detail=None,
        )
        conn = sqlite3.connect(str(isolated_db))
        cnt = conn.execute("SELECT COUNT(*) FROM classifier_refusals").fetchone()[0]
        conn.close()
        assert cnt == 1


class TestMigrationTable:
    """`_ensure_migrations` is a loop over `_MIGRATIONS` — lock what that must do.

    The hand-written version was four near-identical try/except blocks and had
    grown db.py to 391 of its 400 permitted LOC. Folding it into data must not
    change what a deployed database ends up with, so these assert the outcome
    rather than the shape.
    """

    def _bare_db(self, tmp_path):
        """A database old enough to predate every migration below."""
        import sqlite3

        p = tmp_path / "bare.db"
        conn = sqlite3.connect(str(p))
        conn.execute("CREATE TABLE task_log (id INTEGER PRIMARY KEY, pueue_id INTEGER)")
        conn.commit()
        conn.close()
        return p

    def _objects(self, path):
        import sqlite3

        conn = sqlite3.connect(str(path))
        rows = {(r[0], r[1]) for r in conn.execute("SELECT type, name FROM sqlite_master")}
        conn.close()
        return rows

    def test_every_step_lands_on_a_legacy_db(self, tmp_path, monkeypatch):
        import sqlite3

        p = self._bare_db(tmp_path)
        monkeypatch.setattr(db, "_MIGRATIONS_APPLIED", False)
        conn = sqlite3.connect(str(p))
        db._ensure_migrations(conn)
        conn.commit()
        conn.close()

        objects = self._objects(p)
        for table in (
            "callback_decisions",
            "sdk_post_result_errors",
            "gate_health",
            "classifier_refusals",
        ):
            assert ("table", table) in objects, f"{table} not created"
        for index in (
            "idx_callback_decisions_ts",
            "idx_callback_decisions_demoted_ts",
            "idx_sdk_post_result_errors_ts",
            "idx_gate_health_ts",
            "idx_classifier_refusals_ts",
        ):
            assert ("index", index) in objects, f"{index} not created"

    def test_branch_column_still_added(self, tmp_path, monkeypatch):
        """TECH-170: the ALTER has no IF NOT EXISTS and stays hand-written."""
        import sqlite3

        p = self._bare_db(tmp_path)
        monkeypatch.setattr(db, "_MIGRATIONS_APPLIED", False)
        conn = sqlite3.connect(str(p))
        db._ensure_migrations(conn)
        conn.commit()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(task_log)").fetchall()}
        conn.close()
        assert "branch" in cols

    def test_rerun_is_idempotent(self, tmp_path, monkeypatch):
        import sqlite3

        p = self._bare_db(tmp_path)
        conn = sqlite3.connect(str(p))
        for _ in range(3):
            monkeypatch.setattr(db, "_MIGRATIONS_APPLIED", False)
            db._ensure_migrations(conn)
        conn.commit()
        conn.close()
        assert ("table", "gate_health") in self._objects(p)

    def test_a_failing_step_does_not_abort_the_later_ones(self, tmp_path, monkeypatch):
        """Per-step try/except, as before: one broken step must not cost the rest.

        Simulated by wedging a step that raises OperationalError in front of the
        real list — a lock table would be the production cause.
        """
        import sqlite3

        p = self._bare_db(tmp_path)
        monkeypatch.setattr(
            db,
            "_MIGRATIONS",
            (("CREATE TABLE this is not valid sql",), *db._MIGRATIONS),
        )
        monkeypatch.setattr(db, "_MIGRATIONS_APPLIED", False)
        conn = sqlite3.connect(str(p))
        db._ensure_migrations(conn)  # must not raise
        conn.commit()
        conn.close()
        assert ("table", "classifier_refusals") in self._objects(p)

    def test_a_step_lands_whole_or_not_at_all(self, tmp_path, monkeypatch):
        """Table and its indexes share one try/except — same grouping as before."""
        import sqlite3

        p = self._bare_db(tmp_path)
        monkeypatch.setattr(
            db,
            "_MIGRATIONS",
            (
                (
                    "CREATE TABLE IF NOT EXISTS partial_step (id INTEGER)",
                    "CREATE INDEX IF NOT EXISTS bad_idx ON no_such_table(nope)",
                    "CREATE TABLE IF NOT EXISTS never_reached (id INTEGER)",
                ),
            ),
        )
        monkeypatch.setattr(db, "_MIGRATIONS_APPLIED", False)
        conn = sqlite3.connect(str(p))
        db._ensure_migrations(conn)
        conn.commit()
        conn.close()
        objects = self._objects(p)
        assert ("table", "partial_step") in objects
        assert ("table", "never_reached") not in objects
