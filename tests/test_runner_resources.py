"""Exercise only the resource helper, never the full experiment driver."""
import ast
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "run_all.py"


def helper(name, os_api):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == name)
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    namespace = {"os": os_api, "Path": Path}
    exec(compile(module, str(SOURCE), "exec"), namespace)
    return namespace[name]()


def affinity_query(os_api):
    return helper("current_cpu_affinity", os_api)


class RunnerResources(unittest.TestCase):
    def test_missing_plot_font_stops_before_campaign(self):
        with self.assertRaisesRegex(ValueError, "LOCALEMESH_PLOT_FONT"):
            helper("plot_font_arguments", SimpleNamespace(environ={}))

    def test_nonexistent_plot_font_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                helper("plot_font_arguments", SimpleNamespace(environ={"LOCALEMESH_PLOT_FONT": str(Path(temp) / "absent.ttf")}))

    def test_explicit_plot_font_is_forwarded(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "font with spaces.ttf"
            path.write_bytes(b"owned path-only fixture; actual font validation remains in analyze_sliced")
            result = helper("plot_font_arguments", SimpleNamespace(environ={"LOCALEMESH_PLOT_FONT": str(path)}))
            self.assertEqual(result, ["--font-file", str(path.resolve())])

    def test_absent_windows_api_remains_unavailable(self):
        self.assertIsNone(affinity_query(SimpleNamespace()))

    def test_available_os_affinity_is_sorted(self):
        self.assertEqual(affinity_query(SimpleNamespace(sched_getaffinity=lambda pid: {3, 1})), [1, 3])

    def test_unsupported_or_denied_query_remains_unavailable(self):
        for error in (OSError, NotImplementedError):
            def query(pid):
                raise error("Unavailable")
            with self.subTest(error=error.__name__):
                self.assertIsNone(affinity_query(SimpleNamespace(sched_getaffinity=query)))


if __name__ == "__main__":
    unittest.main()
