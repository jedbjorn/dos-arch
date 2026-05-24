---
name: git_push
description: Push commits to upstream.
kind: builtin
handler: git.push
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "cwd": {
      "type": "string",
      "description": "repository working directory"
    },
    "force": {
      "type": "boolean",
      "description": "force-with-lease the push"
    }
  },
  "required": [
    "cwd"
  ]
}

<!-- @@ PROMPT @@ -->
### git_push — push to upstream

**use when:** publishing local commits. Force is `--force-with-lease` only; **confirm with the operator before any force push**, and never force-push `main`/`master`.

**args (model fills):**
- `cwd` (string, required) — repository working directory.
- `force` (boolean, optional) — `--force-with-lease`. Default false.

**example:** push a feature branch

  <tool:git_push>{"cwd":"~/dos-arch"}</tool>
