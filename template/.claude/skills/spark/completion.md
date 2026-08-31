# Spark Completion Logic

**Read this AFTER creating spec — Shared completion logic for both Feature and Bug modes**

---

## ID Determination Protocol (MANDATORY — Spec-First CAS)

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
2. **Собрать зависимости из шапки спеки.** Каждый `**AFTER <ID>**` в заголовочном блоке —
   это ребро. Извлечь их и проверить, что запись существует, ПЕРЕД claim'ом (опечатка
   ловится здесь, демон её не увидит — он fail-open):
   ```bash
   DEPS=$(sed -n '1,15p' "$SPEC_HEADER" | grep -oE '\bAFTER +[A-Z]{2,5}-[0-9]+' \
            | awk '{print $2}' | sort -u)
   for D in $DEPS; do git cat-file -e "HEAD:ai/lifecycle/$D.yaml" 2>/dev/null \
     || echo "UNKNOWN DEPENDENCY: $D — исправить шапку спеки, не класть в depends_on"; done
   PY_DEPS=$(echo $DEPS | tr ' ' ',' | sed "s/\([A-Z0-9-]\+\)/'\1'/g")
   ```
3. **Claim the ID via CAS — where a lifecycle module is available:**
   ```bash
   python3 -c "
   import sys; sys.path.insert(0, 'scripts/vps')
   import lifecycle
   lifecycle.create_initial('$REPO_DIR', '$CANDIDATE',
                            priority='$PRIORITY', kind='$KIND',
                            status='queued', by='spark',
                            depends_on=[$PY_DEPS])   # пусто, если AFTER в шапке нет
   "
   ```

   **Most projects do not ship this module** — it belongs to the orchestrator, and an
   agent runs with `cwd` set to the project, so the import usually fails there. Usually,
   not always: a headless run can reach it by another path. So ask HEAD what happened
   rather than predicting it from the file list:

   ```bash
   git cat-file -e HEAD:ai/lifecycle/$CANDIDATE.yaml 2>/dev/null && echo claimed || echo unclaimed
   ```

   `claimed` → go to step 5. `unclaimed` → the id is not yours, and:

   - Do **not** hand-write the YAML. Lifecycle writes are CAS-guarded, and a pre-commit
     hook rejects any staged `ai/lifecycle/*.yaml`.
   - **Do add a row for the spec to `ai/backlog.md`.** This is the one case where the
     backlog is written by hand, and it is not optional. An orchestrator bootstraps the
     missing lifecycle record only for specs the backlog already names — a spec file it
     cannot find a row for is treated as a historical artifact and skipped. With no
     record and no row, the spec is never dispatched and nothing reports it: it sits in
     `ai/features/` forever.
   - After that first cycle the record exists, and the row belongs to the renderer again.

   Know what this costs: the spec-first CAS exists to stop two machines claiming the
   same ID. Without the module that protection is not in play — which is why interactive
   Spark runs from one machine at a time.
4. **Handle CAS collision** (concurrent spark on another machine claimed the
   same ID): if `LifecycleWriteRaceError` → re-read HEAD, recompute `NEXT = MAX + 1`,
   retry. Cap at **5 attempts**.
5. **On success** → lifecycle yaml is in HEAD with `by: spark`. Write
   `ai/features/{CANDIDATE}-YYYY-MM-DD-name.md`. **Do not touch `ai/backlog.md`** —
   see "The backlog is a render" below.
6. **On exhausted retries** → log WARNING `SPARK_ID_CAS_EXHAUSTED`, bump
   `ai/.spark-cas-exhausted-count`, fall back to `MAX + 5` with `cas-fallback`
   in transitions[0].reason.

**Numbering remains SEQUENTIAL ACROSS ALL TYPES** (see CLAUDE.md#Backlog-Rules).

---

## Pre-Completion Checklist (BLOCKING)

⛔ **DO NOT COMPLETE SPARK** without checking ALL items:

1. [ ] **ID determined by protocol** — not guessed!
2. [ ] **Uniqueness check** — `git ls-tree HEAD:ai/lifecycle/` did not already contain this ID
3. [ ] **Spec file created** — ai/features/TYPE-XXX-YYYY-MM-DD-name.md
4. [ ] **Lifecycle record accounted for** — `git cat-file -e HEAD:ai/lifecycle/{TASK_ID}.yaml`
   succeeds, or it does not and you wrote the backlog row that lets an orchestrator create it
5. [ ] **Status = queued** wherever that record ends up — never a second copy elsewhere
6. [ ] **Allowlist Linter passed** (Phase 5.5) — `grep '<!-- callback-allowlist v1' ai/features/{TASK_ID}*.md` returns ≥1 line and `## Allowed Files` heading exists exactly once
7. [ ] **Function overlap check** — grep other queued specs for same function names
   - If overlap found: merge into single spec OR mark dependency
8. [ ] **Auto-commit done** — `git add ai/ && git commit` (no push!)

If any item not done — **STOP and do it**.

---

## Post-Write Verification (MANDATORY)

After the spec file is written, verify the two things the pipeline actually reads:

```bash
# 1. The spec file exists
ls ai/features/{TASK_ID}-*.md

# 2. If the claim landed, the record is in HEAD and says queued
git show HEAD:ai/lifecycle/{TASK_ID}.yaml | grep -E '^status:'
# → status: queued
```

No record in HEAD is **not** a failure by itself — it means the claim did not land, which
is the common case, and the spec file plus the backlog row from step 2 is then the correct
end state. It *is* a failure if the record is there and says anything but `queued`. Never
write the YAML by hand in either case: it is the one file with a CAS protocol around it.

---

## The backlog is a render — with exactly one exception

Where an orchestrator dispatches specs, it reads the lifecycle records. `ai/backlog.md` is a
view over them: a status sync folds the new status into the same commit as the record, and it
rewrites **only the Status cell of rows that already exist** — it adds no rows and touches no
prose. A spec **that has a lifecycle record** and no backlog row is dispatched normally.

**The exception, stated once:** write a backlog row if and only if
`git cat-file -e HEAD:ai/lifecycle/{TASK_ID}.yaml` fails after your claim attempt. An
orchestrator bootstraps a missing record only for specs the backlog already names, so in
that case the row is not bookkeeping — it is the only thing that makes the spec visible.
If the record is there, leave the file alone.

**Test the outcome, not the repository.** Keying this on whether the module ships here
reads as equivalent and is not: a headless run can import it by a path the working tree
does not show, and then the hand-written row is racing the renderer for no reason. One
command against HEAD is right in both cases.

This section used to say *"Spark without backlog entry = DATA LOSS! Autopilot reads ONLY
backlog"*, which was true when the backlog was the source of truth and false once per-spec
lifecycle YAML replaced it. It then said never to touch the backlog at all, which is false
in the other direction for any project without the module. Both halves matter.

Under the exception there is no renderer race: the status sync rewrites existing rows and
adds none, so a hand-written row survives until the record exists.

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

Not your concern — the renderer owns the layout (sections by priority, sort order, spec
links) and rebuilds it from the lifecycle YAMLs. What determines how your spec appears is
what you passed to `create_initial`: `priority` and `kind`.

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

### Grouped Specs (IN Backlog)

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

## Auto-Commit + Push (MANDATORY)

After spec file is created and backlog updated — commit and push:

```bash
# 1. Stage spec-related changes only (explicit paths, not entire ai/ directory)
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

1. **Leave the spec file on disk.** The id was claimed before the spec was written,
   so deleting the file leaves its lifecycle record behind as an orphan and burns
   the id — and a human needs to see what failed. This step used to read "delete
   now via `rm -f`", contradicting `feature-mode.md` in the same breath, and told
   you to hand-edit a backlog row out of a file that is rendered.
2. **DO NOT run `git add` / `git commit` / `git push`** for this task. An unpushed
   spec is invisible to the orchestrator, which is the outcome you want here.
3. Return final status. `spec_path: null` reports what the pipeline received, not what is
   on disk — nothing was handed off. Name the file in `error_message` so the human can
   find it:
   ```yaml
   status: blocked
   spec_path: null
   spec_status: not_created
   pushed: false
   error_code: ALLOWLIST_E00X
   error_message: "<description> — unpushed spec left at ai/features/{TASK_ID}-*.md"
   ```
4. The orchestrator/operator surfaces the error to the founder via Telegram —
   no auto-recovery.

⛔ Pushing a spec that fails the linter defeats the point of the canonical format.
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
backlog row, is what an orchestrator dispatches from.
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
