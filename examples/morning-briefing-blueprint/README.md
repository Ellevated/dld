# Example: a full `/board` + `/architect` output

This is a complete Business Blueprint and System Blueprint for a product called
**Morning Briefing Agent** — a hypothetical SaaS (Clerk auth, Fly.io, Turso, $99/month)
designed as a dogfooding exercise on 2026-05-23. It was never built.

It is kept because it is the most complete worked example of what the two skills produce:
six directors' research and cross-critique, seven architect personas, a domain map, data
architecture, API contracts and cross-cutting rules. Read it to see the shape of the output
before running the skills on your own product.

## Why it moved here

It used to live in `ai/blueprint/`, which is not an archive — it is an **input**.
`skills/spark/feature-mode.md` reads it:

```
If `ai/blueprint/system-blueprint/` exists, ALL scouts receive it as CONSTRAINT.
```

Plus "all approaches must respect blueprint" in Phase 4, and a Phase 8 gate asking
"No contradictions with system blueprint?". So every `/spark` run in DLD was handing three
scouts the architecture of a different product as a binding constraint, and then checking
its own output for agreement with it.

That is not theoretical. It was found on 2026-08-02 by a `/spark` eval run, which refused
its task and reported the blueprint as the reason. A second run in the same batch was less
suspicious: it produced `FTR-221 — Identity store: expand-only clerk_user_id binding`, an
R0 spec built on this file's Clerk identity model, and wrote it to the queue. The "100
requests per minute" figure in that run traces directly to
`system-blueprint/api-contracts.md`.

The failure mode is expensive and quiet: a well-formed spec that passes every gate,
against files that do not exist, handed to an autopilot session that merges nothing.

## What did not move

`system-blueprint/callback-lifecycle-contour.md` was the one file here genuinely about DLD
— a TO-BE design for the `scripts/vps/` orchestrator contour. It is now
`docs/orchestrator/callback-lifecycle-contour-to-be.md`, with the rest of the orchestrator
documentation.

## Using this as a starting point

Do not copy it into `ai/blueprint/` unless you are building this product. Run `/board` and
`/architect` on your own idea instead — the value here is the format, not the content.
