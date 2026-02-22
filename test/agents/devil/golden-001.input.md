# Feature Proposal: Add caching layer for API responses

## Problem
API calls to external LLM provider are slow (2-5 seconds). Users see delays on repeated queries.

## Proposed Solution
Add Redis caching layer between our API and the LLM provider. Cache responses for identical prompts with 1-hour TTL.

## Scope
- New `src/infra/cache/redis_client.py` module
- Modify `src/domains/seller/agent.py` to check cache before LLM call
- Add `REDIS_URL` to `.env`

## Context
- Current stack: Python 3.12 + FastAPI + PostgreSQL
- No caching exists in the project
- ~500 unique prompts/day, ~30% repeat rate
