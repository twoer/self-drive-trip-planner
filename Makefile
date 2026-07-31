PYTHON ?= python3
OUT ?= trip-output
TITLE ?= Demo 自驾游
START_DATE ?= 2026-07-17

.PHONY: install test demo-estimate demo-api demo-data pages-demo

install:
	$(PYTHON) -m pip install -r requirements.txt

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
