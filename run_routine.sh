#!/usr/bin/env bash
# Nightly Buzz Screener — Routine entry point.
#
# The SQLite mention DB must survive across routine runs. We keep it on a
# dedicated 'data/mention-db' branch so it never touches main. Each run
# restores the DB from that branch before scraping, then pushes the
# updated blob back after the screener finishes.
#
# Required env vars (set in the Routine's cloud environment):
#   REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
#   SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM, EMAIL_TO
set -euo pipefail

TODAY=$(date +%F)
DATA_BRANCH="data/mention-db"
DB_FILE="buzz_mentions.db"

echo "=== Nightly Buzz Screener — $TODAY ==="

git config user.email "routine@claude.ai"
git config user.name "Nightly Buzz Routine"

# ── Restore DB from the data branch (if it exists) ──────────────────────────
if git fetch origin "$DATA_BRANCH" 2>/dev/null; then
    if git show "FETCH_HEAD:$DB_FILE" > "$DB_FILE" 2>/dev/null; then
        echo "[routine] Restored $DB_FILE from $DATA_BRANCH"
    else
        echo "[routine] No $DB_FILE on $DATA_BRANCH yet — starting fresh"
    fi
else
    echo "[routine] $DATA_BRANCH does not exist yet — starting fresh"
fi

# ── Run the screener ─────────────────────────────────────────────────────────
pip install -r requirements.txt -q
python run_nightly.py

# ── Push updated DB to the data branch via git plumbing (no checkout) ────────
BLOB=$(git hash-object -w "$DB_FILE")
TREE=$(printf '100644 blob %s\t%s\n' "$BLOB" "$DB_FILE" | git mktree)

PARENT_ARGS=""
if git rev-parse --verify "refs/remotes/origin/$DATA_BRANCH" >/dev/null 2>&1; then
    PARENT_ARGS="-p origin/$DATA_BRANCH"
fi

# shellcheck disable=SC2086
COMMIT=$(echo "data: update mention DB for $TODAY [skip ci]" \
    | git commit-tree "$TREE" $PARENT_ARGS)

git push origin "$COMMIT:refs/heads/$DATA_BRANCH"
echo "[routine] Pushed updated DB to $DATA_BRANCH"
echo "=== Done ==="
