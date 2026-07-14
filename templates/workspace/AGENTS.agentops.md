## Agentops repository contracts

`/projects/dev/agentops` is the canonical source for shared dispatch skills,
manifest schemas, state-protocol context/result schemas, and the dependency-free
repository gate.

- Repositories opt in with one root `*.dispatch.json` and repository-specific overlays under `.agents/overlays/`.
- Reusable verification intent belongs in data-only `verification/contexts/*.json`; executable tests and production logic remain in the owning repository.
- Inspect declared `risk_surfaces` before changing queue, claim, lease, retry, recovery, projection, publication, reconciliation, or backend-parity paths.
- Run `python /projects/dev/agentops/templates/dispatch/scripts/validate_verification_artifacts.py --root .` from an opted-in repository.
- `full` is a sequence, not blanket repair authority. Repair and production mutation remain separately authorized.
