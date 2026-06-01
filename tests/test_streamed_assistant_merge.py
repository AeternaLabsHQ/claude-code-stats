import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _merge_streamed_assistant_entries


def _assist(mid, block, output_tokens=100, **extra):
    obj = {
        "type": "assistant",
        "uuid": extra.pop("uuid", "u-" + str(block)),
        "message": {
            "id": mid,
            "model": "claude-opus-4-8",
            "content": [block],
            "usage": {"output_tokens": output_tokens, "input_tokens": 10},
        },
    }
    obj.update(extra)
    return obj


THINK = {"type": "thinking", "thinking": "..."}
TEXT = {"type": "text", "text": "hello"}
TOOL = {"type": "tool_use", "id": "t1", "name": "Read", "input": {}}


class MergeStreamedAssistantTest(unittest.TestCase):
    def test_consecutive_same_id_merge_into_one(self):
        entries = [
            _assist("msg_A", THINK),
            _assist("msg_A", TEXT),
            _assist("msg_A", TOOL),
        ]
        out = _merge_streamed_assistant_entries(entries)
        self.assertEqual(len(out), 1)
        self.assertEqual(
            [b["type"] for b in out[0]["message"]["content"]],
            ["thinking", "text", "tool_use"],
        )

    def test_usage_taken_once_from_first(self):
        entries = [_assist("msg_A", THINK, output_tokens=500),
                   _assist("msg_A", TOOL, output_tokens=500)]
        out = _merge_streamed_assistant_entries(entries)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["message"]["usage"]["output_tokens"], 500)

    def test_different_ids_not_merged(self):
        entries = [_assist("msg_A", TEXT), _assist("msg_B", TEXT)]
        out = _merge_streamed_assistant_entries(entries)
        self.assertEqual(len(out), 2)

    def test_assistant_without_id_not_merged(self):
        a = _assist(None, TEXT); a["message"].pop("id", None)
        b = _assist(None, TEXT); b["message"].pop("id", None)
        out = _merge_streamed_assistant_entries([a, b])
        self.assertEqual(len(out), 2)

    def test_same_id_merged_across_interleaved_tool_results(self):
        # Agentic turns interleave one response's tool_use blocks with the
        # tool_result (type:"user") entries that come back. message.id is
        # globally unique per API response, so all blocks of one id must
        # merge into a single assistant entry even when not consecutive.
        tr = {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}}
        entries = [_assist("msg_A", TOOL), tr, _assist("msg_A", TOOL)]
        out = _merge_streamed_assistant_entries(entries)
        assistants = [e for e in out if e["type"] == "assistant"]
        self.assertEqual(len(assistants), 1)
        self.assertEqual(len(assistants[0]["message"]["content"]), 2)
        # the interleaved tool_result entry is preserved
        self.assertEqual(len([e for e in out if e["type"] == "user"]), 1)

    def test_two_responses_with_interleaving_stay_separate(self):
        tr = {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}}
        entries = [_assist("msg_A", TOOL, output_tokens=200), tr,
                   _assist("msg_A", TEXT, output_tokens=200),
                   _assist("msg_B", TOOL, output_tokens=50)]
        out = _merge_streamed_assistant_entries(entries)
        assistants = [e for e in out if e["type"] == "assistant"]
        self.assertEqual(len(assistants), 2)
        by_id = {a["message"]["id"]: a for a in assistants}
        self.assertEqual(len(by_id["msg_A"]["message"]["content"]), 2)
        self.assertEqual(by_id["msg_A"]["message"]["usage"]["output_tokens"], 200)
        self.assertEqual(len(by_id["msg_B"]["message"]["content"]), 1)

    def test_input_not_mutated(self):
        entries = [_assist("msg_A", THINK), _assist("msg_A", TOOL)]
        _merge_streamed_assistant_entries(entries)
        # original first entry still has a single block
        self.assertEqual(len(entries[0]["message"]["content"]), 1)

    def test_non_split_session_passthrough(self):
        # one entry already carrying all blocks (older format) is unchanged
        e = _assist("msg_A", THINK)
        e["message"]["content"] = [THINK, TEXT, TOOL]
        out = _merge_streamed_assistant_entries([e])
        self.assertEqual(len(out), 1)
        self.assertEqual(len(out[0]["message"]["content"]), 3)


if __name__ == "__main__":
    unittest.main()
