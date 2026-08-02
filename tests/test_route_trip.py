import importlib.util
import argparse
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

    def test_budget_cli_parsers_reject_non_finite_amounts(self):
        for value in ("nan", "inf", "-inf"):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    self.route_trip.parse_non_negative_float(value)
                with self.assertRaises(argparse.ArgumentTypeError):
                    self.route_trip.parse_named_amount(f"费用={value}")

    def test_generated_html_keeps_user_text_out_of_script_markup(self):
        malicious = '__LEAFLET_MAP__ </script><img src=x onerror="alert(1)">'
        data = self.route_trip.enrich(
            self.route_trip.parse_itinerary("D1\n合肥 到 岳阳\n"),
            use_api=False,
        )
        data["title"] = malicious
        data["days"][0]["title"] = malicious

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "trip.html"
            self.route_trip.generate_html(data, output)
            generated = output.read_text(encoding="utf-8")

        self.assertEqual(generated.count('id="trip-map"'), 1)
        self.assertIn("__LEAFLET_MAP__", generated)
        self.assertNotIn("</script><img", generated)
        self.assertIn("\\u003c/script\\u003e", generated)

    def test_parse_common_chinese_route_connectors(self):
        days = self.route_trip.parse_itinerary("""D1
合肥 到达 岳阳
D2
岳阳 前往 韶山 去往 凤凰古城
D3
凤凰古城 至 荔波
D4
荔波 - 小七孔
D5
中国天眼 回到 合肥
""")

        self.assertEqual(days[0]["legs"], [{"from": "合肥", "to": "岳阳"}])
        self.assertEqual(days[1]["legs"], [{"from": "岳阳", "to": "韶山"}, {"from": "韶山", "to": "凤凰古城"}])
        self.assertEqual(days[2]["legs"], [{"from": "凤凰古城", "to": "荔波"}])
        self.assertEqual(days[3]["legs"], [{"from": "荔波", "to": "小七孔"}])
        self.assertEqual(days[4]["legs"], [{"from": "中国天眼", "to": "合肥"}])

    def test_parse_day_label_with_inline_route_or_note(self):
        days = self.route_trip.parse_itinerary("""D1：合肥 到 岳阳
Day2 岳阳 到 韶山
D3：韶山市区
D4-韶山 返回 合肥
""")

        self.assertEqual([day["day"] for day in days], ["D1", "D2", "D3", "D4"])
        self.assertEqual(days[0]["legs"], [{"from": "合肥", "to": "岳阳"}])
        self.assertEqual(days[1]["legs"], [{"from": "岳阳", "to": "韶山"}])
        self.assertEqual(days[2]["notes"], ["韶山市区"])
        self.assertEqual(days[3]["legs"], [{"from": "韶山", "to": "合肥"}])

    def test_parse_chinese_day_label_with_inline_route_or_note(self):
        days = self.route_trip.parse_itinerary("""第1天：合肥 到 岳阳
第二天 岳阳 到 韶山
第3天：韶山市区
第十天 韶山 返回 合肥
""")

        self.assertEqual([day["day"] for day in days], ["D1", "D2", "D3", "D10"])
        self.assertEqual(days[0]["legs"], [{"from": "合肥", "to": "岳阳"}])
        self.assertEqual(days[1]["legs"], [{"from": "岳阳", "to": "韶山"}])
        self.assertEqual(days[2]["notes"], ["韶山市区"])
        self.assertEqual(days[3]["legs"], [{"from": "韶山", "to": "合肥"}])

    def test_parse_leading_notes_avoid_explicit_day_label_collision(self):
        days = self.route_trip.parse_itinerary("""出发前检查车辆
D1
合肥 到 岳阳
""")

        self.assertEqual([day["day"] for day in days], ["D1"])
        self.assertEqual(days[0]["notes"], ["出发前检查车辆"])
        self.assertEqual(days[0]["legs"], [{"from": "合肥", "to": "岳阳"}])

    def test_parse_leading_route_avoid_explicit_day_label_collision(self):
        days = self.route_trip.parse_itinerary("""合肥 到 岳阳
D1
岳阳 到 韶山
""")

        self.assertEqual([day["day"] for day in days], ["D2", "D1"])
        self.assertEqual(days[0]["legs"], [{"from": "合肥", "to": "岳阳"}])
        self.assertEqual(days[1]["legs"], [{"from": "岳阳", "to": "韶山"}])

    def test_parse_rejects_zero_day_label(self):
        with self.assertRaisesRegex(ValueError, "Day numbers must start at 1"):
            self.route_trip.parse_itinerary("""D0
合肥 到 岳阳
""")

    def test_parse_rejects_zero_day_label_with_inline_route(self):
        with self.assertRaisesRegex(ValueError, "Day numbers must start at 1"):
            self.route_trip.parse_itinerary("D0：合肥 到 岳阳\n")

    def test_parse_rejects_zero_chinese_day_label(self):
        with self.assertRaisesRegex(ValueError, "Day numbers must start at 1"):
            self.route_trip.parse_itinerary("第0天：合肥 到 岳阳\n")

    def test_parse_rejects_duplicate_explicit_day_label(self):
        with self.assertRaisesRegex(ValueError, "Duplicate day label: D1"):
            self.route_trip.parse_itinerary("""D1：合肥 到 岳阳
第一天 岳阳 到 韶山
""")

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

    def test_leaflet_map_data_merges_loop_stops(self):
        text = """D1
合肥 到 岳阳 到 韶山 到 凤凰古城
D2
凤凰古城 到 荔波 到 小七孔 到 中国天眼 到 安顺 到 贵阳
D3
贵阳 到 茅台镇 到 遵义 到 荆州 到 合肥
"""
        data = self.route_trip.enrich(self.route_trip.parse_itinerary(text), use_api=False)
        map_data = self.route_trip.leaflet_map.build_map_data(data)
        stops = map_data["stops"]

        self.assertEqual(stops[0]["name"], "合肥")
        self.assertEqual(stops[0]["day"], "D1/D3")
        self.assertEqual(len([stop for stop in stops if stop["name"] == "合肥"]), 1)
        self.assertTrue(all(stop.get("lng") and stop.get("lat") for stop in stops))

    def test_cli_default_fixture_generates_expected_contract(self):
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
            self.assertIn("Verified: output contract", result.stdout)
            self.assertTrue((output_dir / "trip.html").is_file())
            self.assertTrue((output_dir / "trip-data.json").is_file())
            self.assertTrue((output_dir / "manifest.json").is_file())

            # The shareable route map is PNG when Playwright is available, otherwise SVG.
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
            self.assertIn(manifest["files"]["budget_image"], ("budget-summary.png", "budget-summary.svg"))
            self.assertTrue((output_dir / manifest["files"]["budget_image"]).is_file())
            self.assertEqual(manifest["data_source"], "estimated")
            self.assertEqual(
                manifest["counts"],
                {"days": 10, "driving_days": 8, "legs": 13, "estimated_legs": 13},
            )
            self.assertGreaterEqual(len(manifest["warnings"]), 1)

            self.assertEqual(len(data["days"]), 10)
            self.assertEqual(data["days"][6]["title"], "贵阳市区")
            self.assertEqual(data["days"][8]["title"], "重庆市区")

            legs = [leg for day in data["days"] for leg in day["legs"]]
            self.assertEqual(
                [(leg["from"], leg["to"]) for leg in legs],
                [
                    ("合肥", "岳阳"),
                    ("岳阳", "韶山"),
                    ("韶山", "凤凰古城"),
                    ("凤凰古城", "荔波"),
                    ("荔波", "小七孔"),
                    ("小七孔", "中国天眼"),
                    ("中国天眼", "安顺"),
                    ("安顺", "黄果树"),
                    ("黄果树", "贵阳"),
                    ("贵阳", "茅台镇红军桥"),
                    ("茅台镇红军桥", "遵义会议遗址"),
                    ("遵义会议遗址", "重庆"),
                    ("重庆", "合肥"),
                ],
            )
            self.assertEqual(
                [len(day["legs"]) for day in data["days"]],
                [1, 1, 1, 1, 3, 2, 0, 3, 0, 1],
            )
            self.assertEqual(data["days"][6]["notes"], ["贵阳市区"])
            self.assertEqual(data["days"][8]["notes"], ["重庆市区"])
            self.assertTrue(all(leg["origin"] and leg["destination"] for leg in legs))
            chongqing_to_hefei = next(leg for leg in legs if leg["from"] == "重庆" and leg["to"] == "合肥")
            self.assertGreater(chongqing_to_hefei["distance_km"], 1000)
            self.assertNotIn(100.0, [leg["distance_km"] for leg in legs])

            budget = data["budget"]
            assumptions = budget["assumptions"]
            self.assertEqual(
                assumptions["passengers"],
                {
                    "adults": 2,
                    "children_under_1_2m": 1,
                    "children_over_1_2m": 0,
                },
            )
            self.assertEqual(
                assumptions["vehicle"],
                {
                    "type": "ev",
                    "kwh_price_cny": 1.5,
                    "kwh_per_100km": 18.0,
                    "estimated_kwh": round(data["totals"]["distance_km"] * 18 / 100, 1),
                },
            )
            self.assertEqual(assumptions["hotel"], {"nightly_cny": 300.0, "nights": 9})
            self.assertEqual(assumptions["meal"], {"daily_cny": 200.0, "days": 10})
            self.assertEqual(budget["category_totals"]["hotel"], 2700.0)
            self.assertEqual(budget["category_totals"]["meal"], 2000.0)
            self.assertEqual(budget["category_totals"]["attraction"], 1040.0)
            self.assertEqual(budget["category_totals"]["toll"], data["totals"]["toll_cny"])
            self.assertEqual(
                budget["category_totals"]["vehicle_energy"],
                round(data["totals"]["distance_km"] * 18 / 100 * 1.5, 2),
            )
            attraction_amounts = {}
            for item in budget["items"]:
                if item["category"] == "attraction":
                    attraction_amounts[item["label"]] = (
                        attraction_amounts.get(item["label"], 0) + item["amount_cny"]
                    )
            self.assertEqual(
                attraction_amounts,
                {
                    "天眼景区": 180.0,
                    "凤凰古城": 0.0,
                    "黄果树瀑布": 500.0,
                    "小七孔": 360.0,
                },
            )
            self.assertEqual(
                [item["name"] for item in budget["missing_attractions"]],
                ["韶山景区"],
            )
            self.assertEqual(budget["warnings"], [])
            self.assertEqual(
                budget["total_cny"],
                round(sum(budget["category_totals"].values()), 2),
            )
            html = (output_dir / "trip.html").read_text(encoding="utf-8")
            self.assertIn("费用预估", html)
            self.assertIn('href="./budget-summary.', html)
            self.assertIn("下载费用清单图", html)
            self.assertIn(" download>", html)
            self.assertNotIn("html2canvas", html)
            self.assertIn("<span>总费用</span>", html)
            self.assertIn("含过路费等", html)
            self.assertIn("¥1.5/度", html)
            self.assertIn("摆渡车 3 × ¥50", html)
            self.assertIn("function scrollToCurrentDay", html)
            self.assertIn("tab.dataset.tab === 'daily'", html)
            self.assertIn("scrollToCurrentDay('auto')", html)
            self.assertIn("isProgrammaticScroll", html)
            self.assertIn("targetSlide.offsetLeft - daySlider.offsetLeft", html)
            self.assertIn("diffDays < 0 || diffDays >= dayTitles.length", html)
            self.assertEqual(html.count('<div class="budget-label">黄果树瀑布</div>'), 1)
            self.assertEqual(html.count('<div class="budget-label">小七孔</div>'), 1)
            self.assertNotIn("budget-chips", html)
            self.assertNotIn("示例：--vehicle-type", html)
            self.assertIn("data-tab=\"budget\"", html)
            self.assertTrue(budget["configured"])
            self.assertIn("budget", manifest)

    def test_cli_without_budget_shows_activation_reminder(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "input.txt"
            output_dir = Path(tmp) / "trip-output"
            input_path.write_text("""D1
合肥 到 岳阳
D2
岳阳 回 合肥
""", encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(input_path),
                    "--out",
                    str(output_dir),
                    "--title",
                    "无预算 Demo",
                    "--no-api",
                ],
                check=True,
                text=True,
                capture_output=True,
            )

            data = json.loads((output_dir / "trip-data.json").read_text(encoding="utf-8"))
            html = (output_dir / "trip.html").read_text(encoding="utf-8")

            self.assertFalse(data["budget"]["configured"])
            self.assertIsNone(
                json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))["files"]["budget_image"]
            )
            self.assertIn("费用计算未启用", html)
            self.assertIn("你可以这样说", html)
            self.assertIn("<span>过路费</span>", html)
            self.assertIn("估算参考", html)

    def test_budget_arguments_generate_cost_tab_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "input.txt"
            output_dir = Path(tmp) / "trip-output"
            route_text, _budget_text = self.route_trip.split_budget_section(
                (ROOT / "examples" / "simple-trip.txt").read_text(encoding="utf-8")
            )
            input_path.write_text(route_text, encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(input_path),
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
            self.assertIn(manifest["files"]["budget_image"], ("budget-summary.png", "budget-summary.svg"))
            toll_item = next(item for item in budget["items"] if item["category"] == "toll")
            energy_item = next(item for item in budget["items"] if item["category"] == "vehicle_energy")
            self.assertIn("全程", toll_item["detail"])
            self.assertIn("公里 · 来自路线数据", toll_item["detail"])
            self.assertIn("16 度/百公里", energy_item["detail"])
            self.assertIn("= ", energy_item["detail"])
            self.assertIn("费用预估", html)
            self.assertIn("小七孔", html)
            self.assertNotIn("budget-chips", html)

    def test_natural_language_budget_derives_days_and_child_ticket_rules(self):
        route_text, _budget_text = self.route_trip.split_budget_section(
            (ROOT / "examples" / "simple-trip.txt").read_text(encoding="utf-8")
        )
        text = route_text + """

费用预算：
我们是两大一小（低于 1.2m），开电车，电价 1.5 元/度，百公里电耗 16 度。
酒店每晚 300 元，餐费每天 100 元。
景点门票：小七孔成人票 120 元，中国天眼成人票 140 元。
其他费用：停车费 100 元，杂费 200 元。
"""
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "input.txt"
            output_dir = Path(tmp) / "trip-output"
            input_path.write_text(text, encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(input_path),
                    "--out",
                    str(output_dir),
                    "--mode",
                    "estimate",
                ],
                check=True,
                text=True,
                capture_output=True,
            )

            data = json.loads((output_dir / "trip-data.json").read_text(encoding="utf-8"))
            html = (output_dir / "trip.html").read_text(encoding="utf-8")
            budget = data["budget"]
            attraction_items = [item for item in budget["items"] if item["category"] == "attraction"]

            self.assertTrue(budget["configured"])
            self.assertEqual(data["days"][-1].get("notes") or [], [])
            self.assertEqual(budget["assumptions"]["hotel"]["nights"], 9)
            self.assertEqual(budget["assumptions"]["meal"]["days"], 10)
            self.assertEqual(budget["assumptions"]["passengers"]["adults"], 2)
            self.assertEqual(budget["assumptions"]["passengers"]["children_under_1_2m"], 1)
            self.assertEqual(budget["assumptions"]["passengers"]["children_over_1_2m"], 0)
            self.assertEqual(budget["category_totals"]["hotel"], 2700.0)
            self.assertEqual(budget["category_totals"]["meal"], 1000.0)
            self.assertEqual(budget["category_totals"]["attraction"], 520.0)
            self.assertEqual(budget["category_totals"]["misc"], 300.0)
            self.assertEqual([item["label"] for item in attraction_items], ["小七孔", "中国天眼"])
            self.assertEqual([item["amount_cny"] for item in attraction_items], [240.0, 280.0])
            self.assertIn("1.2m 以下儿童 1 人免票", html)

    def test_natural_language_budget_child_over_1_2m_uses_half_price(self):
        parsed = self.route_trip.parse_budget_text("""费用预算：
两大一小（高于 1.2m）。
景点门票：小七孔成人票 120 元。
""")
        data = {
            "days": [{"day": "D1", "legs": [], "distance_km": 0.0, "duration_min": 0, "toll_cny": 0}],
            "totals": {"distance_km": 0.0, "duration_min": 0, "toll_cny": 0},
        }
        budget = self.route_trip.build_budget(
            data,
            attractions=parsed["attractions"],
            passengers=parsed["passengers"],
        )

        self.assertEqual(budget["assumptions"]["passengers"]["adults"], 2)
        self.assertEqual(budget["assumptions"]["passengers"]["children_over_1_2m"], 1)
        self.assertEqual(budget["category_totals"]["attraction"], 300.0)
        self.assertEqual(budget["items"][0]["detail"], "成人 2 × ¥120；1.2m 以上儿童 1 × ¥60")

    def test_budget_section_can_start_on_same_line(self):
        itinerary_text, budget_text = self.route_trip.split_budget_section("""D1
合肥 到 岳阳
费用预算：两大一小（低于 1.2m），酒店每晚 300 元。
""")
        parsed = self.route_trip.parse_budget_text(budget_text)

        self.assertIn("合肥 到 岳阳", itinerary_text)
        self.assertEqual(parsed["passengers"]["adults"], 2)
        self.assertEqual(parsed["passengers"]["children_under_1_2m"], 1)
        self.assertEqual(parsed["hotel_nightly"], 300.0)

    def test_budget_parser_accepts_approximate_amounts(self):
        parsed = self.route_trip.parse_budget_text("费用预算：餐费每天约100元，酒店一晚300元左右，电价约人民币1.5元/度，百公里电耗16度左右。")

        self.assertEqual(parsed["meal_daily"], 100.0)
        self.assertEqual(parsed["hotel_nightly"], 300.0)
        self.assertEqual(parsed["ev_kwh_price"], 1.5)
        self.assertEqual(parsed["ev_kwh_per_100km"], 16.0)
        self.assertEqual(parsed["warnings"], [])

    def test_build_budget_deduplicates_external_and_derived_warnings(self):
        warning = "Vehicle is EV but --ev-kwh-price or --ev-kwh-per-100km is missing; energy cost skipped."
        data = {
            "days": [{"day": "D1", "legs": []}],
            "totals": {"distance_km": 0.0, "duration_min": 0, "toll_cny": 0.0},
        }

        budget = self.route_trip.build_budget(
            data,
            vehicle_type="ev",
            warnings=[warning, warning, "  Check price  "],
        )

        self.assertEqual(budget["warnings"], [warning, "Check price"])

    def test_budget_range_warning_is_persisted_to_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "input.txt"
            output_dir = Path(tmp) / "trip-output"
            input_path.write_text("""D1
合肥 到 岳阳
D2
岳阳 回 合肥

费用预算：
酒店每晚 300-400 元，餐费每天 100 元。
""", encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(input_path),
                    "--out",
                    str(output_dir),
                    "--mode",
                    "data-only",
                ],
                check=True,
                text=True,
                capture_output=True,
            )

            data = json.loads((output_dir / "trip-data.json").read_text(encoding="utf-8"))
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            warning = "Hotel budget range was provided; use a single nightly amount or --hotel-nightly for totals."

            self.assertIn(warning, data["budget"]["warnings"])
            self.assertIn(warning, manifest["warnings"])
            self.assertNotIn("hotel", data["budget"]["category_totals"])
            self.assertEqual(data["budget"]["category_totals"]["meal"], 200.0)

    def test_budget_parser_rejects_ev_and_attraction_ranges(self):
        parsed = self.route_trip.parse_budget_text(
            "费用预算：开电车，电价 1.2-1.5 元/度，百公里电耗 16-18 度左右。景点门票：小七孔成人票 100-120元左右，摆渡车 40-50 元一人。其他费用：停车费 20-30 元，杂费 10 元。"
        )

        self.assertEqual(parsed["attractions"], [])
        self.assertEqual(parsed["misc_fees"], [{"name": "杂费", "amount_cny": 10.0}])
        self.assertNotIn("ev_kwh_price", parsed)
        self.assertNotIn("ev_kwh_per_100km", parsed)
        self.assertIn("EV electricity price range was provided; use a single CNY/kWh amount or --ev-kwh-price for totals.", parsed["warnings"])
        self.assertIn("EV consumption range was provided; use a single kWh/100km amount or --ev-kwh-per-100km for totals.", parsed["warnings"])
        self.assertIn("Attraction or component fee range was provided; use a single amount or --attraction for totals.", parsed["warnings"])
        self.assertIn("Misc fee range was provided; use a single amount or --misc-fee for totals.", parsed["warnings"])

    def test_budget_range_warnings_for_ev_and_attractions_reach_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "input.txt"
            output_dir = Path(tmp) / "trip-output"
            input_path.write_text("""D1
荔波 到 小七孔

费用预算：
开电车，电价 1.2-1.5 元/度，百公里电耗 16-18 度。
景点门票：小七孔成人票 100-120 元。
其他费用：停车费 20-30 元。
""", encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(input_path),
                    "--out",
                    str(output_dir),
                    "--mode",
                    "data-only",
                ],
                check=True,
                text=True,
                capture_output=True,
            )

            data = json.loads((output_dir / "trip-data.json").read_text(encoding="utf-8"))
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

            self.assertNotIn("vehicle_energy", data["budget"]["category_totals"])
            self.assertNotIn("attraction", data["budget"]["category_totals"])
            self.assertTrue(any("EV electricity price range" in warning for warning in manifest["warnings"]))
            self.assertTrue(any("EV consumption range" in warning for warning in manifest["warnings"]))
            self.assertTrue(any("Attraction or component fee range" in warning for warning in manifest["warnings"]))
            self.assertTrue(any("Misc fee range" in warning for warning in manifest["warnings"]))
            self.assertTrue(any("Vehicle is EV" in warning for warning in manifest["warnings"]))

    def test_leading_budget_text_supports_scenic_list_and_combined_ev_consumption(self):
        itinerary_text, budget_text = self.route_trip.split_budget_section("""我们是两大一小（低于 1.2m），
开电车，电价 1.5 元/度，百公里综合电耗 18 度；
酒店每晚 300 元，
餐费每天 200 元；
景区：韶山景区、黄果树瀑布、小七孔，天眼景区（门票不要钱，摆渡车 50 元一人，保险 10 元一人），凤凰古城免费。
已确认景区价格：黄果树瀑布成人票 160 元。

D1
合肥 到 岳阳
D2
岳阳 到 韶山
""")
        parsed = self.route_trip.parse_budget_text(budget_text)

        self.assertIn("合肥 到 岳阳", itinerary_text)
        self.assertNotIn("百公里综合电耗", itinerary_text)
        self.assertEqual(parsed["ev_kwh_per_100km"], 18.0)
        self.assertEqual(parsed["meal_daily"], 200.0)
        self.assertEqual([item["name"] for item in parsed["attractions"]], ["天眼景区", "凤凰古城", "黄果树瀑布"])

    def test_leading_budget_text_splits_before_inline_day_label(self):
        itinerary_text, budget_text = self.route_trip.split_budget_section("""两大一小（低于 1.2m），酒店每晚 300 元。

D1：合肥 到 岳阳
D2：岳阳 到 韶山
""")
        days = self.route_trip.parse_itinerary(itinerary_text)
        parsed = self.route_trip.parse_budget_text(budget_text)

        self.assertEqual([day["day"] for day in days], ["D1", "D2"])
        self.assertEqual(days[0]["legs"], [{"from": "合肥", "to": "岳阳"}])
        self.assertEqual(parsed["hotel_nightly"], 300.0)

    def test_leading_budget_heading_splits_before_day_label(self):
        itinerary_text, budget_text = self.route_trip.split_budget_section("""费用预算：
两大一小（低于 1.2m），酒店每晚 300 元。

D1
合肥 到 岳阳
D2
岳阳 到 韶山
""")
        days = self.route_trip.parse_itinerary(itinerary_text)
        parsed = self.route_trip.parse_budget_text(budget_text)

        self.assertEqual([day["day"] for day in days], ["D1", "D2"])
        self.assertIn("费用预算", budget_text)
        self.assertEqual(parsed["hotel_nightly"], 300.0)

    def test_leading_budget_text_splits_before_chinese_day_label(self):
        itinerary_text, budget_text = self.route_trip.split_budget_section("""两大一小（低于 1.2m），酒店每晚 300 元。

第1天：合肥 到 岳阳
第二天 岳阳 到 韶山
""")
        days = self.route_trip.parse_itinerary(itinerary_text)
        parsed = self.route_trip.parse_budget_text(budget_text)

        self.assertEqual([day["day"] for day in days], ["D1", "D2"])
        self.assertEqual(days[0]["legs"], [{"from": "合肥", "to": "岳阳"}])
        self.assertEqual(parsed["hotel_nightly"], 300.0)

    def test_cli_leading_budget_heading_generates_route_and_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "input.txt"
            output_dir = Path(tmp) / "trip-output"
            input_path.write_text("""费用预算：
酒店每晚 300 元，餐费每天 100 元。

D1
合肥 到 岳阳
D5
岳阳 到 合肥
""", encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(input_path),
                    "--out",
                    str(output_dir),
                    "--mode",
                    "data-only",
                ],
                check=True,
                text=True,
                capture_output=True,
            )

            data = json.loads((output_dir / "trip-data.json").read_text(encoding="utf-8"))

            self.assertEqual([day["day"] for day in data["days"]], ["D1", "D5"])
            self.assertEqual(len([leg for day in data["days"] for leg in day["legs"]]), 2)
            self.assertEqual(data["budget"]["assumptions"]["trip_days"], 5)
            self.assertEqual(data["budget"]["category_totals"]["hotel"], 1200.0)
            self.assertEqual(data["budget"]["category_totals"]["meal"], 500.0)

    def test_attraction_components_support_free_ticket_and_per_person_fees(self):
        parsed = self.route_trip.parse_budget_text("""费用预算：
两大一小（低于 1.2m）。
景点门票：天眼景区门票不要钱，摆渡车 50 元一人，保险 10 元一人。
""")
        data = {
            "days": [{"day": "D1", "legs": [], "distance_km": 0.0, "duration_min": 0, "toll_cny": 0}],
            "totals": {"distance_km": 0.0, "duration_min": 0, "toll_cny": 0},
        }
        budget = self.route_trip.build_budget(
            data,
            attractions=parsed["attractions"],
            passengers=parsed["passengers"],
        )

        self.assertEqual(len(parsed["attractions"]), 1)
        self.assertEqual(parsed["attractions"][0]["name"], "天眼景区")
        self.assertEqual(budget["category_totals"]["attraction"], 180.0)
        self.assertEqual(budget["items"][0]["label"], "天眼景区")
        self.assertEqual(budget["items"][0]["detail"], "门票免费；摆渡车 3 × ¥50；保险 3 × ¥10")
        self.assertEqual([component["amount_cny"] for component in budget["items"][0]["components"]], [0.0, 150.0, 30.0])

    def test_route_scenic_spots_without_fees_are_reported_but_not_totaled(self):
        parsed = self.route_trip.parse_budget_text("""费用预算：
两大一小（低于 1.2m）。
景点门票：天眼景区门票不要钱，摆渡车 50 元一人，保险 10 元一人。
""")
        data = self.route_trip.enrich(self.route_trip.parse_itinerary("""D1
岳阳 到 韶山
D2
荔波 到 小七孔
D3
小七孔 到 中国天眼
D4
安顺 到 黄果树
"""), use_api=False)
        budget = self.route_trip.build_budget(
            data,
            attractions=parsed["attractions"],
            passengers=parsed["passengers"],
        )
        missing_names = [item["name"] for item in budget["missing_attractions"]]

        self.assertEqual(budget["category_totals"]["attraction"], 180.0)
        self.assertNotIn("中国天眼景区", missing_names)
        self.assertEqual(missing_names, ["韶山景区", "荔波小七孔景区", "黄果树瀑布景区"])
        self.assertEqual(budget["missing_attractions"][1]["matched_names"], ["小七孔"])

    def test_single_line_budget_does_not_parse_energy_hotel_meal_as_attractions(self):
        parsed = self.route_trip.parse_budget_text(
            "我们是两大一小（低于 1.2m），开电车，电价 1.5 元/度，百公里电耗 16 度；酒店每晚 300 元，餐费每天 100 元；天眼景区门票不要钱，摆渡车 50 元一人，保险 10 元一人。"
        )
        data = {
            "days": [{"day": f"D{index}", "legs": [], "distance_km": 0.0, "duration_min": 0, "toll_cny": 0} for index in range(1, 11)],
            "totals": {"distance_km": 1000.0, "duration_min": 0, "toll_cny": 0},
        }
        budget = self.route_trip.build_budget(
            data,
            vehicle_type=parsed.get("vehicle_type", "none"),
            ev_kwh_price=parsed.get("ev_kwh_price"),
            ev_kwh_per_100km=parsed.get("ev_kwh_per_100km"),
            hotel_nightly=parsed.get("hotel_nightly"),
            meal_daily=parsed.get("meal_daily"),
            attractions=parsed["attractions"],
            passengers=parsed["passengers"],
        )
        attraction_labels = [item["label"] for item in budget["items"] if item["category"] == "attraction"]

        self.assertEqual(attraction_labels, ["天眼景区"])
        self.assertEqual(budget["category_totals"]["attraction"], 180.0)
        self.assertEqual(budget["category_totals"]["hotel"], 2700.0)
        self.assertEqual(budget["category_totals"]["meal"], 1000.0)
        self.assertEqual(budget["category_totals"]["vehicle_energy"], 240.0)
        energy_item = next(item for item in budget["items"] if item["category"] == "vehicle_energy")
        self.assertEqual(energy_item["detail"], "全程 1000 公里 × 16 度/百公里 = 160 度 × ¥1.5/度")

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
            self.assertTrue((output_dir / "budget-summary.svg").is_file())
            self.assertEqual(data["map"]["source"], "fallback-svg")
            self.assertTrue(data["map"]["fallback"])
            self.assertEqual(manifest["files"]["map_image"], "route-map.svg")
            self.assertEqual(manifest["files"]["budget_image"], "budget-summary.svg")

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
            self.assertFalse((output_dir / "budget-summary.png").exists())
            self.assertFalse((output_dir / "budget-summary.svg").exists())
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["mode"], "data-only")
            self.assertIsNone(manifest["files"]["html"])
            self.assertIsNone(manifest["files"]["map_image"])
            self.assertIsNone(manifest["files"]["budget_image"])

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
                cwd=tmp,
            )

            self.assertEqual(result.returncode, 3)
            self.assertIn("requires AMAP_KEY or GAODE_KEY", result.stderr)

    def test_cli_invalid_day_label_returns_clean_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "bad.txt"
            output_dir = Path(tmp) / "out"
            input_path.write_text("D0\n合肥 到 岳阳\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(input_path),
                    "--out",
                    str(output_dir),
                    "--mode",
                    "estimate",
                ],
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("Day numbers must start at 1", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(output_dir.exists())

    def test_cli_duplicate_day_label_returns_clean_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "bad.txt"
            output_dir = Path(tmp) / "out"
            input_path.write_text("D1：合肥 到 岳阳\nD1 岳阳 到 韶山\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(input_path),
                    "--out",
                    str(output_dir),
                    "--mode",
                    "estimate",
                ],
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("Duplicate day label: D1", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(output_dir.exists())

    def test_cli_note_only_input_returns_clean_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "bad.txt"
            output_dir = Path(tmp) / "out"
            input_path.write_text("D1\n贵阳市区\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(input_path),
                    "--out",
                    str(output_dir),
                    "--mode",
                    "estimate",
                ],
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("No route legs found", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(output_dir.exists())


if __name__ == "__main__":
    unittest.main()
