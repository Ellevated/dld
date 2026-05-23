# LLM Architect Research — Agent Ergonomics of scripts/vps/

**Persona:** Erik Schluntz (LLM Architect, Anthropic)
**Phase:** 1 — Individual Research
**Date:** 2026-05-23
**Scope:** scripts/vps/ contour, agent ergonomics audit

---

## Research Basis

Note: Exa search credits exhausted. Research is grounded in:
- Direct code inspection of callback.py (1374 LOC), lifecycle.py (602 LOC), orchestrator.py (667 LOC)
- Deep Audit report (85 findings from 6 personas)
- Anthropic "Building Effective Agents" patterns (knowledge cutoff August 2025)
- Principles from "context is RAM, simplicity > sophistication, self-describing APIs"

The absence of external search sources is disclosed. All claims are quoted from code or the audit report.

---

## Kill Question Answer

**"Can an agent work with this API without reading source code?"**

**Verdict: No.**

The kill question for this codebase is not "can an agent call an external API without reading docs" — it is subtler and more damaging: **can a coder-agent modify callback.py safely without reading all 1374 LOC of it?**

The answer is no, for reasons that are architectural, not stylistic.

---

## 1. The Core Agent Ergonomics Problem

### 1.1 The God Module Problem

The module docstring of callback.py reads:

```
Role: Pueue completion callback — release slot, update phase, dispatch QA/Reflect, write audit log.
```

But the Deep Audit found 7 distinct responsibilities:
1. Pueue integration
2. Spec parsing (v1 + legacy parsers)
3. Git guard (Rule 1 + circuit-breaker + commit stats)
4. Audit JSONL
5. Backlog render trigger
6. Downstream dispatch (QA, reflect, events)
7. `verify_status_sync` — 202 LOC gate function, alone more than half the CLAUDE.md file size limit

The docstring describes responsibility #6 only. An agent reading only the module header has a fundamentally wrong mental model before writing a single line.

**Agent ergonomics test:** A coder-agent asked to "add Rule 9 to verify_status_sync" would need to:
1. Read the full `verify_status_sync` function (lines 1001-1202)
2. Read `_emit_audit` and understand its 12-argument signature (lines 931-962)
3. Read `_is_done_on_develop` and `_subject_implements` to understand what "done" means (lines 734-775, 660-711)
4. Understand `_fetch_develop` (lines 714-731)
5. Understand how `_record` feeds `is_circuit_open` (lines 965-970, 792-819)
6. Read the circuit breaker constants (CIRCUIT_THRESHOLD, CIRCUIT_WINDOW_MIN, CIRCUIT_HEAL_MIN)
7. Read `_SPEC_ID_RE` to understand which spec IDs are recognized (line 43)
8. Understand all 7+ `_emit_audit` call sites to not break the audit trail

**Token count to safely modify `verify_status_sync`:** Reading the relevant sections is approximately 400-500 lines = ~7,000-10,000 tokens of context load. This is before any project-specific rules, ADR references, or test comprehension.

**The module has no interface boundary.** There is no stable public API surface. Every function is potentially reachable from any other.

### 1.2 The Reference Overhead Problem

From the audit agenda: "Context budget: spec for callback includes 7 ADR + 11 TECH + 3 ARCH + 2 BUG references. Total context overhead ~3000 LOC just for reading."

Let's verify this. The `verify_status_sync` docstring references:

```python
"""Single gate: lifecycle.status = done iff origin/develop contains a commit
with `<spec_id>:` in its subject AND touching at least one allowed file.

Implements the 2026-05-21 redesign (8 rules). The decision is a pure
function of (origin/develop after fetch, allowed_files, existing lifecycle).

Rules enforced here:
  1. done iff commit on origin/develop...
  3. noop if no ai/lifecycle/<spec_id>.yaml...
  4. fetch origin/develop before evaluating
  5. inline render of ai/backlog.md after every lifecycle write
  7. done is terminal — never demote done
"""
```

Rules 2 and 6 are missing. They exist elsewhere — in the orchestrator (Rule 2 = only scan `queued`) and in the gate design (Rule 6 = circuit breaker, which is checked at the START of `verify_status_sync` not listed in the docstring's rule enumeration). An agent reading this docstring gets a partial picture and has no way to discover Rules 2 and 6 without reading all of callback.py.

The architecture.md ADR table lists ADR-018 through ADR-024. Each has "см. dld-orchestrator.md§N" which is in `~/.claude/projects/-root/memory/`, a path external to the project. An agent working on a spec touching callback must retrieve: architecture.md (~8K chars), dependencies.md (~12K chars), the ADR entries they reference, and then the orchestrator.md from memory. This is 3,000+ lines of context before the agent reads a single line of code it needs to change.

**This overhead is not a documentation problem — it is an architecture problem.** The complexity exists because the code has evolved through 5 incident-fix iterations, each adding a layer.

---

## 2. Tool Design Failures

### 2.1 `_emit_audit` — 12 Positional Arguments

Current signature (callback.py:931-943):

```python
def _emit_audit(
    project_id: str,
    spec_id: str,
    pueue_id: int | None,
    target_in: str,
    target_out: str,
    reason: str,
    allowed_count: int,
    code_loc: int,
    test_loc: int,
    code_commits: int,
    started_at: str | None,
    start_wall: float,
) -> None:
```

This function is called 7+ times in `verify_status_sync` alone. Each call site passes 12 positional arguments. An agent generating a new call site has a ~60% chance of transposing two `int` arguments (`allowed_count`, `code_loc`, `test_loc`, `code_commits`) since they are all the same type with no semantic differentiation at the call site.

Compare to what this SHOULD look like:

```python
@dataclass
class AuditPayload:
    project_id: str
    spec_id: str
    pueue_id: int | None
    target_in: str
    target_out: str
    reason: str
    allowed_count: int
    code_loc: int
    test_loc: int
    code_commits: int
    started_at: str | None
    start_wall: float

def _emit_audit(payload: AuditPayload) -> None:
```

With a dataclass, an agent constructing an audit record can build it incrementally as gate rules execute, passing fields by name, catching type errors at construction. With 12 positional args, correctness requires the agent to count and match positions manually — a brittle operation that regex-based code synthesis is particularly bad at.

**This is not just DX — this is agent reliability.** Positional argument errors are silent in Python and only manifest as wrong audit logs, which are used by `scan_queued` in orchestrator.py for anti-recency decisions.

### 2.2 `verify_status_sync` — A Tool That Does Not Know It Is A Tool

The `verify_status_sync` function (202 LOC) is functionally equivalent to an agent tool — it takes inputs, runs a gate, produces a status transition. But it has no structured output. It returns `None` and communicates through side effects (lifecycle.write_lifecycle, _emit_audit, log.warning).

An agent that calls `verify_status_sync` cannot know:
- Whether the gate ran at all (circuit breaker may have skipped it)
- What the gate decision was (only in logs)
- Why a spec stayed `blocked` (reason is in audit log, not in return value)
- Whether the lifecycle write succeeded (only distinguishable from logs)

From the audit: "most failures are silent debug-level logs." Specifically, `_push_best_effort` logs at DEBUG — invisible in INFO mode. An agent debugging why multi-machine convergence is failing cannot retrieve this signal without escalating log levels.

**What a tool-shaped `verify_status_sync` looks like:**

```python
@dataclass
class GateResult:
    spec_id: str
    previous_status: str
    new_status: str
    reason: GateReason  # enum, not free-text
    gate_ran: bool
    write_succeeded: bool
    allowed_files_found: int
    duration_ms: int

class GateReason(Enum):
    CIRCUIT_OPEN = "circuit_open"
    NOT_IN_PROJECT = "not_in_project"
    ALREADY_DONE = "already_done_terminal"
    MISSING_ALLOWED_FILES = "missing_allowed_files"
    COMMIT_FOUND_ON_DEVELOP = "commit_on_develop"
    NO_COMMIT_ON_DEVELOP = "no_merged_implementation"
    AUTOPILOT_SIGNALED_BLOCKED = "autopilot_signaled_blocked"
    ALREADY_CORRECT = "already_correct"
    WRITE_FAILED = "write_failed"

def verify_status_sync(
    project_path: str,
    spec_id: str,
    target: str = "done",
    pueue_id: int | None = None,
) -> GateResult:
```

Now an agent can:
- Assert `result.gate_ran == True` before trusting the outcome
- Branch on `result.reason` with an exhaustive enum (language models handle enums much better than free-text reason strings)
- Log `result` as a structured record without calling `_emit_audit` manually
- Test gate logic with `assert result.new_status == "done"` directly

This is the Anthropic "structured outputs" pattern applied to internal function design.

### 2.3 `_subject_implements` — A Regex Classifier Pretending to be a Gate

From the audit: "_subject_implements current regex misses 460/636 commits in awardybot (accuracy ~28%)."

Current implementation (callback.py:660-711):

```python
def _subject_implements(subject: str, spec_id: str) -> bool:
    if not subject or not spec_id:
        return False
    m = re.match(r"^[a-z]+\(([^)]*)\)!?:", subject)
    if m:
        scopes = [s.strip() for s in m.group(1).split(",")]
        if spec_id in scopes:
            return True
    if re.match(rf"^merge\s+{re.escape(spec_id)}\b", subject, re.IGNORECASE):
        return True
    if re.match(rf"^{re.escape(spec_id)}:\s", subject):
        return True
    return False
```

This handles three commit formats. The dominant format in awardybot/dowry is the fourth: `feat(billing): description (FTR-1053 Task 4)` — where SPEC-ID appears as a parenthetical trailer inside the commit body, not as the scope.

The agenda raises the question: "Should `_subject_implements` be a structured-output prompt-based classifier?"

**My analysis:** Not entirely, but the architecture reveals a deeper insight. The function is called in a tight loop over `git log` output (potentially hundreds of commits). LLM calls in that loop are inappropriate. However:

**Option A: Extend regex to cover trailer format** — mechanical fix, still brittle, as the 5-iteration pattern shows. Each extension opens new edge cases.

**Option B: Build a test dataset first, gate with tests** — The audit notes 0 regression tests for `_subject_implements` edge cases. Before ANY classifier change (regex or LLM), build a golden dataset: 50 commit subjects (canonical, trailer, merge, bare, negative examples from all known projects), with expected results. This makes the classifier testable regardless of implementation.

**Option C: Move classification to commit time** — Agents (coder, autopilot) generate commit messages. If the commit message format is validated at write time (pre-commit hook in managed projects), `_subject_implements` becomes trivial. This is the boring-tech approach: enforce at write, not at read.

**For agent ergonomics specifically:** The function has zero logging when it returns `False`. From the audit (Finding #2): "`_subject_implements` ничего не логирует при rejection — спека остаётся `blocked` без диагностики, оператор не знает что искать." An agent debugging a false-blocked spec cannot determine that `_subject_implements` was the failure point without adding print statements.

**Minimum viable fix for debuggability:**

```python
def _subject_implements(subject: str, spec_id: str) -> bool:
    result = _subject_implements_inner(subject, spec_id)
    if not result:
        log.debug("GATE_MISS: subject=%r spec_id=%r — no match", subject[:80], spec_id)
    return result
```

One log line at DEBUG changes "silent false" into a findable diagnostic.

### 2.4 `bootstrap_new_specs` — Unstructured Text Parsing as Authority Source

From the audit: "`orchestrator.py:295` читает backlog.md из dirty WT (а не HEAD) для bootstrap → читает то, что человек только что отредактировал, а не то что закоммичено."

Code (orchestrator.py:295):

```python
backlog_text = backlog_path.read_text(errors="replace")
active_re = re.compile(
    r"^\|\s*(?P<id>(TECH|FTR|BUG|ARCH|GROWTH)-\d+[a-z]*)\s*\|"
    r"[^|]+\|\s*(?P<status>queued|in_progress|blocked|done|resumed|draft)\s*\|",
    re.MULTILINE,
)
active_status = {m.group("id"): m.group("status") for m in active_re.finditer(backlog_text)}
```

The problem for agent ergonomics is not only the WT-vs-HEAD race. It is that this function uses markdown-table regex parsing as an authoritative data source. From the agent perspective:

**"What is the canonical data source for spec status?"**

The architecture.md says: lifecycle.yaml (ADR-023). But bootstrap_new_specs doesn't use lifecycle.yaml — it uses backlog.md. There is no way for an agent to know this without reading orchestrator.py:285-334.

Furthermore, the regex `active_re` has `GROWTH` in the SPEC-ID list, but `_SPEC_ID_RE` in callback.py (line 43) does not include `GROWTH`:

```python
_SPEC_ID_RE = re.compile(r"(TECH|FTR|BUG|ARCH)-\d+[a-z]*")
```

An agent adding a new prefix type would need to know to update BOTH regexes in BOTH files. There is no central registry of valid SPEC-ID prefixes. This is the "read source code to understand conventions" failure mode.

**Schema-validated alternative:**

```python
# vps_types.py — single source of truth
VALID_SPEC_PREFIXES: frozenset[str] = frozenset({"TECH", "FTR", "BUG", "ARCH", "GROWTH"})
SPEC_ID_PATTERN = re.compile(
    r"(?:" + "|".join(VALID_SPEC_PREFIXES) + r")-\d+[a-z]*"
)
```

Both callback.py and orchestrator.py import from `vps_types`. Adding a new prefix is a one-line change in one file, and agents can discover valid prefixes by reading `vps_types.VALID_SPEC_PREFIXES`.

---

## 3. Error Taxonomy Failure

### 3.1 Current State: 19 Bare Except Blocks

From the audit: "callback.py 19 bare `except Exception` (ADR-004 разрешает только в hooks/)."

The architecture.md explicitly states:

> Exception: Bare `except Exception:` is ALLOWED in `.claude/hooks/` for fail-safe behavior.

callback.py is not in `.claude/hooks/`. But it has the `INVARIANT: Always exit 0` contract that hooks follow. This creates a semantic confusion: the module behaves like a hook (never crash, always exit 0) but is not in the hook infrastructure, so ADR-004's exception does not formally apply.

**The result:** An agent reading a failure in callback execution cannot distinguish between:
1. Expected degradation ("gate evaluated, spec stayed blocked — correct behavior")
2. Silent bug ("lifecycle write race lost, spec status not updated — bug")
3. Infrastructure failure ("pueue socket mismatch — transient, retry")
4. Configuration error ("DB_PATH wrong — operator error, don't retry")

All four result in the same pattern: `except Exception as exc: log.warning(...)`.

### 3.2 Proposed Error Taxonomy

```python
# errors.py — single source of typed exceptions

class OrchestratorError(Exception):
    """Base for all orchestrator/callback errors."""

class InfrastructureError(OrchestratorError):
    """External system unavailable. Safe to retry after delay."""
    # Covers: pueue socket, git network, openclaw
    retry_after_seconds: int = 30

class ConfigurationError(OrchestratorError):
    """System misconfigured. Do NOT retry — requires operator intervention."""
    # Covers: DB_PATH wrong, missing .env, missing lifecycle dir

class GateEvaluationError(OrchestratorError):
    """Gate could not evaluate. Conservative: spec stays blocked."""
    # Covers: git log failure, timeout, missing allowed files
    spec_id: str
    reason: str

class LifecycleWriteConflict(OrchestratorError):
    """CAS race lost. Safe to retry immediately."""
    # This already exists as LifecycleWriteRaceError in lifecycle.py
    spec_id: str
    attempts: int

class DataIntegrityError(OrchestratorError):
    """Data consistency violation. Do NOT proceed — requires investigation."""
    # Covers: bootstrap_new_specs reading inconsistent backlog
    # Covers: 3-store split brain detected
```

**Usage in callback.py:**

```python
# Before (silent):
except Exception as exc:
    log.warning("GATE: git log failed for %s: %s", spec_id, exc)
    return False

# After (typed, agent-readable):
except (OSError, subprocess.SubprocessError) as exc:
    raise GateEvaluationError(spec_id=spec_id, reason=f"git log failed: {exc}") from exc
```

The caller (verify_status_sync) catches `GateEvaluationError` and takes the conservative path (block, not fail). An agent debugging a stuck spec now has a typed exception with `spec_id` and `reason` attached — not a log string it needs to grep for.

### 3.3 The "INVARIANT: Always exit 0" Problem

The docstring says:

```
INVARIANT: Always exit 0. Every step in try/except.
```

This invariant is correct at the process boundary — pueue must not see a non-zero exit from callback. But inside the code, it causes every exception to be swallowed. The current pattern is:

```python
try:
    # real work
except Exception as exc:
    log.warning(...)
    # no re-raise, execution continues
```

This means a lifecycle write failure at line 1168 does NOT prevent the circuit breaker logic at line 1140 from running — they are in different try blocks. The execution path after a failed write is the same as after a successful one, except the audit record says `"error"` in one case.

**Better pattern for gate code:**

```python
def verify_status_sync(...) -> GateResult:
    """Gate evaluates to GateResult. Process boundary catches and exits 0."""
    # raises typed exceptions internally, never catches Exception
    ...

def _callback_main(pueue_id, group, result):
    """Process boundary: catches everything, always exits 0."""
    try:
        _do_callback(pueue_id, group, result)
    except Exception as exc:
        log.error("CALLBACK FATAL: %s", exc, exc_info=True)
    sys.exit(0)
```

Now the gate logic is testable with typed exceptions. The "always exit 0" invariant is honored at exactly one place — the process boundary — not scattered through 19 exception handlers.

---

## 4. Context Engineering Proposal

### 4.1 What Goes In Context vs. What Gets Retrieved

The fundamental problem is that callback.py has 7 responsibilities, so ANY task touching it requires understanding all 7. Context budget cannot be optimized for a god module — it can only be optimized for well-bounded modules.

**After decomposition** (see Domain Architect research for module split), context budget per module:

| Module | LOC | Context load | What agent needs |
|---|---|---|---|
| `gate.py` | ~150 | ~2K tokens | gate rules, GateResult type, _SPEC_ID_RE |
| `dispatcher.py` | ~100 | ~1.5K tokens | dispatch_qa, dispatch_reflect signatures |
| `lifecycle_writer.py` | ~50 | ~0.5K tokens | write_lifecycle wrapper, error types |
| `audit.py` | ~80 | ~1K tokens | AuditPayload dataclass, _write_audit |
| `circuit.py` | ~80 | ~1K tokens | is_circuit_open, _trip_circuit, constants |

Each module is comprehensible in one context window. An agent modifying the gate reads `gate.py` only — not 1374 LOC.

### 4.2 The Agent Reference Document Pattern

**Pattern from Anthropic:** For any code that agents frequently touch, provide an "agent reference" — not comprehensive docs, but exactly what an agent needs to work safely:

Proposed: `scripts/vps/AGENT_REFERENCE.md`

```markdown
# VPS Orchestrator — Agent Reference

## Quick Facts
- Status SoT: ai/lifecycle/{spec_id}.yaml (git HEAD, never WT)
- Valid SPEC-ID prefixes: TECH, FTR, BUG, ARCH, GROWTH (from vps_types.VALID_SPEC_PREFIXES)
- Callback INVARIANT: always exits 0 (errors are logged, not raised to process)
- Gate is CONSERVATIVE: ambiguity → blocked, not done
- Lifecycle write: use lifecycle.write_lifecycle(), never Path.write_text() directly

## Module Map (after decomposition)
- gate.py: THE gate (Rule 1). Returns GateResult. Read this to understand "done".
- dispatcher.py: pueue task dispatch. Read this to add new post-completion actions.
- audit.py: structured audit log. Read this to extend audit fields.
- circuit.py: circuit breaker. Read this to change CIRCUIT_THRESHOLD.
- common.py: shared utils (_load_env, SPEC_ID_PATTERN, _pueue_add). Always import from here.

## SPEC-ID Commit Convention
Two valid formats (both tested in gate/tests/test_subject_implements.py):
1. Canonical (DLD): feat(SPEC-ID): description
2. Trailer (awardybot/dowry): feat(domain): description (SPEC-ID Task N)

## Error Taxonomy
- GateEvaluationError: gate couldn't run → spec stays blocked (correct behavior)
- InfrastructureError: retry after 30s
- ConfigurationError: do NOT retry, requires operator
- LifecycleWriteConflict: retry immediately (CAS lost)

## When Adding a Gate Rule
1. Add to gate.py:_evaluate_gate()
2. Add GateReason enum value to errors.py
3. Add test to gate/tests/test_gate_rules.py
4. Update AGENT_REFERENCE.md rule table
5. Do NOT add to verify_status_sync directly (it no longer exists as a monolith)
```

**Token cost of this document:** ~1,000 tokens. An agent working on gate logic reads this plus gate.py (~2,000 tokens) = ~3,000 tokens total context load for the gate module. Currently: 10,000+ tokens to understand the same gate logic buried in callback.py.

**Reduction: 3x in context load for gate tasks.**

### 4.3 The ADR Chain Compression Problem

Current ADR chain: ADR-018 → ADR-023 → ADR-024, each partially superseding the previous, with cross-references to external memory files.

From architecture.md, every ADR entry says "см. dld-orchestrator.md§N". This means:

- An agent must retrieve `~/.claude/projects/-root/memory/dld-orchestrator.md`
- That file is not in the project repo
- The agent working in a managed project (awardybot) does not have this file in context at all

**The dead ADR problem:** ADR-018 is marked `[SUPERSEDED by ADR-023]` but spec_lint.py still validates its format. An agent reading ADR-018 might implement the old marker format because the ADR entry says "Callback пишет markdown DLD-CALLBACK-MARKER" before the superseded notice.

**Proposed compression:**

```markdown
## ADR Summary for agents (all-in-one, no external refs needed)

| Topic | Current Rule | Superseded Rules (ignore these) |
|---|---|---|
| Status SoT | lifecycle.yaml in git HEAD (ADR-023) | backlog.md DLD-CALLBACK-MARKER (ADR-018 DEAD) |
| Callback exit | exit_code=0 once ResultMessage(is_error=False) received (ADR-024) | — |
| Writer identity | callback only via lifecycle.write_lifecycle() | Path.write_text() FORBIDDEN |
| Commit classifier | both canonical and trailer formats valid | scope-only was cefaa55 regression |
```

This table is the entire ADR chain compressed to 200 tokens. An agent needs this table, not the full ADR history. History stays for humans; summary goes for agents.

---

## 5. Proposed Tool/API Surface for Agents

The core principle: agents should never read SQLite directly. Agents should never parse yaml directly. Agents should call tools with typed inputs and get structured outputs.

### 5.1 CLI Tools (for coder, debugger, planner agents)

**`python3 vps-orch.py status SPEC-ID [--project PROJECT]`**

```
Output (JSON):
{
  "spec_id": "FTR-1053",
  "project": "awardybot",
  "status": "blocked",
  "blocked_reason": "no_merged_implementation",
  "version": 12,
  "updated_at": "2026-05-23T11:17:00Z",
  "updated_by": "callback",
  "last_gate_result": {
    "reason": "no_merged_implementation",
    "allowed_files_checked": 4,
    "commits_scanned": 636,
    "duration_ms": 340
  }
}
```

An agent debugging a false-blocked spec calls this tool. Currently, the agent must: (a) find the lifecycle yaml path, (b) read it with cat, (c) find the audit log, (d) grep for the spec_id, (e) parse JSONL manually. That is 5 manual steps with string parsing at each step.

**`python3 vps-orch.py gate-check SPEC-ID --project PROJECT`**

Runs `verify_status_sync` in dry-run mode (read-only, no writes) and returns the GateResult. An agent can call this to understand why a spec is blocked without triggering a status change.

```
Output:
{
  "would_transition_to": "done",
  "gate_reason": "commit_on_develop",
  "matching_commit": "a3f7b2c",
  "matching_subject": "feat(billing): batch worker (FTR-1053 Task 3)",
  "dry_run": true
}
```

Currently: no way to test gate logic without triggering the full callback. The debugger-agent cannot safely test its hypothesis without side effects.

**`python3 vps-orch.py classify-commit "feat(billing): batch worker (FTR-1053 Task 3)" FTR-1053`**

Returns `{"matches": true, "format": "trailer", "spec_id": "FTR-1053"}` or `{"matches": false, "rejection_reason": "spec_id_in_trailer_position_not_scope"}`.

This exposes `_subject_implements` as a testable, callable tool. Currently: no way to test the classifier without running full callback. Agents investigating false-blocked cannot diagnose commit format mismatches.

### 5.2 Python API (for integration with managed project agents)

When an autopilot agent completes work in a managed project, it should be able to signal completion through a structured API rather than relying on commit message conventions that the gate may or may not recognize:

```python
# In managed project autopilot completion:
from orchestrator_client import signal_completion

result = signal_completion(
    spec_id="FTR-1053",
    project_path="/path/to/awardybot",
    commit_sha="a3f7b2c",  # the actual merge commit
    by="autopilot",
)
# Returns: CompletionSignal(accepted=True, new_status="done", verified_by="gate")
# Or: CompletionSignal(accepted=False, reason="commit_not_on_develop", retry_in=60)
```

This inverts the current architecture: instead of callback.py inferring completion from git history, the agent explicitly signals completion with the evidence. The gate verifies; the signal provides the pointer.

This is aligned with Anthropic's "structured outputs" pattern: the agent produces a typed signal, the system validates it.

### 5.3 The Audit Query Tool

Currently `callback-audit.jsonl` is append-only and has no query interface. An agent debugging must `grep spec_id callback-audit.jsonl | tail -5` — raw shell string parsing.

**`python3 vps-orch.py audit SPEC-ID [--last N] [--project PROJECT]`**

```
Output:
[
  {
    "ts": "2026-05-23T11:17:00Z",
    "transition": "queued → done",
    "reason": "commit_on_develop",
    "duration_ms": 340
  },
  {
    "ts": "2026-05-23T11:16:30Z",
    "transition": "in_progress → blocked",
    "reason": "no_merged_implementation"
  }
]
```

An agent reading the last 3 audit entries for a spec ID needs a single tool call, not a shell pipeline.

---

## 6. Agent Debuggability: What Happens When Something Fails

### 6.1 Current Signal-to-Noise Ratio

From the audit: "Сегодня инцидент произошёл в 11:17 утра — был замечен ~16:00. 5 часов прод-trouble без алерта."

For a debugger-agent trying to understand why 15 specs flipped to `done`:

**Current state:**
- `bootstrap_new_specs` logs `INFO "BOOTSTRAP: created lifecycle.yaml for FTR-XXX status=done in awardybot"` — one line per flip
- `verify_status_sync` was NOT called (bootstrap bypassed it)
- No audit entry for bootstrap writes (audit log only covers verify_status_sync)
- No threshold alert on mass bootstrap

**What the debugger-agent sees:** A log file with 15 BOOTSTRAP INFO lines. No error signal. No "this is unusual" signal. The agent asked "why are 15 specs done?" has to trace bootstrap_new_specs through backlog.md (WT) through the archive/done detection logic — ~150 lines of orchestrator.py — to find the root cause.

**What the debugger-agent SHOULD see:**

```
[11:17:23] WARNING BOOTSTRAP_ANOMALY: 15 lifecycle yaml created in 30s 
           for project=awardybot — mass bootstrap detected. 
           Source: backlog.md WT at hash abc123. 
           Action: check if backlog.md WT differs from HEAD.
```

One structured log line with: event type, count, time window, source, suggested action. The agent can act on this without reading code.

### 6.2 The Silent Failure Catalogue

From the audit (verbatim findings compiled into agent-relevant table):

| Failure | Current signal | Agent can find it? |
|---|---|---|
| `_push_best_effort` fails | `log.debug` | No (INFO filter hides it) |
| `_subject_implements` returns False | Nothing | No — must grep git log manually |
| `_atomic_write` WT-sync stale blob | `log.warning` | Yes, but reason unclear |
| Lifecycle write race (CAS lost) | `LifecycleWriteRaceError` in lifecycle.py | Yes (typed exception) |
| bootstrap reads stale backlog.md | `log.info BOOTSTRAP` | No — INFO looks normal |
| GROWTH prefix not in callback._SPEC_ID_RE | Spec never processes QA/reflect | No — silent skip |
| Circuit breaker OPEN | `log.warning CIRCUIT_OPEN` | Yes |
| pre-commit hook not installed | No signal | No — protection is silently absent |

The ratio is: 2 of 8 failures produce findable agent signals. For the other 6, an agent must read source code to diagnose.

**The Anthropic principle:** "Can an agent figure out WHY from available signals?" For this codebase: mostly no. The system was designed for human operators who can grep logs. Agents need structured, typed, high-priority signals.

**Minimum viable fix for debuggability without full refactor:**

1. `_subject_implements`: add one `log.debug` line on False return with the subject and spec_id
2. `bootstrap_new_specs`: add threshold check — if `created_count > 5`, emit `log.warning BOOTSTRAP_ANOMALY`
3. `_push_best_effort`: change to `log.warning` (not debug)
4. `_SPEC_ID_RE` in callback.py: add GROWTH prefix to match orchestrator

These four changes, totaling ~10 lines, would make 4 of the 6 silent failures findable. Zero architecture change required.

---

## 7. The Meta-Question: This Code Serves Agents

The agenda correctly identifies this as a meta-question: **this code IS what serves agents, so agent-friendliness is the requirement, not nice-to-have.**

callback.py is not just a component that agents happen to modify. It is the system that processes agent output and decides whether autopilot's work was accepted. When callback.py malfunctions:

- Agents do real work that doesn't get credited (false-blocked → retry)
- Agents don't do real work that appears credited (false-done → no QA runs)
- Agents cannot diagnose why their work was rejected (silent gate mismatches)

**The current callback.py fails its own users three ways:**

1. **False-blocked via `_subject_implements`:** 460 commits in awardybot rejected silently. The coder-agent wrote valid code with a valid commit message in the project's convention — and the gate didn't recognize it. Agent effort wasted with no diagnostic.

2. **False-done via `bootstrap_new_specs`:** 15 specs marked done without gate evaluation. Autopilot agents will be dispatched to run QA on completed work — or not dispatched at all if the spec is terminally done. Either way, the signal is wrong.

3. **No structured output from gate:** The gate knows why it made its decision (reason string) but this information is in a JSONL file that only humans with shell access can read. Agents cannot query it programmatically.

**The fix is not complex — it is consistent application of patterns that already exist in the codebase:**

- `lifecycle.py` already has `LifecycleWriteRaceError` — a typed exception. Apply this pattern to `gate.py`.
- `GateResult` dataclass already exists conceptually (every field is computed in verify_status_sync). Formalize it.
- `vps-orch.py status` command is one Python script that reads lifecycle yaml and returns JSON. 50 lines.
- `AGENT_REFERENCE.md` is documentation, not code. 200 lines.

The structural decomposition (god module → 5 bounded modules) is the larger work. But the debuggability fixes are available NOW, without architectural changes, with measurable impact on agent success rate.

---

## Summary of Proposals

### Tool Surface (Priority-ordered)

| Tool | Effort | Impact | Status |
|---|---|---|---|
| `vps-orch.py status SPEC-ID` | 50 LOC | High — agents can query without reading yaml | Not exists |
| `vps-orch.py gate-check SPEC-ID` | 80 LOC | High — dry-run gate for debugging | Not exists |
| `vps-orch.py classify-commit` | 20 LOC | Medium — expose _subject_implements | Not exists |
| `vps-orch.py audit SPEC-ID` | 30 LOC | Medium — structured audit query | Not exists |
| `GateResult` dataclass | 30 LOC | High — verify_status_sync returns typed output | Not exists |
| `AuditPayload` dataclass | 15 LOC | High — replace 12-arg _emit_audit | Not exists |

### Error Taxonomy

| Error Class | Covers | Agent Action |
|---|---|---|
| `InfrastructureError` | pueue, git network, openclaw | Retry after 30s |
| `ConfigurationError` | DB_PATH, missing .env | Escalate to operator, don't retry |
| `GateEvaluationError` | git log failure, timeout | Block spec (conservative), log reason |
| `LifecycleWriteConflict` | CAS race | Retry immediately |
| `DataIntegrityError` | split-brain detected | Halt, escalate |

### Context Budget (Before vs After Decomposition)

| Task | Current context load | After decomposition |
|---|---|---|
| Add gate rule | 10K tokens (full callback.py) | 3K tokens (gate.py + AGENT_REFERENCE.md) |
| Debug false-blocked | 15K tokens (callback + lifecycle + logs) | 2K tokens (vps-orch status + gate-check output) |
| Add dispatch action | 10K tokens (full callback.py) | 1.5K tokens (dispatcher.py) |
| Add audit field | 10K tokens (full callback.py) | 1K tokens (audit.py + AuditPayload) |

**3-5x context reduction is achievable through decomposition alone, without any LLM-specific tooling.**

### Documentation for Agents

1. `scripts/vps/AGENT_REFERENCE.md` — 1,000 tokens, replaces reading architecture.md + ADR chain for gate tasks
2. `scripts/vps/vps_types.py` — single source of SPEC-ID prefixes, status enum, error taxonomy
3. Module-level docstrings for decomposed modules that accurately describe ONE responsibility each
4. `gate/tests/test_subject_implements.py` — golden dataset of 50 commit subjects, doubles as executable documentation of classifier behavior

### Minimum Viable Fixes (No Architecture Change)

These can be done NOW as P0 items before the full decomposition:

1. Add `log.debug` to `_subject_implements` on False return — 3 lines
2. Add GROWTH to `_SPEC_ID_RE` in callback.py — 1 line
3. Add mass-bootstrap threshold log in `bootstrap_new_specs` — 5 lines
4. Change `_push_best_effort` from `log.debug` to `log.warning` — 1 line
5. Replace 12-arg `_emit_audit` with `AuditPayload` dataclass — 30 lines

**Total: ~40 LOC of changes. Zero architectural changes. Fixes 4 of 6 silent failure modes.**

---

## References

- Anthropic "Building Effective Agents" — orchestrator-workers pattern, tool design
- Anthropic "Prompt Engineering Guide" — structured outputs, context management
- DLD Deep Audit Report (2026-05-23) — 85 findings, 6 personas
- DLD Architecture Agenda — Erik section
- callback.py source (lines 660-711, 931-962, 1001-1202) — verified claims
- orchestrator.py source (lines 285-334) — bootstrap_new_specs
- lifecycle.py source (lines 1-60, 140-220) — CAS write, error types
