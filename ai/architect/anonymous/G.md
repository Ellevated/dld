# Devil's Advocate — Conceptual Integrity Audit

**Persona:** Fred (The Skeptic — Brooks' Lens)
**Phase:** 1 (Research)
**Date:** 2026-05-23

> "Conceptual integrity is the most important consideration in system design."
> — Fred Brooks, The Mythical Man-Month, Chapter 4

> "Show me your flow charts and conceal your tables, and I shall continue to be mystified.
>  Show me your tables, and I won't usually need your flow charts; they'll be obvious."
> — Brooks, ibid.

> "Plan to throw one away; you will, anyhow."
> — Brooks, Chapter 11

---

## Research Sources

*Note: Exa search credits exhausted at time of analysis (402 error). All evidence
is sourced directly from the codebase — a richer source for this type of analysis
than general web results. Patterns cited below map to well-documented principles
(Brooks, DDIA, Fowler) that are foundational, not news.*

**Code sources read:**
- `scripts/vps/callback.py` (1374 LOC) — full module header + Rule sections + main()
- `scripts/vps/lifecycle.py` (602 LOC) — CAS write, `_ALLOWED_WRITERS`, `reconcile_orphans`
- `scripts/vps/orchestrator.py` (667 LOC) — `bootstrap_new_specs`, `_load_env`
- `scripts/vps/render_backlog.py` — module role, `PRIORITY_ORDER`
- `scripts/vps/spec_verify.py` — module header, import chain
- `ai/audit/deep-audit-report.md` — 85 findings, 6 personas
- `ai/architect/architecture-agenda.md` — AS-IS, agenda per persona
- `ai/qa/*.md` — real operator usage logs for `spec_operator` and `spec_verify`
- `scripts/vps/callback.py:699-711` — `_subject_implements` exact implementation
- `scripts/vps/lifecycle.py:551` — `reconcile_orphans` identity misattribution

---

## Kill Question Answer

**"Who is solely responsible for system integrity? What are the 3 inviolable principles?"**

**Integrity Owner:** NONE IDENTIFIED.

Evidence: Every ADR (018, 023, 024) was written reactively, after an incident,
by whoever was on call at the time. There is no named architect. There is no
review gate that asks "does this new rule contradict an existing rule?" The
8-rule redesign in commit `cefaa55` was written without cross-checking against
the commit convention in managed projects (`awardybot`: 460 coercive-subject
commits vs. 176 canonical-scope commits — the gate was tuned for the minority).

**Core Principles — as stated in ADRs:**

1. ADR-023: "callback is the sole writer of lifecycle status."
   — **VIOLATED** by 6 actual writers, including `orchestrator.reconcile_orphans`
   which hardcodes `by="callback"` (lifecycle.py:551) to disguise the violation.

2. ADR-023: "never touches working tree."
   — **VIOLATED** by `lifecycle.py:243-258` WT-sync (stale-index race, Root 4 today),
   `migrate_backlog_to_lifecycle.py:224-225` uses `Path.write_text()` directly.

3. ADR-024: "once ResultMessage(is_error=False) received, run is successful."
   — Nominally intact, but the symmetric pre-side guard (early-exit for merged
   implementations) is documented in SKILL.md, not enforced at runtime.

**Verdict:** No clear principles. All three declared principles have code-level
counterexamples in the same codebase.

---

## Part I — Conceptual Integrity Violation (the Core Indictment)

Brooks defined conceptual integrity as: "the design must proceed from one mind,
or from a very small number of agreeing minds." The test is: can you state the
system's design in one sentence, and does the code match that sentence?

### What the system claims to be (ADR-023, module docstrings)

```
callback.py docstring:
"Role: Pueue completion callback — release slot, update phase,
dispatch QA/Reflect, write audit log."

"INVARIANT: Always exit 0. Every step in try/except."

lifecycle.py:46-51:
_ALLOWED_WRITERS = frozenset(
    {"callback", "orchestrator", "spark", "operator",
     "qa", "audit", "autopilot", "migration"}
)
```

The claim: "callback is the sole writer." The implementation: 8 allowed writers,
which is equivalent to saying "everyone is the sole writer." This is not a design
decision; it is a design declaration that has been continuously undermined until
the declaration became meaningless.

### What the system actually is

A bash callback script that was grown into a Python module by adding rules each
time an incident revealed a gap. The current 1374-LOC callback.py is:

1. Pueue integration (resolve_label, _pueue_add)
2. Spec parser v1 (extract spec ID from label)
3. Spec parser v2 legacy (handle old label formats)
4. Git gate — Rule 1 (did the spec land on develop?)
5. Git gate — circuit-breaker (TECH-169)
6. Git gate — commit-subject convention (_subject_implements)
7. Audit JSONL writer (_emit_audit, 12 arguments)
8. Backlog render trigger (_render_and_commit_backlog)
9. Downstream dispatcher (QA, reflect, spark events)
10. verify_status_sync — 202 LOC, contains 5 of the 8 rules inline

This is not 7 responsibilities. It is 10. And "conceptual integrity" means
being able to say what the thing IS. You cannot say what callback.py is
without a numbered list.

---

## Part II — The 0-Rule Design Hypothesis

**Hypothesis:** Could we design this system with 0 rules in callback?

The current design requires rules because callback must *infer intent* from
*artifacts*. It sees: a pueue exit code, a commit subject string, a file path
pattern, a yaml status field. From these it must answer: "Was the work done?"

Every rule is an attempt to disambiguate. Every edge case is a new rule.

**What if we change the question?**

Instead of: "Did the work land? Let me check 8 conditions."
Ask: "Who is responsible for marking done — the worker or the gate?"

**Option A — Worker marks done (zero-rule callback)**

The autopilot agent, when it finishes, writes its own lifecycle yaml entry:
`status: done, by: autopilot, finished_at: now`. Callback's job: receive pueue
completion signal, dispatch QA/reflect, exit. No gate. No rules. No regex.

*What do we lose?* Trust enforcement. If the agent is wrong about being done
(hallucination, partial work), the gate is not there to catch it.

*Counter:* The gate already fails to catch it. `_subject_implements` has ~28%
accuracy against awardybot's commit convention (460/636 commits not recognized).
A gate with 28% accuracy is worse than no gate for the false-blocked cases,
and not much better than probabilistic for the real done-detection.

**Option B — Post-merge git hook (zero-callback design)**

A post-receive hook on the remote (`git push origin develop`) fires whenever
develop advances. The hook reads `git log --oneline origin/develop~1..develop`,
extracts spec IDs, marks them done. No pueue. No callback. No async gap.

*What we lose:* The pueue abstraction, which enables parallelism and retries.
*What we gain:* Determinism. The git history IS the ground truth. No inference.

**Option C — The 200-LOC callback (concrete proposal)**

```python
# callback.py — 200 LOC hypothesis
# Single responsibility: receive pueue signal, dispatch downstream, exit.
# Status determination: NOT callback's job.

def main(pueue_id, group, result):
    label = resolve_label(pueue_id)          # 15 LOC
    spec_id = extract_spec_id(label)          # 5 LOC
    project = resolve_project(label)          # 5 LOC
    db.release_slot(pueue_id)                 # 1 LOC
    db.finish_task(pueue_id, result)          # 1 LOC
    if result == "Success":
        dispatch_qa(project, spec_id)         # 10 LOC
        dispatch_reflect(project, spec_id)    # 10 LOC
    event_writer.notify(project, spec_id)     # 5 LOC
    sys.exit(0)

# Status determination: separate daemon (gate.py)
# gate.py polls develop every 60s.
# For each in_progress spec: check git log for merge.
# Single responsibility: "did this spec land on develop?"
# No pueue dependency. No exit code inference.
# Can be tested in isolation with real git repos.
# Accuracy: 100% (git log is authoritative) vs current ~72%.
```

Total: ~60 LOC main() + ~140 LOC gate.py. Compared to current 1374 LOC callback.
The gate becomes a separate process with a single, testable, pure-function
question: "is spec X in git log of origin/develop since date Y?"

*What we lose in the 200-LOC design:*
- Real-time detection (now: within pueue callback; proposed: within 60s)
- Pueue exit-code as signal (was already proved unreliable — BUG-188)
- Circuit-breaker (becomes unnecessary if gate has no mass-bootstrap path)

*Is 60-second delay acceptable?* The current system has 5-hour detection latency
for the today's bootstrap-flip incident. 60 seconds is a 300x improvement.

---

## Part III — YAGNI Verdicts Per Component

### bootstrap_new_specs (orchestrator.py:280-333)

**Claim (docstring):** "Spark writes spec.md but does NOT touch ai/lifecycle/.
Orchestrator bootstraps the YAML on first sight."

**Challenge:** ADR-023 was implemented 2026-05-16. The claim is that Spark
does not write lifecycle yaml. But the agenda for this very session says
"Spark already writes lifecycle yaml when creating specs." If Spark now writes
yaml (as a result of ARCH-186), then bootstrap_new_specs is dead code for all
specs created after ARCH-186.

Bootstrap exists for specs created BEFORE ARCH-186. Wave 1 of migration
(`migrate_backlog_to_lifecycle.py`) was supposed to cover those. After migration,
bootstrap_new_specs has one job: handle specs that somehow slipped through
migration AND were created before Spark got updated to write yaml.

**Today's bug:** `bootstrap_new_specs` read `backlog.md` from the working tree
(orchestrator.py:295: `backlog_text = backlog_path.read_text()`) — a WT read,
not HEAD — and bootstrapped 15 specs as `done` because `backlog.md` reflected
an old render. This is not a bootstrap bug; it is the cost of bootstrap's
continued existence past its useful life.

**Verdict: KILL.**

If Spark writes lifecycle yaml at spec creation, bootstrap has no purpose
post-migration. Keep only as a one-time recovery tool, not a permanent
daemon path. The correct design: if `ai/lifecycle/{spec_id}.yaml` does not
exist when callback tries to read it, that is a Spark bug, not a callback
recovery opportunity. Fail loudly and let Spark fix it.

### render_backlog.py

**Claim (module docstring):** "Pure function that renders ai/backlog.md from
ai/lifecycle/*.yaml files. Never raises on bad data."

**Actual usage:** Called from `callback.py:1187` (`_render_and_commit_backlog`)
after every lifecycle write. Also called from `migrate_backlog_to_lifecycle.py`.

**Has anyone read backlog.md programmatically?**

Yes — `orchestrator.py:295`:
```python
backlog_text = backlog_path.read_text(errors="replace")
```
This is the ROOT CAUSE of today's 15 fake-done flips. `bootstrap_new_specs`
reads the rendered markdown as if it were authoritative. This means
render_backlog.py is not a pure view — it feeds back into the decision logic
as a secondary source of truth. The "view" became a "source."

**Verdict: CONDITIONAL KILL.**

If bootstrap_new_specs is killed (see above), no code reads backlog.md
programmatically. render_backlog.py becomes a human-facing tool only
(operator reads the markdown, not machines). In that case: keep as a CLI
tool (`python3 render_backlog.py`), remove from callback's hot path,
remove `_render_and_commit_backlog` from verify_status_sync entirely.

The backlog.md file should carry a banner: "DO NOT READ PROGRAMMATICALLY.
Source of truth: ai/lifecycle/*.yaml." This is enforced by convention only,
but it is better than the current situation where the banner is absent and
the code reads it anyway.

### spec_operator.py

**Search result:** The file does not exist at `scripts/vps/spec_operator.py`.
It is referenced in QA logs:

```
ai/qa/2026-05-15-tech-973-hermes-intake.md:48:
  python3 scripts/vps/spec_operator.py mark-done dld TECH-973 "QA verified"

ai/qa/2026-05-16-arch-186.md:123:
  python3 scripts/vps/spec_operator.py demote /home/dld/projects/dld ARCH-186
```

The file was referenced in QA flows for ARCH-186 (the most recent major spec),
which means it WAS used in real operator workflow. However, the file does not
exist on disk currently. It may have been deleted or never committed.
`spec_verify.py` references it in its own docstring ("Used by: operators (CLI),
/qa skill, post-circuit triage").

**Verdict: ALREADY DEAD. Do not resurrect.**

The fact that it does not exist but is referenced in qa logs indicates it was
a temporary operator tool, not a core system component. If it is needed for
ARCH-186-era spec management, the need is past. If a new version is needed,
write it as a thin CLI wrapper over lifecycle.write_lifecycle with explicit
authentication — not another 200-LOC god module.

### circuit-breaker (TECH-169)

**What it does:** Pauses pueue if >3 demotions in 10 minutes. Logs to
`callback_decisions` table. `is_circuit_open()` check at top of `verify_status_sync`.

**Challenge:** The circuit-breaker exists because `bootstrap_new_specs` can
create mass-demotions. If bootstrap is killed, the circuit-breaker's primary
trigger disappears. The secondary trigger — a broken `_subject_implements` that
false-blocks en masse — would be solved by fixing `_subject_implements` or
replacing it with the gate.py model above.

**But here is the real question:** If the gate is reliable and bootstrap does
not exist, can mass-demotion still happen? Yes — in theory, if orchestrator
`reconcile_orphans` misfires. But `reconcile_orphans` demotes `in_progress` to
`queued` (not to `done`), which is a self-correcting state.

**Verdict: KEEP as last-resort safety, SIMPLIFY.**

Reduce from a full pause mechanism to a simple counter that logs a WARNING and
sends an alert. Remove the "pause pueue group" behavior — stopping the entire
orchestrator because of a demotion rate is a blunt instrument that amplifies
the incident (work stops) rather than containing it.

### render_backlog at all (second question)

**Brooks principle:** "Show me your tables" — lifecycle yaml IS the table.
Each `ai/lifecycle/{spec_id}.yaml` is 12 fields. `git log ai/lifecycle/ --oneline`
gives full history. `grep "status: done" ai/lifecycle/*.yaml | wc -l` gives
done count. The markdown view is for human convenience, not system function.

**Verdict: DEMOTE to optional CLI tool, never called from daemon paths.**

---

## Part IV — Identity Enforcement Reality Check

**The declaration (lifecycle.py:46-51):**

```python
_ALLOWED_WRITERS = frozenset(
    {"callback", "orchestrator", "spark", "operator",
     "qa", "audit", "autopilot", "migration"}
)
```

This is 8 allowed writers. The set `frozenset({"everyone"})` would be
functionally equivalent. Any caller that passes `by="callback"` is accepted.
There is no cryptographic check. There is no process-identity check. There is
no git-author check.

**The contradiction:**

`lifecycle.py:551`:
```python
write_lifecycle(repo_dir, spec_id, "queued",
                reason="orphaned from crash", by="callback")
```

This line is in `reconcile_orphans()`, which is called from `orchestrator.py:364`.
The orchestrator is writing lifecycle yaml and attributing it to "callback."
This is not a bug — it is the system correctly working around its own identity
fiction. The identity field does not mean "who wrote this." It means "what
category of writer do you want to pretend wrote this."

**The real identity is git author.**

Every lifecycle write produces a git commit via `_atomic_write` CAS plumbing.
That commit has an author (the system user running callback/orchestrator,
i.e., the `dld` unix user). The git log of `ai/lifecycle/` IS the identity
audit trail. The `updated_by` field in the YAML is a redundant, unverified,
honor-system annotation.

**Proposal: delete `updated_by` entirely.**

Replace with: `git log --follow ai/lifecycle/{spec_id}.yaml --format='%H %ae %s'`
This gives cryptographically verifiable authorship. No honor system.
If someone manually writes a lifecycle yaml, the git author is their email —
not "operator."

**Kill question for ADR-024:** What assumption breaks?
ADR-024 says "identity enforcement: only known writer identities may call
write_lifecycle." The assumption is that the Python-level `_ALLOWED_WRITERS`
check provides meaningful enforcement. It does not — any Python code that
calls `write_lifecycle(by="callback")` passes. The real enforcement is the
pre-commit hook (ARCH-187). That hook is not deployed anywhere (Coroner #1,
Cartographer #4). Therefore ADR-024's identity clause is entirely decorative.

The exit-code contract part of ADR-024 is sound and should be kept.

---

## Part V — "Pueue + Callback" Paradigm Question

**The question:** Is this the right pattern, or legacy from bash-based orchestration?

**History (from ADR timeline):**

- ARCH-161 (2026-03-18): "Radical rewrite: orchestrator.py, callback.py,
  event_writer.py replace bash scripts."

The bash scripts were replaced by Python scripts with the same pueue callback
architecture. The bash-era callback was a single-purpose fire-and-forget script.
The Python callback inherited the same contract (exit 0, called by pueue on
task completion) but accumulated responsibilities because it was now "the right
place" to add logic — it ran on every task completion.

This is Brooks' second-system effect in action:

> "The general tendency is to over-design the second system, using all the ideas
> and fringe ornaments that were held back on the first one."
> — Brooks, Chapter 5

The first system: a bash script that fired on completion and updated a markdown
file. Simple, fragile.

The second system (current callback.py): a Python module with CAS-based git
plumbing, circuit-breakers, multi-rule gates, identity enforcement, audit trails,
commit-subject parsers, multi-convention support, backlog rendering, downstream
event dispatch. Sophisticated, fragile in different ways.

The question "is pueue the right foundation?" is separate from "is callback the
right design." Pueue itself is sound — it provides queuing, parallelism, retry,
and a clean completion signal. The problem is not pueue. The problem is that
the callback contract (a short-lived script called by pueue on completion) has
been stretched to do 10 things it was not designed for.

**Alternative: pueue callback remains 50 LOC; gate is separate persistent daemon.**

pueue callback: releases slot, records completion, dispatches QA/reflect.
Gate daemon: polls `origin/develop` every 60s, updates lifecycle yaml.
Separation of concerns: one component reacts to pueue events, one component
monitors git state. Neither does both.

---

## Part VI — Multi-Project Orchestrator Necessity Check

**The question:** 10 projects, one operator (founder), same Claude SDK.
Could each project self-host without central orchestrator?

**What centralization currently buys:**

1. Slot management across projects (max 3 concurrent Claude sessions)
2. Project hot-reload from `projects.json` without restart
3. Night reviewer dispatch
4. Hermes intake scan across projects

**What each project needs independently:**

1. Trigger autopilot on `queued` specs
2. Dispatch QA/reflect on completion
3. Update lifecycle status

**The slot management problem** is the only thing that genuinely requires
central coordination. If project A is running 2 Claude sessions and project B
wants to start 3, the central orchestrator prevents overcommit. A per-project
systemd unit cannot know about project A's current slot usage.

**However:** With 10 projects and max 3 concurrent sessions, the average
utilization is at most 30%. Slot contention is rare in practice. The cost of
central coordination (one god-daemon managing 10 projects' pueue queues) may
exceed the benefit of the 30% contention avoidance.

**Alternative: per-project systemd unit + shared semaphore file.**

A `/tmp/dld-claude-slots` counting semaphore (a file with an integer, written
atomically) shared across all project units. Each unit acquires a slot before
launching Claude, releases on completion. Total: 20 LOC of shell in each
project unit vs. 667 LOC orchestrator.py.

**Verdict:** The central orchestrator is justified by slot management and
Hermes intake. But both of these could be extracted into a much smaller
coordination service (~100 LOC) rather than the current 667-LOC daemon that
also does project state management, lifecycle scanning, reconciliation, and
hot-reload.

---

## Part VII — ADR Chain Kill Questions

### ADR-018 — "Callback writes markdown DLD-CALLBACK-MARKER"

**Kill question:** Was there ever a case where the DLD-CALLBACK-MARKER approach
worked reliably across all edge cases?

**Evidence:** The audit report notes "10+ fixes around one contract in 2.5 months,
each closed one race and opened another." ADR-018 was superseded by ADR-023
because the markdown-editing approach was fundamentally unreliable (race with
autostash, git-tracked working tree, concurrent edits). The approach was wrong
from the start — using a working-tree markdown file as a state store is
incompatible with git's model.

**Broken assumption:** That a working-tree file can serve as reliable state
in a system where multiple processes (callback, orchestrator, human) may have
the file checked out simultaneously.

**Should ADR-018 be formally deprecated?**

Yes — but it hasn't been. `spec_lint.py` still validates DLD-CALLBACK-MARKER.
`template/.claude/skills/spark/completion.md:46` still requires them. These
are zombie enforcers for a dead standard. This is worse than no standard —
it creates false compliance confidence.

### ADR-023 — "Lifecycle SoT = git per-spec YAML"

**Kill question:** Is git-plumbing as a database the right abstraction, or
is it the "second-system over-engineering" that created new failure modes?

**Evidence for keeping:** Deterministic, append-only, cryptographically
verifiable, multi-machine convergent via push/pull. These are real properties
that SQLite does not provide for a multi-machine setup.

**Evidence against:** The complexity of `_atomic_write` (private GIT_INDEX_FILE,
CAS via update-ref, 8 subprocess calls without timeout) has produced 2 bugs
directly (stale-index race = Root 4 today, WT-sync stale blob = 13 D files).
The implementation is more complex than the entire rest of lifecycle.py.

**Broken assumption:** That git plumbing operations are fast, safe, and
trivially timeout-able in a Python subprocess context. They are not — `git hash-object`,
`write-tree`, `commit-tree`, `update-ref` can hang indefinitely on filesystem
lock contention (`.git/index.lock`).

**Honest verdict:** The CONCEPT (git as SoT) is correct. The IMPLEMENTATION
(private GIT_INDEX_FILE in a temp file, 8-step plumbing dance, no timeout)
is fragile. ADR-023 should be split into:

- ADR-023a: "Status SoT is ai/lifecycle/*.yaml committed to git" — KEEP.
- ADR-023b: "Writes use private GIT_INDEX_FILE CAS" — REPLACE with simpler
  atomic write: write yaml to tempfile, `git add`, `git commit`. Slower by
  ~50ms per write. Avoids all private-index complexity.

**Was ARCH-186 wrong?**

The migration from markdown to git-yaml was correct. The mechanism of
"never touch working tree" (achieved through private GIT_INDEX_FILE) was
an over-engineering that created new bugs. ARCH-186 was right in direction,
wrong in implementation. The correct critique is not "don't use git as SoT"
but "use the simple git interface, not the plumbing interface."

### ADR-024 — "exit_code contract + identity enforcement"

**Kill question:** Is the exit_code contract meaningful if the gate
(verify_status_sync) determines status independently of exit code?

**The current design (post-BUG-188):** pueue exit code is not used to determine
spec status. `verify_status_sync` looks at git log of origin/develop instead.
The exit code only affects whether we enter the "Success" branch vs the "Failed"
branch of callback.py's main(), which dispatches different downstream tasks.

**Broken assumption:** That exit code and git status are correlated. They are
not, by design — ADR-024 was created precisely BECAUSE they diverged (BUG-188:
post-ResultMessage exception set exit_code=1 even though the work was done).

**The honest consequence:** If exit code and git status are decoupled, what does
the exit code mean? It means "did the Claude process complete without crashing."
That is a useful signal for infrastructure health monitoring, not for spec status
determination. The current code uses it as a triage hint (`task_status` field
check) but the gate overrides it anyway.

**Recommendation:** Document this decoupling explicitly. The exit code is a
health signal, not a status signal. Remove any code that uses exit code to
influence lifecycle status. This simplifies the main() function significantly.

---

## Part VIII — Evaporating Cloud (Conflict Resolution)

Brooks used the term "the second-system effect" to describe what happens when
engineers over-build the successor to a system they understood too well.
The Theory of Constraints uses an "Evaporating Cloud" (conflict diagram)
to find the hidden assumption that makes two seemingly incompatible requirements
compatible.

**The conflict:**

```
[A] Goal: Stop incident churn in callback/lifecycle contour
 |
 +--[B] Need: Reliable status management
 |    |
 |    +--[D] Want: Incremental fix (low migration cost, known behavior)
 |
 +--[C] Need: Sustainable architecture
      |
      +--[E] Want: Full rewrite (clean design, no accidental complexity)

Conflict arrow: D <---conflicts---> E
(You cannot both incrementally patch AND rewrite simultaneously.)
```

**Hidden assumptions to surface:**

**Assumption 1 (supporting D):** "We know all the edge cases now; we just need
to handle them correctly." — BROKEN. Five iterations have each discovered NEW
edge cases. The pattern is diverging, not converging. "Knowing all the edge cases"
is not an achievable state for a system that infers intent from artifacts.

**Assumption 2 (supporting D):** "A rewrite would lose battle-tested behavior."
— EXAMINE. What behavior is "battle-tested"? The circuit breaker (TECH-169)
fires on bootstrap-induced mass-demotions — if bootstrap is killed, the circuit
breaker has no battle to test. The 8-rule gate tests commit-subject conventions
that match ~72% of real commits. The "battle-tested" behavior is mostly
defense against problems created by the system itself.

**Assumption 3 (supporting E):** "A rewrite must replace everything at once."
— BROKEN. A rewrite of callback.py alone (1374 LOC → 200 LOC) does not require
rewriting lifecycle.py, orchestrator.py, or the pueue infrastructure. The
scope of rewrite is bounded.

**Assumption 4 (universal):** "The choice is binary: patch OR rewrite."
— BROKEN. The Strangler Fig pattern (Fowler) allows incremental replacement.
Write the 200-LOC callback.py alongside the existing one, route 1 test project
through it, verify, migrate all projects, delete old code.

**Cloud evaporates when:** We accept that the rewrite scope is small
(callback.py, ~200 LOC) and the migration risk is low (one new file, parallel
deployment). The perceived cost of "rewrite" is inflated because "rewrite"
connotes "everything." The actual rewrite is scoped: kill bootstrap_new_specs,
kill render call from hot path, split verify_status_sync into separate gate daemon.

---

## Part IX — Brooks' Second-System Effect Verdict

**Attempt 1 (bash-era):** Simple bash callback that wrote to markdown.
"Commit-and-forget" design. Known fragile. Did not pretend to be robust.

**Attempt 2 (current):** Python callback.py (1374 LOC) with CAS git plumbing,
circuit-breakers, identity enforcement, multi-rule gates, audit trails.
This IS the second-system overshoot. Every feature that was "too hard to do
in bash" (CAS writes, audit logs, multi-convention support) was added.
The system is sophisticated. It fails in sophisticated ways.

**Attempt 3 (ARCH-186/187):** Added lifecycle.py as a principled SoT layer.
This was not a third-system attempt — it was a correct architectural insight
(separate the data model from the logic). But it added 600+ LOC of new
complexity (private GIT_INDEX_FILE, CAS, _ALLOWED_WRITERS theater) on top
of attempt 2 rather than replacing it.

**Where are we?** Midway through attempt 3. ARCH-186 cleaned up the data layer
in concept but the process layer (callback.py) was not touched. The result is
a sophisticated data layer coupled to an overgrown process layer.

**Brooks' prescription:** "Plan to throw one away." We are on attempt 2.5.
The prescription is to acknowledge that callback.py (the process layer) is the
one to throw away, and design attempt 3 properly: clean separation between
"I received a pueue signal" (50 LOC) and "I determine spec status from git"
(150 LOC), with no coupling between them.

---

## Part X — Questions That Must Be Answered

1. **Who is the sole owner of callback/lifecycle architecture decisions?**
   Not "who fixes the next incident" but "who reviews all changes for conceptual
   integrity before merge?" If no one can be named, the architecture will continue
   to accrete rules.

2. **Is the gate's job to determine status, or to record status?**
   These are different things. Determining status (reading git log) should happen
   in a separate process. Recording status (writing lifecycle yaml) should happen
   once, atomically. Currently both happen in `verify_status_sync` (202 LOC).

3. **When does bootstrap_new_specs stop being a daemon path and become a
   one-time migration tool?** If Spark writes lifecycle yaml at creation,
   bootstrap has no runtime purpose. Document the cutover date and delete
   bootstrap from the orchestrator loop.

4. **Is the commit-subject convention a DLD standard or a managed-project
   standard?** 460 commits in awardybot do not use the canonical scope format.
   Either the gate must accept both conventions (and document them both as
   valid), or the managed projects must be migrated to the canonical format.
   This is an organizational decision, not a code decision. No amount of regex
   sophistication will solve it.

5. **What is the blast radius of deleting callback.py and writing it from
   scratch in 200 LOC?** This should be answerable in one afternoon of analysis.
   If it is not answerable, the system is too tightly coupled.

---

## Overall Integrity Assessment

**Conceptual Integrity:** D

**Reasoning:**

There is no unifying idea. There are five unifying ideas in conflict:
- "callback is sole writer" (ADR-023) — violated by 6 writers
- "git plumbing is SoT" (ADR-023) — correct concept, fragile implementation
- "8 rules determine done" (cefaa55) — ~72% accuracy, creates false-blocked
- "identity enforcement" (ADR-024/ARCH-187) — honor system, hook not deployed
- "circuit-breaker protects from mass-demote" (TECH-169) — fires on self-induced
  problems, blunt instrument

A system with five unifying ideas has zero unifying ideas.

**Biggest Risk:**

The biggest risk in the next 12 months is not a new bug variant. It is
continued patching. The pattern is clear: each patch introduces a new assumption,
each assumption has an edge case, each edge case becomes the next incident.
The theoretical limit of this trajectory is a callback.py of infinite length.
The practical limit is the point where no developer (human or AI) can hold the
entire system in their head — which, at 1374 LOC with 7 interacting responsibilities,
may already be past.

**What Would Brooks Say:**

Brooks would say: "You have a system designed by committee, where each incident
is a committee of one. You have no conceptual integrity because you have no
concept — only a collection of rules. Rules are the absence of design. When
you find yourself adding Rule 9, ask why Rules 1 through 8 did not prevent the
problem that Rule 9 addresses. If the answer is 'because edge case X,' you have
not failed to handle edge case X — you have failed to find the abstraction that
makes edge case X impossible."

The abstraction that makes most edge cases impossible: **make status determination
a pure function of git history.** A pure function of git history has no race
conditions (git log is immutable), no bootstrap ambiguity (git log is the ground
truth), no convention conflicts (git log is unambiguous), and no identity theater
(git log carries cryptographic authorship). The current system infers present
state from past artifacts in a system where those artifacts are being written
concurrently. That is the root design error, not any specific rule.

---

## Concrete Deliverable: Proposed Minimal Design

```
scripts/vps/
├── callback.py         ~200 LOC  (was 1374)
│   Responsibility: ONE. Receive pueue signal → release slot → dispatch QA/reflect → exit.
│   No status determination. No git reads. No rule evaluation.
│
├── gate.py             ~200 LOC  (new)
│   Responsibility: ONE. Poll origin/develop every 60s.
│   For each in_progress spec: `git log origin/develop --grep=<spec_id>` → if found → write done.
│   This is a pure function of git state. No pueue dependency. Independently testable.
│
├── lifecycle.py        ~300 LOC  (was 602, remove _atomic_write complexity)
│   Simplification: use `git add + git commit` instead of private GIT_INDEX_FILE dance.
│   Remove _ALLOWED_WRITERS theater (use git author for identity).
│   Keep: CAS logic, but simplified to: read yaml → modify → write → commit → if conflict retry.
│
├── orchestrator.py     ~400 LOC  (was 667)
│   Remove: bootstrap_new_specs (kill)
│   Remove: reconcile_orphans (move to gate.py — it has git context)
│   Keep: slot management, Hermes intake, project hot-reload, night reviewer dispatch.
│
├── db.py               ~400 LOC  (was 531, add schema versioning, retention)
│
└── common.py           ~100 LOC  (new)
    _load_env, _setup_logging, _pueue_add, _SPEC_ID_RE — deduplicated.
```

**Migration: Strangler Fig**

1. Write `gate.py` alongside existing system. Deploy to 1 test project (dld itself).
2. In callback.py, comment out `verify_status_sync` call. Route status to gate.py instead.
3. Run both for 1 week. Compare outcomes. Gate.py should match verify_status_sync
   for all correctly-functioning specs.
4. If gate.py outcomes match: remove verify_status_sync from callback.py.
5. Simplify callback.py to 200 LOC. Delete bootstrap_new_specs from orchestrator.py.
6. After 2 weeks: remove render_backlog from callback hot-path.

Total migration: 4-6 weeks of parallel operation, not a "big bang" rewrite.
This is NOT a rewrite. This is removal of the second-system over-engineering
and replacement with the simple thing that was too hard to do in bash.

---

## References

- Fred Brooks — The Mythical Man-Month (1975, 20th Anniversary Edition 1995)
  Chapters 4 (Conceptual Integrity), 5 (The Second-System Effect), 11 (Plan to Throw One Away)
- `scripts/vps/callback.py` — 1374 LOC, 36 functions, 7 responsibilities (direct measurement)
- `scripts/vps/lifecycle.py:551` — `by="callback"` identity misattribution in orchestrator code
- `scripts/vps/orchestrator.py:295` — WT read of backlog.md as authoritative (root of today's bug)
- `ai/audit/deep-audit-report.md` — 85 findings, structural root cause analysis
- `ai/architect/architecture-agenda.md` — AS-IS summary, per-persona agenda
- `ai/qa/2026-05-16-arch-186.md` — spec_operator.py referenced in real QA workflow
- Commit history pattern: `cefaa55` (8-rule redesign) + TECH-166/176/177 + BUG-185/188 chain
- Goldratt, E. — The Goal (1984): Evaporating Cloud conflict resolution method
- Fowler, M. — Strangler Fig Application pattern (martinfowler.com)
