# Harness implementation profiles

## Current decision

OpenCode is not built from source on every host. A harness is a stable
semantic contract, while each host package channel supplies a separately
qualified implementation profile. This avoids silently treating an upgrade,
a package rebuild, or a locally patched binary as equivalent to a previous
provider run.

The current devbox profile is `opencode-nixpkgs-devbox-1.18.4`. It is a
preflight observation, not a claim that every OpenCode 1.18.4 binary is
equivalent. The older 1.18.5 references record a historical observation; they
are not a global minimum version gate.

## Boundaries

```text
semantic harness adapter -> implementation profile -> host package/config
```

- AgentOps owns the semantic adapter version, profile schema, capability and
  behaviour probes, and the receipt fields.
- GitOps owns the selected package/channel, executable/store fingerprint,
  contained identity, and immutable configuration artifact.
- ActionQ keeps typed adapters for provider-specific argv, stdin, and
  environment translation. It must select a known compatible profile before
  spawning a subprocess; a generic command template is not an authority-safe
  replacement.

## Required profile evidence

Every qualification receipt must bind the semantic adapter, profile id, CLI
version, executable or store fingerprint, channel revision, profile and
overlay hashes, provider/model revision, capability-probe results, and the
contained worker identity. A new fingerprint starts a new qualification
stratum unless the same profile's compatibility probes pass.

## Delivery sequence

1. Add the `harness-profiles` schema and validator under `templates/dispatch/`.
2. Add the devbox 1.18.4 profile plus read-only capability and contained
   behaviour probes.
3. Make GitOps publish the selected immutable profile artifact and record its
   fingerprint.
4. Make ActionQ reject unknown or incompatible `harness_profile` values before
   process launch.
5. Run the disposable no-model-override provider cycle and retain its stamped
   receipt. Only then consider the narrowly scoped daemon trial.

`startDaemon` remains disabled until that sequence has executable evidence.
