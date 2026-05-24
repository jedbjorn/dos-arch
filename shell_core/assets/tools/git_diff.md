---
name: git_diff
description: Show the diff of a repository, working tree or staged.
kind: builtin
handler: git.diff
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "cwd": {
      "type": "string",
      "description": "repository working directory"
    },
    "staged": {
      "type": "boolean",
      "description": "show the staged diff instead of the working tree"
    },
    "path": {
      "type": "string",
      "description": "limit the diff to this path"
    }
  },
  "required": [
    "cwd"
  ]
}

<!-- @@ PROMPT @@ -->
### git_diff — show repo diff

**use when:** inspecting unstaged or staged changes before committing. `staged: true` mirrors `git diff --cached`.

**args (model fills):**
- `cwd` (string, required) — repository working directory.
- `staged` (boolean, optional) — show the staged diff instead of the working tree. Default false.
- `path` (string, optional) — limit the diff to this path.

**example:** see staged changes scoped to one file

  <tool:git_diff>{"cwd":"~/dos-arch","staged":true,"path":"shell_core/shell_render.py"}</tool>
