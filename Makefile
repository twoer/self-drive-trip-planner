VENV ?= .venv
BOOTSTRAP_PYTHON ?= python3
PYTHON ?= $(VENV)/bin/python
OUT ?= trip-output
TITLE ?= Demo 自驾游
START_DATE ?= 2026-07-17
CODEX_SKILLS_DIR ?= $(HOME)/.codex/skills
PLUGIN_CREATOR_DIR ?= $(HOME)/.codex/skills/.system/plugin-creator
PLUGIN_VALIDATOR ?= $(PLUGIN_CREATOR_DIR)/scripts/validate_plugin.py
SCRIPT_FILES := $(wildcard scripts/*.py)

.PHONY: install install-pdf setup demo install-skill install-plugin check-installed-plugin test demo-estimate demo-api demo-data demo-pdf demo-batch pages-demo package-plugin check-plugin-package validate-plugin

$(PYTHON):
	$(BOOTSTRAP_PYTHON) -m venv $(VENV)

install: $(PYTHON)
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

install-pdf: install
	$(PYTHON) -m pip install playwright
	$(PYTHON) -m playwright install chromium

setup: $(PYTHON)
	$(PYTHON) scripts/setup_env.py

demo: install
	$(PYTHON) scripts/run_demo.py --out $(OUT) --title "$(TITLE)" --start-date $(START_DATE)

install-skill: $(PYTHON)
	$(PYTHON) scripts/install_skill.py --dest $(CODEX_SKILLS_DIR)

install-plugin: $(PYTHON)
	$(PYTHON) scripts/install_plugin_local.py

check-installed-plugin: package-plugin
	$(PYTHON) scripts/check_installed_plugin.py --expected-plugin dist/self-drive-trip-planner --require-cache --require-codex-list

test: install
	$(PYTHON) -m py_compile $(SCRIPT_FILES)
	$(PYTHON) -m unittest discover -s tests

demo-estimate: install
	$(PYTHON) scripts/route_trip.py examples/simple-trip.txt --out $(OUT) --title "$(TITLE)" --start-date $(START_DATE) --mode estimate

demo-api: install
	$(PYTHON) scripts/route_trip.py examples/simple-trip.txt --out $(OUT) --title "$(TITLE)" --start-date $(START_DATE) --mode accurate

demo-data: install
	$(PYTHON) scripts/route_trip.py examples/simple-trip.txt --out $(OUT) --title "$(TITLE)" --start-date $(START_DATE) --mode data-only

demo-pdf: install
	$(PYTHON) scripts/route_trip.py examples/simple-trip.txt --out $(OUT) --title "$(TITLE)" --start-date $(START_DATE) --mode estimate --pdf

demo-batch: install
	$(PYTHON) scripts/generate_demo_batch.py --out trip-output/random-demo --mode auto

pages-demo: install
	$(PYTHON) scripts/route_trip.py examples/simple-trip.txt --out docs --title "Self-Drive Trip Planner Demo" --start-date $(START_DATE) --mode publish-demo
	touch docs/.nojekyll

package-plugin: $(PYTHON)
	$(PYTHON) scripts/package_plugin.py --out dist

check-plugin-package: package-plugin
	$(PYTHON) scripts/check_plugin_package.py dist/self-drive-trip-planner

validate-plugin: package-plugin check-plugin-package
	$(PYTHON) $(PLUGIN_VALIDATOR) dist/self-drive-trip-planner
