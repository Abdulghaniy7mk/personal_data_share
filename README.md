# AI OS — Secure Autonomous User Layer

A production-grade AI agent layer on top of Linux. The AI operates as a
separate Unix user (UID 1001), controls apps through Wayland-compatible
automation, and is bounded by a multi-layer security stack.

**Architecture**: deterministic + probabilistic hybrid autonomous system.

---

## Repo structure

```
ai-os/
├── core/
│   ├── agent_main.py        # Central agent loop — start here
│   ├── planner.py           # LLM planner (local Mistral/Phi-3/Qwen)
│   ├── context_firewall.py  # Filters memory before inference (Gap 4 fix)
│   └── memory.py            # Cognitive + operational memory stores
├── security/
│   ├── input_tagger.py      # HMAC-stamps real human input (root daemon)
│   ├── confirm_gate.py      # Detect → Analyze → Explain → Suggest → Execute
│   ├── supervisor.py        # Rate limiter + loop detector (Gap 2 fix)
│   └── channel_guard.py     # Privilege separation by channel (Gap 1 fix)
├── execution/
│   ├── executor.py          # DBus → AT-SPI → ydotool execution engine
│   └── real_world.py        # Non-bypassable barrier for payments/orders (Gap 3 fix)
├── recovery/
│   └── snapshot.py          # Btrfs snapshot + rollback via snapper
├── voice/
│   └── voice_pipeline.py    # Whisper STT + Kokoro/Piper TTS (local only)
├── config/
│   ├── default.yaml         # Full config (8GB+ RAM)
│   └── low_ram.yaml         # 3–4GB RAM config (Phi-3-mini)
├── systemd/
│   └── ai-agent.service     # Hardened systemd unit
├── apparmor/
│   └── ai-agent             # AppArmor profile
└── requirements.txt
```

---

## Trust model

```
Real user (UID 1000, user.slice)
  │  Physical keyboard → evdev → input_tagger.py → HMAC stamp
  │  Only HMAC-stamped events carry source="HUMAN"
  │
  ▼
Intent → ContextFirewall (strips injection from external content)
  │
  ▼
Planner (local LLM — sees filtered context only, never HMAC keys)
  │
  ▼
Supervisor (rate limit · loop detect · session budget · fail counter)
  │
  ▼
ChannelGuard (blocks AI input to auth dialogs, validates terminal commands)
  │
  ▼
RealWorldBarrier (payment/order/message: preview + HMAC-verified confirm)
  │
  ▼
ConfirmationGate (AUTO · NOTIFY · CONFIRM · BLOCK)
  │
  ▼
Executor (DBus proxy → AT-SPI filtered → ydotool broker → bwrap sandbox)
  │
  ▼
Btrfs snapshot + Merkle event log
  │
  ▼
Debian base + TPM 2.0 + AppArmor + auditd
```

---

## The four gaps fixed (v6)

| Gap | Problem | Fix |
|-----|---------|-----|
| 1 | AI types into terminal → indirect privilege escalation | `channel_guard.py`: blocks dangerous terminal commands, blocks all input to auth dialogs |
| 2 | AI loops → spam 1000 tabs, infinite clicks | `supervisor.py`: rate limiter + exact loop + near-loop + session budget + fail counter |
| 3 | Payment/order forms filled before user sees them | `real_world.py`: preview → lock → HMAC-verified confirm before any form submission |
| 4 | Cognitive + operational memory combined at inference | `context_firewall.py`: strips command patterns, paths, injection strings before planning context |

---

## Security properties

- UID 1001 cannot escalate to UID 1000 (no shared cgroup, no sudo rules for agent)
- Every AI syscall tagged in auditd: `ausearch -k ai-agent-exec`
- HMAC session key: root-owned tmpfs, regenerated each boot, never in AI context
- AT-SPI denied for: pinentry, polkit, gnome-keyring, keepassxc, bitwarden
- AppArmor denies: /dev/uinput, /etc/shadow, /etc/sudoers, /root/, kernel tunables
- systemd: NoNewPrivileges, ProtectSystem=strict, PrivateDevices, CapabilityBoundingSet=
- bwrap: --unshare-net on all terminal commands (explicit grant required for network)
- Supervisor hard-pauses on 5 consecutive failures (not just rate limiting)
- Context firewall blocks prompt injection even in signed memory entries

---

## Installation

### Requirements
- Debian 12+ or Ubuntu 24.04+ (x86_64 or ARM64)
- Python 3.11+
- 3GB RAM minimum (low_ram.yaml), 8GB recommended (default.yaml)
- Btrfs root filesystem + snapper configured
- AppArmor enabled (default on Debian)

### Quick start

```bash
# 1. Clone and enter
git clone https://github.com/yourname/ai-os
cd ai-os

# 2. Run setup (creates UID 1001, AppArmor, audit rules, systemd units)
sudo bash setup.sh

# 3. Download a model
# Full (7B, needs 8GB RAM):
wget -P /opt/ai-os/models/ \
  https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.3-GGUF/resolve/main/mistral-7b-instruct-v0.3.Q4_K_M.gguf

# Low RAM (3.8B, needs 3GB):
wget -P /opt/ai-os/models/ \
  https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf

# 4. Install Python deps (in venv)
sudo -u ai-agent python3 -m venv /opt/ai-os/venv
sudo -u ai-agent /opt/ai-os/venv/bin/pip install -r requirements.txt
apt install python3-pyatspi   # AT-SPI (system package)

# 5. Start services
sudo systemctl enable --now ai-input-tagger
sudo systemctl enable --now ai-agent

# 6. Verify
sudo systemctl status ai-agent
sudo journalctl -u ai-agent -f

# 7. Send a test command
echo '{"text":"open VS Code","source":"HUMAN"}' | \
  socat - UNIX-CONNECT:/run/ai-os/agent.sock
```

### For 3–4GB RAM devices

```bash
# Use low_ram.yaml instead of default.yaml
sudo systemctl edit ai-agent --force
# Add: Environment=AI_OS_CONFIG=config/low_ram.yaml
```

---

## Panic / emergency stop

Any of these immediately kills the AI agent and optionally rolls back:

```bash
# Keyboard shortcut (configure in your DE)
sudo systemctl stop ai-agent

# Or the panic alias (add to ~/.bashrc)
alias panic-ai='sudo systemctl stop ai-agent && sudo snapper rollback'
```

The `Ctrl+Alt+Shift+R` shortcut can be bound in your DE's keyboard settings
to run `sudo systemctl stop ai-agent`.

---

## Next development priorities

1. `dbus_proxy.py` — DBus proxy daemon (UID 1000 side, method whitelist)
2. `ui_server.py` — WebSocket server for the chat/voice sidebar
3. `ebpf_supervisor/` — Kernel-level supervisor (Rust + eBPF, out-of-process)
4. Merkle event log implementation (currently in-memory only)
5. Model quantization scripts for on-device fine-tuning (Malayalam, Hindi support)

---

## Added in v6 final

| File | What it does |
|------|-------------|
| `execution/dbus_proxy.py` | Runs as UID 1000, bridges to UID 1001 via socket with strict method whitelist. The fundamental fix for app control on Wayland. |
| `ui/ui_server.py` | WebSocket server (localhost:8765) bridging browser UI → agent socket. Handles confirmations, notifications, voice audio. |
| `ui/index.html` | Dark-mode chat sidebar. Auto-reconnects, handles confirm dialogs, voice recording, real-world action previews. |
| `systemd/ai-dbus-proxy.service` | User systemd service (UID 1000) for the DBus proxy. |
| `systemd/ai-ui-server.service` | User systemd service (UID 1000) for the UI WebSocket server. |

## Kernel trust boundary decision

The eBPF supervisor shares kernel trust level. This is explicitly accepted as the trust boundary — same as any standard OS (Linux, Windows, macOS). If kernel-level compromise is in scope, the correct solution is running the AI OS as a KVM guest with the hypervisor as the supervisor (Phase 3). For current scope: user-space security is complete and production-grade.

## Start order

```bash
# System services (as root)
sudo systemctl start ai-input-tagger   # evdev watcher — root daemon
sudo systemctl start ai-agent          # AI agent — UID 1001

# User services (as UID 1000, run in your desktop session)
systemctl --user start ai-dbus-proxy   # D-Bus bridge
systemctl --user start ai-ui-server    # WebSocket + UI

# Open the chat UI
xdg-open http://localhost:8765/ui/index.html
# OR: just open ai-os/ui/index.html directly in your browser
```
