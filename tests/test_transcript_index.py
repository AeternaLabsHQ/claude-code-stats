"""The parse pass records where each transcript lives, so the detail-page
pass does not search the filesystem once per session.

Before this, extract_session_messages() rebuilt the source list and probed
the filesystem for every session. With a sudo_user source that meant two
subprocess round trips (test -e, then find) per session, even for sessions
that live in the primary dir - roughly a third of a full run.

The index must resolve exactly like the old search did: earlier source wins,
and within a source a file directly under the project dir beats a nested one.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import extract_stats as es  # noqa: E402
from tests.fixture_utils import (assistant_line, patched_sources,  # noqa: E402
                                 user_line, write_jsonl)

LINES = [user_line(), assistant_line(output_tokens=100)]


class TranscriptIndexTest(unittest.TestCase):
    def setUp(self):
        es._reset_transcript_index()

    def test_parse_pass_records_the_transcript_path(self):
        tmp = Path(tempfile.mkdtemp(prefix="cs-idx-"))
        pd = tmp / "projects"
        write_jsonl(pd / "proj1" / "S1.jsonl", LINES)
        with patched_sources(pd) as _es:
            _es.parse_session_transcripts()
        path, sudo_user = es._lookup_transcript("proj1", "S1")
        self.assertEqual(path, pd / "proj1" / "S1.jsonl")
        self.assertIsNone(sudo_user)

    def test_earlier_source_wins(self):
        tmp = Path(tempfile.mkdtemp(prefix="cs-idx-src-"))
        prim = tmp / "primary" / "projects"
        prim.mkdir(parents=True)
        b = tmp / "b" / "projects"
        c = tmp / "c" / "projects"
        write_jsonl(b / "proj1" / "S1.jsonl", LINES)
        write_jsonl(c / "proj1" / "S1.jsonl", LINES)
        with patched_sources(prim, additional=[
            {"label": "x1", "projects_dir": b, "sudo_user": None},
            {"label": "x2", "projects_dir": c, "sudo_user": None},
        ]) as _es:
            _es.parse_session_transcripts()
        path, _ = es._lookup_transcript("proj1", "S1")
        self.assertEqual(path, b / "proj1" / "S1.jsonl")

    def test_primary_dir_loses_against_an_additional_source(self):
        """The primary dir is appended last, so it must not win a tie - the
        old per-session search checked additional sources first."""
        tmp = Path(tempfile.mkdtemp(prefix="cs-idx-prim-"))
        prim = tmp / "primary" / "projects"
        b = tmp / "b" / "projects"
        write_jsonl(prim / "proj1" / "S1.jsonl", LINES)
        write_jsonl(b / "proj1" / "S1.jsonl", LINES)
        with patched_sources(prim, additional=[
            {"label": "x1", "projects_dir": b, "sudo_user": None},
        ]) as _es:
            _es.parse_session_transcripts()
        path, _ = es._lookup_transcript("proj1", "S1")
        self.assertEqual(path, b / "proj1" / "S1.jsonl")

    def test_direct_file_beats_a_nested_one_in_the_same_source(self):
        """rglob order is not the search order: the old code checked
        <project>/<sid>.jsonl before descending into subdirectories."""
        tmp = Path(tempfile.mkdtemp(prefix="cs-idx-nest-"))
        pd = tmp / "projects"
        # "aaa" sorts before the direct file, so a naive sorted-rglob index
        # would pick the nested one.
        write_jsonl(pd / "proj1" / "aaa" / "S1.jsonl", LINES)
        write_jsonl(pd / "proj1" / "S1.jsonl", LINES)
        with patched_sources(pd) as _es:
            _es.parse_session_transcripts()
        path, _ = es._lookup_transcript("proj1", "S1")
        self.assertEqual(path, pd / "proj1" / "S1.jsonl")

    def test_a_second_parse_pass_replaces_the_first_index(self):
        """Two parse passes in one process (tests, or any embedding driver):
        the second must not be shadowed by stale paths from the first, which
        carry the same rank and would otherwise never be overwritten."""
        tmp = Path(tempfile.mkdtemp(prefix="cs-idx-reparse-"))
        first = tmp / "first" / "projects"
        second = tmp / "second" / "projects"
        write_jsonl(first / "proj1" / "S1.jsonl", LINES)
        write_jsonl(second / "proj1" / "S1.jsonl", LINES)
        with patched_sources(first) as _es:
            _es.parse_session_transcripts()
        with patched_sources(second) as _es:
            _es.parse_session_transcripts()
        path, _ = es._lookup_transcript("proj1", "S1")
        self.assertEqual(path, second / "proj1" / "S1.jsonl")

    def test_unknown_session_resolves_to_nothing(self):
        tmp = Path(tempfile.mkdtemp(prefix="cs-idx-miss-"))
        pd = tmp / "projects"
        write_jsonl(pd / "proj1" / "S1.jsonl", LINES)
        with patched_sources(pd) as _es:
            _es.parse_session_transcripts()
        self.assertEqual(es._lookup_transcript("proj1", "NOPE"), (None, None))
        self.assertEqual(es._lookup_transcript("nosuchproj", "S1"), (None, None))


class ExtractUsesIndexTest(unittest.TestCase):
    def setUp(self):
        es._reset_transcript_index()

    def test_no_filesystem_search_once_the_index_is_built(self):
        tmp = Path(tempfile.mkdtemp(prefix="cs-idx-nosearch-"))
        pd = tmp / "projects"
        write_jsonl(pd / "proj1" / "S1.jsonl", LINES)
        with patched_sources(pd) as _es:
            _es.parse_session_transcripts()
            with mock.patch.object(Path, "rglob",
                                   side_effect=AssertionError("rglob")) as rg:
                messages = _es.extract_session_messages("S1", "proj1")
        self.assertEqual(rg.call_count, 0)
        self.assertTrue(messages)

    def test_sudo_probes_are_not_spawned_once_the_index_is_built(self):
        """The expensive case: a sudo source that does not hold the session.
        The old code paid `sudo test -e` plus `sudo find` for it anyway."""
        tmp = Path(tempfile.mkdtemp(prefix="cs-idx-sudo-"))
        prim = tmp / "primary" / "projects"
        remote = tmp / "remote" / "projects"
        remote.mkdir(parents=True)
        write_jsonl(prim / "proj1" / "S1.jsonl", LINES)
        boom = AssertionError("sudo subprocess spawned")
        with patched_sources(prim, additional=[
            {"label": "remote", "projects_dir": remote, "sudo_user": "someone"},
        ]) as _es:
            with mock.patch.object(_es, "sudo_path_exists", return_value=False), \
                 mock.patch.object(_es, "sudo_list_dir", return_value=[]):
                _es.parse_session_transcripts()
            with mock.patch.object(_es, "sudo_path_exists", side_effect=boom), \
                 mock.patch.object(_es, "sudo_find_files", side_effect=boom):
                messages = _es.extract_session_messages("S1", "proj1")
        self.assertTrue(messages)

    def test_falls_back_to_searching_when_no_parse_pass_ran(self):
        """extract_session_messages() is importable on its own; without an
        index it must still find the transcript the old way."""
        tmp = Path(tempfile.mkdtemp(prefix="cs-idx-fallback-"))
        pd = tmp / "projects"
        write_jsonl(pd / "proj1" / "S1.jsonl", LINES)
        with patched_sources(pd) as _es:
            messages = _es.extract_session_messages("S1", "proj1")
        self.assertTrue(messages)

    def test_nested_transcript_is_found_through_the_index(self):
        tmp = Path(tempfile.mkdtemp(prefix="cs-idx-sub-"))
        pd = tmp / "projects"
        write_jsonl(pd / "proj1" / "PARENT" / "subagents" / "agent-a1.jsonl",
                    [user_line(session_id="agent-a1"),
                     assistant_line(session_id="agent-a1", output_tokens=7)])
        with patched_sources(pd) as _es:
            _es.parse_session_transcripts()
            messages = _es.extract_session_messages("agent-a1", "proj1")
        self.assertTrue(messages)


if __name__ == "__main__":
    unittest.main()
