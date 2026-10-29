"""Checks for per-post conda-forge MatchSpec metadata and single-env aggregation."""

import importlib.util
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("render-site.py")
MODULE_SPEC = importlib.util.spec_from_file_location("render_site", SCRIPT)
render = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(render)


class PackageMetadataTests(unittest.TestCase):
    def test_render_inputs_follow_quarto_config(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "_quarto.yml").write_text(
                'project:\n  render:\n    - "*.qmd"\n    - "posts/**/*.qmd"\n'
                '    - "research/index.qmd"\n'
            )
            (root / "index.qmd").write_text("---\ntitle: Home\n---\n")
            (root / "posts" / "new").mkdir(parents=True)
            (root / "posts" / "new" / "index.qmd").write_text(
                "---\ntitle: New\narea: geek\n---\n")
            (root / "research").mkdir()
            (root / "research" / "index.qmd").write_text("---\ntitle: Research\n---\n")
            (root / "docs").mkdir()
            (root / "docs" / "unused.qmd").write_text("---\nci-packages: [r-arrow]\n---\n")
            with patch.object(render, "ROOT", root):
                paths, whole = render.find_documents(".")
                self.assertTrue(whole)
                self.assertEqual(
                    {p.relative_to(root).as_posix() for p in paths},
                    {"index.qmd", "posts/new/index.qmd", "research/index.qmd"},
                )

    def test_post_area_is_required_and_valid(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            post = root / "posts" / "new" / "index.qmd"
            post.parent.mkdir(parents=True)
            with patch.object(render, "ROOT", root):
                for value in ["", "area: typo\n", "area: research\n"]:
                    post.write_text("---\ntitle: New\n" + value + "---\n")
                    if value == "area: research\n":
                        render.validate_posts([post])
                    else:
                        with self.assertRaisesRegex(ValueError, "area must be"):
                            render.validate_posts([post])
                with self.assertRaisesRegex(ValueError, "excluded"):
                    render.validate_posts([])

    def test_supported_pixi_matchspecs(self):
        for value, expected in [
            ("r-sf", "r-sf"),
            ("r-spdep", "r-spdep"),
            ("numpy=2.*", "numpy"),
            ("numpy>=1.26,<2", "numpy"),
            ("networkx>=3.4", "networkx"),
            ("r-data.table", "r-data.table"),
        ]:
            with self.subTest(value=value):
                self.assertEqual(render.spec_name(value), expected)

    def test_invalid_spec(self):
        for value in ["", "numpy; rm -rf /", "bad spec extra words"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    render.spec_name(value)

    def test_union_core_override_and_versioned_packages(self):
        with tempfile.TemporaryDirectory(dir=render.ROOT) as td:
            folder = Path(td)
            a, b = folder / "a.qmd", folder / "b.qmd"
            a.write_text('---\nci-packages:\n  - r-spdep\n  - "numpy=2.*"\n---\n')
            b.write_text('---\nci-packages:\n  - "networkx>=3.4"\n  - r-spdep\n---\n')
            specs, frozen = render.aggregate_specs([a, b], whole_site=True)
            self.assertFalse(frozen)
            self.assertIn("numpy=2.*", specs)
            self.assertNotIn("numpy", specs)
            self.assertIn("networkx>=3.4", specs)
            self.assertEqual(specs.count("r-spdep"), 1)

    def test_generic_spec_does_not_conflict_with_pinned_spec(self):
        with tempfile.TemporaryDirectory(dir=render.ROOT) as td:
            folder = Path(td)
            unpinned, pinned = folder / "a.qmd", folder / "b.qmd"
            unpinned.write_text('---\nci-packages:\n  - numpy\n---\n')
            pinned.write_text('---\nci-packages:\n  - "numpy=2.*"\n---\n')
            for pair in ([unpinned, pinned], [pinned, unpinned]):
                with self.subTest(order=[p.name for p in pair]):
                    specs, _ = render.aggregate_specs(pair, whole_site=True)
                    self.assertIn("numpy=2.*", specs)
                    self.assertNotIn("numpy", specs)

    def test_conflicts_raise_before_pixi_invocation(self):
        with tempfile.TemporaryDirectory(dir=render.ROOT) as td:
            folder = Path(td)
            a, b = folder / "a.qmd", folder / "b.qmd"
            a.write_text('---\nci-packages:\n  - "numpy=2.*"\n---\n')
            b.write_text('---\nci-packages:\n  - "numpy=1.*"\n---\n')
            with self.assertRaisesRegex(ValueError, "Conflicting specs"):
                render.aggregate_specs([a, b], whole_site=True)

    def test_auto_freeze_skips_packages_only_with_matching_source(self):
        with tempfile.TemporaryDirectory(dir=render.ROOT) as td:
            p = Path(td) / "auto.qmd"
            initial = "---\nci-packages:\n  - r-arrow\n---\n"
            p.write_text(initial)
            key = str(p.relative_to(render.ROOT))
            frozen_hash = render.freeze_fingerprint(p)
            with patch.object(render, "load_manifest", return_value={key: frozen_hash}), \
                    patch.object(render.Path, "is_file", return_value=True):
                specs, frozen = render.aggregate_specs([p], whole_site=True)
            self.assertNotIn("r-arrow", specs)
            self.assertEqual(frozen, [key])
            p.write_text(initial + "changed")
            with patch.object(render, "load_manifest", return_value={key: frozen_hash}), \
                    patch.object(render.Path, "is_file", return_value=True):
                specs, frozen = render.aggregate_specs([p], whole_site=True)
            self.assertIn("r-arrow", specs)
            self.assertFalse(frozen)

    def test_freeze_without_precomputed_result_fails_early(self):
        with tempfile.TemporaryDirectory(dir=render.ROOT) as td:
            p = Path(td) / "heavy.qmd"
            p.write_text('---\nci-packages:\n  - r-arrow\nexecute:\n  freeze: true\n---\n')
            with self.assertRaisesRegex(ValueError, "no frozen HTML result exists"):
                render.aggregate_specs([p], whole_site=True)

    def test_explicit_freeze_skips_only_in_global_render(self):
        with tempfile.TemporaryDirectory(dir=render.ROOT) as td:
            p = Path(td) / "frozen.qmd"
            p.write_text('---\nci-packages:\n  - r-arrow\nexecute:\n  freeze: true\n---\n')
            with patch.object(render.Path, "is_file", return_value=True):
                specs, frozen = render.aggregate_specs([p], whole_site=True)
            self.assertNotIn("r-arrow", specs)
            self.assertEqual(len(frozen), 1)
            specs, frozen = render.aggregate_specs([p], whole_site=False)
            self.assertIn("r-arrow", specs)
            self.assertFalse(frozen)


if __name__ == "__main__":
    unittest.main()
