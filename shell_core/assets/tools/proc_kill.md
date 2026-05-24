---
name: proc_kill
description: Send a signal to a process. Destructive.
kind: builtin
handler: proc.kill
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "pid": {
      "type": "integer",
      "description": "process id to signal"
    },
    "signal": {
      "type": "string",
      "description": "signal name, defaults to SIGTERM"
    }
  },
  "required": [
    "pid"
  ]
}

<!-- @@ PROMPT @@ -->
### proc_kill — signal a process

**use when:** stopping a process you control. **Destructive — confirm with the operator before killing anything you did not yourself start.** Default signal is SIGTERM; SIGKILL only when SIGTERM has been ignored.

**args (model fills):**
- `pid` (integer, required) — process id to signal.
- `signal` (string, optional) — signal name, e.g. `SIGTERM`, `SIGINT`, `SIGKILL`. Defaults to `SIGTERM`.

**example:** ask a backgrounded process to stop cleanly

  <tool:proc_kill>{"pid":12345}</tool>
