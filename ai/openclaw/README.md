# OpenClaw Artifact Wake Flow

North-star hybrid model:

- callback writes durable event files to `ai/openclaw/pending-events/`
- OpenClaw wakes on cron as fallback / polling safety net
- OpenClaw reads repo artifacts (`ai/qa/`, `ai/reflect/`, backlog/status) and decides next action
- after review, processed event files move to `ai/openclaw/processed-events/`

Scanner:

```bash
python3 scripts/vps/openclaw-artifact-scan.py --project-dir .
python3 scripts/vps/openclaw-artifact-scan.py --project-dir . --mark-processed
```

Important invariant:
- wake events do **not** enqueue work
- only OpenClaw may create new inbox items after reviewing artifacts
