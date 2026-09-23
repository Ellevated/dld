"""callback_event.pick_artifact — QA/reflect artifact selection for the Hermes event.

Hermes got "qa-BUG-522 -> FTR-282 artifact" because selection used to be plain
`sorted(glob)[-1]` (name order, not the run's own file). These tests pin the
replacement: prefer the label's own spec file, else fall back to the newest
file by mtime — never by filename.

EC-6: own spec file wins over a newer foreign file; a label must not match as
      a digit prefix of a longer id.
EC-7: no own file for the label -> newest mtime wins.
"""

import os
import sys
import time
from pathlib import Path

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import callback_event  # noqa: E402


def _touch(path: Path, mtime: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("content\n", encoding="utf-8")
    os.utime(path, (mtime, mtime))


def test_ec6_qa_picks_own_spec_file(tmp_path):
    """EC-6: own file wins even though a foreign file is newer; a shorter id
    must not match as a digit prefix of the real one."""
    now = time.time()
    own = tmp_path / "ai" / "qa" / "2026-09-23-bug-520-a.md"
    foreign = tmp_path / "ai" / "qa" / "2026-09-23-zzz-other.md"
    _touch(own, now - 100)
    _touch(foreign, now)

    assert callback_event.pick_artifact(str(tmp_path), "qa", "qa-BUG-520") == (
        "ai/qa/2026-09-23-bug-520-a.md"
    )
    # "BUG-52" is a digit-prefix of "BUG-520" in the own file's name — must NOT
    # count as a match, so selection falls back to newest-mtime among all files.
    assert callback_event.pick_artifact(str(tmp_path), "qa", "qa-BUG-52") == (
        "ai/qa/2026-09-23-zzz-other.md"
    )


def test_ec7_qa_falls_back_to_newest_mtime(tmp_path):
    """EC-7: neither file names the spec — newest mtime wins."""
    now = time.time()
    aaa = tmp_path / "ai" / "qa" / "2026-09-23-aaa.md"
    zzz = tmp_path / "ai" / "qa" / "2026-09-23-zzz.md"
    _touch(zzz, now - 100)
    _touch(aaa, now)

    assert callback_event.pick_artifact(str(tmp_path), "qa", "qa-BUG-999") == (
        "ai/qa/2026-09-23-aaa.md"
    )


def test_reflect_picks_newest_mtime_regardless_of_name(tmp_path):
    """reflect has no spec-id matching — always newest mtime, not last by name."""
    now = time.time()
    named_last = tmp_path / "ai" / "reflect" / "findings-zzz.md"
    named_first = tmp_path / "ai" / "reflect" / "findings-aaa.md"
    _touch(named_last, now - 100)
    _touch(named_first, now)

    assert callback_event.pick_artifact(str(tmp_path), "reflect", "reflect-1") == (
        "ai/reflect/findings-aaa.md"
    )


def test_unknown_skill_or_no_files_returns_empty(tmp_path):
    """Neither qa nor reflect, and an empty qa dir, both yield ''."""
    assert callback_event.pick_artifact(str(tmp_path), "spark", "spark-1") == ""
    assert callback_event.pick_artifact(str(tmp_path), "qa", "qa-BUG-1") == ""
