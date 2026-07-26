# review agent — ADR-029 A/B, 2026-07-26

ADR-029 moved the review agent from `sonnet/xhigh` to `opus/low` on Anthropic's
published guidance, with nothing measured. This run tests that decision against
`golden-001` — six planted defects, three decoys, scored
`0.7 * recall + 0.3 * precision`.

Kept separate from `test/agents/eval-report.md`: only `review` was re-run, and
overwriting the shared report would discard the devil/planner/coder results.

| Arm | Model | Effort | Recall | Precision | **Score** | Findings | Wall | Cost |
|-----|-------|--------|--------|-----------|-----------|----------|------|------|
| A | claude-opus-5 | low | 5.0/6 = 0.833 | 3/3 = 1.00 | **0.883** | 30 | 221s | ~$1.11 |
| B | claude-sonnet-5 | xhigh | 4.0/6 = 0.667 | 3/3 = 1.00 | **0.767** | ~18 | 301s | ~$0.57 |

Threshold 0.7 — both PASS. **opus/low scores higher, so ADR-029 stands.**

## Per-defect

| ID | Defect | A (opus/low) | B (sonnet/xhigh) |
|----|--------|--------------|------------------|
| D1 | `text=True` CRLF-translates stdin → CRLF blob despite `eol=lf` | 0.5 — found the symptom chain (blob ≠ `git add`, file permanently modified, `assert_clean_lifecycle_tree` aborts) but attributed it to the missing `--path`, not to newline translation | 0 — noted the same `--path` gap and concluded "сейчас безобидно" |
| D2 | `text=True` decodes git output in locale → `UnicodeDecodeError` on Cyrillic | 1.0 — named **both** directions, in `lifecycle.py` and `orchestrator.py` | 0.5 — named the encode side on stdin only |
| D3 | `shutil.which` outranks the installer path; under the daemon's PATH a stale binary wins | 0.5 — connected the stripped PATH and named the headless/interactive version skew, but concluded `which` returns `None` | 0.5 — same connection, same wrong conclusion ("`which` в реальном деплое всегда возвращает `None`") |
| D4 | `get_available_slots(...) >= 0` is vacuous for a `COUNT(*)` | 1.0 — plus the false "no slots" log and permanent starvation | 1.0 — same; called it its hottest finding |
| D5 | `except Exception: pass` outside `.claude/hooks/` | 1.0 | 1.0 |
| D6 | `git add -A` sweeps untracked state | 1.0 — creds + staged lifecycle yaml + the ADR-025 guard interaction | 1.0 — same |

Decoys: neither arm flagged the ADR-004 hook catch, neither recommended
`Decimal` for money, neither reported a file under the 400 LOC ceiling as a
violation — both stated that check explicitly as "not a violation". Precision
ties at 1.00.

## The result that matters more than the score

**Neither arm identified the mechanism behind the real incident.** D3 is the bug
that ran the pipeline on Opus 4.6 for four months and burned ~5% of a weekly
limit in a single session. Both reviewers examined the ordering, reasoned about
the stripped PATH, and concluded `shutil.which` would return `None` — harmless.
The actual failure is the opposite: `/usr/local/bin` *is* on that PATH, so
`which` returns a stale binary that outranks the current one.

Both were reasoning from the snippet without checking what is on the box. A
reviewer restricted to a diff cannot catch an environment-dependent defect —
a limit of diff review, not of either configuration. Worth remembering before
treating a green review as coverage.

## Method notes (read before trusting the numbers)

- **n = 1.** One golden input. Enough to say ADR-029 is not obviously wrong; not
  enough to rank configurations with confidence.
- **Two variables move together.** Model and effort changed as a pair, matching
  what ADR-029 actually changed. Neither is isolated.
- Scoring is my own judgment against a key I wrote. The partial credits on
  D1/D3 are the debatable calls; the full credits on D4/D5/D6 are not.
- Cost comes from transcript usage at published rates. Arm B's `output_tokens`
  reads implausibly low (43) because it returned its report through a message
  tool rather than as final text, so **its true cost is higher than $0.57 and
  the gap is narrower than the table suggests.**
- A first attempt was discarded as invalid: the agent variants were spawned in
  the same turn they were created, before the types registered. Spawning with an
  unregistered `subagent_type` does not error — it silently falls back to a
  generic teammate on the parent session's model, with no agent system prompt,
  so both arms ran identically. Confirmed by `customAgentType` being absent from
  the spawn `meta.json`.

## Recommendation

Keep `opus/low`. It wins on recall at equal precision, and Anthropic's guidance
that Opus 5 review accuracy holds at low effort is consistent with what this
measured. Revisit if a second and third golden input reverse the ordering.

Separately: 30 and 18 findings on a seven-snippet input is a lot of surface for
a human to triage. The report bar in `review.md` ("flag any issue that could
cause incorrect behavior… only omit pure cosmetic preferences") is deliberate —
Opus 5 follows a "be conservative" instruction literally and loses recall — but
a severity-ordered cap on what reaches the operator is worth testing.
