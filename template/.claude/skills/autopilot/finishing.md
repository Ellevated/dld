# Finishing Workflow (PHASE 3)

**Note:** In loop mode (SPEC_ID provided), step 9 exits immediately after merge.
External orchestrator (`autopilot-loop.sh`) provides fresh context for next spec.

Final verification, status update, merge, and cleanup.

## Flow

```
1. Final test: ./test fast
   └─ must pass!

2. Exa Verification (see below)
   └─ warnings only, never block

3. REFLECT (v2, NEW — see below)
   └─ Write upstream signals if issues found
   └─ Informational only, never blocks

4. Pre-Done Checklist (see below)
   └─ ALL items must be checked

5. Update status → done
   └─ Spec file: **Status:** done
   └─ Backlog: done
   └─ VERIFY both match!

6. Commit status change:
   git commit -m "docs: mark {TYPE}-XXX as done"

7. Push feature branch (backup):
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
   git push origin develop
   git stash pop (if stashed)

9. Cleanup:
   **Safety check:** Verify no uncommitted changes before force-removal
   ```bash
   cd ".worktrees/{ID}"
   if ! git diff-index --quiet HEAD -- 2>/dev/null; then
     echo "ERROR: Worktree has uncommitted changes! Aborting cleanup."
     git status --short
     exit 1
   fi
   cd -
   ```

   git worktree remove ".worktrees/{ID}" --force
   git branch -d {type}/{ID}

10. Loop Mode Exit Check:
    If SPEC_ID was provided (loop mode):
    - Do NOT continue to next spec
    - Do NOT call /compact
    - EXIT cleanly — external orchestrator handles next
    - Fresh context will be provided for next spec

    If interactive mode (no SPEC_ID):
    - Continue to next queued spec
    - Context already managed by orchestrator
```

## Reflect (v2, NEW)

After tests pass, before Pre-Done Checklist:

**Step 1:** Compare spec (what was planned) vs git diff (what was done)

**Step 2:** Check for issues:
- Were there debug retries? (check debug log)
- Were there escalations? (check escalation log)
- Did coder find spec gaps during implementation?
- Did blueprint compliance check fail and need fixes?

**Step 3:** If issues found, write upstream signals:

```yaml
Task tool:
  subagent_type: "diary-recorder"
  model: haiku
  prompt: |
    spec_id: "{TASK_ID}"
    spec_path: "ai/features/{TASK_ID}*.md"
    git_diff_summary: "{summary of changes}"
    issues_found:
      - type: gap | contradiction | missing_rule
        message: "{what was missing or wrong}"
        evidence: "{file:line — specific evidence}"

    TASK: Write upstream signal to ai/reflect/upstream-signals.md
    Format: SIGNAL-{timestamp} with source=autopilot, target=spark|architect

    If no issues → write nothing (no empty signals!)
```

**Rules:**
- Reflect is INFORMATIONAL — never blocks finishing
- Only write signals for REAL issues, not cosmetic differences
- If spec was perfect → skip reflect (no signal needed)

---

## Exa Verification

After `./test fast` passes, verify the approach against known pitfalls:

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

## Pre-Done Checklist

⛔ **Before setting status=done, verify ALL items:**

### Code Quality
- [ ] `./test fast` passes (run it!)
- [ ] No `# TODO` or `# FIXME` in changed files
- [ ] All tasks from Implementation Plan completed

### Definition of Done
- [ ] Each item in spec's "Definition of Done" section checked
- [ ] E2E user journey works (for UI features)

### Documentation
- [ ] If BREAKING/FEATURE change → changelog entry added
- [ ] Related docs updated

### Autopilot Log Completeness
For EACH task, verify:
- [ ] Coder entry present
- [ ] Tester entry present
- [ ] Spec Reviewer entry with status
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
- [ ] Status synced: spec=done AND backlog=done
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
- Spec Reviewer: approved | needs_implementation | needs_removal
- Code Quality Reviewer: approved | needs_refactor
- Exa Verify: no issues | WARNING: {description}
- Local Verify: pass | warn: {details} | skip (no AV)
- Post-Deploy Verify: pass | warn: {details} | skip (no URL)
- Commit: abc1234 | BLOCKED (reviewer not approved)
```

## Status Sync (MANDATORY)

**Status must match in TWO places:**

| Transition | Feature File | Backlog |
|------------|--------------|---------|
| Start work | `**Status:** in_progress` | `in_progress` |
| Blocked | `**Status:** blocked` | `blocked` |
| Complete | `**Status:** done` | `done` |

**Self-check (say out loud):**
```
"Updating spec file: Status → done" [Edit spec]
"Updating backlog: Status → done"   [Edit backlog]
"Both updated? ✓"                   [Verify match]
```

## Git Safety for Merge

- ⛔ **NEVER push to `main`** — only `develop`
- ⛔ **NEVER auto-resolve conflicts** → STATUS: blocked
- ✅ Use `--ff-only` for merge (ensures clean history)
- ✅ Stash uncommitted changes before merge (parallel agents)
