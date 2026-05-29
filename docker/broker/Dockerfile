# syntax=docker/dockerfile:1
#
# Credential-broker image — dos-arch substrate.
# The broker runs as its OWN container (`dos-broker`) on the shared
# `dos-net` network: the trusted, secret-holding container, strictly
# separate from shell containers. Shell containers reach it by Docker DNS
# name. Never baked into the shell image — that would put secrets back
# inside a shell container and lose the credential-free property.
#
# Build context is shell_core/broker/ (where broker.py + requirements live):
#   docker build -f docker/broker/Dockerfile -t dos-broker:latest shell_core/broker/
#
# Run — secrets supplied at runtime via --env-file, never baked:
#   docker run -d --name dos-broker --network dos-net \
#     --env-file .env --restart unless-stopped dos-broker:latest

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ── dependencies (pinned — see requirements.txt) ─────────────────────────────
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
 && rm /tmp/requirements.txt

# ── broker code ──────────────────────────────────────────────────────────────
# Code only — no secrets. As of Phase 1 the broker owns an envelope-encrypted
# secret store (secrets_store.py); the KEK + secrets.db live on a mounted
# /secrets volume at run time, never in the image. Modules are flat at /app, so
# broker.py does `import secrets_store` and the CLI is `python -m secrets_store`.
WORKDIR /app
COPY broker.py /app/broker.py
COPY secrets_store.py /app/secrets_store.py

# ── non-root + secrets mountpoint ─────────────────────────────────────────────
# /secrets is a docker NAMED VOLUME at run time (KEK + secrets.db). Pre-create
# it owned by `broker` so a fresh named volume inherits that ownership and this
# non-root container can write it. (A host bind mount would carry host-user
# ownership that, under rootless docker, the mapped container uid can't write —
# which is why we use a named volume here, not a bind mount.)
RUN useradd -m -u 1000 broker \
 && mkdir -p /secrets && chown broker:broker /secrets
USER broker

EXPOSE 8788
CMD ["uvicorn", "broker:app", "--host", "0.0.0.0", "--port", "8788"]
