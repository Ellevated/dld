"""
Integration tests for TECH-172: callback is the only Status writer.

Verifies that autopilot skill docs no longer contain Status-writing instructions,
coder.md forbids Status edits, and callback.py correctly parses task_status.

No mocks per ADR-013 — all assertions against real files and real imports.
"""

import json
import sys
from pathlib import Path

import pytest

# Worktree / project root (two levels up from tests/integration/)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Paths to autopilot skill files
FINISHING_MD = PROJECT_ROOT / ".claude" / "skills" / "autopilot" / "finishing.md"
TASK_LOOP_MD = PROJECT_ROOT / ".claude" / "skills" / "autopilot" / "task-loop.md"
SKILL_MD = PROJECT_ROOT / ".claude" / "skills" / "autopilot" / "SKILL.md"
CODER_MD = PROJECT_ROOT / ".claude" / "agents" / "coder.md"

# Template mirror paths
TMPL_FINISHING_MD = PROJECT_ROOT / "template" / ".claude" / "skills" / "autopilot" / "finishing.md"
TMPL_TASK_LOOP_MD = PROJECT_ROOT / "template" / ".claude" / "skills" / "autopilot" / "task-loop.md"
TMPL_SKILL_MD = PROJECT_ROOT / "template" / ".claude" / "skills" / "autopilot" / "SKILL.md"
TMPL_CODER_MD = PROJECT_ROOT / "template" / ".claude" / "agents" / "coder.md"


# ---------------------------------------------------------------------------
# EC-1 — finishing.md no longer contains Status-write instructions
# ---------------------------------------------------------------------------

def test_finishing_md_has_no_status_edit_instruction():
    """finishing.md must contain 'Status Writes — Callback Only' section."""
    text = FINISHING_MD.read_text(encoding="utf-8")
    assert "Status Writes — Callback Only" in text, (
        "finishing.md must contain 'Status Writes — Callback Only' section (TECH-172)"
    )


# ---------------------------------------------------------------------------
# EC-1 — task-loop.md forbids Status writes
# ---------------------------------------------------------------------------

def test_task_loop_md_forbids_status_writes():
    """task-loop.md must contain 'Status Writes — Forbidden' section."""
    text = TASK_LOOP_MD.read_text(encoding="utf-8")
    assert "Status Writes — Forbidden" in text, (
        "task-loop.md must contain 'Status Writes — Forbidden in task-loop' section (TECH-172)"
    )


# ---------------------------------------------------------------------------
# EC-1 — SKILL.md documents task_status field
# ---------------------------------------------------------------------------

def test_skill_md_documents_task_status():
    """SKILL.md must mention task_status in Notification Output Format."""
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "task_status" in text, (
        "SKILL.md must document task_status in Notification Output Format (TECH-172)"
    )


# ---------------------------------------------------------------------------
# EC-1 — coder.md forbids Status edit and mentions callback
# ---------------------------------------------------------------------------

def test_coder_md_forbids_status_edit():
    """coder.md must contain both '**Status:**' and 'callback' in forbidden rules."""
    text = CODER_MD.read_text(encoding="utf-8")
    assert "**Status:**" in text, (
        "coder.md must mention '**Status:**' in its Forbidden section (TECH-172)"
    )
    assert "callback" in text, (
        "coder.md must mention 'callback' in its Forbidden section (TECH-172)"
    )


# ---------------------------------------------------------------------------
# EC-2 — callback._parse_log_file returns 3-tuple with task_status
# ---------------------------------------------------------------------------

def test_callback_parses_task_status(tmp_path):
    """_parse_log_file must return (skill, preview, task_status) triple."""
    # Add scripts/vps to sys.path so callback can import db / event_writer
    scripts_vps = str(PROJECT_ROOT / "scripts" / "vps")
    if scripts_vps not in sys.path:
        sys.path.insert(0, scripts_vps)

    import callback  # noqa: PLC0415

    log_file = tmp_path / "test-run.log"
    payload = {
        "skill": "autopilot",
        "result_preview": "x",
        "task_status": "blocked",
    }
    log_file.write_text(json.dumps(payload), encoding="utf-8")

    result = callback._parse_log_file(log_file)
    assert len(result) == 3, f"Expected 3-tuple, got {len(result)}-tuple: {result}"
    skill, preview, task_status = result
    assert skill == "autopilot", f"skill mismatch: {skill!r}"
    assert preview == "x", f"preview mismatch: {preview!r}"
    assert task_status == "blocked", f"task_status mismatch: {task_status!r}"


def test_callback_parses_task_status_from_preview_json(tmp_path):
    """_parse_log_file falls back to parsing task_status from JSON in result_preview."""
    scripts_vps = str(PROJECT_ROOT / "scripts" / "vps")
    if scripts_vps not in sys.path:
        sys.path.insert(0, scripts_vps)

    import callback  # noqa: PLC0415

    log_file = tmp_path / "test-run2.log"
    # task_status embedded inside result_preview JSON string
    inner = json.dumps({"task_status": "complete", "summary": "ok"})
    payload = {
        "skill": "autopilot",
        "result_preview": inner,
        # no top-level task_status
    }
    log_file.write_text(json.dumps(payload), encoding="utf-8")

    result = callback._parse_log_file(log_file)
    assert len(result) == 3, f"Expected 3-tuple, got {len(result)}-tuple: {result}"
    _, _, task_status = result
    assert task_status == "complete", f"task_status from inner JSON mismatch: {task_status!r}"


# ---------------------------------------------------------------------------
# EC-2 — extract_agent_output returns 3-tuple (smoke test)
# ---------------------------------------------------------------------------

def test_callback_extract_returns_triple():
    """extract_agent_output must return a 3-tuple even for unknown pueue_id."""
    scripts_vps = str(PROJECT_ROOT / "scripts" / "vps")
    if scripts_vps not in sys.path:
        sys.path.insert(0, scripts_vps)

    import callback  # noqa: PLC0415

    result = callback.extract_agent_output("-1", "")
    assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
    assert len(result) == 3, f"Expected 3-tuple, got {len(result)}-tuple: {result}"
    skill, preview, task_status = result
    # All empty strings for unknown pueue_id
    assert isinstance(skill, str)
    assert isinstance(preview, str)
    assert isinstance(task_status, str)


# ---------------------------------------------------------------------------
# EC-3 — template mirrors root (new section headers present in both)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("root_path,tmpl_path,section_header", [
    (
        FINISHING_MD,
        TMPL_FINISHING_MD,
        "Status Writes — Callback Only",
    ),
    (
        TASK_LOOP_MD,
        TMPL_TASK_LOOP_MD,
        "Status Writes — Forbidden",
    ),
    (
        SKILL_MD,
        TMPL_SKILL_MD,
        "task_status",
    ),
    (
        CODER_MD,
        TMPL_CODER_MD,
        "**Status:**",
    ),
])
def test_template_mirrors_root(root_path, tmpl_path, section_header):
    """Both root and template versions must contain the new TECH-172 markers."""
    root_text = root_path.read_text(encoding="utf-8")
    tmpl_text = tmpl_path.read_text(encoding="utf-8")

    assert section_header in root_text, (
        f"Root {root_path.name} missing '{section_header}' (TECH-172)"
    )
    assert section_header in tmpl_text, (
        f"Template {tmpl_path.name} missing '{section_header}' (TECH-172)"
    )
