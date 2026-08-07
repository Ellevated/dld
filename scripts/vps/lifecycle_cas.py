"""
Module: lifecycle_cas
Role: One-attempt atomic writes via private GIT_INDEX_FILE + CAS update-ref
      (per-spec yaml and arbitrary file paths), plus the retry loop that
      serializes them on the single process-wide write lock.

Uses:
  - os, tempfile: private GIT_INDEX_FILE for index isolation
  - re: status extraction from the yaml content
  - random, time: retry jitter
  - subprocess: TimeoutExpired
  - lifecycle_git: _run
  - lifecycle_push: _push_best_effort
  - lifecycle_const: LIFECYCLE_DIR, MAX_CAS_RETRIES, _write_lock
  - lifecycle_errors: LifecycleWriteRaceError
  - render_backlog: sync_status (lazy, best-effort backlog fold)

Used by:
  - lifecycle.py: write_lifecycle, create_initial, write_file_atomic
  - lifecycle_recovery.py: the two narrow Rule 7 escapes (Task 4)
"""

import logging
import os
import random
import re
import subprocess
import tempfile
import time

import lifecycle_git
import lifecycle_push
from lifecycle_const import LIFECYCLE_DIR, MAX_CAS_RETRIES, _write_lock
from lifecycle_errors import LifecycleWriteRaceError

log = logging.getLogger(__name__)


def _atomic_write(repo_dir: str, spec_id: str, yaml_content: str, branch: str) -> bool:
    """One CAS attempt. Returns True on success, False on race (HEAD moved)."""
    git_dir = os.path.join(repo_dir, ".git")

    with tempfile.NamedTemporaryFile(dir=git_dir, delete=False) as f:
        idx_path = f.name

    try:
        env = {**os.environ, "GIT_INDEX_FILE": idx_path}

        # TOCTOU fix (FTR-1270 wipe, 2026-06-22): pin HEAD once so the tree
        # snapshot, the commit parent, and the CAS all reference the SAME commit.
        # Reading HEAD twice (read-tree HEAD ... later rev-parse HEAD) let a
        # concurrent push land between them — the tree snapshotted the OLD HEAD
        # while the parent was the NEW HEAD; the CAS only guards parent==branch,
        # so it committed a stale tree that silently reverted everything in between.
        hr = lifecycle_git._run(["git", "rev-parse", "HEAD"], cwd=repo_dir)
        if hr.returncode != 0:
            return False
        head_sha = hr.stdout.strip()

        if (
            lifecycle_git._run(["git", "read-tree", head_sha], cwd=repo_dir, env=env).returncode
            != 0
        ):
            return False

        r = lifecycle_git._run(
            ["git", "hash-object", "-w", "--stdin"], cwd=repo_dir, env=env, input_text=yaml_content
        )
        if r.returncode != 0:
            return False
        blob_sha = r.stdout.strip()

        path_in_repo = f"{LIFECYCLE_DIR}/{spec_id}.yaml"
        if (
            lifecycle_git._run(
                [
                    "git",
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    f"100644,{blob_sha},{path_in_repo}",
                ],
                cwd=repo_dir,
                env=env,
            ).returncode
            != 0
        ):
            return False

        # backlog.md status sync (re-enabled, status-only). lifecycle.yaml stays
        # the SoT; backlog.md is a human-authored view. The OLD plain-table render
        # was disabled 2026-05-16 because it destroyed founder descriptions /
        # section structure. render_backlog.sync_status rewrites ONLY the Status
        # cell of existing rows (override carries THIS spec's new status, which is
        # not in HEAD yet) and is folded into the SAME atomic commit as the YAML —
        # no second commit, no WT race. Best-effort: never break the status write.
        try:
            import render_backlog

            bl = lifecycle_git._run(["git", "show", f"{head_sha}:ai/backlog.md"], cwd=repo_dir)
            if bl.returncode == 0:
                m_status = re.search(r"status:\s*(\S+)", yaml_content)
                override = {spec_id: m_status.group(1)} if m_status else None
                synced = render_backlog.sync_status(repo_dir, bl.stdout, overrides=override)
                if synced != bl.stdout:
                    blob = lifecycle_git._run(
                        ["git", "hash-object", "-w", "--stdin"],
                        cwd=repo_dir,
                        env=env,
                        input_text=synced,
                    )
                    if blob.returncode == 0:
                        lifecycle_git._run(
                            [
                                "git",
                                "update-index",
                                "--add",
                                "--cacheinfo",
                                f"100644,{blob.stdout.strip()},ai/backlog.md",
                            ],
                            cwd=repo_dir,
                            env=env,
                        )
        except Exception as exc:  # noqa: BLE001 — render must never break the write
            log.warning("backlog sync skipped for %s: %s", spec_id, exc)

        r = lifecycle_git._run(["git", "write-tree"], cwd=repo_dir, env=env)
        if r.returncode != 0:
            return False
        tree_sha = r.stdout.strip()

        m = re.search(r"status:\s*(\S+)", yaml_content)
        status_str = m.group(1) if m else "update"
        msg = f"lifecycle({spec_id}): {status_str}"

        r = lifecycle_git._run(
            ["git", "commit-tree", tree_sha, "-p", head_sha, "-m", msg], cwd=repo_dir, env=env
        )
        if r.returncode != 0:
            return False
        new_commit = r.stdout.strip()

        r = lifecycle_git._run(
            ["git", "update-ref", f"refs/heads/{branch}", new_commit, head_sha], cwd=repo_dir
        )
        if r.returncode != 0:
            log.debug("CAS lost for %s (branch %s)", spec_id, branch)
            return False

        # Layer 3 (ARCH-187 / ADR-024 / TECH-194): sync WT to new HEAD blob so
        # subsequent `git add .` from any agent cannot smuggle a stale yaml into
        # a commit. Uses `git checkout HEAD -- <path>` (not checkout-index) so
        # both the default .git/index and WT are updated atomically. checkout-index
        # with a private GIT_INDEX_FILE only writes the WT file but leaves the
        # default index with a staged deletion (`D  `) — fixed in TECH-194.
        # Best-effort: log on failure but don't fail the write
        # (assert_clean_lifecycle_tree at orchestrator boot is the backstop).
        sync_result = lifecycle_git._run(
            ["git", "checkout", "HEAD", "--", f"{LIFECYCLE_DIR}/{spec_id}.yaml"],
            cwd=repo_dir,
        )
        if sync_result.returncode != 0:
            log.warning(
                "WT sync after write_lifecycle failed (best-effort): rc=%d stderr=%s",
                sync_result.returncode,
                sync_result.stderr.strip(),
            )

        # Sync WT for backlog.md too (it was folded into the commit above). Best-
        # effort + separate: backlog.md may not exist in some projects, and a miss
        # here must not fail the lifecycle write.
        lifecycle_git._run(["git", "checkout", "HEAD", "--", "ai/backlog.md"], cwd=repo_dir)

        return True

    finally:
        try:
            os.unlink(idx_path)
        except OSError:
            pass


def _atomic_write_file(
    repo_dir: str,
    rel_path: str,
    content: str,
    commit_message: str,
    branch: str,
) -> bool:
    """One CAS attempt for arbitrary file path. Mirrors _atomic_write but generic."""
    git_dir = os.path.join(repo_dir, ".git")
    with tempfile.NamedTemporaryFile(dir=git_dir, delete=False) as f:
        idx_path = f.name
    try:
        env = {**os.environ, "GIT_INDEX_FILE": idx_path}
        # TOCTOU fix (FTR-1270 wipe): pin HEAD once — tree, parent, CAS all on the
        # same commit (see _atomic_write). Reading HEAD twice raced a concurrent
        # push and silently reverted in-between commits.
        hr = lifecycle_git._run(["git", "rev-parse", "HEAD"], cwd=repo_dir)
        if hr.returncode != 0:
            return False
        head_sha = hr.stdout.strip()
        if (
            lifecycle_git._run(["git", "read-tree", head_sha], cwd=repo_dir, env=env).returncode
            != 0
        ):
            return False
        r = lifecycle_git._run(
            ["git", "hash-object", "-w", "--stdin"],
            cwd=repo_dir,
            env=env,
            input_text=content,
        )
        if r.returncode != 0:
            return False
        blob_sha = r.stdout.strip()
        if (
            lifecycle_git._run(
                ["git", "update-index", "--add", "--cacheinfo", f"100644,{blob_sha},{rel_path}"],
                cwd=repo_dir,
                env=env,
            ).returncode
            != 0
        ):
            return False
        r = lifecycle_git._run(["git", "write-tree"], cwd=repo_dir, env=env)
        if r.returncode != 0:
            return False
        tree_sha = r.stdout.strip()
        r = lifecycle_git._run(
            ["git", "commit-tree", tree_sha, "-p", head_sha, "-m", commit_message],
            cwd=repo_dir,
            env=env,
        )
        if r.returncode != 0:
            return False
        new_commit = r.stdout.strip()
        r = lifecycle_git._run(
            ["git", "update-ref", f"refs/heads/{branch}", new_commit, head_sha],
            cwd=repo_dir,
        )
        if r.returncode != 0:
            return False
        # Sync WT (best-effort; backlog.md is a render so stale WT is recoverable).
        # Uses `git checkout HEAD -- <path>` (not checkout-index) to update both
        # default .git/index and WT. checkout-index with private GIT_INDEX_FILE
        # only writes WT, leaving default index with staged deletion — TECH-194.
        sync = lifecycle_git._run(["git", "checkout", "HEAD", "--", rel_path], cwd=repo_dir)
        if sync.returncode != 0:
            log.warning("write_file_atomic WT sync failed: %s", sync.stderr.strip()[:200])
        return True
    finally:
        try:
            os.unlink(idx_path)
        except OSError:
            pass


def _cas_loop(repo_dir: str, spec_id: str, branch: str, yaml_fn) -> None:
    """Run CAS retry loop with in-process lock + jitter.

    In-process lock (_write_lock) serializes writes within one Python process,
    eliminating intra-process CAS stampede while preserving multi-machine CAS
    safety via git update-ref.
    """
    with _write_lock:
        for attempt in range(1, MAX_CAS_RETRIES + 1):
            yaml_content = yaml_fn()
            try:
                wrote = _atomic_write(repo_dir, spec_id, yaml_content, branch)
            except subprocess.TimeoutExpired as exc:
                log.warning(
                    "lifecycle git plumbing timeout (spec=%s cmd=%s); treating as CAS failure",
                    spec_id,
                    exc.cmd,
                )
                wrote = False
            if wrote:
                lifecycle_push._push_best_effort(repo_dir, branch)
                return
            log.warning("CAS attempt %d/%d failed for %s", attempt, MAX_CAS_RETRIES, spec_id)
            if attempt < MAX_CAS_RETRIES:
                # Jitter: spread retries to reduce multi-machine CAS stampede (0–50ms)
                time.sleep(random.uniform(0, 0.05))
        raise LifecycleWriteRaceError(spec_id, MAX_CAS_RETRIES)
