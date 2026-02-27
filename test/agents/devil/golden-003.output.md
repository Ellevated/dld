# Reference Output (Devil's Advocate)

## Why NOT

1. **Two heavy dependencies:** `boto3` (AWS SDK, 100+ MB) and `Pillow` (C extension, build issues on Alpine/ARM). Both add CI complexity, cold start time, and security surface area.
2. **S3 + CloudFront for 50 uploads/day is over-engineered:** At this volume, local filesystem + nginx serves the same purpose. S3 justified at 10K+ uploads/day or multi-region.
3. **Image processing is a security minefield:** Pillow has had CVEs (buffer overflows via crafted images). Accepting arbitrary file uploads opens path traversal, SSRF via SVG, and zip bomb risks.

## Simpler Alternatives

1. **Local filesystem + nginx:** Store files in `./uploads/`, serve via nginx. Zero AWS cost, zero SDK. Migrate to S3 when scale demands it.
2. **Gravatar integration:** Use email hash → Gravatar URL. Zero storage, zero upload, works immediately. Fallback to initials avatar.
3. **Pre-signed upload URL:** Instead of proxying through FastAPI, generate S3 pre-signed URL. Client uploads directly to S3. Saves server bandwidth and memory.

**Verdict:** Start with Gravatar for immediate value. If custom avatars are truly needed, use pre-signed URLs to avoid proxying files through the app server.

## What Breaks

### Side Effects

| Affected Component | File:line | Why It Breaks | Fix Required |
|--------------------|-----------|---------------|--------------|
| users API | src/api/users.py:* | New endpoint changes router, may affect existing routes | Verify no path conflicts |
| User model | src/domains/users/ | avatar_url field semantics change from null to S3 URL | Migration if URL format changes |
| CI/CD | Dockerfile | Pillow needs system deps (libjpeg, zlib) | Update Dockerfile |
| Tests | tests/ | Need S3 mock (moto) or localstack | Add test dependency |

### Dependencies at Risk

| Dependency | Type | Risk | Mitigation |
|------------|------|------|------------|
| boto3 | pip dependency | Med | Pin version, wrap in adapter |
| Pillow | pip dependency | High (CVEs) | Validate file type before processing, limit file size |
| AWS S3 | external service | Med | Retry logic, fallback to local |

## Eval Assertions

### Deterministic Assertions

| ID | Scenario | Input | Expected Behavior | Risk | Priority | Type |
|----|----------|-------|-------------------|------|----------|------|
| DA-1 | Non-image upload | .exe file | Rejected with 400, not processed | High | P0 | deterministic |
| DA-2 | Oversized file | 50MB image | Rejected before full upload (streaming check) | High | P0 | deterministic |
| DA-3 | S3 unavailable | Valid image | Graceful error, no partial state | Med | P1 | deterministic |
| DA-4 | Concurrent upload | Same user, two uploads | Last write wins, no orphan files in S3 | Med | P1 | deterministic |
| DA-5 | SVG with embedded script | Malicious SVG | Rejected or sanitized, never served raw | High | P0 | deterministic |

### Side-Effect Assertions

| ID | Affected Component | File:line | Regression Check | Priority |
|----|-------------------|-----------|------------------|----------|
| SA-1 | User GET endpoint | api/users.py | avatar_url field in response unchanged for users without avatar | P0 |
| SA-2 | User model | domains/users/ | No migration breaks existing data | P1 |

### Assertion Summary
- Deterministic: 5 | Side-effect: 2 | Total: 7
