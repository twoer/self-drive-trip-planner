import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "output_assets.py"


def load_output_assets():
    spec = importlib.util.spec_from_file_location("output_assets", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class OutputAssetsTests(unittest.TestCase):
    def setUp(self):
        self.output_assets = load_output_assets()

    def test_generate_pdf_uses_discovered_playwright_interpreter(self):
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "trip.html"
            pdf_path = Path(tmp) / "trip.pdf"
            html_path.write_text("<html><body>trip</body></html>", encoding="utf-8")
            def fake_run(command, **kwargs):
                self.assertEqual(command[:2], ["/playwright/python", "-c"])
                self.assertIn(str(html_path.resolve()), command[2])
                pdf_path.write_bytes(b"%PDF-1.7\n%%EOF")
                return SimpleNamespace(returncode=0, stdout="OK\n", stderr="")

            with (
                patch.object(self.output_assets.leaflet_map, "find_playwright_python", return_value="/playwright/python"),
                patch.object(self.output_assets.subprocess, "run", side_effect=fake_run),
            ):
                self.assertTrue(self.output_assets.generate_pdf(html_path, pdf_path))

    def test_generate_pdf_reports_subprocess_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "trip.html"
            pdf_path = Path(tmp) / "trip.pdf"
            html_path.write_text("<html></html>", encoding="utf-8")
            failure = SimpleNamespace(returncode=1, stdout="", stderr="browser launch failed")
            with (
                patch.object(self.output_assets.leaflet_map, "find_playwright_python", return_value="/playwright/python"),
                patch.object(self.output_assets.subprocess, "run", return_value=failure),
            ):
                with self.assertRaisesRegex(RuntimeError, "browser launch failed"):
                    self.output_assets.generate_pdf(html_path, pdf_path)

    def test_route_svg_fallback_contains_share_credit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "route-map.svg"
            data = {
                "title": "Fallback",
                "days": [],
                "totals": {"distance_km": 0.0, "duration_min": 0, "toll_cny": 0.0},
            }

            self.output_assets.generate_svg(data, path)

            self.assertIn(
                self.output_assets.leaflet_map.SHARE_CREDIT,
                path.read_text(encoding="utf-8"),
            )

    def test_route_map_fallback_records_playwright_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = {
                "title": "Fallback",
                "days": [],
                "totals": {"distance_km": 0.0, "duration_min": 0, "toll_cny": 0.0},
            }

            def fake_svg(value, path):
                path.write_text('<svg><path d="M0 0"/></svg>', encoding="utf-8")

            with (
                patch.object(
                    self.output_assets.leaflet_map,
                    "render_route_png",
                    side_effect=RuntimeError("browser crashed"),
                ),
                patch.object(self.output_assets, "generate_svg", side_effect=fake_svg),
            ):
                map_file = self.output_assets.generate_route_map(data, out_dir, key=None)

            self.assertEqual(map_file, "route-map.svg")
            self.assertEqual(data["map_png_error"], "browser crashed")
            self.assertTrue(data["map"]["fallback"])

    def test_route_map_records_svg_failure_after_png_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = {"title": "Failure", "days": [], "totals": {}}
            with (
                patch.object(
                    self.output_assets.leaflet_map,
                    "render_route_png",
                    side_effect=RuntimeError("browser crashed"),
                ),
                patch.object(self.output_assets, "generate_svg", side_effect=OSError("disk full")),
            ):
                map_file = self.output_assets.generate_route_map(data, Path(tmp), key=None)

            self.assertIsNone(map_file)
            self.assertEqual(data["map_png_error"], "browser crashed")
            self.assertEqual(data["map_svg_error"], "disk full")


if __name__ == "__main__":
    unittest.main()
