import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_outputs.py"


def load_verify_outputs():
    spec = importlib.util.spec_from_file_location("verify_outputs", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sample_budget() -> dict:
    return {
        "currency": "CNY",
        "configured": True,
        "total_cny": 292.0,
        "category_totals": {"toll": 292.0},
        "items": [
            {
                "category": "toll",
                "label": "过路费",
                "amount_cny": 292.0,
                "detail": "全程 593.1 公里 · 来自路线数据",
            }
        ],
        "missing_attractions": [],
        "assumptions": {"trip_days": 1, "distance_km": 593.1, "passengers": {"adults": 1, "children_under_1_2m": 0, "children_over_1_2m": 0}},
        "warnings": [],
    }


def sample_data(map_image: str | None = "route-map.svg") -> dict:
    data = {
        "title": "Demo",
        "days": [
            {
                "day": "D1",
                "title": "合肥 - 岳阳",
                "notes": [],
                "legs": [
                    {
                        "from": "合肥",
                        "to": "岳阳",
                        "distance_km": 593.1,
                        "duration_min": 371,
                        "toll_cny": 292.0,
                        "source": "estimated",
                        "estimated": True,
                        "origin": {"lng": 117.2272, "lat": 31.8206},
                        "destination": {"lng": 113.1289, "lat": 29.3571},
                        "polyline": [[117.2272, 31.8206], [113.1289, 29.3571]],
                    }
                ],
                "distance_km": 593.1,
                "duration_min": 371,
                "toll_cny": 292.0,
                "estimated": True,
            }
        ],
        "totals": {"distance_km": 593.1, "duration_min": 371, "toll_cny": 292.0},
        "budget": sample_budget(),
    }
    if map_image:
        source = "leaflet-playwright-screenshot" if map_image == "route-map.png" else "fallback-svg"
        data["map"] = {"file": map_image, "source": source, "fallback": map_image == "route-map.svg"}
    return data


def sample_warnings(mode: str = "estimate", map_image: str | None = "route-map.svg") -> list[str]:
    warnings = ["One or more driving legs contain estimated metrics; verify before booking or departure."]
    if mode == "data-only":
        warnings.append("Data-only mode skipped HTML and route image generation.")
    elif map_image == "route-map.svg":
        warnings.append("Static route image fell back to schematic SVG; the HTML still contains the interactive route map.")
    if mode != "data-only":
        warnings.append("Budget summary image fell back to SVG.")
    return warnings


def sample_manifest(mode: str = "estimate", html: str | None = "trip.html", map_image: str | None = "route-map.svg") -> dict:
    source = "leaflet-playwright-screenshot" if map_image == "route-map.png" else "fallback-svg"
    return {
        "schema_version": 1,
        "mode": mode,
        "title": "Demo",
        "start_date": None,
        "data_source": "estimated",
        "source_counts": {"estimated": 1},
        "files": {
            "data": "trip-data.json",
            "manifest": "manifest.json",
            "html": html,
            "map_image": map_image,
            "budget_image": None if mode == "data-only" else "budget-summary.svg",
            "pdf": None,
        },
        "map": {"file": map_image, "source": source, "fallback": map_image == "route-map.svg"} if map_image else None,
        "budget": sample_budget(),
        "totals": {"distance_km": 593.1, "duration_min": 371, "toll_cny": 292.0},
        "counts": {"days": 1, "driving_days": 1, "legs": 1, "estimated_legs": 1},
        "warnings": sample_warnings(mode, map_image),
    }


class VerifyOutputsTests(unittest.TestCase):
    def setUp(self):
        self.verify_outputs = load_verify_outputs()

    def write_output(self, out_dir: Path, data: dict, manifest: dict) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "trip-data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    def test_valid_complete_output_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data()
            self.write_output(out_dir, data, sample_manifest())
            map_data_json = json.dumps(self.verify_outputs.build_map_data(data), ensure_ascii=False)
            (out_dir / "trip.html").write_text(
                '<html><head><link rel="stylesheet" href="leaflet.css"></head><body>'
                '<div id="trip-map"></div><a href="./route-map.svg">map</a>'
                '<a href="./budget-summary.svg">budget</a>'
                f'<script src="leaflet.js"></script><script id="trip-map-data" type="application/json">{map_data_json}</script>'
                '<script>window.__MAP_DATA__ = JSON.parse(document.getElementById("trip-map-data").textContent);</script>'
                '</body></html>',
                encoding="utf-8",
            )
            (out_dir / "route-map.svg").write_text("<svg><path d=\"M0 0\"/></svg>", encoding="utf-8")
            (out_dir / "budget-summary.svg").write_text(
                '<svg width="1600" height="1000"><rect width="1600" height="1000"/></svg>',
                encoding="utf-8",
            )

            self.assertEqual(self.verify_outputs.verify_output_dir(out_dir), [])

    def test_html_map_data_must_match_trip_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data()
            self.write_output(out_dir, data, sample_manifest())
            wrong_map_data = self.verify_outputs.build_map_data(data)
            wrong_map_data["title"] = "stale title"
            map_data_json = json.dumps(wrong_map_data, ensure_ascii=False)
            (out_dir / "trip.html").write_text(
                '<html><head><link rel="stylesheet" href="leaflet.css"></head><body>'
                '<div id="trip-map"></div><a href="./route-map.svg">map</a>'
                f'<script src="leaflet.js"></script><script id="trip-map-data" type="application/json">{map_data_json}</script>'
                '<script>window.__MAP_DATA__ = JSON.parse(document.getElementById("trip-map-data").textContent);</script>'
                '</body></html>',
                encoding="utf-8",
            )
            (out_dir / "route-map.svg").write_text("<svg><path d=\"M0 0\"/></svg>", encoding="utf-8")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("manifest.files.html #trip-map-data must match trip-data.json map projection", errors)

    def test_manifest_rejects_missing_and_unknown_top_level_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest.pop("counts")
            manifest["extra"] = True
            self.write_output(out_dir, sample_data(map_image=None), manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("manifest missing required field: counts", errors)
            self.assertIn("manifest has unsupported field: extra", errors)

    def test_budget_rejects_unknown_fields_and_categories(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["extra"] = True
            data["budget"]["items"].append(
                {"category": "custom", "label": "自定义", "amount_cny": 10.0, "detail": "test"}
            )
            data["budget"]["category_totals"]["custom"] = 10.0
            data["budget"]["total_cny"] = 302.0
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = json.loads(json.dumps(data["budget"]))
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("trip-data.json.budget has unsupported field: extra", errors)
            self.assertIn("trip-data.json.budget.items[2].category is unsupported: custom", errors)
            self.assertIn("trip-data.json.budget.category_totals has unsupported category: custom", errors)

    def test_duplicate_and_stale_warnings_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["warnings"] = ["Check price", "Check price"]
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = json.loads(json.dumps(data["budget"]))
            manifest["warnings"].extend(["Check price", "Check price", "PDF generation failed: stale"])
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("trip-data.json.budget.warnings must not contain duplicates", errors)
            self.assertIn("manifest.warnings must not contain duplicates", errors)
            self.assertIn("manifest.warnings contains stale expected text: PDF generation failed", errors)

    def test_generated_error_fields_require_text_and_warning_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["map_png_error"] = " "
            data["map_svg_error"] = "disk full"
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["warnings"].append("SVG map generation failed: disk full")
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("trip-data.json.map_png_error must be a non-empty string when present", errors)
            self.assertNotIn("manifest.warnings missing expected text: SVG map generation failed", errors)

    def test_valid_data_only_output_passes_without_html_or_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            self.write_output(
                out_dir,
                sample_data(map_image=None),
                sample_manifest(mode="data-only", html=None, map_image=None),
            )

            self.assertEqual(self.verify_outputs.verify_output_dir(out_dir), [])

    def test_manifest_schema_version_must_be_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["schema_version"] = 2
            self.write_output(out_dir, sample_data(map_image=None), manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("manifest.schema_version is 2, expected 1", errors)

    def test_manifest_title_and_start_date_types(self):
        cases = (
            ("title", 123, "manifest.title must be a string"),
            ("start_date", 20260717, "manifest.start_date must be null or an ISO date string YYYY-MM-DD"),
            ("start_date", "2026-99-99", "manifest.start_date must be null or an ISO date string YYYY-MM-DD"),
        )
        for field, value, expected_error in cases:
            with self.subTest(field=field, value=value):
                with tempfile.TemporaryDirectory() as tmp:
                    out_dir = Path(tmp)
                    manifest = sample_manifest(mode="data-only", html=None, map_image=None)
                    manifest[field] = value
                    self.write_output(out_dir, sample_data(map_image=None), manifest)

                    errors = self.verify_outputs.verify_output_dir(out_dir)

                    self.assertIn(expected_error, errors)

    def test_trip_data_title_and_start_date_types(self):
        cases = (
            ("title", 123, "trip-data.json.title must be a string"),
            ("start_date", 20260717, "trip-data.json.start_date must be null or an ISO date string YYYY-MM-DD"),
            ("start_date", "2026-99-99", "trip-data.json.start_date must be null or an ISO date string YYYY-MM-DD"),
        )
        for field, value, expected_error in cases:
            with self.subTest(field=field, value=value):
                with tempfile.TemporaryDirectory() as tmp:
                    out_dir = Path(tmp)
                    data = sample_data(map_image=None)
                    data[field] = value
                    self.write_output(out_dir, data, sample_manifest(mode="data-only", html=None, map_image=None))

                    errors = self.verify_outputs.verify_output_dir(out_dir)

                    self.assertIn(expected_error, errors)

    def test_manifest_title_and_start_date_must_match_trip_data(self):
        cases = (
            ("title", "Other Demo", "manifest.title must match trip-data.json title"),
            ("start_date", "2026-07-17", "manifest.start_date must match trip-data.json start_date"),
        )
        for field, value, expected_error in cases:
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as tmp:
                    out_dir = Path(tmp)
                    data = sample_data(map_image=None)
                    data[field] = value
                    self.write_output(out_dir, data, sample_manifest(mode="data-only", html=None, map_image=None))

                    errors = self.verify_outputs.verify_output_dir(out_dir)

                    self.assertIn(expected_error, errors)

    def test_manifest_counts_must_be_integer_values(self):
        cases = (
            ("days", "1"),
            ("driving_days", 1.0),
            ("legs", True),
            ("estimated_legs", -1),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                with tempfile.TemporaryDirectory() as tmp:
                    out_dir = Path(tmp)
                    manifest = sample_manifest(mode="data-only", html=None, map_image=None)
                    manifest["counts"][field] = value
                    self.write_output(out_dir, sample_data(map_image=None), manifest)

                    errors = self.verify_outputs.verify_output_dir(out_dir)

                    self.assertIn(f"manifest.counts.{field} must be a non-negative integer", errors)

    def test_manifest_source_counts_must_be_integer_values(self):
        cases = (
            ("estimated", "1"),
            ("estimated", 1.0),
            ("estimated", False),
            ("estimated", -1),
            ("", 1),
        )
        for source, value in cases:
            with self.subTest(source=source, value=value):
                with tempfile.TemporaryDirectory() as tmp:
                    out_dir = Path(tmp)
                    manifest = sample_manifest(mode="data-only", html=None, map_image=None)
                    manifest["source_counts"] = {source: value}
                    self.write_output(out_dir, sample_data(map_image=None), manifest)

                    errors = self.verify_outputs.verify_output_dir(out_dir)

                    if source:
                        self.assertIn(f"manifest.source_counts.{source} must be a non-negative integer", errors)
                    else:
                        self.assertIn("manifest.source_counts keys must be non-empty strings", errors)

    def test_manifest_files_data_and_manifest_names_are_fixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["files"]["data"] = "data.json"
            manifest["files"]["manifest"] = "summary.json"
            self.write_output(out_dir, sample_data(map_image=None), manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("manifest.files.data must be trip-data.json", errors)
            self.assertIn("manifest.files.manifest must be manifest.json", errors)

    def test_manifest_files_html_must_match_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            manifest = sample_manifest()
            manifest["files"]["html"] = "trip-data.json"
            self.write_output(out_dir, sample_data(), manifest)
            (out_dir / "route-map.svg").write_text("<svg></svg>", encoding="utf-8")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("manifest.files.html must be trip.html in estimate mode", errors)

    def test_publish_demo_manifest_html_must_be_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            manifest = sample_manifest(mode="publish-demo", html="trip.html")
            self.write_output(out_dir, sample_data(), manifest)
            (out_dir / "trip.html").write_text("<html></html>", encoding="utf-8")
            (out_dir / "route-map.svg").write_text("<svg></svg>", encoding="utf-8")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("manifest.files.html must be index.html in publish-demo mode", errors)

    def test_manifest_files_map_image_and_pdf_names_are_fixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            manifest = sample_manifest()
            manifest["files"]["map_image"] = "trip-data.json"
            manifest["files"]["pdf"] = "notes.pdf"
            manifest["map"]["file"] = "trip-data.json"
            data = sample_data()
            data["map"]["file"] = "trip-data.json"
            self.write_output(out_dir, data, manifest)
            (out_dir / "trip.html").write_text("<html></html>", encoding="utf-8")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("manifest.files.map_image must be route-map.png or route-map.svg", errors)
            self.assertIn("manifest.files.pdf must be trip.pdf or null", errors)

    def test_data_only_output_rejects_stale_html_and_map_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            self.write_output(
                out_dir,
                sample_data(map_image=None),
                sample_manifest(mode="data-only", html=None, map_image=None),
            )
            (out_dir / "trip.html").write_text("<html>stale</html>", encoding="utf-8")
            (out_dir / "route-map.svg").write_text("<svg></svg>", encoding="utf-8")
            (out_dir / "budget-summary.png").write_bytes(b"stale")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("stale generated file is not referenced by manifest.files: trip.html", errors)
            self.assertIn("stale generated file is not referenced by manifest.files: route-map.svg", errors)
            self.assertIn("stale generated file is not referenced by manifest.files: budget-summary.png", errors)

    def test_non_pdf_output_rejects_stale_pdf_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            self.write_output(out_dir, sample_data(), sample_manifest())
            (out_dir / "trip.html").write_text("<html></html>", encoding="utf-8")
            (out_dir / "route-map.svg").write_text("<svg></svg>", encoding="utf-8")
            (out_dir / "trip.pdf").write_text("stale", encoding="utf-8")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("stale generated file is not referenced by manifest.files: trip.pdf", errors)

    def test_data_only_output_rejects_pdf_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["files"]["pdf"] = "trip.pdf"
            self.write_output(out_dir, sample_data(map_image=None), manifest)
            (out_dir / "trip.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("manifest.files.pdf must be null in data-only mode", errors)
            self.assertIn("data-only output must not include manifest.files.pdf", errors)

    def test_pdf_asset_requires_signature_and_eof_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trip.pdf"
            path.write_bytes(b"not a pdf")
            errors = []

            self.verify_outputs.verify_pdf_asset(path, errors)

            self.assertIn("trip.pdf must have a valid PDF signature", errors)
            self.assertIn("trip.pdf must contain a PDF end-of-file marker", errors)

            path.write_bytes(b"%PDF-1.4\n%%EOF\n")
            errors = []
            self.verify_outputs.verify_pdf_asset(path, errors)
            self.assertEqual(errors, [])

    def test_budget_png_asset_requires_fixed_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "budget-summary.png"
            png_header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            path.write_bytes(png_header + (1600).to_bytes(4, "big") + (1000).to_bytes(4, "big"))
            errors = []

            self.verify_outputs.verify_budget_image_asset(path, path.name, errors)

            self.assertIn("budget-summary.png dimensions are 1600x1000, expected 3200x2000", errors)

    def test_budget_svg_asset_requires_fixed_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "budget-summary.svg"
            path.write_text('<svg width="800" height="500"><rect/></svg>', encoding="utf-8")
            errors = []

            self.verify_outputs.verify_budget_image_asset(path, path.name, errors)

            self.assertIn("budget-summary.svg dimensions must be 1600x1000", errors)

    def test_pdf_error_cannot_coexist_with_pdf_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data()
            data["pdf_error"] = "render failed"
            manifest = sample_manifest()
            manifest["files"]["pdf"] = "trip.pdf"
            manifest["warnings"].append("PDF generation failed: render failed")
            self.write_output(out_dir, data, manifest)
            (out_dir / "trip.html").write_text("<html></html>", encoding="utf-8")
            (out_dir / "route-map.svg").write_text("<svg></svg>", encoding="utf-8")
            (out_dir / "trip.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn(
                "manifest.files.pdf must be null when trip-data.json contains pdf_error",
                errors,
            )

    def test_non_data_output_requires_map_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            self.write_output(out_dir, sample_data(), sample_manifest())
            (out_dir / "trip.html").write_text("<html></html>", encoding="utf-8")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertTrue(any("map_image" in error for error in errors))

    def test_html_must_embed_leaflet_and_link_current_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            self.write_output(out_dir, sample_data(), sample_manifest())
            (out_dir / "trip.html").write_text(
                '<html><body><a href="./old-map.svg">map</a></body></html>',
                encoding="utf-8",
            )
            (out_dir / "route-map.svg").write_text("<svg><path d=\"M0 0\"/></svg>", encoding="utf-8")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("manifest.files.html must contain the #trip-map Leaflet container", errors)
            self.assertIn("manifest.files.html must load the Leaflet script", errors)
            self.assertIn("manifest.files.html must load the Leaflet stylesheet", errors)
            self.assertIn("manifest.files.html must embed window.__MAP_DATA__", errors)
            self.assertIn("manifest.files.html must link to the current map asset: route-map.svg", errors)

    def test_svg_map_asset_must_have_rendered_elements(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            self.write_output(out_dir, sample_data(), sample_manifest())
            (out_dir / "trip.html").write_text("<html></html>", encoding="utf-8")
            (out_dir / "route-map.svg").write_text("<svg></svg>", encoding="utf-8")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("route-map.svg must contain rendered map elements", errors)

    def test_png_map_asset_must_have_png_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            self.write_output(
                out_dir,
                sample_data(map_image="route-map.png"),
                sample_manifest(map_image="route-map.png"),
            )
            (out_dir / "trip.html").write_text("<html></html>", encoding="utf-8")
            (out_dir / "route-map.png").write_bytes(b"not a png")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("route-map.png must have a valid PNG signature", errors)

    def test_leg_contract_requires_required_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data()
            data["days"][0]["legs"][0].pop("toll_cny")
            self.write_output(out_dir, data, sample_manifest(mode="data-only", html=None, map_image=None))

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertTrue(any("toll_cny" in error for error in errors))

    def test_leg_coordinates_must_use_lng_lat_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["days"][0]["legs"][0]["origin"] = {"lng": "117.2"}
            data["days"][0]["legs"][0]["destination"] = "岳阳"
            self.write_output(out_dir, data, sample_manifest(mode="data-only", html=None, map_image=None))

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("leg #1 合肥->岳阳.origin.lng must be numeric", errors)
            self.assertIn("leg #1 合肥->岳阳.origin.lat must be numeric", errors)
            self.assertIn("leg #1 合肥->岳阳.destination must be an object with numeric lng/lat", errors)

    def test_leg_polyline_must_use_numeric_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["days"][0]["legs"][0]["polyline"] = [[117.2, 31.8], {"lng": 113.1, "lat": 29.3}]
            self.write_output(out_dir, data, sample_manifest(mode="data-only", html=None, map_image=None))

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("leg #1 合肥->岳阳.polyline[2] must be [lng, lat] numeric pair", errors)

    def test_leg_geometry_requires_valid_coordinate_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            leg = data["days"][0]["legs"][0]
            leg["origin"]["lng"] = 181
            leg["destination"]["lat"] = -91
            leg["polyline"] = [[181, 31.8206], [113.1289, -91]]
            self.write_output(out_dir, data, sample_manifest(mode="data-only", html=None, map_image=None))

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("leg #1 合肥->岳阳.origin.lng must be between -180 and 180", errors)
            self.assertIn("leg #1 合肥->岳阳.destination.lat must be between -90 and 90", errors)
            self.assertIn("leg #1 合肥->岳阳.polyline[1] longitude must be between -180 and 180", errors)
            self.assertIn("leg #1 合肥->岳阳.polyline[2] latitude must be between -90 and 90", errors)

    def test_leg_polyline_rejects_single_point(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["days"][0]["legs"][0]["polyline"] = [[117.2272, 31.8206]]
            self.write_output(out_dir, data, sample_manifest(mode="data-only", html=None, map_image=None))

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn(
                "leg #1 合肥->岳阳.polyline must be empty or contain at least two points",
                errors,
            )

    def test_leg_source_must_be_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["days"][0]["legs"][0]["source"] = "manual"
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["source_counts"] = {"manual": 1}
            manifest["data_source"] = "manual"
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("leg #1 合肥->岳阳 field source is unsupported: manual", errors)

    def test_leg_place_names_and_source_must_be_non_empty_strings(self):
        cases = (
            ("from", ""),
            ("to", ""),
            ("source", 123),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                with tempfile.TemporaryDirectory() as tmp:
                    out_dir = Path(tmp)
                    data = sample_data(map_image=None)
                    data["days"][0]["legs"][0][field] = value
                    self.write_output(out_dir, data, sample_manifest(mode="data-only", html=None, map_image=None))

                    errors = self.verify_outputs.verify_output_dir(out_dir)

                    self.assertTrue(any(f"field {field} must be a non-empty string" in error for error in errors))

    def test_estimated_source_requires_estimated_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["days"][0]["legs"][0]["estimated"] = False
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["counts"]["estimated_legs"] = 0
            manifest["warnings"] = [warning for warning in manifest["warnings"] if "estimated metrics" not in warning]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("leg #1 合肥->岳阳 source estimated requires estimated=true", errors)

    def test_leg_lookup_error_must_be_non_empty_string_when_present(self):
        invalid_lookup_errors = ("", 123)
        for invalid_lookup_error in invalid_lookup_errors:
            with self.subTest(invalid_lookup_error=invalid_lookup_error):
                with tempfile.TemporaryDirectory() as tmp:
                    out_dir = Path(tmp)
                    data = sample_data(map_image=None)
                    data["days"][0]["legs"][0]["lookup_error"] = invalid_lookup_error
                    manifest = sample_manifest(mode="data-only", html=None, map_image=None)
                    manifest["warnings"].append(f"Map lookup errors occurred: 合肥->岳阳: {invalid_lookup_error}")
                    self.write_output(out_dir, data, manifest)

                    errors = self.verify_outputs.verify_output_dir(out_dir)

                    self.assertIn("leg #1 合肥->岳阳 field lookup_error must be a non-empty string when present", errors)

    def test_day_estimated_must_be_boolean_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["days"][0]["estimated"] = "yes"
            self.write_output(out_dir, data, sample_manifest(mode="data-only", html=None, map_image=None))

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("D1 field estimated must be a boolean", errors)

    def test_day_estimated_is_required_and_must_match_legs(self):
        cases = (
            (None, "D1 missing required field: estimated"),
            (False, "D1.estimated is false, expected true from its legs"),
        )
        for value, expected_error in cases:
            with self.subTest(value=value):
                with tempfile.TemporaryDirectory() as tmp:
                    out_dir = Path(tmp)
                    data = sample_data(map_image=None)
                    if value is None:
                        data["days"][0].pop("estimated")
                    else:
                        data["days"][0]["estimated"] = value
                    self.write_output(out_dir, data, sample_manifest(mode="data-only", html=None, map_image=None))

                    errors = self.verify_outputs.verify_output_dir(out_dir)

                    self.assertIn(expected_error, errors)

    def test_accurate_mode_requires_complete_amap_leg_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data()
            manifest = sample_manifest(mode="accurate")
            self.write_output(out_dir, data, manifest)
            (out_dir / "trip.html").write_text("<html></html>", encoding="utf-8")
            (out_dir / "route-map.svg").write_text("<svg></svg>", encoding="utf-8")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("accurate mode requires complete Amap leg data: 合肥->岳阳", errors)

    def test_accurate_mode_requires_complete_amap_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data()
            leg = data["days"][0]["legs"][0]
            leg.update({"source": "amap", "estimated": False, "polyline": []})
            data["days"][0]["estimated"] = False
            manifest = sample_manifest(mode="accurate")
            manifest["source_counts"] = {"amap": 1}
            manifest["data_source"] = "amap"
            manifest["counts"]["estimated_legs"] = 0
            manifest["warnings"] = [
                warning for warning in manifest["warnings"] if "estimated metrics" not in warning
            ]
            self.write_output(out_dir, data, manifest)
            (out_dir / "trip.html").write_text("<html></html>", encoding="utf-8")
            (out_dir / "route-map.svg").write_text("<svg></svg>", encoding="utf-8")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("accurate mode requires complete Amap leg data: 合肥->岳阳", errors)

    def test_output_requires_at_least_one_driving_leg(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["days"][0]["legs"] = []
            data["days"][0]["distance_km"] = 0.0
            data["days"][0]["duration_min"] = 0
            data["days"][0]["toll_cny"] = 0.0
            data["totals"] = {"distance_km": 0.0, "duration_min": 0, "toll_cny": 0.0}
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["source_counts"] = {}
            manifest["data_source"] = "none"
            manifest["totals"] = data["totals"]
            manifest["counts"] = {"days": 1, "driving_days": 0, "legs": 0, "estimated_legs": 0}
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("trip-data.json must include at least one driving leg", errors)

    def test_duplicate_day_labels_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data()
            data["days"].append(
                {
                    "day": "D1",
                    "title": "岳阳市区",
                    "notes": ["岳阳市区"],
                    "legs": [],
                    "distance_km": 0.0,
                    "duration_min": 0,
                    "toll_cny": 0.0,
                }
            )
            manifest = sample_manifest()
            manifest["counts"]["days"] = 2
            self.write_output(out_dir, data, manifest)
            (out_dir / "trip.html").write_text("<html></html>", encoding="utf-8")
            (out_dir / "route-map.svg").write_text("<svg></svg>", encoding="utf-8")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("duplicate trip-data.json day label: D1", errors)

    def test_day_labels_must_use_normalized_d_format(self):
        invalid_labels = ("D0", "D01", "Day1", "第一天")
        for invalid_label in invalid_labels:
            with self.subTest(invalid_label=invalid_label):
                with tempfile.TemporaryDirectory() as tmp:
                    out_dir = Path(tmp)
                    data = sample_data(map_image=None)
                    data["days"][0]["day"] = invalid_label
                    self.write_output(out_dir, data, sample_manifest(mode="data-only", html=None, map_image=None))

                    errors = self.verify_outputs.verify_output_dir(out_dir)

                    self.assertIn(f"{invalid_label} field day must use normalized D1/D2 format", errors)

    def test_day_title_must_be_non_empty_string(self):
        invalid_titles = (None, "", 123)
        for invalid_title in invalid_titles:
            with self.subTest(invalid_title=invalid_title):
                with tempfile.TemporaryDirectory() as tmp:
                    out_dir = Path(tmp)
                    data = sample_data(map_image=None)
                    data["days"][0]["title"] = invalid_title
                    self.write_output(out_dir, data, sample_manifest(mode="data-only", html=None, map_image=None))

                    errors = self.verify_outputs.verify_output_dir(out_dir)

                    self.assertIn("D1 field title must be a non-empty string", errors)

    def test_day_notes_must_be_string_list(self):
        invalid_notes = ("岳阳市区", [123], None)
        for invalid_note_value in invalid_notes:
            with self.subTest(invalid_note_value=invalid_note_value):
                with tempfile.TemporaryDirectory() as tmp:
                    out_dir = Path(tmp)
                    data = sample_data(map_image=None)
                    data["days"][0]["notes"] = invalid_note_value
                    self.write_output(out_dir, data, sample_manifest(mode="data-only", html=None, map_image=None))

                    errors = self.verify_outputs.verify_output_dir(out_dir)

                    self.assertIn("D1 field notes must be a list of non-empty strings", errors)

    def test_user_facing_text_fields_reject_whitespace_only_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["title"] = "   "
            day = data["days"][0]
            day["title"] = "\t"
            day["notes"] = [" "]
            day["legs"][0]["from"] = " "
            data["budget"]["items"][0]["label"] = " "
            data["budget"]["warnings"] = [" "]
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["title"] = "   "
            manifest["budget"] = data["budget"]
            manifest["warnings"].append(" ")
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("manifest.title must be a non-empty string", errors)
            self.assertIn("trip-data.json.title must be a non-empty string", errors)
            self.assertIn("D1 field title must be a non-empty string", errors)
            self.assertIn("D1 field notes must be a list of non-empty strings", errors)
            self.assertTrue(any("field from must be a non-empty string" in error for error in errors))
            self.assertIn("trip-data.json.budget.items[1].label must be a non-empty string", errors)
            self.assertIn("trip-data.json.budget.warnings must be a list of non-empty strings", errors)
            self.assertIn("manifest.warnings must be a list of non-empty strings", errors)

    def test_day_metrics_must_be_numeric(self):
        cases = (
            ("distance_km", "593.1"),
            ("duration_min", True),
            ("toll_cny", None),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                with tempfile.TemporaryDirectory() as tmp:
                    out_dir = Path(tmp)
                    data = sample_data(map_image=None)
                    data["days"][0][field] = value
                    self.write_output(out_dir, data, sample_manifest(mode="data-only", html=None, map_image=None))

                    errors = self.verify_outputs.verify_output_dir(out_dir)

                    self.assertIn(f"D1 field {field} must be numeric", errors)

    def test_route_metrics_must_be_finite_and_non_negative(self):
        cases = (
            ("leg", "distance_km", float("inf"), "leg #1 合肥->岳阳 field distance_km must be numeric"),
            ("leg", "duration_min", float("nan"), "leg #1 合肥->岳阳 field duration_min must be numeric"),
            ("leg", "toll_cny", -1, "leg #1 合肥->岳阳 field toll_cny must be non-negative"),
            ("day", "distance_km", -1, "D1 field distance_km must be non-negative"),
            ("totals", "duration_min", -1, "trip-data.json.totals.duration_min must be non-negative"),
        )
        for owner, field, value, expected_error in cases:
            with self.subTest(owner=owner, field=field, value=value):
                with tempfile.TemporaryDirectory() as tmp:
                    out_dir = Path(tmp)
                    data = sample_data(map_image=None)
                    if owner == "leg":
                        data["days"][0]["legs"][0][field] = value
                    elif owner == "day":
                        data["days"][0][field] = value
                    else:
                        data["totals"][field] = value
                    manifest = sample_manifest(mode="data-only", html=None, map_image=None)
                    if owner == "totals":
                        manifest["totals"][field] = value
                    self.write_output(out_dir, data, manifest)

                    errors = self.verify_outputs.verify_output_dir(out_dir)

                    self.assertIn(expected_error, errors)

    def test_total_rollups_must_match_legs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data()
            data["days"][0]["distance_km"] = 600.0
            self.write_output(out_dir, data, sample_manifest())
            (out_dir / "trip.html").write_text("<html></html>", encoding="utf-8")
            (out_dir / "route-map.svg").write_text("<svg></svg>", encoding="utf-8")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertTrue(any("D1.distance_km" in error for error in errors))

    def test_manifest_map_must_match_data_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            manifest = sample_manifest()
            manifest["map"]["file"] = "other.svg"
            self.write_output(out_dir, sample_data(), manifest)
            (out_dir / "trip.html").write_text("<html></html>", encoding="utf-8")
            (out_dir / "route-map.svg").write_text("<svg></svg>", encoding="utf-8")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertTrue(any("manifest.map" in error for error in errors))

    def test_manifest_map_source_must_be_supported(self):
        for source in ("custom-renderer", ["fallback-svg"]):
            with self.subTest(source=source):
                with tempfile.TemporaryDirectory() as tmp:
                    out_dir = Path(tmp)
                    data = sample_data()
                    data["map"]["source"] = source
                    manifest = sample_manifest()
                    manifest["map"] = data["map"]
                    self.write_output(out_dir, data, manifest)
                    (out_dir / "trip.html").write_text("<html></html>", encoding="utf-8")
                    (out_dir / "route-map.svg").write_text("<svg></svg>", encoding="utf-8")

                    errors = self.verify_outputs.verify_output_dir(out_dir)

                    self.assertIn(f"manifest.map.source is unsupported: {source}", errors)

    def test_manifest_map_source_controls_file_and_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data()
            data["map"].update({"source": "leaflet-playwright-screenshot", "fallback": True})
            manifest = sample_manifest()
            manifest["map"] = data["map"]
            self.write_output(out_dir, data, manifest)
            (out_dir / "trip.html").write_text("<html></html>", encoding="utf-8")
            (out_dir / "route-map.svg").write_text("<svg></svg>", encoding="utf-8")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn(
                "manifest.map source leaflet-playwright-screenshot requires file route-map.png",
                errors,
            )
            self.assertIn(
                "manifest.map source leaflet-playwright-screenshot requires fallback=false",
                errors,
            )

    def test_manifest_map_note_must_be_non_empty_string(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data()
            data["map"]["note"] = ""
            manifest = sample_manifest()
            manifest["map"] = data["map"]
            self.write_output(out_dir, data, manifest)
            (out_dir / "trip.html").write_text("<html></html>", encoding="utf-8")
            (out_dir / "route-map.svg").write_text("<svg></svg>", encoding="utf-8")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("manifest.map.note must be a non-empty string when present", errors)

    def test_manifest_budget_must_match_data_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            manifest = sample_manifest()
            manifest["budget"]["total_cny"] = 300.0
            self.write_output(out_dir, sample_data(), manifest)
            (out_dir / "trip.html").write_text("<html></html>", encoding="utf-8")
            (out_dir / "route-map.svg").write_text("<svg></svg>", encoding="utf-8")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertTrue(any("manifest.budget" in error for error in errors))

    def test_budget_must_be_an_object(self):
        invalid_budgets = (None, "bad")
        for invalid_budget in invalid_budgets:
            with self.subTest(invalid_budget=invalid_budget):
                with tempfile.TemporaryDirectory() as tmp:
                    out_dir = Path(tmp)
                    data = sample_data(map_image=None)
                    data["budget"] = invalid_budget
                    manifest = sample_manifest(mode="data-only", html=None, map_image=None)
                    manifest["budget"] = invalid_budget
                    self.write_output(out_dir, data, manifest)

                    errors = self.verify_outputs.verify_output_dir(out_dir)

                    self.assertIn("trip-data.json.budget must be an object", errors)

    def test_budget_configured_must_be_boolean(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["configured"] = "yes"
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = data["budget"]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("trip-data.json.budget.configured must be a boolean", errors)

    def test_budget_assumptions_require_trip_distance_and_passenger_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["assumptions"] = {
                "trip_days": 0,
                "distance_km": "593.1",
                "passengers": {
                    "adults": 1.0,
                    "children_under_1_2m": -1,
                },
            }
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = data["budget"]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            prefix = "trip-data.json.budget.assumptions"
            self.assertIn(f"{prefix}.trip_days must be a positive integer", errors)
            self.assertIn(f"{prefix}.distance_km must be numeric", errors)
            self.assertIn(f"{prefix}.passengers.adults must be a non-negative integer", errors)
            self.assertIn(f"{prefix}.passengers.children_under_1_2m must be a non-negative integer", errors)
            self.assertIn(f"{prefix}.passengers.children_over_1_2m must be a non-negative integer", errors)

    def test_budget_assumptions_must_match_trip_days_and_distance(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["assumptions"]["trip_days"] = 2
            data["budget"]["assumptions"]["distance_km"] = 100.0
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = data["budget"]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            prefix = "trip-data.json.budget.assumptions"
            self.assertIn(f"{prefix}.trip_days is 2, expected 1", errors)
            self.assertIn(f"{prefix}.distance_km is 100.0, expected 593.1", errors)

    def test_budget_optional_assumptions_validate_shape_and_rollups(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["assumptions"].update(
                {
                    "vehicle": {
                        "type": "fuel",
                        "kwh_price_cny": 1.5,
                        "kwh_per_100km": 16.0,
                        "estimated_kwh": 1.0,
                    },
                    "hotel": {"nightly_cny": 300.0, "nights": 1.5},
                    "meal": {"daily_cny": -100.0, "days": 1},
                }
            )
            data["budget"]["category_totals"].update(
                {"vehicle_energy": 1.5, "hotel": 300.0, "meal": -100.0}
            )
            data["budget"]["items"].extend(
                [
                    {"category": "vehicle_energy", "label": "补能", "amount_cny": 1.5, "detail": "test"},
                    {"category": "hotel", "label": "住宿", "amount_cny": 300.0, "detail": "test"},
                    {"category": "meal", "label": "餐饮", "amount_cny": -100.0, "detail": "test"},
                ]
            )
            data["budget"]["total_cny"] = 493.5
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = data["budget"]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            prefix = "trip-data.json.budget.assumptions"
            self.assertIn(f"{prefix}.vehicle.type must be ev", errors)
            self.assertIn(f"{prefix}.vehicle.estimated_kwh is 1.0, expected 94.9", errors)
            self.assertIn(f"{prefix}.hotel.nights must be a non-negative integer", errors)
            self.assertIn(f"{prefix}.meal.daily_cny must be non-negative", errors)
            self.assertIn(
                "trip-data.json.budget.category_totals.vehicle_energy is 1.5, expected 142.34 from assumptions",
                errors,
            )

    def test_budget_category_requires_matching_assumption(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["items"].append(
                {"category": "hotel", "label": "住宿", "amount_cny": 300.0, "detail": "test"}
            )
            data["budget"]["category_totals"]["hotel"] = 300.0
            data["budget"]["total_cny"] = 592.0
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = data["budget"]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn(
                "trip-data.json.budget.assumptions.hotel is required for budget category hotel",
                errors,
            )

    def test_optional_budget_assumptions_cannot_be_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["assumptions"].update(
                {"vehicle": None, "hotel": None, "meal": None}
            )
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = data["budget"]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            prefix = "trip-data.json.budget.assumptions"
            self.assertIn(f"{prefix}.vehicle must be an object", errors)
            self.assertIn(f"{prefix}.hotel must be an object", errors)
            self.assertIn(f"{prefix}.meal must be an object", errors)

    def test_budget_items_require_renderable_label_and_detail(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["items"][0].pop("label")
            data["budget"]["items"][0]["detail"] = 123
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = data["budget"]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("trip-data.json.budget.items[1].label must be a non-empty string", errors)
            self.assertIn("trip-data.json.budget.items[1].detail must be a non-empty string", errors)

    def test_budget_item_components_schema_is_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["items"] = [
                {
                    "category": "attraction",
                    "label": "天眼景区",
                    "amount_cny": 180.0,
                    "detail": "门票免费；摆渡车 3 × ¥50；保险 3 × ¥10",
                    "components": [
                        {"label": "门票", "unit_price_cny": 0.0, "quantity": 0, "amount_cny": 0.0, "charge": "free"},
                        {"label": "", "unit_price_cny": "50", "quantity": 3, "amount_cny": 150.0, "charge": "ticket"},
                    ],
                }
            ]
            data["budget"]["category_totals"] = {"attraction": 180.0}
            data["budget"]["total_cny"] = 180.0
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = data["budget"]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("trip-data.json.budget.items[1].components[2].label must be a non-empty string", errors)
            self.assertIn("trip-data.json.budget.items[1].components[2].charge must be free or per_person", errors)
            self.assertIn("trip-data.json.budget.items[1].components[2].unit_price_cny must be numeric", errors)

    def test_budget_item_components_total_must_match_item_amount(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["items"] = [
                {
                    "category": "attraction",
                    "label": "天眼景区",
                    "amount_cny": 180.0,
                    "detail": "门票免费；摆渡车 3 × ¥50；保险 3 × ¥10",
                    "components": [
                        {"label": "门票", "unit_price_cny": 0.0, "quantity": 0, "amount_cny": 0.0, "charge": "free"},
                        {"label": "摆渡车", "unit_price_cny": 50.0, "quantity": 3, "amount_cny": 150.0, "charge": "per_person"},
                    ],
                }
            ]
            data["budget"]["category_totals"] = {"attraction": 180.0}
            data["budget"]["total_cny"] = 180.0
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = data["budget"]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("trip-data.json.budget.items[1].components total is 150.0, expected item amount 180.0", errors)

    def test_budget_item_quantity_and_unit_price_must_reproduce_amount(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            item = data["budget"]["items"][0]
            item.update({"quantity": 2, "unit_price_cny": 100.0})
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = data["budget"]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn(
                "trip-data.json.budget.items[1].amount_cny is 292.0, expected 200.0 from quantity * unit price",
                errors,
            )

    def test_component_charges_must_match_price_and_passenger_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["items"] = [
                {
                    "category": "attraction",
                    "label": "景区服务",
                    "amount_cny": 110.0,
                    "detail": "test",
                    "components": [
                        {
                            "label": "摆渡车",
                            "unit_price_cny": 50.0,
                            "quantity": 2,
                            "amount_cny": 100.0,
                            "charge": "per_person",
                        },
                        {
                            "label": "门票",
                            "unit_price_cny": 10.0,
                            "quantity": 1,
                            "amount_cny": 10.0,
                            "charge": "free",
                        },
                    ],
                }
            ]
            data["budget"]["category_totals"] = {"attraction": 110.0}
            data["budget"]["total_cny"] = 110.0
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = data["budget"]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            component_prefix = "trip-data.json.budget.items[1].components"
            self.assertIn(f"{component_prefix}[1].quantity is 2, expected total passengers 1", errors)
            self.assertIn(f"{component_prefix}[2].quantity must be 0 when charge is free", errors)
            self.assertIn(
                f"{component_prefix}[2].amount_cny is 10.0, expected 0.0 from component rules",
                errors,
            )

    def test_ticket_counts_must_match_passengers_and_reproduce_amount(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["items"] = [
                {
                    "category": "attraction",
                    "label": "景区门票",
                    "amount_cny": 999.0,
                    "detail": "test",
                    "adult_price_cny": 100.0,
                    "charged_adults": 2,
                    "free_children_under_1_2m": 1,
                    "half_price_children_over_1_2m": 1,
                }
            ]
            data["budget"]["category_totals"] = {"attraction": 999.0}
            data["budget"]["total_cny"] = 999.0
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = data["budget"]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            item_prefix = "trip-data.json.budget.items[1]"
            self.assertIn(f"{item_prefix}.amount_cny is 999.0, expected 250.0 from ticket counts", errors)
            self.assertIn(f"{item_prefix}.charged_adults is 2, expected passengers.adults 1", errors)
            self.assertIn(
                f"{item_prefix}.free_children_under_1_2m is 1, expected passengers.children_under_1_2m 0",
                errors,
            )
            self.assertIn(
                f"{item_prefix}.half_price_children_over_1_2m is 1, expected passengers.children_over_1_2m 0",
                errors,
            )

    def test_missing_attractions_schema_is_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["missing_attractions"] = [
                {
                    "name": "",
                    "matched_names": "小七孔",
                    "days": [1],
                    "suggestion": "",
                }
            ]
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = data["budget"]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("trip-data.json.budget.missing_attractions[1].name must be a non-empty string", errors)
            self.assertIn("trip-data.json.budget.missing_attractions[1].matched_names must be a list of non-empty strings", errors)
            self.assertIn("trip-data.json.budget.missing_attractions[1].days must be a list of non-empty strings", errors)
            self.assertIn("trip-data.json.budget.missing_attractions[1].suggestion must be a non-empty string", errors)

    def test_budget_total_must_match_category_totals(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["total_cny"] = 999.0
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = data["budget"]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("trip-data.json.budget.total_cny is 999.0, expected 292.0", errors)

    def test_budget_amounts_must_be_finite_and_non_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["items"][0]["amount_cny"] = -292.0
            data["budget"]["category_totals"]["toll"] = -292.0
            data["budget"]["total_cny"] = -292.0
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = data["budget"]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("trip-data.json.budget.items[1].amount_cny must be non-negative", errors)
            self.assertIn("trip-data.json.budget.category_totals.toll must be non-negative", errors)
            self.assertIn("trip-data.json.budget.total_cny must be non-negative", errors)

    def test_budget_component_amounts_must_be_finite_and_non_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["items"] = [
                {
                    "category": "attraction",
                    "label": "摆渡车",
                    "amount_cny": -50.0,
                    "detail": "1 × ¥-50",
                    "components": [
                        {
                            "label": "摆渡车",
                            "unit_price_cny": float("inf"),
                            "quantity": 1,
                            "amount_cny": -50.0,
                            "charge": "per_person",
                        }
                    ],
                }
            ]
            data["budget"]["category_totals"] = {"attraction": -50.0}
            data["budget"]["total_cny"] = -50.0
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = data["budget"]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("trip-data.json.budget.items[1].components[1].unit_price_cny must be numeric", errors)
            self.assertIn("trip-data.json.budget.items[1].components[1].amount_cny must be non-negative", errors)

    def test_budget_category_totals_must_match_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["category_totals"]["toll"] = 999.0
            data["budget"]["total_cny"] = 999.0
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = data["budget"]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("trip-data.json.budget.category_totals.toll is 999.0, expected 292.0", errors)

    def test_budget_category_totals_require_matching_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["category_totals"]["meal"] = 100.0
            data["budget"]["total_cny"] = 392.0
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = data["budget"]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("trip-data.json.budget.category_totals.meal has no matching budget items", errors)

    def test_budget_rollups_are_checked_when_budget_is_not_user_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data(map_image=None)
            data["budget"]["configured"] = False
            data["budget"]["category_totals"]["toll"] = 999.0
            data["budget"]["total_cny"] = 999.0
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["budget"] = data["budget"]
            self.write_output(out_dir, data, manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertIn("trip-data.json.budget.category_totals.toll is 999.0, expected 292.0", errors)

    def test_estimated_legs_require_manifest_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            manifest = sample_manifest()
            manifest["warnings"] = [warning for warning in manifest["warnings"] if "estimated metrics" not in warning]
            self.write_output(out_dir, sample_data(), manifest)
            (out_dir / "trip.html").write_text("<html></html>", encoding="utf-8")
            (out_dir / "route-map.svg").write_text("<svg></svg>", encoding="utf-8")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertTrue(any("estimated metrics" in error for error in errors))

    def test_lookup_error_requires_manifest_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data = sample_data()
            data["days"][0]["legs"][0]["lookup_error"] = "quota exceeded"
            manifest = sample_manifest()
            self.write_output(out_dir, data, manifest)
            (out_dir / "trip.html").write_text("<html></html>", encoding="utf-8")
            (out_dir / "route-map.svg").write_text("<svg></svg>", encoding="utf-8")

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertTrue(any("Map lookup errors occurred" in error for error in errors))

    def test_data_only_output_requires_skip_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            manifest = sample_manifest(mode="data-only", html=None, map_image=None)
            manifest["warnings"] = [warning for warning in manifest["warnings"] if "Data-only" not in warning]
            self.write_output(out_dir, sample_data(map_image=None), manifest)

            errors = self.verify_outputs.verify_output_dir(out_dir)

            self.assertTrue(any("Data-only mode skipped" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
