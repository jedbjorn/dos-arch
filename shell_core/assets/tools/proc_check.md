---
name: proc_check
description: Check whether a process is running.
kind: builtin
handler: proc.check
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "pid": {
      "type": "integer",
      "description": "process id to check"
    }
  },
  "required": [
    "pid"
  ]
}

<!-- @@ PROMPT @@ -->
### proc_check — check if a pid is alive

**use when:** verifying that a process you started (typically via `exec_bg`) is still running.

**args (model fills):**
- `pid` (integer, required) — process id to check.

**example:** check on a backgrounded process

  <tool:proc_check>{"pid":12345}</tool>
