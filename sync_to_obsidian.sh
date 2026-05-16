#!/bin/bash
# Sync Dental SaaS backend to Obsidian vault

set -e

BACKEND_DIR="$HOME/meu-backend"
VAULT_DIR="/storage/emulated/0/Obsidian/opencode-vault"
LOGS_DIR="$VAULT_DIR/logs"

cd "$BACKEND_DIR" || exit 1

echo "[$(date)] Starting sync..."

# Generate knowledge graph
python3 generate_graph.py
python3 export_obsidian.py

# Copy core files to vault
cp "$BACKEND_DIR/CONTEXT.md" "$VAULT_DIR/CONTEXT.md"
cp "$BACKEND_DIR/DECISIONS.md" "$VAULT_DIR/DECISIONS.md"

# Append sync event to today's log
TODAY=$(date +%Y-%m-%d)
LOG_FILE="$LOGS_DIR/${TODAY}.md"
mkdir -p "$LOGS_DIR"

if [ -f "$LOG_FILE" ]; then
    echo -e "\n### $(date +%H:%M:%S) -Sync completed\n- Context files synced to vault" >> "$LOG_FILE"
else
    echo "# $TODAY\n\n### $(date +%H:%M:%S) - Sync completed\n- Context files synced to vault" > "$LOG_FILE"
fi

# Update last_sync timestamp in CONTEXT.md
LAST_SYNC=$(date +%Y-%m-%d\ %H:%M:%S)
sed -i "s/## Current Status (May 2026)/## Current Status (May 2026)\\n- **Last Sync:** $LAST_SYNC/" "$BACKEND_DIR/CONTEXT.md"
sed -i "s/## Current Status (May 2026)/## Current Status (May 2026)\\n- **Last Sync:** $LAST_SYNC/" "$VAULT_DIR/CONTEXT.md"

echo "[$(date)] Sync complete"
