# Devil's Advocate — Worktree Cleanup After Merge

## Why NOT Do This?

### Argument 1: The "Deterministic" Cleanup Is Actually Non-Deterministic
**Concern:** The cleanup is proposed as part of `autopilot-loop.sh` — but that script is driven by an LLM agent (`claude --print "autopilot $SPEC_ID"`). The LLM executes the PHASE 3 steps. If the LLM session crashes, runs out of tokens, hits a compaction event, or exits early (status still `in_progress`), the cleanup step at the end of `finishing.md` never runs. The worktree is orphaned. This is the EXACT failure mode the feature is trying to fix.

**Evidence:** `autopilot-loop.sh:142-145` explicitly handles the case where status is still `in_progress` after the Claude run — meaning the session ended before finishing. The cleanup is inside the session. Cleanup-after-crash requires cleanup to be OUTSIDE the session.

**Impact:** High

**Counter:** Cleanup must live in `autopilot-loop.sh` itself (bash, not LLM), triggered unconditionally AFTER each Claude invocation, checking for stale worktrees by SPEC_ID. This is the only reliable position.

---

### Argument 2: `git diff-index --quiet HEAD` Is an Insufficient Safety Check
**Concern:** The proposed uncommitted-change check (`git diff-index --quiet HEAD --`) only detects changes to tracked files. It silently passes for: (a) untracked files not in .gitignore, (b) new files staged but not yet committed, and (c) the `.env` file that was manually copied into the worktree (worktree-setup.md:45 — `cp "$MAIN_REPO/.env" ".worktrees/{ID}/.env"`). The `--force` flag on `git worktree remove` then deletes the directory regardless.

**Evidence:** `worktree-setup.md:97` uses `git diff-index --quiet HEAD --`. This passes even when `git status` shows `??` (untracked) entries. In Python/Node projects, a developer might have run database setup or created debug output files in the worktree that are .gitignored but represent real work.

**Impact:** Medium

**Counter:** Use `git status --porcelain` instead — it catches both tracked changes AND untracked files (the `??` lines). The check is one line to fix. The `.env` copy specifically should be deleted explicitly before the `--force` remove, not relied on silently.

---

### Argument 3: `--force` + `git branch -D` vs `git branch -d` Mismatch Creates Data Loss Cliff
**Concern:** `finishing.md:70` uses `git worktree remove --force` (correct) but `finishing.md:71` uses `git branch -d` (safe, refuses if unmerged). However, `autopilot-git.md:243` uses `git branch -D` (force delete, no merge check). These two places have inconsistent semantics. The cleanup script writer will pick one. If they pick `-D`, a branch that was never actually merged (ff-only merge failed silently, push succeeded but merge didn't apply) gets deleted with no recovery path.

**Evidence:** `autopilot-git.md:243` — `git branch -D ${BRANCH_PREFIX}/${TASK_ID}`. Compare `finishing.md:71` — `git branch -d {type}/{ID}`. Two different sources, two different flags.

**Impact:** High

**Counter:** Always use `git branch -d` (lowercase) in cleanup. If it refuses (branch unmerged), that's a signal something went wrong — surface it instead of forcing deletion. Add explicit merge verification before any branch deletion: `git merge-base --is-ancestor {branch} develop`.

---

### Argument 4: Symlink `.claude` in Worktree Creates Cleanup Ordering Problem
**Concern:** `worktree-setup.md:41` creates `ln -s "$MAIN_REPO/.claude" ".worktrees/{ID}/.claude"`. When `git worktree remove --force` runs, it removes the worktree directory. On some platforms/configurations, if the symlink target resolution is cached (or if the worktree is the CWD of any running process), removal can leave the main `.claude` directory inaccessible temporarily, or the hooks runner (`run-hook.mjs`) which uses `git worktree list` to find main repo root may get confused during the cleanup window.

**Evidence:** `run-hook.mjs:30-35` — on every hook invocation, calls `git worktree list --porcelain` and takes the FIRST worktree as root. During cleanup, if `git worktree list` lists a worktree that's mid-removal, the hook runner could resolve to the wrong root. The 5-second timeout means this is a real race window.

**Impact:** Medium

**Counter:** Remove the `.claude` symlink explicitly before `git worktree remove` to ensure clean state. Add to cleanup sequence: `rm -f ".worktrees/{ID}/.claude"` before the remove command.

---

### Argument 5: Remote Branch Deletion Has No Business Being Automatic
**Concern:** The proposal mentions "remote cleanup — deleting remote branches." The current `finishing.md` only pushes feature branch as backup then merges. Automatic `git push origin --delete feature/FTR-XXX` after merge introduces: (a) PR invalidation if a teammate opened a review, (b) irreversible action (unlike local branch restore from reflog), (c) GitHub/GitLab branch protection rules that may reject the deletion and cause the script to fail, blocking the entire cleanup flow.

**Evidence:** `finishing.md:33` pushes feature branch to remote as "backup." The word "backup" is in the comment. Deleting the backup immediately after creating it defeats its purpose. There is no current `git push origin --delete` anywhere in the autopilot codebase.

**Impact:** High — remote deletion is irreversible and affects collaborators.

**Counter:** Do not add remote branch deletion to the automatic cleanup. Remote branches are cheap. Add a standalone `scripts/cleanup-remote-branches.sh` that lists merged-and-pushed branches and asks for confirmation before deleting. Run manually, not automatically.

---

## Simpler Alternatives

### Alternative 1: Bash Cleanup Guard in autopilot-loop.sh (No New Script)
**Instead of:** A standalone cleanup script + integration into autopilot-loop.sh
**Do this:** Add a 10-line bash cleanup block directly inside `autopilot-loop.sh` after the Claude invocation exits:

```bash
# After each claude run, check for orphaned worktrees matching this SPEC_ID
WORKTREE_PATH="${BASE_DIR}/.worktrees/${SPEC_ID}"
if [[ -d "$WORKTREE_PATH" ]]; then
  cd "$WORKTREE_PATH"
  if git diff-index --quiet HEAD -- 2>/dev/null && \
     [[ -z "$(git status --porcelain 2>/dev/null)" ]]; then
    cd "$BASE_DIR"
    git worktree remove "$WORKTREE_PATH" --force 2>/dev/null || true
    git worktree prune 2>/dev/null || true
  fi
fi
```

**Pros:** Zero new files. Runs in bash, not LLM. Idempotent. Runs even if LLM crashed.
**Cons:** Only handles the single SPEC_ID that just ran, not older orphans.
**Viability:** High — solves 90% of the problem.

---

### Alternative 2: Periodic Stale-Worktree Scanner (Cron/Systemd Timer)
**Instead of:** Cleanup in autopilot pipeline at all
**Do this:** A separate `scripts/cleanup-stale-worktrees.sh` that runs every 30 minutes and removes worktrees whose branch is already merged into develop.

```bash
for wt in $(git worktree list --porcelain | grep "worktree .worktrees" | awk '{print $2}'); do
  branch=$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null)
  if git merge-base --is-ancestor "$branch" develop 2>/dev/null; then
    # clean, merged — safe to remove
    git worktree remove "$wt" --force
  fi
done
```

**Pros:** Decoupled from pipeline. Handles ALL orphans, not just current run. Works even if autopilot-loop.sh was killed.
**Cons:** Adds cron dependency. 30-minute lag. Doesn't cover local-only branches not pushed.
**Viability:** Medium — better as complement to Alternative 1, not replacement.

---

### Alternative 3: Fix The Spec Only (No New Code)
**Instead of:** New cleanup scripts
**Do this:** Fix the inconsistency in the two existing cleanup blocks (`finishing.md` and `autopilot-git.md`) and add the `--porcelain` check. The reason cleanup "doesn't reliably happen" is the LLM exits early — not that the cleanup code is wrong. The real fix is adding the bash guard in `autopilot-loop.sh` (line 119, after the claude command).

**Pros:** Minimal surface area. Fixes the root cause (cleanup outside the LLM session).
**Cons:** Doesn't provide a standalone cleanup command for manual use.
**Viability:** High — addresses the stated problem directly.

**Verdict:** Alternative 3 + Alternative 1 (bash guard in loop) solves the stated problem with ~20 lines of code. Skip the standalone cleanup script and remote deletion entirely. If a standalone script is needed, it should be additive — never automatic for remote branches.

---

## Eval Assertions (Structured from Risk Analysis)

### Deterministic Assertions

| ID | Scenario | Input | Expected Behavior | Risk | Priority | Type |
|----|----------|-------|-------------------|------|----------|------|
| DA-1 | LLM session crashes mid-execution, status stays `in_progress` | `claude --print "autopilot FTR-XXX"` exits non-zero, `.worktrees/FTR-XXX/` exists | Bash cleanup guard in loop detects worktree, checks clean state, removes it | High | P0 | deterministic |
| DA-2 | Worktree has untracked files (e.g. debug output, generated DB) | `git diff-index --quiet HEAD --` passes, but `git status --porcelain` shows `??` entries | Cleanup aborts, logs warning, does NOT remove worktree | High | P0 | deterministic |
| DA-3 | Cleanup script runs twice for same SPEC_ID | First run removes worktree, second run finds no `.worktrees/FTR-XXX/` | Script exits 0 silently, no error | Medium | P1 | deterministic |
| DA-4 | Branch was manually created with same name as autopilot convention | Branch `feature/FTR-XXX` exists but was not created by autopilot | Cleanup checks `git merge-base --is-ancestor` before deletion; if not merged, skip | High | P0 | deterministic |
| DA-5 | ff-only merge succeeded locally but `git push origin develop` failed | Branch merged to local develop, but remote develop is behind | Branch appears merged locally, deleted — but remote never got the code | High | P0 | deterministic |
| DA-6 | VPS: two projects have worktrees simultaneously, cleanup runs for project A | `.worktrees/FTR-XXX` in project A path, same ID pattern exists in project B | Cleanup scoped to `BASE_DIR` / `PROJECT_DIR` env var — no cross-project deletion | High | P0 | deterministic |
| DA-7 | `.claude` symlink exists in worktree, cleanup runs | `ln -s MAIN_REPO/.claude .worktrees/{ID}/.claude` present | Symlink removed before `git worktree remove` to avoid resolution confusion | Medium | P1 | deterministic |
| DA-8 | `git branch -d` refuses (branch not fully merged per git's check) | Feature branch was squash-merged (not ff-only), git doesn't see it as ancestor | Cleanup logs "branch not fully merged per git" and skips branch deletion — surfaces to human | Medium | P1 | deterministic |
| DA-9 | Worktree directory exists but is not registered in git (manually deleted .git/worktrees entry) | `git worktree list` doesn't show the path, but directory exists | `git worktree prune` removes stale references, then `rm -rf` safe since not tracked | Low | P2 | deterministic |
| DA-10 | Remote branch deletion attempted automatically | `git push origin --delete feature/FTR-XXX` in cleanup | This command must NOT exist in automatic cleanup paths | High | P0 | deterministic |

### Side-Effect Assertions

| ID | Affected Component | File:line | Regression Check | Priority |
|----|-------------------|-----------|------------------|----------|
| SA-1 | `run-hook.mjs` worktree root resolution | `.claude/hooks/run-hook.mjs:30-35` | After cleanup, `git worktree list --porcelain` returns correct main repo as first entry | P0 |
| SA-2 | `autopilot-loop.sh` iteration counter | `scripts/autopilot-loop.sh:86-155` | Cleanup failure must not block next iteration (use `|| true` on cleanup calls) | P0 |
| SA-3 | `finishing.md` cleanup block | `.claude/skills/autopilot/finishing.md:59-71` | Existing safety check (`git diff-index`) still present; upgrade to `--porcelain` check | P1 |
| SA-4 | `autopilot-git.md` cleanup block | `.claude/skills/autopilot/autopilot-git.md:242-244` | `-D` flag usage audited; replaced with `-d` + merge-ancestor verification | P1 |
| SA-5 | VPS orchestrator parallel execution | `scripts/vps/orchestrator.sh:236-243` | Pueue tasks for different projects use `PROJECT_DIR` scoping; cleanup respects same scoping | P0 |

### Assertion Summary
- Deterministic: 10 | Side-effect: 5 | Total: 15

---

## What Breaks?

### Side Effects

| Affected Component | File:line | Why It Breaks | Fix Required |
|--------------------|-----------|---------------|--------------|
| `run-hook.mjs` root resolution | `.claude/hooks/run-hook.mjs:30` | During cleanup window, `git worktree list` may list being-removed worktree first, resolving to wrong root | Remove `.claude` symlink before `git worktree remove` |
| `finishing.md` cleanup | `.claude/skills/autopilot/finishing.md:59-71` | `git diff-index` check misses untracked files — false "clean" signal | Replace with `git status --porcelain` |
| `autopilot-git.md` cleanup | `.claude/skills/autopilot/autopilot-git.md:243` | `-D` flag deletes even unmerged branches silently | Use `-d` + merge check |
| `autopilot-loop.sh` | `scripts/autopilot-loop.sh:118-119` | Cleanup inside LLM session never runs on crash | Add bash cleanup guard after line 121 (after `EXIT_CODE=$?`) |

### Dependencies at Risk

| Dependency | Type | Risk | Mitigation |
|------------|------|------|------------|
| git worktree internal `.git/worktrees/` tracking | data | High — inconsistent state if process killed mid-remove | Always run `git worktree prune` after any removal attempt |
| `PROJECT_DIR` env var (VPS multi-project) | config | High — missing env var defaults to `.` (current dir), could scope cleanup incorrectly | Assert `PROJECT_DIR` is set and is an absolute path before running any cleanup |
| Remote feature branch (pushed as "backup") | git remote | High — auto-deletion loses backup and invalidates potential PRs | Never auto-delete remote; only local |
| `.env` copied into worktree | file | Low — `git worktree remove --force` silently deletes it | Acceptable; `.env` is a copy, not the source |

---

## Test Derivation

All test cases are captured in `## Eval Assertions` above as DA-IDs and SA-IDs.
Facilitator maps these to EC-IDs in the spec's `## Eval Criteria` section.

---

## Questions to Answer Before Implementation

1. **Question:** Where does cleanup live — inside the LLM session (finishing.md) or outside (autopilot-loop.sh bash guard)?
   **Why it matters:** Cleanup inside the session is exactly as reliable as the session itself. If the goal is "deterministic cleanup," it MUST be in bash outside the LLM. Both can coexist but the bash guard is the safety net.

2. **Question:** Should the standalone cleanup command (`scripts/cleanup-worktrees.sh`) be interactive (prompts before delete) or fully automatic?
   **Why it matters:** Fully automatic risks deleting worktrees that look merged but aren't (squash merges, rebased branches). Interactive is safer. The difference is one `read -p` call but the consequence of getting it wrong is data loss.

3. **Question:** What is the merge verification method — `git branch -d` refusal, or `git merge-base --is-ancestor branch develop`?
   **Why it matters:** `git branch -d` uses git's internal ancestry check which fails for squash-merges (common pattern). `git merge-base --is-ancestor` is also false for squash merges. The only reliable check for squash-merge scenarios is checking if the branch's unique commits appear in develop's log — which requires `git log develop..branch --oneline | wc -l`. Squash merge = 0 unique commits in branch after merge.

4. **Question:** Does the VPS orchestrator's `scan_backlog` function ever dispatch the same SPEC_ID twice before the first run completes?
   **Why it matters:** If it does, the second autopilot run creates a new worktree for the same ID, finds the old one already exists, and the worktree-setup.md Step 5 `git worktree add` will FAIL (branch already exists). Current code in `autopilot-git.md:311-312` handles resumed tasks by force-removing old worktree — but only when status is `resumed`, not `queued`. A double-dispatch on `queued` would fail at worktree creation.

5. **Question:** Is `git worktree remove --force` safe when the worktree's process has an open file handle?
   **Why it matters:** On Linux, open file handles don't prevent directory deletion (unlink semantics). On macOS, same. But git's worktree internal state file (`.git/worktrees/{id}/locked`) could be present and `--force` ignores it. The lock file exists to signal "this worktree is intentionally in use." Ignoring it is the current behavior — is this intentional for the cleanup case?

---

## Final Verdict

**Recommendation:** Proceed with caution

**Reasoning:** The feature is necessary — worktree accumulation is a real operational problem. But the proposed approach (cleanup script + integration in autopilot-loop.sh) has at least 3 high-risk issues that must be resolved before implementation: (1) the bash guard vs LLM session placement, (2) the `-D` vs `-d` inconsistency that already exists and will be copy-pasted into new code, and (3) the absolute prohibition on automatic remote branch deletion.

The good news: the fix is ~20-30 lines of bash correctly placed in `autopilot-loop.sh` plus one doc fix in `finishing.md`. That's the 90% solution. The standalone script is a nice-to-have.

**Conditions for success:**
1. Cleanup bash guard MUST be in `autopilot-loop.sh` (outside LLM session), not just in `finishing.md` — this is the primary safety net
2. Safety check MUST use `git status --porcelain` not `git diff-index` — catches untracked files
3. Branch deletion MUST use `git branch -d` (not `-D`) + `git merge-base --is-ancestor` verification
4. Remote branch deletion MUST NOT be automatic — document as manual-only operation with explicit confirmation
5. Symlink `.claude` MUST be removed before `git worktree remove` to avoid hook root resolution race
6. Fix the existing inconsistency: `finishing.md` uses `-d`, `autopilot-git.md:243` uses `-D` — align both to `-d`
