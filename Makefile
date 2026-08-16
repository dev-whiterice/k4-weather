PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: setup preview generate icons test inspect clean

setup: ## crea il virtualenv e installa tutto, Chromium compreso
	python3 -m venv .venv
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements.txt -r requirements-dev.txt
	.venv/bin/playwright install chromium

preview: ## genera out/dashboard.png dalla fixture locale, senza rete
	PYTHONPATH=src $(PY) -m k4weather preview

generate: ## scarica i dati veri e genera out/dashboard.png
	PYTHONPATH=src $(PY) -m k4weather generate

icons: ## provino di tutte le icone alle dimensioni reali
	PYTHONPATH=src $(PY) tools/icon_sheet.py out/icons.png

inspect: ## verifica che il PNG sia digeribile da eips
	PYTHONPATH=src $(PY) -m k4weather inspect out/dashboard.png

test:
	.venv/bin/pytest -q

clean:
	rm -rf out .pytest_cache **/__pycache__
