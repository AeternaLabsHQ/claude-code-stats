"""Incremental scan: which sessions a run has to rebuild, and what the
cache epoch covers.

The corpus is append-only and mostly frozen - a few transcripts grow, the
other ~8,700 files are identical from run to run. The cache reuses the
merged session state and only re-parses what actually moved.

Two rules make that safe:

* The epoch is a hash over every source file that can change how a
  transcript is interpreted. Any edit to the parser, the pricing table or
  the config invalidates everything, so no cached number can outlive the
  code that produced it.
* Invalidating a session pulls in every file that claims it, not just the
  file that changed. absorb_file() is "first seen wins" across sources, so
  a duplicate that was skipped last run may have to win this one.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import extract_stats as es  # noqa: E402
from tests.fixture_utils import (assistant_line, patched_cache,  # noqa: E402
                                 patched_sources, user_line, write_jsonl)


def entry(fsid, sids, mtime=100.0, size=10):
    return {"mtime": mtime, "size": size,
            "file_session_id": fsid, "session_ids": list(sids)}


class DirtySetTest(unittest.TestCase):
    """_plan_reparse(manifest, current) -> (dirty_ids, paths_to_reparse)"""

    def test_nothing_changed_means_nothing_to_do(self):
        manifest = {"/a/S1.jsonl": entry("S1", ["S1"])}
        current = {"/a/S1.jsonl": (100.0, 10)}
        dirty, reparse = es._plan_reparse(manifest, current)
        self.assertEqual(dirty, set())
        self.assertEqual(reparse, set())

    def test_a_grown_file_invalidates_its_own_sessions(self):
        manifest = {"/a/S1.jsonl": entry("S1", ["S1"]),
                    "/a/S2.jsonl": entry("S2", ["S2"])}
        current = {"/a/S1.jsonl": (100.0, 99), "/a/S2.jsonl": (100.0, 10)}
        dirty, reparse = es._plan_reparse(manifest, current)
        self.assertEqual(dirty, {"S1"})
        self.assertEqual(reparse, {"/a/S1.jsonl"})

    def test_mtime_alone_is_enough_to_invalidate(self):
        manifest = {"/a/S1.jsonl": entry("S1", ["S1"])}
        current = {"/a/S1.jsonl": (200.0, 10)}
        dirty, _ = es._plan_reparse(manifest, current)
        self.assertEqual(dirty, {"S1"})

    def test_a_new_file_is_parsed_without_dirtying_anything_else(self):
        manifest = {"/a/S1.jsonl": entry("S1", ["S1"])}
        current = {"/a/S1.jsonl": (100.0, 10), "/a/S9.jsonl": (100.0, 10)}
        dirty, reparse = es._plan_reparse(manifest, current)
        self.assertEqual(reparse, {"/a/S9.jsonl"})
        self.assertEqual(dirty, {"S9"})

    def test_a_deleted_file_drops_its_sessions_and_is_not_reparsed(self):
        manifest = {"/a/S1.jsonl": entry("S1", ["S1"])}
        dirty, reparse = es._plan_reparse(manifest, {})
        self.assertEqual(dirty, {"S1"})
        self.assertEqual(reparse, set())

    def test_a_file_holding_several_sessions_dirties_all_of_them(self):
        """One transcript can carry more than one sessionId, since the id
        comes from the line content, not from the filename."""
        manifest = {"/a/S1.jsonl": entry("S1", ["S1", "S1-resumed"])}
        current = {"/a/S1.jsonl": (100.0, 99)}
        dirty, _ = es._plan_reparse(manifest, current)
        self.assertEqual(dirty, {"S1", "S1-resumed"})

    def test_a_skipped_duplicate_is_reparsed_when_the_winner_changes(self):
        """The heart of it: /b was skipped last run because /a claimed S1
        first. If /a changes, both have to be re-parsed together, in source
        order, or 'first seen wins' silently picks a different winner."""
        manifest = {"/a/S1.jsonl": entry("S1", ["S1"]),
                    "/b/S1.jsonl": entry("S1", [])}
        current = {"/a/S1.jsonl": (100.0, 99), "/b/S1.jsonl": (100.0, 10)}
        dirty, reparse = es._plan_reparse(manifest, current)
        self.assertEqual(dirty, {"S1"})
        self.assertEqual(reparse, {"/a/S1.jsonl", "/b/S1.jsonl"})

    def test_a_deleted_winner_hands_the_session_to_the_duplicate(self):
        manifest = {"/a/S1.jsonl": entry("S1", ["S1"]),
                    "/b/S1.jsonl": entry("S1", [])}
        current = {"/b/S1.jsonl": (100.0, 10)}
        dirty, reparse = es._plan_reparse(manifest, current)
        self.assertEqual(dirty, {"S1"})
        self.assertEqual(reparse, {"/b/S1.jsonl"})

    def test_invalidation_chains_through_shared_sessions(self):
        """/a dirties S1, /b claims S1 and also carries S2, so S2 is dirty
        too and /c which claims S2 gets pulled in as well.

        "x" lands in the dirty set as well, even though no session by that
        name exists: it is /b's file_session_id, and once /b is re-parsed a
        duplicate of /b that was skipped last run has to be re-weighed too.
        Dropping an id that is not in the cache is a no-op, so erring wide
        here costs nothing."""
        manifest = {"/a/S1.jsonl": entry("S1", ["S1"]),
                    "/b/x.jsonl": entry("x", ["S1", "S2"]),
                    "/c/S2.jsonl": entry("S2", []),
                    "/d/far.jsonl": entry("far", ["far"])}
        current = {p: (100.0, 99 if p == "/a/S1.jsonl" else 10)
                   for p in manifest}
        dirty, reparse = es._plan_reparse(manifest, current)
        self.assertEqual(dirty, {"S1", "S2", "x"})
        self.assertEqual(reparse,
                         {"/a/S1.jsonl", "/b/x.jsonl", "/c/S2.jsonl"})
        self.assertNotIn("/d/far.jsonl", reparse)

    def test_an_untouched_file_is_never_reparsed(self):
        """The whole point: 8,700 frozen files must stay untouched."""
        manifest = {f"/a/S{i}.jsonl": entry(f"S{i}", [f"S{i}"])
                    for i in range(50)}
        current = {p: (100.0, 10) for p in manifest}
        current["/a/S7.jsonl"] = (100.0, 11)
        dirty, reparse = es._plan_reparse(manifest, current)
        self.assertEqual(reparse, {"/a/S7.jsonl"})
        self.assertEqual(dirty, {"S7"})


class VolatileSessionsTest(unittest.TestCase):
    """--verify-cache runs against a live corpus, so it has to tell a real
    cache mismatch from a session that simply kept writing during the check."""

    def setUp(self):
        # _sessions_touched_by consults the manifest; without this it would
        # read the real multi-megabyte cache next to extract_stats.py.
        self._cache = patched_cache()
        self._cache.__enter__()
        self.addCleanup(self._cache.__exit__, None, None, None)

    def test_a_moved_transcript_marks_its_own_session(self):
        ids = es._sessions_touched_by({"/p/proj1/S1.jsonl"})
        self.assertIn("S1", ids)

    def test_a_moved_subagent_marks_its_parent(self):
        """finalize_sessions folds a subagent's usage into its parent, so the
        parent's numbers move while the parent's own file stands still. The
        first version of the check missed this and cried wolf on every
        long-running session."""
        ids = es._sessions_touched_by(
            {"/p/proj1/PARENT-ID/subagents/agent-a1.jsonl"})
        self.assertIn("agent-a1", ids)
        self.assertIn("PARENT-ID", ids)

    def test_an_untouched_corpus_marks_nothing(self):
        self.assertEqual(es._sessions_touched_by(set()), set())


class EpochTest(unittest.TestCase):
    def test_epoch_is_stable_across_calls(self):
        self.assertEqual(es._cache_epoch(), es._cache_epoch())

    def test_epoch_covers_the_parser_source(self):
        base = es._cache_epoch()
        self.assertNotEqual(
            base, es._cache_epoch(_extra={"extract_stats.py": b"changed"}))

    def test_epoch_covers_the_core_package_and_config(self):
        base = es._cache_epoch()
        for probe in ("claudestats_core/pricing.py",
                      "claudestats_core/sessions.py",
                      "config.json",
                      "templates/session_detail.html",
                      "locales/en.json"):
            self.assertNotEqual(base, es._cache_epoch(_extra={probe: b"x"}),
                                f"{probe} must be part of the epoch")


class WarmRunMatchesColdRunTest(unittest.TestCase):
    """The only property that really matters: a warm run must produce what a
    cold run would have produced. Everything else is an optimisation detail."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cs-warm-"))
        self.pd = self.tmp / "projects"
        write_jsonl(self.pd / "proj1" / "S1.jsonl",
                    [user_line(), assistant_line(output_tokens=100)])
        write_jsonl(self.pd / "proj1" / "S2.jsonl",
                    [user_line(session_id="S2"),
                     assistant_line(session_id="S2", output_tokens=40)])

    def _cold(self, primary=None, additional=None):
        """Reference run with a throwaway cache dir, i.e. nothing reused."""
        with patched_sources(primary or self.pd, additional=additional):
            return _dump(es.parse_session_transcripts())

    def _run(self, cache_dir, primary=None, additional=None):
        with patched_sources(primary or self.pd, additional=additional,
                             cache_dir=cache_dir):
            return _dump(es.parse_session_transcripts())

    def test_int_keyed_histograms_survive_the_round_trip(self):
        """JSON has no integer keys. hour_hist and weekday_hist are indexed
        by int, so a naive round trip hands them back as strings - and
        build_dashboard_data sums them into a shared histogram, where "11"
        and 11 become two separate hours.

        Two hours that sort differently as numbers than as text (2 before 11,
        "11" before "2") make the drift visible; a single-hour fixture cannot
        see it, because both spellings serialise identically."""
        write_jsonl(self.pd / "proj1" / "S1.jsonl",
                    [user_line(ts="2026-06-10T02:00:00Z"),
                     assistant_line(ts="2026-06-10T02:00:05Z"),
                     user_line(ts="2026-06-10T11:00:00Z"),
                     assistant_line(ts="2026-06-10T11:00:05Z", msg_id="m2")])
        cache = self.tmp / "cache-hist"
        self._run(cache)
        with patched_sources(self.pd, cache_dir=cache) as _es:
            warm = _es.parse_session_transcripts()
        hours = warm["S1"]["hour_hist"]
        self.assertTrue(hours, "fixture must produce hour buckets")
        self.assertTrue(all(isinstance(k, int) for k in hours),
                        f"hour_hist keys came back as {[type(k).__name__ for k in hours]}")
        weekdays = warm["S1"]["weekday_hist"]
        self.assertTrue(all(isinstance(k, int) for k in weekdays),
                        f"weekday_hist keys came back as {[type(k).__name__ for k in weekdays]}")

    def test_warm_state_is_type_identical_to_cold_state(self):
        """The strict version of the whole feature: not just equal numbers,
        equal Python types down to every dict key. Anything the cache cannot
        carry across a JSON round trip shows up here."""
        write_jsonl(self.pd / "proj1" / "S1.jsonl",
                    [user_line(ts="2026-06-10T02:00:00Z"),
                     assistant_line(ts="2026-06-10T02:00:05Z"),
                     user_line(ts="2026-06-11T11:00:00Z"),
                     assistant_line(ts="2026-06-11T11:00:05Z", msg_id="m2")])
        cache = self.tmp / "cache-typed"
        self._run(cache)
        with patched_sources(self.pd, cache_dir=cache) as _es:
            warm = _es.parse_session_transcripts()
        with patched_sources(self.pd) as _es:
            cold = _es.parse_session_transcripts()
        self.assertEqual(_typed_dump(warm), _typed_dump(cold))

    def test_unchanged_corpus_reuses_everything_and_matches(self):
        cache = self.tmp / "cache"
        first = self._run(cache)
        second = self._run(cache)
        self.assertEqual(first, second)
        manifest = json.loads((cache / "scan_cache.json").read_text())
        self.assertEqual(manifest["cache_format"], es.CACHE_FORMAT)
        self.assertEqual(len(manifest["files"]), 2)

    def test_appending_to_one_transcript_matches_a_cold_run(self):
        cache = self.tmp / "cache"
        self._run(cache)
        write_jsonl(self.pd / "proj1" / "S1.jsonl",
                    [user_line(), assistant_line(output_tokens=100),
                     user_line(ts="2026-06-10T11:00:00Z"),
                     assistant_line(ts="2026-06-10T11:00:05Z", msg_id="m2",
                                    output_tokens=500)])
        self.assertEqual(self._run(cache), self._cold())

    def test_a_new_session_matches_a_cold_run(self):
        cache = self.tmp / "cache"
        self._run(cache)
        write_jsonl(self.pd / "proj2" / "S3.jsonl",
                    [user_line(session_id="S3"),
                     assistant_line(session_id="S3", output_tokens=7)])
        self.assertEqual(self._run(cache), self._cold())

    def test_a_removed_transcript_matches_a_cold_run(self):
        cache = self.tmp / "cache"
        self._run(cache)
        (self.pd / "proj1" / "S2.jsonl").unlink()
        warm = self._run(cache)
        self.assertEqual(warm, self._cold())
        self.assertNotIn('"S2"', warm)

    def test_losing_the_winning_source_hands_over_to_the_duplicate(self):
        """S1 lives in two sources. The earlier one wins while it exists;
        once it is gone the cached state must hand the session to the other,
        not keep the dead winner's numbers."""
        other = self.tmp / "other" / "projects"
        write_jsonl(other / "proj1" / "S1.jsonl",
                    [user_line(), assistant_line(output_tokens=999)])
        extra = [{"label": "other", "projects_dir": other, "sudo_user": None}]
        cache = self.tmp / "cache-dup"
        warm_first = self._run(cache, additional=extra)
        self.assertEqual(warm_first, self._cold(additional=extra))
        # The additional source is checked before the primary dir, so the
        # 999-token copy is the one that counted.
        self.assertIn("999", warm_first)

        (other / "proj1" / "S1.jsonl").unlink()
        self.assertEqual(self._run(cache, additional=extra),
                         self._cold(additional=extra))

    def test_a_stale_epoch_forces_a_full_scan(self):
        cache = self.tmp / "cache"
        self._run(cache)
        path = cache / "scan_cache.json"
        data = json.loads(path.read_text())
        data["epoch"] = "0" * 64
        data["sessions"] = {"GHOST": {"session_id": "GHOST"}}
        path.write_text(json.dumps(data))
        warm = self._run(cache)
        self.assertNotIn("GHOST", warm)
        self.assertEqual(warm, self._cold())

    def test_a_corrupt_cache_is_survivable(self):
        cache = self.tmp / "cache"
        self._run(cache)
        (cache / "scan_cache.json").write_text("{not json")
        self.assertEqual(self._run(cache), self._cold())

    def test_no_cache_neither_reads_nor_writes(self):
        cache = self.tmp / "cache-off"
        saved = es.NO_CACHE
        es.NO_CACHE = True
        try:
            cold = self._run(cache)
        finally:
            es.NO_CACHE = saved
        self.assertEqual(cold, self._cold())
        self.assertFalse((cache / "scan_cache.json").exists())


class PageRenderKeyTest(unittest.TestCase):
    """The page cache fails differently from the session cache: not with
    wrong numbers, but with a page that is NOT rebuilt when it should be.
    So the key has to move whenever anything the page is built from moves."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cs-pagekey-"))
        self.pd = self.tmp / "projects"
        write_jsonl(self.pd / "proj1" / "S1.jsonl",
                    [user_line(), assistant_line(output_tokens=100)])
        self.sess = {"session_id": "S1", "project_dir": "proj1", "cost": 1.0}

    def _key(self, sess=None):
        with patched_sources(self.pd) as _es:
            _es.parse_session_transcripts()
            return _es._page_render_key(sess or self.sess, "proj1")

    def test_key_is_stable_for_an_unchanged_session(self):
        self.assertEqual(self._key(), self._key())

    def test_key_moves_when_the_aggregates_move(self):
        other = dict(self.sess, cost=2.0)
        self.assertNotEqual(self._key(), self._key(other))

    def test_key_moves_when_the_transcript_grows(self):
        before = self._key()
        write_jsonl(self.pd / "proj1" / "S1.jsonl",
                    [user_line(), assistant_line(output_tokens=100),
                     user_line(ts="2026-06-10T12:00:00Z")])
        self.assertNotEqual(before, self._key())

    def test_key_moves_with_the_epoch(self):
        """A template or pricing edit must rebuild every page, even though no
        transcript moved."""
        before = self._key()
        real = es._cache_epoch
        try:
            es._cache_epoch = lambda **kw: "0" * 64
            self.assertNotEqual(before, self._key())
        finally:
            es._cache_epoch = real

    def test_no_key_without_a_transcript(self):
        """A session with no transcript on disk can never be skipped: there
        is nothing to pin the page to."""
        with patched_sources(self.pd) as _es:
            _es.parse_session_transcripts()
            self.assertIsNone(
                _es._page_render_key({"session_id": "GONE",
                                      "project_dir": "proj1"}, "proj1"))


def _dump(sessions):
    return json.dumps(sessions, sort_keys=True, default=str)


def _typed_dump(obj):
    """Like _dump, but keeps the Python type of every key and value.

    json.dumps() spells 11 and "11" the same way, so a value-level compare
    is blind to exactly the drift a JSON round trip introduces. This one is
    not, which makes it the general guard against the hour_hist class of bug
    for fields nobody has thought of yet.
    """
    if isinstance(obj, dict):
        items = sorted(obj.items(), key=lambda kv: (type(kv[0]).__name__, str(kv[0])))
        return "{" + ",".join(f"{type(k).__name__}:{k!r}={_typed_dump(v)}"
                              for k, v in items) + "}"
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(_typed_dump(v) for v in obj) + "]"
    return f"{type(obj).__name__}:{obj!r}"


if __name__ == "__main__":
    unittest.main()
