# Published image evaluator qualification

The exact digest-pulled vuoro-service 0.1.90 image ran its actual application factory over verified local HTTPS with separate PostgreSQL work/audit migration and runtime roles. All 248 checks passed. The packet manifest binds the exact executing source and synthetic receipts; cleanup completed.

The supported hosted binding and synthetic Ed25519 assertions exercised the image gateway verifier through owner run binding and `work.evidence.evaluate-v1`. Nonempty client/grant bindings succeeded; changed principal/client/grant, workspace, missing authorities, forged signature, request correlation, replay, repo scope, extra arguments and idempotency keys were refused. Every evaluator and auth refusal preserved all eight complete owner table snapshots. Authored trust claims remained assertions; execution facts and coverage stayed unsupported. Expiry, missing inputs, invalid legacy validity, exact tail and stale frozen Release histories passed.

This qualifies the assertion verifier and owner evaluator; OAuth issuance, revocation and MCP edge forwarding remain unqualified. It proves neither database crash durability (fixture fsync is off) nor full S4. Host installed-wheel verification and same-digest image installed-member/provenance qualification are separate checks; the latter is retained in `published-image-provenance/`, including attestation verification and exact manifest identity. No production credentials, JWTs, keys, DSNs, environment files or data are included.

Reproduce with `S4_PROOF_PYTHON=<verified-wheel-environment>/bin/python scripts/s4-proof/s4-image-evaluator-pg.sh`; the artifact pins bind required local verified wheels and OCI digest. Historical causal proof pins remain unchanged.

The first attempt failed because the fixture incorrectly added OAuth fields to the closed static identity registry. The fixture was corrected to supported signed gateway assertions; product configuration contracts were unchanged.
