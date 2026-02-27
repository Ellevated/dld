# Feature Proposal: Real-time notifications via WebSocket

## Problem
Users don't see updates (new orders, messages) until they refresh the page. This causes missed opportunities and poor UX.

## Proposed Solution
Add WebSocket server alongside existing FastAPI. Push real-time events to connected clients. Use Redis Pub/Sub for cross-instance message broadcasting.

## Scope
- New `src/infra/ws/manager.py` — WebSocket connection manager
- New `src/infra/ws/events.py` — event types and serialization
- New `src/domains/notifications/service.py` — notification dispatch logic
- Modify `src/api/main.py` — mount WebSocket endpoint
- Add `ws://` endpoint at `/ws/notifications`

## Context
- Current stack: Python 3.12 + FastAPI + PostgreSQL
- No WebSocket infrastructure exists
- ~200 concurrent users at peak
- Redis already used for caching (from previous feature)
