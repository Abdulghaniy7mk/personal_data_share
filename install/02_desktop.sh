#!/usr/bin/env bash
# 02_desktop.sh — Desktop Layer
# Installs XFCE (lightweight, Wayland-compatible via Xwayland).
# Enables accessibility bus (AT-SPI2) system-wide.
# Configures auto-login for 'user' — you'll still need your password for sudo.

set -euo pipefail
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info() { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
die()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

[[ $EUID -ne 0 ]] && die "Run as root"

# ── 1. XFCE desktop ───────────────────────────────────────────────────────────
info "Installing XFCE desktop"
apt-get install -y \
    xfce4 xfce4-goodies \
    lightdm lightdm-gtk-greeter \
    xorg \
    dbus-x11 \
    --no-install-recommends

# ── 2. Accessibility stack (required for AT-SPI app control) ──────────────────
info "Installing accessibility stack"
apt-get install -y \
    at-spi2-core \
    libatspi2.0-0 \
    python3-pyatspi \
    --no-install-recommends

# Enable AT-SPI2 bus globally — required for ai-agent to see UI elements
mkdir -p /etc/X11/xinit/xinitrc.d/
cat > /etc/X11/xinit/xinitrc.d/99-at-spi.sh << 'ATSPI'
#!/bin/sh
# Start accessibility bus for AI OS agent
export NO_AT_BRIDGE=0
/usr/lib/at-spi2-core/at-spi-bus-launcher --launch-immediately &
ATSPI
chmod +x /etc/X11/xinit/xinitrc.d/99-at-spi.sh

# ── 3. LightDM config ─────────────────────────────────────────────────────────
info "Configuring LightDM"
cat > /etc/lightdm/lightdm.conf << 'LIGHTDM'
[LightDM]
run-directory=/run/lightdm

[Seat:*]
# Auto-login for the real user — AI agent never logs in via GUI
autologin-user=user
autologin-user-timeout=0
session-wrapper=/etc/lightdm/Xsession

[Greeter]
LIGHTDM

systemctl enable lightdm
info "LightDM configured (auto-login for 'user')"

# ── 4. Essential user apps ────────────────────────────────────────────────────
info "Installing essential apps"
apt-get install -y \
    firefox-esr \
    mousepad \
    thunar \
    xfce4-terminal \
    --no-install-recommends

# VS Code — add Microsoft repo
info "Adding VS Code repository"
wget -qO /tmp/ms.gpg https://packages.microsoft.com/keys/microsoft.asc
gpg --dearmor < /tmp/ms.gpg > /usr/share/keyrings/microsoft.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft.gpg] \
    https://packages.microsoft.com/repos/code stable main" \
    > /etc/apt/sources.list.d/vscode.list
apt-get update -q
apt-get install -y code --no-install-recommends
info "VS Code installed"

# ── 5. DBus proxy user service launcher ──────────────────────────────────────
# Creates a startup script that user's session launches automatically
info "Configuring AI services to start with user session"
mkdir -p /home/user/.config/autostart

cat > /home/user/.config/autostart/ai-dbus-proxy.desktop << 'AUTOSTART'
[Desktop Entry]
Type=Application
Name=AI DBus Proxy
Comment=AI OS DBus bridge (runs as current user)
Exec=/opt/ai-os/venv/bin/python -m execution.dbus_proxy
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
AUTOSTART

cat > /home/user/.config/autostart/ai-ui-server.desktop << 'AUTOSTART'
[Desktop Entry]
Type=Application
Name=AI UI Server
Comment=AI OS WebSocket UI server
Exec=/opt/ai-os/venv/bin/python -m ui.ui_server
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
AUTOSTART

chown -R user:user /home/user/.config/

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "Desktop setup complete"
echo "  Next: bash 03_ai_brain.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
