---
name: git_log
description: Show recent commits of a repository.
kind: builtin
handler: git.log
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "cwd": {
      "type": "string",
      "description": "repository working directory"
    },
    "n": {
      "type": "integer",
      "description": "number of commits, defaults to 10"
    },
    "path": {
      "type": "string",
      "description": "limit the log to this path"
    }
  },
  "required": [
    "cwd"
  ]
}

<!-- @@ PROMPT @@ -->
### git_log — show recent commits

**use when:** scanning the recent commit history of a repo, optionally scoped to a path.

**args (model fills):**
- `cwd` (string, required) — repository working directory.
- `n` (integer, optional) — number of commits. Defaults to 10.
- `path` (string, optional) — limit the log to this path.

**example:** last 5 commits touching a file

  <tool:git_log>{"cwd":"~/dos-arch","n":5,"path":"shell_core/shell_render.py"}</tool>
