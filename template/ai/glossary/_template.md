# {Domain} Glossary

Domain-specific terms, rules, and conventions.

**Path:** `src/domains/{domain}/`

---

## Money Rules (CRITICAL)

> **Include this section in EVERY domain glossary that touches money.**

All amounts in kopecks. 1 ruble = 100 kopecks.

**Naming:** `amount_kopecks`, `price_kopecks`, never bare `amount` or `price`.

**Why:** Integer arithmetic prevents floating-point precision errors.

**History:** Ambiguous naming (`_rub` vs bare amounts) caused 23-task refactoring (Jan 2026).

**Examples:**
```python
# Correct
transaction_amount_kopecks: int = 15000  # 150 rubles

# Wrong
transaction_amount: float = 150.00  # Precision loss!
amount_rub: int = 150  # Ambiguous — rubles or kopecks?
```

---

## {term_name}

**What:** Brief definition (1-2 sentences)

**Why:** Rationale — why it exists, historical context

**Convention:** How to use in business logic

**Naming:** Code naming convention
```python
# Example
variable_name: Type
```

**Related:** Link to related terms or domains

---

## {another_term}

**What:** ...

**Why:** ...

**Convention:** ...

**Naming:** ...

**Related:** ...

---

## Domain-Specific Rules

| Rule | Description | Enforcement |
|------|-------------|-------------|
| {rule_name} | {description} | {how enforced} |

---

## Anti-Patterns (FORBIDDEN)

| Pattern | Why Forbidden | Instead |
|---------|---------------|---------|
| {anti_pattern} | {reason} | {correct_approach} |

---

## Change History

| Date | Term | Change | Task |
|------|------|--------|------|
| YYYY-MM-DD | {term} | {what changed} | {TASK-ID} |

---

## Self-Contained Principle

**This file must be self-contained.**

LLM reads ONE glossary file and has ALL context needed for the domain:
- Money rules (if applicable)
- All domain terms
- Naming conventions
- Anti-patterns

**Duplication is OK.** If Money Rules apply to this domain — include them here.
Don't rely on links to other files for critical rules.
