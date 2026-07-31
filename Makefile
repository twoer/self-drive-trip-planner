PYTHON ?= python3
OUT ?= trip-output
TITLE ?= Demo 自驾游
START_DATE ?= 2026-07-17
CODEX_SKILLS_DIR ?= $(HOME)/.codex/skills
PLUGIN_CREATOR_DIR ?= $(HOME)/.codex/skills/.system/plugin-creator
PLUGIN_VALIDATOR ?= $(PLUGIN_CREATOR_DIR)/scripts/validate_plugin.py

.PHONY: install setup demo install-skill test demo-estimate demo-api demo-data pages-demo package-plugin validate-plugin

install:
	$(PYTHON) -m pip install -r requirements.txt

setup:
	$(PYTHON) scripts/setup_env.py

demo:
	$(PYTHON) scripts/run_demo.py --out $(OUT) --title "$(TITLE)" --start-date $(START_DATE)

install-skill:
	$(PYTHON) scripts/install_skill.py --dest $(CODEX_SKILLS_DIR)

test:
	$(PYTHON) -m py_compile scripts/route_trip.py scripts/leaflet_map.py
	$(PYTHON) -m unittest discover -s tests

demo-estimate:
	$(PYTHON) scripts/route_trip.py examples/simple-trip.txt --out $(OUT) --title "$(TITLE)" --start-date $(START_DATE) --mode estimate

demo-api:
	$(PYTHON) scripts/route_trip.py examples/simple-trip.txt --out $(OUT) --title "$(TITLE)" --start-date $(START_DATE) --mode accurate

demo-data:
	$(PYTHON) scripts/route_trip.py examples/simple-trip.txt --out $(OUT) --title "$(TITLE)" --start-date $(START_DATE) --mode data-only

pages-demo:
	$(PYTHON) scripts/route_trip.py examples/simple-trip.txt --out docs --title "Self-Drive Trip Planner Demo" --start-date $(START_DATE) --mode publish-demo
	touch docs/.nojekyll

package-plugin:
	$(PYTHON) scripts/package_plugin.py --out dist

validate-plugin: package-plugin
	$(PYTHON) $(PLUGIN_VALIDATOR) dist/self-drive-trip-planner
