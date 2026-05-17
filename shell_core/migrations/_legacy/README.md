# Legacy migrations

Pre-runner historical migrations (`001`–`009`), kept for the record only.

`migrate.py` discovers migrations with `glob("*.sql")` at the top level of
`shell_core/migrations/` — it does **not** descend into this directory and
does **not** run `.py` files. These predate the SQL-based runner.

Their schema changes are already baked into `schema.sql` (which builds a
fresh DB) and into every live database, so nothing here needs to run again.

**Writing a new migration?** Add a `NNN_name.sql` file in the parent
`migrations/` directory — not here, and not as `.py`.
