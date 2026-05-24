---
name: git_branch
description: List the local branches of a repository.
kind: builtin
handler: git.branch
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
### git_branch — list local branches

**use when:** seeing what branches exist locally, and which one is current.

**args (model fills):**
- `cwd` (string, required) — repository working directory.

**example:** list local branches

  <tool:git_branch>{"cwd":"~/dos-arch"}</tool>
