import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MakefileContractTests(unittest.TestCase):
    def test_make_test_compiles_all_python_scripts_via_wildcard(self):
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

        self.assertRegex(makefile, re.compile(r"^SCRIPT_FILES\s*:=\s*\$\(wildcard scripts/\*\.py\)", re.MULTILINE))
        self.assertRegex(makefile, r"\$\(PYTHON\)\s+-m\s+py_compile\s+\$\(SCRIPT_FILES\)")

    def test_demo_batch_uses_script_defaults(self):
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        command = re.search(r"^demo-batch:.*\n\t(.+)$", makefile, re.MULTILINE)

        self.assertIsNotNone(command)
        self.assertIn("scripts/generate_demo_batch.py", command.group(1))
        self.assertNotIn("--count", command.group(1))
        self.assertNotIn("--min-days", command.group(1))
        self.assertNotIn("--max-days", command.group(1))


if __name__ == "__main__":
    unittest.main()
