"""Tests for tools/calibrate_write_categories.py using a fake API client."""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from calibrate_write_categories import calibrate, make_anthropic_counter


class _Resp:
    def __init__(self, n):
        self.input_tokens = n


class _ApiError(Exception):
    def __init__(self, status_code):
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class _FakeMessages:
    """count_tokens fake: 7 tokens fixed overhead + one token per word.
    `failures` is a list of (model, status_code) entries, each consumed by
    the FIRST matching call (so retries succeed afterwards)."""

    def __init__(self, failures=None):
        self.failures = list(failures or [])
        self.calls = []

    def count_tokens(self, model, messages):
        self.calls.append(model)
        for i, (match, status) in enumerate(self.failures):
            if match == model:
                self.failures.pop(i)
                raise _ApiError(status)
        text = messages[0]["content"]
        return _Resp(7 + len(text.split()))


class _FakeClient:
    def __init__(self, **kw):
        self.messages = _FakeMessages(**kw)


def _counter(**kw):
    return make_anthropic_counter("claude-haiku-4-5",
                                  client=_FakeClient(**kw),
                                  sleep=lambda s: None)


class CounterTest(unittest.TestCase):
    def test_exact_token_count_no_off_by_one(self):
        count = _counter()
        toks, degraded = count("alpha beta gamma", "claude-opus-4-7")
        self.assertEqual(toks, 3)  # not 2: the "." baseline token is added back
        self.assertFalse(degraded)

    def test_transient_429_does_not_poison_model(self):
        count = _counter(failures=[("claude-opus-4-7", 429)])
        toks, degraded = count("alpha beta", "claude-opus-4-7")
        self.assertEqual((toks, degraded), (2, False))
        toks2, degraded2 = count("alpha beta gamma", "claude-opus-4-7")
        self.assertEqual((toks2, degraded2), (3, False))

    def test_model_rejection_degrades_and_flags(self):
        count = _counter(failures=[("claude-opus-4-1", 404)])
        toks, degraded = count("alpha beta", "claude-opus-4-1")
        self.assertEqual(toks, 2)
        self.assertTrue(degraded)


class CalibrateTest(unittest.TestCase):
    def test_degraded_blocks_excluded_from_per_model_table(self):
        count = _counter(failures=[("claude-opus-4-1", 404)])
        samples = {"screen_text": [
            {"payload": "alpha beta gamma delta", "model": "claude-opus-4-1"},
            {"payload": "alpha beta", "model": "claude-opus-4-8"},
        ]}
        calib = calibrate(samples, count, "fake")
        models = [pm["model"] for pm in calib["per_model"]]
        self.assertEqual(models, ["claude-opus-4-8"])
        self.assertEqual(calib["degraded_blocks"], 1)
        # Degraded blocks still count toward the category stats.
        self.assertEqual(calib["categories"]["screen_text"]["n"], 2)


if __name__ == "__main__":
    unittest.main()
