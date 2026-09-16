---
name: model-routing-optimizer
description: Use to audit or update model routing across repositories. Treat the canonical model-routing.json as the source of truth and verify provider availability before changing concrete IDs.
---

## Goal

Keep configured model aliases, concrete IDs, fallbacks, and reasoning settings aligned with a reviewed routing policy instead of allowing stale model literals to drift across repos.

## Inputs

- `agentops/templates/dispatch/model-routing.json` and its companion policy documentation.
- The repository list and configuration surfaces to audit.
- Access to provider CLI help or official documentation needed to verify a concrete model or reasoning flag.

## Steps

1. Read `model-routing.json` first. Use its aliases, provider IDs, fallback rules, and `verified` status as the canonical routing policy.
2. Inventory configured model literals and routing aliases across the selected repositories. Include application configuration, examples, deployment manifests, agent guidance, and test fixtures; separate historical documentation from live configuration.
3. Verify provider availability before applying a concrete change:
   - Inspect `claude --help` and `codex --help` for local CLI syntax and supported reasoning controls.
   - Consult current official provider documentation when CLI help cannot establish availability.
   - Leave an unverified model marked `"verified": false`; do not present it as a confirmed default.
4. Build a proposed mapping from every live literal to a routing alias and fallback. Flag any surface that cannot use the preferred model because of provider access, API-key scope, or harness constraints.
5. Apply the smallest scoped updates, preserving repository-local aliases and adding reasoning settings only where the target harness has a verified mechanism.
6. Re-scan the audited repositories for stale literals. Resolve each occurrence, mark it as a documented historical exception, or remove it; do not silently leave a live stale ID behind.
7. Report the evidence: routing policy revision, commands/docs used for verification, changed surfaces, fallbacks selected, reasoning behavior, and the final stale-literal scan.

## Output contract

- Every live configured model maps to a canonical routing alias or an explicit documented exception.
- Concrete provider IDs and reasoning flags are verified or clearly marked unverified in the routing policy.
- Fallback behavior is explicit for environments without access to the preferred frontier model.
- The final audit includes a zero-stale-ref result for the targeted retired IDs, or a list of intentional historical exceptions.

## Do not

- Do not make `model-routing.json` disagree with live configuration.
- Do not hard-code a frontier model into an environment that cannot access it without a tested fallback.
- Do not assume a CLI accepts a reasoning flag based on another harness's syntax.
- Do not rewrite historical records solely to make a grep pass; document intentional historical exceptions instead.
- Do not change provider credentials, secrets, or deployment rollout state as part of a routing audit unless separately authorized.