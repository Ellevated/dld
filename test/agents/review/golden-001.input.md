# Code Review Request

Review the changes below for the DLD orchestrator (`scripts/vps/`). Report every
issue you find with a severity and a one-line justification.

Project rules that apply (from `.claude/rules/architecture.md`):
- Money is `int` cents. Never float, never Decimal.
- Max 400 LOC per file (600 for tests).
- Bare `except Exception:` is FORBIDDEN in general, but explicitly ALLOWED in
  `.claude/hooks/` — hooks are fail-safe infrastructure and must never crash (ADR-004).
- Imports flow `shared → infra → domains → api`, never the reverse.

---

## File 1: `scripts/vps/lifecycle.py` (excerpt, 210 LOC total)

```python
def _run(cmd: list, *, cwd: str, env=None, input_text=None, timeout: int = 30):
    """Run a git plumbing command."""
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def write_lifecycle(repo: str, spec_id: str, status: str, *, by: str, reason: str = ""):
    """Write the lifecycle yaml through git plumbing (never touches the working tree)."""
    blob = yaml.safe_dump(
        {"spec_id": spec_id, "status": status, "blocked_reason": reason, "updated_by": by},
        allow_unicode=True,
        sort_keys=False,
    )
    r = _run(["git", "hash-object", "-w", "--stdin"], cwd=repo, input_text=blob)
    sha = r.stdout.strip()
    _run(["git", "update-index", "--add", "--cacheinfo", f"100644,{sha},ai/lifecycle/{spec_id}.yaml"], cwd=repo)
    return sha
```

Note: the repo ships `.gitattributes` containing `*.yaml eol=lf`, and spec
`blocked_reason` values are frequently written in Russian.

---

## File 2: `scripts/vps/claude-runner.py` (excerpt, 340 LOC total)

```python
def _resolve_cli_path() -> str | None:
    """Prefer the system Claude Code CLI over the SDK's bundled copy."""
    candidates = [
        os.environ.get("CLAUDE_CLI_PATH"),
        shutil.which("claude"),
        str(Path.home() / ".local" / "bin" / "claude"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


MODEL = os.environ.get("AUTOPILOT_MODEL", "claude-opus-5")
```

Note: this process is launched by the pueue daemon, which inherits systemd's
`PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`.
`~/.local/bin/claude` is a symlink the installer repoints on every update.

---

## File 3: `scripts/vps/orchestrator.py` (excerpt, 390 LOC total)

```python
    state = db.get_project_state(project_id)
    provider = (state["provider"] if state else None) or "claude"

    m = re.search(r"^provider:\s+(\w+)", spec_files[0].read_text(), re.MULTILINE)
    if m and db.get_available_slots(m.group(1)) >= 0:
        provider = m.group(1)

    if db.get_available_slots(provider) < 1:
        log.info("no slots for %s provider=%s", project_id, provider)
        return False
```

`db.get_available_slots(provider)` runs `SELECT COUNT(*) ... WHERE provider = ? AND project_id IS NULL`.

---

## File 4: `scripts/vps/render_backlog.py` (excerpt, 150 LOC total)

```python
def render(repo: str) -> None:
    rows = [read_lifecycle(repo, p.stem) for p in lifecycle_dir(repo).glob("*.yaml")]
    try:
        Path(repo, "ai", "backlog.md").write_text(_to_markdown(rows), encoding="utf-8")
    except Exception:
        pass
```

---

## File 5: `scripts/vps/deploy.sh` (excerpt)

```bash
#!/usr/bin/env bash
set -euo pipefail

cd "$REPO_DIR"
git add -A
git commit -m "chore: sync generated backlog view"
git push origin develop
```

---

## File 6: `.claude/hooks/pre-edit-guard.mjs` (excerpt, 90 LOC total)

```javascript
try {
  const spec = inferSpecFromBranch();
  if (spec && !isAllowed(filePath, spec)) {
    process.exit(2);
  }
} catch (e) {
  // Hook must never break the session
  process.exit(0);
}
```

---

## File 7: `src/domains/billing/pricing.py` (excerpt, 380 LOC total)

```python
def apply_discount(amount_cents: int, percent: int) -> int:
    """Discount an amount. Both input and output are integer cents."""
    if not 0 <= percent <= 100:
        raise ValueError(f"percent out of range: {percent}")
    return amount_cents - (amount_cents * percent) // 100
```
