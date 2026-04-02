# Security Model

## Identity Separation
- **UID 1000** — Human user. Absolute authority. Cannot be overridden by AI.
- **UID 1001** — AI user. AppArmor-constrained. No sudo. Cannot write to /etc, /home/user, /root.
- **Recovery user** — Separate account. Read-only immutable recovery model only.

## 6 Guard Layers

### 1. Input Tagger (`security/input_tagger.py`)
- Runs as root daemon watching /dev/input via evdev
- HMAC-stamps every real keypress/click with a secret key
- AI-generated input is never trusted as human input

### 2. Context Firewall (`core/context_firewall.py`)
- Runs before every inference pass
- Strips: shell commands, file paths, system directives, injected content
- Prevents prompt injection via files, web pages, or memory

### 3. Supervisor (`security/supervisor.py`)
- Hard rate limit: max 30 actions/minute
- Per-session action budget: max 200 actions/session
- Loop detector: halts AI if same action repeats 3× in 60s
- Notifies user and pauses AI if any limit is hit

### 4. Channel Guard (`security/channel_guard.py`)
- Monitors active window via AT-SPI
- Blocks all AI keyboard/click input if window is: sudo dialog, polkit, login screen, payment form, password field
- Validates terminal commands against a deny list

### 5. Confirmation Gate (`security/confirm_gate.py`)
Policy by risk score:
| Score | Mode | Behaviour |
|-------|------|-----------|
| 0–2 | AUTO | Execute silently, log |
| 3–4 | NOTIFY | Show banner, execute after 3s |
| 5–7 | CONFIRM | Show dialog, wait for user YES |
| 8–10 | BLOCK | Refuse, explain why |

### 6. Real-World Barrier (`execution/real_world.py`)
- Non-bypassable extra CONFIRM gate for payments/orders/messages
- Requires explicit user interaction (button press, not just timeout)
- Shows full action preview before any external action

## Secondary Validator (gap fix)
`security/secondary_validator.py` — independent rule-based check that runs after the LLM planner but before the gate. Does NOT use the LLM. Uses deterministic rules only.

## Learning Guard (gap fix)
`security/learning_guard.py` — every write to the memory DB is cryptographically signed and verified. Unsigned or malformed entries are rejected and flagged.

## Formal Tool Contracts
Every tool in the execution layer defines:
- `preconditions` — must be true before running
- `postconditions` — verified after running
- `risk_score` — 0-10 integer, determines gate policy
- `rollback` — mandatory for risk ≥ 5

## Confirmation policy — always CONFIRM
- Payments
- Orders
- Messaging
- sudo-like operations
- Destructive filesystem changes
- Auth dialogs

## Audit Log
- All events written to `audit_log.py` Merkle chain
- Tamper-evident: each entry hashes the previous entry
- Stored at: `/var/log/ai-os/audit.db`
