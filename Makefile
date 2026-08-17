PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: setup preview generate icons test inspect clean

setup: ## create the virtualenv and install everything, Chromium included
	python3 -m venv .venv
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements.txt -r requirements-dev.txt
	.venv/bin/playwright install chromium

preview: ## render out/dashboard.png from the local fixture, no network
	PYTHONPATH=src $(PY) -m k4weather preview

generate: ## fetch live data and render out/dashboard.png
	PYTHONPATH=src $(PY) -m k4weather generate

icons: ## contact sheet of every icon at the sizes it is really used
	PYTHONPATH=src $(PY) tools/icon_sheet.py out/icons.png

inspect: ## check that the PNG is digestible by eips
	PYTHONPATH=src $(PY) -m k4weather inspect out/dashboard.png

test:
	.venv/bin/pytest -q

clean:
	rm -rf out .pytest_cache **/__pycache__
