#!/bin/bash
# Install git hooks from scripts/hooks/ into .git/hooks/
# Run once after clone: bash scripts/install-hooks.sh

HOOKS_SRC="scripts/hooks"
HOOKS_DST=".git/hooks"

if [ ! -d "$HOOKS_SRC" ]; then
  echo "No hooks to install ($HOOKS_SRC not found)"
  exit 0
fi

for hook in "$HOOKS_SRC"/*; do
  name=$(basename "$hook")
  cp "$hook" "$HOOKS_DST/$name"
  chmod +x "$HOOKS_DST/$name"
  echo "Installed: $name"
done

echo "Done. Git hooks installed."
