#!/usr/bin/env bash
# scripts/vps/check-doc-references.sh
# Lint: verify all ADR-NNN and TECH-NNN tokens in dld-orchestrator.md exist in
# .claude/rules/architecture.md and ai/features/ respectively.
# Also checks that all §N pointer refs in CLAUDE.md/architecture.md point to
# existing sections in dld-orchestrator.md.
#
# Usage: bash scripts/vps/check-doc-references.sh
# Env override: DLD_ORCH_DOC=/path/to/dld-orchestrator.md
# Exit 0: all OK. Exit 1: missing references.
# Designed to run from project root.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

ORCH_DOC="${DLD_ORCH_DOC:-${HOME}/.claude/projects/-root/memory/dld-orchestrator.md}"
ARCH_DOC="${PROJECT_ROOT}/.claude/rules/architecture.md"
FEATURES_DIR="${PROJECT_ROOT}/ai/features"
CLAUDE_MD="${PROJECT_ROOT}/CLAUDE.md"

errors=0

if [[ ! -f "${ORCH_DOC}" ]]; then
    echo "ERROR: dld-orchestrator.md not found at ${ORCH_DOC}"
    exit 1
fi

echo "Checking: ${ORCH_DOC}"
echo "Against:  ${ARCH_DOC}"
echo "          ${FEATURES_DIR}/"
echo ""

# ── ADR tokens ──────────────────────────────────────────────────────────────
# Extract unique ADR-NNN tokens from orchestrator doc
adr_tokens=$(grep -oE 'ADR-[0-9]{3}' "${ORCH_DOC}" | sort -u)

for token in ${adr_tokens}; do
    if grep -qF "${token}" "${ARCH_DOC}" 2>/dev/null; then
        echo "OK   ${token}"
    else
        echo "MISSING ${token} in ${ARCH_DOC}"
        errors=$((errors + 1))
    fi
done

# ── TECH tokens ──────────────────────────────────────────────────────────────
# Extract unique TECH-NNN tokens from orchestrator doc (not the doc itself)
tech_tokens=$(grep -oE 'TECH-[0-9]{3}[a-z]?' "${ORCH_DOC}" | sort -u)

for token in ${tech_tokens}; do
    # Extract numeric part only for file search (ignore sub-spec suffix)
    base_token=$(echo "${token}" | grep -oE 'TECH-[0-9]{3}')
    # Check if any file in ai/features/ matches TECH-NNN-*.md
    if compgen -G "${FEATURES_DIR}/${base_token}-*.md" > /dev/null 2>&1; then
        echo "OK   ${token}"
    else
        echo "MISSING ${token} in ${FEATURES_DIR}/"
        errors=$((errors + 1))
    fi
done

# ── Section pointer check ────────────────────────────────────────────────────
# Check that "dld-orchestrator.md§N" pointers (where N is a digit or digit+digit)
# actually point to existing "## §N" sections in the orchestrator doc.
pointer_refs=$(grep -ohE 'dld-orchestrator\.md§[0-9]+(\.[0-9]+)?' \
    "${ARCH_DOC}" "${CLAUDE_MD}" 2>/dev/null | sort -u)

for ref in ${pointer_refs}; do
    section="${ref#dld-orchestrator.md}"  # e.g. §5 or §5.3
    # For subsections like §5.3, check parent §5
    parent=$(echo "${section}" | grep -oE '§[0-9]+')
    # Grep for "## §N" heading in the doc
    if grep -qE "^## ${parent}[[:space:]]" "${ORCH_DOC}" 2>/dev/null; then
        echo "OK   pointer ${ref}"
    else
        echo "MISSING pointer ${ref} — no '## ${parent}' heading in ${ORCH_DOC}"
        errors=$((errors + 1))
    fi
done

echo ""
if [[ ${errors} -eq 0 ]]; then
    echo "All checks passed."
    exit 0
else
    echo "FAILED: ${errors} missing reference(s)."
    exit 1
fi
