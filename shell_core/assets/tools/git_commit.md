---
name: git_commit
description: Commit staged changes with a message.
kind: builtin
handler: git.commit
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "cwd": {
      "type": "string",
      "description": "repository working directory"
    },
    "message": {
      "type": "string",
      "description": "commit message"
    },
    "stage_all": {
      "type": "boolean",
      "description": "stage every change before committing"
    }
  },
  "required": [
    "cwd",
    "message"
  ]
}

<!-- @@ PROMPT @@ -->
### git_commit — commit staged changes

**use when:** recording staged changes. With `stage_all: true`, every modified tracked file is staged first (does not pick up untracked files). Skip the call entirely if there is nothing to commit.

**args (model fills):**
- `cwd` (string, required) — repository working directory.
- `message` (string, required) — commit message. One headline line, blank line, then body if needed.
- `stage_all` (boolean, optional) — `git add -u` before committing. Default false.

**example:** commit a focused change

  <tool:git_commit>{"cwd":"~/dos-arch","message":"feat(tools): per-tool prompt_block\n\nEach tool now carries its own TOOLS-section block."}</tool>
