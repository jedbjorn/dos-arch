---
name: proc_check
description: Check whether a process is running.
kind: builtin
handler: proc.check
---
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
