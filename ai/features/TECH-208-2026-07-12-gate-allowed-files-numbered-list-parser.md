# Bug Fix: [TECH-208] Gate Allowed Files parser rejects numbered-list format

**Priority:** P1 | **Date:** 2026-07-12

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Symptom

Specs whose `## Allowed Files` section is written as a numbered list
(`1. \`path\``) get `blocked_reason: empty_allowed_files` from the gate even
when the implementation is fully merged to `develop`. Confirmed live impact:
6 specs sitting falsely blocked despite verified merged work —
plpilot BUG-355 ($19.99/34 turns of real autopilot work), plpilot TECH-343,
TECH-345, TECH-342 (a security fix — leaked `cron_secret` neutralization),
awardybot BUG-1395, awardybot FTR-1394. Grep across `ai/features/*.md`
(files touched since 2026-06-28) found the numbered-list pattern in **22**
spec files across awardybot and plpilot over 3 weeks.

## Root Cause (5 Whys Result)

1. Why does the gate block BUG-355 despite merged implementation? →
   `callback._parse_allowed_files()` returns an empty list for its spec file.
2. Why does the parser return empty? → `_ALLOWED_FILES_V1_BULLET_RE` in
   `scripts/vps/callback.py:453` (mirrored in `scripts/vps/gate_logic.py:48`)
   only matches lines starting with `- ` + backticked path. BUG-355's spec
   uses `1. \`path\`` (numbered), which the regex never matches.
3. Why does the spec use numbered lines? → `.claude/skills/spark/bug-mode.md`
   (Quick Bug Mode's own spec template, lines 122-124) shows the example
   Allowed Files block as a numbered list — directly contradicting the
   canonical v1 dash-bullet format.
4. Why does `bug-mode.md` disagree with the canonical format? → historical
   drift. `feature-mode.md` was hardened under TECH-167/175/ARCH-186 with an
   explicit dash-bullet canonical format description and a Phase 5.5
   Allowlist Linter that hard-blocks non-conforming specs before they're
   ever committed. `bug-mode.md`'s template was never updated to match, and
   Quick Bug Mode has no equivalent linter step.
5. Why wasn't this caught at spec-creation time? → Quick Bug Mode
   (`bug-mode.md`) has no Phase-5.5-equivalent linter in its completion
   flow, so a malformed Allowed Files section silently passes into a
   `queued` spec. It only surfaces weeks later, after real implementation
   work is merged, as a gate false-block — which then looks like a gate bug
   rather than what it actually is: a template/parser format mismatch that
   existed since spec creation.

**ROOT CAUSE:** `bug-mode.md`'s spec template teaches a numbered-list
Allowed Files format that the gate parser (`callback.py` /
`gate_logic.py`) never supported, and Quick Bug Mode has no linter to catch
the mismatch before the spec is committed and pushed.

## Reproduction Steps

1. Create a spec with:
   ```
   ## Allowed Files
   <!-- callback-allowlist v1 -->
   1. `some/file.py` — reason
   ```
2. Merge implementation touching `some/file.py` to `develop`.
3. Run `callback._parse_allowed_files(spec_path)`.
4. Expected: `['some/file.py']`. Got: `[]` — the guard then reports
   `blocked_reason: empty_allowed_files` even though the merge exists.

## Fix Approach

Two-pronged — fix forward (template) AND fix backward-compatible (parser),
since 22 already-created specs use the numbered format and some may still
be in flight:

1. **Parser fix** (`callback.py` + `gate_logic.py`, kept in sync per
   `dependencies.md`): extend `_ALLOWED_FILES_V1_BULLET_RE` matching to also
   accept numbered-list items (`^\d+\.[ \t]+\`...\``) alongside the existing
   dash-bullet pattern — e.g. try the dash regex first, fall back to a
   numbered-list regex with the same capture group, or combine into one
   alternation. Do not change the capture semantics (same file-path
   extraction rules: must end in `.ext`, backticked, optional trailing
   free text).
2. **Template fix** (`bug-mode.md` lines 122-124): change the example
   Allowed Files block to use `- \`path\`` dash-bullets, matching
   `feature-mode.md`'s canonical format exactly (including the
   `<!-- callback-allowlist v1 -->` marker placement).
3. **Regression tests**: add cases to `scripts/vps/tests/test_gate_logic.py`
   mirroring the existing dash-format parser tests, covering: numbered list
   with `1.`/`2.` markers, mixed numbering gaps, and confirming dash-format
   parsing is unaffected (no regression).

**Explicitly out of scope:** adding a Phase-5.5-equivalent linter to Quick
Bug Mode is a larger process change (would need its own spec) and is not
required to fix the immediate parser/template mismatch — noted here for
future reference, not part of this fix.

## Impact Tree Analysis

### Step 1: UP — who uses?
- [ ] `callback.py::_parse_allowed_files` → used by `verify_status_sync` /
  the implementation guard on every autopilot completion (all projects)
- [ ] `gate_logic.py::parse_allowed_files` → used by `gate-daemon.py`
  (shadow polling) and `orchestrator.py`'s `scan_queued` reconciliation gate

### Step 2: DOWN — what depends on?
- [ ] No new external dependencies; pure regex extension

### Step 3: BY TERM — grep entire project
| File | Line | Status | Action |
|------|------|--------|--------|
| scripts/vps/callback.py | 453 | needs fix | extend bullet regex |
| scripts/vps/gate_logic.py | 48 | needs fix | extend bullet regex (keep in sync with callback.py) |
| .claude/skills/spark/bug-mode.md | 122-124 | needs fix | template → dash-bullets |
| template/.claude/skills/spark/bug-mode.md | (mirror) | needs fix | same template drift likely present — sync per template-sync.md |
| scripts/vps/tests/test_gate_logic.py | — | needs new tests | numbered-list regression cases |

### Verification
- [ ] All found files added to Allowed Files

## Research Sources

- Live incident: 6 falsely-blocked specs found and manually verified
  (`spec_operator.py force-done`) 2026-07-12 during orchestrator health
  check — plpilot BUG-355/TECH-343/TECH-345/TECH-342, awardybot
  BUG-1395/FTR-1394.
- `.claude/skills/spark/feature-mode.md:702-707` — canonical regex SSOT
  comment block, confirms dash-bullet is the intended format.

## Allowed Files

<!-- callback-allowlist v1 -->

- `scripts/vps/callback.py` — extend `_ALLOWED_FILES_V1_BULLET_RE` matching to accept numbered-list items
- `scripts/vps/gate_logic.py` — same regex extension, kept in sync with callback.py
- `.claude/skills/spark/bug-mode.md` — fix Allowed Files template example to use dash-bullets
- `template/.claude/skills/spark/bug-mode.md` — sync same template fix (template-sync.md)
- `scripts/vps/tests/test_gate_logic.py` — add regression tests for numbered-list parsing

## Definition of Done

- [ ] Root cause fixed — parser accepts both dash and numbered list formats
- [ ] `bug-mode.md` template (root + template copy) uses dash-bullets, matching `feature-mode.md`
- [ ] Regression test added confirming numbered-list specs parse correctly
- [ ] Existing dash-format parsing has no regression (all current tests in `test_gate_logic.py` pass)
- [ ] No new failures in `./test fast`
