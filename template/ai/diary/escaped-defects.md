# Escaped Defects Log

Defects that passed code review but were found after merge to develop/main.

**Purpose:** Learn from review gaps to improve checklists and pre-review-check.py.

**Used by:** `/reflect` to analyze patterns and suggest new checks.

---

## How to Log

When a bug is found that should have been caught by review:

1. Create entry below using template
2. Run diary-recorder with `problem_type: escaped_defect`
3. After analysis, add check to prevent recurrence

---

## Template

### YYYY-MM-DD: BUG-XXX (escaped from TASK-YYY)

**Found by:** manual testing | user report | CI | monitoring | /audit

**Symptom:**
[What happened? Error message, unexpected behavior, etc.]

**Root cause:**
[Why it happened? Code issue, logic error, missing check, etc.]

**Why review missed it:**
[What check was missing? What should reviewer have caught?]

**Action taken:**
- [ ] Added check to `scripts/pre-review-check.py`
- [ ] Added to Code Quality checklist (`.claude/agents/review.md`)
- [ ] Added to Spec Reviewer checklist (`.claude/agents/spec-reviewer.md`)
- [ ] Added to architecture.md anti-patterns
- [ ] Other: ___

**Prevention check:**
```bash
# Command to detect this issue in future
grep -n "pattern" {files}
```

---

## Log

*(Entries below, newest first)*
