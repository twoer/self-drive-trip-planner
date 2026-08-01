import importlib.util
import io
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "output_reporter.py"


def load_output_reporter():
    spec = importlib.util.spec_from_file_location("output_reporter", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class OutputReporterTests(unittest.TestCase):
    def setUp(self):
        self.output_reporter = load_output_reporter()

    def test_emit_run_report_success(self):
        result = self.output_reporter.OutputRunResult(
            data={},
            manifest={"source_counts": {"estimated": 2}, "warnings": []},
            verification_errors=[],
        )
        out = io.StringIO()
        err = io.StringIO()

        code = self.output_reporter.emit_run_report(
            result,
            Path("/tmp/trip-output"),
            "estimate",
            open_path=Path("/tmp/trip-output/trip.html"),
            out=out,
            err=err,
        )

        self.assertEqual(code, 0)
        self.assertIn("Wrote:", out.getvalue())
        self.assertIn("Sources: estimated=2", out.getvalue())
        self.assertIn("Verified: output contract", out.getvalue())
        self.assertIn("Open: /tmp/trip-output/trip.html", out.getvalue())
        self.assertEqual(err.getvalue(), "")

    def test_emit_run_report_preflight_error_skips_success_text(self):
        result = self.output_reporter.OutputRunResult(
            data={},
            manifest={},
            verification_errors=[],
            gate_error="accurate mode requires AMAP_KEY or GAODE_KEY.",
        )
        out = io.StringIO()
        err = io.StringIO()

        code = self.output_reporter.emit_run_report(result, Path("/tmp/out"), "accurate", out=out, err=err)

        self.assertEqual(code, 3)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("requires AMAP_KEY", err.getvalue())

    def test_emit_run_report_verification_errors_use_code_4(self):
        result = self.output_reporter.OutputRunResult(
            data={},
            manifest={"source_counts": {}, "warnings": []},
            verification_errors=["missing file"],
        )
        out = io.StringIO()
        err = io.StringIO()

        code = self.output_reporter.emit_run_report(result, Path("/tmp/out"), "estimate", out=out, err=err)

        self.assertEqual(code, 4)
        self.assertIn("Output verification failed", err.getvalue())
        self.assertIn("- missing file", err.getvalue())


if __name__ == "__main__":
    unittest.main()
