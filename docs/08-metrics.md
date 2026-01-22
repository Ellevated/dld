# Метрики качества

## Thresholds

| Метрика | Плохо | Хорошо | Отлично |
|---------|-------|--------|---------|
| Контекст домена | >300 строк | 150-300 | <150 строк |
| Файлы в домене | >15 | 8-15 | <8 |
| LOC в файле | >500 | 200-300 | <200 |
| Exports в __init__.py | >10 | 5-10 | ≤5 |
| Глубина вложенности | >4 | 3-4 | ≤3 |
| Время понимания структуры | >5 мин | 2-5 мин | <1 мин |
| Import violations | >0 | 0 | 0 |

---

## CI Gates

```yaml
# Обязательные проверки
- python scripts/check_domain_imports.py --strict  # 0 violations
- python scripts/check_file_sizes.py --max-lines 400 # нет файлов >400 LOC (600 для тестов)
```

---

## Как измерить

```bash
# LOC в файле
wc -l src/domains/**/*.py | sort -n

# Exports в __init__.py
grep -c "^from\|^import" src/domains/*/__init__.py

# Import violations
python scripts/check_domain_imports.py
```
