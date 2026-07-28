# Composed artifact assurance

Status: current release-gate contract.

`composed-artifact/v1` is the release evidence that connects a command the
operator can type to the catalog actually served by a deployed Vuoro image. It
is deliberately stricter than checking package versions independently.

The producer records five views of one domain:

1. every CLI leaf disposition and its selected served operation(s);
2. the served facade's command-to-operation routes;
3. the exact released adapter wheel and its complete operation catalog;
4. the Vuoro composition pin and the catalog produced from that pin; and
5. a catalog response observed from the deployed immutable image.

Run the dependency-free gate with:

```bash
python /projects/dev/agentops/templates/dispatch/scripts/validate_composed_artifact.py \
  path/to/composed-artifact.json
```

The validator rejects route drift, a catalog command without an operation,
local or unavailable commands that acquire a served route, a facade operation
missing from the released adapter, any adapter/composition/deployment catalog
difference, and artifact substitution at the composition boundary. Operation
arrays are compared as sets and carry a canonical SHA-256 over their sorted
compact JSON encoding.

The manifest is evidence, not desired state. Source/release jobs may generate
the first four sections, but the deployment section must come from a fresh
catalog read against the named environment and record the deployed image
digest. Never manufacture deployment evidence from the local composition.

The normative shape is
`templates/dispatch/schemas/composed-artifact.schema.json`. The Python
validator contains the cross-field invariants that JSON Schema cannot express.
