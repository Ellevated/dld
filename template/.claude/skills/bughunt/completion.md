# Bug Hunt Completion

Read after pipeline Steps 0-5 complete. Saves durable bughunt artifacts and pushes.

---

## Step 6: Save Durable Report Only

Bughunt does **not** create inbox items directly.
It saves durable findings to its own report artifact. OpenClaw reviews that report and decides whether to create inbox items.

---

## Report Location

Save the full report (NOT in `ai/features/`, NOT in backlog):

```
ai/bughunt/{YYYY-MM-DD}-report.md
```

The report is a READ-ONLY reference document. OpenClaw may later use it as context when creating inbox items.

---

## Auto-Commit + Push

```bash
# Stage report artifacts
git add ai/bughunt/ 2>/dev/null

# Commit
git diff --cached --quiet || git commit -m "docs: bughunt report"

# Push to develop (orchestrator pulls from remote)
git push origin develop
```

---

## Cleanup

Remove intermediate pipeline data:

```bash
rm -rf {SESSION_DIR}
```

Keep the report file (`ai/bughunt/`) — it serves as Context for Spark.

---

## Report to User

**Interactive mode:**
```
Bug Hunt complete.
Report: ai/bughunt/{date}-report.md
Findings: {N} groups saved to report.
OpenClaw will review and decide next action.
```

**Headless mode:** Same info in return format.

---

## Return Format

```yaml
status: completed | degraded
mode: bughunt
findings_count: N
groups_count: M
report_path: ai/bughunt/{date}-report.md
openclaw_review_needed: true
pushed: true | false
```

---

## What Bughunt Does NOT Do

- Does NOT create inbox items directly
- Does NOT create specs directly
- Does NOT add backlog entries (Spark does that)
- Does NOT invoke autopilot
- Does NOT modify source code
