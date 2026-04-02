# Architecture

## Runtime Flow

```
Voice / Chat / UI (browser)
        ↓
input_tagger.py       ← HMAC-stamps real keypresses (root daemon)
        ↓
context_firewall.py   ← strips prompt injection from memory
        ↓
intent_parser.py      ← classifies: chat / app / system / real-world
        ↓
planner_ollama.py     ← local LLM produces structured action plan (JSON)
        ↓
secondary_validator.py← INDEPENDENT rule-based high-risk check
        ↓
supervisor.py         ← rate limiter + loop detector + session budget
        ↓
channel_guard.py      ← blocks AI input to auth/payment dialogs
        ↓
confirm_gate.py       ← AUTO / NOTIFY / CONFIRM / BLOCK
        ↓  (real-world → real_world.py barrier first)
executor.py           ← DBus → AT-SPI → ydotool  |  bwrap sandbox
        ↓
snapshot.py           ← Btrfs snapshot + Merkle audit log
        ↓
Debian base           ← AppArmor + auditd + TPM
```

## 6 Layers

| Layer | Files | Purpose |
|-------|-------|---------|
| Base OS | install/ | Debian, Btrfs, users, desktop |
| Security | security/ | 6 guard layers, audit log |
| AI Brain | core/ | planner, memory, firewall |
| Execution | execution/ | GUI + shell + real-world |
| UI | ui/ | chat sidebar, WebSocket |
| Recovery | recovery/ | snapshots, rollback, panic |

## User Identity Separation

| UID | Role | Permissions |
|-----|------|-------------|
| 1000 | Human user | Full authority |
| 1001 | AI user | AppArmor + bwrap constrained |
| recovery | Recovery user | Read-only immutable model only |
