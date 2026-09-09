IN_CONTAINER := $(shell test -f /.dockerenv && echo 1 || echo 0)
COMPOSE = docker compose
OPERATIONAL_COMPOSE = $(COMPOSE) -p finsport -f compose.yml
DEV_COMPOSE = $(COMPOSE) -p finsport-dev -f compose.dev.yml
PYTEST_CACHE_DIR = /tmp/finsport-pytest-cache
COVERAGE_FILE = /tmp/finsport-coverage

.PHONY: build up dev-create dev-up dev-destroy deploy-local backup backup-verify operational-up down safe-down status logs observability-up observability-stop observability-logs shell migrate makemigrations migration-check createsuperuser test coverage lint format format-check django-check pip-check security-audit dependency-check check hooks

ifeq ($(IN_CONTAINER),1)
APP =

build up dev-create dev-up dev-destroy deploy-local backup backup-verify operational-up down safe-down status logs:
	@echo "This target controls Docker Compose and must run on the host."
	@exit 1

observability-up observability-stop observability-logs:
	@echo "Observability Compose targets must run on the host."
	@exit 1

hooks:
	@echo "Git hooks must be installed from the host environment."
	@exit 1
else
APP = python3 tools/fs014_lifecycle.py dev-assert-ready && $(DEV_COMPOSE) run --rm --no-deps django-web

build:
	$(DEV_COMPOSE) build django-web

up:
	@grep -Eq '^GRAFANA_ADMIN_PASSWORD=.+$$' .env || (echo "Set a non-empty GRAFANA_ADMIN_PASSWORD in the ignored .env file." && exit 1)
	@python3 tools/fs014_lifecycle.py operational-image-check
	$(OPERATIONAL_COMPOSE) --profile operational --profile observability up -d --wait
	@python3 tools/fs014_lifecycle.py operational-running-check

dev-create:
	python3 tools/fs014_lifecycle.py dev-create

dev-up:
	python3 tools/fs014_lifecycle.py dev-up

dev-destroy:
	python3 tools/fs014_lifecycle.py dev-destroy

deploy-local:
	python3 tools/fs014_lifecycle.py deploy-local

backup:
	python3 tools/finsport_backup.py

backup-verify:
	python3 tools/fs014_lifecycle.py backup-verify

operational-up: up

down: safe-down

safe-down:
	python3 tools/runtime_control.py safe-down

status:
	python3 tools/runtime_control.py status

logs:
	$(OPERATIONAL_COMPOSE) logs -f

observability-up: operational-up

observability-stop:
	$(OPERATIONAL_COMPOSE) --profile observability stop observability-watch alloy loki grafana

observability-logs:
	$(OPERATIONAL_COMPOSE) --profile observability logs -f observability-watch alloy loki grafana

hooks:
	pre-commit install --install-hooks
endif

shell:
	$(APP) python manage.py shell

migrate:
	$(APP) python manage.py migrate

makemigrations:
	$(APP) python manage.py makemigrations

migration-check:
	$(APP) python manage.py makemigrations --check --dry-run

createsuperuser:
	$(APP) python manage.py createsuperuser

test:
	$(APP) pytest -o cache_dir=$(PYTEST_CACHE_DIR)

coverage:
	$(APP) sh -c "COVERAGE_FILE=$(COVERAGE_FILE) pytest -o cache_dir=$(PYTEST_CACHE_DIR) --cov --cov-config=.coveragerc --cov-report=term-missing:skip-covered"

lint:
	$(APP) ruff check --no-cache .

format:
	$(APP) sh -c "black . && ruff check --no-cache --fix ."

format-check:
	$(APP) black --check .

django-check:
	$(APP) python manage.py check

pip-check:
	$(APP) python -m pip check

security-audit:
	$(APP) python -m pip_audit --local

dependency-check: pip-check security-audit

check: format-check lint django-check migration-check dependency-check coverage
