# Scoring Rubric: Devil's Advocate — Avatar Upload Proposal

## Completeness (weight: high)
- Must include "Why NOT" with at least 2 arguments (dependency weight, security, over-engineering)
- Must include alternatives — at least one that avoids file uploads entirely (e.g., Gravatar)
- Must include "What Breaks" identifying CI/CD and dependency impacts
- Must include security-focused assertions (file type validation, size limits, SVG attacks)

## Accuracy (weight: high)
- Pillow CVE history is real and relevant
- boto3 size/complexity concern is factually accurate
- SVG embedded script attack is a known vector
- Pre-signed URL pattern is correctly described (client direct upload)

## Format (weight: medium)
- Uses markdown headers and structured sections
- Eval Assertions use table format with DA-N and SA-N IDs
- Assertion Summary present with counts
- Clear verdict with reasoning

## Relevance (weight: high)
- Arguments specific to THIS proposal (S3 + Pillow for avatar uploads)
- Security concerns tied to image processing, not generic file upload fears
- Scale argument references actual numbers (50 uploads/day)
- Alternatives address the actual problem (user avatars)

## Safety (weight: low)
- Constructive — doesn't dismiss the user need (personalization)
- Suggests incremental approach (Gravatar first, S3 later)
- Security concerns are protective, not fear-mongering
