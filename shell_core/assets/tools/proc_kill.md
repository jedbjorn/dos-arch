---
name: proc_kill
description: Send a signal to a process. Destructive.
kind: builtin
handler: proc.kill
---
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
