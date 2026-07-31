import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "editor_server.py"


def load_editor_server():
    spec = importlib.util.spec_from_file_location("editor_server", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class EditorServerTests(unittest.TestCase):
    def setUp(self):
        self.editor = load_editor_server()

    def test_parse_editor_text_splits_budget_and_days(self):
        result = self.editor.parse_editor_text("""我们是两大一小（低于 1.2m），开电车，电价 1.5 元/度。

D1
合肥 到 岳阳
D2
岳阳市区
D3
岳阳 回 合肥
""")

        self.assertEqual(result["budget_text"], "我们是两大一小（低于 1.2m），开电车，电价 1.5 元/度。")
        self.assertEqual([day["day"] for day in result["days"]], ["D1", "D2", "D3"])
        self.assertEqual(result["days"][0]["legs"], [{"from": "合肥", "to": "岳阳"}])
        self.assertEqual(result["days"][1]["notes"], ["岳阳市区"])

    def test_trip_payload_to_text_preserves_day_cards(self):
        text = self.editor.trip_payload_to_text({
            "budget_text": "酒店每晚 300 元。",
            "days": [
                {"day": "D1", "legs": [{"from": "合肥", "to": "岳阳"}], "notes": []},
                {"day": "D2", "legs": [], "notes": ["岳阳市区"]},
            ],
        })

        self.assertIn("酒店每晚 300 元。", text)
        self.assertIn("D1\n合肥 到 岳阳", text)
        self.assertIn("D2\n岳阳市区", text)

    def test_generate_from_payload_writes_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.editor.generate_from_payload(
                {
                    "title": "编辑器 Demo",
                    "mode": "estimate",
                    "start_date": "2026-07-17",
                    "days": [
                        {"day": "D1", "legs": [{"from": "合肥", "to": "岳阳"}], "notes": []},
                        {"day": "D2", "legs": [{"from": "岳阳", "to": "合肥"}], "notes": []},
                    ],
                    "budget_text": "酒店每晚 300 元，餐费每天 100 元。",
                },
                out_dir=Path(tmp),
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["manifest"]["mode"], "estimate")
            self.assertEqual(result["manifest"]["title"], "编辑器 Demo")
            self.assertTrue((Path(tmp) / "manifest.json").is_file())
            self.assertTrue((Path(tmp) / "trip.html").is_file())

    def test_api_error_is_json(self):
        payload = self.editor.error_payload("bad json", status=400)

        self.assertEqual(payload["status"], 400)
        self.assertEqual(json.loads(payload["body"])["error"], "bad json")
        self.assertEqual(payload["headers"]["Content-Type"], "application/json; charset=utf-8")


if __name__ == "__main__":
    unittest.main()
