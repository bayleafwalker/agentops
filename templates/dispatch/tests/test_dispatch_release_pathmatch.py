"""Coordinator-authored oracle for spec row M-11 — one path matcher, not two.

The driver decides the L-2 ``path-outside-writable`` stop with ``_path_allowed``,
a bare ``fnmatch`` over the packet's ``writable_patch_paths``. ``hybrid_dispatch``
decides the very same question at validate time with ``_matches_any``, which also
understands directory-prefix patterns (``docs/``) and treats ``docs/**`` as
covering ``docs`` itself.

Two matchers for one question means a packet can validate ``fit`` and then have
every one of its touched paths rejected by the driver as outside the writable
set -- or, worse, the reverse. This row makes the driver ask the same question
the validator already answers.

Written against the M-11 spec row only. The driver has one matcher today and the
validator has another, so the agreement fixtures below fail.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


driver = _load("dispatch_release_pathmatch_subject", SCRIPTS / "dispatch_release.py")
validator = _load("hybrid_dispatch_pathmatch_reference", SCRIPTS / "hybrid_dispatch.py")

#: (path, patterns) pairs spanning every pattern form the two callers use.
#: The expected answer is deliberately not written down here: the row's whole
#: content is that the driver agrees with the validator, so the validator IS the
#: expectation. Writing the answers out by hand would let both drift together.
CASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # directory-prefix form, as manifest scope roots are written
    ("docs/evidence/x.json", ("docs/",)),
    ("docs", ("docs/",)),
    ("templates/dispatch/scripts/dispatch_release.py", ("templates/dispatch/scripts/",)),
    ("other/x.py", ("docs/",)),
    # ``/**`` form, as packets are written
    ("docs/evidence/x.json", ("docs/**",)),
    ("docs", ("docs/**",)),
    ("docs/a/b/c.json", ("docs/**",)),
    ("docsx/a.json", ("docs/**",)),
    # exact paths
    ("templates/dispatch/scripts/dispatch_release.py",
     ("templates/dispatch/scripts/dispatch_release.py",)),
    ("templates/dispatch/scripts/hybrid_dispatch.py",
     ("templates/dispatch/scripts/dispatch_release.py",)),
    # ordinary globs, which already worked and must keep working
    ("templates/dispatch/tests/test_x.py", ("templates/dispatch/tests/test_*.py",)),
    ("templates/dispatch/tests/other.py", ("templates/dispatch/tests/test_*.py",)),
    # several patterns at once, and the empty set
    ("docs/a.json", ("templates/**", "docs/**")),
    ("docs/a.json", ()),
)


class PathMatcherAgreementTests(unittest.TestCase):
    """§M-11 — the driver asks the question the validator already answers."""

    def test_the_driver_exposes_one_matcher(self):
        self.assertTrue(
            hasattr(driver, "_path_allowed"),
            "the driver has no _path_allowed to align",
        )

    def test_the_driver_agrees_with_the_validator_on_every_pattern_form(self):
        for path, patterns in CASES:
            with self.subTest(path=path, patterns=patterns):
                expected = validator._matches_any(path, list(patterns))
                actual = driver._path_allowed(path, list(patterns))
                self.assertEqual(
                    actual, expected,
                    f"driver says {actual} and the validator says {expected} "
                    f"for {path!r} against {list(patterns)!r}",
                )

    def test_a_directory_prefix_pattern_admits_files_under_it(self):
        # The single case that motivated the row: a packet whose
        # writable_patch_paths use the manifest's directory-prefix form
        # validates fit, then has every touched path rejected by the driver.
        self.assertTrue(
            driver._path_allowed(
                "templates/dispatch/scripts/dispatch_release.py",
                ["templates/dispatch/scripts/"],
            ),
            "a directory-prefix writable path rejects the file it contains",
        )

    def test_a_double_star_pattern_admits_the_directory_itself(self):
        self.assertTrue(
            driver._path_allowed("docs", ["docs/**"]),
            "docs/** does not admit docs itself",
        )

    def test_paths_outside_every_pattern_are_still_refused(self):
        # The matcher must not become permissive: this is the guard that makes
        # the L-2 path-outside-writable stop mean anything.
        for path, patterns in (
            ("other/x.py", ("docs/",)),
            ("docsx/a.json", ("docs/**",)),
            ("templates/dispatch/scripts/hybrid_dispatch.py",
             ("templates/dispatch/scripts/dispatch_release.py",)),
            ("anything", ()),
        ):
            with self.subTest(path=path, patterns=patterns):
                self.assertFalse(
                    driver._path_allowed(path, list(patterns)),
                    f"{path!r} was admitted by {list(patterns)!r}",
                )


if __name__ == "__main__":
    unittest.main()
