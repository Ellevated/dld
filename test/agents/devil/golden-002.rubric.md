# Scoring Rubric: Devil's Advocate — WebSocket Proposal

## Completeness (weight: high)
- Must include "Why NOT" with at least 2 arguments against WebSocket specifically
- Must include alternatives — SSE and/or polling must be mentioned as simpler options
- Must include "What Breaks" identifying deployment and auth impacts
- Must include structured assertions (DA-IDs) covering connection lifecycle

## Accuracy (weight: high)
- WebSocket scaling concerns (stateful connections, sticky sessions) must be technically correct
- SSE as alternative must be correctly described (one-directional, HTTP/2 compatible)
- Polling math should be reasonable (200 users × interval = requests/sec)
- Auth differences between HTTP and WebSocket must be acknowledged

## Format (weight: medium)
- Uses markdown headers and structured sections
- Eval Assertions use table format with DA-N and SA-N IDs
- Assertion Summary present with counts
- Alternatives have clear structure (name + description)

## Relevance (weight: high)
- Arguments specific to THIS proposal (WebSocket + Redis Pub/Sub), not generic
- Alternatives address the actual problem (real-time updates)
- Side effects reference components from the scope (main.py, auth, Redis)
- Connection lifecycle edge cases covered (disconnect, restart, auth expiry)

## Safety (weight: low)
- Constructive tone — questions complexity, doesn't dismiss the need
- Acknowledges valid use cases for WebSocket (bidirectional)
- No recommendation to ignore user requirements entirely
