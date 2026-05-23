# LLM Systems Architecture Cross-Critique

**Persona:** Erik (LLM Architect)
**Phase:** 2 — Peer Review
**Date:** 2026-05-23
**Mode:** Retrofit

**Research basis:** Direct codebase analysis of all 7 anonymous peer reports + architecture-agenda.md +
deep-audit-report.md. Exa credits exhausted (same condition as all peers) — code is the primary source.

---

## Kill Question (my lens)

**"Can a coder-agent work on callback.py without reading the whole file?"**

Current answer: No. At 1374 LOC with 7 interleaved responsibilities, a coder-agent cannot isolate
the gate logic without loading the dispatcher, audit writer, circuit breaker, backlog renderer, and
identity logic into context. Every change requires the whole file. This is the agent ergonomics
root cause, not just a code hygiene issue.

---

## Peer Analysis Reviews

### Analysis A (Operations / Honeycomb lens)

**Agreement:** Agree

**Reasoning from LLM agent perspective:**

A's incident post-mortem framework is directly useful for agent systems. The key finding — "data
exists in logs and tables, nobody reads it in real time" — maps precisely to how AI agents operate.
Claude SDK agents produce structured outputs. If those outputs are never consumed by monitoring
tooling, the feedback loop is broken. A's "5-hour detection gap" is exactly the kind of gap that
makes it hard for the orchestrator to course-correct autonomously.

A's metrics catalog (M-01 through M-15) is the strongest concrete output in any report. The
distinction between Tier 1 (catch incident in < 5 min), Tier 2 (leading indicators), and Tier 3
(diagnostic) is exactly how agent-facing observability should be structured. Tier 1 metrics are
what an agent health-monitor tool would poll. Tier 3 is postmortem data, not agentic.

The ALERT-004 (heartbeat missed) proposal is agent-critical. An orchestrator stuck in a git
plumbing hang while holding `_write_lock` silently blocks all Claude SDK task completions. No
heartbeat = no way for an autonomous monitoring agent to detect and recover.

**Missed gaps from LLM lens:**

- A's metrics catalog assumes Prometheus/statsd as emission targets. The actual consumers of these
  metrics in this system will be other agents (the night reviewer, monitoring scripts called by
  Hermes). There is no discussion of how agents query these metrics. A tool `vps-orch health` that
  emits a structured JSON snapshot would serve agents better than a push-to-Prometheus model. The
  current system has no "single query to get system health" — an agent must grep multiple log files.
- The ALERT-005 (CircuitBreakerOpen) runbook instructs a human to check `callback_decisions` table
  via SQL. A Claude SDK agent cannot easily query SQLite. A structured CLI command `vps-orch
  circuit-status` with JSON output would make this agent-accessible.

---

### Analysis B (Evolutionary / Fitness Functions lens)

**Agreement:** Agree

**Reasoning from LLM agent perspective:**

B's fitness function framework is one of the highest-leverage proposals across all analyses, and
it is directly agent-relevant. The zombie validator finding (spec_lint.py validates DLD-CALLBACK-
MARKER that ARCH-186 deleted) is a concrete example of an agent-hostile system state: a Claude
agent running the Spark skill checks `grep '<!-- DLD-CALLBACK-MARKER-START v1 -->'` on every new
spec, gets a false-positive or false-negative, and either blocks the workflow or passes a malformed
spec silently. This is not a hypothesis — it is the current state of the completion checklist at
`template/.claude/skills/spark/completion.md:46`.

FF-02 (zombie validator detection) and FF-07 (convention drift test) are the two fitness functions
with the most direct impact on agent operation. FF-07 in particular — if `_subject_implements`
fails for 72% of real commits, the gate is not a gate; it is an obstacle. Any coder-agent working
on awardybot specs will have its work systematically false-blocked.

B's "fix train detector" (check_fix_train.py) is an evolutionary health signal for an AI-maintained
codebase. When a module accumulates > 3 incident commits in 30 days, the LLM-maintainability of
that module is degrading even if no individual change is wrong. This is measurable.

**Missed gaps from LLM lens:**

- B does not address the agent context budget problem that fitness functions themselves create.
  FF-05 (responsibility count) uses AST analysis and custom regex patterns to detect god modules.
  A coder-agent asked to pass FF-05 would need to understand the `RESPONSIBILITY_PREFIXES` patterns
  — and those patterns are defined in a test file, not in the module interface. This is the same
  documentation-in-test anti-pattern that B correctly critiques. Fitness functions should be
  self-documenting for the agents that must satisfy them.
- No mention of fitness function discoverability: how does an agent know which fitness functions
  apply to the file it is editing? Without a module-level manifest or a `## Fitness Functions`
  section in each module's docstring, agents must grep test files to discover invariants.

---

### Analysis C (Domain / DDD lens)

**Agreement:** Agree

**Reasoning from LLM agent perspective:**

C's language audit is the most direct agent-ergonomics contribution across all analyses. When
"status" has five different meanings depending on context (lifecycle, pueue, task_log, event,
map_result output), a coder-agent parsing callback.py will produce code that conflates these
meanings. This is not an LLM cognition weakness — it is a naming collision that would confuse
any developer. LLMs are particularly vulnerable because they pattern-match on term frequency:
in a 1374-LOC file where "status" appears 60+ times with 5 meanings, the agent's statistical
prior will settle on the wrong meaning.

The "gate / guard / rule / check / verify" language audit (six synonyms for different-scoped
concepts) identifies a serious agent confusion surface. A coder-agent instructed to "fix the
gate" will need to determine which of these six synonyms the requester means before writing
a single line of code.

C's proposed bounded context map and ubiquitous language tables are exactly the kind of
structured specification that makes agent operation tractable. An agent given a clear
interface — `WorkVerification.verdict: Verified | Unverified | Inconclusive` — can reason
about the contract without reading the implementation.

The five domain events proposal (SpecCreated, WorkCompleted, WorkVerified, StatusChanged,
PipelinePaused) is architecturally sound and directly improves agent coordination patterns.
Events are tools that agents can emit and subscribe to. Functions called inline are not.

**Missed gaps from LLM lens:**

- C's proposed bounded context map has 7+ components with arrows between them. An agent
  working on a single component needs a self-contained module with a published interface.
  The map diagram is valuable for human architects but does not translate to "what does
  an agent need in context to work on gate.py?" C should have specified the per-module
  API contract explicitly: inputs, outputs, errors — in a format an agent can load as
  a ~500-token interface definition.
- The aggregate root proposal (`SpecLifecycle` with `Author` value object) is architecturally
  correct but does not address the immediate agent problem: agents cannot tell which fields
  are authoritative when the aggregate is smeared across four stores. A transitional step
  should be specified: a read-only `SpecLifecycle.snapshot()` function that collapses all
  representations into one view, making the current state unambiguous for any agent reading it.

---

### Analysis E (DX / Boring Tech lens)

**Agreement:** Agree — strongest single analysis on the agent-ergonomics axis

**Reasoning from LLM agent perspective:**

E explicitly addresses agent ergonomics in the "Developer Workflow Assessment" section and
deserves credit for being the only analysis that directly quotes the architecture-agenda
Erik question: "callback.py 1374 LOC — может ли coder-агент понять 7 ответственностей
не прочитав весь файл?"

The answer E gives — "The answer is no" — is correct and well-reasoned. The proposed
decomposition (gate.py ~100 LOC, writer.py ~80 LOC, dispatcher.py ~150 LOC, each at the
400-LOC limit) is an agent context budget directly. Each file fits in one context shot.
An agent working on the gate does not need to load the dispatcher into context.

The "1-rule gate" proposal (`git log origin/develop --grep SPEC-ID`) is agent-friendly in
a way that 8-rule gate cannot be. A 5-line function has a total context cost of ~50 tokens.
An agent can understand, test, and extend it without reading anything else. The 202-LOC
`verify_status_sync` has a context cost of ~2000 tokens before the agent has read a single
dependency.

The SQLite migration proposal is agent-friendly for a different reason: SQL queries are
structured, typed, and predictable. An agent calling `db.get_spec_status(spec_id)` gets
a typed result. An agent reading `ai/lifecycle/{spec_id}.yaml` must parse YAML, handle
the case where the file doesn't exist in HEAD vs WT, and deal with the stale-index race.
SQL eliminates this class of agent error.

**Missed gaps from LLM lens:**

- E's "Wave 2 boring migration" removes lifecycle.py and replaces it with SQLite. But the
  transition period — when both exist — is not addressed from an agent perspective. During
  migration, which path does a coder-agent use? E proposes `render_backlog.py reads SQLite`
  but does not specify the agent-facing API for status reads during the transition. A bridge
  function `get_spec_status(spec_id) -> LifecycleStatus` that reads from SQLite (if present)
  and falls back to YAML would give agents a single stable interface during migration.
- The `spec_operator.py` removal recommendation is correct (YAGNI) but E does not propose
  an agent-accessible replacement. The three operations (demote, force-done, reset-circuit)
  need to become CLI tools with `--json` output flags so that monitoring agents can invoke
  them programmatically. Simply removing the CLI and replacing with "direct SQLite mutations"
  is only human-friendly, not agent-friendly.

---

### Analysis F (Data Architecture / DDIA lens)

**Agreement:** Partially Agree

**Reasoning from LLM agent perspective:**

F's data architecture analysis is technically rigorous and its schema proposals are correct.
The `dispatched_at` rename, the `blocked_code` enum, `PRAGMA user_version`, and the state
machine validation guard all improve the data layer's reliability for both human and agent
consumers.

The key agent-relevant contribution is F's clarification of the read path. Currently, an
agent querying spec status must know which of three representations is authoritative —
a 300-token explanation of ADR-023 before the agent can make a single read call. F's
proposal to make lifecycle YAML the single SoR with a clear read API reduces this to
a one-line import.

The `VALID_TRANSITIONS` dict is a machine-readable state machine that an agent can import
and reason about. "Can I transition from `blocked` to `done`?" is answered by a dict lookup,
not by reading 202 lines of `verify_status_sync`.

**Missed gaps from LLM lens:**

- F proposes keeping lifecycle YAML as the SoR (rather than E's SQLite migration). This is
  architecturally consistent with existing ADRs, but F does not address the agent interaction
  cost. Reading a spec's current status requires: `git show HEAD:ai/lifecycle/{spec_id}.yaml`
  plus YAML parsing. This is a 3-step operation with subprocess, file handle, and parse.
  An agent-facing `lifecycle.get_status(spec_id) -> LifecycleStatus` function would abstract
  this to one call. F's data architecture proposals are detailed on the write path but thin
  on the agent-facing read API.
- F's `blocked_code` enum proposal is good, but the enum values are defined inline in a code
  comment. For agents to use these correctly, the enum must be a typed Python constant that
  can be imported directly. `BLOCKED_CODES = frozenset({...})` is available in the file but
  not exposed as a module-level export with a docstring. This is the "schema as comment"
  anti-pattern that agents cannot use without reading the implementation.
- F does not address the context budget for the lifecycle module itself. After proposed changes,
  `lifecycle.py` is still ~400 LOC. An agent reading the full module to understand the write
  API will spend ~4000 tokens on context that is almost entirely implementation detail. The
  public API surface (write_lifecycle, read_lifecycle, list_by_status) should be documented
  in a ~100-token interface block at the top of the file.

---

### Analysis G (Devil's Advocate / Brooks lens)

**Agreement:** Partially Agree

**Reasoning from LLM agent perspective:**

G's "0-rule design hypothesis" is the most radical proposal and, from an agent perspective,
the most correct. The current gate design — inferring "is work done?" from commit subjects,
file path patterns, LOC diffs, and branch state — is a multi-step inference chain. Each step
can fail. Each failure mode requires another rule. The inference chain is not a tool; it is
a decision tree that an agent must walk every time it wants to understand a spec's completion.

G's "Option C: 200-LOC callback" and the separate `gate.py` daemon are directly agent-friendly.
A callback that only releases slots and dispatches QA is a single-purpose tool. An agent that
needs to modify dispatch behavior can work on 60 LOC without loading gate logic, audit JSONL
writers, or backlog renderers into context.

The Evaporating Cloud analysis correctly identifies the hidden assumption that makes "incremental
patch" seem necessary: "we know all edge cases now." This assumption is demonstrably false after
five fix iterations. G's proposal to run `gate.py` in parallel with existing `verify_status_sync`
(Strangler Fig) is the correct migration strategy — it creates a period of observable dual-truth
that validates the new design before removing the old one.

**Missed gaps from LLM lens:**

- G's proposed `gate.py` polls git every 60 seconds. This is a background daemon without a
  structured output interface. An agent that wants to know "what did the gate decide about
  TECH-055 in the last cycle?" has no tool to query. The gate's decisions should emit to a
  structured log (or SQLite table) with `spec_id, decision, timestamp, evidence` fields that
  an agent can query via a `vps-orch gate-history SPEC-ID` tool.
- G spends significant space on identity enforcement critique (deleting `updated_by`, using
  git author email). The git-author approach is correct for audit purposes but it creates an
  agent problem: an agent that calls `write_lifecycle` needs to ensure the git author is set
  correctly for its identity. G does not specify how a Claude SDK agent running in a pueue
  task would configure `GIT_COMMITTER_EMAIL` to correctly identify itself. This is an
  agent-in-the-loop design gap.

---

### Analysis H (Security / STRIDE lens)

**Agreement:** Partially Agree

**Reasoning from LLM agent perspective:**

H's threat analysis is accurate and its P0 actions (rotate TELEGRAM_BOT_TOKEN, fix bootstrap
WT read) are correct. The security analysis also surfaces agent-relevant concerns that other
analyses missed.

The audit JSONL tampering threat (H's "suppress dispatch by injecting fake entries") is an
agent coordination attack vector. If an adversarial process can inject `{"spec_id": "FTR-999",
"target_out": "blocked"}` into `callback-audit.jsonl`, the orchestrator's `scan_queued`
function will suppress dispatch of FTR-999. This is not just a security concern — it shows
that the audit JSONL is being used as an inter-agent communication channel without a contract.
The `scan_queued` anti-recency check is an implicit API over an append-only file. Any agent
that writes to this file (even legitimately) can accidentally corrupt the orchestrator's
dispatch decisions.

H's "Layer 2: input validation at trust boundaries" (validate JSONL before processing,
reject `..` paths in `_parse_allowed_files`) is agent-infrastructure work that prevents
agent mistakes from cascading. An agent that writes a malformed spec could currently trigger
a path traversal check failure deep inside `verify_status_sync` — the error would be swallowed
by one of the 19 bare `except Exception` blocks and the agent would see no actionable signal.

**Missed gaps from LLM lens:**

- H's RBAC model defines roles but does not specify how a Claude SDK agent authenticates.
  The proposed "process token in systemd unit" (Layer 1) applies to the orchestrator service.
  But agents running in pueue tasks via `claude-runner.py` are not systemd units — they are
  subprocess invocations. The ORCHESTRATOR_PROCESS_TOKEN approach does not transfer to
  pueue-launched agents without explicit environment injection in `run-agent.sh`. H should
  have specified the token injection chain: systemd env → orchestrator → pueue add → agent env.
- The HMAC proposal for audit JSONL (10 LOC to make injection detectable) is correct but
  creates an agent-unfriendly reading requirement. An agent that queries `callback-audit.jsonl`
  would need to verify HMACs before trusting results. Without an `audit_reader.py` library
  that handles HMAC verification transparently, agents will either skip verification (defeating
  the security) or fail to read valid entries. The reader interface must be specified alongside
  the writer.

---

## Ranking — Top 3 by Leverage

**1. Analysis B (Evolutionary / Fitness Functions) — highest leverage**

Fitness functions are the only proposals that are self-enforcing for agents. An agent that
breaks FF-07 (`_subject_implements` convention coverage) or FF-03 (sole writer check) will
fail CI before its change is deployed. No other proposal has this automatic enforcement
property. B's `pyproject.toml testpaths` fix (1 line, unblocks 100 tests) is the highest
ROI change in the entire analysis corpus.

**2. Analysis E (DX / Boring Tech) — second highest leverage**

The decomposition proposal (gate.py / writer.py / dispatcher.py, each ~100-150 LOC) is the
structural change that makes all other improvements possible. You cannot write good fitness
functions for a god module. You cannot add observability to a 1374-LOC file that swallows
all exceptions. The boring-is-better argument is correct: SQLite replaces 280 LOC of git
plumbing and eliminates the stale-index race class entirely.

**3. Analysis A (Ops / Honeycomb) — third highest leverage for runtime health**

The metrics catalog and SLO definitions give agents and humans a shared vocabulary for system
health. ALERT-001 (mass bootstrap detection) would have caught today's incident in 5 minutes.
At current incident rate (one per week in this contour), the ROI on 160 LOC of observability
is ~$258/week in prevented false retries plus hours of debugging time.

---

## Convergence

All 7 analyses converge on four findings:

1. **callback.py must be decomposed.** No analysis defends 1374 LOC with 7 responsibilities.
   Proposals range from 3-4 modules (E, C) to a 200-LOC callback with a separate gate daemon (G, F).

2. **bootstrap_new_specs must not read backlog.md from WT.** All analyses identify this as the
   root cause of today's incident (Root 1 from deep-audit-report.md).

3. **scripts/vps/tests/ must be in CI.** pyproject.toml testpaths is a 1-line fix that enables
   100 tests. Every analysis that mentions testing includes this.

4. **Zombie validators (spec_lint.py, completion.md:46) must be deleted.** All analyses that
   touch the ARCH-186 migration identify these as active blockers in agent workflows.

---

## Divergence

**Lifecycle SoR: YAML vs SQLite**

E proposes replacing lifecycle.py entirely with SQLite. F and Martin defend keeping git-YAML
as SoR. G proposes simplifying the CAS implementation (`git add + commit` instead of private
GIT_INDEX_FILE) but keeping git-as-SoR. This is the most significant architectural divergence
and it is unresolved across the analyses.

**From the LLM lens:** The divergence maps to different agent interaction patterns. SQLite
means agents interact via `db.get_spec_status(spec_id)` — a typed function call. Git-YAML
means agents interact via `lifecycle.read_lifecycle(repo_dir, spec_id)` — a filesystem + YAML
parse operation. Both are viable, but SQLite is more composable as a tool interface.

**Callback paradigm: incremental decomposition vs 0-rule redesign**

A, B, C, F propose incremental decomposition (split callback.py into 4 modules, each ~200 LOC).
G proposes a clean-break redesign (200-LOC callback + separate gate daemon). E proposes the
boring migration (SQLite removes git-plumbing complexity, making decomposition easier).

The convergence position is: decompose first (achieve the LOC target), redesign gate separately
(Strangler Fig — gate.py runs in parallel with verify_status_sync until validated).

---

## LLM-Specific Assessment

### Proposals that make agent operations EASIER

**E's module decomposition.** Each file fits in one context shot at ~100-150 LOC. An agent
codebase is navigable if files are small and single-purpose. The current 1374-LOC god module
requires an agent to load the entire file before understanding any single function.

**B's fitness functions (FF-07, FF-02, FF-03).** These create CI-enforced contracts that an
agent can rely on. If `_subject_implements` must pass FF-07, an agent fixing the gate knows
exactly what "fixed" means — the test suite defines it.

**C's ubiquitous language tables.** When every term has one meaning, agents can pattern-match
correctly. Five meanings for "status" is a context pollution problem.

**G's 1-rule gate.** A 5-line function is a tool an agent can understand from its docstring
alone. The 202-LOC `verify_status_sync` requires reading every line.

### Proposals that add new tool surfaces WITHOUT contracts

**A's observability metrics.** A proposes 15 metrics but does not specify how agents query
them. Counter files and heartbeat files are human-readable but not agent-accessible without
a structured query API. An agent monitoring system health needs a `vps-orch health --json`
command, not raw log files.

**H's HMAC proposal for audit JSONL.** Adds a security layer without specifying the agent
reading interface. Agents that read `callback-audit.jsonl` would need a library that handles
HMAC verification. Without `audit_reader.read_verified(path)`, agents will bypass the check.

**F's `blocked_code` enum.** The enum is defined in a code comment without a typed export.
Agents cannot import an undocumented constant and use it correctly.

### Proposals that assume "humans will operate this" when the actual user is Claude SDK agents

**H's Layer 1 authentication (process token in systemd unit).** Designed for systemd-launched
daemons. Does not address Claude SDK agents running inside pueue tasks. The injection chain
(orchestrator environment → pueue add → task environment → agent context) is not specified.

**A's Alert runbooks.** ALERT-001 through ALERT-006 all describe human investigation steps.
"Check journalctl", "grep callback-debug.log", "look at callback_decisions table via SQL."
In an autonomous system, these runbooks should be executable by a monitoring agent. The
structured format (Alert → Symptom → Immediate Action → Investigation → Resolution) is
correct but the actions must be expressible as agent tool calls, not human terminal commands.

**G's Strangler Fig migration.** Describes a 4-6 week parallel operation period supervised
by a human watching "do the gate.py outcomes match verify_status_sync?" The actual comparison
should be automated — a nightly report emitted as structured JSON that the orchestrator's
night reviewer agent can read and flag divergences.

---

## MY ADDITION: What Peers Missed About Agent-First Design

**The missing piece: an API contract layer for the orchestrator.**

All 7 analyses treat the `scripts/vps/` contour as an infrastructure layer that agents are
maintained by (coder-agents improve the code) but not consumed by (agents call the API).

This is wrong. Claude SDK agents ARE the consumers of this system at runtime:
- The autopilot agent calls `pueue add` (dispatched by the orchestrator)
- The QA agent runs after callback dispatches it
- The night reviewer reads lifecycle yaml to assess project health
- The reflect agent reads task_log to synthesize lessons

Currently there is no API. Agents interact with the orchestrator through:
- Implicit pueue task labels (format: `project_id:SPEC-ID`)
- Raw git operations on lifecycle YAML files
- Direct SQLite reads when db.py functions are unavailable
- Parsing markdown files (backlog.md, spec body)

**These are not tool interfaces. They are data substrate leakage.**

The architectural improvement that no peer proposed: a `vps-orch` CLI tool with structured
JSON output, suitable for agent use. A single binary with subcommands:

```
vps-orch status SPEC-ID         # → {"spec_id": ..., "status": ..., "blocked_reason": ...}
vps-orch health                 # → {"circuit": "closed", "slots": 2, "queue_depth": 5}
vps-orch gate-check SPEC-ID     # → {"verdict": "done", "evidence": [...commits...]}
vps-orch dispatch SPEC-ID       # → {"pueue_id": 42, "slot": 2}
vps-orch block SPEC-ID REASON   # → {"previous": "in_progress", "new": "blocked"}
```

This is the Anti-Corruption Layer that Eric (domain) proposed conceptually but no one
specified concretely for the agent-as-consumer use case. Without it:

- A QA agent verifying completion must read lifecycle YAML directly, parse YAML, check
  three representations for consistency — a 10-step operation that fails if any step
  throws an unhandled exception.
- A monitoring agent detecting stuck specs must scan `ai/lifecycle/` glob, parse 177
  YAML files, filter by `status == "in_progress"`, check `dispatched_at` age — and
  break on every schema evolution.
- The night reviewer agent must understand the SQLite schema, the YAML schema, and
  the pueue task label format to reconstruct the state of a single spec.

One CLI tool with `--json` output and typed exit codes (0=ok, 1=not found, 2=error)
would give every agent in the system a single stable interface. It can be a thin wrapper
over whatever SoR exists (YAML today, SQLite after E's migration). Schema evolution
in the SoR is hidden behind the tool contract.

This is the "tool descriptions are the UX" principle applied architecturally: the CLI
is the only API document an agent needs. If `vps-orch status --help` is self-describing,
agents can use the full orchestrator surface in < 200 context tokens.

The agent-ergonomics budget for this system should be:

| Agent task | Current context cost | Target after redesign |
|------------|---------------------|----------------------|
| Understand spec status | 300+ tokens (3 representations, ADR-023 explanation) | 50 tokens (`vps-orch status` output) |
| Understand gate decision | 2000+ tokens (verify_status_sync + deps) | 100 tokens (gate-check output) |
| Fix gate logic | 1374 tokens (full callback.py) | 150 tokens (gate.py) |
| Debug blocked spec | ~5000 tokens (logs + YAML + DB) | 500 tokens (structured diagnostics) |

Without this tool contract layer, every other architectural improvement — decomposition,
SQLite migration, fitness functions — remains partially invisible to agents at runtime.

---

## Revised Position

**Overall verdict:** The peer corpus is strong. The structural diagnosis converges correctly
on callback.py decomposition as the primary intervention. The LLM-specific gaps are not in
what peers proposed but in what they did not: the agent-as-consumer API contract layer.

**Top priority for synthesis (from LLM lens):**

1. `vps-orch` CLI with JSON output — creates the agent API contract that makes all other
   improvements observable at runtime (MISSING across all 7 analyses)
2. B's fitness functions, especially FF-07 — creates CI enforcement that agents cannot break
3. E's module decomposition — reduces per-agent context cost from ~4000 tokens to ~400 tokens
4. `pyproject.toml testpaths` fix — unblocks 100 tests that are the regression floor for
   any agent making changes in this contour

**Note:** This is input to synthesis. Final LLM-Ready validation happens in Phase 7 Step 4.

---

## References

- Architecture agenda: `/home/dld/projects/dld/ai/architect/architecture-agenda.md`
- Deep audit report: `/home/dld/projects/dld/ai/audit/deep-audit-report.md`
- Anthropic — Building Effective Agents: https://www.anthropic.com/research/building-effective-agents
- callback.py: `/home/dld/projects/dld/scripts/vps/callback.py` (1374 LOC, 7 responsibilities)
- lifecycle.py: `/home/dld/projects/dld/scripts/vps/lifecycle.py` (602 LOC, CAS plumbing)
- orchestrator.py: `/home/dld/projects/dld/scripts/vps/orchestrator.py` (667 LOC)
- architecture.md ADR chain: `/home/dld/projects/dld/.claude/rules/architecture.md`
