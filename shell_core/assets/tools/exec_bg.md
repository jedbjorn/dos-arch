---
name: exec_bg
description: Run a command in the background. Returns its pid.
kind: builtin
handler: proc.exec_bg
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
    }
  },
  "required": [
    "argv"
  ]
}

<!-- @@ PROMPT @@ -->
### exec_bg — run a command in the background

**use when:** starting a long-lived process and continuing without waiting. Returns the pid; use `proc_check` to see if it is alive, `proc_kill` to stop it. For one-shot work, use `exec`.

**args (model fills):**
- `argv` (array of strings, required) — `[program, arg1, arg2, ...]`. Not a shell line.
- `cwd` (string, optional) — working directory. Defaults to the dispatcher cwd.

**example:** start a server in the background

  <tool:exec_bg>{"argv":["python3","-m","http.server","8088"],"cwd":"~/scratch"}</tool>
