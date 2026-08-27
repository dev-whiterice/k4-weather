# Development targets. Run them from a shell that has GNU make: macOS, Linux,
# or Git Bash on Windows (Git for Windows brings the shell, `make` comes from
# `winget install GnuWin32.Make` or a Scoop/Chocolatey package).
#
# The only thing that differs between the platforms is where a virtualenv puts
# its executables — bin/ everywhere, Scripts/ on Windows — and what the system
# Python is called, since Windows has no `python3`. Both are decided once here
# so that no recipe below has to know.

ifeq ($(OS),Windows_NT)
  VENV_BIN := .venv/Scripts
  # `python3` on Windows is usually the Microsoft Store stub, which opens the
  # Store instead of running anything. `python` is the real one.
  SYS_PY   := python
else
  VENV_BIN := .venv/bin
  SYS_PY   := python3
endif

PY  := $(VENV_BIN)/python
PIP := $(VENV_BIN)/pip

.PHONY: setup preview generate icons indoor-font test inspect lineendings clean

setup: ## create the virtualenv and install everything, Chromium included
	$(SYS_PY) -m venv .venv
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements.txt -r requirements-dev.txt
	$(VENV_BIN)/playwright install chromium

preview: ## render the primary location from the local fixture, no network
	PYTHONPATH=src $(PY) -m k4weather preview

generate: ## fetch live data and render one image per configured location
	PYTHONPATH=src $(PY) -m k4weather generate

icons: ## contact sheet of every icon at the sizes it is really used
	PYTHONPATH=src $(PY) tools/icon_sheet.py out/icons.png

indoor-font: ## rebuild the font the Kindle draws the indoor temperature with
	## Only needed when the page's font or its OpenType features change: the
	## result is committed, because install.sh must be able to copy it without
	## a Python environment.
	$(PY) tools/indoor_font.py

inspect: ## check that every generated PNG is digestible by eips
	PYTHONPATH=src $(PY) -m k4weather inspect out

test:
	$(VENV_BIN)/pytest -q

lineendings: ## rewrite the working tree to the endings .gitattributes asks for
	## Worth running once after cloning on Windows with an older Git, or after
	## anything has dragged the files through a tool that "helpfully" converts
	## them. The scripts under kindle/ run on busybox ash, which reads a stray
	## carriage return as part of the value before it.
	git add --renormalize .
	git status --short

clean:
	rm -rf out .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
