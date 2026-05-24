---
name: git_pull
description: Pull from upstream. Fast-forward only by default.
kind: builtin
handler: git.pull
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "cwd": {
      "type": "string",
      "description": "repository working directory"
    },
    "rebase": {
      "type": "boolean",
      "description": "rebase instead of fast-forward"
    }
  },
  "required": [
    "cwd"
  ]
}

<!-- @@ PROMPT @@ -->
### git_pull — pull from upstream

**use when:** syncing the current branch with its upstream. Fast-forward only by default; set `rebase: true` to rebase local commits on top of upstream instead.

**args (model fills):**
- `cwd` (string, required) — repository working directory.
- `rebase` (boolean, optional) — rebase instead of fast-forward. Default false.

**example:** pull main forward

  <tool:git_pull>{"cwd":"~/dos-arch"}</tool>
