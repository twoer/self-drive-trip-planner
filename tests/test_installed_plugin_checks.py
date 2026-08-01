import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_installed_plugin.py"


def load_check_installed_plugin():
    spec = importlib.util.spec_from_file_location("check_installed_plugin", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class InstalledPluginCheckTests(unittest.TestCase):
    def setUp(self):
        self.checker = load_check_installed_plugin()

    def write_plugin(self, path: Path, version: str = "0.6.0") -> None:
        (path / ".codex-plugin").mkdir(parents=True)
        skill_dir = path / "skills" / "self-drive-trip-planner"
        skill_dir.mkdir(parents=True)
        (path / ".codex-plugin" / "plugin.json").write_text(
            json.dumps({"name": "self-drive-trip-planner", "version": version, "skills": "./skills/"}) + "\n",
            encoding="utf-8",
        )
        (skill_dir / "SKILL.md").write_text("skill\n", encoding="utf-8")

    def write_marketplace(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({
                "name": "personal",
                "plugins": [
                    {
                        "name": "self-drive-trip-planner",
                        "source": {"source": "local", "path": "./plugins/self-drive-trip-planner"},
                    }
                ],
            }) + "\n",
            encoding="utf-8",
        )

    def test_validate_installed_plugin_accepts_matching_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = root / "expected"
            installed = root / "installed"
            cache = root / "cache" / "personal" / "self-drive-trip-planner" / "0.6.0"
            marketplace = root / "marketplace.json"
            self.write_plugin(expected)
            shutil.copytree(expected, installed)
            shutil.copytree(expected, cache)
            self.write_marketplace(marketplace)

            errors = self.checker.validate_installed_plugin(
                installed,
                marketplace,
                root / "cache",
                expected_plugin=expected,
                require_cache=True,
            )

            self.assertEqual(errors, [])

    def test_validate_installed_plugin_reports_cache_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = root / "expected"
            installed = root / "installed"
            cache = root / "cache" / "personal" / "self-drive-trip-planner" / "0.6.0"
            marketplace = root / "marketplace.json"
            self.write_plugin(expected)
            shutil.copytree(expected, installed)
            shutil.copytree(expected, cache)
            (cache / "skills" / "self-drive-trip-planner" / "SKILL.md").write_text("stale\n", encoding="utf-8")
            self.write_marketplace(marketplace)

            errors = self.checker.validate_installed_plugin(
                installed,
                marketplace,
                root / "cache",
                expected_plugin=expected,
                require_cache=True,
            )

            self.assertIn("Codex cache differs from expected file: skills/self-drive-trip-planner/SKILL.md", errors)

    def test_validate_installed_plugin_requires_current_cache_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = root / "expected"
            installed = root / "installed"
            marketplace = root / "marketplace.json"
            self.write_plugin(expected)
            shutil.copytree(expected, installed)
            self.write_marketplace(marketplace)

            errors = self.checker.validate_installed_plugin(
                installed,
                marketplace,
                root / "cache",
                expected_plugin=expected,
                require_cache=True,
            )

            self.assertTrue(any("Codex cache is missing current plugin version" in error for error in errors))

    def test_validate_codex_plugin_state_accepts_current_enabled_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            installed = Path(tmp) / "installed"
            self.write_plugin(installed)
            state = {
                "installed": [
                    {
                        "pluginId": "self-drive-trip-planner@personal",
                        "name": "self-drive-trip-planner",
                        "marketplaceName": "personal",
                        "version": "0.6.0",
                        "installed": True,
                        "enabled": True,
                        "source": {"path": str(installed.resolve())},
                    }
                ]
            }

            errors = self.checker.validate_codex_plugin_state(state, "personal", "0.6.0", installed)

            self.assertEqual(errors, [])

    def test_validate_codex_plugin_state_reports_version_and_enabled_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            installed = Path(tmp) / "installed"
            self.write_plugin(installed)
            state = {
                "installed": [
                    {
                        "pluginId": "self-drive-trip-planner@personal",
                        "name": "self-drive-trip-planner",
                        "marketplaceName": "personal",
                        "version": "0.5.1",
                        "installed": True,
                        "enabled": False,
                        "source": {"path": str(installed.resolve())},
                    }
                ]
            }

            errors = self.checker.validate_codex_plugin_state(state, "personal", "0.6.0", installed)

            self.assertIn("Codex installed plugin version is 0.5.1, expected 0.6.0", errors)
            self.assertIn("Codex plugin is not enabled", errors)

    def test_validate_codex_plugin_state_prefers_exact_marketplace_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            installed = Path(tmp) / "installed"
            self.write_plugin(installed)
            correct = {
                "pluginId": "self-drive-trip-planner@personal",
                "name": "self-drive-trip-planner",
                "marketplaceName": "personal",
                "version": "0.6.0",
                "installed": True,
                "enabled": True,
                "source": {"path": str(installed.resolve())},
            }
            unrelated = {
                **correct,
                "pluginId": "self-drive-trip-planner@other",
                "marketplaceName": "other",
                "version": "0.5.0",
            }

            errors = self.checker.validate_codex_plugin_state(
                {"installed": [unrelated, correct]},
                "personal",
                "0.6.0",
                installed,
            )

            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
