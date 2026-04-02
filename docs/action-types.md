# Action Types

Every action in AI OS is one of these types. No raw shell strings allowed.

## Type Table

| Type | Example | Risk Score | Default Gate |
|------|---------|-----------|--------------|
| chat | Answer a question | 0 | AUTO |
| gui_action | Open app, type text, click | 1–3 | AUTO / NOTIFY |
| app_action | Launch VS Code, play music | 2–4 | NOTIFY |
| system_action | Install package, edit config | 5–7 | CONFIRM |
| recovery_action | Rollback snapshot | 7–8 | CONFIRM |
| real_world_action | Pay, order, call | 8–10 | CONFIRM + Real-World Barrier |

## Required Fields Per Action

```json
{
  "action_id": "uuid",
  "type": "system_action",
  "description": "Install package vim",
  "tool": "terminal_tools.apt_install",
  "args": {"package": "vim"},
  "risk_score": 5,
  "preconditions": ["network_available", "not_in_recovery_mode"],
  "postconditions": ["package_installed:vim"],
  "confirmation_required": true,
  "rollback": "terminal_tools.apt_remove",
  "rollback_args": {"package": "vim"},
  "snapshot_before": true
}
```

## Prohibited Patterns
- Raw `os.system()` or `subprocess.run(shell=True)` calls — use `terminal_tools` only
- Writing to `/etc`, `/home/user`, `/root` as AI user
- Any action without a `risk_score`
- Any system/recovery/real_world action without a `rollback` path
