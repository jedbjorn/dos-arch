---
name: resolve_flag
description: Resolve an open flag (close it as work-of-record) for the calling shell. shell_id is verified server-side from the bearer token; the route is fixed (PATCH /flags/{flag_id}/resolve). WHEN — the user names a flag and signals it has closed, the blocker has cleared, or the work-of-record concludes. SCOPE — closes one flag at a time and appends resolution_notes; for opening flags use create_flag; for listing open flags use surface_flags; reopening or other status transitions remain on the api_* surface for now. CONVENTION — flag_id identifies the target (confirm via surface_flags if uncertain); resolution_notes is the *how* — what shipped, what was learned, what stays open. Aim for ~60-200 characters of substantive content; "done" or "resolved" alone is too thin to be useful.
kind: builtin
handler: flag.resolve
---
{
  "type": "object",
  "required": ["flag_id", "resolution_notes", "status"],
  "properties": {
    "flag_id": {
      "type": "integer",
      "minimum": 1,
      "description": "Flag ID. Required. Positive integer flag_id of the open flag to close. Confirm via surface_flags if uncertain; the user names the flag, you map it to the id."
    },
    "resolution_notes": {
      "type": "string",
      "maxLength": 400,
      "description": "Resolution notes. Required. Aim for ~60-200 characters of substantive content — capture *how* the flag closed: what shipped, what was learned, what stays open. Avoid 'done' or 'resolved' alone; the row is the durable record. Derived from the work that just landed; if context is thin, ask FnB rather than write a stub."
    },
    "status": {
      "type": "integer",
      "enum": [1],
      "default": 1,
      "description": "Status code. Required. Always 1 (= resolved) for this tool — the API endpoint accepts other values but this tool is purpose-built for closing flags. Pass 1 verbatim; do not vary."
    }
  }
}
