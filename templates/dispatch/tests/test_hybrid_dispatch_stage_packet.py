"""The staged packet must be readable by the worker and invisible to every gate.

V6-K attempt 1 dispatched contained and never reached the model::

    Error: File not found: docs/evidence/packets/V6-K-human-turns.json

``worker_argv`` passed ``--file`` as the packet's path in the *coordinator's*
checkout, which the contained worker identity is denied by design. That is not
incidental: the workspace is a clone at ``starting_commit`` and the packet is
commit 2 of a freeze, so the packet is never in the tree the worker is given.
It has to be copied in.

Every location in the *working* tree is wrong, and that is what the first test
here pins. ``post_gates`` computes touched as ``git diff --name-only`` union
``git ls-files --others --exclude-standard``, so a staged file in the working
tree is a touched path: it would make ``diff-nonempty`` true on every packet
even when the worker wrote nothing, and fail ``diff-scope-respected`` because
it is outside ``writable_patch_paths``. ``dispatch_release.py`` then runs
``git add -A``, so it would land in the commit and the PR as well. Staging
under ``.git`` avoids all of it, because git never enumerates its own
directory.

The second test pins the reason to stage from the in-memory packet at dispatch
time rather than copying during ``prepare``: the bytes the worker reads must
hash to the ``packet_hash`` the receipt attests to, or "the worker implemented
this packet" is a claim about a file nobody checked.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


dispatch = _load_module("hybrid_dispatch_stage_subject", SCRIPTS / "hybrid_dispatch.py")

PACKET = {
    "task_id": "V6-K-stage-probe",
    "attempt": 1,
    "sprint_item": {"ref": "agentops#2254", "claim_id": 33, "claim_actor": "x"},
    "writable_patch_paths": ["only/this.txt"],
}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def _repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    (root / "only").mkdir()
    (root / "only" / "this.txt").write_text("seed\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "seed")
    return root


class StagedPacketIsInvisibleToGit(unittest.TestCase):
    def test_staged_packet_is_not_an_untracked_file(self) -> None:
        """The check that would have rejected staging into the working tree."""
        with tempfile.TemporaryDirectory() as tmp:
            work = _repo(Path(tmp) / "w")

            staged = dispatch.stage_packet(work, PACKET, None)
            self.assertTrue(staged.is_file(), "the packet must actually be written")

            untracked = _git(work, "ls-files", "--others", "--exclude-standard").split()
            diffed = _git(work, "diff", "--name-only", "HEAD").split()

            self.assertEqual(
                [], untracked,
                "a staged packet visible to `git ls-files --others` becomes a touched "
                "path in post_gates, making diff-nonempty true on every packet",
            )
            self.assertEqual([], diffed)

    def test_staged_packet_survives_git_add_all(self) -> None:
        """dispatch_release.py runs `git add -A`; the packet must not be committed."""
        with tempfile.TemporaryDirectory() as tmp:
            work = _repo(Path(tmp) / "w")
            dispatch.stage_packet(work, PACKET, None)
            _git(work, "add", "-A")
            staged_for_commit = _git(work, "diff", "--cached", "--name-only").split()
            self.assertEqual(
                [], staged_for_commit,
                "the staged packet must never reach a commit or a PR",
            )

    def test_staged_path_lives_under_dot_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            self.assertEqual(
                work / ".git" / "agentops" / "packet.json",
                dispatch.staged_packet_path(work),
            )


class StagedBytesMatchTheReceipt(unittest.TestCase):
    def test_staged_bytes_hash_to_the_receipt_packet_hash(self) -> None:
        """The worker must read the packet the receipt attests to, byte for byte."""
        with tempfile.TemporaryDirectory() as tmp:
            work = _repo(Path(tmp) / "w")
            staged = dispatch.stage_packet(work, PACKET, None)

            staged_hash = hashlib.sha256(staged.read_bytes()).hexdigest()
            receipt_hash = hashlib.sha256(
                json.dumps(PACKET, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()

            self.assertEqual(
                receipt_hash, staged_hash,
                "staged bytes must use the same canonicalisation _receipt uses, or "
                "the worker can implement one packet while the receipt attests another",
            )

    def test_staged_packet_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = _repo(Path(tmp) / "w")
            staged = dispatch.stage_packet(work, PACKET, None)
            self.assertEqual(PACKET, json.loads(staged.read_text(encoding="utf-8")))

    def test_restaging_is_idempotent(self) -> None:
        """A retry must not fail because the previous attempt left a file behind."""
        with tempfile.TemporaryDirectory() as tmp:
            work = _repo(Path(tmp) / "w")
            first = dispatch.stage_packet(work, PACKET, None).read_bytes()
            second = dispatch.stage_packet(work, PACKET, None).read_bytes()
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
