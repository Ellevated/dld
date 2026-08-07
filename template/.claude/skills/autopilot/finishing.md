# Finishing Workflow (PHASE 3)

**Note:** In loop mode (SPEC_ID provided), step 9 exits immediately after merge.
The VPS orchestrator (`scripts/vps/orchestrator.py`) dispatches the next spec
as a fresh Agent SDK session via pueue.

Final verification, status update, merge, and cleanup.

## Flow

```
1. Final test: ./test ci
   └─ must pass! (CI-parity gate)
   └─ no `./test ci`? → CI_PARITY_UNAVAILABLE fallback (see autopilot-git.md §5.6)

2. Exa Verification (see below)
   └─ warnings only, never block

3. REFLECT (see below)
   └─ Write upstream signals if issues found
   └─ Informational only, never blocks

3.5. DOCUMENTER (subagent — see below)
   └─ Brings docs back in line with the code, once per spec
   └─ Commits its own edits to the feature branch
   └─ Never blocks: a documenter failure is a warning, not a stop

4. Pre-Done Checklist (see below)
   └─ ALL items must be checked

5. Emit task_status in final JSON output:
   └─ `"task_status": "complete"` — all tasks done, callback marks done
   └─ `"task_status": "blocked"` — needs human, callback marks blocked
   └─ `"task_status": "needs_review"` — uncertain, callback marks blocked
   └─ Do NOT Edit `**Status:**` in spec or backlog — callback writes it
   └─ No separate status commit — callback writes status post-pueue

6. Push feature branch (backup):
   git push -u origin {type}/{ID}

7.5. POST-DEPLOY VERIFY (conditional):
   If spec has DEPLOY_URL (not "local-only"):
   a. Poll DEPLOY_URL every 10s (max 120s wait)
   b. Run Smoke checks from spec against DEPLOY_URL
   c. Run Functional checks from spec against DEPLOY_URL
   All results are WARN only, never blocks.
   No DEPLOY_URL or "local-only" → skip entirely.

8. Merge to develop:
   cd "$MAIN_REPO"
   git checkout develop
   git stash push -m "autopilot-temp" (if uncommitted)
   git pull --rebase origin develop
   git merge --ff-only {type}/{ID}

   CI-parity merge gate — BEFORE push:
   ./test ci on merged tree. Red → git reset --hard origin/develop
   (abort merge), emit needs_review, do NOT push.
   No `./test ci`? → CI_PARITY_UNAVAILABLE fallback (autopilot-git.md §5.6).

   git push origin develop
   git stash pop (if stashed)

   ⛔ PUSH GUARD: If `git push origin develop` fails (even
   after retry), emit `"task_status": "needs_review"` instead of
   `"complete"` in the final JSON. Work is merged locally but not
   on origin — callback push-local will attempt recovery, but the
   signal must reflect the uncertainty.

8.5. Preserve telemetry (before worktree cleanup):
   ```bash
   cp ".worktrees/{ID}/autopilot-state.json" "ai/diary/{ID}-state.json" 2>/dev/null || true
   ```
   Rich execution data (per-step timing, retries, outcomes) preserved for /reflect.

9. Cleanup:
   **Safety check:** Verify no uncommitted changes before force-removal
   ```bash
   cd ".worktrees/{ID}"
   if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
     echo "ERROR: Worktree has uncommitted changes! Aborting cleanup."
     git status --short
     exit 1
   fi
   cd -
   ```

   rm -f ".worktrees/{ID}/.claude" 2>/dev/null  # remove symlink first
   git worktree remove ".worktrees/{ID}" --force
   git branch -d {type}/{ID}
   git worktree prune

10. Loop Mode Exit Check:

    ⛔ MANDATORY — check this BEFORE doing anything else after cleanup.

    If SPEC_ID was provided (loop mode):
    - STOP HERE. Session is COMPLETE.
    - Do NOT continue to next spec
    - Do NOT call /compact
    - Do NOT read backlog for more work
    - Do NOT start any unrelated work
    - EXIT cleanly — external orchestrator handles next
    - Fresh context will be provided for next spec
    - ANY further work is a governance violation (BUG-199)

    If interactive mode (no SPEC_ID):
    - Continue to next queued spec
    - If queue empty → STOP
    - Context already managed by orchestrator
```

## Reflect

After tests pass, before Pre-Done Checklist:

**Step 1:** Compare spec (what was planned) vs git diff (what was done)

**Step 2:** Check for issues:
- Were there debug retries? (check debug log)
- Were there escalations? (check escalation log)
- Did coder find spec gaps during implementation?
- Did blueprint compliance check fail and need fixes?

**Step 3:** If issues found, write upstream signals directly (no subagent — ADR-007):

```
Edit tool → ai/reflect/upstream-signals.md

Append:
---
### SIGNAL-{YYYY-MM-DD-HHMM}
- **Source:** autopilot ({TASK_ID})
- **Target:** spark | architect
- **Type:** gap | contradiction | missing_rule
- **Message:** {what was missing or wrong}
- **Evidence:** {file:line — specific evidence}
```

If no issues → write nothing (no empty signals!).

**Rules:**
- Reflect is INFORMATIONAL — never blocks finishing
- Only write signals for REAL issues, not cosmetic differences
- If spec was perfect → skip reflect (no signal needed)

---

## Exa Verification

After `./test ci` passes (step 1), verify the approach against known pitfalls:

**Step 1:** Extract key patterns from spec
- Read spec's `## Design` and `## Approaches` sections
- Identify: libraries used, patterns chosen, architecture decisions

**Step 2:** Search for pitfalls
```yaml
mcp__exa__web_search_exa:
  query: "{pattern_used} {library} common pitfalls production issues"
  numResults: 5
```

**Step 3:** Search for security concerns
```yaml
mcp__exa__web_search_exa:
  query: "{library} security vulnerabilities 2024 2025"
  numResults: 3
```

**Step 4:** Evaluate findings
- If critical issue found → add WARNING to Autopilot Log, flag for human review
- If minor concern → note in Autopilot Log
- If nothing found → proceed

**Rules:** Max 3 Exa calls. Don't block on this — warnings only.

---

## Documenter (Step 3.5)

Runs once per spec, here — not per task, and not after the merge.

Every task is committed and the branch is not yet merged, so the agent sees the whole
change at once and its edits ride into `develop` on the same merge as the code they
describe. Per task it would rewrite the same files from partial views; after the merge,
docs and code would sit diverged in `develop` until someone noticed. Documentation drift
is not free — stale docs cost the next session the same debugging time that a stale spec
costs autopilot.

```yaml
Task tool:
  subagent_type: "documenter"
  prompt: |
    spec_id: "{SPEC_ID}"
    spec_summary: "{one-line statement of what the spec set out to do}"
    feature_type: "{FTR | BUG | TECH | ARCH}"
    files_changed: [{union of files_changed across ALL tasks}]
```

```
├─ status: completed → note docs_updated in the Autopilot Log → Step 4
├─ status: skipped   → note the reason in the Autopilot Log → Step 4
└─ error / no return → WARN in the Autopilot Log, continue to Step 4
```

**Never blocks.** A spec whose code is correct does not become un-shippable because a
changelog entry failed to write. But a skip must be *recorded* — an unexplained silence
here is how the changelog fell 1.5 days behind before.

**Why the agent can edit files the spec never listed:** documentation paths
(`.env.example`, `ai/architecture/**`, `ai/changelog/**`, `ai/decisions/**`,
`ai/glossary/**`, `README.md`, `docs/**`) are in `alwaysAllowedPatterns` in
`.claude/hooks/hooks.config.mjs`. A spec's Allowed Files lists the code being changed,
never the docs describing it — before that exemption existed, this dispatch would have
been denied by the pre-edit hook on its own first edit.

## Pre-Done Checklist

⛔ **Before setting status=done, verify ALL items:**

### Code Quality
- [ ] `./test ci` passes (CI-parity gate)
- [ ] No `# TODO` or `# FIXME` in changed files
- [ ] All tasks from Implementation Plan completed

### Definition of Done
- [ ] Each item in spec's "Definition of Done" section checked
- [ ] E2E user journey works (for UI features)

### Documentation
- [ ] Documenter (Step 3.5) ran, and its result is in the Autopilot Log
- [ ] If it returned `completed` → its `docs_updated` list is recorded and committed
- [ ] If it returned `skipped` → the reason is recorded, not just the status

### Autopilot Log Completeness
For EACH task, verify:
- [ ] Coder entry present
- [ ] Tester entry present
- [ ] Spec compliance entry with result
- [ ] Code Quality entry with status
- [ ] Commit hash present

### Git State
- [ ] All changes committed
- [ ] Pushed to develop
- [ ] `git status` shows clean working directory

### Acceptance Verification (if spec has AV section)
- [ ] LOCAL VERIFY results logged for each task
- [ ] POST-DEPLOY VERIFY attempted (if DEPLOY_URL present)

### Cleanup
- [ ] Autopilot Log updated in spec file
- [ ] task_status emitted in final JSON output
- [ ] Worktree cleaned up

**❌ Any item unchecked → status stays `in_progress`, fix first!**

## Autopilot Log Format

Add to feature file:

```markdown
## Autopilot Log

### Task N/M: [Name] — YYYY-MM-DD HH:MM
- Coder: completed (N files: file1.py, file2.py)
- Tester: passed | failed → debug loop | skipped (no tests for .md)
- Deploy: applied | skipped (no migrations)
- Documenter: completed | skipped (no docs needed)
- Spec compliance: matches | missing something | extra beyond scope
- Code Quality Reviewer: approved | needs_refactor ({N} blocking, {M} advisory)
- Exa Verify: no issues | WARNING: {description}
- Local Verify: pass | warn: {details} | skip (no AV)
- Post-Deploy Verify: pass | warn: {details} | skip (no URL)
- Commit: abc1234 | BLOCKED (reviewer not approved)
```

## Status Writes — Callback Only

Autopilot MUST NOT modify `**Status:**` line in spec or status column in `ai/backlog.md`.
After tests pass, autopilot emits `task_status` in its final JSON output:
- `"task_status": "complete"` — all tasks done, ready for callback to mark done
- `"task_status": "blocked"` — needs human, callback marks blocked
- `"task_status": "needs_review"` — uncertain, callback marks blocked with reason

Callback (`scripts/vps/callback.py`) reads pueue exit code + `task_status` from agent JSON output
and writes status to `ai/lifecycle/{spec_id}.yaml` via git plumbing.

Migration: in-flight specs may still have legacy autopilot status edits — callback's guard
re-verifies via implementation guard.

## Git Safety for Merge

- ⛔ **NEVER push to `main`** — only `develop`
- ⛔ **NEVER auto-resolve conflicts** → STATUS: blocked
- ⛔ **NEVER squash-merge** — `--squash` loses commit subjects; callback gate reads `origin/develop` subjects to detect implementation
- ✅ Use `--ff-only` for merge (ensures clean history and preserves individual commit subjects)
- ✅ Stash uncommitted changes before merge (parallel agents)

---

## Forbidden — Lifecycle writes

- NEVER Edit `**Status:**` in `ai/features/*.md` or status column in `ai/backlog.md`.
- NEVER Edit `ai/lifecycle/*.yaml` directly.
- NEVER `git add ai/lifecycle/*.yaml` (pre-commit hook will REJECT).
- NEVER write commits with subjects like `chore(lifecycle): ...` or any non-canonical lifecycle format.

ONLY mechanism: emit `"task_status": "complete" | "blocked" | "needs_review"`
in your final agent JSON. callback.py reads it and atomically writes lifecycle yaml.

If callback fails to mark done (gate regex bug or similar) — that is a HUMAN OPERATOR
responsibility. Autopilot does NOT have `force-done` permission. Operator runs:
`python3 scripts/vps/spec_operator.py force-done <proj> <SPEC> "<reason>" --by=operator`.
