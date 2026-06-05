"""Tests for _detect_cache_flushes: gap (TTL) and no-gap (anomaly) flushes."""
import unittest

from extract_stats import _detect_cache_flushes


def turn(ts_s, cache_creation, cache_read):
    """Build a turn dict; ts is given in seconds for readability."""
    return {"ts": ts_s * 1000, "cache_creation": cache_creation,
            "cache_read": cache_read, "model": "claude-opus-4-8"}


def steady_session():
    """Buildup + 3 steady post-buildup turns (history filled, 60s apart)."""
    return [
        turn(0, 10_000, 0),         # buildup: write-only
        turn(10, 500, 10_000),      # buildup over (read > creation)
        turn(70, 200, 10_500),
        turn(130, 200, 10_700),
        turn(190, 200, 10_900),
    ]


class TestDetectCacheFlushes(unittest.TestCase):
    def test_short_sessions_return_zeros(self):
        result = _detect_cache_flushes([turn(0, 100, 0), turn(10, 50, 200)], False)
        self.assertEqual(result, {"gap_flushes": 0, "nogap_flushes": 0,
                                  "nogap_rewrite_tokens": 0})

    def test_steady_session_has_no_flushes(self):
        result = _detect_cache_flushes(steady_session(), False)
        self.assertEqual(result["gap_flushes"], 0)
        self.assertEqual(result["nogap_flushes"], 0)

    def test_gap_flush_counted(self):
        # 400s pause (> 300s TTL) followed by a big rewrite
        turns = steady_session() + [turn(590, 50_000, 11_000)]
        result = _detect_cache_flushes(turns, False)
        self.assertEqual(result["gap_flushes"], 1)
        self.assertEqual(result["nogap_flushes"], 0)

    def test_nogap_flush_counted_on_read_collapse(self):
        # 60s gap (< TTL), big rewrite AND cache_read collapses -> anomaly
        turns = steady_session() + [turn(250, 50_000, 500)]
        result = _detect_cache_flushes(turns, False)
        self.assertEqual(result["gap_flushes"], 0)
        self.assertEqual(result["nogap_flushes"], 1)
        self.assertEqual(result["nogap_rewrite_tokens"], 50_000)

    def test_big_write_without_read_collapse_not_counted(self):
        # Big incremental write but cache still read fine -> legitimate work
        turns = steady_session() + [turn(250, 50_000, 11_200)]
        result = _detect_cache_flushes(turns, False)
        self.assertEqual(result["gap_flushes"], 0)
        self.assertEqual(result["nogap_flushes"], 0)

    def test_1h_cache_classifies_400s_pause_as_nogap(self):
        # With a 1h TTL a 400s pause cannot expire the cache -> a rewrite
        # with read collapse there is an anomaly, not a TTL victim
        turns = steady_session() + [turn(590, 50_000, 500)]
        result = _detect_cache_flushes(turns, True)
        self.assertEqual(result["gap_flushes"], 0)
        self.assertEqual(result["nogap_flushes"], 1)


if __name__ == "__main__":
    unittest.main()
