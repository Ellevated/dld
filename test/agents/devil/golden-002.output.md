# Reference Output (Devil's Advocate)

## Why NOT

1. **WebSocket state management complexity:** Each connection is a long-lived stateful resource. Server restarts, deploys, and load balancer reconfigurations all break active connections. Reconnection logic must be bulletproof.
2. **Scaling pain:** WebSocket connections are pinned to specific server instances. Redis Pub/Sub helps but adds failure mode — if Redis drops, all cross-instance notifications silently die.
3. **Premature optimization:** With 200 concurrent users, simple polling every 5-10 seconds generates ~20-40 requests/second. This is trivial for FastAPI. WebSocket justified at 5000+ concurrent users.

## Simpler Alternatives

1. **Server-Sent Events (SSE):** One-directional push, works over HTTP/2, no special infrastructure. FastAPI supports via `StreamingResponse`. No connection manager needed.
2. **Short polling:** `GET /notifications?since={timestamp}` every 10 seconds. Zero new infrastructure, works with existing auth, trivial to implement.
3. **Long polling:** Client holds connection open until event arrives. Simpler than WebSocket, no special protocol.

**Verdict:** SSE covers 95% of the use case with 20% of the complexity. WebSocket only justified if bidirectional communication is needed (e.g., chat).

## What Breaks

### Side Effects

| Affected Component | File:line | Why It Breaks | Fix Required |
|--------------------|-----------|---------------|--------------|
| main.py | src/api/main.py:15 | WebSocket mount changes app startup | Test app lifecycle |
| auth middleware | src/api/middleware.py | WebSocket auth is different from HTTP auth | Separate WS auth handler |
| deployment | docker-compose.yml | Need sticky sessions or Redis for WS routing | Update load balancer config |

### Dependencies at Risk

| Dependency | Type | Risk | Mitigation |
|------------|------|------|------------|
| Redis Pub/Sub | infra | High | Fallback to local-only notifications |
| FastAPI WebSocket | framework | Low | Well-supported, stable API |

## Eval Assertions

### Deterministic Assertions

| ID | Scenario | Input | Expected Behavior | Risk | Priority | Type |
|----|----------|-------|-------------------|------|----------|------|
| DA-1 | Client disconnect | WebSocket close event | Connection cleaned up, no memory leak | High | P0 | deterministic |
| DA-2 | Server restart | Active WS connections | Clients reconnect automatically | High | P0 | deterministic |
| DA-3 | Redis Pub/Sub down | Notification event | Local instance still receives, cross-instance fails gracefully | Med | P1 | deterministic |
| DA-4 | Auth token expired | WS connection active | Connection closed with 4001, not silent drop | Med | P1 | deterministic |

### Side-Effect Assertions

| ID | Affected Component | File:line | Regression Check | Priority |
|----|-------------------|-----------|------------------|----------|
| SA-1 | HTTP endpoints | main.py:* | All existing REST endpoints still work | P0 |
| SA-2 | Auth middleware | middleware.py:* | HTTP auth unchanged | P0 |
| SA-3 | Redis caching | redis_client.py:* | Existing cache not affected by Pub/Sub | P1 |

### Assertion Summary
- Deterministic: 4 | Side-effect: 3 | Total: 7
