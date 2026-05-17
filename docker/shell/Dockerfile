# syntax=docker/dockerfile:1
#
# Shell-instance base image — dos-arch substrate.
# ONE image; every shell container runs from it. All deps baked, never
# mounted from the host. Built + run rootless under the dos-arch service
# user on the Arch host.
#
#   Build:  docker build -t dos-shell:latest docker/shell/
#   Verify: docker run --rm dos-shell:latest claude --version
#
# Pin Claude Code for a reproducible image:
#   docker build --build-arg CLAUDE_VERSION=2.1.89 -t dos-shell:latest docker/shell/

FROM debian:bookworm-slim

# ── baked dependencies ───────────────────────────────────────────────────────
#   git / openssh-client / gh : repo work over SSH + GitHub
#   ca-certificates / curl    : TLS + the Claude Code native installer
#   tzdata                    : correct wall-clock for session narratives
#   tini                      : PID 1 — reaps zombies, forwards signals
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl git openssh-client tzdata tini \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
 && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends gh \
 && rm -rf /var/lib/apt/lists/*

# ── runs as container-root — deliberately, no USER directive ─────────────────
# Under rootless Docker, container-root maps to the unprivileged `dos-arch`
# host user — the account that owns the bind-mounted /workspace. A non-root
# container user maps instead to a subuid with no write access to that mount,
# so `claude` could not write its own workspace. `dos-api`'s image makes the
# same choice for the same reason. "Rootless" already means container-root is
# an unprivileged host account — that is the sandbox boundary.
#
# (A `SHELL_UID`/`SHELL_GID` build-arg approach was considered and dropped:
# under rootless, only container-uid-0 maps to the host `dos-arch` user;
# numerically matching a non-root container uid to it does not make them the
# same identity.)

# ── Claude Code (native installer — self-contained binary, no Node) ──────────
# CLAUDE_VERSION: "stable", "latest", or a pinned version (e.g. 2.1.89).
ARG CLAUDE_VERSION=stable
# The installer keys off $HOME to place ~/.local/bin; pin it to root's home.
ENV HOME=/root
WORKDIR /tmp
RUN curl -fsSL https://claude.ai/install.sh | bash -s "${CLAUDE_VERSION}"

ENV PATH="/root/.local/bin:${PATH}"
# Locked image — no background auto-update, no manual update. The baked
# version stays put; rebuild the image to move it.
ENV DISABLE_AUTOUPDATER=1 \
    DISABLE_UPDATES=1

# Offline sanity check — fails the build if the binary is missing/broken.
RUN claude --version

# ── credential-broker wiring (non-secret) ────────────────────────────────────
# git — every github.com URL is rewritten to the broker's /gh route; the
# broker (its own container, dos-broker, on dos-net) injects the token. No
# credential enters the image, no host loopback — standard container-to-
# container. Baked in because every shell uses brokered git.
#
# Anthropic auth is deliberately NOT baked. The launcher sets it per
# container: CLI shells browser-auth (subscription) with no Anthropic env at
# all; API shells get ANTHROPIC_BASE_URL pointed at the broker's /anthropic
# route. Baking a key here would force every shell into API mode.
RUN git config --global url."http://dos-broker:8788/gh/".insteadOf \
        "https://github.com/" \
 && git config --global url."http://dos-broker:8788/ghcodeload/".insteadOf \
        "https://codeload.github.com/"

# Substrate API (memory) — the dos-api container on dos-net, reached by DNS.
# Non-secret URL; the per-render API token arrives as $DOS_API_TOKEN at
# `docker exec` time, never baked into the image.
ENV DOS_API_URL="http://dos-api:8000"

# ── runtime ──────────────────────────────────────────────────────────────────
# Persistent container: `tini -- sleep infinity` holds it open; the
# orchestrator attaches a session with `docker exec -it shell-<name> claude`
# (wired up in Phase 3). The container must be run with `--network dos-net`
# so `dos-broker` resolves.
WORKDIR /workspace
ENTRYPOINT ["tini", "--"]
CMD ["sleep", "infinity"]
