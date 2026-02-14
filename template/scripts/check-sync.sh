#!/bin/bash
# check-sync.sh — Shows divergence between template/.claude and .claude
# This is INFORMATIONAL only — not all differences need syncing!

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           Template/.claude vs Root/.claude Sync Check        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Files only in root (customizations)
echo "=== Files only in root (customizations) ==="
comm -23 \
  <(find .claude -type f \( -name "*.md" -o -name "*.mjs" -o -name "*.json" \) 2>/dev/null | sed 's|^.claude/||' | sort) \
  <(find template/.claude -type f \( -name "*.md" -o -name "*.mjs" -o -name "*.json" \) 2>/dev/null | sed 's|^template/.claude/||' | sort)
echo ""

# Files only in template
echo "=== Files only in template (need to add to root?) ==="
comm -13 \
  <(find .claude -type f \( -name "*.md" -o -name "*.mjs" -o -name "*.json" \) 2>/dev/null | sed 's|^.claude/||' | sort) \
  <(find template/.claude -type f \( -name "*.md" -o -name "*.mjs" -o -name "*.json" \) 2>/dev/null | sed 's|^template/.claude/||' | sort)
echo ""

# Files with different line counts
echo "=== Files with different line counts ==="
for f in $(find template/.claude -type f \( -name "*.md" -o -name "*.mjs" \) 2>/dev/null); do
  root_f="${f#template/}"
  if [ -f "$root_f" ]; then
    t_lines=$(wc -l < "$f" | tr -d ' ')
    r_lines=$(wc -l < "$root_f" | tr -d ' ')
    if [ "$t_lines" != "$r_lines" ]; then
      diff=$((r_lines - t_lines))
      if [ $diff -gt 0 ]; then
        echo "$root_f: template=$t_lines root=$r_lines (+$diff root newer)"
      else
        echo "$root_f: template=$t_lines root=$r_lines ($diff template newer)"
      fi
    fi
  fi
done
echo ""

# Scripts sync check
echo "=== Scripts sync check ==="
for f in template/scripts/*.sh; do
  root_f="${f#template/}"
  if [ ! -f "$root_f" ]; then
    echo "MISSING in root: $root_f"
  else
    if ! diff -q "$f" "$root_f" > /dev/null 2>&1; then
      t_lines=$(wc -l < "$f" | tr -d ' ')
      r_lines=$(wc -l < "$root_f" | tr -d ' ')
      diff_val=$((r_lines - t_lines))
      if [ $diff_val -gt 0 ]; then
        echo "$root_f: template=$t_lines root=$r_lines (+$diff_val root newer)"
      elif [ $diff_val -lt 0 ]; then
        echo "$root_f: template=$t_lines root=$r_lines ($diff_val template newer)"
      else
        echo "$root_f: same LOC but content differs"
      fi
    fi
  fi
done
echo ""

echo "─────────────────────────────────────────────────────────────────"
echo "Review divergence manually. Not all differences need syncing."
echo "See .claude/CUSTOMIZATIONS.md for sync policy."
echo "─────────────────────────────────────────────────────────────────"
