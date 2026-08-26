IN_CONTAINER := $(shell test -f /.dockerenv && echo 1 || echo 0)
COMPOSE = docker compose
PYTEST_CACHE_DIR = /tmp/finsport-pytest-cache

.PHONY: build up down logs shell migrate makemigrations createsuperuser test coverage lint format format-check django-check check hooks

ifeq ($(IN_CONTAINER),1)
APP =

build up down logs:
	@echo "This target controls Docker Compose and must run on the host."
	@exit 1

hooks:
	@echo "Git hooks must be installed from the host environment."
	@exit 1
else
APP = $(COMPOSE) run --rm django-web

build:
	$(COMPOSE) build django-web celery celery-beat

up:
	$(COMPOSE) up

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

hooks:
	pre-commit install --install-hooks
endif

shell:
	$(APP) python manage.py shell

migrate:
	$(APP) python manage.py migrate

makemigrations:
	$(APP) python manage.py makemigrations

createsuperuser:
	$(APP) python manage.py createsuperuser

test:
	$(APP) pytest -o cache_dir=$(PYTEST_CACHE_DIR)

coverage:
	$(APP) pytest -o cache_dir=$(PYTEST_CACHE_DIR) --cov --cov-config=.coveragerc --cov-report=term-missing:skip-covered

lint:
	$(APP) ruff check --no-cache .

format:
	$(APP) sh -c "black . && ruff check --no-cache --fix ."

format-check:
	$(APP) black --check .

django-check:
	$(APP) python manage.py check

check: format-check lint django-check test
