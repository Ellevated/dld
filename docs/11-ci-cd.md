# CI/CD Configuration

## GitHub Actions (.github/workflows/ci.yml)

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Lint
        run: |
          cd backend
          ruff check src/ tests/
          ruff format --check src/ tests/

      - name: Check imports
        run: |
          cd backend
          python scripts/check_domain_imports.py --strict

      - name: Check file sizes
        run: |
          cd backend
          python scripts/check_file_sizes.py --max-lines 400

      - name: Test
        run: |
          cd backend
          pytest tests/ -v --cov=src --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install & Lint & Test
        run: |
          cd frontend
          npm ci
          npm run lint
          npm run type-check
          npm test
```

---

## Import Linter (scripts/check_domain_imports.py)

```python
#!/usr/bin/env python3
"""Domain import linter.

Rules:
- shared/ → nothing
- infra/ → shared/
- domains/ → shared/, infra/
- api/ → everything
- Cross-domain: only via allowed dependencies
"""

import ast
import sys
from pathlib import Path

LAYER_RULES = {
    "src.shared": set(),
    "src.infra": {"src.shared"},
    "src.domains": {"src.shared", "src.infra"},
    "src.api": {"src.shared", "src.infra", "src.domains"},
}

# Domain dependency rules (DAG)
DOMAIN_DEPS = {
    "auth": [],
    "workflows": ["auth"],
    "tasks": ["workflows"],
    "notifications": ["workflows", "tasks"],
    "bot": ["auth", "workflows", "tasks", "notifications"],
}


def check_file(path: Path) -> list[str]:
    """Check imports in a single file."""
    violations = []
    content = path.read_text()
    tree = ast.parse(content)

    parts = path.parts
    if "src" not in parts:
        return []

    src_idx = parts.index("src")
    source = f"src.{parts[src_idx + 1]}"

    source_domain = None
    if "domains" in parts:
        domain_idx = parts.index("domains")
        if domain_idx + 1 < len(parts):
            source_domain = parts[domain_idx + 1]

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = node.module if isinstance(node, ast.ImportFrom) else None
            if module and module.startswith("src."):
                target = f"src.{module.split('.')[1]}"

                # Layer check
                allowed = LAYER_RULES.get(source, set())
                if target not in allowed and target != source:
                    violations.append(f"{path}: {source} → {target}")

                # Cross-domain check
                if source_domain and "domains" in module:
                    target_parts = module.split(".")
                    if len(target_parts) >= 3:
                        target_domain = target_parts[2]
                        if target_domain != source_domain:
                            allowed_domains = DOMAIN_DEPS.get(source_domain, [])
                            if target_domain not in allowed_domains:
                                violations.append(
                                    f"{path}: domain {source_domain} → {target_domain}"
                                )

    return violations


def main() -> int:
    src_dir = Path("src")
    violations = []

    for py_file in src_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        violations.extend(check_file(py_file))

    if violations:
        print(f"Found {len(violations)} import violations:")
        for v in violations:
            print(f"  {v}")
        return 1

    print("No import violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```
