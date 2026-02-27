# Scoring Rubric: Devil's Advocate

## Completeness (weight: high)
- Must include "Why NOT" section with at least 2 concrete arguments against the feature
- Must include "Simpler Alternatives" with at least 1 actionable alternative
- Must include "What Breaks" or "Eval Assertions" identifying affected components
- Must include structured assertions (DA-IDs or edge cases)

## Accuracy (weight: high)
- Technical arguments must be factually correct (e.g., Redis failure modes are real)
- File paths and component references must be plausible given the context
- No hallucinated dependencies or non-existent patterns

## Format (weight: medium)
- Uses markdown headers and structured sections
- Eval Assertions use table format with IDs (DA-N, SA-N)
- Assertion Summary present with counts

## Relevance (weight: high)
- All arguments specific to THIS proposal (not generic anti-caching sentiment)
- Alternatives address the actual problem (API latency)
- Side effects reference files mentioned in the scope

## Safety (weight: low)
- No dismissive or hostile tone
- Constructive skepticism, not cynicism
- No recommendation to ignore user requirements
