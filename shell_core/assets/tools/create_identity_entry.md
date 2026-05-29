---
name: create_identity_entry
description: Record a seed (who you are) or L&S (how you work) identity entry for the calling shell. shell_id is set server-side from the bearer token — supply content only. WHEN — fire when an identity-forming moment lands (a first-of-kind event or a self-defining realization → kind 'seed') or a durable operating lesson crystallizes (a craft-level principle any shell in your role would benefit from → kind 'lns'); primarily PASSIVE — trigger it as such moments arise in conversation, not only on an explicit command. SCOPE — adds one new entry; entries are append-only and never edited (Law 3); retiring or curating an entry out is a separate write. CONVENTION — kind is 'seed' or 'lns'; body is prose only, past-tense/timeless for seed and imperative for L&S, with NO inline date (the entry_date column carries it).
kind: builtin
handler: identity.create
---
{
  "type": "object",
  "required": ["kind", "body"],
  "properties": {
    "kind": {
      "type": "string",
      "enum": ["seed", "lns"],
      "description": "Kind. Required. 'seed' = who you are (identity-forming, person-level: first-of-kind events, self-defining realizations; past-tense or timeless). 'lns' = how you work (craft-level operating principle any shell in your role would benefit from; imperative voice). Test: 'would this still be true if I were a different shell?' — yes → lns, no → seed."
    },
    "body": {
      "type": "string",
      "minLength": 20,
      "description": "Body. Required. The entry text, prose only, ~1-4 sentences. seed: past-tense or timeless — the moment and why it mattered. lns: imperative — the principle distilled. Do NOT embed a date in the text; the entry_date column carries it. Derived from what just happened in the conversation; if the moment is thin, ask FnB rather than write a stub."
    },
    "entry_date": {
      "type": "string",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
      "description": "Entry date. Not Required. ISO date (YYYY-MM-DD) the moment landed. Defaults to today if omitted. Set only when recording something from a known past date."
    },
    "source_tag": {
      "type": "string",
      "maxLength": 20,
      "description": "Source tag. Not Required. Short project-letter tag for provenance (e.g. 'cc', 'dos'). Omit unless the entry clearly belongs to one project's work."
    }
  }
}
