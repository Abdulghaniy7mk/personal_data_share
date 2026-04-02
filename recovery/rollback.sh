#!/usr/bin/env bash
# recovery/rollback.sh — one-command rollback to a named snapshot
# Usage: sudo bash rollback.sh [snapshot_id]
set -euo pipefail

SNAPPER_CONFIG="ai-os"

if [ -z "${1:-}" ]; then
  echo "Available snapshots:"
  snapper -c "$SNAPPER_CONFIG" list
  echo ""
  read -rp "Enter snapshot number to roll back to: " SNAP_ID
else
  SNAP_ID="$1"
fi

echo ""
echo "!! WARNING: This will rollback filesystem state to snapshot #${SNAP_ID} !!"
echo "!! All changes since that snapshot will be lost. !!"
echo ""
read -rp "Type YES to confirm: " CONFIRM
[ "$CONFIRM" = "YES" ] || { echo "Aborted."; exit 1; }

echo "Stopping AI services..."
systemctl stop ai-agent ai-ui-server 2>/dev/null || true

echo "Creating safety snapshot of current state..."
snapper -c "$SNAPPER_CONFIG" create --type single \
  --description "pre-rollback-safety-$(date +%Y%m%d-%H%M%S)" 

echo "Rolling back to snapshot #${SNAP_ID}..."
snapper -c "$SNAPPER_CONFIG" undochange "${SNAP_ID}..0"

echo "Restarting AI services..."
systemctl start ai-agent ai-ui-server 2>/dev/null || true

echo ""
echo "Rollback to snapshot #${SNAP_ID} complete."
