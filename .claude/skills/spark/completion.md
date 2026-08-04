# Spark Completion Logic

**Read this AFTER creating spec — Shared completion logic for both Feature and Bug modes**

---

## ID Determination Protocol (MANDATORY — Spec-First CAS, ARCH-196)

Use the Kafka-style spec-first pattern: **write claims the ID**. The lifecycle
plumbing (`create_initial` + CAS via `git update-ref`) guarantees uniqueness
even with concurrent spark sessions on multiple machines (multi-master).

### Protocol

1. **Compute candidate ID from HEAD lifecycle:**
   ```bash
   MAX=$(git ls-tree HEAD:ai/lifecycle/ 2>/dev/null \
         | grep -oE '(TECH|FTR|BUG|ARCH|GROWTH)-[0-9]+' \
         | sort -t- -k2 -n | tail -1 | grep -oE '[0-9]+$' || echo 0)
   NEXT=$((MAX + 1))
   CANDIDATE="{TYPE}-$(printf '%03d' $NEXT)"
   ```
2. **Claim the ID via CAS — where the module exists:**
   ```bash
   python3 -c "
   import sys; sys.path.insert(0, 'scripts/vps')
   import lifecycle
   lifecycle.create_initial('$REPO_DIR', '$CANDIDATE',
                            priority='$PRIORITY', kind='$KIND',
                            status='queued', by='spark')
   "
   ```

   **`scripts/vps/lifecycle.py` ships in the DLD repository only.** An orchestrated
   project has `ai/lifecycle/` full of records but no module to write them with — the
   agent runs with `cwd` set to the project, so the import fails there. If it does:

   - Do **not** hand-write the YAML. `write_lifecycle` is CAS-guarded, and the
     pre-commit hook rejects any staged `ai/lifecycle/*.yaml`.
   - **Do add a row for the spec to `ai/backlog.md`.** This is the one case where the
     backlog is written by hand, and it is not optional:
     `orchestrator_backlog.bootstrap_new_specs` reads `git show HEAD:ai/backlog.md`
     and **skips any spec whose id is absent** — `if spec_id not in backlog_ids:
     continue`, commented "Orphan spec.md (not in backlog) — skip. Historical
     artifact." With no module to claim the id and no row to be found, the spec is
     never bootstrapped, never dispatched, and never reported as anything: it simply
     sits in `ai/features/` forever.
   - Then the orchestrator creates the lifecycle record on its next cycle, dispatch
     proceeds, and from that point the row is maintained by the renderer rather than
     by you.

   *This paragraph said the opposite between 2026-08-02 and 2026-08-04* — "do not
   fall back to editing the backlog, bootstrap creates the record for any spec that
   lacks one". The second half is false: bootstrap creates it only for specs already
   named in the backlog. The correction that removed the hand-written row was right
   about DLD, where the module exists and the CAS claims the id, and wrong about every
   project DLD manages, where it is the only path a spec has.

   Know what this costs: the spec-first CAS exists to stop two machines claiming the
   same ID. Without the module, that protection is not in play — which is why
   interactive Spark runs from one machine at a time.
3. **Handle CAS collision** (concurrent spark on another machine claimed the
   same ID): if `LifecycleWriteRaceError` → re-read HEAD, recompute `NEXT = MAX + 1`,
   retry. Cap at **5 attempts**.
4. **On success** → lifecycle yaml is in HEAD with `by: spark`. Write
   `ai/features/{CANDIDATE}-YYYY-MM-DD-name.md`. **Do not touch `ai/backlog.md`** —
   see "The backlog is a render" below.
5. **On exhausted retries** → log WARNING `SPARK_ID_CAS_EXHAUSTED`, bump
   `ai/.spark-cas-exhausted-count`, fall back to `MAX + 5` with `cas-fallback`
   in transitions[0].reason.

**Numbering remains SEQUENTIAL ACROSS ALL TYPES** (see CLAUDE.md#Backlog-Rules).

---

## Pre-Completion Checklist (BLOCKING)

⛔ **DO NOT COMPLETE SPARK** without checking ALL items:

1. [ ] **ID determined by protocol** — not guessed!
2. [ ] **Uniqueness check** — `git ls-tree HEAD:ai/lifecycle/` did not already contain this ID
3. [ ] **Spec file created** — ai/features/TYPE-XXX-YYYY-MM-DD-name.md
4. [ ] **Lifecycle record accounted for** — either `ai/lifecycle/{TASK_ID}.yaml` exists
   (`create_initial` ran), or the module does not ship here and bootstrap will create it
5. [ ] **Status = queued** wherever that record ends up — never a second copy elsewhere
6. [ ] **Allowlist Linter passed** (Phase 5.5) — `grep '<!-- callback-allowlist v1' ai/features/{TASK_ID}*.md` returns ≥1 line and `## Allowed Files` heading exists exactly once
7. [ ] **Function overlap check** (ARCH-226) — grep other queued specs for same function names
   - If overlap found: merge into single spec OR mark dependency
8. [ ] **Auto-commit + push done** — `## Auto-Commit + Push (MANDATORY)` block executed

If any item not done — **STOP and do it**.

---

## Post-Write Verification (MANDATORY)

After the spec file is written, verify the two things the pipeline actually reads:

```bash
# 1. The spec file exists
ls ai/features/{TASK_ID}-*.md

# 2. Where the lifecycle module was available, the record is in HEAD and says queued
git show HEAD:ai/lifecycle/{TASK_ID}.yaml | grep -E '^status:'
# → status: queued
```

A missing YAML is only a failure **if `create_initial` was available and you ran it**.
Where the module does not ship (any orchestrated project — see step 2 of the ID protocol),
the spec file alone is the correct end state; bootstrap creates the record. Either way,
do not write the YAML or the backlog by hand.

---

## The backlog is a render — with exactly one exception

`ai/backlog.md` opens with `AUTO-GENERATED from ai/lifecycle/*.yaml — do not edit
manually`, and that is accurate:

| | |
|---|---|
| What dispatches your spec | `orchestrator.scan_queued` → `lifecycle.list_by_status(...)` reads `ai/lifecycle/*.yaml` |
| What produces the backlog | `callback._render_and_commit_backlog` → `render_backlog.render_backlog()`, from those same YAMLs, after every lifecycle write |

So a spec with a lifecycle record and no backlog row is **dispatched normally**, and its
row appears on the next render. A hand-written row, meanwhile, is racing a renderer that
rewrites the file from the YAMLs.

This section used to say the opposite — *"Spark without backlog entry = DATA LOSS! Autopilot
reads ONLY backlog"* — and instructed Spark to edit the table by hand. That was true before
ARCH-186/ADR-023 moved the source of truth into per-spec YAML, and false afterwards.
`orchestrator.scan_queued`'s own docstring has said so since: *"reads ai/lifecycle/*.yaml
(HEAD-based), not ai/backlog.md (which is now an auto-rendered read-only view)"*.
Reported from awardybot by an agent that declined to follow the checklist and raised a
signal instead — the right call, and half right. `scan_queued` does read the YAMLs. But
`bootstrap_new_specs` runs before it every cycle and refuses to create a YAML for a spec
the backlog does not name, so in a project where Spark cannot claim the id itself, the
hand-written row is not redundant bookkeeping — it is the whole handshake.

**The exception, stated once:** write a backlog row if and only if `create_initial` was
unavailable, i.e. `scripts/vps/lifecycle.py` does not ship in this repository. If the
module is there, the id is already claimed and the row is the renderer's business.

There is a known race under that exception: `callback._render_and_commit_backlog`
rewrites the file from the YAMLs after any lifecycle write, so a row added by hand can be
erased before the next bootstrap sees it. The window is one orchestrator cycle and closes
as soon as the record exists. It predates this note; it is recorded here rather than
discovered again.

**Status lives in exactly one place**, the lifecycle YAML. There is no second copy to keep
in sync, and nothing to "say out loud" — that ritual existed because there were two.

### Status on Spark exit:
| Situation | Status | Reason |
|-----------|--------|--------|
| Spark completed fully | `queued` | Ready for orchestrator pickup |
| Spec created but interrupted | `queued` | Orchestrator will pick up on next cycle |
| Needs discussion/postponed | `queued` | Left for refinement, orchestrator holds until slot available |

⛔ **`blocked` is NOT a valid status for a created spec.** Council/architect
decisions happen in Phase 4 — BEFORE the spec is written. If a decision is
still pending, the spec file must not exist yet: exit with `status: blocked,
spec_status: not_created` (same shape as a linter failure) and let the
orchestrator surface it to the user. A spec sitting in the backlog "waiting
for /council" is a process violation — a written spec means all decisions
are made, and its only status is `queued`.

---

## Backlog format

Not your concern — `render_backlog.py` owns the layout (sections by priority, sort order,
spec links) and rebuilds it from the lifecycle YAMLs. What determines how your spec appears
is what you passed to `create_initial`: `priority` and `kind`.

If a row looks wrong, fix the YAML field it came from, not the rendered table.

---

## File Naming Conventions

| Mode | Pattern | Example |
|------|---------|---------|
| Feature | `FTR-XXX-YYYY-MM-DD-name.md` | `FTR-089-2026-02-15-diagram-skill.md` |
| Quick Bug | `BUG-XXX-YYYY-MM-DD-name.md` | `BUG-082-2026-02-08-push-ambiguity.md` |
| Bug Hunt report | `BUG-XXX-bughunt.md` | `BUG-084-bughunt.md` |
| Bug Hunt grouped | `BUG-XXX.md` | `BUG-087.md` |

Bug Hunt grouped specs omit date/name for brevity (auto-generated, many at once).

---

## Bug Hunt Mode Output

Bug Hunt creates a READ-ONLY report + standalone grouped specs:

```
ai/features/
├── BUG-XXX-bughunt.md   ← report (READ-ONLY index, NOT in backlog)
├── BUG-YYY.md            ← standalone spec: Group 1 (queued)
├── BUG-ZZZ.md            ← standalone spec: Group 2 (queued)
└── ...
```

### Report (NOT in Backlog)

The report is a READ-ONLY index of what was found. It does NOT go into backlog.
File naming: `BUG-XXX-bughunt.md` (the XXX is the report ID, not a task ID).

### Grouped Specs (dispatchable)

Each group claims its OWN sequential ID through `create_initial`, and therefore gets its own
lifecycle record — which is what makes it dispatchable, and what puts it in the rendered
backlog. Three groups means three `create_initial` calls, not one record with three rows.

### ID Protocol for Grouped Specs

1. Report gets an ID (e.g., BUG-084) — used only for the report filename
2. Find global max ID in backlog (e.g., max is BUG-084)
3. Each group gets NEXT sequential ID: BUG-085, BUG-086, BUG-087, etc.
4. Each grouped spec is a standalone, independently executable spec

### Autopilot Handoff

Each grouped spec runs independently through autopilot:
```
BUG-085 → Planner → Coder → Tester → done
BUG-086 → Planner → Coder → Tester → done
...
```

Each spec is fully independent. User can run autopilot on any single spec.

---

## Headless Mode: Write SpecID to Inbox File (MANDATORY)

When running in headless mode (inbox-originated), write the spec ID back to the
originating inbox file so the pipeline can map inbox labels to real spec IDs.

After spec is created and BEFORE auto-commit:

1. Check env var: `CLAUDE_CURRENT_SPEC_PATH`
2. If set and file exists at that path:
   - Append line: `**SpecID:** {TASK_ID}` to the file
   - This enables callback.py to resolve real spec_id for QA dispatch

Example:
```bash
# The inbox done file at CLAUDE_CURRENT_SPEC_PATH gets:
**SpecID:** TECH-157
```

**Why:** Without this, QA dispatch after autopilot can't find the spec file
because the pueue task label contains the inbox filename, not the spec ID.

---

## Auto-Commit + Push (MANDATORY)

After the spec file is created — commit and push:

```bash
# 1. Stage the spec only. NOT ai/backlog.md (a render, rewritten by callback) and
#    NOT ai/lifecycle/*.yaml (create_initial already committed it via git plumbing;
#    staging it is blocked by the pre-commit guard, ADR-025).
git add "ai/features/${TASK_ID}"* 2>/dev/null

# 2. Commit
# Note: If ai/ is in .gitignore, git add is a no-op (expected)
git diff --cached --quiet || git commit -m "docs: create spec ${TASK_ID}"

# 3. Push to develop (orchestrator pulls from remote)
git push origin develop
```

**Why push:** Orchestrator runs on VPS — needs specs on remote to pull and process.

**Why `git add ai/` (not `-A`):**
- Only commits the spec — a controlled, explicitly named path
- Protects from accidental credential commits
- .gitignore is defense-in-depth, not primary protection

**Bug Hunt mode:** Uses its own commit pattern from `bug-mode.md` (explicit file list instead of `ai/`).

### CI Protection

Projects MUST have `ai/**` in `.github/workflows` `paths-ignore`.
Otherwise each spark push triggers CI on documentation-only changes.

```yaml
# .github/workflows/ci.yml
on:
  push:
    paths-ignore:
      - 'ai/**'
      - '*.md'
```

---

## Linter Failure → Do Not Commit (MANDATORY)

If Phase 5.5 (Allowlist Linter) still fails after the repairs described in
`feature-mode.md` ("On failure — fix the section, do not delete the spec"):

1. **Leave the spec file on disk.** The id was claimed through `create_initial`
   before the spec was written, so deleting the file leaves its lifecycle record
   behind as an orphan and burns the id — and a human needs to see what failed.
   This step used to read "delete now via `rm -f`", contradicting `feature-mode.md`
   in the same breath, and told you to hand-edit a backlog row out of a file that
   is rendered.
2. **DO NOT run `git add` / `git commit` / `git push`** for this task. An unpushed
   spec is invisible to the orchestrator, which is the outcome you want here.
3. Return final status:
   ```yaml
   status: blocked
   spec_path: null
   spec_status: not_created
   pushed: false
   error_code: ALLOWLIST_E00X
   error_message: "<human-readable description>"
   ```
5. The orchestrator/operator surfaces the error to the founder via Telegram —
   no auto-recovery.

⛔ Pushing a spec that fails the linter defeats the whole point of TECH-167.
The callback parser will reject it on the autopilot side, and the founder will
have to debug the same drift again.

## Completion — No Handoff

After spec is committed and pushed, Spark is DONE. No autopilot handoff.

**Flow:**
1. Spec saved to `ai/features/TYPE-XXX-YYYY-MM-DD-name.md` with status `queued`
2. Committed + pushed to develop
3. Orchestrator detects queued spec on next cycle
4. Autopilot picks it up

**Announcement format (interactive mode only):**
```
Spec ready: `ai/features/TYPE-XXX-YYYY-MM-DD-name.md`

**Summary:**
- [2-3 bullet points what will be done]

Spec is queued. Orchestrator will hand it to autopilot.
```

**DO NOT invoke `/autopilot`.** Orchestrator manages the lifecycle.

---

## Output

### If running as subagent (Task tool — no user interaction):
⛔ **MUST use Write tool to create spec file BEFORE returning!**
⛔ **MUST have claimed the ID via `create_initial` BEFORE returning** — that record, not a
backlog row, is what the orchestrator dispatches from.
<GATE>
After Write/Edit, MUST run `## Auto-Commit + Push (MANDATORY)` via Bash tool BEFORE returning.
Returning without push = spec invisible to orchestrator (reads from remote HEAD on next cycle).
</GATE>

Returning spec_path without creating file = DATA LOSS (subagent context dies).

### If running interactively (Skill tool):
<GATE>
After spec is created and backlog updated, ALWAYS commit and push unconditionally.
Do NOT ask the user about autopilot handoff — orchestrator manages lifecycle.
The auto-commit block above (`## Auto-Commit + Push (MANDATORY)`) is the only correct ending.
</GATE>
Write spec file when spec is complete, then run the auto-commit+push block above.

### Return format:
```yaml
status: complete | needs_discussion | blocked
spec_path: ai/features/TYPE-XXX-YYYY-MM-DD-name.md  # file MUST exist
spec_status: queued  # always queued — orchestrator picks up on next cycle
pushed: true | false
```
