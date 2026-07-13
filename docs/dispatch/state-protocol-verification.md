# Stateful protocol verification

Agentops provides two shared dispatch skills for repositories that own lifecycle, queue, lease, projection, retry, recovery, or backend-parity semantics:

- `verify-state-protocols` selects `survey`, `plan`, `verify`, or `repair` mode and Depth 0 through 3 from the requested work and risk surface.
- `reconcile-project-contracts` is a read-only drift check across governing documents, sprintctl items and refs, implementation, tests, verification evidence, and generated projections.

`full` is a meta-dispatch sequence. It does not grant repair authority; the repair step must be independently authorized.

## Manifest routing

Repositories opt in through `*.dispatch.json`:

```json
{
  "routing": {
    "action_classes": {
      "verify": { "enabled": true, "review_required": true },
      "reconcile": { "enabled": true }
    }
  },
  "skills": {
    "selected": ["verify-state-protocols", "reconcile-project-contracts"],
    "overlays": [".agents/overlays/example.state-protocols.md"]
  },
  "risk_surfaces": [
    {
      "id": "claim-lifecycle",
      "paths": ["src/claims/**", "migrations/**"],
      "skills": ["verify-state-protocols", "reconcile-project-contracts"],
      "default_depth": 2,
      "required_on_change": true
    }
  ]
}
```

The overlay closes the generic skill over repository-specific subjects, implementation anchors, verification environments, known limitations, and escalation rules.

## Data-only evidence

Reusable intent belongs in `verification/contexts/*.json` and validates against `templates/dispatch/schemas/test-context.schema.json`. Results belong in CI artifacts by default, or in `verification/results/*.json` when intentionally committed, and validate against `verification-result.schema.json`.

Run the dependency-free minimum validator from the repository root:

```bash
python /projects/dev/agentops/templates/dispatch/scripts/validate_verification_artifacts.py --root .
```

Packets contain data and symbol-level anchors only. They must not embed executable code, secrets, production credentials, or copied production validation logic.
