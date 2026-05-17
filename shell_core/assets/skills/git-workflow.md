---
name: git-workflow
description: Identity-prefix env vars, stacked-PR retarget rule, squash-merge default, cleanup pattern. Self-bootstraps creds (Name, Email, auth) into shells.connections on first invocation.
category: workflow
common: 1
---
# git-workflow

- **category:** workflow
- **description:** Identity-prefix env vars, stacked-PR retarget rule, squash-merge default, cleanup pattern. Self-bootstraps creds on first invocation.

Cross-reference: `~/.claude/CLAUDE.md` "Committing changes with git" + "Executing actions with care" hold the safety rules and Co-Authored-By trailer requirement — don't repeat them, follow them.

---

## First-run: identity bootstrap

Before using git, this skill needs three things from the operator. Check
`shells.connections` for this shell — look for a `## Git` section. If
present, use those values. If absent, ask the FnB:

1. **Name** for `GIT_AUTHOR_NAME` / `GIT_COMMITTER_NAME` (e.g. `jdoe`).
2. **Email** for `GIT_AUTHOR_EMAIL` / `GIT_COMMITTER_EMAIL`.
3. **Auth method** for pushing — one of:
   - `ssh` (SSH key on `$HOME/.ssh/`, remote URLs use `git@github.com:…`)
   - `gh` (GitHub CLI handles auth; remotes can be HTTPS)
   - `https-pat` (personal access token, stored in a credential helper)

UPDATE `shells.connections` to add or refresh a `## Git` section:

```markdown
## Git

- Name: <name>
- Email: <email>
- Auth: <ssh | gh | https-pat>
- Default merge: squash + delete branch
```

Subsequent invocations read from there. No re-interview unless the FnB
explicitly asks to update.

---

## Identity prefix

Claude Code's system protocol forbids `git config` updates. Shell state
doesn't persist between Bash tool calls either. Inline env vars on every
git command that creates a commit (commit, rebase, cherry-pick, merge):

```
GIT_AUTHOR_NAME="<name>" GIT_AUTHOR_EMAIL="<email>" \
GIT_COMMITTER_NAME="<name>" GIT_COMMITTER_EMAIL="<email>" \
git commit -m "..."
```

Both `AUTHOR` and `COMMITTER` env vars are required — `COMMITTER` falls back
to git config (unset) without them, and the command fails. Below this is
the **identity prefix**.

---

## Branch + commit

- Branch from main: short, kebab-case slug (e.g. `flag-search-spec`,
  `boot-arch-laws-to-flat-file`). Match the repo's existing branch style;
  check with `git log --oneline -10` if unsure.
- Commit subject: match the repo's recent log style — `feat(scope): …`,
  `fix: …`, `chore: …`, or plain prose, depending. Inspect with
  `git log --oneline -20`.
- Body via heredoc; include the `Co-Authored-By` trailer per `~/.claude/CLAUDE.md`.

---

## PR creation

`gh pr create --title "..." --body "..."` with body via heredoc.

Keep descriptions concise — the diff is the *what*, the body is the *why*.
A tight paragraph or a Summary + Test plan checklist (per Claude Code's
default template) both work; match the repo. Avoid duplicating the commit
message into the PR body.

```
gh pr create --title "..." --body "$(cat <<'EOF'
<one paragraph on motivation + user-facing change>
EOF
)"
```

---

## Multi-remote repos: pin `gh`'s default

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

---

## Untracking a tracked file — snapshot first

`git rm --cached <file>` + commit + pull removes the file from the working
tree on every fast-forward, even after `.gitignore` lists it. Gitignore
only governs *untracked* files; once a deletion is in the commit graph,
git applies it on checkout regardless.

Failure mode: you want to keep a local-only file (DB, secret store,
generated artifact) but stop tracking it. After the merge lands, `git pull`
deletes the local copy. A subsequent tool that opens the path
(e.g. `sqlite3.connect()`) silently re-creates it as empty, masking the
data loss.

**Before** `git rm --cached` on a binary or stateful file:

1. Snapshot it (`make db-backup` for the DB, or `cp` for anything else).
2. Commit + push + merge as usual.
3. Immediately after `git pull` on main, verify the local file's size is
   non-zero. If it's gone or empty, restore from the snapshot **before**
   any tool can touch the path.

This applies when you want to *keep locally* but *stop tracking* — not to
true deletions where the file should be gone everywhere.

## Stacked PRs — retarget before merge

When PR B depends on PR A (B's base ≠ main), retarget B **before** merging A:

```
gh pr edit <B> --base main          # do this first
gh pr merge <A> --squash --delete-branch
gh pr merge <B> --squash --delete-branch
```

Why: merging a PR with `--delete-branch` removes the head branch, which is
the base ref of any stacked PR. GitHub then closes the stacked PR
(`state=CLOSED`, `mergeable=CONFLICTING`) and blocks reopen because the base
ref is gone. Recovery requires a local rebase + force-push + a fresh PR —
costs ~5k tokens of context churn and can dump file contents into the
conversation through system-reminders.

If the retarget step gets skipped, recovery rebase (using the **identity prefix**):

```
<identity-prefix> git rebase --onto origin/main <sha-of-last-dep-commit>
git push --force-with-lease
gh pr create --base main ...
```

---

## Merge

```
gh pr merge <n> --squash --delete-branch
```

Squash matches the convention on most repos — one squash per PR with
`(#n)` appended (auto-applied by `gh pr merge --squash`). Override per
project if the repo prefers merge commits or rebase-merges.

---

## Verify + cleanup

After merging, confirm with `git log --oneline -N` (cheap). **Do not** use
`git show --stat` for routine confirmation — it echoes the full commit body
(~1k tokens of waste).

```
git fetch origin
git log --oneline origin/main -6
```

After all PRs in a batch land:

```
git checkout main
git pull --ff-only
git fetch --prune                  # drops stale remote-tracking refs
```

If services need a restart to pick up backend changes (pm2, systemd,
docker compose, etc.), do that here. The specific service names are
project-specific — check `shells.connections` or the project's
`Makefile`/`ecosystem.config.cjs`.
