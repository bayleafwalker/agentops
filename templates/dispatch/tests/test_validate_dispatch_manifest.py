"""Oracle for ``templates/dispatch/scripts/validate_dispatch_manifest.py``.

Every repository in this tree carries a ``<name>.dispatch.json`` and nothing
checks any of them. The agentops suite can reach the manifests inside agentops;
it cannot reach actionq's, appservice's, kctl's or the dozen others, and that
is exactly where the drift lands -- agentops' own manifest violated its own
schema (``skills.selected`` named skills the enum did not admit) and no one
knew until a checker was pointed at it. This packet is the checker every repo
can run for itself, so the oracle grades it as a COMMAND that takes manifest
paths, not as a library.

The seam under test::

    main(argv=None) -> int
    if __name__ == "__main__":
        raise SystemExit(main())

plus two pure helpers this file pins by name:

* ``resolve_template_root(manifest, manifest_path) -> Path`` -- where the
  skills directory listing is expected to live for one manifest;
* ``validate`` -- the module-level name through which the tool reaches
  ``schema_check.validate``. It is pinned because ``UnsupportedKeyword``
  handling can only be exercised by substituting the checker (the real schema
  is fully enforceable today), and a name that cannot be substituted cannot be
  tested. Either ``from schema_check import validate`` or a module attribute
  ``schema_check`` whose ``validate`` can be replaced satisfies it.

Choices this oracle makes where the packet spec leaves room, each pinned by a
test so the implementer inherits the decision rather than guessing:

1. ``skills.template_root`` resolution. The schema declares it optional with a
   ``default`` of an absolute agentops path. Absent from the manifest, the
   default is used -- and the default is read out of the schema file here, not
   hard-coded, so moving the skills tree moves both sides together. Present and
   absolute, it is used verbatim. Present and RELATIVE, it resolves against the
   directory holding the manifest, not the process CWD: this tool is run from
   sibling repositories against their own manifests, and a CWD-relative root
   would mean the same manifest validates differently depending on where the
   shell happened to be.

2. A ``template_root`` that does not exist on this machine is a WARNING, not a
   violation. This is the normal case, not the exceptional one: every manifest
   in this tree names ``/projects/dev/agentops/templates/dispatch/skills``, so
   a CI box or a checkout without agentops beside it would fail every manifest
   in the fleet for a condition the manifest author cannot fix. The schema enum
   -- the copy of that listing that actually shipped the bug -- is still
   enforced, so the run is not silently weakened; the tool says out loud that
   the directory cross-check was skipped and names the root it looked for.

3. The three failure modes are distinguished by MESSAGE, not by exit code.
   Exit codes stay binary (0 clean / non-zero any problem) because one
   invocation carries many manifests and can hit several modes at once -- a
   run over five files where one is missing and one violates the schema has no
   single code to return, and a scheme that picks one would report the other as
   though it had not happened. So: a missing file says so and names the path
   and never carries a ``$.`` breadcrumb; an unparseable file says JSON and
   names the path; a schema violation is the only mode that prints
   ``schema_check`` breadcrumbs. All three are non-zero, all three are
   pairwise distinct text.

Error WORDING is otherwise the implementer's. This file asserts on breadcrumbs,
paths, skill names, and a small set of case-insensitive keyword regexes -- never
on a whole sentence.

Fixtures are real files in real temp directories. A mocked filesystem would
test nothing here: the whole point of the skills cross-check is whether a
directory is on disk.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "templates/dispatch/scripts/validate_dispatch_manifest.py"
SCHEMA = ROOT / "templates/dispatch/manifest.schema.json"
MANIFEST = ROOT / "agentops.dispatch.json"
SCHEMA_CHECK = ROOT / "templates/dispatch/scripts/schema_check.py"
EXAMPLES = ROOT / "templates/dispatch/examples"

BREADCRUMB = re.compile(r"\$\.")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# Imported by module NAME, not by file location: the tool under test will
# ``import schema_check`` after putting the scripts directory on ``sys.path``,
# and a second copy loaded under another name would give ``UnsupportedKeyword``
# two distinct classes -- so the exception this oracle raises would sail
# straight through the tool's ``except``.
sys.path.insert(0, str(SCHEMA_CHECK.parent))
import schema_check  # noqa: E402
SCHEMA_DOC = json.loads(SCHEMA.read_text(encoding="utf-8"))
SCHEMA_DEFAULT_ROOT = (
    SCHEMA_DOC["properties"]["skills"]["properties"]["template_root"]["default"]
)
ENUM_SKILLS = (
    SCHEMA_DOC["properties"]["skills"]["properties"]["selected"]["items"]["enum"]
)


def clean_manifest(template_root=None, selected=("dispatch-build",)):
    """The smallest manifest the schema admits, as a v1 document."""
    manifest = {
        "schema_version": 1,
        "repo_id": "fixture-repo",
        "adoption_level": "observable",
        "routing": {
            "default_harness": "claude",
            "default_model_alias": "fast-build",
            "action_classes": {"build": {"enabled": True}},
        },
        "skills": {"selected": list(selected)},
        "verification": {"command_families": ["unit"]},
        "hooks": {"level": "audit", "publishers": ["git"]},
    }
    if template_root is not None:
        manifest["skills"]["template_root"] = str(template_root)
    return manifest


def violating_manifest(template_root=None):
    """Three violations at three distinct breadcrumbs, none of them the first key."""
    manifest = clean_manifest(template_root=template_root)
    manifest["repo_id"] = "not a valid id"          # $.repo_id  (pattern)
    manifest["adoption_level"] = "whenever"          # $.adoption_level (enum)
    manifest["routing"]["default_harness"] = "gpt"   # $.routing.default_harness
    return manifest


class _ValidatorCase(unittest.TestCase):
    """Shared plumbing: a temp dir, fixture writers, and in-process runs."""

    module = None

    @classmethod
    def load_module(cls):
        if _ValidatorCase.module is None:
            if not SCRIPT.exists():
                raise AssertionError(f"{SCRIPT} does not exist")
            _ValidatorCase.module = _load("validate_dispatch_manifest", SCRIPT)
        return _ValidatorCase.module

    def setUp(self):
        self.validator = self.load_module()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def skills_root(self, *names):
        root = self.tmp / "skills"
        root.mkdir(exist_ok=True)
        for name in names:
            (root / name).mkdir(exist_ok=True)
        return root

    def write(self, name, payload):
        path = self.tmp / name
        path.write_text(
            payload if isinstance(payload, str)
            else json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        return path

    def run_main(self, *argv):
        """Call ``main(argv)`` in process; return (code, stdout, combined)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.validator.main([str(a) for a in argv])
        self.assertIsInstance(code, int, "main must return an int exit code")
        return code, out.getvalue(), out.getvalue() + err.getvalue()

    @contextlib.contextmanager
    def checker_raising(self, message="synthetic unenforceable construct"):
        """Substitute ``validate`` so it raises ``UnsupportedKeyword``."""
        unsupported = getattr(
            self.validator, "UnsupportedKeyword", schema_check.UnsupportedKeyword)

        def boom(instance, schema, path="$"):
            raise unsupported(message)

        target = None
        if hasattr(self.validator, "validate"):
            target = (self.validator, "validate")
        elif hasattr(self.validator, "schema_check"):
            target = (self.validator.schema_check, "validate")
        self.assertIsNotNone(
            target,
            "the validator must reach the checker through a substitutable "
            "module-level name ('validate', or a 'schema_check' module "
            "attribute) so UnsupportedKeyword handling can be exercised",
        )
        holder, attribute = target
        original = getattr(holder, attribute)
        setattr(holder, attribute, boom)
        try:
            yield
        finally:
            setattr(holder, attribute, original)


class CleanManifestTests(_ValidatorCase):
    def test_clean_manifest_exits_zero(self):
        root = self.skills_root("dispatch-build")
        path = self.write("clean.dispatch.json", clean_manifest(root))
        code, _, combined = self.run_main(path)
        self.assertEqual(code, 0, combined)

    def test_clean_manifest_says_so(self):
        root = self.skills_root("dispatch-build")
        path = self.write("clean.dispatch.json", clean_manifest(root))
        _, stdout, _ = self.run_main(path)
        self.assertTrue(stdout.strip(), "a clean run printed nothing at all")
        self.assertRegex(
            stdout, r"(?i)\bok\b|valid|clean|pass",
            "a clean run must say the manifest is good, not stay silent",
        )

    def test_clean_manifest_prints_no_breadcrumbs(self):
        root = self.skills_root("dispatch-build")
        path = self.write("clean.dispatch.json", clean_manifest(root))
        _, _, combined = self.run_main(path)
        self.assertNotRegex(combined, BREADCRUMB)


class RepositoryManifestTests(_ValidatorCase):
    """The repo's own manifest, end to end, against the real schema."""

    def test_the_manifest_and_schema_are_where_this_oracle_expects(self):
        self.assertTrue(MANIFEST.is_file(), f"{MANIFEST} moved or vanished")
        self.assertTrue(SCHEMA.is_file(), f"{SCHEMA} moved or vanished")
        self.assertTrue(
            Path(SCHEMA_DEFAULT_ROOT).is_dir(),
            f"the schema's default skills root {SCHEMA_DEFAULT_ROOT} is not a "
            f"directory on this machine",
        )
        self.assertTrue(EXAMPLES.is_dir(), f"{EXAMPLES} moved or vanished")

    def test_agentops_own_manifest_validates_clean(self):
        code, stdout, combined = self.run_main(MANIFEST)
        self.assertEqual(code, 0, combined)
        self.assertNotRegex(combined, BREADCRUMB)
        self.assertTrue(stdout.strip())

    def test_the_shipped_examples_validate_clean(self):
        examples = sorted(EXAMPLES.glob("*.dispatch.json"))
        self.assertTrue(examples, "no example manifests found")
        code, _, combined = self.run_main(*examples)
        self.assertEqual(code, 0, combined)


class ViolationReportingTests(_ValidatorCase):
    def test_violating_manifest_exits_non_zero(self):
        root = self.skills_root("dispatch-build")
        path = self.write("bad.dispatch.json", violating_manifest(root))
        code, _, _ = self.run_main(path)
        self.assertNotEqual(code, 0)

    def test_every_violation_is_reported_not_just_the_first(self):
        root = self.skills_root("dispatch-build")
        instance = violating_manifest(root)
        path = self.write("bad.dispatch.json", instance)
        _, _, combined = self.run_main(path)
        for fragment in ("$.repo_id", "$.adoption_level",
                         "$.routing.default_harness"):
            self.assertIn(fragment, combined,
                          f"violation at {fragment} was not reported")

    def test_the_breadcrumbs_are_the_ones_schema_check_produced(self):
        root = self.skills_root("dispatch-build")
        instance = violating_manifest(root)
        path = self.write("bad.dispatch.json", instance)
        expected = schema_check.validate(instance, SCHEMA_DOC)
        self.assertEqual(len(expected), 3, "fixture drifted from the schema")
        _, _, combined = self.run_main(path)
        for violation in expected:
            self.assertIn(violation, combined,
                          "the tool must print schema_check's own breadcrumb")

    def test_the_offending_file_is_named(self):
        root = self.skills_root("dispatch-build")
        path = self.write("bad.dispatch.json", violating_manifest(root))
        _, _, combined = self.run_main(path)
        self.assertIn("bad.dispatch.json", combined)


class MultipleManifestTests(_ValidatorCase):
    def _files(self, specs):
        root = self.skills_root("dispatch-build")
        paths = []
        for index, bad in enumerate(specs):
            payload = violating_manifest(root) if bad else clean_manifest(root)
            if not bad:
                payload["repo_id"] = f"repo-{index}"
            paths.append(self.write(f"m{index}.dispatch.json", payload))
        return paths

    def test_five_clean_manifests_exit_zero(self):
        code, _, combined = self.run_main(*self._files([False] * 5))
        self.assertEqual(code, 0, combined)

    def test_a_failure_that_is_not_last_still_fails_the_run(self):
        paths = self._files([True, False, False, False, False])
        code, _, combined = self.run_main(*paths)
        self.assertNotEqual(
            code, 0,
            "the exit code tracked the last manifest, not 'any failed'",
        )
        self.assertIn("m0.dispatch.json", combined)

    def test_manifests_after_a_failure_are_still_checked(self):
        paths = self._files([True, False, True, False, False])
        code, _, combined = self.run_main(*paths)
        self.assertNotEqual(code, 0)
        self.assertIn("m0.dispatch.json", combined)
        self.assertIn("m2.dispatch.json", combined,
                      "checking stopped at the first failing manifest")

    def test_clean_manifests_are_still_reported_alongside_a_failure(self):
        paths = self._files([True, False, False, False, False])
        _, _, combined = self.run_main(*paths)
        for name in ("m1.dispatch.json", "m4.dispatch.json"):
            self.assertIn(name, combined,
                          "a five-file run reported on only the failure")


class SkillsCrossCheckTests(_ValidatorCase):
    """``skills.selected`` against the directory listing the enum copies."""

    def test_selected_skill_without_a_directory_is_reported_by_name(self):
        root = self.skills_root("dispatch-build")
        path = self.write(
            "m.dispatch.json",
            clean_manifest(root, selected=["dispatch-build", "dispatch-review"]),
        )
        code, _, combined = self.run_main(path)
        self.assertNotEqual(code, 0, combined)
        self.assertIn("dispatch-review", combined,
                      "the missing skill must be named")
        self.assertIn(str(root), combined,
                      "the root that was searched must be named")

    def test_a_selected_skill_with_a_directory_is_accepted(self):
        root = self.skills_root("dispatch-build", "dispatch-review")
        path = self.write(
            "m.dispatch.json",
            clean_manifest(root, selected=["dispatch-build", "dispatch-review"]),
        )
        code, _, combined = self.run_main(path)
        self.assertEqual(code, 0, combined)

    def test_extra_directories_in_the_root_are_not_a_violation(self):
        root = self.skills_root("dispatch-build", "some-unlisted-skill")
        path = self.write("m.dispatch.json", clean_manifest(root))
        code, _, combined = self.run_main(path)
        self.assertEqual(code, 0, combined)

    def test_a_file_where_a_skill_directory_belongs_is_reported(self):
        root = self.skills_root("dispatch-build")
        (root / "dispatch-review").write_text("not a directory", encoding="utf-8")
        path = self.write(
            "m.dispatch.json",
            clean_manifest(root, selected=["dispatch-build", "dispatch-review"]),
        )
        code, _, combined = self.run_main(path)
        self.assertNotEqual(code, 0, combined)
        self.assertIn("dispatch-review", combined)

    def test_absent_template_root_falls_back_to_the_schema_default(self):
        path = self.write("m.dispatch.json", clean_manifest(None))
        code, _, combined = self.run_main(path)
        self.assertEqual(
            code, 0,
            "with no template_root the schema's default root should have been "
            "used, and it holds dispatch-build\n" + combined,
        )

    def test_resolve_template_root_absent_is_the_schema_default(self):
        path = self.write("m.dispatch.json", clean_manifest(None))
        resolved = self.validator.resolve_template_root(
            clean_manifest(None), path)
        self.assertEqual(Path(resolved), Path(SCHEMA_DEFAULT_ROOT))

    def test_resolve_template_root_absolute_is_used_verbatim(self):
        root = self.skills_root("dispatch-build")
        path = self.write("m.dispatch.json", clean_manifest(root))
        resolved = self.validator.resolve_template_root(
            clean_manifest(root), path)
        self.assertEqual(Path(resolved), root)

    def test_resolve_template_root_relative_is_anchored_to_the_manifest(self):
        nested = self.tmp / "repo"
        (nested / "skills" / "dispatch-build").mkdir(parents=True)
        manifest = clean_manifest("skills")
        path = nested / "m.dispatch.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        resolved = self.validator.resolve_template_root(manifest, path)
        self.assertEqual(Path(resolved), nested / "skills")

    def test_a_relative_root_validates_from_any_working_directory(self):
        nested = self.tmp / "repo"
        (nested / "skills" / "dispatch-build").mkdir(parents=True)
        path = nested / "m.dispatch.json"
        path.write_text(json.dumps(clean_manifest("skills")), encoding="utf-8")
        cwd = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, cwd)
        code, _, combined = self.run_main(path)
        self.assertEqual(
            code, 0,
            "a relative template_root must anchor to the manifest's directory, "
            "not the process CWD\n" + combined,
        )


class MissingTemplateRootTests(_ValidatorCase):
    """A sibling repo naming an agentops path that is not on this machine."""

    def test_a_missing_root_is_a_warning_not_a_violation(self):
        absent = self.tmp / "no-such-agentops" / "skills"
        path = self.write("m.dispatch.json", clean_manifest(absent))
        code, _, combined = self.run_main(path)
        self.assertEqual(
            code, 0,
            "an absent skills root is the normal cross-repo case and must not "
            "fail an otherwise clean manifest\n" + combined,
        )

    def test_a_missing_root_is_announced_and_named(self):
        absent = self.tmp / "no-such-agentops" / "skills"
        path = self.write("m.dispatch.json", clean_manifest(absent))
        _, _, combined = self.run_main(path)
        self.assertIn(str(absent), combined)
        self.assertRegex(
            combined,
            r"(?i)skip|not (found|exist)|does not exist|unavailable|missing|warn",
            "the skipped directory cross-check must be said out loud",
        )

    def test_a_missing_root_does_not_disable_the_schema_enum(self):
        absent = self.tmp / "no-such-agentops" / "skills"
        manifest = clean_manifest(absent)
        manifest["skills"]["selected"] = ["totally-invented-skill"]
        path = self.write("m.dispatch.json", manifest)
        code, _, combined = self.run_main(path)
        self.assertNotEqual(
            code, 0,
            "the enum is the check that caught the real drift; an absent "
            "directory must not switch it off\n" + combined,
        )
        self.assertIn("$.skills.selected[0]", combined)


class FailureModeTests(_ValidatorCase):
    """Missing file, unparseable file, and schema violation are three problems."""

    def _three(self):
        root = self.skills_root("dispatch-build")
        missing = self.tmp / "nowhere.dispatch.json"
        broken = self.write("broken.dispatch.json", "{ not json ,,, ")
        bad = self.write("bad.dispatch.json", violating_manifest(root))
        return missing, broken, bad

    def test_a_missing_file_fails_and_is_named(self):
        missing, _, _ = self._three()
        code, _, combined = self.run_main(missing)
        self.assertNotEqual(code, 0)
        self.assertIn("nowhere.dispatch.json", combined)
        self.assertRegex(
            combined, r"(?i)not found|no such file|does not exist|missing|cannot")

    def test_an_unparseable_file_fails_and_is_named(self):
        _, broken, _ = self._three()
        code, _, combined = self.run_main(broken)
        self.assertNotEqual(code, 0)
        self.assertIn("broken.dispatch.json", combined)
        self.assertRegex(combined, r"(?i)json|parse|decode")

    def test_the_three_modes_do_not_report_identically(self):
        missing, broken, bad = self._three()
        reports = {}
        for label, path in (("missing", missing), ("broken", broken),
                            ("bad", bad)):
            code, _, combined = self.run_main(path)
            self.assertNotEqual(code, 0, label)
            reports[label] = combined.replace(str(self.tmp), "<tmp>")
        text = {label: re.sub(r"\S+\.dispatch\.json", "<file>", value)
                for label, value in reports.items()}
        self.assertNotEqual(text["missing"], text["broken"])
        self.assertNotEqual(text["missing"], text["bad"])
        self.assertNotEqual(text["broken"], text["bad"])

    def test_only_a_schema_violation_carries_breadcrumbs(self):
        missing, broken, bad = self._three()
        for path in (missing, broken):
            _, _, combined = self.run_main(path)
            self.assertNotRegex(
                combined, BREADCRUMB,
                "an unreadable file is not a schema violation and must not be "
                "dressed up as one",
            )
        _, _, combined = self.run_main(bad)
        self.assertRegex(combined, BREADCRUMB)

    def test_an_unreadable_file_does_not_abort_the_rest_of_the_run(self):
        root = self.skills_root("dispatch-build")
        missing, broken, bad = self._three()
        clean = self.write("clean.dispatch.json", clean_manifest(root))
        code, _, combined = self.run_main(missing, broken, clean, bad)
        self.assertNotEqual(code, 0)
        self.assertIn("$.repo_id", combined,
                      "the run stopped before reaching the last manifest")
        self.assertIn("clean.dispatch.json", combined)


class UnenforceableSchemaTests(_ValidatorCase):
    """``UnsupportedKeyword`` must be reported, never swallowed or fatal.

    The real schema is fully enforceable today, so this is pinned by
    substituting ``validate``. If the schema ever regains a construct
    ``schema_check`` refuses to fake, the worst outcome is not a traceback --
    it is a clean bill of health over a schema that was never applied.
    """

    def test_it_does_not_crash(self):
        root = self.skills_root("dispatch-build")
        path = self.write("clean.dispatch.json", clean_manifest(root))
        with self.checker_raising():
            code, _, _ = self.run_main(path)
        self.assertIsInstance(code, int)

    def test_it_is_not_reported_as_clean(self):
        root = self.skills_root("dispatch-build")
        path = self.write("clean.dispatch.json", clean_manifest(root))
        with self.checker_raising():
            code, _, combined = self.run_main(path)
        self.assertNotEqual(
            code, 0,
            "an unenforceable schema reported a clean manifest\n" + combined,
        )

    def test_it_says_the_schema_cannot_be_fully_enforced(self):
        root = self.skills_root("dispatch-build")
        path = self.write("clean.dispatch.json", clean_manifest(root))
        with self.checker_raising("unsupported keyword 'dependentSchemas'"):
            _, _, combined = self.run_main(path)
        self.assertRegex(
            combined, r"(?i)enforc|unsupported",
            "the report must say the schema cannot be fully enforced",
        )
        self.assertIn("dependentSchemas", combined,
                      "the construct named by the exception must survive")


class RunAsACommandTests(_ValidatorCase):
    """The tool is run, not imported: a real subprocess, a real exit status.

    A previous packet in this repo passed 31 tests over a script with no
    ``if __name__ == "__main__":`` block at all -- every test called ``main``.
    Run as a command it printed nothing and exited 0. These tests would have
    caught it.
    """

    def _run(self, *argv):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(
            [sys.executable, str(SCRIPT), *[str(a) for a in argv]],
            capture_output=True, text=True, env=env, cwd=str(ROOT),
        )

    def test_the_script_exists(self):
        self.assertTrue(SCRIPT.is_file(), f"{SCRIPT} does not exist")

    def test_the_happy_path_runs_and_says_so(self):
        result = self._run(MANIFEST)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            result.stdout.strip(),
            "running the script produced no stdout -- is there a __main__ "
            "block wired to main()?",
        )
        self.assertRegex(result.stdout, r"(?i)\bok\b|valid|clean|pass")

    def test_a_failing_manifest_exits_non_zero_as_a_process(self):
        root = self.skills_root("dispatch-build")
        path = self.write("bad.dispatch.json", violating_manifest(root))
        result = self._run(path)
        self.assertNotEqual(
            result.returncode, 0,
            "the process exited 0 over a violating manifest",
        )
        self.assertRegex(result.stdout + result.stderr, BREADCRUMB)

    def test_no_arguments_is_a_usage_error(self):
        result = self._run()
        self.assertNotEqual(result.returncode, 0)


class StubDiscriminationTests(_ValidatorCase):
    """Two stubs this suite must reject, stated plainly.

    * ``def main(argv=None): return 0`` -- returns 0, prints nothing. It fails
      here because a clean run must SAY the manifest is clean (in process and
      as a subprocess), and because a violating manifest must be reported and
      must exit non-zero.
    * a main that reports every violation faithfully but always ``return 0``.
      It fails here because the exit status is the only part a caller in
      another repository's CI can see; a report nobody's shell notices is not
      a gate.

    Both properties are asserted throughout this file. They are restated in
    this class so the discrimination is not an emergent side effect of some
    other assertion but a stated requirement.
    """

    def test_a_silent_main_is_not_enough(self):
        root = self.skills_root("dispatch-build")
        path = self.write("clean.dispatch.json", clean_manifest(root))
        code, stdout, _ = self.run_main(path)
        self.assertEqual(code, 0)
        self.assertTrue(stdout.strip(), "a stub that prints nothing passes")

    def test_reporting_without_a_non_zero_exit_is_not_enough(self):
        root = self.skills_root("dispatch-build")
        path = self.write("bad.dispatch.json", violating_manifest(root))
        code, _, combined = self.run_main(path)
        self.assertRegex(combined, BREADCRUMB)
        self.assertNotEqual(code, 0, "violations were reported but exit was 0")


if __name__ == "__main__":
    unittest.main()
