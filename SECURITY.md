# Security Policy

## Supported versions

`dos-arch` is developed on `main`. Security fixes land on `main`; there are no
separately maintained release branches. Run a recent `main` to stay current.

## Reporting a vulnerability

**Do not open a public issue for security problems.**

Report privately through GitHub's **Private Vulnerability Reporting**:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability**.
3. Describe the issue, the impact, and steps to reproduce.

This opens a private advisory visible only to you and the maintainers. You can
expect an initial acknowledgement within a few days; the fix timeline depends
on severity and complexity, and we will keep you updated on the advisory thread.

## Scope and handling notes

The substrate handles credentials directly:

- The credential broker reads `ANTHROPIC_API_KEY` and `GITHUB_TOKEN` from a
  repo-root `.env`. That file is gitignored and **must never be committed** —
  if you find a leaked key in history or in an issue/PR, treat it as an
  incident: report it privately and rotate the key.
- The launcher stores scrypt-hashed passwords in the substrate DB
  (`shell_db.db`), which is gitignored and local-only.
- Diagnostic commands that *render* config (e.g. `docker compose config`) can
  echo secrets to stdout — and into logs or transcripts. Be careful what you
  paste into a report.

When in doubt about whether something is a security issue, report it privately
and let the maintainers triage.
