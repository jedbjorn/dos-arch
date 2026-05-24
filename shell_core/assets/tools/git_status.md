---
name: git_status
description: Show the working-tree status of a repository.
kind: builtin
handler: git.status
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "cwd": {
      "type": "string",
      "description": "repository working directory"
    }
  },
  "required": [
    "cwd"
  ]
}

<!-- @@ PROMPT @@ -->
### git_status — show working-tree status

**use when:** checking what is modified, staged, or untracked in a repo before staging or committing.

**args (model fills):**
- `cwd` (string, required) — repository working directory.

**example:** check the dos-arch checkout

  <tool:git_status>{"cwd":"~/dos-arch"}</tool>
