# Bug Hunt Completion

Read after pipeline Steps 0-5 complete. Creates inbox files and pushes.

---

## Step 6: Create Inbox Files

For each finding group from validator-output.yaml, create an inbox file.

**Limit:** Max 10 inbox files. If more groups exist, include only top 10 by severity.
Remaining findings stay in the report for manual review.

### Inbox File Format

For each group (index i):

```markdown
# Idea: {timestamp}-bughunt-{i}
**Source:** bughunt
**Route:** spark_bug
**Status:** new
**Context:** ai/.bughunt/{session}/report.md
---
{finding group description: what's broken, where, severity, evidence from validator}
```

### Write to disk

```python
inbox_dir = Path(project_dir) / "ai" / "inbox"
inbox_dir.mkdir(parents=True, exist_ok=True)

for i, group in enumerate(groups[:10]):
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    filepath = inbox_dir / f"{ts}-bughunt-{i+1}.md"
    filepath.write_text(content)
```

---

## Report Location

Save the full report (NOT in `ai/features/`, NOT in backlog):

```
ai/bughunt/{YYYY-MM-DD}-report.md
```

The report is a READ-ONLY reference document. Spark will read it via the `Context:` field
in inbox files when creating specs.

---

## Auto-Commit + Push

```bash
# Stage report + inbox files
git add ai/bughunt/ ai/inbox/ 2>/dev/null

# Commit
git diff --cached --quiet || git commit -m "docs: bughunt report + ${N} inbox findings"

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
Findings: {N} groups → {M} inbox files created.
Spark will process findings on next orchestrator cycle.
```

**Headless mode:** Same info in return format.

---

## Return Format

```yaml
status: completed | degraded
mode: bughunt
findings_count: N
groups_count: M
inbox_files_created: M  # max 10
report_path: ai/bughunt/{date}-report.md
pushed: true | false
```

---

## What Bughunt Does NOT Do

- Does NOT create specs (Spark does that from inbox)
- Does NOT add backlog entries (Spark does that)
- Does NOT invoke autopilot
- Does NOT modify source code
