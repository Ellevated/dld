"""Unit tests for openclaw-artifact-scan.py extract functions."""

import importlib
import sys
from pathlib import Path

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

# Module uses hyphens in name, import via importlib
artifact_scan = importlib.import_module("openclaw-artifact-scan")


class TestExtractStatus:
    """Tests for extract_status()."""

    def test_standard_qa_loop_format(self):
        """qa-loop.sh writes **Status:** passed — should parse."""
        text = "# QA Report: TECH-153\n\n**Status:** passed\n**Project:** dld\n"
        assert artifact_scan.extract_status(text) == "passed"

    def test_standard_qa_loop_failed(self):
        """qa-loop.sh writes **Status:** failed — should parse."""
        text = "**Status:** failed\n**Spec:** BUG-123\n"
        assert artifact_scan.extract_status(text) == "failed"

    def test_hand_written_report_no_status_header(self):
        """Hand-written QA reports have no **Status:** line."""
        text = (
            "# QA Report: TECH-151 — Orchestrator North-Star Alignment\n\n"
            "**Date:** 2026-03-17\n"
            "**Environment:** VPS\n\n"
            "## Summary\n\n"
            "| Total | Pass | Fail | Blocked |\n"
            "|-------|------|------|--------|\n"
            "| 10    | 3    | 6    | 1       |\n"
        )
        assert artifact_scan.extract_status(text) == "no_status_header"

    def test_empty_text(self):
        """Empty text returns 'no_status_header'."""
        assert artifact_scan.extract_status("") == "no_status_header"


class TestExtractSpec:
    """Tests for extract_spec()."""

    def test_standard_spec_header(self):
        """qa-loop.sh writes **Spec:** TECH-153 — should parse."""
        text = "**Status:** passed\n**Spec:** TECH-153\n"
        assert artifact_scan.extract_spec(text) == "TECH-153"

    def test_hand_written_report_title_fallback(self):
        """Hand-written reports have spec ID in title."""
        text = (
            "# QA Report: TECH-151 — Orchestrator North-Star Alignment\n\n"
            "**Date:** 2026-03-17\n"
        )
        assert artifact_scan.extract_spec(text) == "TECH-151"

    def test_hand_written_lowercase_title(self):
        """Spec ID in title may be lowercase."""
        text = "# QA Report: tech-153 AI-First Model\n"
        assert artifact_scan.extract_spec(text) == "TECH-153"

    def test_no_spec_anywhere(self):
        """No spec info at all returns empty string."""
        text = "# Some Report\n\nNo spec info here.\n"
        assert artifact_scan.extract_spec(text) == ""
