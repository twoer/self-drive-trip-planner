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
            self.assertTrue((output_dir / "manifest.json").is_file())

            # The static map is PNG when Playwright is available, otherwise SVG.
            data = json.loads((output_dir / "trip-data.json").read_text(encoding="utf-8"))
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            map_file = data["map"]["file"]
            self.assertTrue((output_dir / map_file).is_file(), f"{map_file} should exist")
            self.assertIn(data["map"]["source"],
                          ("leaflet-playwright-screenshot", "fallback-svg"))
            self.assertEqual(manifest["mode"], "estimate")
            self.assertEqual(manifest["files"]["data"], "trip-data.json")
            self.assertEqual(manifest["files"]["html"], "trip.html")
            self.assertEqual(manifest["files"]["map_image"], map_file)
            self.assertEqual(manifest["data_source"], "estimated")
            self.assertGreaterEqual(len(manifest["warnings"]), 1)

            self.assertEqual(len(data["days"]), 10)
            self.assertEqual(data["days"][6]["title"], "贵阳市区")
            self.assertEqual(data["days"][8]["title"], "重庆市区")

            legs = [leg for day in data["days"] for leg in day["legs"]]
            self.assertTrue(all(leg["origin"] and leg["destination"] for leg in legs))
            chongqing_to_hefei = next(leg for leg in legs if leg["from"] == "重庆" and leg["to"] == "合肥")
            self.assertGreater(chongqing_to_hefei["distance_km"], 1000)
            self.assertNotIn(100.0, [leg["distance_km"] for leg in legs])
            html = (output_dir / "trip.html").read_text(encoding="utf-8")
            self.assertIn("费用计算未启用", html)
            self.assertIn("你可以这样说", html)
            self.assertIn("电价 1.5 元/度", html)
            self.assertNotIn("示例：--vehicle-type", html)
            self.assertIn("data-tab=\"budget\"", html)
            self.assertFalse(data["budget"]["configured"])
            self.assertIn("budget", manifest)

    def test_budget_arguments_generate_cost_tab_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "trip-output"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(ROOT / "examples" / "simple-trip.txt"),
                    "--out",
                    str(output_dir),
                    "--title",
                    "预算 Demo",
                    "--no-api",
                    "--vehicle-type",
                    "ev",
                    "--ev-kwh-price",
                    "1.5",
                    "--hotel-nightly",
                    "300",
                    "--meal-daily",
                    "100",
                    "--attraction",
                    "小七孔=120",
                    "--attraction",
                    "中国天眼=140",
                ],
                check=True,
                text=True,
                capture_output=True,
            )

            data = json.loads((output_dir / "trip-data.json").read_text(encoding="utf-8"))
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            html = (output_dir / "trip.html").read_text(encoding="utf-8")
            budget = data["budget"]

            self.assertTrue(budget["configured"])
            self.assertGreater(budget["total_cny"], data["totals"]["toll_cny"])
            self.assertIn("vehicle_energy", budget["category_totals"])
            self.assertEqual(budget["assumptions"]["vehicle"]["kwh_per_100km"], 16.0)
            self.assertEqual(budget["category_totals"]["hotel"], 2700.0)
            self.assertEqual(budget["category_totals"]["meal"], 1000.0)
            self.assertEqual(budget["category_totals"]["attraction"], 260.0)
            self.assertEqual(manifest["budget"]["total_cny"], budget["total_cny"])
            self.assertIn("费用预估", html)
            self.assertIn("小七孔", html)

    def test_data_only_pdf_request_reports_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "trip-output"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(ROOT / "examples" / "simple-trip.txt"),
                    "--out",
                    str(output_dir),
                    "--mode",
                    "data-only",
                    "--pdf",
                ],
                check=True,
                text=True,
                capture_output=True,
            )

            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertIsNone(manifest["files"]["pdf"])
            self.assertTrue(any("PDF" in warning for warning in manifest["warnings"]))

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
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue((output_dir / "route-map.svg").is_file())
            self.assertEqual(data["map"]["source"], "fallback-svg")
            self.assertTrue(data["map"]["fallback"])
            self.assertEqual(manifest["files"]["map_image"], "route-map.svg")

    def test_data_only_mode_writes_only_json_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "trip-output"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(ROOT / "examples" / "simple-trip.txt"),
                    "--out",
                    str(output_dir),
                    "--title",
                    "Demo",
                    "--mode",
                    "data-only",
                ],
                check=True,
                text=True,
                capture_output=True,
            )

            self.assertTrue((output_dir / "trip-data.json").is_file())
            self.assertTrue((output_dir / "manifest.json").is_file())
            self.assertFalse((output_dir / "trip.html").exists())
            self.assertFalse((output_dir / "route-map.png").exists())
            self.assertFalse((output_dir / "route-map.svg").exists())
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["mode"], "data-only")
            self.assertIsNone(manifest["files"]["html"])
            self.assertIsNone(manifest["files"]["map_image"])

    def test_publish_demo_writes_index_html_contract(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "docs"
            old_value = os.environ.get("SDTP_NO_PLAYWRIGHT")
            os.environ["SDTP_NO_PLAYWRIGHT"] = "1"
            try:
                days = self.route_trip.parse_itinerary((ROOT / "examples" / "simple-trip.txt").read_text(encoding="utf-8"))
                data = self.route_trip.enrich(days, use_api=False)
                data["title"] = "Demo"
                self.route_trip.write_outputs(data, output_dir, key=None, mode="publish-demo")
            finally:
                if old_value is None:
                    os.environ.pop("SDTP_NO_PLAYWRIGHT", None)
                else:
                    os.environ["SDTP_NO_PLAYWRIGHT"] = old_value

            self.assertTrue((output_dir / "index.html").is_file())
            self.assertFalse((output_dir / "trip.html").exists())
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["mode"], "publish-demo")
            self.assertEqual(manifest["files"]["html"], "index.html")

    def test_accurate_mode_requires_key(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            env = {key: value for key, value in os.environ.items() if key not in ("AMAP_KEY", "GAODE_KEY")}
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(ROOT / "examples" / "simple-trip.txt"),
                    "--out",
                    str(Path(tmp) / "trip-output"),
                    "--mode",
                    "accurate",
                ],
                text=True,
                capture_output=True,
                env=env,
            )

            self.assertEqual(result.returncode, 3)
            self.assertIn("requires AMAP_KEY or GAODE_KEY", result.stderr)


if __name__ == "__main__":
    unittest.main()
