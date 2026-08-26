"""Every committed packet that has a receipt must be the packet that produced it.

A receipt records ``inputs.packet_hash``, and its ``execution_id`` embeds the
first 16 characters of that hash. So the link between a frozen packet and the run
it authorised is already written down -- but nothing checked it, and on
2026-08-26 four of twenty packets did not hold:

* ``V59-2-schema-check-composition`` was reconstructed by hand during the
  lost-packet recovery in #103 and lost one ``protected_paths`` entry on the way.
  **The recovery introduced the drift**, because a restored packet was accepted
  on the strength of its filename.
* ``V6-I-schema-formats`` was committed from the pre-fix copy -- the version
  carrying its own writable path in ``protected_paths``, which would fail
  ``validate`` today. The version that ran had the trap fixed.
* ``V6-G-defect-seeds`` was enriched after its run with the seeds it had just
  built.
* ``V6-E-churn-metrics`` was retried under L-4, which appends gate output to
  ``purpose``; the mutated packet lived only in the coordinator workspace.

Three were recovered from the object store and re-linked. The fourth is declared
lost below. This test exists so the fifth never happens quietly: a corpus whose
packets do not hash to their receipts cannot be audited cold, which is the whole
claim ``agentops#2017`` rests on.

Rule 11: this file reads committed JSON only. It runs no git and no subprocess.
"""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
PACKETS = ROOT / "docs/evidence/packets"
RECEIPTS = ROOT / "docs/evidence/receipts"

#: Packets whose dispatched form is genuinely gone, with the reason. A name here
#: is a declaration that the artifact cannot be recovered -- not a way to silence
#: a link that merely looks inconvenient. Adding one is a deliberate act and the
#: reason is part of the record.
DECLARED_LOST = {
    "V6-E-churn-metrics": (
        "attempt 2 was dispatched by the L-4 retry path, which appends the gate "
        "output to purpose. That mutated packet was never committed and is not "
        "in the object store. Searched 2026-08-26."
    ),
}


def _packet_hash(packet: dict) -> str:
    """The hash exactly as ``_receipt`` computes it (hybrid_dispatch.py:2156)."""
    payload = json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _pairs():
    for packet_path in sorted(PACKETS.glob("*.json")):
        task_id = packet_path.stem
        receipt_path = RECEIPTS / task_id / "receipt.json"
        if receipt_path.exists():
            yield task_id, packet_path, receipt_path


class ReceiptsHavePacketsTests(unittest.TestCase):
    """The other direction, which is the failure this file was written for.

    ``_pairs`` walks packets and looks up receipts, so a receipt whose packet
    went missing -- the freeze-branch trap, verbatim -- simply stops generating
    a pair and every hash assertion above passes. Deleting
    ``V6-B-build-scorecard-iterable.json`` left this file green until this class
    existed. The corpus document and the handover both state "every receipt now
    has its packet" as a standing guarantee; this is what makes that a claim
    rather than a hope.
    """

    def test_every_receipt_has_a_committed_packet(self):
        orphans = []
        for receipt_path in sorted(RECEIPTS.glob("*/receipt.json")):
            task_id = receipt_path.parent.name
            if not (PACKETS / f"{task_id}.json").exists():
                orphans.append(task_id)
        self.assertEqual(
            orphans, [],
            "these receipts have no packet -- the freeze-branch trap. Recover "
            "them from the object store (git cat-file --batch-all-objects) and "
            "hash-check the result before committing it.",
        )

    def test_at_least_one_receipt_is_checked(self):
        self.assertGreater(len(list(RECEIPTS.glob("*/receipt.json"))), 0)


class IdentityMatchesFilenameTests(unittest.TestCase):
    """Pairing is by filename stem, so the stem must not be the only evidence.

    "A restored packet was accepted on the strength of its filename" is the
    defect this whole file narrates. A packet restored under the wrong name
    pairs with nothing and would be skipped in silence rather than failing.
    """

    def test_each_packet_declares_its_own_filename_as_task_id(self):
        for packet_path in sorted(PACKETS.glob("*.json")):
            with self.subTest(packet=packet_path.name):
                packet = json.loads(packet_path.read_text())
                self.assertEqual(packet.get("task_id"), packet_path.stem)

    def test_each_receipt_declares_its_own_directory_as_task_id(self):
        for receipt_path in sorted(RECEIPTS.glob("*/receipt.json")):
            with self.subTest(receipt=receipt_path.parent.name):
                receipt = json.loads(receipt_path.read_text())
                self.assertEqual(receipt.get("task_id"), receipt_path.parent.name)


class PacketReceiptLinkageTests(unittest.TestCase):

    def test_at_least_one_pair_is_checked(self):
        # A glob that silently matches nothing would make every other assertion
        # in this file vacuous -- the same failure shape the V6-J oracle exists
        # to catch on the frontier half.
        self.assertGreater(len(list(_pairs())), 0)

    def test_every_receipt_hashes_to_its_committed_packet(self):
        for task_id, packet_path, receipt_path in _pairs():
            with self.subTest(task=task_id):
                if task_id in DECLARED_LOST:
                    # Skipped checks must not read like passed ones. This repo
                    # has diagnosed that shape twice -- read_trace's
                    # "skipped:untraced" and worker_writability's
                    # "skipped:no-worker-user" are both reserved statuses for
                    # exactly this -- so the exemption is announced, not elided.
                    self.skipTest(f"declared lost: {DECLARED_LOST[task_id]}")
                packet = json.loads(packet_path.read_text())
                receipt = json.loads(receipt_path.read_text())
                self.assertEqual(
                    receipt["inputs"]["packet_hash"],
                    _packet_hash(packet),
                    f"{task_id}: the committed packet is not the one that produced "
                    "this receipt. Recover the dispatched packet from the object "
                    "store (git cat-file --batch-all-objects) rather than editing "
                    "either side to agree.",
                )

    def test_execution_id_embeds_the_same_hash(self):
        # execution_id is what a reader actually quotes, so it must agree with
        # inputs.packet_hash rather than being a second, drifting copy.
        for task_id, _, receipt_path in _pairs():
            with self.subTest(task=task_id):
                receipt = json.loads(receipt_path.read_text())
                digest = receipt["inputs"]["packet_hash"].split(":", 1)[1]
                self.assertEqual(
                    receipt["execution_id"],
                    f"{receipt['task_id']}:{digest[:16]}:attempt-{receipt['attempt']}",
                )

    def test_declared_lost_names_only_real_unlinked_packets(self):
        # A stale exemption is worse than none: it would hide a regression on a
        # packet that has since been recovered.
        for task_id, reason in DECLARED_LOST.items():
            with self.subTest(task=task_id):
                packet_path = PACKETS / f"{task_id}.json"
                receipt_path = RECEIPTS / task_id / "receipt.json"
                self.assertTrue(packet_path.exists(), f"{task_id} has no packet")
                self.assertTrue(receipt_path.exists(), f"{task_id} has no receipt")
                self.assertTrue(reason.strip(), f"{task_id} must carry a reason")
                packet = json.loads(packet_path.read_text())
                receipt = json.loads(receipt_path.read_text())
                self.assertNotEqual(
                    receipt["inputs"]["packet_hash"],
                    _packet_hash(packet),
                    f"{task_id} is exempted but now links; remove it from "
                    "DECLARED_LOST rather than leaving the exemption standing.",
                )


if __name__ == "__main__":
    unittest.main()
