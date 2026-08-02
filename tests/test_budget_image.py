import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "budget_image.py"


def load_budget_image():
    spec = importlib.util.spec_from_file_location("budget_image", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sample_data() -> dict:
    return {
        "title": "黔湘 <暑假> 自驾",
        "start_date": "2026-07-17",
        "days": [
            {
                "day": "D1",
                "legs": [{"from": "合肥", "to": "岳阳"}],
            },
            {
                "day": "D3",
                "legs": [{"from": "岳阳", "to": "合肥"}],
            },
        ],
        "totals": {"distance_km": 1234.5},
        "budget": {
            "configured": True,
            "total_cny": 3456.7,
            "category_totals": {"toll": 1200.0, "hotel": 2256.7},
            "items": [
                {"category": "toll", "label": "过路费", "detail": "来自路线数据", "amount_cny": 1200.0},
                {"category": "hotel", "label": "住宿", "detail": "2 晚 × ¥1128.35", "amount_cny": 2256.7},
            ],
            "missing_attractions": [{"name": "黄果树"}],
            "assumptions": {
                "passengers": {
                    "adults": 2,
                    "children_under_1_2m": 1,
                    "children_over_1_2m": 0,
                }
            },
        },
    }


class BudgetImageTests(unittest.TestCase):
    def setUp(self):
        self.budget_image = load_budget_image()

    def test_eligibility_requires_configured_budget_items(self):
        data = sample_data()
        self.assertTrue(self.budget_image.budget_image_eligible(data))
        data["budget"]["items"] = []
        self.assertFalse(self.budget_image.budget_image_eligible(data))

    def test_svg_has_fixed_layout_and_escaped_editorial_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "budget-summary.svg"
            self.budget_image.generate_budget_summary_svg(sample_data(), path)

            raw = path.read_text(encoding="utf-8")
            root = ElementTree.parse(path).getroot()
            self.assertEqual(root.get("width"), "1600")
            self.assertEqual(root.get("height"), "1000")
            self.assertIn("黔湘 &lt;暑假&gt; 自驾", raw)
            self.assertIn("¥3,457", raw)
            self.assertIn("待补费用：黄果树", raw)
            self.assertNotIn("TRIP BUDGET", raw)
            self.assertIn('clip-path="url(#budget-bar-clip)"', raw)
            self.assertIn("基础费用", raw)
            self.assertIn("景点费用", raw)
            self.assertIn('data-icon="car"', raw)
            self.assertIn(self.budget_image.leaflet_map.SHARE_CREDIT, raw)
            self.assertNotIn("SELF-DRIVE TRIP PLANNER", raw)

    def test_detail_columns_merge_same_attraction(self):
        items = [
            {"category": "toll", "label": "过路费", "amount_cny": 100, "detail": "路线"},
            {"category": "attraction", "label": "黄果树", "amount_cny": 320, "detail": "门票"},
            {"category": "attraction", "label": "黄果树", "amount_cny": 180, "detail": "观光车"},
        ]

        basic, attractions, hidden = self.budget_image.detail_item_columns(items)

        self.assertEqual([item["label"] for item in basic], ["过路费"])
        self.assertEqual(len(attractions), 1)
        self.assertEqual(attractions[0]["amount_cny"], 500)
        self.assertEqual(attractions[0]["detail"], "门票；观光车")
        self.assertEqual(hidden, 0)

    def test_each_budget_category_has_a_lucide_icon(self):
        for category, icon_name in self.budget_image.CATEGORY_ICONS.items():
            self.assertIn(
                f'data-icon="{icon_name}"',
                self.budget_image.svg_icon(category, 0, 0),
            )

    def test_generate_image_uses_svg_fallback_without_playwright(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            with mock.patch.object(self.budget_image, "render_budget_summary_png", return_value=False):
                filename = self.budget_image.generate_budget_summary_image(sample_data(), out_dir)

            self.assertEqual(filename, "budget-summary.svg")
            self.assertTrue((out_dir / filename).is_file())
            self.assertFalse((out_dir / "budget-summary.png").exists())

    def test_generate_image_records_png_failure_and_removes_partial_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)

            def fail_render(_svg_path, png_path):
                png_path.write_bytes(b"partial")
                raise RuntimeError("browser failed")

            data = sample_data()
            with mock.patch.object(self.budget_image, "render_budget_summary_png", side_effect=fail_render):
                filename = self.budget_image.generate_budget_summary_image(data, out_dir)

            self.assertEqual(filename, "budget-summary.svg")
            self.assertEqual(data["budget_image_png_error"], "browser failed")
            self.assertFalse((out_dir / "budget-summary.png").exists())

    def test_png_renderer_uses_discovered_playwright_interpreter(self):
        with tempfile.TemporaryDirectory() as tmp:
            svg_path = Path(tmp) / "budget-summary.svg"
            png_path = Path(tmp) / "budget-summary.png"
            svg_path.write_text('<svg width="1600" height="1000"></svg>', encoding="utf-8")
            png_path.write_bytes(b"x" * 10001)
            completed = mock.Mock(returncode=0, stdout="OK\n", stderr="")
            with mock.patch.object(self.budget_image.leaflet_map, "find_playwright_python", return_value="/opt/pw/python"):
                with mock.patch.object(self.budget_image.subprocess, "run", return_value=completed) as run:
                    self.assertTrue(self.budget_image.render_budget_summary_png(svg_path, png_path))

            self.assertEqual(run.call_args.args[0][0], "/opt/pw/python")
            self.assertIn("device_scale_factor=2", run.call_args.args[0][2])


if __name__ == "__main__":
    unittest.main()
