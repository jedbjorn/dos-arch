---
name: exec
description: Run a command synchronously and capture its output.
kind: builtin
handler: proc.exec
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
    },
    "timeout": {
      "type": "integer",
      "description": "seconds before timeout, ceiling 300"
    }
  },
  "required": [
    "argv"
  ]
}
