import importlib.util
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_plugin_package.py"


def load_check_plugin_package():
    spec = importlib.util.spec_from_file_location("check_plugin_package", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PluginPackageCheckTests(unittest.TestCase):
    def setUp(self):
        self.checker = load_check_plugin_package()

    def test_referenced_skill_paths_finds_packaged_file_references(self):
        references = self.checker.referenced_skill_paths(
            """
Run `python3 scripts/route_trip.py`.
Read `references/output-contract.md` and examples/simple-trip.txt.
"""
        )

        self.assertEqual(
            references,
            [
                "examples/simple-trip.txt",
                "references/output-contract.md",
                "scripts/route_trip.py",
            ],
        )

    def test_validate_skill_references_reports_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text("Run scripts/missing.py and read references/ok.md.", encoding="utf-8")
            (skill_dir / "references").mkdir()
            (skill_dir / "references" / "ok.md").write_text("ok", encoding="utf-8")

            missing = self.checker.validate_skill_references(skill_dir)

            self.assertEqual(missing, ["scripts/missing.py"])

    def test_validate_python_scripts_compiles_packaged_scripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir()
            (scripts_dir / "ok.py").write_text("print('ok')\n", encoding="utf-8")

            self.assertEqual(self.checker.validate_python_scripts(skill_dir), [])

    def test_validate_python_scripts_reports_compile_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir()
            (scripts_dir / "bad.py").write_text("def broken(:\n", encoding="utf-8")

            errors = self.checker.validate_python_scripts(skill_dir)

            self.assertEqual(len(errors), 1)
            self.assertIn("scripts/bad.py", errors[0])

    def test_required_package_files_cover_runtime_layout(self):
        self.assertIn("README.md", self.checker.REQUIRED_PLUGIN_FILES)
        self.assertIn("INSTALL.md", self.checker.REQUIRED_PLUGIN_FILES)
        for rel_path in (
            ".env.example",
            "agents/openai.yaml",
            "references/data-schema.md",
            "references/map-services.md",
            "references/ui-generation-baseline.md",
            "scripts/run_demo.py",
            "scripts/generate_demo_batch.py",
            "scripts/setup_env.py",
            "scripts/install_skill.py",
        ):
            self.assertIn(rel_path, self.checker.REQUIRED_SKILL_FILES)

    def test_submission_version_info_parses_version_and_release_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SUBMISSION.md"
            path.write_text(
                """- Version: `0.6.0`
https://example.com/releases/download/v0.6.0/file.zip
""",
                encoding="utf-8",
            )

            version, release_versions = self.checker.submission_version_info(path)

            self.assertEqual(version, "0.6.0")
            self.assertEqual(release_versions, ["0.6.0"])

    def test_validate_submission_version_reports_mismatches(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SUBMISSION.md"
            path.write_text(
                """- Version: `0.5.0`
https://example.com/releases/download/v0.4.0/file.zip
""",
                encoding="utf-8",
            )

            errors = self.checker.validate_submission_version("0.6.0", path)

            self.assertIn("SUBMISSION.md version is 0.5.0, expected 0.6.0", errors)
            self.assertIn("SUBMISSION.md release URL uses 0.4.0, expected 0.6.0", errors)

    def test_validate_archive_matches_folder_accepts_matching_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plugin_dir = base / "self-drive-trip-planner"
            (plugin_dir / "skills").mkdir(parents=True)
            (plugin_dir / "skills" / "SKILL.md").write_text("skill", encoding="utf-8")
            archive_path = base / "self-drive-trip-planner-plugin.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.write(plugin_dir / "skills" / "SKILL.md", "self-drive-trip-planner/skills/SKILL.md")

            self.assertEqual(self.checker.validate_archive_matches_folder(plugin_dir), [])

    def test_validate_archive_matches_folder_reports_missing_archive_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plugin_dir = base / "self-drive-trip-planner"
            plugin_dir.mkdir()

            errors = self.checker.validate_archive_matches_folder(plugin_dir)

            self.assertEqual(len(errors), 1)
            self.assertIn("missing plugin archive", errors[0])

    def test_validate_archive_matches_folder_reports_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plugin_dir = base / "self-drive-trip-planner"
            plugin_dir.mkdir()
            (plugin_dir / "expected.txt").write_text("expected", encoding="utf-8")
            archive_path = base / "self-drive-trip-planner-plugin.zip"
            extra_file = base / "extra.txt"
            extra_file.write_text("extra", encoding="utf-8")
            with ZipFile(archive_path, "w") as archive:
                archive.write(extra_file, "self-drive-trip-planner/extra.txt")

            errors = self.checker.validate_archive_matches_folder(plugin_dir)

            self.assertIn("archive missing file: self-drive-trip-planner/expected.txt", errors)
            self.assertIn("archive contains extra file: self-drive-trip-planner/extra.txt", errors)

    def test_validate_documented_commands_reports_missing_targets_and_scripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Makefile").write_text("install:\n", encoding="utf-8")
            (root / "README.md").write_text("Run `make missing` and `python3 scripts/missing.py`.", encoding="utf-8")
            (root / "INSTALL.md").write_text("Run `make install`.", encoding="utf-8")
            (root / "SUBMISSION.md").write_text("Run `make install`.", encoding="utf-8")
            (root / "SKILL.md").write_text("Run scripts/missing.py.", encoding="utf-8")

            errors = self.checker.validate_documented_commands(root)

            self.assertIn("README.md references missing make target: missing", errors)
            self.assertIn("README.md references missing script: scripts/missing.py", errors)
            self.assertIn("SKILL.md references missing script: scripts/missing.py", errors)


if __name__ == "__main__":
    unittest.main()
