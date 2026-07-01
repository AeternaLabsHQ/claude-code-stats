"""Parser-level integration tests: orphan subagents and duplicate sources."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.fixture_utils import (assistant_line, patched_sources, user_line,
                                 write_jsonl)


class OrphanSubagentTest(unittest.TestCase):
    def test_orphan_subagent_survives_parsing(self):
        tmp = Path(tempfile.mkdtemp(prefix="cs-orphan-"))
        pd = tmp / "projects"
        write_jsonl(
            pd / "proj1" / "PARENT-GONE" / "subagents" / "agent-a1.jsonl",
            [user_line(session_id="agent-a1"),
             assistant_line(session_id="agent-a1", output_tokens=77)])
        with patched_sources(pd) as es:
            sessions = es.parse_session_transcripts()
        self.assertIn("agent-a1", sessions)
        total_out = sum(m["output_tokens"]
                        for m in sessions["agent-a1"]["models"].values())
        self.assertEqual(total_out, 77)


class DuplicateSourceTest(unittest.TestCase):
    def test_same_session_in_two_additional_sources_counts_once(self):
        tmp = Path(tempfile.mkdtemp(prefix="cs-dup-"))
        prim = tmp / "primary" / "projects"
        prim.mkdir(parents=True)
        b = tmp / "b" / "projects"
        c = tmp / "c" / "projects"
        lines = [user_line(), assistant_line(output_tokens=100)]
        write_jsonl(b / "proj1" / "S1.jsonl", lines)
        write_jsonl(c / "proj1" / "S1.jsonl", lines)
        with patched_sources(prim, additional=[
            {"label": "x1", "projects_dir": b, "sudo_user": None},
            {"label": "x2", "projects_dir": c, "sudo_user": None},
        ]) as es:
            sessions = es.parse_session_transcripts()
        s1 = sessions["S1"]
        self.assertEqual(
            sum(m["output_tokens"] for m in s1["models"].values()), 100)
        self.assertEqual(s1["message_count"], 2)


if __name__ == "__main__":
    unittest.main()
