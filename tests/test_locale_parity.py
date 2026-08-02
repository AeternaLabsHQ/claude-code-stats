"""Locale parity guard: en.json and de.json must stay structurally identical,
free of em dashes, and every __L_*__ token used in templates must resolve."""
import json
import re
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
LOCALES = BASE / "locales"
TEMPLATES = BASE / "templates"


def flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = prefix + k
        if isinstance(v, dict):
            out.update(flatten(v, key + "."))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                list_key = key + "." + str(i)
                if isinstance(item, dict):
                    out.update(flatten(item, list_key + "."))
                else:
                    out[list_key] = item
        else:
            out[key] = v
    return out


class LocaleParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
        cls.de = json.loads((LOCALES / "de.json").read_text(encoding="utf-8"))
        cls.flat_en = flatten(cls.en)
        cls.flat_de = flatten(cls.de)

    def test_key_sets_identical(self):
        only_en = set(self.flat_en) - set(self.flat_de)
        only_de = set(self.flat_de) - set(self.flat_en)
        self.assertFalse(only_en or only_de,
                         f"only in en: {sorted(only_en)}; only in de: {sorted(only_de)}")

    def test_placeholders_match(self):
        ph = re.compile(r"\{[a-zA-Z0-9_]+\}")
        for key, en_val in self.flat_en.items():
            de_val = self.flat_de.get(key)
            if not isinstance(en_val, str) or not isinstance(de_val, str):
                continue
            self.assertEqual(sorted(ph.findall(en_val)), sorted(ph.findall(de_val)),
                             f"placeholder mismatch in {key}")

    def test_no_em_dashes(self):
        for name, flat in (("en", self.flat_en), ("de", self.flat_de)):
            for key, val in flat.items():
                if isinstance(val, str):
                    self.assertNotIn("—", val, f"em dash in {name}:{key}")

    def test_template_tokens_resolve(self):
        valid = set()
        for sec, val in self.en.items():
            if isinstance(val, dict):
                for k in val:
                    valid.add(f"__L_{sec}_{k}__")
            elif isinstance(val, str):
                valid.add(f"__L_{sec}__")
        sources = (list(TEMPLATES.glob("*.html")) + list(TEMPLATES.glob("*.js"))
                   + list((TEMPLATES / "components").glob("*.js")))
        self.assertTrue(sources, "no template sources found")
        token_re = re.compile(r"__L_[A-Za-z0-9_]+__")
        for path in sources:
            for tok in token_re.findall(path.read_text(encoding="utf-8")):
                self.assertIn(tok, valid, f"{path.name}: unresolved token {tok}")


if __name__ == "__main__":
    unittest.main()
