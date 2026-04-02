#!/usr/bin/env bash
# 01_base.sh — Base System Setup
# Sets up: Btrfs+Snapper, users (UID 1000 + 1001), core packages, AppArmor, auditd
# Safe to re-run — each step checks before acting.

set -euo pipefail
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
die()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

[[ $EUID -ne 0 ]] && die "Run as root"

# ── 1. Package update ──────────────────────────────────────────────────────────
info "Updating package lists"
apt-get update -q

# ── 2. Core packages ───────────────────────────────────────────────────────────
info "Installing core packages"
apt-get install -y \
    btrfs-progs snapper \
    apparmor apparmor-utils apparmor-profiles \
    auditd audispd-plugins \
    bubblewrap \
    python3 python3-pip python3-venv python3-dev \
    python3-dbus python3-pyatspi \
    ydotool neofetch \
    at-spi2-core \
    git curl wget \
    usbutils pciutils \
    systemd-container \
    bc socat \
    --no-install-recommends

# ── 3. Btrfs + Snapper ────────────────────────────────────────────────────────
ROOT_FS=$(df -T / | awk 'NR==2{print $2}')

if [[ "$ROOT_FS" == "btrfs" ]]; then
    info "Btrfs detected — configuring Snapper"

    if ! snapper -c root list &>/dev/null; then
        snapper -c root create-config /
        info "Snapper config created for /"
    else
        warn "Snapper root config already exists — skipping"
    fi

    # Limit snapshot count so disk doesn't fill up
    snapper -c root set-config \
        NUMBER_LIMIT=10 \
        NUMBER_MIN_AGE=1800 \
        TIMELINE_CREATE=yes \
        TIMELINE_CLEANUP=yes \
        TIMELINE_LIMIT_HOURLY=3 \
        TIMELINE_LIMIT_DAILY=3 \
        TIMELINE_LIMIT_WEEKLY=1 \
        TIMELINE_LIMIT_MONTHLY=1

    systemctl enable --now snapper-timeline.timer
    systemctl enable --now snapper-cleanup.timer
    info "Snapper timers enabled"
else
    warn "Root is $ROOT_FS (not btrfs) — Snapper not configured"
    warn "Snapshot rollback will be unavailable"
    warn "To enable: reinstall with btrfs as root filesystem"
fi

# ── 4. Users ──────────────────────────────────────────────────────────────────
info "Creating users"

# Real user (UID 1000) — skip if exists
if ! id "user" &>/dev/null; then
    useradd --uid 1000 --create-home --shell /bin/bash \
            --comment "Real User" user
    # Set a password — will prompt
    echo "Set password for 'user' (your login account):"
    passwd user
    info "Created user (UID 1000)"
else
    warn "user (UID 1000) already exists"
fi

# AI agent (UID 1001) — no login, no password
if ! id "ai-agent" &>/dev/null; then
    useradd --uid 1001 --create-home --home-dir /home/ai-agent \
            --shell /usr/sbin/nologin \
            --comment "AI OS Agent" ai-agent
    info "Created ai-agent (UID 1001)"
else
    warn "ai-agent (UID 1001) already exists"
fi

# Create ai-agent group for socket access
if ! getent group ai-agent &>/dev/null; then
    groupadd ai-agent
    usermod -aG ai-agent user       # user can read AI agent sockets
    usermod -aG ai-agent ai-agent
    info "Created ai-agent group"
fi

# ── 5. Runtime directories ────────────────────────────────────────────────────
info "Creating runtime directories"
mkdir -p /run/ai-os
chown root:ai-agent /run/ai-os
chmod 0770 /run/ai-os

mkdir -p /var/log/ai-os
chown ai-agent:ai-agent /var/log/ai-os
chmod 0755 /var/log/ai-os

mkdir -p /opt/ai-os/models
chown -R ai-agent:ai-agent /opt/ai-os

# ── 6. HMAC session key (regenerated each boot via tmpfs) ─────────────────────
info "Creating session key generator (systemd-tmpfiles)"
cat > /etc/tmpfiles.d/ai-os.conf << 'TMPFILES'
# AI OS runtime files — recreated on each boot
d /run/ai-os 0770 root ai-agent -
f /run/ai-os/tagger.key 0600 root root -
TMPFILES

# Generate initial key now
dd if=/dev/urandom bs=32 count=1 2>/dev/null > /run/ai-os/tagger.key
chmod 0600 /run/ai-os/tagger.key
chown root:root /run/ai-os/tagger.key
info "Session key generated at /run/ai-os/tagger.key"

# ── 7. AppArmor ───────────────────────────────────────────────────────────────
info "Enabling AppArmor"
systemctl enable --now apparmor

# Copy profile if repo is present
PROFILE_SRC="$(dirname "$0")/../ai-os/apparmor/ai-agent"
if [[ -f "$PROFILE_SRC" ]]; then
    cp "$PROFILE_SRC" /etc/apparmor.d/ai-agent
    apparmor_parser -r /etc/apparmor.d/ai-agent
    info "AppArmor profile loaded"
else
    warn "AppArmor profile not found at $PROFILE_SRC — load manually later"
fi

# ── 8. auditd ─────────────────────────────────────────────────────────────────
info "Configuring auditd rules"
cat > /etc/audit/rules.d/ai-agent.rules << 'AUDIT'
# Tag all AI agent actions in the audit log
-a always,exit -F uid=1001 -S execve    -k ai-agent-exec
-a always,exit -F uid=1001 -S openat    -k ai-agent-fs
-a always,exit -F uid=1001 -S unlinkat  -k ai-agent-delete
AUDIT

systemctl enable --now auditd
augenrules --load 2>/dev/null || true
info "auditd rules installed"

# ── 9. ydotool setup ──────────────────────────────────────────────────────────
info "Configuring ydotool"
# ydotoold needs uinput — load module and persist
modprobe uinput
echo "uinput" > /etc/modules-load.d/uinput.conf

# ydotoold socket — ai-agent group can use it
cat > /etc/systemd/system/ydotoold.service << 'YDOTOOL'
[Unit]
Description=ydotool daemon
After=local-fs.target

[Service]
Type=simple
ExecStart=/usr/bin/ydotoold --socket-path /run/ai-os/ydotool.sock --socket-perm 0660
Restart=always

[Install]
WantedBy=multi-user.target
YDOTOOL

systemctl daemon-reload
systemctl enable --now ydotoold
info "ydotoold running on /run/ai-os/ydotool.sock"

# ── 10. Python venv for AI agent ──────────────────────────────────────────────
info "Creating Python venv for ai-agent"
python3 -m venv /opt/ai-os/venv
/opt/ai-os/venv/bin/pip install --quiet --upgrade pip
chown -R ai-agent:ai-agent /opt/ai-os/venv

# ── 11. Aegis OS Branding ─────────────────────────────────────────────────────
info "Applying Aegis OS Branding"

# Update OS release info
cat > /etc/os-release << 'OSINFO'
PRETTY_NAME="Aegis OS"
NAME="Aegis OS"
ID=aegis
ID_LIKE=debian
HOME_URL="https://github.com/ai-os"
SUPPORT_URL="https://github.com/ai-os/issues"
BUG_REPORT_URL="https://github.com/ai-os/issues"
OSINFO

cat > /etc/lsb-release << 'LSB'
DISTRIB_ID=Aegis
DISTRIB_RELEASE=1.0
DISTRIB_CODENAME=genesis
DISTRIB_DESCRIPTION="Aegis OS"
LSB

# Copy logo and wallpaper to system directories (if present in repo)
mkdir -p /usr/share/backgrounds/aegis /usr/share/icons/aegis
if [[ -d "$REPO_DIR/ui/assets" ]]; then
    cp "$REPO_DIR/ui/assets/aegis-wallpaper"* /usr/share/backgrounds/aegis/ 2>/dev/null || true
    cp "$REPO_DIR/ui/assets/aegis-logo"* /usr/share/icons/aegis/ 2>/dev/null || true
    # Set default symlink
    ln -sf /usr/share/backgrounds/aegis/aegis-wallpaper.png /usr/share/backgrounds/default.png
fi

# Configure neofetch globally to use our custom ASCII shield
mkdir -p /etc/neofetch
cat > /etc/neofetch/config.conf << 'NEOCONF'
print_info() {
    info title
    info underline
    info "OS" distro
    info "Host" model
    info "Kernel" kernel
    info "Uptime" uptime
    info "Packages" packages
    info "Shell" shell
    info "Resolution" resolution
    info "DE" de
    info "WM" wm
    info "Theme" theme
    info "Icons" icons
    info "Terminal" term
    info "Terminal Font" term_font
    info "CPU" cpu
    info "GPU" gpu
    info "Memory" memory
}
title_fqdn="off"
kernel_shorthand="on"
distro_shorthand="off"
os_arch="on"
uptime_shorthand="on"
memory_percent="off"
package_managers="on"
shell_path="off"
shell_version="on"

image_backend="ascii"
image_source="/etc/neofetch/aegis.ascii"
ascii_distro="auto"
ascii_colors=(4 6 1 8 8 6)
ascii_bold="on"
NEOCONF

# The Aegis OS Shield ASCII art
cat > /etc/neofetch/aegis.ascii << 'AEGIS_ASCII'
${c1}       /\       
${c1}      /  \      
${c1}     /    \     
${c1}    /  ${c2}/\${c1}  \    
${c1}   /  ${c2}/__\${c1}  \   
${c1}  /__________\  
${c4}  A E G I S  O S
AEGIS_ASCII
chmod 644 /etc/neofetch/aegis.ascii /etc/neofetch/config.conf

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "Base setup complete"
echo "  Next: bash 02_desktop.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

