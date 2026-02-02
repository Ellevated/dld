# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 3.x.x   | :white_check_mark: |
| < 3.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability, please:

1. **Do NOT** open a public issue
2. Email security concerns to the maintainers via GitHub private vulnerability reporting
3. Include steps to reproduce the issue
4. Allow 48 hours for initial response

We take security seriously and will address valid reports promptly.

## Security Measures

- **Dependabot** enabled for automatic dependency updates
- **GitHub Actions** pinned to specific versions
- All PRs require review before merge
- No secrets in repository (use environment variables)
- Hooks validated with ruff linting and mypy type checking (CI checks `template/.claude/hooks/`, root `.claude/hooks/` syncs from template)

## Security Features in DLD

DLD includes built-in safety mechanisms:

- **Pre-Bash hooks** block dangerous commands (git push to main, force operations)
- **Pre-Edit hooks** protect test files and enforce file limits
- **Prompt guards** detect potentially risky prompts

See `template/.claude/hooks/` for implementation (source of truth).
