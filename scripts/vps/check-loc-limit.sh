#!/usr/bin/env bash
# scripts/vps/check-loc-limit.sh
# Gate: no Python module under scripts/vps/ exceeds the LOC ceiling.
#
# 400 lines for code, 600 for tests — the limits in .claude/rules/architecture.md
# § Limits. They exist because a module that no longer fits in one reading is where
# the split debt accumulates: TECH-210..216 and TECH-213 spent real runs cutting
# callback.py (1438), orchestrator.py (1078) and claude-runner.py (912) back under
# the line, and nothing stopped them growing there in the first place.
#
# This is the thing that stops it. `wc -l` needs no model and no judgement, so it
# belongs in CI rather than in a prompt asking an agent to be careful.
#
# Files already over the line when the gate landed are listed in loc-limit-baseline.txt
# with their count. That file is a debt register, not an exemption list: a baselined file
# that GREW still fails, and one that came back under the limit fails too, because a stale
# entry would silently cover the next regression.
#
# Usage:  bash scripts/vps/check-loc-limit.sh [--json] [dir ...]
# Env:    LOC_LIMIT_CODE (default 400), LOC_LIMIT_TESTS (default 600),
#         LOC_LIMIT_BASELINE (default scripts/vps/loc-limit-baseline.txt)
# Exit 0: every file within its limit or unchanged at its baseline.
# Exit 1: a new violation, a baselined file that grew, or a stale baseline entry.
# Exit 2: usage.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIMIT_CODE="${LOC_LIMIT_CODE:-400}"
LIMIT_TESTS="${LOC_LIMIT_TESTS:-600}"

json=0
dirs=()
for arg in "$@"; do
    case "$arg" in
        --json) json=1 ;;
        -h|--help)
            sed -n '2,16p' "${BASH_SOURCE[0]}"
            exit 0
            ;;
        -*)
            echo "unknown flag: $arg" >&2
            exit 2
            ;;
        *) dirs+=("$arg") ;;
    esac
done
if [[ ${#dirs[@]} -eq 0 ]]; then
    dirs=("${SCRIPT_DIR}")
fi

PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BASELINE="${LOC_LIMIT_BASELINE:-${SCRIPT_DIR}/loc-limit-baseline.txt}"

# path -> baselined line count
declare -A baseline=()
if [[ -f "${BASELINE}" ]]; then
    while read -r path count; do
        # A CRLF register (checked out on Windows, or written by a Windows tool) leaves
        # \r on the count and every arithmetic comparison below dies on it.
        path="${path%$'\r'}"
        count="${count%$'\r'}"
        [[ -z "${path}" || "${path}" == \#* ]] && continue
        baseline["${path}"]="${count}"
    done < "${BASELINE}"
fi

violations=()
stale=()
checked=0

while IFS= read -r -d '' file; do
    lines=$(wc -l < "$file" | tr -d ' ')
    case "$file" in
        */tests/*) limit="${LIMIT_TESTS}" ;;
        *) limit="${LIMIT_CODE}" ;;
    esac
    checked=$((checked + 1))
    rel="${file#"${PROJECT_ROOT}"/}"
    # Match a baseline entry by path SUFFIX, not by exact string. The gate is run from
    # CI (repo-relative paths), from a worktree (a different absolute prefix), and from
    # the tests (a tmp tree outside the repo entirely) — an exact-match register would
    # silently match nothing in two of those three and report every debt file as new.
    # Separators are normalised on both sides: `find` returns whatever mix of \ and /
    # the starting path had on a Windows host, and the register is written with /.
    norm_file="${file//\\//}"
    norm_rel="${rel//\\//}"
    based=""
    for key in "${!baseline[@]}"; do
        norm_key="${key//\\//}"
        if [[ "$norm_rel" == "$norm_key" || "$norm_rel" == *"/$norm_key" || "$norm_file" == *"/$norm_key" || "$norm_file" == "$norm_key" ]]; then
            based="${baseline[$key]}"
            break
        fi
    done
    if [[ "$lines" -gt "$limit" ]]; then
        if [[ -z "${based}" ]]; then
            violations+=("${rel}|${lines}|${limit}|new")
        elif [[ "$lines" -gt "${based}" ]]; then
            violations+=("${rel}|${lines}|${based}|grew past its baseline")
        fi
    elif [[ -n "${based}" ]]; then
        stale+=("${rel}|${lines}|${limit}")
    fi
done < <(find "${dirs[@]}" -type f -name '*.py' -not -path '*/__pycache__/*' -print0 | sort -z)

if [[ "$json" -eq 1 ]]; then
    printf '{"checked":%d,"violations":[' "$checked"
    for i in "${!violations[@]}"; do
        IFS='|' read -r f n l <<< "${violations[$i]}"
        [[ "$i" -gt 0 ]] && printf ','
        printf '{"file":"%s","lines":%d,"limit":%d}' "$f" "$n" "$l"
    done
    printf ']}\n'
else
    if [[ ${#violations[@]} -eq 0 && ${#stale[@]} -eq 0 ]]; then
        echo "LOC limit OK — ${checked} file(s) checked (${LIMIT_CODE} code / ${LIMIT_TESTS} tests, ${#baseline[@]} baselined)"
    fi
    if [[ ${#violations[@]} -gt 0 ]]; then
        echo "LOC limit exceeded — split before adding to these:"
        for v in "${violations[@]}"; do
            IFS='|' read -r f n l why <<< "$v"
            printf '  %-52s %4d / %-4d  %s\n' "$f" "$n" "$l" "$why"
        done
    fi
    if [[ ${#stale[@]} -gt 0 ]]; then
        echo "Stale baseline entries — under the limit now, drop their line from ${BASELINE##*/}:"
        for s in "${stale[@]}"; do
            IFS='|' read -r f n l <<< "$s"
            printf '  %-52s %4d / %d\n' "$f" "$n" "$l"
        done
    fi
fi

[[ ${#violations[@]} -eq 0 && ${#stale[@]} -eq 0 ]]
