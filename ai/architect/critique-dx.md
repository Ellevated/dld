# Developer Experience Cross-Critique

**Persona:** Dan (DX Architect)
**Phase:** 2 — Peer Review
**Date:** 2026-05-23

---

## Peer Analysis Reviews

### Analysis A — Operations (Charity)

**Agreement:** Agree

**Reasoning from DX perspective:**

A is the most operationally grounded report in the set. The incident narrative (11:17 bootstrap flip, 16:00 human detection, 5-hour gap) is a DX catastrophe: if your dev workflow requires a human to notice by accident, that is the opposite of boring-tech reliability. Boring tech fails loudly and immediately. This system fails silently.

The minimum-viable observability table at the end is exactly the pragmatist move I respect: 160 LOC across three files covers five of six critical alerts. No Prometheus. No Grafana. No new infrastructure. Just counter files, a heartbeat, and a cron job. That is innovation-token-free and solves a real business problem (not spending $258/week on false-fail retries, not losing 5 hours detecting a bootstrap corruption).

One concern: the metrics catalog (M-01 through M-15) is thorough but risks scope creep if taken as a single delivery. The ordering is correct — Tier 1 is genuinely critical and should block everything else. Tiers 2 and 3 can wait until the architectural decomposition is done.

**Missed gaps:**

- A does not ask whether the observability debt is a symptom of over-engineering in the first place. A heartbeat file and counter files are boring fixes for a complex system. The correct long-term DX question is: if callback.py were 200 LOC with one responsibility, would you even need 15 metrics? Some of these metrics exist because the system has 10 interacting responsibilities packed into one file. Decompose first, instrument what survives.
- No mention of developer onboarding friction. An on-call developer seeing these alerts for the first time has no runbook path that does not require reading 1374 LOC of callback.py to understand the alert context.

---

### Analysis B — Evolutionary Architecture (Neal)

**Agreement:** Agree

**Reasoning from DX perspective:**

B nails the most important DX observation in the entire set: the `spec_lint.py` zombie validator produces inverted signal. A linter that validates an absent format is not merely useless — it provides false confidence. Any agent or developer who runs the linter, sees "pass," and concludes the spec is correct has been actively misled. This is resume-driven-development's worst failure mode in reverse: not building shiny new things, but maintaining shiny old things that no longer have any connection to reality.

The fitness function suite (FF-01 through FF-08) is the right kind of boring: mechanical checks that run in CI, cost nothing per run, and catch regressions before they become 5-hour incidents. The `pyproject.toml` one-line fix to include `scripts/vps/tests/` is the highest-ROI change in the entire report set: $0 compute, 100 tests enabled, zero risk.

The "fix train detector" (check_fix_train.py) is a genuinely novel DX concept: use git log as a leading indicator of architectural decay. When a single file accumulates 3+ incident-driven commits in 30 days, that is the signal to stop patching and start redesigning. This converts a lagging indicator (the next incident) into a leading indicator (the commit pattern that precedes it).

**Missed gaps:**

- B proposes fitness functions but does not address the cost of the P0 ones. The answer is: $3 compute, 1 hour wall-clock. The LLM-native cost frame is missing — these are autopilot tasks, not sprint work.
- The ADR "## Kills" section proposal is excellent governance but adds a new process artifact that itself needs maintenance. The fitness function (`test_adr_kills_complete.py`) is the right enforcement mechanism. Without it, the Kills section becomes another zombie checklist.

---

### Analysis C — Domain (Eric)

**Agreement:** Agree

**Reasoning from DX perspective:**

C's most important finding from a DX lens is the language audit: five different meanings for "status," six synonyms for "gate/guard/rule/check/verify." This is not a pedantic naming complaint. When the ubiquitous language is fragmented, every developer working in this codebase carries cognitive overhead translating between vocabularies on every read. That cognitive load is the DX cost of domain boundary violations.

The concrete business translation of the current system — "when a developer finishes a task, we check whether the work was actually merged. If yes, mark done. If no, leave it for another try. If something is clearly broken, pause everything and alert us" — is three sentences. The code is 1374 lines. The gap is the complexity budget that got spent on infrastructure instead of business problems.

The bounded context map is sound. Work Verification as a pure function (input: project_path, spec_id, allowed_files; output: Verified | Unverified) is the exact kind of boring design that makes testing trivial. You can run it against a real git repo with real commits in 10 milliseconds. No mocking. No pueue dependency.

**Missed gaps:**

- C does not estimate migration cost, which makes the proposals feel expensive. The LLM-native frame: extracting Work Verification Context into a pure function is a 2-hour autopilot task, $5. The domain event model (SpecCreated, WorkCompleted, StatusChanged) is a 4-hour task, $15. The absence of cost estimates lets the proposals feel like "big design upfront" when they are actually small, composable changes.
- The aggregate root analysis (SpecLifecycle with no enforced invariants) correctly identifies the problem but the proposed solution (transition() method with invariant checks) is standard OOP that could be implemented in lifecycle.py without any domain event infrastructure. That simple fix should be separated from the larger bounded context refactor.

---

### Analysis D — LLM Architect (Erik)

**Agreement:** Agree

**Reasoning from DX perspective:**

D is the most directly relevant to the project's actual situation: this code is maintained by AI agents, and the code that maintains AI agents is itself unmaintainable by AI agents. That is the definition of a DX crisis.

The context token count is the right metric: 10,000 tokens to safely modify `verify_status_sync` vs 3,000 after decomposition. This is a 3x context efficiency improvement that translates directly to reduced hallucination rate, reduced cost per task, and reduced time-to-correct. These are measurable DX outcomes.

The `AGENT_REFERENCE.md` proposal is exactly the kind of boring solution I want to see: 1,000 tokens of compressed information that replaces reading ADR chains plus three different config files. The ADR Summary for agents table (200 tokens, replaces 3,000+ tokens of ADR history) is elegant.

The silent failure catalogue — 6 failure modes, 2 of which produce findable agent signals — is the most damning single table in the entire report set. A system where agents can only find 2 of 6 failure modes is a system that wastes agent compute on random exploration instead of systematic diagnosis.

**Missed gaps:**

- D proposes `vps-orch.py` as a CLI tool but does not note that this is a new dependency to onboard. The onboarding question: does the agent reference document tell a new agent how to use `vps-orch.py`? If not, the tool adds DX friction before it reduces it. `AGENT_REFERENCE.md` should be written before `vps-orch.py` exists.
- The `signal_completion` API (5.2) is the most innovative proposal in the set — it inverts the architecture from inference to explicit signal. This deserves more prominent placement in the overall architecture recommendations. It is also the highest innovation-token cost of any proposal in D.

---

### Analysis F — Data (Martin)

**Agreement:** Agree

**Reasoning from DX perspective:**

F correctly identifies the backlog.md situation as a system-of-record confusion, not just a data quality problem. When a file is declared a "render" but is read as authoritative input, you have spent one innovation token on a custom git-as-database design that still cannot maintain a simple invariant about its own read path. That is not a good return on the token.

The wave-based migration strategy is pragmatic DX engineering: Wave 0 (remove bootstrap WT read) is a single-file change with no data migration risk. Wave 1 (schema cleanup) has well-defined rollback. Wave 2 (render pipeline) is deferred until the harder problems are solved. This is exactly the right ordering for a system that has been accumulating incidents.

The `VALID_TRANSITIONS` state machine guard is a boring, correct fix for `queued → done` without `started_at`. One dict and one function call. No new infrastructure.

**Missed gaps:**

- F's proposal to remove `bootstrap_new_specs` and have Spark write lifecycle YAML directly is excellent but depends on Spark skill modification. F does not estimate the Spark skill change cost. It is trivial (one `lifecycle.create_initial()` call), but if it is not specified, it will be deferred or forgotten.
- The `schema_version: 1` field in lifecycle YAML is a good forward-compatibility move, but it is also infrastructure investment with no current business problem to solve. YAGNI applies here. Defer until there is an actual schema migration to guide. The `PRAGMA user_version` for SQLite is more justified (there is an active migration needed for `cost_usd → cost_millicents`).

---

### Analysis G — Devil's Advocate (Fred/Brooks)

**Agreement:** Partially Agree

**Reasoning from DX perspective:**

G's core insight is correct and underweighted by every other peer: the 0-rule callback proposal (Option C, 200-LOC design) is not a thought experiment — it is the boring tech answer that should have been built in the first place. Status determination as a pure function of git history, running as a separate poller, is the simplest thing that could possibly work. Pueue callback releases slot and dispatches QA. Gate daemon polls git. These are two separate, independently testable, independently deployable programs.

The Evaporating Cloud analysis is the best framing in the report set for why the incremental-vs-rewrite debate is a false dilemma. The rewrite scope is bounded: callback.py, 1374 → 200 LOC. Everything else (lifecycle.py, orchestrator.py, db.py) is minimally changed. The "rewrite" connotes risk that does not exist at this scope.

Brooks' second-system effect diagnosis is exact: bash-era callback was simple and fragile. Python callback is sophisticated and fragile in new ways. The sophistication did not buy reliability — it bought new failure modes.

However, G's skepticism about the multi-project orchestrator is where I disagree with the DX analysis. The semaphore-file alternative (20 LOC per project unit) is more fragile than SQLite slot management for a system that already runs 10 projects. Per-project systemd units with shared semaphores is a classic case of solving a coordination problem with a non-atomic mechanism. Boring technology for coordination is SQLite, not semaphore files.

**Missed gaps:**

- G correctly identifies that bootstrap_new_specs should die but does not specify the concrete migration step (Spark writes lifecycle YAML). Without that step, killing bootstrap creates a gap where newly-created specs are never bootstrapped into the lifecycle system. G says "fail loudly and let Spark fix it" — that is philosophically correct but practically leaves the system broken until Spark is updated.
- G's "delete `updated_by` entirely, use git author" proposal is conceptually elegant but operationally problematic. git author is the Unix user (`dld`) for all processes. You cannot distinguish orchestrator from callback from operator from git author alone. The proposal requires GPG-signed commits, which G acknowledges — but does not estimate the DX cost of maintaining a per-service GPG key rotation in a single-person operation.

---

### Analysis H — Security (Bruce)

**Agreement:** Partially Agree

**Reasoning from DX perspective:**

H's P0 items are correctly P0. TELEGRAM_BOT_TOKEN in git history is not a DX issue — it is an actual incident that needs rotation now regardless of architecture decisions. The backlog.md WT read as an exploit path (any agent with write access to the project can influence bootstrap) is the correct security framing for what other reports treat as a data quality bug. These two are unambiguous.

The HMAC-per-line on callback-audit.jsonl (P1) is where H and I diverge. This is an innovation token being spent on a security concern that exists in a single-tenant system where the threat model already accepts "if dld user is compromised, all controls fail anyway." If we accept that premise, HMAC on the audit log is defense-in-depth for a threat that is already inside the trust boundary. The 15 LOC cost is low but the maintenance cost (rotating the HMAC key, explaining it to agents) is not zero. The boring alternative: fix bootstrap_new_specs to not read from the audit JSONL as authoritative dispatch-suppression input. If the design decision driving the threat (scan_queued reading last 200 JSONL lines) is eliminated, the threat disappears without any cryptographic machinery.

The process token for systemd (`ORCHESTRATOR_PROCESS_TOKEN`) is the pragmatic identity enforcement that avoids the GPG key management overhead of signed commits. This is correct DX-aware security.

**Missed gaps:**

- H does not note that most of the security issues are symptoms of the god-module design. A decomposed gate.py with explicit, typed inputs has a much smaller attack surface than a 1374-LOC callback.py with 19 bare exceptions and shared state between 7 responsibilities. The DX-first fix (decompose) is also the security-first fix.
- Layer 3 (register-project.sh for pre-commit hooks) is the highest-value security control but also the highest operational friction. H does not address how this interacts with the current worktree-based autopilot workflow or with managed projects that may not have git-hooks set up.

---

## Convergence

All 7 analyses converge on the following without contradiction:

**1. bootstrap_new_specs reading WT backlog.md is the immediate fix (P0)**
All reports identify this as the root cause of today's incident. A (ops), C (domain), D (LLM), F (data), G (Brooks), H (security) all name it. The fix is one line: read from HEAD, or remove the function. This is a $1 compute change.

**2. callback.py god module is the architectural root cause**
Every analysis, from every lens, arrives at the same conclusion: 1374 LOC, 7+ responsibilities, is the structural source of the recurring incident pattern. None of the 7 reports defend the current structure. This is the strongest convergence signal in the set.

**3. `pyproject.toml testpaths` one-line fix is the highest-ROI change**
B (evolutionary), D (LLM) both identify this. 100 existing tests go from invisible to CI-enforced. $0 cost, 0 risk.

**4. `_push_best_effort` at DEBUG is a correctness defect**
A (ops), B (evolutionary), F (data), H (security) all flag this. One-line fix. Zero risk. Changes from "silent multi-machine divergence" to "visible push failure." This is the definition of boring tech correctness.

**5. `_subject_implements` rejecting 460/636 awardybot commits is a gate accuracy crisis**
B (fitness function FF-07), C (domain), D (LLM), G (Brooks) all identify this. The gate has ~28-72% accuracy depending on the project. Any gate below 95% accuracy is not a gate — it is a noise generator.

---

## Divergence

**Point of divergence 1: Incremental patching vs bounded rewrite**

G argues for a clean callback.py → 200 LOC rewrite (Strangler Fig). C argues for domain event model and bounded contexts (more structural). A and B argue for observability first, then decompose. D argues minimum viable fixes now, architecture later.

The DX resolution: G and D are both right for different time horizons. D's minimum viable fixes ($3 compute, 1 hour) should happen this week. G's 200-LOC callback redesign should be a single autopilot task ($15 compute, 1 day). These are not competing — they are sequential.

**Point of divergence 2: Lifecycle YAML as git SoT vs SQLite**

G (Brooks) suggests the git-plumbing implementation is over-engineered and proposes using simple `git add + git commit` instead of private `GIT_INDEX_FILE` CAS. F (data) accepts the CAS design and proposes adding VALID_TRANSITIONS guard. H (security) accepts the CAS design with minor hardening.

The DX resolution: the design decision (git-as-SoT) is worth one innovation token and has real value (multi-machine convergence, cryptographic history, no schema migration required for status changes). The implementation complexity (private GIT_INDEX_FILE, 8 subprocess calls without timeout) is fixable without changing the design. G's simpler `git add + commit` alternative loses the no-WT-touch property that ADR-023 correctly requires. Accept the design, fix the implementation.

**Point of divergence 3: Domain events (SpecCreated, WorkCompleted, StatusChanged)**

C proposes a domain event model as the long-term solution for decoupling contexts. G argues against this as second-system over-engineering. F achieves similar decoupling through Spark writing lifecycle YAML at creation time (event-sourcing without an event bus).

The DX resolution: F's approach is boring tech. Spark writes one YAML file. That is not a domain event bus — it is a function call. C's domain event model is the correct long-term design but is an innovation token. For now: F's concrete proposal (Spark calls `lifecycle.create_initial()`), not an event broker.

---

## Ranking Top 3 by Leverage

**Rank 1: B (Evolutionary Architecture / Neal)**

Best leverage because it provides executable enforcement mechanisms for every other team's recommendations. The `pyproject.toml` fix enables 100 tests. FF-07 makes the `_subject_implements` convention gap a CI failure. FF-03 makes the sole-writer invariant machine-verifiable. FF-01 makes the 400-LOC limit a build gate. Without fitness functions, every other recommendation is a policy statement that will be forgotten under the next incident.

Cost to implement all P0+P1 fitness functions: $5 compute, 1 day wall-clock. Leverage: every future regression in the callback/lifecycle contour hits a CI gate instead of a production incident.

**Rank 2: D (LLM Architect / Erik)**

Best leverage for the actual maintenance model. This system is maintained by AI agents. If agents cannot safely work in callback.py without 10,000 tokens of context load, every task touching callback is 3x more expensive, more error-prone, and less likely to succeed. D's four minimum-viable fixes ($3 compute, 40 LOC total) reduce the silent failure rate from 6/6 to 2/6 — a 4x improvement in agent debuggability without any architectural change.

The `AGENT_REFERENCE.md` (1,000 tokens, replaces 3,000+ tokens of ADR chain navigation) is the single highest-ROI documentation artifact in the set.

**Rank 3: G (Devil's Advocate / Fred/Brooks)**

Best leverage for preventing the next phase of technical debt accumulation. The fix-train detector and the 200-LOC callback proposal address the meta-problem: why do 5 rounds of "prevention fixes" keep failing? Because the fixes are added to a module that has no executable specification of its current invariants. G's proposal to separate status determination (pure git function) from callback dispatching (pueue signal handler) is the architectural move that makes the entire incident pattern structurally impossible.

Cost: $15 compute, 1 day. A single well-specified autopilot task.

---

## DX-Specific Analysis

### Which peer proposals spend more innovation tokens?

**H's HMAC-per-line on audit JSONL** — spends half an innovation token on a cryptographic mechanism for a single-tenant system. The threat (audit log injection) exists only because scan_queued reads the JSONL as authoritative input. Fix the reader, not the log. Cost of HMAC: ~15 LOC + key management forever. Cost of fixing the reader: 0 LOC (remove the JSONL-reading anti-recency logic, which is itself fragile).

**C's domain event model** — spends one innovation token on an event bus abstraction for a system that currently has five interconnected Python files. The bounded contexts are correct. The domain events as a delivery mechanism are overkill until the contexts are actually separated. F achieves the key decoupling (Spark as lifecycle creator) without any event infrastructure.

**D's `signal_completion` API (5.2)** — explicitly proposes inverting the architecture from inference to explicit signal. This is architecturally elegant but is the most innovative proposal in the set and changes the interface contract between managed project agents and the orchestrator. One full innovation token. Worth tracking as a future state but not for the current stabilization phase.

### Which proposals add components without removing equivalent complexity?

**B's fitness function suite** adds 8 new test files and one new script (`check_fix_train.py`) without removing anything. This is justified because the tests enforce removal of dead code (zombie validator, missing test paths). But FF-05 (god module detector) and FF-06 (incident coverage bank) add ongoing maintenance overhead that is only justified after the decomposition is complete. Adding a responsibility-counting test for a 1374-LOC file that is about to be rewritten is waste. Defer FF-05 and FF-06 until after callback.py is decomposed.

**A's 15-metric catalog** risks adding metric infrastructure (even the simple counter-file approach) without removing any of the root causes that make those metrics necessary. If bootstrap_new_specs is killed and callback.py is decomposed, M-04 (blocked rate), M-05 (callback latency), and M-12 (bootstrap volume) become either irrelevant or trivially simple. Implement Tier 1 metrics now. Defer the rest until after structural changes.

**H's Layer 3 (register-project.sh)** adds a registration script and hook deployment process to 10 managed projects. The pre-commit hook it deploys (pre-commit-lifecycle-guard.mjs) is already dead everywhere (wrong `core.hooksPath`). Adding infrastructure to deploy a dead hook is a negative ROI move. Fix the hook first. Then fix the deployment. Then add the registration script.

### Which proposals solve a problem the founder doesn't have?

**F's `schema_version: 1`** in lifecycle YAML and SQLite `schema_migrations` table are forward-compatibility infrastructure for schema evolution that has never required coordination in 5+ months of operation. The SQLite migration table is justified (there is an active `cost_usd → cost_millicents` fix needed). The lifecycle YAML `schema_version` field is YAGNI. The system has 190+ YAML files and no schema migration tooling. Adding a field that promises future migration capability without delivering it is false infrastructure.

**G's multi-project orchestrator necessity check** (per-project systemd + shared semaphore) solves a complexity problem the founder does not have and replaces a boring working solution (SQLite slot management) with a fragile one (atomic semaphore files). Slot management across 10 projects is the exact use case SQLite was designed for. The 667-LOC orchestrator is large, but the semaphore alternative creates consistency hazards (two projects reading the semaphore file simultaneously, TOCTOU races) that SQLite's `BEGIN IMMEDIATE` prevents by design.

---

## What Peers Missed: The Infrastructure Innovation Trap

None of the seven reports explicitly names the over-engineering pattern that produced the current state: **the callback.py was built as if reliability requires complexity**.

The evidence is in the commit history. ADR-018 → ADR-023 → ADR-024 is not a story of progressive architectural improvement. It is a story of adding sophistication to address failures of sophistication. The CAS git plumbing replaced markdown editing because markdown editing was fragile — but git plumbing with private GIT_INDEX_FILE and 8 subprocess calls has its own fragility that has produced two bugs directly (stale-index race, WT-sync corrupted files). The 8-rule gate replaced a simpler check because the simpler check had gaps — but the 8-rule gate has a 28% false-negative rate on the dominant project convention.

The pattern: each fix increases complexity to address a failure mode of the previous complexity. The system never returns to simplicity. This is what spending innovation tokens on infrastructure looks like over time.

The correct intervention is not "add more tests to catch complexity failures" (B), not "add more observability to detect complexity failures faster" (A), not "add better type annotations to make complexity safer" (D). The correct intervention is to reduce complexity back to the level where those failures cannot occur:

- A callback that does not infer status from git history cannot have a false-blocked rate. It does not run the gate.
- A bootstrap function that does not exist cannot read a stale working tree. It is not there.
- A lifecycle YAML without 8 allowed writers cannot have identity confusion. There is one writer.

Every proposed fix in the peer reports accepts the current complexity level as fixed and proposes engineering to manage it better. The pragmatist position is: the complexity level is not fixed. The callback.py can be 200 LOC. The cost is one autopilot session ($15, 1 day). The innovation token budget for this project should be: zero tokens on infrastructure (use pueue, SQLite, Python, git — all boring), zero tokens on framework (no domain events, no event bus, no HMAC infrastructure), all three tokens on the business problem (what does "work is done" mean, how do we verify it, how do we communicate it reliably).

The system currently has three innovation tokens spent on infrastructure: CAS git plumbing (ADR-023), multi-rule gate with circuit breaker (TECH-169), identity enforcement theater (ADR-024 `_ALLOWED_WRITERS`). None of these tokens were spent on the business problem. The business problem remains: reliably determine when autopilot work is merged and transition spec status accordingly. A 60-second git polling daemon that runs `git log --grep=<spec_id> origin/develop` solves this in 50 lines, with 100% accuracy (git log is the ground truth), and zero complexity overhead.

That is the boring technology answer. None of the seven peers said it plainly. I am saying it now.

---

## Revised Position

**Verdict:** Same as Phase 1 — this is a classic over-engineered infrastructure problem, and the solution is boring tech reduction, not additional engineering.

**Final DX Recommendation:**

Week 1 ($5 compute, 2 days):
- `pyproject.toml` testpaths one-line fix (B)
- `_push_best_effort` debug → warning (A, F, H)
- bootstrap_new_specs reads HEAD not WT (everyone)
- Add GROWTH to `_SPEC_ID_RE` in callback.py (B, D)
- FF-07 test suite for `_subject_implements` (B)
- Delete zombie DLD-CALLBACK-MARKER references from spec_lint.py and completion.md (B)

Week 2 ($15 compute, 2 days):
- Write `gate.py` as pure git-polling daemon, 200 LOC (G's design, D's typed GateResult output)
- Shrink callback.py to 50-100 LOC: slot release, dispatch QA/reflect, exit. No gate.
- Spark writes `lifecycle.create_initial()` at spec creation — kills bootstrap entirely (F, G)

Week 3 ($5 compute, 1 day):
- `AGENT_REFERENCE.md` for scripts/vps/ (D)
- Heartbeat file + heartbeat monitor cron (A)
- Add M-01 (bootstrap_ops_rate counter) and M-03 (push failure counter) — Tier 1 only (A)

Total: $25 compute. Three weeks wall-clock. The system emerges with no innovation tokens spent on infrastructure, a 1-responsibility callback, an accurate gate, and executable fitness functions.

---

## References

- Dan McKinley — Choose Boring Technology (mcfunley.com/choose-boring-technology)
- A: Charity (Operations) — Tier 1 metrics catalog, 5-incident postmortem analysis
- B: Neal (Evolutionary) — Fitness function suite, fix-train detector, pyproject.toml gap
- C: Eric (Domain) — Language audit, bounded context map, aggregate root analysis
- D: Erik (LLM Architect) — Context token budgets, silent failure catalogue, AGENT_REFERENCE.md
- F: Martin (Data) — Wave migration strategy, VALID_TRANSITIONS guard, backlog.md SoR analysis
- G: Fred/Brooks (Devil) — 0-rule callback hypothesis, 200-LOC design, Evaporating Cloud
- H: Bruce (Security) — STRIDE analysis, TELEGRAM_BOT_TOKEN P0, backlog.md exploit path
