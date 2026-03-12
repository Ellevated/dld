# Tech: [TECH-061] Fix Discord Placeholder Links

**Status:** done | **Priority:** P0 | **Date:** 2026-02-01

## Why

README.md and CONTRIBUTING.md contain fake Discord links (`XXXXXXXXX`, `INVITE_CODE`). Clicking leads nowhere. Looks unprofessional and breaks trust.

## Context

Current broken links:

**README.md:246:**
```markdown
[![Discord](https://img.shields.io/discord/XXXXXXXXX?...)](https://discord.gg/INVITE_CODE)
```

**CONTRIBUTING.md:48:**
```markdown
- Join our [Discord](https://discord.gg/INVITE_CODE)
```

---

## Scope

**In scope:**
- Either: Set up real Discord server and add real links
- Or: Remove Discord references entirely until ready

**Out of scope:**
- Discord bot development
- Community management setup

---

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `README.md` | modify | Fix or remove Discord |
| 2 | `CONTRIBUTING.md` | modify | Fix or remove Discord |
| 3 | `FAQ.md` | modify | Check for Discord refs |

---

## Approaches

### Approach 1: Create Real Discord Server

**Summary:** Set up Discord, get real invite link, update files

**Pros:**
- Community building starts now
- Professional appearance
- Direct support channel

**Cons:**
- Requires moderation commitment
- May be premature before traction

### Approach 2: Remove Discord References

**Summary:** Remove all Discord mentions until community forms organically

**Pros:**
- No broken links
- No maintenance burden
- Can add later when needed

**Cons:**
- Loses community touchpoint
- May seem less established

### Approach 3: Replace with GitHub Discussions

**Summary:** Remove Discord, point to GitHub Discussions instead

**Pros:**
- Built into GitHub
- No separate platform
- Searchable, public

**Cons:**
- Less real-time than Discord
- Different UX

### Selected: Approach 3

**Rationale:** GitHub Discussions provides community without extra platform overhead. Can add Discord later if demand exists.

---

## Design

### Changes

**README.md — Replace:**
```markdown
## Community

Join discussions and get help:

[![Discussions](https://img.shields.io/github/discussions/Ellevated/dld)](https://github.com/Ellevated/dld/discussions)
```

**CONTRIBUTING.md — Replace:**
```markdown
## Questions?

- Open a [Discussion](https://github.com/Ellevated/dld/discussions)
- Use the [question template](../../issues/new?template=question.md)
```

**FAQ.md — Add:**
```markdown
### Where can I get help?

- [GitHub Discussions](https://github.com/Ellevated/dld/discussions) — ask questions, share ideas
- [GitHub Issues](https://github.com/Ellevated/dld/issues) — bug reports
```

---

## Implementation Plan

### Task 1: Enable GitHub Discussions

**Steps:**
1. Go to repo Settings → Features
2. Enable Discussions
3. Create categories: Q&A, Ideas, Show & Tell

**Acceptance:**
- [ ] Discussions tab visible on repo

### Task 2: Update README.md

**Files:**
- Modify: `README.md`

**Steps:**
1. Remove Discord badge and link
2. Add GitHub Discussions badge
3. Update Community section

**Acceptance:**
- [ ] No Discord references
- [ ] Discussions link works

### Task 3: Update CONTRIBUTING.md

**Files:**
- Modify: `CONTRIBUTING.md`

**Steps:**
1. Replace Discord link with Discussions
2. Keep issue template reference

**Acceptance:**
- [ ] No Discord references

### Task 4: Update FAQ.md

**Files:**
- Modify: `FAQ.md`

**Steps:**
1. Add Discussions to "Where can I get help"
2. Remove any Discord mentions

**Acceptance:**
- [ ] FAQ updated

### Execution Order

Task 1 → Task 2 → Task 3 → Task 4

---

## Definition of Done

### Functional
- [ ] No placeholder links in any file
- [ ] All community links work
- [ ] GitHub Discussions enabled

### Technical
- [ ] Badge displays correctly
- [ ] Links resolve

### Documentation
- [ ] Community options clearly listed

---

## Autopilot Log

*(Filled by Autopilot during execution)*
