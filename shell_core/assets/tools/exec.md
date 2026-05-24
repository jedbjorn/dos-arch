---
name: exec
description: Run a command synchronously and capture its output.
kind: builtin
handler: proc.exec
---
<!-- @@ SPEC @@ -->
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

<!-- @@ PROMPT @@ -->
### exec — run a command and wait for output

**use when:** running a short-to-medium command and using its stdout/stderr. No shell — pass program + args as a list. For a long-running process, use `exec_bg`.

**args (model fills):**
- `argv` (array of strings, required) — `[program, arg1, arg2, ...]`. Not a shell line.
- `cwd` (string, optional) — working directory. Defaults to the dispatcher cwd.
- `timeout` (integer, optional) — seconds before timeout. Ceiling 300.

**example:** run a script and read its output

  <tool:exec>{"argv":["python3","scripts/check.py","--quick"],"cwd":"~/dos-arch","timeout":60}</tool>
