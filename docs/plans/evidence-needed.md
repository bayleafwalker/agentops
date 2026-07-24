• A progressing Claude session becomes a valid observation only when it crosses a real resume boundary.

  At the next safe pause:

  1. Record before pausing:
      - repository, branch/worktree, task/item;
      - timestamp and current session shape: solo, delegated, or multi-agent;
      - what state is intentionally left in Git/Vuoro;
      - whether a handoff bundle or authored note exists.

  2. After a meaningful idle gap, start a fresh Claude session with no prior transcript. Record:
      - resume start/end timestamps;
      - exact resume surface used (handoff, claims, sprint list, Git, notes, etc.);
      - time to the first confident, evidence-backed next action;
      - conflicts/blockers surfaced;
      - other sources consulted;
      - remaining ambiguity or wrong-next-action risk;
      - whether the authored note changed or accelerated the next action (H9).

  3. Preserve the raw evidence:
      - session transcript or command log;
      - bundle/note path;
      - Git commit and worktree state;
      - timestamps.

  For the five-observation gate, we need at least one multi-agent resume and one after a meaningful idle gap; five uninterrupted same-day solo continuations do not qualify. A paired
  manual reconstruction from Git/plans/transcripts without the Vuoro bundle is strongly preferred and is needed for a full assisted-versus-manual comparison.

  The required record shape is documented in the docs/assessments/vuoro-pre-clean-room/README.md:114 and docs/plans/Vuoro-Pre-Clean-Room-Assessment-Plan.md:248.
