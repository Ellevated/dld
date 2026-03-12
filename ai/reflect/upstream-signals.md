# Upstream Signals from Architect

**Date:** 2026-02-28
**Source:** Architect Board (8 personas + synthesis)
**Architecture:** Alternative B — Domain-Pure

---

## Signals for Board (target=board)

### SIGNAL-001: Google OAuth Verification is Critical Path
**Severity:** Critical
**Detail:** Google OAuth App Verification takes 4-6 weeks external review. Must submit day 31 of Phase 2. Blocks public launch (>100 users). Requires privacy policy, homepage, demo video, security questionnaire.
**Recommendation:** Board should add this to Phase 2 timeline. Privacy policy must be ready by day 30. Testing mode (100 user cap) available before verification.

### SIGNAL-002: Pricing Tier Task Definition Needed
**Severity:** High
**Detail:** Board says "500 tasks/workspace/month for Solo." Architect needs precise definition: is 1 briefing = 1 task? Or does each source fetch count? Usage cap enforcement depends on this.
**Recommendation:** Board should define: 1 briefing compilation = 1 task (recommended by Data Architect).

### SIGNAL-003: Multi-Workspace Priority Scope
**Severity:** Medium
**Detail:** Pro tier has 3 workspaces. Are priorities per-workspace or per-user? If per-workspace, different workspaces can have different priorities (personal vs work). If per-user, priorities are shared.
**Recommendation:** Board should decide. Architect recommends per-workspace (different contexts of use).

### SIGNAL-004: Degraded Briefing Policy
**Severity:** Medium
**Detail:** When a source is unhealthy (e.g., Gmail OAuth expired), should briefing compile without that source (degraded) or block until all sources healthy?
**Recommendation:** Architect implements degraded delivery (partial briefing > no briefing). Board should confirm this is the right UX.

---

## Signals for Spark (target=spark)

### SIGNAL-005: Onboarding Flow is Critical for Conversion
**Detail:** Sub-10-minute time-to-first-value requires: (1) Clerk signup (2 min), (2) Add 1 source — RSS or HN, no OAuth (1 min), (3) Set priorities (2 min), (4) Trigger first briefing (instant). Gmail/Calendar as day-2 upgrades (OAuth friction).
**Priority:** First feature spec should be onboarding flow.

### SIGNAL-006: Telegram Bot Commands
**Detail:** Bot needs: /start (connect channel), /stop (disconnect), /briefing (manual trigger), /settings (show prefs). Each command maps to an API endpoint.

### SIGNAL-007: Feedback Capture UI
**Detail:** For behavioral memory to work, briefings must capture engagement: opened, item_clicked, item_dismissed, full_read, skipped. Telegram inline keyboards recommended. This is the compound loop that creates switching cost.

---

## Process Signals (target=architect-next)

### SIGNAL-008: Cross-Critique Confirmed Data Architect Dominance
**Detail:** Data Architect (Martin) ranked best by 5 of 7 personas. The data model decisions (append-only ledger, two-table memory, structured JSON) were the most impactful.
**Lesson:** In future Architect sessions, give Data persona more explicit agenda weight.

### SIGNAL-009: Devil Found 5 Contradictions, All Resolved
**Detail:** Evaporating Cloud technique resolved all 5 contradictions (domain count, scheduler, storage, OAuth ownership, tool calls). No unresolved tensions in final architecture.
**Lesson:** Devil is most valuable when contradictions are NAMED and given formal resolution structure.

### SIGNAL-010: "Agent-runtime" as Context was Unanimously Rejected
**Detail:** Domain persona identified "agent-runtime" as a technical term masquerading as domain concept. All other personas agreed. LLM execution is infrastructure inside Briefing context.
**Lesson:** Always check Business Blueprint domain names against DDD linguistic test.
