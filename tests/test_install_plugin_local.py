import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install_plugin_local.py"


def load_install_plugin_local():
    scripts_dir = str(SCRIPT.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("install_plugin_local", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class InstallPluginLocalTests(unittest.TestCase):
    def setUp(self):
        self.installer = load_install_plugin_local()

    def test_install_rejects_build_output_nested_inside_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin_parent = Path(tmp) / "plugins"
            build_dir = plugin_parent / self.installer.PLUGIN_NAME / "build"

            with self.assertRaisesRegex(RuntimeError, "overlapping build and install paths"):
                self.installer.install_plugin(plugin_parent, build_dir)


if __name__ == "__main__":
    unittest.main()
