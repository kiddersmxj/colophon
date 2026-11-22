# colophon: development and operation.
#
# `make help` lists everything. Targets are grouped by where they act:
#
#   (local)     this checkout: tests, a dev server, the CLI
#   prod-*      the server on your prod host
#
# Nothing here uses sudo. The server is a user service under the deploying
# user on the prod host (with lingering on), so that user owns the code, the
# venv and the state, and deploys never ask for a password. `make lint-sudo`
# keeps it that way. See docs/operations.md.
#
# Your own values (prod host, repos, public address) go in local.mk, which git
# ignores: copy local.mk.example. local.mk may also add targets of its own.
# The CLI's settings go in colophon.conf (see colophon.conf.example).

.DEFAULT_GOAL := help
SHELL := /bin/bash

-include local.mk

# Topology. colophon listens on the prod host's loopback; whatever fronts it
# (a reverse proxy, tailscale serve) gives it COLOPHON_URL.
PROD_HOST     ?=
PROD_DIR      ?= prod/colophon
PROD_PORT     ?= 8796
COLOPHON_URL  ?=

# Prod installs what is on the remote, never a working tree.
REPO          ?= $(shell git remote get-url origin 2>/dev/null)
BRANCH        ?= main
# The content. Only the server pushes to it, with a deploy key for this repo alone.
ENTRIES_REPO  ?=
ENTRIES_GH    ?=
DEPLOY_KEY    ?= .ssh/colophon-entries
KEY_SSH       := ssh -i ~/$(DEPLOY_KEY) -o IdentitiesOnly=yes

VENV          ?= .venv
PY            ?= $(VENV)/bin/python

.PHONY: help
help: ## Show this help
	@echo ""
	@echo "  colophon make targets"
	@awk 'BEGIN {FS = ":.*?## "} \
		/^# --- / { gsub(/^# --- /, ""); gsub(/ -*$$/, ""); printf "\n  \033[1m%s\033[0m\n", $$0 } \
		/^[a-zA-Z0-9_-]+:.*?## / { printf "    \033[36m%-20s\033[0m %s\n", $$1, $$2 }' \
		$(MAKEFILE_LIST)
	@echo ""

# --- Local development ------------------------------------------------------

.PHONY: install
install: ## Create the local venv with dev extras
	python3 -m venv $(VENV)
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet -e '.[dev]'
	@echo "installed: $$($(PY) -V)"

.PHONY: test
test: ## Run the test suite
	$(PY) -m pytest -q -p no:warnings

.PHONY: test-v
test-v: ## Run the test suite, verbosely
	$(PY) -m pytest -v -p no:warnings

.PHONY: dev
dev: ## Run the server locally on :8796, entries in ./var (a local repo, never pushed)
	COLOPHON_ENTRIES_DIR=$(PWD)/var/entries COLOPHON_STATE_DIR=$(PWD)/var/state \
	COLOPHON_PUBLIC_URL=http://127.0.0.1:$(PROD_PORT) COLOPHON_PUSH=false \
		$(PY) -m colophon.server

.PHONY: cli-install
cli-install: ## Link the CLI onto PATH as ~/.local/bin/colophon
	@mkdir -p ~/.local/bin
	@ln -sfn $(PWD)/bin/colophon ~/.local/bin/colophon
	@echo "linked ~/.local/bin/colophon -> $(PWD)/bin/colophon"

.PHONY: lint-sudo
lint-sudo: ## Fail if sudo appears in the Makefile recipes or the unit
	@! grep -nE '\bsudo\b' infra/systemd/* 2>/dev/null
	@! awk '/^[a-zA-Z0-9_-]+:/ {t=$$1} /^\t[^#]*\<sudo\>/ {print FILENAME": "t" "$$0}' Makefile | grep .
	@echo "no privilege escalation found"

.PHONY: lint-py
lint-py: ## Lint the Python (ruff: unused code, likely bugs, import order)
	$(VENV)/bin/ruff check colophon tests bin

.PHONY: lint
lint: lint-sudo lint-py test ## Run every check

# Deploys ship the remote, so unpushed work would silently not deploy.
.PHONY: pushed
pushed:
	@test -z "$$(git status --porcelain -- colophon infra pyproject.toml assets)" || \
		{ echo "uncommitted changes: commit and push first:"; \
		  git status --short -- colophon infra pyproject.toml assets | sed 's/^/    /'; exit 1; }
	@git fetch -q origin $(BRANCH)
	@test "$$(git rev-parse HEAD)" = "$$(git rev-parse origin/$(BRANCH))" || \
		{ echo "HEAD is not origin/$(BRANCH): push first"; exit 1; }

# --- Prod: the server on PROD_HOST -------------------------------------------
#
# First time, in order: prod-deploy-key, prod-bootstrap, prod-env, deploy.
# Then `make deploy` for every update.

.PHONY: need-prod
need-prod:
	@test -n "$(PROD_HOST)" -a -n "$(ENTRIES_REPO)" || \
		{ echo "PROD_HOST and ENTRIES_REPO are not set: copy local.mk.example to local.mk and fill it in"; exit 1; }

.PHONY: prod-deploy-key
prod-deploy-key: need-prod ## Make the prod host's key for the entries repo and add it to GitHub with write access
	@# The key never leaves the prod host; only its public half comes back, to gh.
	@ssh $(PROD_HOST) 'set -e; test -f ~/$(DEPLOY_KEY) || \
		ssh-keygen -q -t ed25519 -N "" -C "colophon@$(PROD_HOST)" -f ~/$(DEPLOY_KEY); \
		chmod 600 ~/$(DEPLOY_KEY); cat ~/$(DEPLOY_KEY).pub' \
		| gh repo deploy-key add - --repo $(ENTRIES_GH) --allow-write --title "colophon@$(PROD_HOST)"

.PHONY: prod-bootstrap
prod-bootstrap: need-prod ## First-time setup on prod: code checkout, entries checkout, state dir, venv
	@ssh $(PROD_HOST) 'set -euo pipefail; \
		python3 -c "import sys; assert sys.version_info >= (3, 11), sys.version" ; \
		mkdir -p $(PROD_DIR)/state; chmod 700 $(PROD_DIR)/state; \
		if [ ! -d $(PROD_DIR)/src/.git ]; then \
			git clone -q --branch $(BRANCH) $(REPO) $(PROD_DIR)/src; echo "cloned code into $(PROD_DIR)/src"; \
		fi; \
		if [ ! -d $(PROD_DIR)/entries/.git ]; then \
			GIT_SSH_COMMAND="$(KEY_SSH)" git clone -q $(ENTRIES_REPO) $(PROD_DIR)/entries; \
			git -C $(PROD_DIR)/entries config core.sshCommand "$(KEY_SSH)"; \
			echo "cloned entries into $(PROD_DIR)/entries"; \
		fi; \
		test -x $(PROD_DIR)/venv/bin/python || python3 -m venv $(PROD_DIR)/venv; \
		if ss -ltnH "sport = :$(PROD_PORT)" | grep -q . && ! systemctl --user -q is-active colophon; then \
			echo "port $(PROD_PORT) is taken by something else: pick another in the unit and PROD_PORT"; exit 1; \
		fi; \
		echo "bootstrapped"'

.PHONY: deploy
deploy: need-prod pushed lint ## Deploy: prod pulls the remote, reinstalls, restarts
	@# colophon.conf is ignored by git, so it travels beside the code, not in it.
	@if [ -f colophon.conf ]; then scp -q colophon.conf $(PROD_HOST):$(PROD_DIR)/src/colophon.conf && echo "copied colophon.conf"; fi
	@# fetch + reset --hard, not pull: prod is a deploy artifact, not a workspace.
	@ssh $(PROD_HOST) 'set -euo pipefail; \
		cd $(PROD_DIR)/src; \
		git fetch -q origin $(BRANCH); \
		git reset -q --hard origin/$(BRANCH); \
		../venv/bin/pip install --quiet ".[server]"; \
		../venv/bin/pip install --quiet --force-reinstall --no-deps .; \
		mkdir -p ~/.config/systemd/user; \
		install -m 644 infra/systemd/colophon.service ~/.config/systemd/user/; \
		systemctl --user daemon-reload; \
		systemctl --user enable colophon >/dev/null 2>&1; \
		systemctl --user restart colophon; \
		for i in $$(seq 30); do \
			if curl -sS --max-time 2 http://127.0.0.1:$(PROD_PORT)/health 2>/dev/null; then \
				echo; break; fi; \
			if [ "$$i" = 30 ]; then \
				echo "not answering on /health after 30s" >&2; \
				systemctl --user is-active colophon >&2 || true; exit 1; fi; \
			sleep 1; \
		done; \
		git log -1 --format="deployed %h %s"'

.PHONY: prod-env
prod-env: need-prod ## Write the server's settings into its env file on prod (keeps secrets there)
	@# The unit reads state/colophon.env. Each setting is replaced or appended;
	@# any other line (a directory token) is left as it is and never printed.
	@ssh $(PROD_HOST) 'set -euo pipefail; f=~/$(PROD_DIR)/state/colophon.env; umask 077; touch "$$f"; \
		set_var() { grep -v "^$$1=" "$$f" > "$$f.new" || true; printf "%s=%s\n" "$$1" "$$2" >> "$$f.new"; mv "$$f.new" "$$f"; }; \
		set_var COLOPHON_PUBLIC_URL "$(COLOPHON_URL)"; \
		$(if $(PROD_ROSTER_URL),set_var COLOPHON_ROSTER_URL "$(PROD_ROSTER_URL)";) \
		$(if $(PROD_TAILSCALE_SOCKET),set_var COLOPHON_TAILSCALE_SOCKET "$(PROD_TAILSCALE_SOCKET)";) \
		$(if $(PROD_COMMIT_EMAIL),set_var COLOPHON_COMMIT_EMAIL "$(PROD_COMMIT_EMAIL)";) \
		chmod 600 "$$f"; grep -oE "^[A-Z_]+=" "$$f" | sed "s/=$$//" | tr "\n" " "; echo'

.PHONY: health
health: ## Is the server up, at COLOPHON_URL
	@test -n "$(COLOPHON_URL)" || { echo "COLOPHON_URL is not set (local.mk)"; exit 1; }
	@curl -sS --max-time 10 $(COLOPHON_URL)/health | python3 -m json.tool || \
		echo "no answer from $(COLOPHON_URL)"

.PHONY: prod-version
prod-version: need-prod ## What commit is running on prod, and the entries checkout's head
	@ssh $(PROD_HOST) 'git -C $(PROD_DIR)/src log -1 --format="code    %h %ci %s"; \
		git -C $(PROD_DIR)/entries log -1 --format="entries %h %ci %s" 2>/dev/null || echo "entries: no commits yet"'

.PHONY: prod-status
prod-status: need-prod ## Server state and unpushed entry commits
	@ssh $(PROD_HOST) 'systemctl --user status colophon --no-pager -l | head -12; echo; \
		git -C $(PROD_DIR)/entries status -sb | head -1'

.PHONY: prod-logs
prod-logs: need-prod ## Follow the server's log
	@ssh $(PROD_HOST) 'journalctl --user -u colophon -f -n 50 --no-pager'

.PHONY: prod-restart
prod-restart: need-prod ## Restart the server
	@ssh $(PROD_HOST) 'systemctl --user restart colophon && sleep 1 && systemctl --user is-active colophon'
