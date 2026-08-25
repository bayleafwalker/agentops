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

    def test_the_scan_does_not_blow_up_on_a_long_unbroken_token(self):
        """A transcript is megabytes and arbitrary: it holds minified files,
        base64 blobs and lines with no whitespace in them. A pattern that
        backtracks catastrophically on one of those hangs the capture step,
        which sits between a finished worker and its evidence.

        The bound is deliberately loose. A correct implementation does this in
        tens of milliseconds; the point is to fail an exponential one, not to
        police the constant factor.
        """
        # The scan is INTERRUPTED rather than timed. Measuring afterwards only
        # works if the call returns: an exponential pattern does not return, so
        # a wall-clock assertion placed after it hangs the suite instead of
        # failing it. SIGALRM turns the hang into a failure.
        import signal

        def _fire(signum, frame):
            raise TimeoutError("scan did not return")

        previous = signal.signal(signal.SIGALRM, _fire)
        try:
            for size in (50_000, 200_000):
                with self.subTest(size=size):
                    signal.setitimer(signal.ITIMER_REAL, 2.0)
                    try:
                        self.scan("a" * size)
                    except TimeoutError:
                        self.fail(
                            f"scanning {size} unbroken characters did not finish in 2s; "
                            "a pattern is backtracking catastrophically"
                        )
                    finally:
                        signal.setitimer(signal.ITIMER_REAL, 0)
        finally:
            signal.signal(signal.SIGALRM, previous)

    def test_the_names_still_tell_the_kinds_apart(self):
        seen = {k: frozenset(self.scan(s)) for k, s in MUST_DETECT.items()}
        self.assertGreater(
            len({frozenset(v) for v in seen.values()}), 1,
            "every kind reports the same names; the return value is a count",
        )


class EscapedTranscriptTests(unittest.TestCase):
    """A worker transcript is a stream of JSON, so its text still carries the
    escapes: a newline is the two characters ``\\`` and ``n``, not a line
    break. Three receipts in one session were withheld because of it."""

    #: The exact text that withheld the V6-E, V6-F and V6-G receipts. The value
    #: is eleven characters; the twenty-character run is made entirely of the
    #: escapes that follow it.
    WITHHELD = r'nWORKER_PLACEHOLDER_API_KEY = \"local-only\"\n\n\ndef'

    def test_the_placeholder_that_withheld_three_receipts_is_not_a_finding(self):
        self.assertEqual(driver.scan_for_secrets(self.WITHHELD), [])

    def test_a_short_value_does_not_become_long_through_its_escapes(self):
        self.assertEqual(driver.scan_for_secrets(r'token = \"abc\"\n\n\n\n\n\n\ndef f():'), [])

    def test_a_genuinely_long_value_is_still_a_finding(self):
        self.assertIn(
            "secret_assignment",
            driver.scan_for_secrets('password = "correcthorsebatterystaple123"'),
        )

    def test_a_secret_escaped_inside_a_json_string_is_now_found(self):
        # The other direction, and the reason decoding beats loosening the
        # pattern: before decoding, an escaped quote hid the value entirely.
        self.assertIn(
            "secret_assignment",
            driver.scan_for_secrets(r'\"api_key\": \"correcthorsebatterystaple123\"'),
        )

    def test_a_vendor_token_is_found_in_either_form(self):
        raw = "ghp_abcdefghijklmnopqrstuvwxyz"
        self.assertIn("github_token", driver.scan_for_secrets(raw))
        self.assertIn("github_token", driver.scan_for_secrets(r'\"' + raw + r'\"'))

    def test_decoding_leaves_text_without_escapes_alone(self):
        plain = 'password = "correcthorsebatterystaple123"'
        self.assertEqual(driver.decode_transcript_escapes(plain), plain)

    def test_a_doubly_escaped_newline_is_read_as_a_newline(self):
        # Deliberate, and a real loss of information: after two levels of
        # escaping, "a literal backslash followed by n" and "a newline escaped
        # twice" are the same characters, and nothing can tell them apart. The
        # scanner reads them as a newline, because the alternative -- treating
        # every escaped newline as an opaque token -- is what let a value run
        # past twenty characters and withhold every receipt of a session.
        # Only the SCANNED copy is decoded; the stored transcript is untouched.
        self.assertEqual(driver.decode_transcript_escapes(r"a\\nb"), "a\nb")

    def test_an_unknown_escape_keeps_its_backslash(self):
        self.assertEqual(driver.decode_transcript_escapes(r"a\qb"), r"a\qb")

    def test_prose_still_produces_no_findings_after_decoding(self):
        self.assertEqual(
            driver.scan_for_secrets(r"the token is rotated weekly\nand the password too"), []
        )

    def test_a_doubly_escaped_transcript_is_decoded_all_the_way(self):
        # The receipt text is escaped twice: once at source, because the
        # worker's stdout is JSON lines whose values are themselves escaped,
        # and again when the payload is serialised. A single pass leaves the
        # false positive standing, which is why the first fix was incomplete.
        doubled = r'WORKER_PLACEHOLDER_API_KEY = \\\"local-only\\\"\\n631:'
        self.assertEqual(driver.scan_for_secrets(doubled), [])

    def test_decoding_terminates_and_never_grows(self):
        # Decoding removes backslashes, so it is contracting and always
        # terminates. The pass bound means a pathological input may stop short
        # of its fixed point -- which is the safe direction: less decoding, not
        # an unbounded loop on a hostile transcript.
        text = "\\" * 200 + "n"
        decoded = driver.decode_transcript_escapes(text)
        self.assertLessEqual(len(decoded), len(text))
        self.assertLessEqual(len(driver.decode_transcript_escapes(decoded)), len(decoded))

    def test_a_genuinely_long_value_survives_repeated_decoding(self):
        self.assertIn(
            "secret_assignment",
            driver.scan_for_secrets(r'\\"password\\": \\"correcthorsebatterystaple123\\"'),
        )


if __name__ == "__main__":
    unittest.main()
