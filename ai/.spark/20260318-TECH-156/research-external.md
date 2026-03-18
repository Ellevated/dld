# External Research: Notification Suppression Patterns

## CI/CD Notification Patterns

- GitHub Actions: job-level conditions, only final job notifies
- GitLab CI: pipeline-level notifications, not per-job
- Jenkins: quietPeriod + build result aggregation

## Notification Fatigue Research

- Developers ignore >70% of CI notifications when every step notifies
- Best practice: notify on final result only OR notify on failure only
- Aggregator pattern (OpenClaw reading events) is modern best practice

## Recommended: Skill Allowlist (Hardcoded)

- Simple, follows existing code patterns (reflect already uses this)
- No external config dependency
- Bash-native, no new dependencies
- Easy to audit and rollback

## Environment Variable Alternative (Not Recommended)

- SILENT_SKILLS env var adds string parsing complexity
- Not worth it for a fixed set of 4 skills
