IN_CONTAINER := $(shell test -f /.dockerenv && echo 1 || echo 0)
COMPOSE = docker compose
PYTEST_CACHE_DIR = /tmp/finsport-pytest-cache
COVERAGE_FILE = /tmp/finsport-coverage

.PHONY: build up dev-up operational-up down safe-down status logs observability-up observability-stop observability-logs shell migrate makemigrations migration-check createsuperuser test coverage lint format format-check django-check pip-check security-audit dependency-check check hooks

ifeq ($(IN_CONTAINER),1)
APP =

build up dev-up operational-up down safe-down status logs:
	@echo "This target controls Docker Compose and must run on the host."
	@exit 1

observability-up observability-stop observability-logs:
	@echo "Observability Compose targets must run on the host."
	@exit 1

hooks:
	@echo "Git hooks must be installed from the host environment."
	@exit 1
else
APP = $(COMPOSE) run --rm django-web

build:
	$(COMPOSE) build

up:
	@grep -Eq '^GRAFANA_ADMIN_PASSWORD=.+$$' .env || (echo "Set a non-empty GRAFANA_ADMIN_PASSWORD in the ignored .env file." && exit 1)
	$(COMPOSE) --profile operational --profile observability up -d

dev-up:
	python3 tools/runtime_control.py safe-down
	$(COMPOSE) up -d --wait db redis
	@depth=$$($(COMPOSE) exec -T redis redis-cli -n 14 LLEN finsport.local.safe); \
	if [ "$$depth" != "0" ]; then \
		echo "Refusing dev-up: finsport.local.safe contains $$depth queued task(s). Review/drain them operationally; the queue was not purged."; \
		exit 1; \
	fi
	$(COMPOSE) up -d django-web celery nginx

operational-up: up

down: safe-down

safe-down:
	python3 tools/runtime_control.py safe-down

status:
	python3 tools/runtime_control.py status

logs:
	$(COMPOSE) logs -f

observability-up: operational-up

observability-stop:
	$(COMPOSE) --profile observability stop observability-watch alloy loki grafana

observability-logs:
	$(COMPOSE) --profile observability logs -f observability-watch alloy loki grafana

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
