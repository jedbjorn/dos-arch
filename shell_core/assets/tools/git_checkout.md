---
name: git_checkout
description: Switch to a branch, or create one.
kind: builtin
handler: git.checkout
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "cwd": {
      "type": "string",
      "description": "repository working directory"
    },
    "branch": {
      "type": "string",
      "description": "branch name"
    },
    "create": {
      "type": "boolean",
      "description": "create the branch before switching"
    }
  },
  "required": [
    "cwd",
    "branch"
  ]
}

<!-- @@ PROMPT @@ -->
### git_checkout — switch to a branch (optionally create it)

**use when:** moving HEAD to another branch, or starting a new branch off the current one (`create: true`). Verify a clean working tree first; the checkout will refuse to clobber unstaged changes.

**args (model fills):**
- `cwd` (string, required) — repository working directory.
- `branch` (string, required) — branch name.
- `create` (boolean, optional) — create the branch first. Default false.

**example:** start a new feature branch

  <tool:git_checkout>{"cwd":"~/dos-arch","branch":"feat/tool-prompt-blocks","create":true}</tool>
