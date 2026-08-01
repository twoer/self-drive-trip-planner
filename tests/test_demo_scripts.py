import json
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_batch_module():
    script = ROOT / "scripts" / "generate_demo_batch.py"
    scripts_dir = str(script.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("generate_demo_batch", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DemoScriptTests(unittest.TestCase):
    def test_batch_defaults_cover_twenty_trips_from_three_to_twenty_five_days(self):
        batch = load_batch_module()

        counts = batch.day_counts(
            batch.DEFAULT_BATCH_COUNT,
            batch.DEFAULT_MIN_DAYS,
            batch.DEFAULT_MAX_DAYS,
        )

        self.assertEqual(len(counts), 20)
        self.assertEqual(min(counts), 3)
        self.assertEqual(max(counts), 25)
        self.assertEqual(counts, sorted(counts))

    def test_batch_demo_uses_pipeline_and_verifies_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "batch"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "generate_demo_batch.py"),
                    "--count",
                    "2",
                    "--min-days",
                    "3",
                    "--max-days",
                    "4",
                    "--out",
                    str(out_dir),
                    "--mode",
                    "estimate",
                ],
                check=True,
                text=True,
                capture_output=True,
                cwd=ROOT,
            )

            self.assertIn("Wrote:", result.stdout)
            summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(len(summary), 2)
            self.assertTrue(all(item["returncode"] == 0 for item in summary))
            for item in summary:
                output_dir = out_dir / item["output"]
                self.assertEqual(item["verification_errors"], [])
                self.assertIsNone(item["gate_error"])
                self.assertEqual(item["stderr"], "")
                self.assertTrue((output_dir / "manifest.json").is_file())
                self.assertTrue((output_dir / "trip.html").is_file())
                self.assertTrue((output_dir / item["manifest"]["files"]["map_image"]).is_file())

    def test_batch_demo_rejects_invalid_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "generate_demo_batch.py"),
                    "--count",
                    "0",
                    "--out",
                    str(Path(tmp) / "batch"),
                ],
                text=True,
                capture_output=True,
                cwd=ROOT,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("--count must be greater than 0", result.stderr)
            self.assertNotIn("Wrote:", result.stdout)

    def test_batch_demo_rejects_invalid_day_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "generate_demo_batch.py"),
                    "--count",
                    "2",
                    "--min-days",
                    "5",
                    "--max-days",
                    "3",
                    "--out",
                    str(Path(tmp) / "batch"),
                ],
                text=True,
                capture_output=True,
                cwd=ROOT,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("--max-days must be greater than or equal to --min-days", result.stderr)
            self.assertNotIn("Wrote:", result.stdout)

    def test_run_demo_missing_input_returns_clean_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run_demo.py"),
                    "--input",
                    str(Path(tmp) / "missing.txt"),
                    "--out",
                    str(Path(tmp) / "out"),
                    "--mode",
                    "estimate",
                ],
                text=True,
                capture_output=True,
                cwd=ROOT,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("Input file not found", result.stdout)
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
