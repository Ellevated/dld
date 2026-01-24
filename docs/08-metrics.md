# Quality Metrics

## Thresholds

| Metric | Bad | Good | Excellent |
|--------|-----|------|-----------|
| Domain context | >300 lines | 150-300 | <150 lines |
| Files in domain | >15 | 8-15 | <8 |
| LOC per file | >500 | 200-300 | <200 |
| Exports in __init__.py | >10 | 5-10 | ≤5 |
| Nesting depth | >4 | 3-4 | ≤3 |
| Time to understand structure | >5 min | 2-5 min | <1 min |
| Import violations | >0 | 0 | 0 |

---

## CI Gates

```yaml
# Mandatory checks
- python scripts/check_domain_imports.py --strict  # 0 violations
- python scripts/check_file_sizes.py --max-lines 400 # no files >400 LOC (600 for tests)
```

---

## How to Measure

```bash
# LOC per file
wc -l src/domains/**/*.py | sort -n

# Exports in __init__.py
grep -c "^from\|^import" src/domains/*/__init__.py

# Import violations
python scripts/check_domain_imports.py
```
