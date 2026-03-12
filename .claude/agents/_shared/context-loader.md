# Context Loading Protocol

## WHEN

Execute this protocol BEFORE starting ANY work.

---

## STEPS

### Step 1: Load Project Context (ALWAYS)

```bash
Read: .claude/rules/dependencies.md
Read: .claude/rules/architecture.md
```

**Use for:**
- Understanding what depends on what
- Following established patterns
- Avoiding anti-patterns

### Step 2: Identify Affected Domains

From task/spec files → extract domain names.

**Example:**
- File `src/domains/billing/services.py` → domain = `billing`
- File `src/infra/db/client.py` → domain = `infra`

### Step 3: Load Domain Contexts

For each affected domain:

```bash
Read: .claude/rules/domains/{domain}.md (if exists)
Read: ai/glossary/{domain}.md (if exists)
```

**Use for:**
- Domain-specific patterns
- Known entities and their locations
- Forbidden actions
- Domain terminology

### Step 4: Mental Summary

After loading, note:

```yaml
key_dependencies:
  - {domain} is used by {list of callers}

patterns_to_follow:
  - {pattern 1}
  - {pattern 2}

forbidden:
  - {forbidden 1}
```

---

## WARNING TRIGGERS

WARN user if during work you discover:

| Situation | Warning |
|-----------|---------|
| Changing public API but dependents NOT in scope | "API change affects {list}, add to Allowed Files?" |
| Adding cross-domain import | "Cross-domain import, check architecture.md" |
| Creating similar function to existing | "Similar to {existing}, consider reusing" |

---

## OUTPUT

None (internal preparation). Continue with your main task.
