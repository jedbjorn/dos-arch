CORE := shell_core
DB   := $(CORE)/shell_db.db
SCHEMA := $(CORE)/schema.sql
BACKUP_DIR := $(HOME)/db_backups/dos-arch

.PHONY: help install bootstrap migrate db-backup db-sync catalogue collect-hardware sync-models sync-cloud-models sync-remote-models up down restart status logs health create-user gen-api-key dispatch

help:
	@echo "shell-infra — host-level substrate (API system; shells run via the dispatcher, not a terminal)"
	@echo ""
	@echo "  make create-user         create a new substrate user"
	@echo "  make gen-api-key ARGS=<shortname>  issue/rotate a shell's substrate-API key"
	@echo "  make install             pip + npm dependencies"
	@echo "  make bootstrap           one-shot: schema + skills + Forge + first user + Sys-Admin (refuses if DB exists)"
	@echo "  make migrate             apply pending DB migrations (ARGS=--status to preview)"
	@echo "  make db-backup           snapshot $(DB) to $(BACKUP_DIR)/<ts>.db"
	@echo "  make db-sync             refresh dr_router + dr_api from live routes"
	@echo "  make catalogue           print the substrate catalogue (filter via ARGS=, e.g. ARGS='api')"
	@echo "  make collect-hardware    probe this host into user_hardware (ARGS='--user-id N')"
	@echo "  make sync-models         sync the models table from Ollama (runs collect-hardware first)"
	@echo "  make sync-cloud-models   sync the models table from Ollama Cloud's /api/tags (anonymous)"
	@echo "  make sync-remote-models  sync the models table from Anthropic + OpenAI /v1/models (needs keys)"
	@echo "  make up                  pm2 start the API, UI, dispatcher + model-sync; only the broker is a container"
	@echo "  make down                pm2 delete the API, UI, dispatcher + model-sync"
	@echo "  make restart             pm2 restart the API, UI, dispatcher + model-sync"
	@echo "  make status              pm2 ls"
	@echo "  make logs                pm2 logs (Ctrl-C to detach)"
	@echo "  make health              curl http://127.0.0.1:8001/health"
	@echo "  make dispatch            run the browser-chat dispatcher in the foreground (debug; pm2 runs it normally)"

create-user:
	@python3 $(CORE)/scripts/create_user.py

gen-api-key:
	@python3 $(CORE)/scripts/gen_api_key.py $(ARGS)

install:
	@command -v pm2 >/dev/null     || { echo "ERROR: pm2 not found — run 'sudo ./install/host-setup.sh' first."; exit 1; }
	@command -v node >/dev/null    || { echo "ERROR: node not found — run 'sudo ./install/host-setup.sh' first."; exit 1; }
	@command -v python3 >/dev/null || { echo "ERROR: python3 not found — run 'sudo ./install/host-setup.sh' first."; exit 1; }
	@echo "Creating .venv (PEP 668 hosts require an isolated env)..."
	@python3 -m venv .venv
	@echo "Installing python deps into .venv..."
	@./.venv/bin/pip install --quiet --upgrade pip
	@./.venv/bin/pip install --quiet -r $(CORE)/requirements.txt
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
	@PY=./.venv/bin/python3; [ -x "$$PY" ] || PY=python3; "$$PY" $(CORE)/scripts/dr_sync.py

catalogue:
	@python3 $(CORE)/scripts/catalogue.py $(ARGS)

collect-hardware:
	@python3 $(CORE)/scripts/collect_hardware.py $(ARGS)

sync-models:
	@python3 $(CORE)/scripts/collect_hardware.py
	@python3 $(CORE)/scripts/model_sync.py $(ARGS)

sync-cloud-models:
	@python3 $(CORE)/scripts/cloud_model_sync.py $(ARGS)

sync-remote-models:
	@BROKER_BASE=$${BROKER_BASE:-http://127.0.0.1:8788} python3 $(CORE)/scripts/remote_model_sync.py $(ARGS)

up:
	@pm2 start ecosystem.config.cjs

down:
	@pm2 delete ecosystem.config.cjs 2>/dev/null || pm2 delete dosarch-api dosarch-ui dosarch-dispatch dosarch-modelsync 2>/dev/null || true

restart:
	@pm2 restart ecosystem.config.cjs

status:
	@pm2 ls

logs:
	@pm2 logs

health:
	@curl -fsS http://127.0.0.1:8001/health && echo

dispatch:
	@PY=./.venv/bin/python3; [ -x "$$PY" ] || { echo "ERROR: .venv missing — run 'make install'"; exit 1; }; \
	ENV="$$HOME/.config/dos-arch/.env"; [ -f "$$ENV" ] || { echo "ERROR: $$ENV missing — see install/README.md"; exit 1; }; \
	set -a; . "$$ENV"; set +a; \
	"$$PY" $(CORE)/services/dispatch_live.py
