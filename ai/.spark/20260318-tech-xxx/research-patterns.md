# Pattern Research — DLD Cycle E2E Reliability (3 breaks + smoke test)

## Context

Three concrete breaks prevent the pipeline from completing a full end-to-end run:

1. **Break 1 (qa-loop.sh)** — `qa-loop.sh` receives `SPEC_ID` but passes `/qa SPEC_ID` as a freeform
   prompt to Claude. The agent cannot find the spec, asks the user, gets `permission_denied`, and
   returns exit 0. False pass.
2. **Break 2 (artifact-scan regex)** — `openclaw-artifact-scan.py` matches only
   `YYYYMMDD-HHMMSS-SPEC-ID.md`, but `qa-loop.sh` writes files as `2026-03-17-tech-151.md`
   (ISO date, lowercase). Files fall through as `unknown`.
3. **Break 3 (topic_id NULL)** — 5 of 6 projects in `projects.json` have no `topic_id`. `notify.py`
   refuses to send (fail-closed guard) → silent failures across the board.

The question: fix these three breaks + add a smoke test via which of three approaches?

---

## Approach 1: Targeted Surgical Fixes (Minimal Changes)

**Source:** [Effective End-to-End Testing with BATS](https://blog.cubieserver.de/2025/effective-end-to-end-testing-with-bats/)
and [Smoke testing in CI/CD pipelines](https://circleci.com/blog/smoke-tests-in-cicd-pipelines/)

### Description

Fix each break at the exact location where it occurs, nothing more. Amend `qa-loop.sh`
to pass the resolved spec file path as Claude context. Fix the regex in
`openclaw-artifact-scan.py` to also accept ISO-date filenames. Add `topic_id` entries in
`projects.json` for all 5 missing projects. Add a single `scripts/vps/tests/smoke-e2e.sh`
that injects a synthetic inbox item into a test project, waits for `idle` phase, and asserts
the QA report was created.

### Pros

- Each change targets exactly one file, one function, one root cause — blast radius is R2 for all
  three fixes and the smoke test
- No new concepts, no new abstractions — maintainers read the same code they already know
- Smoke test can run against the live orchestrator with a fake project without mocking
- All three fixes + smoke test independently deployable — if one fix is wrong, roll it back without
  touching the others
- Consistent with the project's existing philosophy (ADR-017: shell bugs fixed in Python CLI, not
  by adding layers)

### Cons

- Adds no systemic protection — the same class of boundary mismatch can recur in future components
- `projects.json` fix is a one-time data patch; relies on humans remembering to add `topic_id`
  for new projects
- Smoke test only covers the exact happy path wired today — does not document data contracts
  between stages
- Does not prevent future regex drift between qa-loop filename format and artifact scanner pattern

### Compute Cost

**Estimate:** ~$5 (R2: contained)
**Why:** 4 files affected (`qa-loop.sh`, `openclaw-artifact-scan.py`, `projects.json`,
`scripts/vps/tests/smoke-e2e.sh`). Each fix is 1-5 lines. Smoke test is a new ~60-line bash
script. No cross-domain changes. Rollback = revert one commit.

### Example Source

```bash
# qa-loop.sh fix: pass spec file path as env, not freeform prompt
SPEC_FILE=$(find "${PROJECT_DIR}/ai/features/" -name "${SPEC_ID}*" -type f | head -1)
export QA_SPEC_FILE="$SPEC_FILE"
claude --print -p "/qa ${SPEC_ID}" ...

# smoke-e2e.sh pattern (from circleci smoke-test pattern)
inject_test_inbox "$TEST_PROJECT_DIR"
wait_for_phase "$TEST_PROJECT_ID" "idle" 120
assert_file_exists "$TEST_PROJECT_DIR/ai/qa/*.md"
```

---

## Approach 2: Pipeline Contract/Schema Layer

**Source:** [Data Contracts for Reliable Pipelines](https://conduktor.io/glossary/data-contracts-for-reliable-pipelines)
and [Contract Testing vs E2E API Testing](https://dev.tools/blog/contract-testing-vs-end-to-end-api-testing-a-decision-framework-for-engineering-teams/)

### Description

Introduce a single Python module `scripts/vps/pipeline_contract.py` that defines the schema
for data passed between pipeline stages (orchestrator → autopilot → qa-loop → artifact-scan →
openclaw). Each stage validates its inputs and outputs against the contract at runtime. The
contract file also documents expected filename formats, required DB fields, and what `topic_id`
must be non-null before notifications are attempted. Fix the three breaks by enforcing contracts
at stage boundaries rather than fixing individual scripts.

### Pros

- Systemic: future breaks in the same class (wrong format, missing field) are caught at
  boundary entry rather than buried in log output
- Contract file is human-readable documentation of the data flow — new contributors understand
  the pipeline shape without reading all scripts
- Validation errors produce explicit, actionable messages ("qa-loop received spec_id without
  resolvable file") instead of silent `exit 0`
- Filename format is defined once in the contract, consumed by both `qa-loop.sh` and
  `artifact-scan.py` — drift is prevented structurally

### Cons

- Adds a new abstraction layer that every script must call — increases coupling to `pipeline_contract.py`
- Contract module must be kept in sync when scripts evolve; stale contracts produce false
  confidence (confirmed by [Contract testing helps but it's not enough](https://medium.com/@reginalafont/contract-testing-helps-but-its-not-enough-bd015791b1e3))
- For the three known breaks, the contract does not eliminate the bugs — it wraps them in
  better error messages; actual fix still needs to happen inside the scripts
- Higher blast radius: `pipeline_contract.py` is imported by multiple scripts, so a bug
  there affects the whole pipeline
- Overkill for a 6-project orchestrator with 6 shell scripts — contract patterns pay off at
  scale (10+ services, multiple teams)

### Compute Cost

**Estimate:** ~$15 (R1: medium blast radius)
**Why:** New module `pipeline_contract.py` (~150 LOC), 6 scripts modified to call validation,
`db.py` extended with `validate_project_for_notify()`, tests for contract module. Cross-cutting
change across all orchestrator components. Risk: if contract validation is too strict, it could
block the pipeline; if too loose, it gives false confidence.

### Example Source

```python
# pipeline_contract.py (data contract pattern from Conduktor/Pandera approach)
from dataclasses import dataclass
from pathlib import Path

@dataclass
class QAStageInput:
    project_id: str
    project_dir: str
    spec_id: str
    spec_file: Path  # resolved, must exist

    def validate(self):
        if not self.spec_file.exists():
            raise ContractViolation(
                f"QA input contract: spec_file not found: {self.spec_file}. "
                f"spec_id={self.spec_id} project_dir={self.project_dir}"
            )
```

---

## Approach 3: Pipeline Dry-Run / Preflight Mode

**Source:** [How to Dry-Run an Ansible Playbook](https://thelinuxcode.com/how-to-dry-run-an-ansible-playbook-check-mode-without-surprises/)
and [SoS dryrun mode](https://vatlab.github.io/sos-docs/doc/user_guide/dryrun.html)

### Description

Add a `--dry-run` flag to each pipeline script (`orchestrator.sh`, `qa-loop.sh`,
`pueue-callback.sh`, `inbox-processor.sh`). In dry-run mode, scripts resolve all paths, check
all DB states, validate topic_id and file patterns, but do not dispatch Claude, write to DB, or
send notifications. Add `scripts/vps/pipeline-preflight.sh` that runs the entire pipeline in
dry-run mode against the real DB and projects, printing what would happen. The three breaks are
fixed because dry-run surfaces them before real runs.

### Pros

- Operator can validate the entire pipeline configuration before deploying changes
- Dry-run mode is a natural debugging tool: "why didn't QA run?" → `pipeline-preflight.sh`
  shows the decision at each gate
- Tested pattern in infrastructure automation (Ansible `--check`, Terraform `plan`)
- No new runtime coupling — dry-run is opt-in; normal execution path is unchanged

### Cons

- Does not fix the three breaks — it surfaces them earlier, but the underlying fixes (path
  resolution, regex, topic_id) still need to happen separately
- Each script must implement dry-run flag separately — if one script omits it, preflight gives
  incomplete picture
- Dry-run divergence from real behavior is a known problem (Ansible modules that can't fully
  predict changes); scripts with side effects (pueue add, claude invocation) are hard to mock
  faithfully without actually running them
- Adds maintenance burden: every new script feature must also handle `DRY_RUN=true` branch
- The smoke test requirement (full cycle without manual intervention) cannot be satisfied by
  dry-run alone — it still requires a real execution path
- Highest compute cost of all three approaches with the least direct value for these specific bugs

### Compute Cost

**Estimate:** ~$15 (R1: medium blast radius)
**Why:** 6 scripts modified for `DRY_RUN` flag handling (~30 LOC each), new
`pipeline-preflight.sh` (~100 LOC), plus the actual bug fixes still needed separately.
Effectively doubles the work of Approach 1 without replacing it.

### Example Source

```bash
# Ansible-style dry-run pattern adapted for bash orchestrator
DRY_RUN="${DRY_RUN:-false}"

dispatch_qa() {
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[preflight] Would dispatch QA for ${project_id}:${current_task}"
        echo "[preflight] spec_file=$(find_spec_file ${current_task}) topic_id=$(get_topic_id ${project_id})"
        return 0
    fi
    # ... real dispatch
}
```

---

## Comparison Matrix

| Criteria | Approach 1: Surgical Fixes | Approach 2: Contract Layer | Approach 3: Dry-Run Mode |
|----------|---------------------------|---------------------------|--------------------------|
| Fixes actual breaks | High (direct) | Medium (wraps, not fixes) | Low (surfaces only) |
| Smoke test coverage | High | Medium | Low |
| Blast radius | Low (R2) | Medium (R1) | Medium (R1) |
| Maintainability | High | Medium | Low |
| Prevents future drift | Low | High | Low |
| Implementation cost | ~$5 | ~$15 | ~$15 |
| New abstractions | None | `pipeline_contract.py` | `DRY_RUN` in 6 scripts |
| Complexity added | Low | Medium | Medium |
| Testability | High | High | Low (hard to verify) |
| Time to fix production | Fast | Slow | Does not fix |

**Rating scale:** Low / Medium / High

---

## Recommendation

**Selected:** Approach 1 (Targeted Surgical Fixes)

### Rationale

The three breaks are well-understood, root-cause isolated, and each lives in a single location.
The `qa-loop.sh` issue is a missing variable export (1 line). The regex mismatch is a pattern
string change (1 line in `openclaw-artifact-scan.py`). The `topic_id` gap is a data fix in
`projects.json` plus a `set_project_topic()` call for the live DB (2 steps). All three are R2:
contained, reversible, single-file scope.

Approaches 2 and 3 solve a different problem: they add systemic protection against future
boundary mismatches. That's valuable, but not what we need right now. The contract layer
(Approach 2) correctly notes that it doesn't eliminate the bugs — it just surfaces them with
better messages. [Research confirms](https://medium.com/@reginalafont/contract-testing-helps-but-its-not-enough-bd015791b1e3)
that contract testing struggles when the actual defect is behavioral (wrong path passed) rather
than schema-level (wrong type). The dry-run mode (Approach 3) is the worst fit: it surfaces
breaks during preflight but still requires the same three fixes, so it doubles the work without
replacing it.

Key factors:
1. **Root causes are known** — no investigation needed, targeted fix is safe
2. **Smoke test validates the fix** — `smoke-e2e.sh` provides the systemic regression guard at
   lower cost than a full contract layer; if the cycle breaks again, the smoke test will catch it
3. **Complexity budget** — this is a 6-project orchestrator maintained by AI agents; adding
   `pipeline_contract.py` as a cross-cutting dependency increases the blast radius for all future
   autopilot tasks without proportional benefit at this scale

### Trade-off Accepted

We accept that the same class of boundary mismatch (filename format drift, missing field) can
recur in future components. The smoke test catches regressions after the fact, not before.
If the pipeline grows to 15+ projects or gains multiple independent teams writing new stages,
revisiting Approach 2 (contract layer) becomes justified. That decision point should be tracked
as a future TECH task, not implemented now.

We also accept that `topic_id` for new projects remains a manual step (add to `projects.json`).
The correct systemic fix is the `/addproject` Telegram wizard in `admin_handler.py`, which
already captures `topic_id` at registration — the gap is only in the static `projects.json`
for projects added before that wizard existed.

---

## Research Sources

- [Effective End-to-End Testing with BATS](https://blog.cubieserver.de/2025/effective-end-to-end-testing-with-bats/) — smoke test pattern for real-environment pipeline validation without mocking
- [Data Contracts for Reliable Pipelines](https://conduktor.io/glossary/data-contracts-for-reliable-pipelines) — contract/schema enforcement at stage boundaries; producer-consumer agreement
- [How to Dry-Run an Ansible Playbook](https://thelinuxcode.com/how-to-dry-run-an-ansible-playbook-check-mode-without-surprises/) — dry-run/check-mode pattern and its known limitations in behavioral validation
- [Contract testing helps but it's not enough](https://medium.com/@reginalafont/contract-testing-helps-but-its-not-enough-bd015791b1e3) — contract testing fails for behavioral/semantic breaks vs schema breaks
- [Contract Testing vs E2E API Testing](https://dev.tools/blog/contract-testing-vs-end-to-end-api-testing-a-decision-framework-for-engineering-teams/) — decision framework for when each approach delivers value
- [Smoke testing in CI/CD pipelines](https://circleci.com/blog/smoke-tests-in-cicd-pipelines/) — smoke test structure for post-deploy verification of critical paths
