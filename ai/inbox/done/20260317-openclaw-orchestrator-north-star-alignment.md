# Idea: 20260317-134800
**Source:** openclaw
**Route:** spark
**Status:** processing
**Context:** ai/architect/orchestrator-final-state.md
---
Intake complete. Do not ask new questions.

Bring the orchestrator in line with the north-star flow from ai/architect/orchestrator-final-state.md.

Required direction:
- only OpenClaw writes to ai/inbox/
- Spark creates queued specs directly when intake is complete
- remove draft approval dependency from orchestrator loop
- QA writes durable report files to ai/qa/ instead of creating inbox items
- Reflect writes only to its diary / reflect artifacts, not inbox
- callback/orchestrator must not auto-enqueue follow-up work from QA/Reflect/Council/Architect outputs
- after Autopilot -> QA -> Reflect the cycle stops
- OpenClaw reviews artifacts and decides whether to write a new inbox item

Target: make tool behavior and docs consistent with this model.
