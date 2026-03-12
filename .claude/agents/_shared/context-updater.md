# Context Update Protocol

## WHEN

Execute this protocol AFTER completing work that changes project knowledge.

---

## TRIGGERS

| What you did | What to update |
|--------------|----------------|
| Created new public function/class | Add to domain "Entities" |
| Created new cross-domain call | Add to dependencies.md |
| Established new pattern | Add to domain "Patterns" |
| Discovered forbidden action | Add to domain "Forbidden" |
| Changed existing API signature | Update dependents list |
| Added new term | Add to ai/glossary/{domain}.md |

---

## HOW TO UPDATE

### Adding new entity to domain context

In `.claude/rules/domains/{domain}.md`, section "Entities":

```markdown
| {Name} | {file}:{line} | {description} |
```

### Adding new dependency

In `.claude/rules/dependencies.md`, section "{domain}":

```markdown
### Used by (←)
| {caller_domain} | {file}:{line} | {function}() |
```

### Adding history entry

In `.claude/rules/domains/{domain}.md`, section "History":

```markdown
| {YYYY-MM-DD} | {what changed} | {TASK-ID} | coder |
```

### Adding glossary term

In `ai/glossary/{domain}.md`:

```markdown
## term_name
**What:** Definition
**Why:** Rationale
**Naming:** `code_convention`
```

---

## IMPORTANT

- Update IMMEDIATELY after code change
- Don't batch updates — update as you go
- If unsure whether to add — ADD (better too much than too little)
- Use exact file:line references

---

## VERIFICATION

Before finishing, verify:

```bash
# Check dependencies.md was updated if new cross-domain call
grep "{new_function}" .claude/rules/dependencies.md

# Check domain context was updated if new entity
grep "{new_entity}" .claude/rules/domains/{domain}.md
```

---

## OUTPUT

After updating, confirm:

```yaml
context_updates:
  - file: .claude/rules/domains/billing.md
    change: "Added Transaction.refund() to Entities"
  - file: .claude/rules/dependencies.md
    change: "Added: seller → billing.refund()"
```
