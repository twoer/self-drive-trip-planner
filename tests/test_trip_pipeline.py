import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "trip_pipeline.py"


def load_trip_pipeline():
    spec = importlib.util.spec_from_file_location("trip_pipeline", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TripPipelineTests(unittest.TestCase):
    def setUp(self):
        self.trip_pipeline = load_trip_pipeline()

    def test_resolve_mode_estimate_clears_key(self):
        mode, key, use_api = self.trip_pipeline.resolve_mode("estimate", False, "secret")

        self.assertEqual(mode, "estimate")
        self.assertIsNone(key)
        self.assertFalse(use_api)

    def test_mode_contract_constants_drive_resolution(self):
        self.assertEqual(self.trip_pipeline.API_CAPABLE_MODES, ("auto", "accurate", "publish-demo", "data-only"))
        self.assertEqual(self.trip_pipeline.KEY_REQUIRED_MODES, ("accurate", "publish-demo"))

        mode, key, use_api = self.trip_pipeline.resolve_mode("data-only", False, "secret")

        self.assertEqual(mode, "data-only")
        self.assertEqual(key, "secret")
        self.assertTrue(use_api)

    def test_default_output_dir_uses_docs_for_publish_demo(self):
        self.assertEqual(self.trip_pipeline.default_output_dir("publish-demo", None), Path("docs"))
        self.assertEqual(self.trip_pipeline.default_output_dir("estimate", None), Path("trip-output"))
        self.assertEqual(self.trip_pipeline.default_output_dir("estimate", "custom"), Path("custom"))

    def test_build_trip_data_merges_natural_budget_and_cli_overrides(self):
        data = self.trip_pipeline.build_trip_data(
            """两大一小（低于 1.2m），开电车，电价 1.5 元/度。
酒店每晚 300 元。

D1
合肥 到 岳阳
D2
岳阳 回 合肥
""",
            title="Pipeline Demo",
            start_date="2026-07-17",
            use_api=False,
            meal_daily=100,
            children_over_1_2m=1,
        )

        self.assertEqual(data["title"], "Pipeline Demo")
        self.assertEqual(data["start_date"], "2026-07-17")
        self.assertEqual(len([leg for day in data["days"] for leg in day["legs"]]), 2)
        self.assertTrue(data["budget"]["configured"])
        self.assertEqual(data["budget"]["assumptions"]["passengers"]["children_over_1_2m"], 1)
        self.assertEqual(data["budget"]["category_totals"]["hotel"], 300.0)
        self.assertEqual(data["budget"]["category_totals"]["meal"], 200.0)

    def test_build_trip_data_rejects_note_only_input(self):
        with self.assertRaisesRegex(ValueError, "No route legs found"):
            self.trip_pipeline.build_trip_data(
                """D1
贵阳市区
""",
                title="No Legs",
                use_api=False,
            )

    def test_write_outputs_generates_manifest_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = self.trip_pipeline.build_trip_data(
                """D1
合肥 到 岳阳
""",
                title="Data Only",
                use_api=False,
            )

            manifest = self.trip_pipeline.write_outputs(data, out_dir, key=None, mode="data-only")

            self.assertEqual(manifest["mode"], "data-only")
            self.assertTrue((out_dir / "trip-data.json").is_file())
            self.assertTrue((out_dir / "manifest.json").is_file())
            self.assertIsNone(manifest["files"]["html"])
            self.assertIsNone(manifest["files"]["map_image"])
            self.assertIsNone(manifest["files"]["budget_image"])

    def test_write_outputs_removes_stale_files_when_reusing_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = self.trip_pipeline.build_trip_data(
                """D1
合肥 到 岳阳
""",
                title="Reusable Output",
                use_api=False,
            )
            for filename in (
                "trip.html",
                "index.html",
                "route-map.png",
                "route-map.svg",
                "budget-summary.png",
                "budget-summary.svg",
                "trip.pdf",
            ):
                (out_dir / filename).write_text("stale", encoding="utf-8")

            manifest = self.trip_pipeline.write_outputs(data, out_dir, key=None, mode="data-only")

            self.assertIsNone(manifest["files"]["html"])
            self.assertIsNone(manifest["files"]["map_image"])
            self.assertFalse((out_dir / "trip.html").exists())
            self.assertFalse((out_dir / "index.html").exists())
            self.assertFalse((out_dir / "route-map.png").exists())
            self.assertFalse((out_dir / "route-map.svg").exists())
            self.assertFalse((out_dir / "budget-summary.png").exists())
            self.assertFalse((out_dir / "budget-summary.svg").exists())
            self.assertFalse((out_dir / "trip.pdf").exists())

    def test_write_outputs_preserves_previous_output_when_generation_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "trip-output"
            out_dir.mkdir()
            previous_files = {
                "trip-data.json": "old data",
                "manifest.json": "old manifest",
                "trip.html": "old html",
                "route-map.svg": "old map",
            }
            for filename, content in previous_files.items():
                (out_dir / filename).write_text(content, encoding="utf-8")
            (out_dir / "notes.txt").write_text("keep me", encoding="utf-8")
            data = self.trip_pipeline.build_trip_data(
                """D1
合肥 到 岳阳
""",
                title="Transactional Output",
                use_api=False,
            )
            original_data = json.dumps(data, ensure_ascii=False, sort_keys=True)
            original_map = self.trip_pipeline.generate_route_map
            original_html = self.trip_pipeline.generate_html

            def fake_route_map(working_data, staging_dir, key):
                (staging_dir / "route-map.svg").write_text("<svg><path/></svg>", encoding="utf-8")
                working_data["map"] = {
                    "file": "route-map.svg",
                    "source": "fallback-svg",
                    "fallback": True,
                }
                return "route-map.svg"

            def fail_html_generation(*args):
                raise RuntimeError("render failed")

            self.trip_pipeline.generate_route_map = fake_route_map
            self.trip_pipeline.generate_html = fail_html_generation
            try:
                with self.assertRaisesRegex(RuntimeError, "render failed"):
                    self.trip_pipeline.write_outputs(data, out_dir, key=None, mode="estimate")
            finally:
                self.trip_pipeline.generate_route_map = original_map
                self.trip_pipeline.generate_html = original_html

            for filename, content in previous_files.items():
                self.assertEqual((out_dir / filename).read_text(encoding="utf-8"), content)
            self.assertEqual((out_dir / "notes.txt").read_text(encoding="utf-8"), "keep me")
            self.assertEqual(json.dumps(data, ensure_ascii=False, sort_keys=True), original_data)

    def test_publish_generated_files_restores_previous_output_on_replace_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging_dir = root / "staging"
            out_dir = root / "output"
            staging_dir.mkdir()
            out_dir.mkdir()
            for filename in ("trip-data.json", "manifest.json"):
                (staging_dir / filename).write_text(f"new {filename}", encoding="utf-8")
                (out_dir / filename).write_text(f"old {filename}", encoding="utf-8")

            real_replace = self.trip_pipeline.os.replace

            def fail_second_publish(source, destination):
                source_path = Path(source)
                if source_path.parent == staging_dir and source_path.name == "manifest.json":
                    raise OSError("replace failed")
                return real_replace(source, destination)

            self.trip_pipeline.os.replace = fail_second_publish
            try:
                with self.assertRaisesRegex(OSError, "replace failed"):
                    self.trip_pipeline.publish_generated_files(staging_dir, out_dir)
            finally:
                self.trip_pipeline.os.replace = real_replace

            self.assertEqual((out_dir / "trip-data.json").read_text(encoding="utf-8"), "old trip-data.json")
            self.assertEqual((out_dir / "manifest.json").read_text(encoding="utf-8"), "old manifest.json")

    def test_write_outputs_clears_stale_generated_metadata_between_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = self.trip_pipeline.build_trip_data(
                """D1
合肥 到 岳阳
""",
                title="Reusable Data",
                use_api=False,
            )
            original_map = self.trip_pipeline.generate_route_map
            original_pdf = self.trip_pipeline.generate_pdf

            def fake_route_map(data, out_dir, key):
                (out_dir / "route-map.svg").write_text("<svg></svg>", encoding="utf-8")
                data["map"] = {"file": "route-map.svg", "source": "fallback-svg", "fallback": True}
                data["map_png_error"] = "playwright unavailable"
                data["map_svg_error"] = "stale failure"
                return "route-map.svg"

            self.trip_pipeline.generate_route_map = fake_route_map
            self.trip_pipeline.generate_pdf = lambda html_path, pdf_path: False
            try:
                first_manifest = self.trip_pipeline.write_outputs(data, root / "html", key=None, mode="estimate", pdf=True)
                second_manifest = self.trip_pipeline.write_outputs(data, root / "data", key=None, mode="data-only")
            finally:
                self.trip_pipeline.generate_route_map = original_map
                self.trip_pipeline.generate_pdf = original_pdf

            data_only = json.loads((root / "data" / "trip-data.json").read_text(encoding="utf-8"))
            self.assertTrue(any("PDF generation failed" in warning for warning in first_manifest["warnings"]))
            self.assertIsNone(second_manifest["map"])
            self.assertIsNone(second_manifest["files"]["map_image"])
            self.assertIsNone(second_manifest["files"]["budget_image"])
            self.assertNotIn("map", data_only)
            self.assertNotIn("map_png_error", data_only)
            self.assertNotIn("map_svg_error", data_only)
            self.assertNotIn("pdf_error", data_only)
            self.assertFalse(any("Static route image fell back" in warning for warning in second_manifest["warnings"]))
            self.assertFalse(any("PDF generation failed" in warning for warning in second_manifest["warnings"]))

    def test_pdf_failure_is_written_to_data_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = self.trip_pipeline.build_trip_data(
                """D1
合肥 到 岳阳
""",
                title="PDF Failure",
                use_api=False,
            )
            original_map = self.trip_pipeline.generate_route_map
            original_pdf = self.trip_pipeline.generate_pdf

            def fake_route_map(data, out_dir, key):
                (out_dir / "route-map.svg").write_text("<svg></svg>", encoding="utf-8")
                data["map"] = {"file": "route-map.svg", "source": "fallback-svg", "fallback": True}
                return "route-map.svg"

            self.trip_pipeline.generate_route_map = fake_route_map
            self.trip_pipeline.generate_pdf = lambda html_path, pdf_path: False
            try:
                manifest = self.trip_pipeline.write_outputs(data, out_dir, key=None, mode="estimate", pdf=True)
            finally:
                self.trip_pipeline.generate_route_map = original_map
                self.trip_pipeline.generate_pdf = original_pdf

            data_on_disk = json.loads((out_dir / "trip-data.json").read_text(encoding="utf-8"))
            self.assertEqual(data_on_disk["pdf_error"], "PDF generation did not create trip.pdf.")
            self.assertIsNone(manifest["files"]["pdf"])
            self.assertTrue(any("PDF generation failed" in warning for warning in manifest["warnings"]))

    def test_write_and_verify_outputs_returns_success_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = self.trip_pipeline.build_trip_data(
                """D1
合肥 到 岳阳
""",
                title="Verified",
                use_api=False,
            )

            result = self.trip_pipeline.write_and_verify_outputs(data, out_dir, key=None, mode="data-only")

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stderr, "")
            self.assertEqual(result.verification_errors, [])
            self.assertEqual(result.manifest["mode"], "data-only")
            self.assertTrue((out_dir / "trip-data.json").read_text(encoding="utf-8").endswith("\n"))
            self.assertTrue((out_dir / "manifest.json").read_text(encoding="utf-8").endswith("\n"))

    def test_write_and_verify_outputs_reports_accuracy_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = self.trip_pipeline.build_trip_data(
                """D1
合肥 到 岳阳
""",
                title="Accurate",
                use_api=False,
            )

            result = self.trip_pipeline.write_and_verify_outputs(data, out_dir, key="fake-key", mode="accurate")

            self.assertEqual(result.returncode, 3)
            self.assertIn("accurate mode failed", result.stderr)
            self.assertEqual(result.verification_errors, [])
            self.assertIsNotNone(result.gate_error)

    def test_accuracy_gate_rejects_amap_leg_without_route_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = self.trip_pipeline.build_trip_data(
                """D1
合肥 到 岳阳
""",
                title="Accurate Geometry",
                use_api=False,
            )
            leg = data["days"][0]["legs"][0]
            leg.update({"source": "amap", "estimated": False, "polyline": []})
            data["days"][0]["estimated"] = False

            result = self.trip_pipeline.write_and_verify_outputs(
                data,
                out_dir,
                key="fake-key",
                mode="accurate",
            )

            self.assertEqual(result.returncode, 3)
            self.assertEqual(result.verification_errors, [])
            self.assertIn("accurate mode failed", result.stderr)

    def test_generate_trip_output_reports_missing_key_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)

            result = self.trip_pipeline.generate_trip_output(
                """D1
合肥 到 岳阳
""",
                out_dir,
                mode="accurate",
                key=None,
                use_api=False,
                title="Missing Key",
            )

            self.assertEqual(result.returncode, 3)
            self.assertIn("requires AMAP_KEY", result.stderr)
            self.assertEqual(result.manifest, {})
            self.assertFalse((out_dir / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
