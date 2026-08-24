"""Coordinator-authored oracle for spec row M-12 — what the secret scan misses.

``scan_for_secrets`` is the only control between worker output and a committed
file. Independent review of the shipped M-10a scan found two compounding gaps:

* it is case-sensitive throughout, so ``Authorization: Bearer`` is caught and
  ``authorization: bearer`` is not;
* its only general-purpose pattern requires ``=``, and the scan's own primary
  input is ``json.dumps(receipt)``, where every separator is ``:``. So on the
  receipt half the scan degrades to a handful of vendor prefixes.

Neither is hypothetical: ``cold_command_results[].stderr_tail`` is committed
verbatim, four thousand characters at a time.

The false-positive side is half the row and the harder half. A scan that fires
on ordinary transcript prose withholds every transcript, which is the same as
never capturing one -- so the fixtures below assert silence on a realistic
worker transcript, on base64-shaped build noise, and on git hashes, as firmly
as they assert detection.

Written against the M-12 spec row only.
"""
from __future__ import annotations

import importlib.util
import json
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


driver = _load("dispatch_release_scan_subject", SCRIPTS / "dispatch_release.py")

#: Assembled from fragments so no complete secret-shaped literal sits in this
#: file. None is real. Each must be detected wherever it appears.
MUST_DETECT: dict[str, str] = {
    # already caught by M-10a -- regressions here are as bad as the new misses
    "github_classic": "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8",
    "github_fine_grained": "github_pat_" + "11ABCDEFG0" + "a" * 22,
    "aws_key_id": "AKIA" + "IOSFODNN7EXAMPLE",
    "pem_header": "-----BEGIN RSA PRIVATE" + " KEY-----",
    "slack": "xoxb-" + "123456789012-1234567890123-" + "AbCdEfGhIjKlMnOpQrStUvWx",
    # case: the same header the shipped scan catches, lowercased
    "bearer_lowercase": "authorization: bearer " + ("s3cr3tv4lue" * 3),
    # the JSON separator -- the scan's own primary input shape
    "json_api_key": json.dumps({"api_key": "z" * 32}),
    "json_token_nested": json.dumps({"opts": {"Token": "q" * 40}}),
    # env-assignment form, uppercase name
    "env_export": "export API_KEY=" + "k" * 32,
    # vendor formats the shipped scan does not know
    "openai": "sk-" + "T3BlbkFJ" + "x" * 32,
    "anthropic": "sk-ant-" + "api03-" + "y" * 40,
    "google_api": "AIzaSy" + "B" * 33,
    "stripe_live": "sk_live_" + "5" * 24,
    "npm": "npm_" + "n" * 36,
    "pypi": "pypi-" + "AgEIcHlwaS5vcmc" + "p" * 32,
    "jwt": "eyJhbGciOiJIUzI1NiJ9." + "eyJzdWIiOiIxIn0." + "c2lnbmF0dXJlX2hlcmU",
    "url_basic_auth": "https://alice:" + "hunter2hunter2hunter2" + "@git.example.invalid/x",
    "aws_secret_access_key": 'aws_secret_access_key = "' + "A" * 30 + "b/c+dEfGh1" + '"',
}

#: Every one of these must return an EMPTY list. This is the half that decides
#: whether the capture is usable at all.
MUST_STAY_SILENT: dict[str, str] = {
    "prose": (
        "the worker read the packet and edited two files\n"
        "pytest reported 590 passed in 29.70s\n"
        "the gate was green and the disposition is candidate\n"
    ),
    "git_hashes": (
        "starting_commit 6ddd78ced05f8167d01e3927c3dd3bc26e74c794\n"
        "merged 55c739c1a2b3c4d5e6f708192a3b4c5d6e7f8091 into main\n"
    ),
    "base64_build_noise": (
        "sha256-xn+/C0WoDpMu57AZeEZcsHopqNRUyeb/vHvwwD+Z8kQ=\n"
        "/nix/store/53h5s92ld7x4pv7ys5f12wn88z3pg5pg-nixos-system-devbox\n"
    ),
    "json_without_secrets": json.dumps(
        {"stage": "gate", "disposition": "candidate",
         "gates": {"diff-nonempty": True, "registered-commands-green": False},
         "touched_paths": ["templates/dispatch/scripts/dispatch_release.py"]},
        indent=2,
    ),
    "prose_naming_the_concepts": (
        "the secret scan matched no patterns and the token budget held;\n"
        "the api_key handling is described in the runbook, password rotation too\n"
    ),
    "long_identifiers": (
        "execution_id 0f1e2d3c-4b5a-4978-8b6c-1a2b3c4d5e6f\n"
        "overlay_sha256 a9500e09af8772af224a0ea6f0ccd0efd4ccaf5774e4e624705ca87f2684c979\n"
    ),
}


class ScanHardeningTests(unittest.TestCase):
    """§M-12 — the scan sees the shapes its own input actually takes."""

    def setUp(self):
        self.scan = getattr(driver, "scan_for_secrets", None)
        self.assertIsNotNone(self.scan, "the driver has no scan_for_secrets")

    def test_every_secret_shape_is_detected(self):
        for kind, secret in MUST_DETECT.items():
            with self.subTest(kind=kind):
                findings = self.scan(f"prelude line\n{secret}\npostlude line\n")
                self.assertTrue(findings, f"{kind} was not detected")

    def test_a_finding_never_carries_the_secret(self):
        for kind, secret in MUST_DETECT.items():
            with self.subTest(kind=kind):
                for name in self.scan(f"x\n{secret}\ny\n"):
                    self.assertNotIn(secret, name, f"the finding quotes {kind}")
                    self.assertNotIn(secret[-12:], name, f"the finding quotes {kind}")

    def test_ordinary_output_produces_no_findings(self):
        for kind, text in MUST_STAY_SILENT.items():
            with self.subTest(kind=kind):
                self.assertEqual(
                    self.scan(text), [],
                    f"{kind} fired the scan; every transcript like it would be withheld",
                )

    def test_detection_is_case_insensitive(self):
        # The shipped scan caught "Authorization: Bearer" and missed the
        # lowercase form, which is what a shell or a JSON dump actually emits.
        for variant in (
            "AUTHORIZATION: BEARER " + ("s3cr3tv4lue" * 3),
            "authorization: bearer " + ("s3cr3tv4lue" * 3),
            "Authorization: Bearer " + ("s3cr3tv4lue" * 3),
        ):
            with self.subTest(variant=variant[:24]):
                self.assertTrue(self.scan(variant), "case decided whether it was seen")

    def test_the_json_separator_is_covered(self):
        # The scan's own primary input is json.dumps(receipt): every separator
        # is a colon, and the shipped general-purpose pattern required "=".
        for key in ("api_key", "apiKey", "token", "secret", "password"):
            with self.subTest(key=key):
                blob = json.dumps({"outer": {key: "v" * 32}}, indent=2)
                self.assertTrue(
                    self.scan(blob), f"a JSON {key} of 32 characters was not seen",
                )

    def test_the_names_still_tell_the_kinds_apart(self):
        seen = {k: frozenset(self.scan(s)) for k, s in MUST_DETECT.items()}
        self.assertGreater(
            len({frozenset(v) for v in seen.values()}), 1,
            "every kind reports the same names; the return value is a count",
        )


if __name__ == "__main__":
    unittest.main()
