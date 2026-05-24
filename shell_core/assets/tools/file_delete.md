---
name: file_delete
description: Delete a file. Destructive. Refuses a directory.
kind: builtin
handler: file.delete
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "file to delete"
    }
  },
  "required": [
    "path"
  ]
}

<!-- @@ PROMPT @@ -->
### file_delete — delete a file

**use when:** removing a regular file. **Destructive — confirm with the operator before deleting anything you did not yourself just create.** Refuses directories.

**args (model fills):**
- `path` (string, required) — file to delete.

**example:** delete a scratch file you created

  <tool:file_delete>{"path":"~/scratch/draft.tmp"}</tool>
