import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "leaflet_map.py"


def load_leaflet_map():
    spec = importlib.util.spec_from_file_location("leaflet_map", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LeafletMapTests(unittest.TestCase):
    def setUp(self):
        self.leaflet_map = load_leaflet_map()

    def test_embedded_map_data_is_script_safe(self):
        malicious = '</script><img src=x onerror="alert(1)">'
        data = {
            "title": "Safe Map",
            "totals": {"distance_km": 1.0, "duration_min": 1, "toll_cny": 0},
            "days": [
                {
                    "day": "D1",
                    "title": malicious,
                    "distance_km": 1.0,
                    "duration_min": 1,
                    "toll_cny": 0,
                    "estimated": True,
                    "legs": [
                        {
                            "from": malicious,
                            "to": "终点",
                            "distance_km": 1.0,
                            "duration_min": 1,
                            "toll_cny": 0,
                            "estimated": True,
                            "origin": {"lng": 117.0, "lat": 31.0},
                            "destination": {"lng": 118.0, "lat": 32.0},
                            "polyline": [[117.0, 31.0], [118.0, 32.0]],
                        }
                    ],
                }
            ],
        }

        snippet = self.leaflet_map.build_leaflet_snippet(data)

        self.assertIn("function escapeHtml", snippet)
        self.assertNotIn("</script><img", snippet)
        self.assertNotIn("<img src=x", snippet)
        self.assertIn("\\u003c/script\\u003e", snippet)
        self.assertIn("\\u003cimg", snippet)

    def test_screenshot_legend_escapes_user_text(self):
        malicious = '</script><img src=x onerror="alert(1)">'
        data = {
            "title": malicious,
            "totals": {"distance_km": 1.0, "duration_min": 1, "toll_cny": 0},
            "days": [
                {
                    "day": "D1",
                    "title": malicious,
                    "distance_km": 1.0,
                    "duration_min": 1,
                    "toll_cny": 0,
                    "estimated": True,
                    "legs": [],
                }
            ],
        }

        page = self.leaflet_map._full_page_html(data)

        self.assertNotIn(malicious, page)
        self.assertIn("&lt;/script&gt;&lt;img", page)
        self.assertIn(self.leaflet_map.SHARE_CREDIT, page)
        self.assertIn('class="share-credit"', page)

    def test_route_png_preserves_browser_failure_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "route-map.png"
            failure = SimpleNamespace(returncode=1, stdout="", stderr="browser crashed")
            with (
                patch.object(self.leaflet_map, "find_playwright_python", return_value="/playwright/python"),
                patch.object(self.leaflet_map.subprocess, "run", return_value=failure),
            ):
                with self.assertRaisesRegex(RuntimeError, "browser crashed"):
                    self.leaflet_map.render_route_png({}, output)


if __name__ == "__main__":
    unittest.main()
