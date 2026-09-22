# E1 durable edge capability — design record

These four documents are the written design for E1, the read-only MCP capability
served from vuoro.cloud. They were produced on 2026-09-22 and lived only in
`/projects/dev/_artifacts/vuoro/`, which is not a git repository, so the entire
direction survived on one disk with no history. They are copied here verbatim so
that a successor can read the reasoning rather than re-derive it, and so that
`git log` records when each claim was made.

Read them in this order:

1. `e1-placement-decision-brief-2026-09-22.md` — why the capability is served
   from vuoro.cloud (Estate B) rather than the homelab. Operator-closed.
2. `e1-design-and-security-note-2026-09-22.md` — the disclosure boundary, the
   tool classification (read / coordinate / record / propose), and the
   prompt-injection defences that were measured against the real corpus and
   rejected.
3. `e1-implementation-design-synthesis-2026-09-22.md` — the fullest account of
   the implementation, written under the static-bearer and one-month-trial
   framing that the operator removed on 2026-09-22. Large parts are therefore
   SUPERSEDED. It is kept because its security reasoning and its enumeration of
   failure modes outlived the framing that produced it; read it for those, not
   for its architecture.
4. `e1-stronger-baseline-design-2026-09-22.md` — the adversarial rebuild of the
   baseline, written against the live trees after the framing change. This is
   the most current design, and where it contradicts (3), it wins.

None of these is a decision record. Operator decisions live in sprintctl; the
handoff files under `docs/dispatch/handoffs/` carry the constraint list and the
rejected-alternatives list that bind a successor.
