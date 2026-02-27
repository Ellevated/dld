# Feature Proposal: User avatar upload with S3 storage

## Problem
Users cannot set profile avatars. This reduces engagement and makes the platform feel impersonal.

## Proposed Solution
Add file upload endpoint. Store images in AWS S3. Generate thumbnails on upload. Serve via CloudFront CDN.

## Scope
- New `src/infra/storage/s3_client.py` — S3 upload/download wrapper
- New `src/domains/users/avatar.py` — avatar processing (resize, thumbnail)
- Modify `src/api/users.py` — add `POST /users/{id}/avatar` endpoint
- Add `Pillow` dependency for image processing
- Add `boto3` dependency for S3

## Context
- Current stack: Python 3.12 + FastAPI + PostgreSQL
- No file storage exists in the project
- User table has `avatar_url: Optional[str]` column (unused)
- ~1000 registered users, ~50 uploads/day expected
