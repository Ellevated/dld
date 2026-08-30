"""
Unit tests for scripts/vps/lifecycle.py.

Tests 1, 2 (concurrent + private index) run unconditionally.
Test 3 (BUG-185 regression) is now active — Task 3 complete, autostash removed.

Note: read_lifecycle and list_by_status read from HEAD (git object store), so
      working tree sync is not needed for read operations.
      assert_clean_lifecycle_tree checks working tree — tests that exercise
      dirty-WT detection write files to WT directly.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make scripts/vps importable
VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import lifecycle  # noqa: E402
import lifecycle_cas  # noqa: E402
import lifecycle_git  # noqa: E402
import lifecycle_push  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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

    # Create ai/lifecycle/ with a .gitkeep so HEAD exists
    lc_dir = repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True)
    (lc_dir / ".gitkeep").write_text("", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "init")

    return repo


# ---------------------------------------------------------------------------
# Test 1 (spec line 601): atomic write under concurrency
# ---------------------------------------------------------------------------


def test_concurrent_writes_no_loss(tmp_git_repo):
    """10 parallel write_lifecycle() for different specs — all land in HEAD."""
    import concurrent.futures as cf

    def write_one(i):
        lifecycle.write_lifecycle(tmp_git_repo, f"TECH-{i}", "queued")

    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(write_one, i) for i in range(10)]
        for f in futures:
            f.result()  # propagate any exceptions

    for i in range(10):
        data = lifecycle.read_lifecycle(tmp_git_repo, f"TECH-{i}")
        assert data is not None, f"TECH-{i} missing from HEAD"
        assert data["status"] == "queued"
        assert data["version"] >= 1


def test_concurrent_commit_during_write_not_reverted(tmp_git_repo):
    """TOCTOU regression (FTR-1270 wipe, fd9455f): a commit landing on the branch
    DURING a lifecycle write must NOT be silently reverted.

    test_concurrent_writes_no_loss above only exercises the in-process
    _write_lock (10 threads, one process — serialized). It cannot catch THIS
    bug, which is a cross-process race: the OLD code read HEAD twice
    (read-tree HEAD ... later rev-parse HEAD). A commit landing between the two
    reads produced a tree snapshotted off the OLD HEAD but parented on the NEW
    HEAD; the CAS only guards parent==branch, so it passed and committed a stale
    tree that DROPPED the concurrent commit's files (data loss). Pinning HEAD
    once makes the CAS fail on a moved HEAD → _cas_loop retries → no loss.

    Injection point: the first `git write-tree`, which in BOTH old and new code
    runs after the tree snapshot is taken. With the fix the retry picks up
    concurrent.txt; without it the file vanishes from HEAD.
    """
    real_run = lifecycle_git._run
    state = {"injected": False}

    def injecting_run(cmd, **kwargs):
        if not state["injected"] and cmd[:2] == ["git", "write-tree"]:
            state["injected"] = True
            # Simulate a parallel process advancing the branch mid-write.
            (tmp_git_repo / "concurrent.txt").write_text("from a parallel writer", encoding="utf-8")
            subprocess.run(["git", "add", "concurrent.txt"], cwd=str(tmp_git_repo), check=True)
            subprocess.run(
                ["git", "commit", "-m", "concurrent commit during lifecycle write"],
                cwd=str(tmp_git_repo),
                check=True,
                capture_output=True,
            )
        return real_run(cmd, **kwargs)

    with patch.object(lifecycle_git, "_run", injecting_run):
        lifecycle.write_lifecycle(tmp_git_repo, "TECH-700", "queued")

    # 1) The lifecycle write itself landed.
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-700")
    assert data is not None and data["status"] == "queued"

    # 2) The concurrent commit's file is STILL in HEAD — not reverted (the bug).
    r = subprocess.run(
        ["git", "cat-file", "-e", "HEAD:concurrent.txt"],
        cwd=str(tmp_git_repo),
        capture_output=True,
    )
    assert r.returncode == 0, "concurrent.txt was silently reverted — TOCTOU regression"


# ---------------------------------------------------------------------------
# Test 2 (spec line 618): private GIT_INDEX_FILE — operator-staged files don't leak
# ---------------------------------------------------------------------------


def test_operator_staged_file_does_not_leak(tmp_git_repo):
    """Operator does git add some-other-file. Callback writes lifecycle.
    Commit contains ONLY lifecycle, not some-other-file."""
    wip = tmp_git_repo / "operator-wip.txt"
    wip.write_text("wip", encoding="utf-8")
    subprocess.run(["git", "add", "operator-wip.txt"], cwd=str(tmp_git_repo), check=True)

    lifecycle.write_lifecycle(tmp_git_repo, "TECH-100", "done")

    # Last commit should only contain the lifecycle yaml
    r = subprocess.run(
        ["git", "show", "--name-only", "--format=", "HEAD"],
        cwd=str(tmp_git_repo),
        capture_output=True,
        text=True,
    )
    changed_files = r.stdout.strip()
    assert "ai/lifecycle/TECH-100.yaml" in changed_files
    assert "operator-wip.txt" not in changed_files

    # operator-wip.txt still staged, not lost
    r2 = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=str(tmp_git_repo),
        capture_output=True,
        text=True,
    )
    assert "operator-wip.txt" in r2.stdout


# ---------------------------------------------------------------------------
# Test 3 (spec line 633, BUG-185 regression): skipped pending Task 3
# ---------------------------------------------------------------------------


def test_dirty_wt_does_not_revert_callback_write(tmp_git_repo):
    """Simulate BUG-185: dirty WT + callback write. Lifecycle.yaml in HEAD
    remains 'done' even after next scan."""
    import orchestrator  # noqa: E402

    lifecycle.create_initial(tmp_git_repo, "TECH-200", "p1", "tech")
    (tmp_git_repo / "ai" / "qa").mkdir(parents=True, exist_ok=True)
    (tmp_git_repo / "ai" / "qa" / "garbage.md").write_text("untracked", encoding="utf-8")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-200", "done")

    # Orchestrator next cycle: ff-only pull is a no-op when up-to-date.
    # No autostash dance — ARCH-186 removed the stash path entirely.
    with patch("orchestrator.subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        orchestrator.git_pull("test", str(tmp_git_repo))

    queued = lifecycle.list_by_status(tmp_git_repo, "queued")
    assert "TECH-200" not in [s["spec_id"] for s in queued]


# ---------------------------------------------------------------------------
# Additional unit tests
# ---------------------------------------------------------------------------


def test_create_initial_then_read(tmp_git_repo):
    """Round-trip: create_initial → read_lifecycle returns correct data."""
    lifecycle.create_initial(tmp_git_repo, "TECH-501", "p0", "ftr")
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-501")
    assert data is not None
    assert data["spec_id"] == "TECH-501"
    assert data["status"] == "queued"
    assert data["priority"] == "p0"
    assert data["kind"] == "ftr"
    assert data["version"] == 1
    assert data["transitions"] == []


def test_create_initial_writes_depends_on(tmp_git_repo):
    """EC-5: create_initial(..., depends_on=[...]) lands depends_on in HEAD."""
    lifecycle.create_initial(tmp_git_repo, "TECH-505", "p1", "tech", depends_on=["TECH-220"])
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-505")
    assert data["depends_on"] == ["TECH-220"]
    assert data["status"] == "queued"


def test_create_initial_without_depends_on_defaults_empty(tmp_git_repo):
    """EC-6: back-compat for existing callers (bootstrap, migrate) that don't
    pass depends_on — defaults to [] and other fields are unaffected."""
    lifecycle.create_initial(tmp_git_repo, "TECH-506", "p1", "tech")
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-506")
    assert data["depends_on"] == []
    assert data["spec_id"] == "TECH-506"
    assert data["status"] == "queued"
    assert data["priority"] == "p1"
    assert data["kind"] == "tech"


def test_write_lifecycle_fills_depends_on_on_legacy_yaml(tmp_git_repo):
    """EC-4: a lifecycle yaml committed before depends_on existed has no key at
    all. write_lifecycle (update branch) must not crash and must leave
    depends_on == [] — same effective behavior as today's absent backlog line."""
    lc_dir = tmp_git_repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True, exist_ok=True)
    (lc_dir / "TECH-600.yaml").write_text(
        "spec_id: TECH-600\nstatus: queued\npriority: p1\nkind: tech\n"
        "blocked_reason: null\nstarted_at: null\nfinished_at: null\n"
        "allowed_files_hash: null\nupdated_at: '2026-01-01T00:00:00Z'\n"
        "updated_by: migration\nversion: 1\npueue_id: null\ntransitions: []\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "ai/lifecycle/TECH-600.yaml"], cwd=str(tmp_git_repo), check=True)
    subprocess.run(
        ["git", "commit", "-m", "pre-migration lifecycle yaml"],
        cwd=str(tmp_git_repo),
        check=True,
        capture_output=True,
    )

    lifecycle.write_lifecycle(tmp_git_repo, "TECH-600", "in_progress")

    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-600")
    assert data["depends_on"] == []
    assert data["status"] == "in_progress"


def test_version_monotonic(tmp_git_repo):
    """Two writes must increment version each time."""
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-502", "queued")
    d1 = lifecycle.read_lifecycle(tmp_git_repo, "TECH-502")
    assert d1["version"] == 1

    lifecycle.write_lifecycle(tmp_git_repo, "TECH-502", "in_progress")
    d2 = lifecycle.read_lifecycle(tmp_git_repo, "TECH-502")
    assert d2["version"] == 2
    assert d2["status"] == "in_progress"


def test_started_at_set_on_in_progress(tmp_git_repo):
    """started_at should be set when transitioning queued→in_progress."""
    lifecycle.create_initial(tmp_git_repo, "TECH-503", "p1", "tech")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-503", "in_progress")
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-503")
    assert data["started_at"] is not None


def test_finished_at_set_on_done(tmp_git_repo):
    """finished_at should be set when transitioning to done."""
    lifecycle.create_initial(tmp_git_repo, "TECH-504", "p1", "tech")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-504", "in_progress")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-504", "done")
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-504")
    assert data["finished_at"] is not None
    assert data["status"] == "done"


def test_list_by_status_filters(tmp_git_repo):
    """Write 3 specs with mixed statuses, list_by_status filters correctly."""
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-510", "queued")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-511", "in_progress")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-512", "done")

    queued = lifecycle.list_by_status(tmp_git_repo, "queued")
    spec_ids = [d["spec_id"] for d in queued]
    assert "TECH-510" in spec_ids
    assert "TECH-511" not in spec_ids
    assert "TECH-512" not in spec_ids

    # Multi-status filter
    active = lifecycle.list_by_status(tmp_git_repo, {"queued", "in_progress"})
    active_ids = [d["spec_id"] for d in active]
    assert "TECH-510" in active_ids
    assert "TECH-511" in active_ids
    assert "TECH-512" not in active_ids


def test_assert_clean_lifecycle_tree_raises_on_dirty(tmp_git_repo):
    """Manually writing a lifecycle yaml without committing → raises RuntimeError."""
    lc_dir = tmp_git_repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True, exist_ok=True)
    (lc_dir / "TECH-520.yaml").write_text("spec_id: TECH-520\nstatus: queued\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Dirty lifecycle"):
        lifecycle.assert_clean_lifecycle_tree(tmp_git_repo)


def test_assert_clean_lifecycle_tree_passes_when_clean(tmp_git_repo):
    """assert_clean_lifecycle_tree passes when lifecycle/ WT matches HEAD."""
    lifecycle.create_initial(tmp_git_repo, "TECH-521", "p2", "bug")
    # Plumbing write adds the file to HEAD but NOT to WT.
    # In production the orchestrator calls git pull to sync WT.
    # Here we simulate that sync explicitly:
    subprocess.run(
        ["git", "checkout", "HEAD", "--", "ai/lifecycle/"],
        cwd=str(tmp_git_repo),
        check=True,
    )
    lifecycle.assert_clean_lifecycle_tree(tmp_git_repo)  # should not raise


def test_reconcile_orphans_demotes_in_progress(tmp_git_repo):
    """write in_progress with pueue_id=999, pass empty alive set → reconciled."""
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-530", "in_progress", pueue_id=999)

    reconciled = lifecycle.reconcile_orphans(tmp_git_repo, pueue_alive_ids=set())
    assert "TECH-530" in reconciled

    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-530")
    assert data["status"] == "queued"
    assert data.get("blocked_reason") == "orphaned from crash"
    # TECH-189 Task 9: reconcile_orphans is called by orchestrator (startup_reconcile),
    # not callback — the transition `by` must reflect the true source for accurate
    # post-incident forensics.
    last_transition = data["transitions"][-1]
    assert last_transition["by"] == "orchestrator"
    assert last_transition["to"] == "queued"


def test_reconcile_orphans_skips_alive_tasks(tmp_git_repo):
    """pueue_id=888 is alive — should not be reconciled."""
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-531", "in_progress", pueue_id=888)

    reconciled = lifecycle.reconcile_orphans(tmp_git_repo, pueue_alive_ids={888})
    assert "TECH-531" not in reconciled


def test_read_lifecycle_returns_none_for_missing(tmp_git_repo):
    """read_lifecycle returns None for a spec that doesn't exist."""
    result = lifecycle.read_lifecycle(tmp_git_repo, "TECH-NONEXISTENT")
    assert result is None


def test_blocked_reason_stored(tmp_git_repo):
    """write_lifecycle with reason= stores it as blocked_reason."""
    lifecycle.create_initial(tmp_git_repo, "TECH-540", "p1", "tech")
    lifecycle.write_lifecycle(
        tmp_git_repo,
        "TECH-540",
        "blocked",
        reason="no implementation commits",
    )
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-540")
    assert data["status"] == "blocked"
    assert data["blocked_reason"] == "no implementation commits"


def test_push_best_effort_warns_on_failure(tmp_git_repo, caplog):
    """TECH-189 Task 5: push failures log WARNING (not DEBUG) and bump counter.

    Silent DEBUG masked multi-machine convergence failures. WARNING surfaces
    them in orchestrator logs; counter file enables external monitoring.
    """
    import logging

    fail = subprocess.CompletedProcess(
        args=["git", "push"], returncode=1, stdout="", stderr="No such remote 'origin'"
    )
    with patch.object(lifecycle_git, "_run", return_value=fail):
        with caplog.at_level(logging.WARNING, logger="lifecycle_push"):
            lifecycle_push._push_best_effort(str(tmp_git_repo), "develop")

    assert any("lifecycle push failed" in r.message for r in caplog.records)
    counter = Path(tmp_git_repo) / "ai" / ".lifecycle-push-failures"
    assert counter.is_file()
    assert counter.read_text(encoding="utf-8").strip() == "1"

    # Second failure increments
    with patch.object(lifecycle_git, "_run", return_value=fail):
        lifecycle_push._push_best_effort(str(tmp_git_repo), "develop")
    assert counter.read_text(encoding="utf-8").strip() == "2"


def test_cas_loop_treats_timeout_as_retry(tmp_git_repo):
    """TECH-189 Task 7: TimeoutExpired from _run is caught in _cas_loop.

    Guarantee: a hung git subprocess does NOT hold _write_lock indefinitely.
    The retry loop catches subprocess.TimeoutExpired, logs WARNING, and
    proceeds to the next attempt (eventually raising LifecycleWriteRaceError
    after MAX_CAS_RETRIES, never propagating TimeoutExpired to caller).
    """
    lifecycle.create_initial(tmp_git_repo, "TECH-560", "p1", "tech")
    # Patch _atomic_write to raise TimeoutExpired on every call.
    with patch.object(
        lifecycle_cas,
        "_atomic_write",
        side_effect=subprocess.TimeoutExpired(cmd=["git", "write-tree"], timeout=30),
    ):
        with pytest.raises(lifecycle.LifecycleWriteRaceError):
            lifecycle.write_lifecycle(tmp_git_repo, "TECH-560", "in_progress")
    # Lock must be released (next call succeeds — real write, no patch).
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-560", "in_progress")
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-560")
    assert data["status"] == "in_progress"


def test_backlog_fold_survives_the_split(tmp_git_repo, caplog):
    """_atomic_write imports render_backlog lazily and swallows any failure.

    After the split that import crosses a module boundary; a breakage would only
    surface as a WARNING nobody reads. Assert the fold actually happened.
    """
    import logging

    backlog = tmp_git_repo / "ai" / "backlog.md"
    backlog.write_text(
        "| ID | Status | Kind | Updated | Spec |\n"
        "|----|--------|------|---------|------|\n"
        "| TECH-777 | queued | tech | 2026-07-28 | x |\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "ai/backlog.md"], cwd=str(tmp_git_repo), check=True)
    subprocess.run(
        ["git", "commit", "-m", "seed backlog"],
        cwd=str(tmp_git_repo),
        check=True,
        capture_output=True,
    )

    with caplog.at_level(logging.WARNING, logger="lifecycle_cas"):
        lifecycle.write_lifecycle(tmp_git_repo, "TECH-777", "done", by="callback")

    assert not [r for r in caplog.records if "backlog sync skipped" in r.message]
    head = subprocess.run(
        ["git", "show", "HEAD:ai/backlog.md"],
        cwd=str(tmp_git_repo),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "| TECH-777 | done |" in head


def test_run_has_default_timeout(tmp_git_repo):
    """TECH-189 Task 7: _run() includes timeout=30 by default.

    Smoke check: calling _run with a fast command does NOT raise TimeoutExpired
    (would fail if timeout were e.g. 0). The default value is asserted via
    function signature introspection to guard against accidental removal.
    """
    import inspect

    sig = inspect.signature(lifecycle_git._run)
    assert sig.parameters["timeout"].default == 30


def test_transitions_list_grows(tmp_git_repo):
    """Each write appends to transitions list."""
    lifecycle.create_initial(tmp_git_repo, "TECH-550", "p1", "tech")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-550", "in_progress")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-550", "done")

    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-550")
    # create_initial doesn't add transition; 2 writes add 2 transitions
    assert len(data["transitions"]) == 2
    assert data["transitions"][0]["from"] == "queued"
    assert data["transitions"][0]["to"] == "in_progress"
    assert data["transitions"][1]["from"] == "in_progress"
    assert data["transitions"][1]["to"] == "done"


# ---------------------------------------------------------------------------
# Test CR-9: spec-first ID collision retry via multiprocessing CAS race
# ---------------------------------------------------------------------------


def _worker_create_initial(repo_dir: str, spec_id: str, barrier, result_queue) -> None:
    """Worker function for multiprocessing CAS race test.

    Waits at barrier so both processes start create_initial simultaneously,
    then reports success or exception type to the result_queue.
    """
    import sys
    from pathlib import Path

    vps_dir = str(Path(__file__).resolve().parent.parent)
    if vps_dir not in sys.path:
        sys.path.insert(0, vps_dir)
    import lifecycle as lc

    barrier.wait()  # synchronize start
    try:
        lc.create_initial(repo_dir, spec_id, priority="P1", kind="ARCH", by="spark")
        result_queue.put(("success", None))
    except lc.LifecycleWriteRaceError as exc:
        result_queue.put(("race_error", str(exc)))
    except Exception as exc:
        result_queue.put(("other_error", f"{type(exc).__name__}: {exc}"))


def test_create_initial_cas_collision_retry(tmp_git_repo):
    """CR-9: Two concurrent create_initial calls for same ID via separate processes.

    One caller wins the CAS race (update-ref succeeds), the other exhausts
    MAX_CAS_RETRIES and raises LifecycleWriteRaceError.

    Uses multiprocessing (not threading) to bypass the in-process _write_lock
    that serializes writes within a single Python process. Cross-process CAS
    is protected only by git update-ref — the real guard being tested here.
    """
    import multiprocessing as mp

    spec_id = "ARCH-999"
    repo_dir = str(tmp_git_repo)

    # Use a Barrier so both processes hit create_initial at the same moment.
    barrier = mp.Barrier(2)
    result_queue = mp.Queue()

    p1 = mp.Process(
        target=_worker_create_initial,
        args=(repo_dir, spec_id, barrier, result_queue),
    )
    p2 = mp.Process(
        target=_worker_create_initial,
        args=(repo_dir, spec_id, barrier, result_queue),
    )

    p1.start()
    p2.start()
    p1.join(timeout=30)
    p2.join(timeout=30)

    assert not p1.is_alive(), "Process 1 hung (timeout)"
    assert not p2.is_alive(), "Process 2 hung (timeout)"

    results = []
    while not result_queue.empty():
        results.append(result_queue.get_nowait())

    assert len(results) == 2, f"Expected 2 results from workers, got {len(results)}: {results}"

    outcomes = [r[0] for r in results]
    # Exactly one success and one race_error — or both success if git CAS
    # serialized perfectly (both commits landed on different HEAD SHAs).
    # The invariant we must enforce: ARCH-999.yaml appears exactly ONCE in HEAD.
    head_files = subprocess.check_output(
        ["git", "ls-tree", "HEAD:ai/lifecycle/"],
        cwd=repo_dir,
        text=True,
    )
    arch_999_count = head_files.count("ARCH-999.yaml")
    assert arch_999_count == 1, (
        f"Expected exactly 1 ARCH-999.yaml in HEAD, got {arch_999_count}. Outcomes: {outcomes}"
    )

    # At least one worker must have succeeded (i.e. no both-fail scenario).
    assert "success" in outcomes, f"No worker succeeded: {results}"

    # If one got a race error, confirm it's the expected type.
    for outcome, detail in results:
        assert outcome in ("success", "race_error"), f"Unexpected outcome {outcome!r}: {detail}"


# ---------------------------------------------------------------------------
# ADR-027: _ALLOWED_WRITERS security invariant tests
# ---------------------------------------------------------------------------


def test_allowed_writers_for_create_spark_isolation():
    """ADR-027: spark in _ALLOWED_WRITERS_FOR_CREATE but NOT in _ALLOWED_WRITERS.
    This ensures spark can claim IDs via create_initial but cannot mutate status.
    """
    assert "spark" in lifecycle._ALLOWED_WRITERS_FOR_CREATE
    assert "spark" not in lifecycle._ALLOWED_WRITERS
    assert "autopilot" not in lifecycle._ALLOWED_WRITERS_FOR_CREATE
    assert "autopilot" not in lifecycle._ALLOWED_WRITERS


def test_create_initial_rejects_disallowed_writer(tmp_git_repo):
    """create_initial must reject by='autopilot' — autopilot is not in _ALLOWED_WRITERS_FOR_CREATE."""
    with pytest.raises(ValueError, match="invalid by='autopilot'"):
        lifecycle.create_initial(
            tmp_git_repo, "TECH-901", priority="P1", kind="TECH", by="autopilot"
        )


def test_create_initial_respects_rule7(tmp_git_repo):
    """Rule 7: create_initial raises LifecycleAlreadyDoneError on a done lifecycle (ADR-025)."""
    lifecycle.create_initial(tmp_git_repo, "TECH-902", priority="P1", kind="TECH")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-902", "in_progress", by="callback")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-902", "done", by="callback")

    with pytest.raises(lifecycle.LifecycleAlreadyDoneError):
        lifecycle.create_initial(tmp_git_repo, "TECH-902", priority="P1", kind="TECH", by="spark")


def test_create_initial_spark_rejects_non_queued(tmp_git_repo):
    """Spark may only create status='queued': council decisions happen in Spark
    Phase 4 before the spec exists, so a spark-born blocked spec (e.g.
    'council_required' pre-implementation gate) is a process violation."""
    for status in ("blocked", "done", "in_progress"):
        with pytest.raises(ValueError, match="by='spark' may only create status='queued'"):
            lifecycle.create_initial(
                tmp_git_repo,
                "TECH-903",
                priority="P1",
                kind="TECH",
                status=status,
                by="spark",
            )

    # queued still works, and orchestrator keeps its status override (ADR-026 bootstrap-as-done)
    lifecycle.create_initial(tmp_git_repo, "TECH-903", priority="P1", kind="TECH", by="spark")
    assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-903")["status"] == "queued"
    lifecycle.create_initial(
        tmp_git_repo,
        "TECH-904",
        priority="P1",
        kind="TECH",
        status="done",
        by="orchestrator",
    )
    assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-904")["status"] == "done"


# ---------------------------------------------------------------------------
# recover_false_reconciliation — the second narrow Rule 7 escape (2026-07-27)
#
# Reopens specs the reconciliation gate closed against their own birth commit
# (`lifecycle(BUG-460): queued`). Must refuse anything that looks like real work.
# ---------------------------------------------------------------------------


def _git(repo, *args):
    r = subprocess.run(
        ["git"] + list(args), cwd=str(repo), capture_output=True, text=True, check=False
    )
    if r.returncode != 0:
        raise RuntimeError(f"git {args} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def _make_false_reconciled(repo, spec_id, *, subject, extra_file=None):
    """Create the on-disk shape of a falsely-reconciled spec, return the cited sha."""
    lifecycle.create_initial(repo, spec_id, priority="p1", kind="tech", by="spark")
    if extra_file:
        target = repo / extra_file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x = 1\n", encoding="utf-8")
        _git(repo, "add", extra_file)
    else:
        _git(repo, "add", f"ai/lifecycle/{spec_id}.yaml")
    _git(repo, "commit", "--allow-empty", "-m", subject)
    sha = _git(repo, "rev-parse", "HEAD")
    lifecycle.write_lifecycle(
        repo,
        spec_id,
        "done",
        by="orchestrator",
        reason=f"already_implemented_on_develop:{sha[:12]}",
    )
    return sha


def test_recovers_spec_closed_by_its_own_birth_commit(tmp_git_repo):
    _make_false_reconciled(tmp_git_repo, "BUG-460", subject="lifecycle(BUG-460): queued")
    assert lifecycle.read_lifecycle(tmp_git_repo, "BUG-460")["status"] == "done"

    lifecycle.recover_false_reconciliation(
        tmp_git_repo, "BUG-460", reason="false reconciliation, gate bug 2026-07-27"
    )
    after = lifecycle.read_lifecycle(tmp_git_repo, "BUG-460")
    assert after["status"] == "queued"
    assert after["pueue_id"] is None


def test_refuses_when_cited_commit_is_real_work(tmp_git_repo):
    """The guard that makes this safe: a real implementation commit stays done."""
    _make_false_reconciled(
        tmp_git_repo,
        "BUG-461",
        subject="fix(BUG-461): escape first_name",
        extra_file="src/copy.py",
    )
    with pytest.raises(lifecycle.NotFalseReconciliationError) as exc:
        lifecycle.recover_false_reconciliation(tmp_git_repo, "BUG-461", reason="attempt")
    assert exc.value.criterion == "cited_commit_is_real_work"
    assert lifecycle.read_lifecycle(tmp_git_repo, "BUG-461")["status"] == "done"


def test_refuses_a_spec_that_actually_ran(tmp_git_repo):
    """pueue_id set = it was dispatched; Rule 7 keeps protecting it."""
    lifecycle.create_initial(tmp_git_repo, "TECH-9", priority="p1", kind="tech", by="spark")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-9", "in_progress", by="orchestrator", pueue_id=42)
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-9", "done", by="callback")
    with pytest.raises(lifecycle.NotFalseReconciliationError):
        lifecycle.recover_false_reconciliation(tmp_git_repo, "TECH-9", reason="attempt")
    assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-9")["status"] == "done"


def test_rejects_unknown_writer_identity(tmp_git_repo):
    _make_false_reconciled(tmp_git_repo, "BUG-462", subject="lifecycle(BUG-462): queued")
    with pytest.raises(ValueError):
        lifecycle.recover_false_reconciliation(tmp_git_repo, "BUG-462", reason="x", by="autopilot")


class TestSplitContract:
    """Structural invariants of the TECH-214 split (EC-1, EC-7, EC-10, EC-11)."""

    def test_write_lock_is_a_single_instance(self):
        import lifecycle_const

        assert lifecycle._write_lock is lifecycle_const._write_lock
        assert lifecycle_cas._write_lock is lifecycle_const._write_lock

    def test_bound_imports_still_resolve(self):
        import migrate_backlog_to_lifecycle
        import render_backlog
        import salvage

        assert salvage._git is lifecycle.run_git
        assert render_backlog.LIFECYCLE_DIR == lifecycle.LIFECYCLE_DIR
        assert migrate_backlog_to_lifecycle.build_initial_yaml is lifecycle.build_initial_yaml

    def test_no_sibling_imports_the_facade(self):
        siblings = ["const", "errors", "git", "cas", "push", "recovery"]
        for name in siblings:
            src = (Path(lifecycle.__file__).parent / f"lifecycle_{name}.py").read_text(
                encoding="utf-8"
            )
            for line in src.splitlines():
                stripped = line.strip()
                assert not stripped.startswith("from lifecycle import"), f"{name}: {line}"
                assert stripped != "import lifecycle", f"{name}: {line}"

    def test_every_module_under_the_loc_limit(self):
        vps = Path(lifecycle.__file__).parent
        names = ["lifecycle.py"] + [
            f"lifecycle_{n}.py" for n in ["const", "errors", "git", "cas", "push", "recovery"]
        ]
        for name in names:
            loc = len((vps / name).read_text(encoding="utf-8").splitlines())
            assert loc <= 400, f"{name}: {loc} LOC > 400"


def test_write_lifecycle_preserves_depends_on(tmp_git_repo):
    """A status change must not drop depends_on — otherwise the dependency gate
    dies on the very first dispatch of a spec that declared one."""
    lifecycle.create_initial(tmp_git_repo, "TECH-507", "p1", "tech", depends_on=["TECH-220"])
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-507", "in_progress", by="orchestrator")
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-507")
    assert data["depends_on"] == ["TECH-220"]
    assert data["status"] == "in_progress"


def test_set_depends_on_preserves_concurrent_status_write(tmp_git_repo):
    """EC-7 (devil DA-6): статус, записанный между чтением и коммитом, обязан выжить.

    Инжектим сырым git-коммитом, а НЕ через write_lifecycle: _write_lock —
    обычный threading.Lock, вызов публичного writer'а изнутри CAS-петли = дедлок.
    """
    lifecycle.create_initial(tmp_git_repo, "TECH-580", "p1", "tech")
    yaml_path = tmp_git_repo / "ai" / "lifecycle" / "TECH-580.yaml"
    state = {"injected": False}
    real_run = lifecycle_git._run

    def injecting_run(cmd, **kwargs):
        if not state["injected"] and cmd[:2] == ["git", "write-tree"]:
            state["injected"] = True
            yaml_path.write_text(
                yaml_path.read_text(encoding="utf-8").replace(
                    "status: queued", "status: in_progress"
                ),
                encoding="utf-8",
            )
            _git(tmp_git_repo, "add", "ai/lifecycle/TECH-580.yaml")
            _git(tmp_git_repo, "commit", "-m", "lifecycle(TECH-580): in_progress")
        return real_run(cmd, **kwargs)

    with patch.object(lifecycle_git, "_run", injecting_run):
        lifecycle.set_depends_on(tmp_git_repo, "TECH-580", ["TECH-220"], by="operator")

    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-580")
    assert data["status"] == "in_progress", "параллельная смена статуса откатилась"
    assert data["depends_on"] == ["TECH-220"]


def test_set_depends_on_rejects_unknown_writer(tmp_git_repo):
    """ADR-024: by обязателен и проверяется по _ALLOWED_WRITERS."""
    lifecycle.create_initial(tmp_git_repo, "TECH-581", "p1", "tech")
    with pytest.raises(ValueError, match="invalid by='autopilot'"):
        lifecycle.set_depends_on(tmp_git_repo, "TECH-581", ["TECH-220"], by="autopilot")
