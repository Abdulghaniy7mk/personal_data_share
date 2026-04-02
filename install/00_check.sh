#!/usr/bin/env bash
# 00_check.sh — Pre-flight checks
# Run this FIRST. It tells you exactly what's ready and what's missing.
# Makes no system changes.

set -euo pipefail
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

ok()   { echo -e "${GREEN}  ✔${NC} $*"; }
warn() { echo -e "${YELLOW}  ⚠${NC} $*"; }
fail() { echo -e "${RED}  ✗${NC} $*"; }
head() { echo -e "\n${BLUE}[$1]${NC}"; }

ERRORS=0

head "System"
[[ $EUID -eq 0 ]] && ok "Running as root" || { fail "Must run as root (sudo bash 00_check.sh)"; ((ERRORS++)); }
ARCH=$(uname -m)
ok "Architecture: $ARCH"
[[ "$ARCH" == "x86_64" || "$ARCH" == "aarch64" ]] || warn "Untested arch — some packages may differ"
. /etc/os-release 2>/dev/null
ok "OS: $PRETTY_NAME"
[[ "$ID" == "debian" || "$ID_LIKE" == *debian* ]] || warn "Not Debian-based — adjust package names"

head "RAM"
RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
RAM_GB=$(echo "scale=1; $RAM_KB/1024/1024" | bc)
ok "RAM: ${RAM_GB} GB"
(( RAM_KB < 2000000 )) && { fail "Less than 2GB RAM — use low_ram.yaml and phi3:mini only"; ((ERRORS++)); }
(( RAM_KB < 4000000 )) && warn "Less than 4GB — use low_ram.yaml config"

head "Disk"
ROOT_FS=$(df -T / | awk 'NR==2{print $2}')
ok "Root filesystem: $ROOT_FS"
if [[ "$ROOT_FS" == "btrfs" ]]; then
    ok "Btrfs detected — snapshots will work"
else
    warn "Root is NOT btrfs — snapshots will be disabled"
    warn "For fresh install: choose btrfs during Debian netinstall"
fi
FREE_GB=$(df -BG / | awk 'NR==2{print $4}' | tr -d G)
ok "Free disk: ${FREE_GB} GB"
(( FREE_GB < 10 )) && { fail "Less than 10GB free — models won't fit"; ((ERRORS++)); }

head "Network"
ping -c1 -W3 8.8.8.8 &>/dev/null && ok "Internet: reachable" || { fail "No internet — required for package install"; ((ERRORS++)); }

head "Required packages"
for pkg in curl wget git python3 python3-pip; do
    command -v $pkg &>/dev/null && ok "$pkg: found" || warn "$pkg: missing (will install)"
done

head "Users"
id user &>/dev/null    && ok "user (UID 1000): exists"    || warn "user: will be created"
id ai-agent &>/dev/null && ok "ai-agent (UID 1001): exists" || warn "ai-agent: will be created"

head "GPU (optional — for faster LLM)"
if command -v nvidia-smi &>/dev/null; then
    ok "NVIDIA GPU detected — can use GPU layers in llama.cpp"
else
    warn "No GPU detected — CPU inference only (slower but works)"
fi

echo ""
if (( ERRORS > 0 )); then
    echo -e "${RED}$ERRORS error(s) found — fix before running 01_base.sh${NC}"
    exit 1
else
    echo -e "${GREEN}All checks passed — ready to build${NC}"
    echo "Run next: sudo bash 01_base.sh"
fi
