CORE := shell_core
DB   := $(CORE)/shell_db.db
SCHEMA := $(CORE)/schema.sql
BACKUP_DIR := $(HOME)/db_backups/dos-arch

.PHONY: help install bootstrap migrate db-backup db-sync catalogue up down restart status logs health launch set-password create-user gen-api-key

help:
	@echo "shell-infra — host-level substrate"
	@echo ""
	@echo "  make launch              auth + pick + boot a shell (renders CLAUDE.md, exec claude)"
	@echo "  make launch-<shortname>  auth + boot that shell directly (skip picker)"
	@echo "  make set-password        set/reset a user's launcher password"
	@echo "  make create-user         create a new substrate user (with password)"
	@echo "  make gen-api-key ARGS=<shortname>  issue/rotate a shell's substrate-API key"
	@echo "  make install             pip + npm dependencies"
	@echo "  make bootstrap           one-shot: schema + skills + Forge + first user + Sys-Admin (refuses if DB exists)"
	@echo "  make migrate             apply pending DB migrations (ARGS=--status to preview)"
	@echo "  make db-backup           snapshot $(DB) to $(BACKUP_DIR)/<ts>.db"
	@echo "  make db-sync             refresh dr_router + dr_api from live routes"
	@echo "  make catalogue           print the substrate catalogue (filter via ARGS=, e.g. ARGS='api')"
	@echo "  make up                  pm2 start the UI (127.0.0.1:5173); API + broker run as containers"
	@echo "  make down                pm2 delete the UI"
	@echo "  make restart             pm2 restart the UI"
	@echo "  make status              pm2 ls"
	@echo "  make logs                pm2 logs (Ctrl-C to detach)"
	@echo "  make health              curl http://127.0.0.1:8000/health"

launch:
	@python3 $(CORE)/scripts/run.py

launch-%:
	@python3 $(CORE)/scripts/run.py $*

set-password:
	@python3 $(CORE)/scripts/set_password.py

create-user:
	@python3 $(CORE)/scripts/create_user.py

gen-api-key:
	@python3 $(CORE)/scripts/gen_api_key.py $(ARGS)

install:
	@command -v pm2 >/dev/null     || { echo "ERROR: pm2 not found — host dependencies skipped. As the operator: sudo npm install -g pm2  (see README Quickstart Step 0)."; exit 1; }
	@command -v node >/dev/null    || { echo "ERROR: node not found — host dependencies skipped. Run README Quickstart Step 0 as the operator."; exit 1; }
	@command -v python3 >/dev/null || { echo "ERROR: python3 not found — host dependencies skipped. Run README Quickstart Step 0 as the operator."; exit 1; }
	@echo "Creating .venv (PEP 668 hosts require an isolated env)..."
	@python3 -m venv .venv
	@echo "Installing python deps into .venv..."
	@./.venv/bin/pip install --quiet --upgrade pip
	@./.venv/bin/pip install --quiet fastapi uvicorn pydantic
	@echo "Installing UI deps..."
	@cd $(CORE)/ui && npm install --silent
	@echo "Done. Next: make bootstrap && make up"

bootstrap:
	@python3 $(CORE)/scripts/bootstrap.py

migrate:
	@python3 $(CORE)/scripts/migrate.py $(ARGS)

db-backup:
	@mkdir -p $(BACKUP_DIR)
	@TS=$$(date +%Y%m%d_%H%M%S); cp "$(DB)" "$(BACKUP_DIR)/shell_db.bak.$${TS}.db" && echo "Backed up -> $(BACKUP_DIR)/shell_db.bak.$${TS}.db"

db-sync:
	@./.venv/bin/python3 $(CORE)/scripts/dr_sync.py

catalogue:
	@python3 $(CORE)/scripts/catalogue.py $(ARGS)

up:
	@pm2 start ecosystem.config.cjs

down:
	@pm2 delete ecosystem.config.cjs 2>/dev/null || pm2 delete shell-infra-api shell-infra-ui 2>/dev/null || true

restart:
	@pm2 restart shell-infra-ui

status:
	@pm2 ls

logs:
	@pm2 logs shell-infra-ui

health:
	@curl -fsS http://127.0.0.1:8000/health && echo
