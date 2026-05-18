# Contributing to dos-arch

Thanks for your interest in contributing. `dos-arch` is a shell-infrastructure
substrate — it stays deliberately minimal, so the bar for new surface area is
"does the substrate genuinely need this," not "is this a nice feature."

## Ground rules

- **`main` is protected.** Every change lands through a pull request — no
  direct pushes, no force-pushes. The maintainer reviews and merges.
- **One change per PR.** Keep PRs focused; a reviewer should be able to hold
  the whole diff in their head.
- **Discuss first for anything large.** Open an issue before starting work
  that adds a dependency, changes the schema, or reshapes the install flow.

## Development setup

Clone the repo (you need your own GitHub access — it is your clone to own):

```bash
git clone git@github.com:jedbjorn/dos-arch.git && cd dos-arch
make install      # .venv + UI deps
make bootstrap    # create the substrate DB, seed it, create the first user
make up           # start api + ui
```

For the dockerized rootless substrate (service user, rootless Docker, the
broker/api/shell images), follow [`install/README.md`](install/README.md)
end to end.

## Workflow

1. Branch off `main` — `fix/...`, `feat/...`, `refactor/...`, `docs/...`.
2. Make the change. Match the style of the surrounding code.
3. **Smoke-test it.** A syntactically valid script or config can still do
   nothing — run the thing that consumes your change and verify real
   behavior, not just that the file parses.
4. Commit with a [Conventional Commits](https://www.conventionalcommits.org/)
   message — e.g. `fix(install): portable shared-dir anchor`.
5. Open a PR. Fill in the template: what changed, why, and how you tested it.
6. The maintainer reviews and **squash-merges** — your branch is deleted
   automatically. Keep your branch; rebase on `main` if review takes a while.

## Conventions

- **One source of truth.** Pointers everywhere else — duplication is drift
  waiting to happen.
- **Secrets never touch the repo.** `.env` is gitignored and holds real
  credentials; never commit it, never paste keys into issues or PRs. See
  [`SECURITY.md`](SECURITY.md).
- **Substrate stays minimal.** Project-specific memory patterns, extra
  routers, and UI surface belong in a clone, not here.

By contributing you agree your contributions are licensed under the
repository's [MIT License](LICENSE).
