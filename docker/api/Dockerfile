# syntax=docker/dockerfile:1
#
# Substrate API image — dos-arch.
# Runs as its OWN container (`dos-api`) on the shared `dos-net` network — a
# trusted service container, like dos-broker. Shell containers reach it by
# Docker DNS (http://dos-api:8000) for memory; the host UI reaches it via a
# loopback-published port.
#
# The image carries ONLY the Python deps. The substrate code + DB are
# bind-mounted from the host repo at run time (-v shell_core:/substrate/
# shell_core), so `git pull` + a container restart updates the API with no
# rebuild — and SQLite's DB and its journal stay co-located on the host,
# visible to both this container and the host-side launcher.
#
#   docker build -f docker/api/Dockerfile -t dos-api:latest docker/api
#   docker run -d --name dos-api --network dos-net \
#     -v <repo>/shell_core:/substrate/shell_core \
#     -p 127.0.0.1:8000:8000 --restart unless-stopped dos-api:latest

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/substrate/shell_core

RUN pip install --no-cache-dir fastapi uvicorn pydantic

# No USER directive: under rootless Docker, container-root maps to the
# unprivileged dos-arch host user — which is what holds write access to the
# bind-mounted shell_db.db. A non-root container user would map to a subuid
# with no access to it.
WORKDIR /substrate/shell_core
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
