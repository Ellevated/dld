# Idea: Hermes intake bridge + status gate before Spark
**Source:** telegram-founder
**Route:** spark
**Status:** processing
**Owner:** Hermes intake bridge
**Context:** DLD orchestrator currently dispatches raw inbox items directly to Spark; Hermes replaces the failed OpenClaw supervisory layer.
---

## Business intent

Hermes should act as Oleg's personal Telegram intake bridge before Spark. The bridge reviews raw thoughts from inbox and post-autopilot artifacts, clarifies business requirements with Oleg, closes stale/noisy items, and only then releases a fully business-described task to Spark.

Spark must not invent product/business requirements. Spark's role after intake is technical integration into the project: impact tree, architecture, allowed files, tests, and DLD spec formatting.

## Target flow

1. Raw idea/artifact appears in an intake source:
   - `ai/inbox/`
   - QA report
   - reflect findings
   - pending event from autopilot/QA/reflect
   - Telegram message from Oleg
2. Item starts as `draft` / not-ready-for-Spark.
3. Hermes reviews it and brings Oleg only proposals that may deserve a spec.
4. If the item is noisy, stale, or non-essential, Hermes says so and proposes cleanup/closure.
5. If business requirements are missing, Hermes asks Oleg. Rule: on business layer, ask rather than guess.
6. If the source already contains enough business context, Hermes reports: “вопрос понятен, отдал Spark”.
7. Hermes updates the item to `queued` only when intake is complete.
8. Orchestrator/Spark must only pick up `queued`, never raw `draft` items.

## Required status contract

Recommended statuses for intake files:

- `draft` — raw thought/artifact, not eligible for Spark.
- `clarifying` — Hermes has asked Oleg questions; waiting for answer.
- `stale` — no longer relevant, candidate for archive/delete.
- `rejected` — explicitly closed, do not process.
- `queued` — business intake complete; Spark may process.
- `processing` — Spark/orchestrator has picked it up.
- `done` — intake item converted into spec or closed successfully.

Hard requirement: orchestrator `scan_inbox()` should dispatch only `**Status:** processing` items. Existing raw `new` should no longer trigger Spark.

## Business acceptance criteria

- Raw Telegram/inbox thoughts never go directly to Spark.
- Hermes can summarize candidate items to Oleg in Telegram and ask concise business questions.
- Hermes can close/mark stale items with Oleg approval.
- Hermes can promote complete items to `queued`.
- Spark receives a business-complete brief: goal, user/customer, scenario, constraints, success criteria, out of scope.
- Post-autopilot QA/reflect outputs do not self-loop into Spark; Hermes reviews them and decides with Oleg whether a new intake item is warranted.

## Out of scope

- Reintroducing OpenClaw.
- Letting QA/reflect write directly into inbox as queued work.
- Letting Spark infer missing product strategy.

## Open technical questions for Spark

- Whether to rename legacy `new` to `draft` across docs/tests.
- Whether to support migration/backward compatibility for existing `new` files.
- Where to store Hermes intake decisions: inline status fields only, or `ai/intake/` ledger.
- Whether pending-events should be marked processed by Hermes after review.
