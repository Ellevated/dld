# Feature Mode — Spark (8-Phase Protocol)

Self-contained protocol for Feature Mode execution. Extract from SKILL.md.

---

## Purpose

Transform raw feature ideas into executable specs through 8 phases:

```
Collect → Research → Synthesize → Decide → Write → Validate → Reflect → Completion
```

**When to use:** New features, user flows, architecture decisions.

**Not for:** Bugs (use bug-mode.md), hotfixes <5 LOC.

---

## Session Directory

Compute before Phase 2:

```
SESSION_DIR = ai/.spark/{YYYYMMDD}-{spec_id}/
```

---

## State Tracking (Enforcement as Code)

After EACH phase, update the session state file:

```
Write tool → {SESSION_DIR}/state.json
```

**Format:** See `.claude/scripts/spark-state.mjs` for utilities.

**After each phase completes:**
1. Update state.json with phase status = "done" and timestamp
2. For research phase: include `files` array with research file names
3. For decide phase: include `approach` number selected

**This is NOT optional.** Hooks read state.json to validate spec completeness.

---

### Cost Estimate

Before launching Phase 2 (Research), inform user (non-blocking):

```
"Feature spec: {title} — 3 scouts (parallel) + synthesis, est. ~$1-3. Running..."
```

---

## FORBIDDEN ACTIONS (ADR-007/008/009/010)

```
⛔ NEVER store scout responses in orchestrator variables
⛔ NEVER pass full scout output in another scout's prompt
⛔ NEVER use TaskOutput to read scout results
⛔ NEVER read output_file paths from background scouts

✅ ALL scout Task calls use run_in_background: true
✅ Scouts WRITE output to SESSION_DIR files
✅ File gates (Glob) verify scout completion
✅ Orchestrator reads scout files for synthesis (4 files × ~5K = ~20K acceptable)
```

Note: Phase 3 synthesis reads scout output files directly (~15K total). This is an acceptable exception to ADR-010 zero-read — small, bounded output from 3 scouts.

---

### Degraded Mode

If scout phases fail partially, continue with available data:

| Failed Phase | Action | Impact |
|-------------|--------|--------|
| Phase 2: 1 scout fails | Continue with 2 of 3 scouts | Note missing perspective in synthesis |
| Phase 2: 2 scouts fail | Continue with the survivor | Reduced analysis quality, note gaps |
| Phase 2: All scouts fail | Skip research, proceed with user input only | Spec based on dialogue only, note "No external research" |
| Phase 3: Synthesis fails | Read scout files directly, present raw findings | User manually picks approach |
| Phase 6: Validation fails | Retry once, then skip validation gate | Note "Spec not validated" |

Minimum viable spec: user dialogue (Phase 1) + the codebase scout. Losing `spark-codebase`
is the one failure that degrades the spec structurally — Gate 7 (Historical Risks) and
Gate 8 (Verified References) both read its output, and both auto-pass without it, so the
spec ships with unverified references. Note it explicitly when it happens.

---

## Phase 1: COLLECT (Socratic Dialogue)

Three modes depending on feature origin:

### Mode H: Headless (Orchestrator-Initiated)

Detected by `[headless]` marker or `Source:` field in prompt.
All information is already provided — DO NOT ask questions.

1. Read the prompt content as the complete problem statement
2. If `Context:` field present — Read the linked document
3. Extract problem statement, proceed directly to Phase 2
4. State.json: collect = done

### Mode A: Human-Initiated

User started the feature — ask 5-7 deep questions. ONE at a time!

**Question Bank (pick 5-7 relevant):**

1. **Problem:** "What problem are we solving?" (not feature, but pain)
2. **User:** "Who is the user of this function? Seller? Buyer? Admin?"
3. **Current state:** "How is it solved now without this feature?"
4. **MVP:** "What's the minimum scope that delivers 80% of value?"
5. **Risks:** "What can go wrong? Edge cases?"
6. **Verification:** "How will we verify it works?"
7. **Existing:** "Is there an existing solution we can adapt?"
8. **Priority:** "How urgent is this? P0/P1/P2?"
9. **Dependencies:** "What does it depend on? What's blocking?"
10. **Past Behavior:** "Have users tried to solve this themselves? How?"
11. **Kill Question:** "If we do nothing — what happens in 3 months?"

**Rules:**
- Ask ONE question at a time — wait for answer
- Don't move to design until key questions are answered
- If user says "just do it" — ask 2-3 minimum clarifying questions anyway
- Capture insights for scout context

### Mode B: Blueprint-Initiated

Architect/Board assigned this task — read from blueprint, do NOT ask user.

1. Read task description from `ai/blueprint/system-blueprint/`
2. If clarifications are needed → read the blueprint yourself. `domain-map.md`,
   `data-architecture.md`, `cross-cutting.md` and `api-contracts.md` are the same
   sources any responder would consult, and you already have Read.
   - Still unresolved after reading, and the answer would change the design →
     escalate to `/architect` in Phase 4, which is the route that already exists
3. Human = 0% involvement (per design doc)

**Output for both modes:** Problem statement captured, ready for scouts.

<GATE>
DO NOT proceed to Phase 2 until:
- [ ] state.json initialized with initState()
- [ ] state.json updated: collect = done
- [ ] Problem statement clearly captured
</GATE>

---

## Phase 2: RESEARCH (3 Parallel Scouts)

Dispatch 3 isolated scouts in parallel. Each scout gets a frozen snapshot — they do NOT see each other's work.

Three, because each one holds something this session does not:

| Scout | What it brings that you cannot get otherwise |
|---|---|
| `spark-research` | Everything outside the repo — web, docs, library versions. A separate context absorbs the search volume instead of flooding this one |
| `spark-codebase` | Grep evidence across the whole tree, the Impact Tree, and `## Verified References` / `## Historical Risks`, which Gates 7 and 8 read directly |
| `spark-devil` | Independence of judgment. The author of a proposal cannot see its holes — this is the same reason autopilot keeps a separate `review` |

Research and alternatives used to be two scouts running the same Exa queries and returning
two recommendations that then had to be reconciled. They are one search, so they are one
scout.

> **Emit all Task calls in a SINGLE assistant message** (multiple tool calls in
> one turn). They run concurrently only when emitted together — calls in
> separate turns serialize. Do not launch-then-wait per agent. The harness caps
> concurrent agents and queues the rest, so emitting many at once is safe.

```yaml
# Scout 1: Research (practices, libraries, alternative approaches)
Task tool:
  description: "Spark scout: external research"
  subagent_type: spark-research       # → agents/spark/research.md
  run_in_background: true
  prompt: |
    FEATURE: {feature description}
    BLUEPRINT: [contents of ai/blueprint/system-blueprint/ if exists]
    SOCRATIC INSIGHTS: {key insights from Phase 1}
    Output: research-web.md

# Scout 2: Codebase (existing code, dependencies)
Task tool:
  description: "Spark scout: codebase analysis"
  subagent_type: spark-codebase       # → agents/spark/codebase.md
  run_in_background: true
  prompt: |
    FEATURE: {feature description}
    BLUEPRINT: [contents of ai/blueprint/system-blueprint/ if exists]
    SOCRATIC INSIGHTS: {key insights from Phase 1}
    Output: research-codebase.md

# Scout 3: Devil's Advocate
Task tool:
  description: "Spark scout: devil's advocate"
  subagent_type: spark-devil          # → agents/spark/devil.md
  run_in_background: true
  prompt: |
    FEATURE: {feature description}
    BLUEPRINT: [contents of ai/blueprint/system-blueprint/ if exists]
    SOCRATIC INSIGHTS: {key insights from Phase 1}
    Output: research-devil.md
```

**All 3 scouts run in PARALLEL, ALL background, and do NOT see each other's work.**

If `ai/blueprint/system-blueprint/` exists, ALL scouts receive it as CONSTRAINT.

**⏳ FILE GATE:** Wait for ALL 3 completion notifications, then verify:
```
Glob("{SESSION_DIR}/research-*.md") → must find 3 files
If < 3: launch extractor subagent for missing files (caller-writes fallback, ADR-007)
```

<GATE>
DO NOT proceed to Phase 3 until:
- [ ] ALL 3 scout completion notifications received
- [ ] Glob confirms 3 research files exist in SESSION_DIR
- [ ] `research-codebase.md` contains a `## Verified References` section (grep `^## Verified References$` → ≥1 hit). Codebase scout in degraded mode is an acceptable exception — note "no codebase research" in state.json.
- [ ] state.json updated: research = done, files = [list of 4 files]
</GATE>

---

## Phase 3: SYNTHESIZE

Read all inputs:
- Problem statement from Phase 1
- 3 research files from Phase 2
- `ai/blueprint/system-blueprint/` (as constraint)

### Build 2-3 Approaches WITHIN Blueprint

For each approach:

| Field | Source |
|-------|--------|
| Summary | Research scout `## Approaches` + `## Recommendation` |
| Affected files | Codebase scout Impact Tree |
| Risks | Devil scout edge cases |
| Test strategy | Devil scout assertions + Research scout |
| Blueprint compliance | ✓ or ⚠️ with explanation |

### Rules

- **NO INVENTION** — if scouts didn't find it, it's a gap (note for Phase 7 reflect)
- **Cite sources** — every claim must reference a scout file
- **Conflicts** → apply Evaporating Cloud (what's the underlying assumption?)
- **All approaches must respect blueprint** — if none fit, escalate to ARCHITECT in Phase 4

**Output:** 2-3 approaches ready for Phase 4 decision.

<GATE>
DO NOT proceed to Phase 4 until:
- [ ] 2-3 approaches documented with pros/cons
- [ ] Every claim cites a scout research file
- [ ] state.json updated: synthesize = done
</GATE>

---

## Phase 4: DECIDE

<!-- This matrix applies ONLY in Spark Phase 4. Autopilot/callback MUST NOT apply this matrix. -->
### Impact x Risk Routing Matrix

Assign Priority (P0/P1/P2) and Risk (R0/R1/R2) from research, then route:

```
Risk Classification:
R0 = Irreversible: data loss, schema migration, security exposure, public API break
R1 = High blast radius: 3+ files, cross-domain, external dependency, state machine change
R2 = Contained: 1-2 files, single domain, internal, trivially rollbackable
```

| Impact \ Risk | R0 (Irreversible) | R1 (Blast radius) | R2 (Contained) |
|---|---|---|---|
| P0 | COUNCIL | HUMAN | AUTO |
| P1 | COUNCIL | AUTO | AUTO |
| P2 | HUMAN | AUTO | AUTO |

### AUTO (you decide)
- Matrix says AUTO
- Feature is within blueprint constraints
- Devil scout's verdict is "Proceed"
→ Select best approach, move to Phase 5

### HUMAN (ask user)
- Matrix says HUMAN
- Multiple approaches with no clear winner
- Scope unclear after dialogue
→ Present 2-3 approaches, user chooses

### COUNCIL (convene NOW, inside this Spark session)
- Matrix says COUNCIL
- Cross-domain impact (affects 3+ domains)
- Major architectural decision

Council is a Phase 4 decision instrument — it runs BEFORE the spec is written,
never after. Protocol:

1. **Interactive mode:** present the R0/impact assessment to the user first.
   User chooses: (a) convene `/council` now, (b) decide together without
   council (route downgrades to HUMAN), or (c) drop the feature (no spec).
2. **Headless mode:** convene `/council` inline immediately (user unavailable).
3. Input to council: the 2-3 approaches from Phase 3 + scout research files.
4. Incorporate the synthesis:
   - `approved` / `needs_changes` → select/adjust approach, proceed to Phase 5
   - `rejected` → return to Phase 3 with council feedback (or exit without spec)
   - `needs_human` in headless → EXIT WITHOUT creating the spec file
     (`status: blocked, spec_status: not_created` — same shape as a linter
     failure); orchestrator surfaces it to the user.

⛔ **NEVER write the spec first and defer council.** A spec with status
`blocked`, "council_required", or any other pre-implementation gate MUST NOT
exist. By the time Phase 5 starts, all decisions are made — every created
spec exits Spark as `queued` (see completion.md).

### ARCHITECT (escalate)
- Blueprint gap (domain missing, rule missing)
- Blueprint contradiction (research conflicts with blueprint)
→ Architect updates blueprint → retry from Phase 3

### Session Budget (size the spec before writing it)

One spec = one autopilot session, and that session is hard-capped:
`MAX_TURNS = 300`, `TIMEOUT_SECONDS = 10800` (3 hours) in
`scripts/vps/claude-runner.py`. A spec that doesn't fit the budget is a scoping
problem — but note the budget is not fixed forever, and the old "the timeout is
deliberately NOT raised" absolute was wrong: it was raised on 2026-08-23 because
the run it had been calibrated against stopped existing. Until 2026-07-26 the
orchestrator silently ran Opus 4.6 on a 200K window; on real Opus 5 the median
run went from 8.7 to 47.1 minutes and the timeout rate from 1% to 32%. Sizing
guidance below is unchanged — the ceilings were never the thing that broke.

A session that overruns still produces nothing mergeable. It is killed mid-work,
callback marks it `blocked`, and only what `salvage.py` pushed survives on the
branch. FTR-0081 (2026-07-26) spent a full 90 minutes and merged zero lines.

Decide the shape here, while the spec is still an outline:

| Fits one session | Split into epic + children |
|---|---|
| ≤ 5 implementation tasks | > 8 tasks |
| ≤ 10 entries in Allowed Files | > 15 files |
| One domain (plus its tests) | Touches 3+ domains |
| Feature only | Migration AND the feature that consumes it |

Between the columns (6–8 tasks, 11–15 files): a single spec is allowed, but state
in one line why it is indivisible.

**Splitting is not deferral.** Claim one `ARCH-*` id for the epic and one id per
child — each through `lifecycle.create_initial`, same as any spec — write every
child spec in this session, and have the epic list them. Each child must be
independently shippable: if child 2 is useless without child 1, that is one spec,
not two.

Judge by tasks and files, not by prose length. A 400-line spec with 3 tasks is
fine; a 60-line spec that quietly rewrites nine files is not.

<GATE>
DO NOT proceed to Phase 5 until:
- [ ] Decision route selected (AUTO/HUMAN/COUNCIL/ARCHITECT)
- [ ] If HUMAN: user has explicitly chosen an approach
- [ ] If COUNCIL: council has ALREADY run and its decision is incorporated — "council later" is not a state
- [ ] Session Budget applied: single spec, or the epic + child split decided and ids claimed
- [ ] state.json updated: decide = done, approach = N
</GATE>

---

## Phase 5: WRITE (Feature Spec Template)

### Spec-First ID Generation (Kafka pattern via lifecycle CAS)

Instead of "scan backlog → pick max+1 → write spec", use atomic CAS:

1. **Compute candidate ID:**
   ```bash
   # Get max existing ID (returns empty if ai/lifecycle/ doesn't exist yet → start from 001)
   MAX=$(git ls-tree HEAD:ai/lifecycle/ 2>/dev/null | grep -oE '(TECH|FTR|BUG|ARCH|GROWTH)-[0-9]+' | sort -t- -k2 -n | tail -1)
   # If empty (new project), use 001; otherwise increment
   CANDIDATE="${TYPE}-$(printf '%03d' $((${MAX##*-} + 1)))"
   ```
   Keep same prefix as your spec type (`TECH`/`FTR`/`BUG`/`ARCH`).

2. **Attempt atomic claim:**
   ```bash
   python3 -c "
   from scripts.vps.lifecycle import create_initial, LifecycleWriteRaceError
   try:
       create_initial('<REPO_DIR>', '<CANDIDATE_ID>', priority='<P0|P1|P2>', kind='<TECH|FTR|BUG|ARCH>', by='spark', status='queued', depends_on=[<'AFTER' ids from the spec header, or empty>])
       print('claimed')
   except LifecycleWriteRaceError:
       print('race')
   "
   ```
   `depends_on` — плоский список spec_id из `**AFTER <ID>**` в шапке спеки. Проверить каждый
   через `git cat-file -e HEAD:ai/lifecycle/<ID>.yaml` до claim'а; несуществующий ID не класть.

3. **On `LifecycleWriteRaceError`** → re-read HEAD, increment candidate, retry (max 3 attempts — `MAX_CAS_RETRIES`).

4. **On success** → ID is yours. Write `ai/features/<ID>-<date>-<title>.md`. Nothing else —
   `ai/backlog.md` is rendered from the lifecycle records.
5. **If `git cat-file -e HEAD:ai/lifecycle/<ID>.yaml` fails** after the attempt, the claim
   did not land — write the spec **and** a backlog row for it. An orchestrator bootstraps a
   missing lifecycle record only for specs the backlog already names, so without the row the
   spec is never dispatched. See `completion.md`, "The backlog is a render — with exactly
   one exception".

6. **On exhausted retries** → surface error to user; do NOT write spec with an unclaimed ID.

Write spec using selected approach from Phase 4:

```markdown
# Feature: [FTR-XXX] Title
**Priority:** P0/P1/P2 | **Date:** YYYY-MM-DD

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml`.
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why
[Problem statement from Socratic Dialogue]

## Context
[Background, related features, current state]

---

## Scope
**In scope:** [What we're doing]
**Out of scope:** [What we're NOT doing]

---

## Impact Tree Analysis

### Step 1: UP — who uses?
_Source: code graph or grep — state which._
- [ ] `trace_path(project, function_name="{name}", direction="inbound", depth=2)` → ___ callers
      (no graph: `grep -r "from.*{module}" . --include="*.py"` → ___ results)
- [ ] All callers identified: [list files]

### Step 2: DOWN — what depends on?
- [ ] Imports in changed file checked
- [ ] External dependencies: [list]

### Step 3: BY TERM — grep entire project
- [ ] `grep -rn "{old_term}" . --include="*.py" --include="*.sql"` → ___ results
- [ ] **Signature change or method removal — grep `tests/` separately.** When a function's
      arguments change (added, removed, renamed) or a method/module is deleted, run
      `grep -rn "{symbol}" tests/` on its own and put **every** caller test in Allowed Files.
      Not the obvious unit test — all of them. Precedent (AwardyBot TECH-1325): the spec
      named 2 test files, 5 actually broke, and autopilot widened its own scope mid-run to
      reach them — seven retries. A caller test outside the allowlist is a run that cannot
      finish honestly.

| File | Line | Status | Action |
|------|------|--------|--------|
| _fill_ | _fill_ | _fill_ | _fill_ |

### Step 4: CHECKLIST — mandatory folders
- [ ] `tests/**` checked
- [ ] `db/migrations/**` checked
- [ ] `ai/glossary/**` checked (if money-related)

### Verification
- [ ] All found files added to Allowed Files
- [ ] grep by old term = 0 (or cleanup task added)

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by the orchestrator callback. -->

ONLY the files listed below may be modified during implementation.

- `path/to/file1.py` — reason (modify)
- `path/to/file2.py` — reason (modify)
- `path/to/new_file.py` — reason (NEW)
- `tests/path/to/test_file.py` — reason (NEW)

**Format contract (enforced by Spark linter — see Phase 5.5):**
- Heading is exactly `## Allowed Files` (case-sensitive H2, no suffix, no
  qualifier in parentheses).
- The HTML comment marker `<!-- callback-allowlist v1 -->` (or
  `<!-- callback-allowlist v1: ... -->`) is REQUIRED and must appear
  before the first path.
- Each path lives on its own bullet `- ` line, wrapped in single backticks.
  Optional free-text after the closing backtick is allowed.
- No fenced code blocks, no nested lists, no tables. One path per line.
- Minimum one path. Empty Allowed Files = block the spec (Spark refuses to
  write).

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

<!-- Smart defaults: adjust based on your stack -->
nodejs: false
docker: false
database: false

---

## Blueprint Reference

<!-- If ai/blueprint/system-blueprint/ exists, fill this section -->
**Domain:** {which domain from domain-map.md}
**Cross-cutting:** {Money? Auth? Errors? — from cross-cutting.md}
**Data model:** {which entities from data-architecture.md are affected}

---

## Historical Risks

<!-- lessons-binding v1 -->

_Auto-populated by spark-codebase from `ai/lessons/{domain}/`. Copy from `## Historical Risks` section of research-codebase.md._

| ID | Class | Rule | Sources |
|----|-------|------|---------|
| {L-ID} | {root_cause_class} | {prevention_rule} | {TASK-IDs} |

_Write "none" explicitly if spark-codebase found no historical lessons for this domain._

---

## Approaches

### Approach 1: [Name] (based on [source])
**Source:** [URL from Scout research]
**Summary:** [Brief description]
**Pros:** [Benefits]
**Cons:** [Drawbacks]

### Approach 2: [Name] (based on [source])
**Source:** [URL]
**Summary:** [Brief description]
**Pros:** [Benefits]
**Cons:** [Drawbacks]

### Selected: [N]
**Rationale:** [Why this approach was chosen]

---

## Design

> **Every claim about how the system behaves today carries a `file:line` or a command that
> shows it.** Not the design you are proposing — the *existing* behaviour you are designing
> against: how a merge happens, what a diff range covers, which gate runs first, what a
> function returns. Those sentences are the ones that get written from memory of the prompt
> tree rather than from the code, and a wrong one produces a spec that looks implemented and
> is not. TECH-220 specified a diff range that is empty under `--ff-only` — the only merge
> the pipeline performs — and its own EC would have passed while the gate never fired; the
> planner caught it against the code, spec review had not. Cite it or drop it.

### User Flow
[Step-by-step user journey]

### Architecture
[Component diagram or description]

### Database Changes
[If applicable: schema changes, migrations needed]

---

## UI Event Completeness (REQUIRED for UI features)

If creating UI elements with callbacks/events — fill this table:

| Producer (keyboard/button) | callback_data | Consumer (handler) | Handler File in Allowed Files? |
|---------------------------|---------------|-------------------|-------------------------------|
| `start_keyboard()` | `guard:start` | `cb_guard_start()` | `onboarding.py` ✓ |

**RULE:** Every `callback_data` MUST have a handler in Allowed Files!

- No handler = No commit (Autopilot will block)
- If handler file missing from Allowed Files — add it or explain why not needed
- This prevents orphan callbacks (BUG-156 post-mortem)

---

## Implementation Plan

### Research Sources
- [Pattern Name](https://example.com) — description of what pattern solves
- [Library Docs](https://example.com) — API reference for implementation
- [Example](https://example.com) — code example that inspired approach

### Task 1: [Name]
**Type:** code | test | migrate
**Files:**
  - create: `path/to/new_file.py`
  - modify: `path/to/existing.py`
**Pattern:** [URL from Research Sources]
**Acceptance:** [How to verify task is complete]

### Task 2: [Name]
**Type:** code | test | migrate
**Files:**
  - modify: `path/to/file.py`
**Pattern:** [URL]
**Acceptance:** [Verification criteria]

### Execution Order
1 → 2 → 3

---

## Flow Coverage Matrix (REQUIRED)

Map every User Flow step to Implementation Task:

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | User clicks menu button | - | existing |
| 2 | Guard shows message + button | Task 1,2,3 | ✓ |
| 3 | User clicks [Start] button | Task 4 | ✓ |
| 4 | Onboarding starts | - | existing |

**GAPS = BLOCKER:**
- Every step must be covered by a task OR marked "existing"
- If gap found → add task or explain why not needed
- Uncovered steps = incomplete spec (Council may reject)

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | {scenario} | {input} | {expected behavior} | deterministic | {devil/user/blueprint} | P0 |
| EC-2 | {edge case} | {input} | {expected} | deterministic | {devil scout} | P0 |
| EC-3 | {boundary} | {input} | {expected} | deterministic | {user requirement} | P1 |

### Integration Assertions (if applicable)

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-N | {preconditions} | {action} | {result} | integration | {source} | P1 |

### LLM-Judge Assertions (if LLM-involved feature)

| ID | Input | Rubric | Threshold | Source | Priority |
|----|-------|--------|-----------|--------|----------|
| EC-N | {prompt/input} | {good output criteria} | 0.8 | {source} | P1 |

### Coverage Summary
- Deterministic: {N} | Integration: {N} | LLM-Judge: {N} | Total: {N} (min 3)

### TDD Order
1. Write test from EC-1 -> FAIL -> Implement -> PASS
2. Continue by priority (P0 first)

---

## Acceptance Verification (MANDATORY)

Machine-executable checks: feature WORKS in running system.

### Smoke Checks (process alive)

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | {service starts} | {command} | exit 0 / ready | 30s |

### Functional Checks (business logic)

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | {happy path} | {preconditions} | {action} | {result} |

### Verify Command (copy-paste ready)

```bash
# Smoke
{exact start command}
{exact health check}
# Functional
{exact test command}
```

### Post-Deploy URL (if applicable)

```
DEPLOY_URL={URL or "local-only"}
```

**Rules:**
- Commands must be copy-paste executable (no placeholders except project-specific values)
- Minimum 1 smoke check (AV-S*) + 1 functional check (AV-F*)
- N/A allowed with reason (e.g., "N/A: pure library, no running process")

---

## Definition of Done

### Functional
- [ ] Feature works as specified
- [ ] All tasks from Implementation Plan completed

### Tests
- [ ] All eval criteria from ## Eval Criteria section pass
- [ ] Coverage not decreased

### E2E User Journey (REQUIRED for UI features)
- [ ] Every UI element is interactive (buttons respond to clicks)
- [ ] User can complete full journey from start to finish
- [ ] No dead-ends or hanging states
- [ ] Manual E2E test performed

### Acceptance Verification
- [ ] All Smoke checks (AV-S*) pass locally
- [ ] All Functional checks (AV-F*) pass locally
- [ ] Verify Command runs without errors

### Technical
- [ ] Tests pass (./test fast)
- [ ] No regressions

---

## Autopilot Log
[Auto-populated by autopilot during execution]
```

<GATE>
DO NOT proceed to Phase 6 until:
- [ ] Full spec written to ai/features/{TASK_ID}-*.md
- [ ] All template sections filled (no {placeholders} remain)
- [ ] state.json updated: write = done
</GATE>
---

## Phase 5.5: ALLOWLIST LINTER (Pre-Validate Hard Gate)

After Write, before Validate. Autopilot may write only what this section lists —
so a section that parses differently than you meant is a run that writes the wrong
files, or nothing at all.

```bash
node .claude/scripts/validate-allowlist.mjs ai/features/{TASK_ID}-*.md
```

Exit 0 = pass. Exit 1 = fix required. Exit 2 = the file is missing or unreadable.
The script prints one JSON object: `paths`, `implementation_paths`, `errors`,
`warnings`.

The rules live in the script, not here. This used to be four regexes transcribed
into this file for the model to apply by hand — two copies of one format spec, which
drifted apart and started rejecting specs the rest of the pipeline accepted. If your
project also parses `## Allowed Files` in a CI gate or commit hook, keep that parser
and this script in lockstep and put a test on the pair.

### On failure — fix the section, do not delete the spec

The ID was already claimed in Phase 5, so deleting the spec file burns the ID and
can strand whatever lifecycle record was written alongside it. The allowlist is a
section of markdown — repair it.

1. Read the `errors` array. Each names the line and what the parser will do with it.
2. Edit the `## Allowed Files` section in place. Canonical entry shapes, one path
   per line, nothing else parses:
   ```
   - `path/to/file.py` — reason (modify)
   1. `path/to/file.py` — reason (modify)
   ```
   Tables, fenced blocks and two paths on one line are not read.
3. Re-run the script. Repeat at most twice.
4. Still failing after two repairs → this is a spec problem, not a formatting one
   (`ALLOWLIST_E007_BOOKKEEPING_ONLY` means the spec lists no file that implements
   anything). Return to Phase 3, keep the ID, rewrite the section from the Impact Tree.

Escalate only if the third attempt fails: set `state.json: lint = failed, error = <code>`
and return `status: blocked` with the linter's `error_message` and the spec path —
the spec stays on disk for a human to look at.

### On success

- state.json: `lint = done, allowlist_paths = [<paths from the script>]`.
- Read the `warnings` array before moving on. Warnings do not block, but
  `ALLOWLIST_W002_EXTRA_PATH_IN_REASON` means a second path on an entry line was
  not extracted — if that was meant to be an entry, give it its own line now.
- Proceed to Phase 6.

<GATE>
DO NOT proceed to Phase 6 until:
- [ ] `validate-allowlist.mjs` run on the freshly-written spec, exit 0
- [ ] `warnings` read and any lost entry given its own line
- [ ] state.json updated: lint = done, allowlist_paths = [<paths>]
</GATE>

---
## Phase 6: VALIDATE

Before marking spec `queued`, run 8 structural validation gates.

### Gate 1: Spec Completeness
```
□ Enough information for implementation?
□ No contradictions with system blueprint?
□ Allowed Files cover all tasks?
□ Edge cases covered?
□ DoD is measurable?
```

### Gate 1b: Spec Size (hard ceiling, soft band beneath it)
```
□ ≤ 5 tasks AND ≤ 10 Allowed Files      → pass
□ 6-8 tasks OR 11-15 Allowed Files      → pass, with a written justification
□ > 8 tasks OR > 15 Allowed Files       → BLOCK: split (Phase 4 Session Budget)
```

**Why this one blocks.** Autopilot is capped at `MAX_TURNS = 300` /
`TIMEOUT_SECONDS = 10800` (3 h). The cap is generous, not infinite, and an
oversized spec doesn't degrade gracefully — it is killed mid-run, marked
`blocked`, and merges nothing. BUG-327: 117 turns, $50, FAIL. FTR-0081: 90
minutes, blocked, zero lines merged. This gate used to end with "proceed
anyway", which is precisely why oversized specs kept shipping.

**On BLOCK, do not exit without specs.** Return to Phase 4 Session Budget and
split: one `ARCH-*` epic plus 2-4 independently shippable children, all written
in this session, all `queued`. Splitting yields more specs, never fewer — an
empty exit here is a worse outcome than an oversized spec.

**In the 6-8 / 11-15 band**, add one line under the spec title:
`**Size:** N tasks / M files — indivisible because {reason}.`
A justification that could be pasted onto any spec ("the tasks are related")
means it is divisible; split instead.

### Gate 2: Eval Criteria Gate
```
□ Eval Criteria section filled? (or Tests section for legacy specs)
□ Minimum 3 eval criteria (EC-N rows)?
□ Has edge case from devil's advocate?
□ Coverage Summary present?
□ TDD Order defined?
□ DoD includes tests/eval?
```

### Gate 3: Blueprint Compliance
```
□ Blueprint Reference filled?
□ Cross-cutting rules applied (Money, Auth, Errors)?
□ Data model matches data-architecture.md?
□ Feature respects domain boundaries from domain-map.md?
```

### Gate 4: UI Event Completeness (if UI feature)
```
□ Every callback_data has handler in Allowed Files?
□ No orphan callbacks?
```

### Gate 5: Flow Coverage
```
□ Every User Flow step covered by Implementation Task or marked "existing"?
□ No gaps in flow?
```

### Gate 6: Acceptance Verification
```
□ Has ## Acceptance Verification section?
□ At least 1 AV-S* and 1 AV-F* check?
□ Verify Command has real commands (not just placeholders)?
□ If N/A — reason is valid and documented?
```

### Gate 7: Historical Risks
```
□ ## Historical Risks section present in spec?
□ <!-- lessons-binding v1 --> marker present?
□ Has ≥1 lesson row OR explicit "none"?
```

**Soft gate:** If `ai/lessons/` does not exist in the project → Gate 7 auto-passes.
Write in gate result: "Gate 7: auto-pass (no lessons bank)".

### Gate 8: Verified References
```
□ research-codebase.md содержит секцию ## Verified References?
□ Каждый concrete reference в спеке (Allowed Files paths, Implementation
  Plan endpoints, schema/model fields, FSM/state keys, migration
  filenames, function/class names cited as reuse target) трассируется
  в research-codebase.md → ## Verified References?
□ Нет reference со статусом "assumed" / без verify-команды?
```

**Soft sub-rule:** If Phase 2 codebase-скаут провалился (degraded mode,
research-codebase.md missing or empty) → Gate 8 auto-pass с пометкой
"Gate 8: auto-pass (no codebase research)".

**Why this gate exists:** Spark писал в спеку конкретные пути/endpoint'ы/
state-ключи без grep-верификации; расхождение ловилось только в runtime
автопилота (planner) или code-quality reviewer'ом — уже после того как
спека ушла как готовая.
Gate 8 закрывает петлю: untraced reference → reject → возврат в Phase 3.

**Note:** Gate 8 is LLM-проверка трассируемости (reference ↔ Verified
References row). AST-based file-resolver — отдельный follow-up (out of scope).

**GATE RESULT:** pass / reject with reasons

**If any gate fails →** spec stays in current state, return to Phase 3 (re-synthesize with feedback).

<GATE>
DO NOT proceed to Phase 7 until:
- [ ] All 8 validation gates pass
- [ ] state.json updated: validate = done
</GATE>

---

## Phase 7: REFLECT

After spec passes all validation gates, before completion:

### LOCAL Signal
Improvement for next Spark iteration:
- What scouts missed, what worked well
- Which question bank items were most useful

### UPSTREAM Signal
If issues were found during research/synthesis that affect upstream levels:
- Blueprint gap → write upstream signal with target=architect
- Missing cross-cutting rule → write upstream signal with target=architect
- Business question unanswered → write upstream signal with target=board

### PROCESS Signal
Meta-observation about the process itself:
- Did auto-decide work correctly for this feature?
- Was council escalation needed but not triggered (or vice versa)?
- Scout coverage: did any scout find nothing useful?

```yaml
# Only if issues found — don't write empty signals!
Append to ai/reflect/upstream-signals.md:

## SIGNAL-{timestamp}

| Field | Value |
|-------|-------|
| Source | spark |
| Spec ID | {TASK_ID} |
| Target | architect / board |
| Type | gap / contradiction / missing_rule |
| Severity | info / warning / critical |

### Message
{What's missing or wrong in the blueprint}

### Evidence
{Specific finding from scout research}

### Suggested Action
{What Architect/Board should do}
```

<GATE>
DO NOT proceed to Phase 8 until:
- [ ] Reflect signals written (if any issues found)
- [ ] state.json updated: reflect = done
</GATE>

---

## Phase 8: COMPLETION

After spec is created and validated → read `completion.md` for:
- ID determination protocol (sequential across ALL types)
- Why `ai/backlog.md` is never edited by hand
- Auto-commit rules
- Handoff to autopilot

After completion: state.json updated: completion = done
