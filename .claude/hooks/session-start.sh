#!/bin/bash
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Copy all project skills to global ~/.claude/skills/ so they're available every session
mkdir -p ~/.claude/skills
for skill_dir in "$CLAUDE_PROJECT_DIR/.claude/skills"/*/; do
  if [ -d "$skill_dir" ]; then
    cp -r "$skill_dir" ~/.claude/skills/
  fi
done
