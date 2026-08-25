"""Build-side wiring for the palette config key and the favicon assets."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import extract_stats as es  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ["dashboard.html", "session_detail.html", "project_detail.html"]


class HtmlClassesTest(unittest.TestCase):
    def test_default_palette_yields_no_class(self):
        self.assertEqual(es._html_classes("default"), "")

    def test_colorblind_palette_yields_cvd_class(self):
        self.assertEqual(es._html_classes("colorblind"), "palette-cvd")

    def test_templates_carry_placeholder_on_html_tag(self):
        for name in TEMPLATES:
            html = (ROOT / "templates" / name).read_text(encoding="utf-8")
            self.assertIn('class="__HTML_CLASSES__"', html.split("<head>")[0], name)

    def test_rendered_pages_resolve_placeholder(self):
        old = es.PALETTE
        try:
            es.PALETTE = "colorblind"
            for html in (es.build_inline_html("{}"),
                         es._get_session_html_template(),
                         es._get_project_html_template()):
                self.assertIn('class="palette-cvd"', html)
                self.assertNotIn("__HTML_CLASSES__", html)
            es.PALETTE = "default"
            self.assertIn('class=""', es.build_inline_html("{}"))
        finally:
            es.PALETTE = old


class FaviconProvisionTest(unittest.TestCase):
    def _out(self):
        return Path(tempfile.mkdtemp(prefix="cs-favicon-"))

    def test_default_variant_is_terracotta_svg_plus_png(self):
        out = self._out()
        es._provision_favicon(out, variant="terracotta")
        svg = (out / "favicon.svg").read_text(encoding="utf-8")
        self.assertIn("#c2562f", svg)
        self.assertTrue((out / "favicon.png").read_bytes().startswith(b"\x89PNG"))

    def test_indigo_variant(self):
        out = self._out()
        es._provision_favicon(out, variant="indigo")
        self.assertIn("#5a62e7", (out / "favicon.svg").read_text(encoding="utf-8"))

    def test_unknown_variant_falls_back_to_terracotta(self):
        out = self._out()
        es._provision_favicon(out, variant="neon")
        self.assertIn("#c2562f", (out / "favicon.svg").read_text(encoding="utf-8"))

    def test_provisioning_overwrites_existing_files(self):
        out = self._out()
        (out / "favicon.svg").write_text("stale", encoding="utf-8")
        es._provision_favicon(out, variant="terracotta")
        self.assertNotEqual((out / "favicon.svg").read_text(encoding="utf-8"), "stale")

    def test_templates_link_svg_and_png_icons(self):
        html = (ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn('rel="icon" type="image/png" sizes="32x32" href="favicon.png"', html)
        self.assertIn('rel="icon" type="image/svg+xml" href="favicon.svg"', html)
        for name in ("session_detail.html", "project_detail.html"):
            html = (ROOT / "templates" / name).read_text(encoding="utf-8")
            self.assertIn('href="../favicon.png"', html, name)
            self.assertIn('href="../favicon.svg"', html, name)


class ConfigExampleTest(unittest.TestCase):
    def test_example_config_documents_new_keys(self):
        import json
        cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg.get("palette"), "default")
        self.assertEqual(cfg.get("favicon"), "terracotta")


if __name__ == "__main__":
    unittest.main()
