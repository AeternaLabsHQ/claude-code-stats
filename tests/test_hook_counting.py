"""Hook counting across both transcript formats (issue #28).

Up to Claude Code 2.1.84 every hook run wrote a progress/hook_progress line.
Newer versions only leave a line when a run produces something: an
attachment (hook_success, async_hook_response, errors, context) or, for Stop
hooks, a system/stop_hook_summary line carrying hookCount.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claudestats_core.sessions import SessionFileMeta, absorb_file

TS = "2026-06-10T10:00:00Z"


def progress(hook, event, cmd="cmd"):
    return {"type": "progress", "sessionId": "S1", "timestamp": TS,
            "data": {"type": "hook_progress", "hookEvent": event,
                     "hookName": hook, "command": cmd}}


def att(atype, hook, event, tid, **extra):
    a = {"type": atype, "hookName": hook, "hookEvent": event, "toolUseID": tid}
    a.update(extra)
    return {"type": "attachment", "sessionId": "S1", "timestamp": TS,
            "attachment": a}


def async_resp(hook, event, pid):
    return {"type": "attachment", "sessionId": "S1", "timestamp": TS,
            "attachment": {"type": "async_hook_response", "hookName": hook,
                           "hookEvent": event, "processId": pid,
                           "exitCode": 0}}


def stop_summary(n):
    return {"type": "system", "subtype": "stop_hook_summary", "sessionId": "S1",
            "timestamp": TS, "hookCount": n,
            "hookInfos": [{"command": f"stop-{i}"} for i in range(n)]}


def hooks_of(objs):
    sessions = {}
    meta = SessionFileMeta(source_label="test", file_session_id="S1",
                           project_name="p")
    absorb_file(sessions, meta, objs)
    return dict(sessions["S1"]["hooks"])


class OldFormatTest(unittest.TestCase):
    def test_hook_progress_counts_every_line(self):
        self.assertEqual(hooks_of([
            progress("PostToolUse:Read", "PostToolUse"),
            progress("PostToolUse:Read", "PostToolUse"),
            progress("Stop", "Stop"),
        ]), {"PostToolUse:Read": 2, "Stop": 1})

    def test_stop_summary_next_to_hook_progress_is_not_counted_again(self):
        # 2.1.68 to 2.1.84 wrote both for the same Stop hooks.
        self.assertEqual(hooks_of([
            progress("Stop", "Stop", "a"), progress("Stop", "Stop", "b"),
            stop_summary(2),
        ]), {"Stop": 2})


class NewFormatTest(unittest.TestCase):
    def test_two_hooks_on_one_event_count_twice(self):
        # Two plugins with a SessionStart hook: same toolUseID, different
        # command. The matching context line carries no run of its own.
        self.assertEqual(hooks_of([
            att("hook_success", "SessionStart:startup", "SessionStart", "t1",
                command="plugin-a", exitCode=0),
            att("hook_success", "SessionStart:startup", "SessionStart", "t1",
                command="plugin-b", exitCode=0),
            att("hook_additional_context", "SessionStart", "SessionStart",
                "SessionStart", content=["ctx"]),
        ]), {"SessionStart:startup": 2})

    def test_async_responses_count_once_per_process(self):
        self.assertEqual(hooks_of([
            async_resp("PostToolUse:Write", "PostToolUse", "async_hook_1"),
            async_resp("PostToolUse:Write", "PostToolUse", "async_hook_2"),
        ]), {"PostToolUse:Write": 2})

    def test_stop_summary_counts_hook_count(self):
        self.assertEqual(hooks_of([stop_summary(3), stop_summary(1)]),
                         {"Stop": 4})

    def test_async_stop_hook_is_inside_the_summary(self):
        self.assertEqual(hooks_of([
            stop_summary(2),
            async_resp("Stop", "Stop", "async_hook_9"),
        ]), {"Stop": 2})

    def test_stop_hook_without_summary_still_counts(self):
        self.assertEqual(hooks_of([
            att("hook_success", "Stop", "Stop", "t1", command="c", exitCode=0),
        ]), {"Stop": 1})

    def test_context_counts_only_when_it_is_the_only_trace(self):
        self.assertEqual(hooks_of([
            # run A: context is all that is left of it
            att("hook_additional_context", "PostToolUse:Edit", "PostToolUse",
                "A", content=["ctx"]),
            # run B: has its own success line, context rides along
            att("hook_success", "PostToolUse:Edit", "PostToolUse", "B",
                command="c", exitCode=0),
            att("hook_additional_context", "PostToolUse:Edit", "PostToolUse",
                "B", content=["ctx"]),
        ]), {"PostToolUse:Edit": 2})

    def test_errors_and_blocks_count_as_runs(self):
        self.assertEqual(hooks_of([
            att("hook_non_blocking_error", "UserPromptSubmit",
                "UserPromptSubmit", "t1", command="c", exitCode=1),
            att("hook_cancelled", "UserPromptSubmit", "UserPromptSubmit",
                "t2", command="c"),
            att("hook_stopped_continuation", "PreToolUse:WebFetch",
                "PreToolUse", "t3", message="blocked"),
        ]), {"UserPromptSubmit": 2, "PreToolUse:WebFetch": 1})

    def test_other_attachments_are_ignored(self):
        self.assertEqual(hooks_of([
            {"type": "attachment", "sessionId": "S1", "timestamp": TS,
             "attachment": {"type": "skill_listing", "content": "x"}},
            {"type": "system", "subtype": "compact_boundary",
             "sessionId": "S1", "timestamp": TS},
        ]), {})


if __name__ == "__main__":
    unittest.main()
