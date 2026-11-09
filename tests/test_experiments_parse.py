"""Experiment-ID latching and per-(model, ID, day) reply buckets."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claudestats_core.experiments import (
    hist_bin, hist_median, merge_bucket, new_bucket, normalize_atis)
from claudestats_core.sessions import (
    SessionFileMeta, absorb_file, rehydrate_session)

MODEL = "claude-opus-4-8"
DAY = "2026-06-10"
AAA = "a" * 16
BBB = "b" * 16


def latch(value, sid="S1"):
    return {"type": "atis-latch", "atis": value, "sessionId": sid}


def reply(msg_id, content=None, output_tokens=100, sid="S1", model=MODEL,
          ts="2026-06-10T10:00:05Z"):
    return {"type": "assistant", "sessionId": sid, "timestamp": ts,
            "uuid": "u-" + msg_id,
            "message": {"id": msg_id, "model": model,
                        "content": (content if content is not None
                                    else [{"type": "text", "text": "hi"}]),
                        "usage": {"input_tokens": 10,
                                  "output_tokens": output_tokens}}}


def absorb(objs, sessions=None, stem="S1", **meta_kw):
    sessions = {} if sessions is None else sessions
    meta = SessionFileMeta(source_label="test", file_session_id=stem,
                           project_name="p", **meta_kw)
    absorb_file(sessions, meta, objs)
    return sessions


def bash(n):
    return {"type": "tool_use", "id": "t", "name": "Bash",
            "input": {"command": "x" * n}}


READ = {"type": "tool_use", "id": "r", "name": "Read", "input": {}}


class HelpersTest(unittest.TestCase):
    def test_normalize_atis(self):
        self.assertEqual(
            normalize_atis("v1.5ddd0466fd524dad.t40F.8e9298b0.xx"),
            "5ddd0466fd524dad")
        self.assertEqual(normalize_atis("21e0afd842ce5836"),
                         "21e0afd842ce5836")
        self.assertEqual(normalize_atis(""), "")
        self.assertEqual(normalize_atis(None), "")
        self.assertEqual(normalize_atis(5), "")

    def test_hist_median_close(self):
        hist = {}
        for v in range(100, 1001):
            k = hist_bin(v)
            hist[k] = hist.get(k, 0) + 1
        med = hist_median(hist)
        self.assertLess(abs(med - 550) / 550, 0.10)
        self.assertIsNone(hist_median({}))

    def test_hist_bin_zero(self):
        self.assertEqual(hist_bin(0), "0")
        self.assertEqual(hist_bin(-3), "0")
        self.assertEqual(hist_median({"0": 3}), 0.0)


class AbsorbTest(unittest.TestCase):
    def test_latch_attribution_switches_mid_file(self):
        sess = absorb([
            reply("m0"),
            latch(AAA), reply("m1"), reply("m2"),
            latch(""), reply("m3"),
            latch("v1." + BBB + ".t40F.8e9298b0"), reply("m4"),
        ])["S1"]
        exp = sess["experiments"]
        self.assertEqual(exp[f"{MODEL}|"][DAY]["replies"], 2)
        self.assertEqual(exp[f"{MODEL}|{AAA}"][DAY]["replies"], 2)
        self.assertEqual(exp[f"{MODEL}|{BBB}"][DAY]["replies"], 1)

    def test_latch_only_file_creates_no_session(self):
        self.assertEqual(absorb([latch(AAA), latch("")]), {})

    def test_latch_does_not_count_as_message(self):
        sess = absorb([reply("m1"), latch(AAA)])["S1"]
        self.assertEqual(sess["message_count"], 1)

    def test_reply_metrics(self):
        sess = absorb([
            reply("m1", [{"type": "text", "text": "plan"}, bash(40), READ]),
            reply("m2", [bash(10)]),
        ])["S1"]
        b = sess["experiments"][f"{MODEL}|"][DAY]
        self.assertEqual(b["replies"], 2)
        self.assertEqual(b["multi_tool"], 1)
        self.assertEqual(b["tool_replies"], 2)
        self.assertEqual(b["text_before"], 1)
        self.assertEqual(b["bash_cmds"], 2)
        self.assertEqual(b["bash_hist"][hist_bin(40)], 1)
        self.assertEqual(b["bash_hist"][hist_bin(10)], 1)

    def test_blank_text_and_late_text_do_not_count_as_text_before(self):
        sess = absorb([
            reply("m1", [{"type": "text", "text": "  \n"}, READ]),
            reply("m2", [READ, {"type": "text", "text": "after"}]),
        ])["S1"]
        b = sess["experiments"][f"{MODEL}|"][DAY]
        self.assertEqual(b["text_before"], 0)

    def test_stream_split_counts_once(self):
        lines = [
            reply("m1", [{"type": "thinking", "thinking": ""}], 9),
            reply("m1", [READ], 120),
            reply("m1", [bash(5)], 300),
        ]
        for i, ln in enumerate(lines):
            ln["uuid"] = f"u{i}"
        b = absorb(lines)["S1"]["experiments"][f"{MODEL}|"][DAY]
        self.assertEqual(b["replies"], 1)
        self.assertEqual(b["multi_tool"], 1)
        self.assertEqual(b["output_tokens"], 300)
        self.assertEqual(b["out_hist"], {hist_bin(300): 1})

    def test_subagent_file_has_no_buckets(self):
        sess = absorb([latch(AAA), reply("m1")], stem="agent-1",
                      is_subagent=True, parent_session_id="S1")["agent-1"]
        self.assertNotIn("experiments", sess)

    def test_synthetic_model_and_no_timestamp_skipped(self):
        no_ts = reply("m2")
        del no_ts["timestamp"]
        sess = absorb([reply("m1", model="<synthetic>"), no_ts])["S1"]
        self.assertNotIn("experiments", sess)

    def test_buckets_survive_json_roundtrip(self):
        first = absorb([latch(AAA), reply("m1", [bash(40)], 300),
                        reply("m2", [READ], 50)])
        restored = {"S1": rehydrate_session(
            json.loads(json.dumps(first["S1"], default=dict)))}
        # Resumed-session shape: a second file stem, same sessionId.
        absorb([latch(AAA), reply("m3", [bash(40), READ], 300)],
               sessions=restored, stem="S1-resume")
        b = restored["S1"]["experiments"][f"{MODEL}|{AAA}"][DAY]
        self.assertEqual(b["replies"], 3)
        self.assertEqual(b["multi_tool"], 1)
        self.assertEqual(b["bash_cmds"], 2)
        self.assertEqual(b["out_hist"][hist_bin(300)], 2)
        self.assertEqual(b["out_hist"][hist_bin(50)], 1)
        self.assertEqual(b["output_tokens"], 650)

        total = new_bucket()
        merge_bucket(total, b)
        merge_bucket(total, b)
        self.assertEqual(total["replies"], 6)
        self.assertEqual(total["out_hist"][hist_bin(300)], 4)
        self.assertGreater(hist_median(total["out_hist"]), 0)


if __name__ == "__main__":
    unittest.main()
