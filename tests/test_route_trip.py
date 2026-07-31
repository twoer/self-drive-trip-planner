import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "route_trip.py"


def load_route_trip():
    spec = importlib.util.spec_from_file_location("route_trip", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RouteTripTests(unittest.TestCase):
    def setUp(self):
        self.route_trip = load_route_trip()

    def test_parse_connectors_and_stay_notes(self):
        text = """D1
合肥 到 岳阳
D2
岳阳 -> 韶山 → 凤凰古城
D3
凤凰古城 返回 合肥
D4
合肥市区
"""
        days = self.route_trip.parse_itinerary(text)

        self.assertEqual([day["day"] for day in days], ["D1", "D2", "D3", "D4"])
        self.assertEqual(days[1]["legs"], [{"from": "岳阳", "to": "韶山"}, {"from": "韶山", "to": "凤凰古城"}])
        self.assertEqual(days[2]["legs"], [{"from": "凤凰古城", "to": "合肥"}])
        self.assertEqual(days[3]["notes"], ["合肥市区"])

    def test_enrich_keeps_non_driving_days(self):
        days = self.route_trip.parse_itinerary("""D1
合肥 到 岳阳
D2
岳阳市区
D3
岳阳 回 合肥
""")
        data = self.route_trip.enrich(days, use_api=False)

        self.assertEqual([day["day"] for day in data["days"]], ["D1", "D2", "D3"])
        stay_day = data["days"][1]
        self.assertEqual(stay_day["title"], "岳阳市区")
        self.assertEqual(stay_day["distance_km"], 0.0)
        self.assertEqual(stay_day["duration_min"], 0)
        self.assertEqual(stay_day["toll_cny"], 0)

    def test_overview_markers_merge_loop_and_limit_to_ten(self):
        text = """D1
合肥 到 岳阳 到 韶山 到 凤凰古城
D2
凤凰古城 到 荔波 到 小七孔 到 中国天眼 到 安顺 到 贵阳
D3
贵阳 到 茅台镇 到 遵义 到 荆州 到 合肥
"""
        data = self.route_trip.enrich(self.route_trip.parse_itinerary(text), use_api=False)
        map_stops, omitted = self.route_trip.overview_marker_stops(data)

        self.assertLessEqual(len(map_stops), 10)
        self.assertGreater(len(omitted), 0)
        self.assertEqual(map_stops[0]["name"], "合肥")
        self.assertEqual(map_stops[0]["role"], "起点/终点")
        self.assertEqual(len(self.route_trip.static_map_markers(map_stops).split("|")), len(map_stops))

    def test_cli_no_api_generates_expected_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "trip-output"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(ROOT / "examples" / "simple-trip.txt"),
                    "--out",
                    str(output_dir),
                    "--title",
                    "Demo 自驾游",
                    "--no-api",
                ],
                check=True,
                text=True,
                capture_output=True,
            )

            self.assertIn("Wrote:", result.stdout)
            self.assertTrue((output_dir / "trip.html").is_file())
            self.assertTrue((output_dir / "trip-data.json").is_file())

            # The static map is PNG when Playwright is available, otherwise SVG.
            data = json.loads((output_dir / "trip-data.json").read_text(encoding="utf-8"))
            map_file = data["map"]["file"]
            self.assertTrue((output_dir / map_file).is_file(), f"{map_file} should exist")
            self.assertIn(data["map"]["source"],
                          ("leaflet-playwright-screenshot", "fallback-svg"))

            self.assertEqual(len(data["days"]), 10)
            self.assertEqual(data["days"][6]["title"], "贵阳市区")
            self.assertEqual(data["days"][8]["title"], "重庆市区")

            legs = [leg for day in data["days"] for leg in day["legs"]]
            self.assertTrue(all(leg["origin"] and leg["destination"] for leg in legs))
            chongqing_to_hefei = next(leg for leg in legs if leg["from"] == "重庆" and leg["to"] == "合肥")
            self.assertGreater(chongqing_to_hefei["distance_km"], 1000)
            self.assertNotIn(100.0, [leg["distance_km"] for leg in legs])

    def test_fallback_svg_when_playwright_unavailable(self):
        """When Playwright is unavailable, a route-map.svg fallback is produced."""
        import os
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "trip-output"
            env = {**os.environ, "SDTP_NO_PLAYWRIGHT": "1"}
            subprocess.run(
                [sys.executable, str(SCRIPT), str(ROOT / "examples" / "simple-trip.txt"),
                 "--out", str(output_dir), "--title", "Demo", "--no-api"],
                check=True, text=True, capture_output=True, env=env,
            )
            data = json.loads((output_dir / "trip-data.json").read_text(encoding="utf-8"))
            self.assertTrue((output_dir / "route-map.svg").is_file())
            self.assertEqual(data["map"]["source"], "fallback-svg")
            self.assertTrue(data["map"]["fallback"])


if __name__ == "__main__":
    unittest.main()
