#!/usr/bin/env bash
# recovery/panic_mode.sh — Emergency stop. Kills ALL AI processes immediately.
# Can be triggered by the panic button in the UI or by the human user at any time.
set -euo pipefail

echo "!!! AI OS PANIC MODE TRIGGERED !!!"
echo "Stopping all AI services..."

# Kill all ai-agent processes
systemctl stop ai-agent ai-ui-server ai-dbus-proxy ai-input-tagger 2>/dev/null || true
pkill -u ai-agent 2>/dev/null || true

# Revoke ydotool socket access
chmod 600 /run/ydotool.sock 2>/dev/null || true

# Log the event
mkdir -p /var/log/ai-os
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) PANIC_MODE initiated by $(whoami)" \
  >> /var/log/ai-os/panic.log

echo ""
echo "All AI processes stopped."
echo "System is safe. To restart: sudo systemctl start ai-agent"
echo ""
echo "Last 5 audit events:"
sqlite3 /var/log/ai-os/audit.db \
  "SELECT ts, event, substr(payload,1,80) FROM events ORDER BY ts DESC LIMIT 5;" \
  2>/dev/null || echo "  (audit log not available)"
