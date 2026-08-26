"""Page templates (session / project detail) are built once per run.

_inject_locale does one str.replace per locale key over the whole template;
doing that per session page dominated runtime on large histories."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import extract_stats as es


class TemplateMemoTest(unittest.TestCase):
    def setUp(self):
        es._reset_template_cache()

    def test_session_template_injects_locale_once(self):
        with mock.patch.object(es, "_inject_locale",
                               wraps=es._inject_locale) as inj:
            a = es._get_session_html_template()
            b = es._get_session_html_template()
        self.assertEqual(a, b)
        self.assertEqual(inj.call_count, 1)

    def test_project_template_injects_locale_once(self):
        with mock.patch.object(es, "_inject_locale",
                               wraps=es._inject_locale) as inj:
            a = es._get_project_html_template()
            b = es._get_project_html_template()
        self.assertEqual(a, b)
        self.assertEqual(inj.call_count, 1)


if __name__ == "__main__":
    unittest.main()
