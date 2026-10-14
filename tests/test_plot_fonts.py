"""Font-only regression tests; set P118_TEST_TTF and P118_TEST_CFF to existing files."""
import importlib.util
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "analyze_sliced.py"
spec = importlib.util.spec_from_file_location("analyze_sliced_plot_test", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PlotFontContract(unittest.TestCase):
    def test_missing_font_does_not_fall_back(self):
        with self.assertRaisesRegex(ValueError, "--font-file"):
            module.validated_plot_font(None)


def optional_plot_skip_reason():
    missing = []
    for package in ("matplotlib", "pypdf", "fontTools"):
        try:
            available = importlib.util.find_spec(package) is not None
        except (ImportError, ValueError):
            available = False
        if not available:
            missing.append(package)
    if missing:
        return "Optional plot dependencies unavailable: " + ", ".join(missing)
    absent = [name for name in ("P118_TEST_TTF", "P118_TEST_CFF")
              if not os.getenv(name) or not Path(os.environ[name]).is_file()]
    if absent:
        return "Existing optional font fixtures required: " + ", ".join(absent)
    return ""


PLOT_SKIP_REASON = optional_plot_skip_reason()


@unittest.skipIf(bool(PLOT_SKIP_REASON), PLOT_SKIP_REASON)
class OptionalPlotFonts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Imports are deferred until dependencies and real fixtures are present.
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from matplotlib import font_manager
            from matplotlib.text import Text
            from pypdf import PdfReader
            from fontTools.ttLib import TTFont
        except ImportError as exc:
            raise unittest.SkipTest(f"Optional plot dependency unavailable: {exc}") from exc
        cls.matplotlib, cls.plt = matplotlib, plt
        cls.font_manager, cls.Text = font_manager, Text
        cls.PdfReader, cls.TTFont = PdfReader, TTFont

    def test_cff_is_rejected_before_pdf_export(self):
        with patch("matplotlib.figure.Figure.savefig") as save:
            with self.assertRaisesRegex(ValueError, "CFF"):
                module.plot_sliced([], Path("."), Path(os.environ["P118_TEST_CFF"]))
            save.assert_not_called()

    def test_explicit_file_overrides_registered_otf_and_preserves_sizes(self):
        self.font_manager.fontManager.addfont(os.environ["P118_TEST_CFF"])
        font = module.validated_plot_font(Path(os.environ["P118_TEST_TTF"]))
        fig, ax = self.plt.subplots(figsize=(3.30, 2.58))
        ax.plot([100, 1000, 10000], [1, 10, 100], label="Full scan")
        ax.set_yscale("log")
        ax.set_xlabel("Emitted routes", fontsize=9)
        ax.set_ylabel("Time (ms), median and IQR", fontsize=9)
        ax.tick_params(labelsize=8)
        ax.legend(fontsize=7.1)
        fig.canvas.draw()
        texts = fig.findobj(match=self.Text)
        sizes = [text.get_fontsize() for text in texts]
        module.bind_plot_font(fig, font)
        self.assertEqual(sizes, [text.get_fontsize() for text in texts])
        for text in texts:
            self.assertEqual(Path(text.get_fontproperties().get_file()).resolve(), Path(font.get_file()))
        self.matplotlib.rcParams["pdf.fonttype"] = 42
        self.matplotlib.rcParams["pdf.use14corefonts"] = False
        out = io.BytesIO()
        fig.savefig(out, format="pdf")
        reader = self.PdfReader(out)
        for ref in reader.pages[0]["/Resources"]["/Font"].values():
            entry = ref.get_object()
            self.assertNotEqual(entry["/Subtype"], "/Type3")
            child = entry["/DescendantFonts"][0].get_object()
            self.assertEqual(child["/Subtype"], "/CIDFontType2")
            data = child["/FontDescriptor"]["/FontFile2"].get_object().get_data()
            with self.TTFont(io.BytesIO(data)) as embedded:
                self.assertIn("glyf", embedded)
                self.assertIn("loca", embedded)
                self.assertNotIn("CFF ", embedded)
        self.plt.close(fig)


if __name__ == "__main__":
    unittest.main()
