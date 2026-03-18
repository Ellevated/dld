# Devil's Advocate — Orchestrator North-Star Alignment (TECH-151)

## Why NOT Do This?

### Argument 1: completion.md contradicts SKILL.md — the model already has internal contradictions

**Concern:** The proposal assumes we need to change Spark's behavior. But the DLD copy of `SKILL.md` already says (line 44): "There is no approval gate between Spark and Autopilot in the orchestrator north-star flow." Yet `completion.md` (lines 45, 82–101, 260) still says "Status = draft — awaits human approval" in three separate places, including the pre-completion checklist, the self-check section, and the return format. The model is reading two contradictory truth sources in the same skill invocation. The result is unpredictable: some runs will produce `queued`, others `draft`, depending on which instruction the model weights heavier.

**Evidence:** `.claude/skills/spark/completion.md:45` — checklist item 5 says "Status = draft". `.claude/skills/spark/completion.md:99` — "Spark completed fully → draft". `.claude/skills/spark/completion.md:260` — return YAML says `spec_status: draft  # always draft`. But `.claude/skills/spark/SKILL.md:44` says "no approval gate". This desync was present before this feature was written.

**Impact:** High

**Counter:** Must update `completion.md` atomically with this feature. Not as a separate follow-up — as a blocking prerequisite. Also check `template/.claude/skills/spark/completion.md` — same file exists there with the same `draft` instructions (confirmed identical content at lines 45, 99, 101).

---

### Argument 2: Removing scan_drafts() is safe only if pueue-callback.sh approval logic is also cleaned up

**Concern:** `scan_drafts()` in orchestrator.sh is not called anywhere in `process_project()` (lines 431–447). It's already dead code — it was replaced by Step 5.5 in pueue-callback.sh. But pueue-callback.sh Step 5.5 (lines 214–257) still reads from backlog looking for `draft` specs and sends approval buttons to Telegram. If we change Spark to produce `queued` instead of `draft`, the callback will never find a matching draft spec, and `SENT_APPROVAL` will stay `false`. This means no Telegram approval message for headless Spark runs. That is the **intended** behavior per north-star — but it will silently break the notification flow for interactive Spark runs, which still legitimately produce `draft` specs.

**Evidence:** `pueue-callback.sh:230` — `SPEC_ID=$(grep -E '^\|.*\|\s*draft\s*\|' "$BACKLOG"` — this grep only matches `draft`. If interactive Spark produces `queued`, the approval notification is lost. `pueue-callback.sh:298–303` — the Spark-from-QA message path (`TASK_LABEL =~ inbox-.*-(qa|reflect)-result`) assumes the spark ran from inbox, which changes if Spark skips to `queued`.

**Impact:** High

**Counter:** The callback's approval logic (Step 5.5) should be conditioned on whether this was a headless or interactive Spark run — detectable via the task label (inbox-dispatched tasks have label `project:inbox-TIMESTAMP`, whereas direct `/spark` runs have label `project:SPEC-ID`). Alternatively, Step 5.5 should look for both `draft` AND `queued` specs as the "needs approval" signal, with headless runs producing `queued` skipping the notification entirely (which is the north-star).

---

### Argument 3: Git pull race — orchestrator picks up `queued` spec before Spark's push lands

**Concern:** Spark's new headless flow is: (1) create spec with `queued`, (2) commit, (3) push to develop, (4) return. The orchestrator runs every `POLL_INTERVAL` (default 300s) and calls `git_pull()` followed by `scan_backlog()`. The `git_pull()` function skips the pull entirely if a pueue agent is running for this project (`scripts/vps/orchestrator.sh:119–131`). But Spark itself IS a pueue agent — so while Spark is writing the spec, the orchestrator SKIPS the git pull. On the NEXT cycle (up to 5 minutes later), the orchestrator pulls and finds the spec. This is acceptable timing — no race. However, there is a gap: `git_pull()` only checks for Running tasks, not Queued tasks (`isinstance(status, dict) and 'Running' in status`). If Spark finishes before the orchestrator's git pull attempt, the pull executes and tries to rebase concurrently with Spark's push. This is a fast-forward scenario and should be safe, but it is NOT guaranteed if the push hasn't completed yet.

**Evidence:** `orchestrator.sh:123-128` — only `'Running' in status` prevents pull. If Spark completes its pueue task but the push is still in progress (slow network, large commit), the orchestrator will attempt pull simultaneously. `orchestrator.sh:137` — `git pull --rebase origin develop` — this will fail if the remote isn't updated yet, but will succeed 5 minutes later. Non-fatal since `git_pull()` is called with `|| true`.

**Impact:** Medium — timing window is narrow and failure is non-fatal. But the specific scenario of "push hasn't landed when next cycle fires" can silently drop the spec from being processed for one full cycle (5 minutes extra delay).

**Counter:** The git pull failure is logged as `warn` and non-fatal. Worst case: 5-minute extra delay before orchestrator sees the spec. Acceptable. But the concurrency warning in `completion.md` ("Do not run spark while autopilot is executing") now becomes stale for headless mode — headless Spark runs WILL overlap with other pueue agents.

---

### Argument 4: Interactive mode regression — completion.md says `queued` in the flow section but `draft` everywhere else

**Concern:** `completion.md` has a schizophrenic status section. Lines 226–238 (the "Completion — No Handoff" section) clearly say status `queued` and describe the north-star flow. But lines 45, 82–101, and 260 still say `draft`. If we update ONLY the headless detection in SKILL.md, interactive Spark will continue using `draft` (per completion.md:99–101), while the callback expects `draft` for approval buttons. This is actually CORRECT for interactive mode. The problem is that the two modes (headless → `queued`, interactive → `draft`) are nowhere clearly documented or enforced by the model — both are in the same completion.md, and the model has to infer context.

**Evidence:** `.claude/skills/spark/completion.md:226-238` describes the queued flow without mentioning it's headless-only. `.claude/skills/spark/SKILL.md:59` says "Create spec in `draft` status (orchestrator handles approval via Telegram)" specifically under `**Behavior in headless mode:**`. But then `.claude/skills/spark/completion.md:260` says `spec_status: draft  # always draft` — which overrides the SKILL.md headless instruction.

**Impact:** High — models that load completion.md last will output `draft` for all modes, defeating the feature.

**Counter:** The distinction must be explicit in completion.md: "If headless mode (detect from prompt prefix) → `queued`. If interactive mode → `draft`." Currently SKILL.md says headless creates `draft` — that needs reversal.

---

### Argument 5: .notified-drafts files become orphaned state

**Concern:** The `.notified-drafts-{project_id}` files in `scripts/vps/` track which draft specs have been notified via Telegram. If Spark now creates `queued` directly (no draft phase), these files accumulate stale spec IDs that were never actually notified. More critically, `scan_drafts()` is being removed from orchestrator, and the callback's Step 5.5 won't write new entries for headless Spark runs. The dedup logic in pueue-callback.sh:236 checks `grep -qxF "$SPEC_ID" ".notified-drafts-${PROJECT_ID}"` to prevent duplicate approvals. If these files aren't cleaned up, future interactive Spark runs creating `draft` specs with reused IDs (after deletion+recreation) could silently skip approval notifications.

**Evidence:** `.notified-drafts-*` files exist at `scripts/vps/.notified-drafts-dld`, etc. (confirmed in git status). `pueue-callback.sh:236` dedup check only does `grep -qxF` — never removes entries. ID reuse after spec deletion is possible since sequential IDs count up globally.

**Impact:** Low — IDs are sequential and never reused in practice. But the files are growing unbounded.

**Counter:** Not a blocker. Could add periodic cleanup (e.g., entries older than 30 days), but that's YAGNI for now.

---

## Simpler Alternatives

### Alternative 1: Keep draft for both modes, remove only the orchestrator approval loop
**Instead of:** Teaching Spark to detect headless mode and produce `queued` directly
**Do this:** Keep Spark always creating `draft`. Remove `scan_drafts()` from orchestrator (it's already dead code). Have `pueue-callback.sh` auto-approve headless Spark runs by detecting the inbox task label and calling `_update_spec_status(..., "queued")` directly.
**Pros:** Zero changes to Spark skill prompts. No risk of completion.md desync. Cleaner separation: "draft" is always Spark's output, approval is always a distinct step.
**Cons:** Headless Spark still requires a callback-side auto-approve step. The approval buttons still appear in Telegram for headless runs (could filter by label).
**Viability:** High — this is actually how approve_handler.py already works; `handle_spec_approve` just calls `_update_spec_status(project["path"], spec_id, "queued")`. Could call it from callback for headless labels.

### Alternative 2: Skip the status change entirely — orchestrator scans for both `draft` and `queued`
**Instead of:** Making Spark produce `queued` for headless runs
**Do this:** Modify `scan_backlog()` in orchestrator.sh to also pick up `draft` specs from headless Spark runs (detect via spec frontmatter `Source: ...` field or a `headless: true` marker).
**Pros:** No skill prompt changes. No approval flow changes. Minimal code delta.
**Cons:** Violates the "only human-approved specs get to autopilot" invariant for interactive mode. Would require careful filtering to not auto-run interactively-created drafts.
**Viability:** Low — conflates interactive and headless outputs, creates ambiguity about which drafts are safe to auto-run.

### Alternative 3: Remove QA/Reflect auto-enqueue from callback only (partial alignment)
**Instead of:** Full north-star alignment (all 7 changes)
**Do this:** Only fix the callback's Step 6.5 (already done — it's a no-op comment block). The current code already doesn't write inbox items from QA/Reflect. The "stop after Autopilot → QA → Reflect" is already implemented.
**Pros:** Minimal risk. The stop-after-reflect behavior is already correct.
**Cons:** Doesn't address the `draft` vs `queued` inconsistency. Spark still creates `draft` in headless mode per completion.md.
**Viability:** Medium — solves half the problem with zero code risk.

**Verdict:** Alternative 1 is the safest path if spec quality risk is a concern. Full implementation is justified but the completion.md desync is a P0 — must fix atomically. The callback and orchestrator changes are low-risk since scan_drafts() is already dead code.

---

## Eval Assertions (Structured from Risk Analysis)

### Deterministic Assertions

| ID | Scenario | Input | Expected Behavior | Risk | Priority | Type |
|----|----------|-------|-------------------|------|----------|------|
| DA-1 | Headless Spark creates spec | inbox item with `[headless]` prefix | Spec created with `queued` status in backlog and spec file | High | P0 | deterministic |
| DA-2 | Interactive Spark creates spec | User types `/spark add feature X` | Spec created with `draft` status, approval buttons sent to Telegram | High | P0 | deterministic |
| DA-3 | scan_drafts() dead code removal | orchestrator.sh process_project() call | No call to scan_drafts() exists, no Telegram draft notifications from orchestrator | Med | P0 | deterministic |
| DA-4 | Callback after headless Spark | pueue task with skill=spark, label=inbox-TIMESTAMP | No approval buttons sent (SENT_APPROVAL=false, no draft found) | High | P0 | deterministic |
| DA-5 | Callback after interactive Spark | pueue task with skill=spark, label=project:SPEC-ID | Draft spec found, approval buttons sent via notify.py | High | P0 | deterministic |
| DA-6 | Orchestrator picks up queued spec | backlog.md has queued entry | scan_backlog() submits spec to autopilot within POLL_INTERVAL | High | P0 | deterministic |
| DA-7 | QA callback does NOT write inbox | pueue task with skill=qa, status=done | No inbox file written, no new pueue task queued beyond Reflect | High | P0 | deterministic |
| DA-8 | Reflect callback does NOT write inbox | pueue task with skill=reflect, status=done | No inbox file written, cycle stops after Reflect completes | High | P0 | deterministic |
| DA-9 | completion.md checklist agrees with SKILL.md | model reads both files in headless context | Both files say `queued` for headless mode, no contradiction | High | P1 | deterministic |
| DA-10 | Concurrent headless Sparks (same project) | Two inbox items dispatched simultaneously | Different spec IDs (or git merge conflict surfaced), no silent data loss | Med | P1 | deterministic |
| DA-11 | QA fail scenario | QA exits with code != 0 | Report written to ai/qa/, notify.py called, phase set to qa_failed, no inbox written | Med | P1 | deterministic |
| DA-12 | Reflect skipped (no pending diary) | diary/index.md has 0 pending entries | Callback logs "Skipping reflect: no pending diary entries", cycle stops cleanly | Low | P2 | deterministic |

### Side-Effect Assertions

| ID | Affected Component | File:line | Regression Check | Priority |
|----|-------------------|-----------|------------------|----------|
| SA-1 | pueue-callback.sh Step 5.5 | pueue-callback.sh:214-257 | Interactive Spark still gets approval notification (SENT_APPROVAL=true, buttons sent) | P0 |
| SA-2 | approve_handler.handle_spec_approve | approve_handler.py:240-259 | draft→queued transition still works when human presses "approve" button | P0 |
| SA-3 | scan_backlog() grep pattern | orchestrator.sh:200-201 | Still matches `queued` in backlog (grep pattern unchanged) | P0 |
| SA-4 | .notified-drafts files | scripts/vps/.notified-drafts-* | Not written for headless Spark runs (no approval notification sent) | P1 |
| SA-5 | qa-loop.sh report output | qa-loop.sh:74-113 | Reports still written to ai/qa/, nobody reads them automatically (by design) | P1 |
| SA-6 | SKILL.md headless mode description | .claude/skills/spark/SKILL.md:47-65 | Says `draft` in headless — must be updated to `queued` | P0 |
| SA-7 | template/.claude/skills/spark/completion.md | template/.claude/skills/spark/completion.md:45,99-101,260 | Must be synced with DLD copy per template-sync.md rules | P1 |

### Assertion Summary
- Deterministic: 12 | Side-effect: 7 | Total: 19

---

## What Breaks?

### Side Effects

| Affected Component | File:line | Why It Breaks | Fix Required |
|--------------------|-----------|---------------|--------------|
| completion.md checklist item 5 | .claude/skills/spark/completion.md:45 | Still says "Status = draft" — model obeys this over SKILL.md:44 | Change to context-conditional: headless → queued, interactive → draft |
| completion.md Status Sync self-check | .claude/skills/spark/completion.md:82-88 | Says "Setting spec file: Status → draft" (hardcoded) — breaks headless awareness | Update self-check verbiage |
| completion.md Status table | .claude/skills/spark/completion.md:97-101 | "Spark completed fully → draft" — applies to both modes, wrong for headless | Add mode-split to table |
| completion.md return YAML | .claude/skills/spark/completion.md:260 | `spec_status: draft  # always draft` — contradicts headless queued target | Change to `spec_status: queued` (headless) or `draft` (interactive) |
| SKILL.md headless behavior | .claude/skills/spark/SKILL.md:59 | Says "Create spec in `draft` status (orchestrator handles approval via Telegram)" — wrong for headless north-star | Change to "Create spec in `queued` status — no approval gate" |
| pueue-callback.sh Step 5.5 | pueue-callback.sh:229-231 | Greps backlog for `draft` only — headless Spark writes `queued`, approval block is silently skipped | No fix needed for headless (intended), but verify interactive path still works |
| .claude/agents/spark/facilitator.md | facilitator.md:250,263 | "Add to backlog (status: queued)" at line 250 is correct, but output format says "queued | draft" at 263 — already aligned but needs cleanup | Low priority clarification |
| scan_drafts() function | orchestrator.sh:371-425 | Dead code — never called in process_project(). Removing it is safe. | Delete function body |
| WILL_WRITE_INBOX logic | pueue-callback.sh:276-295 | Block still exists but Step 6.5 is a no-op comment. Messages referencing "Результат передан в Spark для оформления" (line 287) will now never fire since WILL_WRITE_INBOX is never true for qa/reflect. | Verify the conditional (EMPTY_RESULT, FEEDBACK_DEPTH_OK) — if WILL_WRITE_INBOX is always false by design now, remove the entire block to reduce confusion |

### Dependencies at Risk

| Dependency | Type | Risk | Mitigation |
|------------|------|------|------------|
| pueue-callback.sh Step 5.5 approval block | control flow | High | Verify interactive Spark approval still fires when spec is `draft` |
| approve_handler._update_spec_status | code | Med | Still needed for interactive `draft→queued` human approval |
| orchestrator.scan_drafts() | dead code | Low | Safe to delete — but verify `.notified-drafts-*` file consumers won't break |
| template/.claude/skills/spark/completion.md | doc sync | Med | template-sync.md requires universal changes go to template first |
| tests/test_approve_handler.py | test coverage | Med | Tests verify `draft→queued` transition (line 4) — these must still pass |

---

## Test Derivation

All test cases are captured in `## Eval Assertions` above as DA-IDs and SA-IDs.
Facilitator maps these to EC-IDs in the spec's `## Eval Criteria` section.

---

## Questions to Answer Before Implementation

1. **Question:** Does "headless Spark creates queued" apply to bughunt grouped specs too?
   **Why it matters:** `completion.md:140-141` says Bug Hunt grouped specs go to `queued` status. But `completion.md:155-157` shows them as `draft` in the backlog example. If bughunt is always headless (pueue-dispatched), do its grouped specs also skip approval?

2. **Question:** What happens to the existing `.notified-drafts-*` files when scan_drafts() is removed?
   **Why it matters:** These files persist on disk and are still read by pueue-callback.sh:236 for dedup. If they're not cleaned up, a future reuse scenario could silently suppress approval notifications (low probability but non-zero).

3. **Question:** Is the "stop after Autopilot → QA → Reflect" already enforced, or does this feature need to add enforcement?
   **Why it matters:** Reviewing the current `pueue-callback.sh` Step 6.5, it is already a no-op comment block: "North star: only OpenClaw writes inbox items after reviewing artifacts." If this is already in place (from the recent TECH-150 spec), the scope of this feature is smaller than implied — mainly the `draft→queued` change in Spark skill docs.

4. **Question:** The Telegram approval buttons (`spec_approve`, `spec_rework`, `spec_reject`) — do they still make sense in a world where headless Spark skips to `queued`?
   **Why it matters:** Interactive Spark still produces `draft` and needs approval buttons. But if headless Spark produces `queued`, there will never be a `draft` spec from headless runs, and the approval buttons become interactive-only. The approve_handler tests will continue to cover the interactive path, but no test exists for "headless Spark creates queued directly, orchestrator picks up without approval."

5. **Question:** Should `qa-loop.sh` still exist given that pueue-callback.sh now dispatches QA directly via pueue?
   **Why it matters:** `qa-loop.sh` runs `/qa` via the legacy `claude` CLI (not Agent SDK), while pueue-callback.sh dispatches via `run-agent.sh` → `claude-runner.py` (Agent SDK). These are different execution paths. The current orchestrator's `dispatch_qa()` function (lines 330-365) is already a stub that only checks invariants and logs that "callback owns tail dispatch." `qa-loop.sh` may be entirely unused.

---

## Final Verdict

**Recommendation:** Proceed with caution

**Reasoning:** The north-star model is sound. The orchestrator `scan_drafts()` function is already dead code. The callback's Step 6.5 no-op is already correct. The actual risk is concentrated in ONE place: `completion.md` has four independent locations that say `draft`, and `SKILL.md:59` says "create spec in `draft` status" for headless mode. If the coder changes only SKILL.md and not completion.md, the LLM will still produce `draft` for all runs because completion.md is read AFTER SKILL.md and has blocking checklist items. This is not a minor doc cleanup — it's the entire mechanism by which Spark knows what status to write.

**Conditions for success:**
1. `completion.md` must be updated atomically: lines 45, 82-88, 97-101, and 260 must all reflect mode-conditional status. Headless → `queued`. Interactive → `draft`. This is a P0 blocker.
2. `SKILL.md:59` must be corrected from "Create spec in `draft` status" to "Create spec in `queued` status" under the headless mode section.
3. Template sync: `template/.claude/skills/spark/completion.md` must receive identical updates per `template-sync.md` rules — universal improvement applies to template first.
4. `scan_drafts()` removal must be verified as dead code (confirmed: not called in `process_project()` since the TECH-150 refactor).
5. The interactive Spark approval flow must be regression-tested end-to-end: interactive `/spark` → `draft` in backlog → Telegram approval buttons → `draft→queued` via approve_handler → orchestrator picks up.
