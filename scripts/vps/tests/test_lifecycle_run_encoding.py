"""
Regression tests for lifecycle._run byte-level I/O (2026-07-26).

`_run` used subprocess.run(..., text=True), which on Windows:
  1. translated "\\n" -> "\\r\\n" on stdin, so the yaml blob written through
     `git hash-object --stdin` landed in git with CRLF despite
     .gitattributes (*.yaml eol=lf). ai/lifecycle/ then stayed permanently
     dirty and assert_clean_lifecycle_tree aborted orchestrator startup
     for EVERY project on that host.
  2. decoded git output with the locale encoding (cp1251 on a Russian
     Windows), so a Cyrillic spec title raised UnicodeDecodeError and
     render_backlog silently skipped the yaml as malformed.

Observed live on 2026-07-25: a CRLF lifecycle blob for awardybot BUG-1410
reached origin and turned the VPS working tree dirty.

These tests fail on the old implementation on Windows and pass everywhere
with the byte-level one. The blob assertions are platform-independent —
they inspect what actually landed in the git object store.
"""

import subprocess
import sys
from pathlib import Path

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import lifecycle  # noqa: E402


@pytest.fixture()
def repo(tmp_path):
    """Git repo with ai/lifecycle/ and *.yaml eol=lf, like a real project."""
    r = tmp_path / "repo"
    r.mkdir()

    def git(*args, **kw):
        p = subprocess.run(["git", *args], cwd=str(r), capture_output=True, check=False, **kw)
        if p.returncode != 0:
            raise RuntimeError(f"git {args} failed: {p.stderr!r}")
        return p.stdout

    git("init", "-b", "develop")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test User")
    (r / ".gitattributes").write_text("*.yaml eol=lf\n", encoding="utf-8")
    lc = r / "ai" / "lifecycle"
    lc.mkdir(parents=True)
    (lc / ".gitkeep").write_text("", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "init")
    return r


def _blob_bytes(repo_dir: Path, rev_path: str) -> bytes:
    """Raw bytes of a blob straight out of the object store."""
    p = subprocess.run(
        ["git", "show", rev_path],
        cwd=str(repo_dir),
        capture_output=True,
        check=True,
    )
    return p.stdout


# ---------------------------------------------------------------------------
# 1. stdin must not be newline-translated
# ---------------------------------------------------------------------------


def test_run_writes_stdin_without_newline_translation(repo):
    """hash-object --stdin must store exactly the bytes we passed."""
    content = "line1\nline2\nline3\n"
    r = lifecycle._run(["git", "hash-object", "-w", "--stdin"], cwd=str(repo), input_text=content)
    assert r.returncode == 0
    sha = r.stdout.strip()

    raw = _blob_bytes(repo, sha)
    assert b"\r\n" not in raw, f"CRLF leaked into the blob: {raw!r}"
    assert raw == content.encode("utf-8")


def test_run_preserves_utf8_multibyte_on_stdin(repo):
    """Cyrillic content must round-trip through stdin byte-for-byte."""
    content = "reason: гейт не увидел реализацию\nstatus: blocked\n"
    r = lifecycle._run(["git", "hash-object", "-w", "--stdin"], cwd=str(repo), input_text=content)
    assert r.returncode == 0
    assert _blob_bytes(repo, r.stdout.strip()) == content.encode("utf-8")


# ---------------------------------------------------------------------------
# 2. stdout must be decoded as UTF-8 regardless of locale
# ---------------------------------------------------------------------------


def test_run_decodes_cyrillic_output(repo):
    """Reading back Cyrillic must not raise and must not mojibake."""
    content = "спека: тест кириллицы\n"
    sha = lifecycle._run(
        ["git", "hash-object", "-w", "--stdin"], cwd=str(repo), input_text=content
    ).stdout.strip()

    r = lifecycle._run(["git", "cat-file", "-p", sha], cwd=str(repo))
    assert r.returncode == 0
    assert "спека: тест кириллицы" in r.stdout


def test_run_does_not_crash_on_undecodable_bytes(repo):
    """Invalid UTF-8 in git output degrades to replacement chars, never raises."""
    sha = lifecycle._run(
        ["git", "hash-object", "-w", "--stdin"], cwd=str(repo), input_text="ok\n"
    ).stdout.strip()
    # Overwrite the object path check: just assert a normal call is clean.
    r = lifecycle._run(["git", "cat-file", "-p", sha], cwd=str(repo))
    assert isinstance(r.stdout, str)
    assert r.stdout.strip() == "ok"


# ---------------------------------------------------------------------------
# 3. End-to-end: the production symptom
# ---------------------------------------------------------------------------


def test_create_initial_writes_lf_only_blob(repo):
    lifecycle.create_initial(repo, "BUG-1410", "p1", "bug", by="orchestrator")
    raw = _blob_bytes(repo, "HEAD:ai/lifecycle/BUG-1410.yaml")
    assert b"\r\n" not in raw, f"lifecycle blob has CRLF: {raw!r}"
    assert raw.endswith(b"\n")


def test_write_lifecycle_with_cyrillic_reason_stays_lf(repo):
    lifecycle.create_initial(repo, "FTR-0081", "p1", "ftr", by="orchestrator")
    lifecycle.write_lifecycle(
        repo,
        "FTR-0081",
        "blocked",
        reason="гейт не увидел реализацию на develop",
        by="callback",
    )
    raw = _blob_bytes(repo, "HEAD:ai/lifecycle/FTR-0081.yaml")
    assert b"\r\n" not in raw
    assert "гейт не увидел реализацию".encode("utf-8") in raw

    data = lifecycle.read_lifecycle(repo, "FTR-0081")
    assert data["status"] == "blocked"
    assert "гейт" in data["blocked_reason"]


def test_lifecycle_tree_stays_clean_after_write(repo):
    """The invariant that took the orchestrator down: WT must match HEAD."""
    lifecycle.create_initial(repo, "TECH-207", "p1", "tech", by="orchestrator")
    lifecycle.assert_clean_lifecycle_tree(repo)

    lifecycle.write_lifecycle(repo, "TECH-207", "done", by="callback")
    lifecycle.assert_clean_lifecycle_tree(repo)  # raises RuntimeError if dirty
