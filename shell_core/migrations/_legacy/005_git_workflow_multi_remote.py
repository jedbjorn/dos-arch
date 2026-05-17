#!/usr/bin/env python3
"""
Migration 005: extend git-workflow skill with the multi-remote `gh` gotcha.

Project clones often have two remotes (e.g. `origin` = project repo,
`upstream` = substrate). `gh` picks one without `--repo` and not always
the one intended; the failure mode is opaque ("Head sha can't be blank,
No commits between main and <branch>") because gh is silently talking to
the wrong repo. Fix: `gh repo set-default <owner>/<repo>`.

Inserts a `## Multi-remote repos` section into the git-workflow skill
content, between `## PR creation` and `## Stacked PRs`.

Idempotent: skips if the section is already present.

Usage:
    python3 shell_core/migrations/005_git_workflow_multi_remote.py <path-to-db>
"""
import sqlite3
import sys
from pathlib import Path


SECTION_MARKER = "## Multi-remote repos: pin `gh`'s default"

NEW_SECTION = """## Multi-remote repos: pin `gh`'s default

Project clones often have two remotes (e.g. `origin` for the project repo,
`upstream` for the substrate). `gh` picks one when run without `--repo` —
and not always the one you mean. The failure mode is opaque: a PR-create
command returns

```
pull request create failed: GraphQL: Head sha can't be blank,
Base sha can't be blank, No commits between main and <branch>
```

`gh` is silently talking to the wrong repo, sees no diff there, and refuses.

**Detect:** from inside the project, run

```
gh repo view --json nameWithOwner
```

If the result is the *upstream* repo (or any repo other than the project
clone), gh has the wrong default.

**Fix once:**

```
gh repo set-default <owner>/<project>
```

…or pass `--repo <owner>/<project>` on every `gh` command.

The same applies to `gh pr merge`, `gh pr view`, `gh pr edit` — anything
that resolves a PR by branch name. If you skip the set-default, be explicit
on every call.

---

"""

INSERT_BEFORE = "## Stacked PRs — retarget before merge"


def main(db_path):
    db = Path(db_path)
    if not db.exists():
        print(f"ERROR: db not found: {db}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db)
    cur = conn.cursor()
    row = cur.execute(
        "SELECT skill_id, content FROM skills WHERE name='git-workflow'"
    ).fetchone()
    if row is None:
        print(f"[005_git_workflow_multi_remote] {db}: no git-workflow skill found",
              file=sys.stderr)
        conn.close()
        sys.exit(1)

    skill_id, content = row[0], row[1] or ""

    if SECTION_MARKER in content:
        print(f"[005_git_workflow_multi_remote] {db}: section already present, no-op")
        conn.close()
        return

    if INSERT_BEFORE not in content:
        print(f"[005_git_workflow_multi_remote] {db}: insertion anchor not found "
              f"(skill content does not contain {INSERT_BEFORE!r}); aborting "
              f"to avoid clobbering an unfamiliar version", file=sys.stderr)
        conn.close()
        sys.exit(1)

    new_content = content.replace(INSERT_BEFORE, NEW_SECTION + INSERT_BEFORE, 1)

    cur.execute(
        "UPDATE skills SET content=? WHERE skill_id=?",
        (new_content, skill_id),
    )
    conn.commit()
    conn.close()
    print(f"[005_git_workflow_multi_remote] {db}: inserted multi-remote section "
          f"(content {len(content)} → {len(new_content)} chars)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])
