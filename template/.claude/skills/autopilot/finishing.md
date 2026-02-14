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

3. Pre-Done Checklist (see below)
   └─ ALL items must be checked

4. Update status → done
   └─ Spec file: **Status:** done
   └─ Backlog: done
   └─ VERIFY both match!

5. Commit status change:
   git commit -m "docs: mark {TYPE}-XXX as done"

6. Push feature branch (backup):
   git push -u origin {type}/{ID}

7. Merge to develop:
   cd "$MAIN_REPO"
   git checkout develop
   git stash push -m "autopilot-temp" (if uncommitted)
   git pull --rebase origin develop
   git merge --ff-only {type}/{ID}
   git push origin develop
   git stash pop (if stashed)

8. Cleanup:
   git worktree remove ".worktrees/{ID}" --force
   git branch -d {type}/{ID}

9. Loop Mode Exit Check:
   If SPEC_ID was provided (loop mode):
   - Do NOT continue to next spec
   - Do NOT call /compact
   - EXIT cleanly — external orchestrator handles next
   - Fresh context will be provided for next spec

   If interactive mode (no SPEC_ID):
   - Continue to next queued spec
   - Context already managed by orchestrator
```

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
