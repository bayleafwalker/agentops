"""Coordinator hand-pass oracle — worker provider registry, containment flags,
probe/production parity, and the honest scope of the gate.

``hybrid_dispatch.py`` is a protected path, so none of this can be a dispatched
packet: a packet would have to declare the file writable, which is the single
thing the dispatch policy exists to forbid. This is coordinator work and the
fixtures are written before the implementation, as the §3a hand-pass did.

Items:

A. The session overlay carries the provider registry a model alias needs, and
   carries no credential. Established by probe on 2026-08-24: the worker has no
   opencode config or auth store anywhere -- ``/home/agentworker`` does not
   exist -- and ``OPENCODE_CONFIG_CONTENT`` REPLACES rather than merges, so
   without a provider block in the overlay an alias cannot resolve at all. The
   same probe showed the worker infers successfully with no credential file, so
   ``options.apiKey`` in the overlay is the ONLY credential-shaped value that
   ever crosses the boundary. Narrowing it is therefore the whole story.

B. The contained invocation is built in one place and states what it does.
   NOTE what this is NOT: the same probe found the coordinator's
   ``~/.local/share/opencode/auth.json`` and ``~/.ssh`` are already unreadable
   by the worker on filesystem permissions. ``--set-home`` closes no leak. It
   makes the worker's HOME its own rather than one it cannot read, and these
   fixtures assert that and nothing grander.

C. The qualification probe and production dispatch build the same containment
   prefix. They diverged silently when ``--set-home`` was added to one and not
   the other, so every profile probe measured an environment production no
   longer used.

D. The PR body states which commit the gate covered. The gate runs over the
   worker's commit; acceptance happens over the merged PR, and the coordinator
   routinely adds commits after the gate. Saying so is the honest fix.
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


dispatch = _load("hybrid_dispatch_handpass_subject", SCRIPTS / "hybrid_dispatch.py")
probe = _load("probe_opencode_handpass_subject", SCRIPTS / "probe_opencode_profile.py")

SECRET = "sk-live-" + "REALCREDENTIAL" + "0" * 20


def _base_config(api_key: str = SECRET) -> dict:
    """A worker config shaped like the checked-in one, with secrets planted in
    every place a provider block can carry them."""
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": "opencode-go/deepseek-v4-flash",
        "provider": {
            "local3090": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Local RTX 3090 (llama-swap)",
                "options": {
                    "baseURL": "http://127.0.0.1:8020/v1",
                    "apiKey": api_key,
                    "headers": {"Authorization": "Bearer " + SECRET},
                },
                "secretThing": SECRET,
                "models": {"worker-fast": {"name": "3090 Worker Fast", "tools": True}},
            },
        },
        "permission": {"read": "allow"},
        "agent": {"ao-mechanical-bulk": {"model": "opencode-go/deepseek-v4-flash"}},
    }


class ProviderRegistryTests(unittest.TestCase):
    """A — the alias resolves; the credential does not travel."""

    def _registry(self, api_key: str = SECRET) -> dict:
        fn = getattr(dispatch, "worker_provider_registry", None)
        self.assertIsNotNone(
            fn, "hybrid_dispatch has no worker_provider_registry to narrow the copy",
        )
        return fn(_base_config(api_key))

    def test_A1_no_credential_shaped_value_survives_the_copy(self):
        blob = json.dumps(self._registry())
        self.assertNotIn(SECRET, blob, "a credential reached the worker's provider registry")
        self.assertNotIn("secretThing", blob, "an unknown provider key was carried through")
        self.assertNotIn("headers", blob, "provider headers were carried through")

    def test_A2_the_alias_still_resolves(self):
        registry = self._registry()
        self.assertIn("local3090", registry, "the provider disappeared; no alias can resolve")
        local = registry["local3090"]
        self.assertEqual(local["npm"], "@ai-sdk/openai-compatible")
        self.assertEqual(local["name"], "Local RTX 3090 (llama-swap)")
        self.assertIn("worker-fast", local["models"])
        self.assertEqual(local["options"]["baseURL"], "http://127.0.0.1:8020/v1")

    def test_A3_two_configs_differing_only_in_the_key_are_indistinguishable(self):
        # The whole contract in one assertion, and the one a fixture asserting
        # the wholesale copy could never have written.
        self.assertEqual(
            json.dumps(self._registry("sk-live-AAA" + "0" * 24), sort_keys=True),
            json.dumps(self._registry("sk-live-BBB" + "1" * 24), sort_keys=True),
            "the worker's registry still varies with the coordinator's credential",
        )

    def test_A4_an_apiKey_is_present_but_is_never_the_real_one(self):
        # openai-compatible wants some apiKey string. Forcing a placeholder means
        # a provider needing a real credential fails loudly at the worker rather
        # than succeeding with the coordinator's.
        options = self._registry()["local3090"]["options"]
        self.assertIn("apiKey", options, "the provider client will not construct without one")
        self.assertNotIn("REALCREDENTIAL", options["apiKey"])


class ContainedInvocationTests(unittest.TestCase):
    """B — one place builds the sudo prefix, and it says what it does."""

    def _argv(self, worker_user):
        fn = getattr(dispatch, "worker_argv", None)
        self.assertIsNotNone(fn, "hybrid_dispatch has no worker_argv to assert over")
        return fn("/usr/bin/opencode", "ao-mechanical-bulk", "do the thing",
                  Path("/tmp/p.json"), worker_user)

    def test_B1_the_worker_runs_under_its_own_home(self):
        argv = self._argv("agentworker")
        self.assertIn("--set-home", argv, "the worker inherits the coordinator's HOME")
        self.assertLess(
            argv.index("--set-home"), argv.index("/usr/bin/opencode"),
            "--set-home must be a sudo flag, not an opencode argument",
        )

    def test_B2_only_the_overlay_crosses_the_boundary(self):
        argv = self._argv("agentworker")
        preserved = [a for a in argv if a.startswith("--preserve-env")]
        self.assertEqual(
            preserved, ["--preserve-env=OPENCODE_CONFIG_CONTENT"],
            "something other than the session overlay is being carried across sudo",
        )

    def test_B3_no_sudo_at_all_without_a_worker_user(self):
        argv = self._argv(None)
        self.assertNotIn("sudo", argv)
        self.assertNotIn("--set-home", argv)
        self.assertEqual(argv[0], "/usr/bin/opencode")


class ProbeParityTests(unittest.TestCase):
    """C — the probe measures the environment production actually uses."""

    def test_C1_probe_and_dispatch_share_one_containment_prefix(self):
        flags = getattr(dispatch, "CONTAINED_SUDO_FLAGS", None)
        self.assertIsNotNone(
            flags, "there is no single definition of the containment flags to share",
        )
        production = dispatch.worker_argv(
            "/usr/bin/opencode", "a", "m", Path("/tmp/p.json"), "agentworker",
        )
        probe_prefix = probe.contained_sudo_prefix("agentworker")
        self.assertEqual(
            list(probe_prefix), list(production[: len(probe_prefix)]),
            "the qualification probe runs the CLI differently from dispatch, so its "
            "evidence does not describe production",
        )
        self.assertIn("--set-home", probe_prefix)


if __name__ == "__main__":
    unittest.main()
