---
name: exec_bg
description: Run a command in the background. Returns its pid.
kind: builtin
handler: proc.exec_bg
---
{
  "type": "object",
  "properties": {
    "argv": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "command and arguments as a list, no shell"
    },
    "cwd": {
      "type": "string",
      "description": "working directory, defaults to the dispatcher cwd"
    }
  },
  "required": [
    "argv"
  ]
}
