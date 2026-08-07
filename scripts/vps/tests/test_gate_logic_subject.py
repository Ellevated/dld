# scripts/vps/tests/test_gate_logic_subject.py
"""Subject-matcher tests for gate_logic.match_subject (TECH-210).

Split out of test_gate_logic.py (which was 723 LOC against the 600 test limit) and
merged with the 14 cases that lived only in test_callback.py against the now-deleted
callback._subject_implements. Nothing here is new coverage — every case is a case
that already guarded a real incident.
"""

import sys
from pathlib import Path

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

from gate_logic import match_subject  # noqa: E402

# ===========================================================================
# Part 1: match_subject — unit tests (no git)
# ===========================================================================


def test_match_subject_conventional_feat():
    """Conventional Commits form: feat(SPEC-A): description."""
    assert match_subject("feat(SPEC-A): implement the feature", "SPEC-A") is True


def test_match_subject_conventional_fix():
    """Conventional Commits form: fix(SPEC-A)!: description."""
    assert match_subject("fix(SPEC-A)!: critical fix", "SPEC-A") is True


def test_match_subject_merge_form():
    """Merge commit form: merge SPEC-A (spec_id directly after 'merge')."""
    # The regex is ^merge\s+{spec_id}\b — spec_id must come right after 'merge'.
    assert match_subject("Merge SPEC-A", "SPEC-A") is True


def test_match_subject_bare_prefix():
    """Legacy bare prefix form: SPEC-A: description."""
    assert match_subject("SPEC-A: implement the feature", "SPEC-A") is True


def test_match_subject_wrong_spec_id():
    """Negative: feat(BUG-200): work should NOT match TECH-189."""
    assert match_subject("feat(BUG-200): work", "TECH-189") is False


def test_DA4_growth_spec_id_match_subject():
    """DA-4: GROWTH-042 spec_id must be matched by match_subject."""
    assert match_subject("feat(GROWTH-042): add growth metric", "GROWTH-042") is True


# --- 2026-07-02 false-blocked regression (plpilot BUG-338/339, TECH-349) ----


def test_match_subject_trailing_parens_with_scope():
    """Real plpilot BUG-339 subject: domain scope + trailing (SPEC-ID)."""
    assert (
        match_subject(
            "fix(security): REVOKE public execute on 7 SECURITY DEFINER RPCs (BUG-339)",
            "BUG-339",
        )
        is True
    )


def test_match_subject_trailing_parens_no_scope():
    """Real plpilot BUG-338 subject: no scope, trailing (SPEC-ID)."""
    assert (
        match_subject(
            "fix: HTML-aware TG text truncation prevents broken tags (BUG-338)",
            "BUG-338",
        )
        is True
    )


def test_match_subject_trailing_parens_multi_spec():
    """Trailing parens with comma-separated spec ids matches each one."""
    subj = "fix: shared helper hardening (BUG-339, BUG-340)"
    assert match_subject(subj, "BUG-339") is True
    assert match_subject(subj, "BUG-340") is True
    assert match_subject(subj, "BUG-341") is False


def test_match_subject_trailing_parens_free_text_rejected():
    """`(see SPEC-ID)` is a cross-reference, not a declaration → reject."""
    assert match_subject("fix: adjust helper (see BUG-339)", "BUG-339") is False


def test_match_subject_mid_subject_parens_rejected():
    """Parenthesized ID NOT at end of subject stays rejected."""
    assert match_subject("fix: revert (BUG-339) partial change now", "BUG-339") is False


def test_match_subject_merge_colon_form():
    """Real plpilot TECH-349 subject: `merge: feature/SPEC-ID — ...`."""
    assert (
        match_subject(
            "merge: feature/TECH-349 — Edge resilience (CORS fail-fast + timeouts)",
            "TECH-349",
        )
        is True
    )


def test_match_subject_merge_branch_quoted_form():
    """Git default merge subject: Merge branch 'fix/SPEC-ID-slug'."""
    assert (
        match_subject(
            "Merge branch 'fix/BUG-346-one-time-receipt-phantom' into develop",
            "BUG-346",
        )
        is True
    )


def test_match_subject_merge_branch_wrong_spec_rejected():
    """Merge of an UNRELATED branch must not match a different spec."""
    assert (
        match_subject(
            "Merge branch 'fix/BUG-346-one-time-receipt-phantom' into develop",
            "BUG-347",
        )
        is False
    )
    # Spec id boundary: BUG-346 must not match inside BUG-3468.
    assert match_subject("Merge branch 'fix/BUG-3468-x'", "BUG-346") is False


# ===========================================================================
# Part 2: 14 cases absent from test_gate_logic.py, present only in the old
# callback._subject_implements suite (test_callback.py, verified 2026-08-07
# against TestSubjectImplements / TestSubjectImplementsRealWorld /
# TestSubjectImplementsAntiFalsePositive / TestMatchSubjectParityWithCallback).
# [DRIFT-9]: 14 cases, not 13 — §7 Autopilot Log missed
# `feat(other): see also FTR-925`.
# ===========================================================================


def test_match_subject_conventional_multi_scope():
    """Multi-spec scope, with and without whitespace (test_callback.py:405-407)."""
    assert match_subject("feat(FTR-925,FTR-926): both", "FTR-925") is True
    assert match_subject("feat(FTR-925, FTR-926): both", "FTR-926") is True


def test_match_subject_merge_lowercase_and_colon_form():
    """Lowercase `merge` + id-then-colon form (test_callback.py:412-414)."""
    assert match_subject("merge FTR-925", "FTR-925") is True
    assert match_subject("merge FTR-925: impl", "FTR-925") is True


def test_match_subject_body_mention_with_own_scope_rejected():
    """Own-scope subject with a see-also spec id in the parens stays rejected
    (test_callback.py:420-422)."""
    assert match_subject("feat(FTR-923): impl X (see also FTR-925)", "FTR-925") is False


def test_match_subject_id_in_body_without_scope_rejected():
    """`feat: SPEC-ID ...` — id in the description, no scope, is not a
    declaration (test_callback.py:424-425, 491-492)."""
    assert match_subject("feat: FTR-925 something", "FTR-925") is False
    assert match_subject("feat: FTR-1076 implementation", "FTR-1076") is False


def test_match_subject_empty_inputs_rejected():
    """Empty subject or empty spec_id never matches (test_callback.py:430-432)."""
    assert match_subject("", "FTR-925") is False
    assert match_subject("feat(FTR-925): x", "") is False


def test_match_subject_lowercase_scope():
    """Real awardybot BUG-192 subjects: lowercase scope (test_callback.py:440-446)."""
    assert match_subject("feat(ftr-1076): add WB API key Pydantic schemas", "FTR-1076") is True
    assert match_subject("chore(ftr-1076): mark done in spec + backlog", "FTR-1076") is True


def test_match_subject_mixed_case_scope():
    """Mixed-case scope `feat(Ftr-1076)` (test_callback.py:448-449)."""
    assert match_subject("feat(Ftr-1076): something", "FTR-1076") is True


def test_match_subject_merge_with_feature_branch_prefix():
    """`Merge feature/SPEC-ID: ...` (test_callback.py:451-453)."""
    assert match_subject("Merge feature/FTR-1076: SRID — MC admin endpoint", "FTR-1076") is True


def test_match_subject_merge_autopilot_branch_into_develop():
    """`Merge autopilot/SPEC-ID into develop` (test_callback.py:455)."""
    assert match_subject("Merge autopilot/BUG-1065 into develop", "BUG-1065") is True


def test_match_subject_merge_fix_branch_em_dash():
    """`Merge fix/SPEC-ID — ...` (test_callback.py:456)."""
    assert match_subject("Merge fix/BUG-439 — restore constraint", "BUG-439") is True


def test_match_subject_case_insensitive_multi_scope():
    """Case-insensitive match on either side of a multi-spec scope
    (test_callback.py:458-460)."""
    assert match_subject("feat(area, ftr-1076, FTR-1077): both", "FTR-1077") is True
    assert match_subject("feat(area, ftr-1076, FTR-1077): both", "FTR-1076") is True


def test_match_subject_trailing_parens_task_reference_rejected():
    """`(SPEC-ID Task N)` is a task reference, not a pure spec-id token
    (test_callback.py:472-476)."""
    assert (
        match_subject("feat(billing): SRID pre-withdrawal gate (FTR-1077 Task 3)", "FTR-1077")
        is False
    )


def test_match_subject_see_also_in_message_rejected():
    """TECH-177: id in the description with a foreign scope is a cross-reference
    (test_callback.py:485-486, 525)."""
    assert match_subject("feat(other): see also FTR-925", "FTR-925") is False
    assert match_subject("feat(other): see FTR-925", "FTR-925") is False


def test_match_subject_refs_footer_rejected():
    """`Refs: SPEC-ID` footer is not a declaration (test_callback.py:488-489)."""
    assert match_subject("Refs: FTR-925", "FTR-925") is False
