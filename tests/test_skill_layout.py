import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "skill_layout.py"


def load_skill_layout():
    spec = importlib.util.spec_from_file_location("skill_layout", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SkillLayoutTests(unittest.TestCase):
    def setUp(self):
        self.layout = load_skill_layout()

    def test_copy_skill_contents_uses_shared_runtime_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            target = Path(tmp) / "skill"
            (root / "scripts").mkdir(parents=True)
            (root / "references").mkdir()
            (root / "examples").mkdir()
            (root / "SKILL.md").write_text("skill", encoding="utf-8")
            (root / "requirements.txt").write_text("", encoding="utf-8")
            (root / ".env.example").write_text("AMAP_KEY=your-gaode-web-service-key\n", encoding="utf-8")
            (root / "scripts" / "route_trip.py").write_text("print('runtime')\n", encoding="utf-8")
            (root / "scripts" / "skill_layout.py").write_text("print('layout')\n", encoding="utf-8")
            (root / "scripts" / "package_plugin.py").write_text("print('repo helper')\n", encoding="utf-8")
            (root / "scripts" / "check_installed_plugin.py").write_text("print('repo helper')\n", encoding="utf-8")
            (root / "references" / "output-contract.md").write_text("contract", encoding="utf-8")
            (root / "examples" / "simple-trip.txt").write_text("D1\n合肥 到 岳阳\n", encoding="utf-8")
            target.mkdir()

            self.layout.copy_skill_contents(root, target)

            self.assertTrue((target / "scripts" / "route_trip.py").is_file())
            self.assertTrue((target / "scripts" / "skill_layout.py").is_file())
            self.assertFalse((target / "scripts" / "package_plugin.py").exists())
            self.assertFalse((target / "scripts" / "check_installed_plugin.py").exists())
            self.assertTrue((target / "references" / "output-contract.md").is_file())
            self.assertTrue((target / "examples" / "simple-trip.txt").is_file())


if __name__ == "__main__":
    unittest.main()
