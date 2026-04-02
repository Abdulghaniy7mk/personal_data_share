#!/usr/bin/env bash
# 05_test.sh — Smoke Tests
# Runs after deploy + reboot to verify every layer is working.
# Non-destructive — reads only, makes no system changes.

set -euo pipefail
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

pass() { echo -e "  ${GREEN}✔${NC} $*"; }
fail() { echo -e "  ${RED}✗${NC} $*"; FAILED=$((FAILED+1)); }
warn() { echo -e "  ${YELLOW}⚠${NC} $*"; }
FAILED=0

echo "AI OS Smoke Tests"
echo "═══════════════════════════════════"

# ── Users ─────────────────────────────────────────────────────────────────────
echo -e "\n[Users]"
id user    &>/dev/null && pass "user (UID 1000) exists"    || fail "user missing"
id ai-agent &>/dev/null && pass "ai-agent (UID 1001) exists" || fail "ai-agent missing"
[[ $(id -u user) == "1000" ]]     && pass "user UID is 1000"    || fail "user UID wrong"
[[ $(id -u ai-agent) == "1001" ]] && pass "ai-agent UID is 1001" || fail "ai-agent UID wrong"
getent group ai-agent &>/dev/null && pass "ai-agent group exists" || fail "ai-agent group missing"

# ── Services ──────────────────────────────────────────────────────────────────
echo -e "\n[Services]"
for svc in ai-input-tagger ai-agent ollama auditd apparmor ydotoold; do
    status=$(systemctl is-active "$svc" 2>/dev/null)
    [[ "$status" == "active" ]] && pass "$svc: running" || fail "$svc: $status"
done

# ── Sockets ───────────────────────────────────────────────────────────────────
echo -e "\n[Sockets]"
for sock in /run/ai-os/agent.sock /run/ai-os/tagger.key /run/ai-os/ydotool.sock; do
    [[ -e "$sock" ]] && pass "$sock: exists" || fail "$sock: missing"
done

# ── Security ──────────────────────────────────────────────────────────────────
echo -e "\n[Security]"
apparmor_status 2>/dev/null | grep -q "ai-agent" && \
    pass "AppArmor profile: loaded" || warn "AppArmor profile not loaded"

auditctl -l 2>/dev/null | grep -q "ai-agent" && \
    pass "Audit rules: active" || warn "Audit rules not active"

[[ -f /etc/sudoers.d/ai-agent-snapper ]] && \
    pass "Snapper sudo rules: installed" || warn "Snapper sudo rules missing"

# ── Filesystem ────────────────────────────────────────────────────────────────
echo -e "\n[Filesystem]"
ROOT_FS=$(df -T / | awk 'NR==2{print $2}')
[[ "$ROOT_FS" == "btrfs" ]] && pass "Root: btrfs" || warn "Root: $ROOT_FS (not btrfs — snapshots disabled)"
snapper list 2>/dev/null | grep -q "root" && \
    pass "Snapper: configured" || warn "Snapper not configured (non-btrfs system)"

# ── AI brain ──────────────────────────────────────────────────────────────────
echo -e "\n[AI Brain]"
ollama list 2>/dev/null | grep -q "phi3\|mistral\|qwen" && \
    pass "Ollama: model available" || fail "Ollama: no model found (run 03_ai_brain.sh)"

VENV="/opt/ai-os/venv"
[[ -d "$VENV" ]] && pass "Python venv: exists" || fail "Python venv missing"
"$VENV/bin/python" -c "import yaml, websockets, psutil" 2>/dev/null && \
    pass "Python deps: installed" || fail "Python deps missing (run pip install -r requirements.txt)"

# ── Live agent test ───────────────────────────────────────────────────────────
echo -e "\n[Live Agent Test]"
if [[ -S /run/ai-os/agent.sock ]]; then
    RESP=$(echo '{"text":"ping","source":"HUMAN"}' | \
           socat - UNIX-CONNECT:/run/ai-os/agent.sock 2>/dev/null || echo "")
    [[ -n "$RESP" ]] && pass "Agent socket: responds" || warn "Agent socket: no response"
else
    warn "Agent socket not found — agent may still be starting"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════"
if (( FAILED == 0 )); then
    echo -e "${GREEN}All tests passed${NC}"
    echo ""
    echo "Open the UI: http://localhost:8765/ui/index.html"
    echo "Try: 'open VS Code' or 'fix my fingerprint scanner'"
else
    echo -e "${RED}$FAILED test(s) failed${NC}"
    echo "Check: sudo journalctl -u ai-agent --since '5 min ago'"
fi
