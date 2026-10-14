"""Runs the Node smoke test for the session table totals row (skipped without node)."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class SessionTableTotalsJsTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_node_smoke_passes(self):
        res = subprocess.run(["node", str(ROOT / "tools" / "smoke_session_table_totals.js")],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("smoke_session_table_totals: OK", res.stdout)


if __name__ == "__main__":
    unittest.main()
