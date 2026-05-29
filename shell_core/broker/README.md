# Credential broker

Egress reverse proxy. Shell containers route outbound requests for
authenticated services through the broker; it holds every secret and
injects auth on the way out. Shell containers stay **credential-free** — a
prompt-injected shell has nothing to steal.

The broker runs as its **own container** (`dos-broker`), built from its
own image — the trusted, secret-holding container, strictly separate from
shell containers. It is never baked into the shell image: that would put
secrets back inside a shell container and lose the credential-free
property.

## Topology

Both the broker and every shell container join a user-defined Docker
network, `dos-net`. Shell containers reach the broker by Docker DNS name —
`http://dos-broker:8788` — standard container-to-container networking. No
host loopback, no Unix socket, no shim.

```
  dos-net  ┌─────────────┐        ┌──────────────┐
           │ shell-<name>│──HTTP─▶│  dos-broker  │──HTTPS─▶ internet
           │ (no secrets)│  :8788 │ (holds keys) │
           └─────────────┘        └──────────────┘
```

## Routes

| Prefix | Upstream | Injects |
|---|---|---|
| `/anthropic/…`    | `api.anthropic.com` | `x-api-key` |
| `/openai/…`       | `api.openai.com`    | `Authorization: Bearer` |
| `/ollama_cloud/…` | `ollama.com`        | `Authorization: Bearer` |
| `/gh/…`         | `github.com`          | `Authorization` (git over HTTPS) |
| `/ghcodeload/…` | `codeload.github.com` | `Authorization` |

`gh` CLI (the GitHub *API*) is a fast-follow — a `/ghapi` route — once the
core proxy is proven.

## Secrets

Read once at startup from the **process environment** — supplied at
`docker run` via `--env-file`, never baked into the image:

    ANTHROPIC_API_KEY=...
    GITHUB_TOKEN=...

`broker-up.sh` passes the repo-root `.env`. Re-run it after editing `.env`.

## Run

    ./install/build-image.sh      # builds dos-shell + dos-broker
    ./install/broker-up.sh        # creates dos-net, (re)starts dos-broker

`broker-up.sh` also runs a health check from a throwaway container on
`dos-net`. Manual check, same idea:

    docker run --rm --network dos-net --entrypoint python dos-broker:latest \
      -c "import urllib.request as u; \
          print(u.urlopen('http://dos-broker:8788/health').read().decode())"

## How shell containers use it

The shell image bakes the broker wiring (non-secret) — no token ever
enters a shell container. A shell container must be run with
`--network dos-net` so the name `dos-broker` resolves:

- **Anthropic** — set per container by the launcher, not baked into the
  image: API shells get `ANTHROPIC_BASE_URL=http://dos-broker:8788/anthropic`;
  CLI shells get no Anthropic env and browser-auth. See *Anthropic auth — by
  shell type* below.
- **git** — `git config --global url."http://dos-broker:8788/gh/".insteadOf
  "https://github.com/"`; every github URL is transparently rewritten.

## Anthropic auth — by shell type

How a shell reaches Anthropic depends on its type:

- **CLI shells** (interactive Claude Code) may authenticate by **browser
  login** — the auth picker shown when `claude` launches. Credentials
  persist in the per-shell container; usage bills against the Claude
  subscription, not the API. These shells bypass the broker's `/anthropic`
  route.
- **Any shell that exposes a web-app interface** must authenticate via the
  **API** — the broker's `/anthropic` route with the injected
  `ANTHROPIC_API_KEY`. Per Anthropic's Terms of Service, subscription
  (browser) auth is for personal CLI use and may not back a web app.

A browser-authed CLI shell holds its own subscription credentials
in-container, so for the Anthropic leg it is not credential-free — a
deliberate cost trade-off scoped to CLI shells. The broker still brokers
git for every shell.

## Notes

- Reverse proxy, not TLS-intercepting (MITM): no CA key, no certs in the
  caller. caller→broker is plain HTTP on `dos-net`; broker→internet is
  HTTPS.
- The broker stops credential *theft*, not capability *misuse*. The route
  table is the allowlist; per-shell scoping is Phase 5.
- The broker container is trusted and holds secrets — keep shell containers
  off any path that could `docker exec` into it. Under rootless Docker a
  shell container has no Docker socket, so it cannot; Phase 5's manifest
  keeps it that way.
