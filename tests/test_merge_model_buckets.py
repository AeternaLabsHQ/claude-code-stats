import sys
import unittest
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_stats import _merge_model_buckets


def _bucket(**kw):
    base = {
        "input_tokens": 0, "output_tokens": 0,
        "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
        "cache_5m_tokens": 0, "cache_1h_tokens": 0,
        "cost": 0.0, "calls": 0,
    }
    base.update(kw)
    return base


def _models(d):
    m = defaultdict(lambda: _bucket())
    for k, v in d.items():
        m[k] = _bucket(**v)
    return m


class MergeModelBucketsTest(unittest.TestCase):
    def test_adds_new_model(self):
        dst = _models({})
        src = _models({"opus": {"output_tokens": 100, "cost": 1.5, "calls": 2}})
        _merge_model_buckets(dst, src)
        self.assertEqual(dst["opus"]["output_tokens"], 100)
        self.assertEqual(dst["opus"]["cost"], 1.5)
        self.assertEqual(dst["opus"]["calls"], 2)

    def test_sums_existing_model(self):
        dst = _models({"opus": {"output_tokens": 50, "cost": 1.0, "calls": 1}})
        src = _models({"opus": {"output_tokens": 100, "cost": 1.5, "calls": 2}})
        _merge_model_buckets(dst, src)
        self.assertEqual(dst["opus"]["output_tokens"], 150)
        self.assertEqual(dst["opus"]["cost"], 2.5)
        self.assertEqual(dst["opus"]["calls"], 3)

    def test_mixed_models(self):
        dst = _models({"opus": {"input_tokens": 10}})
        src = _models({"opus": {"input_tokens": 5}, "haiku": {"input_tokens": 7}})
        _merge_model_buckets(dst, src)
        self.assertEqual(dst["opus"]["input_tokens"], 15)
        self.assertEqual(dst["haiku"]["input_tokens"], 7)

    def test_source_unchanged(self):
        dst = _models({})
        src = _models({"opus": {"output_tokens": 100}})
        _merge_model_buckets(dst, src)
        self.assertEqual(src["opus"]["output_tokens"], 100)


if __name__ == "__main__":
    unittest.main()
