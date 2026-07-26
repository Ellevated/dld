# Scoring Rubric: Code Quality Reviewer

A reviewer is judged on two things only: how many real defects it finds, and how
much noise it adds. Prose quality is not scored — a terse list that catches
everything beats an essay that catches half.

The input carries **six planted defects** and **three decoys**. Score against
this answer key, not against how confident the review sounds.

## Planted defects (recall — weight: dominant)

| ID | File | Defect | Credit for |
|----|------|--------|-----------|
| D1 | lifecycle.py | `text=True` newline-translates stdin, so the yaml blob reaches `git hash-object` with CRLF on Windows despite `.gitattributes eol=lf` | naming newline translation on **stdin** specifically |
| D2 | lifecycle.py | `text=True` decodes git output with the locale codec — Cyrillic `blocked_reason` raises `UnicodeDecodeError` on a cp1251 host | naming the **decode** side, not just "add encoding" |
| D3 | claude-runner.py | `shutil.which()` is ranked above `~/.local/bin/claude`; under the daemon's PATH (no `~/.local/bin`) a stale system binary silently wins over the self-updating launcher | connecting the ordering to the **stripped PATH** |
| D4 | orchestrator.py | `get_available_slots(...) >= 0` compares a `COUNT(*)` against 0 — always true, so the guard does nothing and the spec's provider always wins | identifying the condition as **vacuous** |
| D5 | render_backlog.py | `except Exception: pass` silently swallows a failed backlog write; this is not a hook, so ADR-004 does not apply | flagging **silent** failure, not merely "bare except" |
| D6 | deploy.sh | `git add -A` stages untracked runtime artifacts (pid/heartbeat files) alongside the intended change | naming the **untracked-sweep** risk |

- Full credit for a defect requires the mechanism, not just the location.
  "lifecycle.py has an encoding issue" is half credit for D1+D2 combined.
- D1 and D2 share one line of code but are two distinct failure modes. A review
  that collapses them into one gets credit for one.

## Decoys (precision — weight: high)

These are correct as written. Flagging any of them as a defect is a false positive.

| ID | File | Why it is correct |
|----|------|-------------------|
| N1 | pre-edit-guard.mjs | Bare `catch` + `exit(0)` is REQUIRED fail-safe behaviour in `.claude/hooks/` (ADR-004) |
| N2 | pricing.py | Integer cents with `//` floor division is the mandated money pattern (ADR-001); no float appears |
| N3 | pricing.py / all files | 380 LOC is under the 400 LOC ceiling; no file in the input violates it |

Deduct for each decoy flagged as a real problem. Suggesting N2 "should use
Decimal" is a direct contradiction of project rules and costs double.

## Scoring

```
recall     = (defects found, weighted by mechanism credit) / 6
precision  = 1 - (decoys flagged / 3)
score      = 0.7 * recall + 0.3 * precision
```

- Additional genuine issues outside the answer key (e.g. `_run` ignores a
  non-zero returncode, `hash-object` output unvalidated) are neither rewarded
  nor penalised — note them separately as bonus observations.
- Severity labels must be present and defensible. A review that marks D4 as
  "critical" and D6 as "critical" without distinction shows no calibration —
  note it, but do not deduct.
- Format, tone, and section structure are NOT scored.
