"""Experiment-ID latching and per-(model, ID, day) reply buckets."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claudestats_core import settings
from claudestats_core.experiments import (
    DEFAULT_CORRECTION_WORDS, HIST_STEPS, bucket_key, hist_bin, hist_median,
    is_correction, is_interactive, merge_bucket, new_bucket, normalize_atis,
    session_experiment_ids, split_key)
from claudestats_core.sessions import (
    SessionFileMeta, absorb_file, rehydrate_session)

MODEL = "claude-opus-4-8"
DAY = "2026-06-10"
AAA = "a" * 16
BBB = "b" * 16


def latch(value, sid="S1"):
    return {"type": "atis-latch", "atis": value, "sessionId": sid}


def reply(msg_id, content=None, output_tokens=100, sid="S1", model=MODEL,
          ts="2026-06-10T10:00:05Z", entrypoint=None, effort=None,
          usage_extra=None):
    usage = {"input_tokens": 10, "output_tokens": output_tokens}
    usage.update(usage_extra or {})
    obj = {"type": "assistant", "sessionId": sid, "timestamp": ts,
           "uuid": "u-" + msg_id,
           "message": {"id": msg_id, "model": model,
                       "content": (content if content is not None
                                   else [{"type": "text", "text": "hi"}]),
                       "usage": usage}}
    if entrypoint is not None:
        obj["entrypoint"] = entrypoint
    if effort is not None:
        obj["effort"] = effort
    return obj


def prompt(text, sid="S1", ts="2026-06-10T10:00:01Z"):
    return {"type": "user", "sessionId": sid, "timestamp": ts,
            "uuid": "p-" + str(abs(hash((text, ts)))),
            "message": {"role": "user", "content": text}}


def tool_result(text, is_error=True, sid="S1", ts="2026-06-10T10:00:06Z",
                tool_use_id="t"):
    return {"type": "user", "sessionId": sid, "timestamp": ts,
            "uuid": "r-" + str(abs(hash((text, ts)))),
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tool_use_id,
                 "is_error": is_error, "content": text}]}}


def tu(name, **inp):
    return {"type": "tool_use", "id": "x", "name": name, "input": inp}


def at(minutes=0, day=10, hour=10):
    """ISO timestamp `minutes` after 2026-06-<day> <hour>:00 UTC."""
    from datetime import datetime, timedelta, timezone
    t = datetime(2026, 6, day, hour, tzinfo=timezone.utc)
    return (t + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def key(atis="", entry="", effort="", model=MODEL):
    return bucket_key(model, atis, entry, effort)


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

    def test_hist_steps_is_32(self):
        self.assertEqual(HIST_STEPS, 32)

    def test_bucket_key_and_split_key(self):
        self.assertEqual(bucket_key(MODEL, AAA, "cli", "high"),
                         f"{MODEL}|{AAA}|cli|high")
        self.assertEqual(bucket_key(MODEL, "", None, None), f"{MODEL}|||")
        self.assertEqual(split_key(f"{MODEL}|{AAA}|cli|high"),
                         (MODEL, AAA, "cli", "high"))
        self.assertEqual(split_key(f"{MODEL}|{AAA}"), (MODEL, AAA, "", ""))
        self.assertEqual(split_key(f"{MODEL}|||"), (MODEL, "", "", ""))

    def test_is_interactive(self):
        self.assertTrue(is_interactive("cli"))
        self.assertTrue(is_interactive(""))
        self.assertFalse(is_interactive("sdk-ts"))
        self.assertFalse(is_interactive("sdk-cli"))

    def test_session_experiment_ids_with_four_part_keys(self):
        sess = {"experiments": {
            key(AAA, "cli", "high"): {}, key(AAA, "sdk-ts", ""): {},
            key(BBB): {}, key(): {}, f"{MODEL}|{AAA[:3]}": {}}}
        self.assertEqual(session_experiment_ids(sess),
                         sorted({AAA, BBB, AAA[:3]}))

    def test_is_correction(self):
        words = DEFAULT_CORRECTION_WORDS
        self.assertTrue(is_correction("nein, das ist falsch", words))
        self.assertTrue(is_correction("NO that is wrong", words))
        self.assertTrue(is_correction("das funktioniert nicht", words))
        self.assertTrue(is_correction("it doesn't work", words))
        self.assertFalse(is_correction("Nonsense, carry on", words))
        self.assertFalse(is_correction("know it all", words))
        self.assertFalse(is_correction("nein " + "x" * 200, words))
        self.assertFalse(is_correction("nein", []))

    def test_is_correction_typographic_apostrophes(self):
        words = list(DEFAULT_CORRECTION_WORDS)
        self.assertTrue(is_correction("it doesn\u2019t work", words))
        self.assertTrue(is_correction("it doesn\u2018t work", words))
        # A configured word with a curly apostrophe matches a plain one.
        self.assertTrue(is_correction("that doesn't help",
                                      ["doesn\u2019t help"]))

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
        self.assertEqual(exp[key()][DAY]["replies"], 2)
        self.assertEqual(exp[key(AAA)][DAY]["replies"], 2)
        self.assertEqual(exp[key(BBB)][DAY]["replies"], 1)

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
        b = sess["experiments"][key()][DAY]
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
        b = sess["experiments"][key()][DAY]
        self.assertEqual(b["text_before"], 0)

    def test_text_only_reply_is_not_text_before(self):
        b = absorb([reply("m1", [{"type": "text", "text": "answer"}])]
                   )["S1"]["experiments"][key()][DAY]
        self.assertEqual(b["replies"], 1)
        self.assertEqual(b["tool_replies"], 0)
        self.assertEqual(b["text_before"], 0)

    def test_two_text_blocks_before_tool_count_once(self):
        t = {"type": "text", "text": "step"}
        b = absorb([reply("m1", [t, dict(t), READ])]
                   )["S1"]["experiments"][key()][DAY]
        self.assertEqual(b["tool_replies"], 1)
        self.assertEqual(b["text_before"], 1)

    def test_stream_split_counts_once(self):
        lines = [
            reply("m1", [{"type": "thinking", "thinking": ""}], 9),
            reply("m1", [READ], 120),
            reply("m1", [bash(5)], 300),
        ]
        for i, ln in enumerate(lines):
            ln["uuid"] = f"u{i}"
        b = absorb(lines)["S1"]["experiments"][key()][DAY]
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
        b = restored["S1"]["experiments"][key(AAA)][DAY]
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


class RicherBucketTest(unittest.TestCase):
    def setUp(self):
        self._words = settings.EXP_CORRECTION_WORDS

    def tearDown(self):
        settings.configure(exp_correction_words=self._words)

    def test_key_carries_entrypoint_and_effort(self):
        sess = absorb([latch(AAA),
                       reply("m1", entrypoint="cli", effort="high")])["S1"]
        self.assertEqual(list(sess["experiments"]),
                         [f"{MODEL}|{AAA}|cli|high"])

    def test_missing_effort_and_entrypoint_give_blank_parts(self):
        sess = absorb([latch(AAA), reply("m1")])["S1"]
        self.assertEqual(list(sess["experiments"]), [f"{MODEL}|{AAA}||"])
        sess = absorb([reply("m1", entrypoint=7, effort=["x"])])["S1"]
        self.assertEqual(list(sess["experiments"]), [f"{MODEL}|||"])

    def test_only_exact_atis_latch_type_matches(self):
        stat = {"type": "statistics", "atis": "v1." + BBB,
                "sessionId": "S1"}
        sess = absorb([stat, reply("m1")])["S1"]
        self.assertEqual(list(sess["experiments"]), [key()])

    def test_session_dict_is_json_serializable(self):
        sess = absorb([latch(AAA), prompt("nein"),
                       reply("m1", [tu("Edit", file_path="/a")],
                             entrypoint="cli", effort="high"),
                       reply("m2", ts=at(0, day=20))])["S1"]
        json.dumps(sess, default=dict)  # must not raise
        self.assertIsInstance(sess["exp_start_ms"], int)
        self.assertNotIn("seen_calls", json.dumps(sess, default=dict))

    def test_thinking_tokens_counted_only_when_reported(self):
        sess = absorb([
            reply("m1", usage_extra={"output_tokens_details":
                                     {"thinking_tokens": 500}}),
            reply("m2"),
            reply("m3", usage_extra={"output_tokens_details": {}}),
        ])["S1"]
        b = sess["experiments"][key()][DAY]
        self.assertEqual(b["replies"], 3)
        self.assertEqual(b["think_replies"], 1)
        self.assertEqual(b["think_tokens"], 500)
        self.assertEqual(b["think_hist"], {hist_bin(500): 1})

    def test_thinking_tokens_use_last_stream_line(self):
        lines = [reply("m1", [{"type": "thinking", "thinking": ""}], 9,
                       usage_extra={"output_tokens_details":
                                    {"thinking_tokens": 3}}),
                 reply("m1", [READ], 300,
                       usage_extra={"output_tokens_details":
                                    {"thinking_tokens": 250}})]
        lines[1]["uuid"] = "u2"
        b = absorb(lines)["S1"]["experiments"][key()][DAY]
        self.assertEqual(b["think_replies"], 1)
        self.assertEqual(b["think_tokens"], 250)

    def test_late_replies_excluded(self):
        sess = absorb([
            reply("m1", ts=at(0, day=10)),
            reply("m2", ts=at(0, day=17)),   # exactly 7 days: still counted
            reply("m3", ts=at(0, day=18)),   # 8 days: late
        ])["S1"]
        days = sess["experiments"][key()]
        self.assertEqual(sorted(days), ["2026-06-10", "2026-06-17"])
        self.assertEqual(sess["experiments_late"], {key(): 1})

    def test_late_cutoff_counts_from_session_start(self):
        # A user line before the first reply starts the clock.
        sess = absorb([prompt("go", ts=at(0, day=10)),
                       reply("m1", ts=at(0, day=18))])["S1"]
        self.assertNotIn("experiments", sess)
        self.assertEqual(sess["experiments_late"], {key(): 1})

    def test_prompt_attributed_to_next_reply(self):
        sess = absorb([
            reply("m1", ts=at(0)),
            prompt("please continue", ts=at(1)),
            prompt("and then", ts=at(2)),
            reply("m2", ts=at(3)),
        ])["S1"]
        b = sess["experiments"][key()][DAY]
        self.assertEqual(b["replies"], 2)
        self.assertEqual(b["prompts"], 2)
        self.assertEqual(b["corrections"], 0)

    def test_prompt_before_any_reply_counts_on_first_reply(self):
        b = absorb([prompt("hello", ts=at(0)), reply("m1", ts=at(1))]
                   )["S1"]["experiments"][key()][DAY]
        self.assertEqual(b["prompts"], 1)

    def test_error_and_interrupt_attributed_to_previous_reply(self):
        sess = absorb([
            reply("m1", [tu("Bash", command="false")], ts=at(0)),
            tool_result("Exit code 1", ts=at(1)),
            reply("m2", [READ], ts=at(2)),
            prompt("[Request interrupted by user]", ts=at(3)),
            reply("m3", ts=at(4), entrypoint="cli"),
        ])["S1"]
        exp = sess["experiments"]
        self.assertEqual(exp[key()][DAY]["tool_errors"], 1)
        self.assertEqual(exp[key()][DAY]["interrupts"], 1)
        self.assertEqual(exp[key(entry="cli")][DAY]["tool_errors"], 0)
        self.assertEqual(exp[key(entry="cli")][DAY]["interrupts"], 0)

    def test_error_without_previous_reply_is_dropped(self):
        sess = absorb([tool_result("Exit code 1", ts=at(0)),
                       reply("m1", ts=at(1))])["S1"]
        b = sess["experiments"][key()][DAY]
        self.assertEqual((b["tool_errors"], b["interrupts"],
                          b["rejected"]), (0, 0, 0))

    def test_error_after_late_reply_is_dropped(self):
        sess = absorb([reply("m1", ts=at(0, day=10)),
                       reply("m2", ts=at(0, day=20)),
                       tool_result("Exit code 1", ts=at(1, day=20))])["S1"]
        b = sess["experiments"][key()]["2026-06-10"]
        self.assertEqual(b["tool_errors"], 0)

    def test_rejection_counts_as_rejected_not_tool_error(self):
        sess = absorb([
            reply("m1", [tu("Bash", command="rm x")], ts=at(0)),
            tool_result("The user doesn't want to proceed with this tool "
                        "use. The tool use was rejected", ts=at(1)),
        ])["S1"]
        b = sess["experiments"][key()][DAY]
        self.assertEqual(b["rejected"], 1)
        self.assertEqual(b["tool_errors"], 0)

    def test_hook_and_cancelled_errors_not_counted(self):
        sess = absorb([
            reply("m1", [tu("Bash", command="x")], ts=at(0)),
            tool_result("PreToolUse hook error: boom", ts=at(1)),
            tool_result("Cancelled: parallel tool call errored", ts=at(1)),
            tool_result("fine", is_error=False, ts=at(1)),
        ])["S1"]
        b = sess["experiments"][key()][DAY]
        self.assertEqual((b["tool_errors"], b["rejected"]), (0, 0))

    def test_repeat_calls_and_re_edits(self):
        sess = absorb([
            reply("m1", [tu("Read", file_path="/a"),
                         tu("Edit", file_path="/a", old_string="x")],
                  ts=at(0)),
            reply("m2", [tu("Read", file_path="/a"),
                         tu("Edit", file_path="/a", old_string="y")],
                  ts=at(1)),
            reply("m3", [tu("Write", file_path="/b")], ts=at(2)),
        ])["S1"]
        b = sess["experiments"][key()][DAY]
        self.assertEqual(b["tool_calls"], 5)
        self.assertEqual(b["repeat_calls"], 1)
        self.assertEqual(b["edit_calls"], 3)
        self.assertEqual(b["re_edits"], 1)

    def test_notebook_edit_uses_notebook_path(self):
        b = absorb([
            reply("m1", [tu("NotebookEdit", notebook_path="/n.ipynb")],
                  ts=at(0)),
            reply("m2", [tu("NotebookEdit", notebook_path="/n.ipynb")],
                  ts=at(1)),
        ])["S1"]["experiments"][key()][DAY]
        self.assertEqual((b["edit_calls"], b["re_edits"]), (2, 1))

    def test_repeat_state_is_per_session_and_per_file(self):
        rd = [tu("Read", file_path="/a")]
        first = absorb([reply("m1", rd, ts=at(0)),
                        reply("m2", rd, ts=at(1))])
        absorb([reply("m3", rd, ts=at(2))], sessions=first, stem="S1-resume")
        b = first["S1"]["experiments"][key()][DAY]
        self.assertEqual(b["repeat_calls"], 1)  # new file: state starts over

    def test_correction_prompt(self):
        b = absorb([
            prompt("nein, das ist falsch", ts=at(0)),
            prompt("nein " + "x" * 500, ts=at(0)),
            prompt("Nonsense", ts=at(0)),
            prompt("looks good", ts=at(0)),
            reply("m1", ts=at(1)),
        ])["S1"]["experiments"][key()][DAY]
        self.assertEqual(b["prompts"], 4)
        self.assertEqual(b["corrections"], 1)

    def test_correction_list_comes_from_settings(self):
        settings.configure(exp_correction_words=["stopp"])
        b = absorb([prompt("stopp das", ts=at(0)), prompt("nein", ts=at(0)),
                    reply("m1", ts=at(1))])["S1"]["experiments"][key()][DAY]
        self.assertEqual(b["corrections"], 1)

    def test_active_ms(self):
        b = absorb([
            reply("m1", ts=at(0)),
            reply("m2", ts=at(5)),
            reply("m3", ts=at(125)),   # 2 h gap: idle, adds nothing
        ])["S1"]["experiments"][key()][DAY]
        self.assertEqual(b["active_ms"], 300000)

    def test_exp_start_ms_is_min_timestamp(self):
        sess = absorb([prompt("a", ts=at(5)), reply("m1", ts=at(0))])["S1"]
        from datetime import datetime, timezone
        self.assertEqual(
            sess["exp_start_ms"],
            int(datetime(2026, 6, 10, 10, tzinfo=timezone.utc).timestamp()
                * 1000))

    def test_new_bucket_fields_roundtrip_and_merge(self):
        first = absorb([prompt("nein", ts=at(0)),
                        reply("m1", [tu("Edit", file_path="/a")], ts=at(1),
                              usage_extra={"output_tokens_details":
                                           {"thinking_tokens": 40}}),
                        tool_result("Exit code 1", ts=at(2))])
        restored = {"S1": rehydrate_session(
            json.loads(json.dumps(first["S1"], default=dict)))}
        b = restored["S1"]["experiments"][key()][DAY]
        total = new_bucket()
        merge_bucket(total, b)
        merge_bucket(total, b)
        for k, v in (("prompts", 2), ("corrections", 2), ("tool_errors", 2),
                     ("think_replies", 2), ("think_tokens", 80),
                     ("edit_calls", 2), ("tool_calls", 2)):
            self.assertEqual(total[k], v, k)
        self.assertEqual(total["think_hist"][hist_bin(40)], 2)


class CorrectionWordsConfigTest(unittest.TestCase):
    def setUp(self):
        import io
        from contextlib import redirect_stdout
        self.buf = io.StringIO()
        self.redirect = redirect_stdout(self.buf)
        self.redirect.__enter__()

    def tearDown(self):
        self.redirect.__exit__(None, None, None)

    def parse(self, *args):
        from extract_stats import parse_correction_words
        return parse_correction_words(*args)

    def test_missing_gives_defaults_silently(self):
        self.assertEqual(self.parse(), DEFAULT_CORRECTION_WORDS)
        self.assertEqual(self.buf.getvalue(), "")

    def test_valid_list_is_used(self):
        self.assertEqual(self.parse([" stopp ", "halt"]), ["stopp", "halt"])
        self.assertEqual(self.buf.getvalue(), "")

    def test_invalid_values_fall_back_with_one_warning(self):
        for raw in (None, "nein", 5, ["ok", 3], ["ok", "  "], {"a": 1}):
            self.buf.truncate(0)
            self.buf.seek(0)
            self.assertEqual(self.parse(raw), DEFAULT_CORRECTION_WORDS, raw)
            self.assertEqual(self.buf.getvalue().count("WARNING"), 1, raw)

    def test_default_returns_a_copy(self):
        out = self.parse()
        out.append("zzz")
        self.assertNotIn("zzz", DEFAULT_CORRECTION_WORDS)


if __name__ == "__main__":
    unittest.main()
