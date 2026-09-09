---
name: cred-broker
description: Use when a task needs Forgejo or GitHub API access, a git push to git.apps.kotona.app over HTTPS, or a protected-branch merge. Mint a short-lived brokered credential instead of looking for a token file. Also covers setting the broker up when it is missing and diagnosing it when it fails.
---

## Goal

Obtain a scoped, short-lived credential from cred-broker for exactly one
repository and one capability, instead of reading a long-lived token from disk.

On the workstation this is not a preference. There is no Forgejo API token on
that machine — `~/.local/share/forgejo-cli/keys.json`,
`~/.config/forgejo/workstation-scope-token` and `~/.config/forgejo/admin-token`
are all absent — so for anything past git-over-SSH the broker is the only path.
Confirm with the session-start hook's probed inventory rather than with this
sentence.

## Inputs

- `KUBECONFIG=/projects/dev/appservice/clusters/.kube/config` (a bare `kubectl`
  hits a local kind cluster).
- `credctl` on PATH. It is not packaged in the host flake yet; it lives at
  `/projects/dev/cred-broker/.venv/bin/credctl`. Prepend that rather than
  concluding the broker is unavailable.
- A live host identity in `~/.config/cred-broker/workstation/`.

## Steps

1. Check what you actually have before assuming. The session-start hook prints
   this; otherwise:
   ```bash
   ls ~/.config/cred-broker/workstation/          # client.crt, client.key, session.json, server-ca.crt
   openssl x509 -in ~/.config/cred-broker/workstation/client.crt -noout -enddate
   systemctl --user is-enabled cred-broker-identity.timer
   ```
   Certificates last 24 hours. If it is expired or the timer is absent, go to
   **Setting it up**.

2. Mint for one command. The child gets `FJ_TOKEN`; nothing is written to disk:
   ```bash
   credctl exec repo.write --repository forgejo:bayleaf/<repo> -- <command>
   ```
   To evaluate policy without minting anything, `credctl explain` takes the same
   arguments.

3. For git over HTTPS, **both** settings are required:
   ```bash
   git -c credential.useHttpPath=true \
       -c 'credential.helper=!credctl git-credential --capability repo.write' \
       push https://git.apps.kotona.app/bayleaf/<repo>.git <ref>
   ```

4. After creating or editing a Forgejo Authorized Integration, prove it against
   the forge:
   ```bash
   CRED_BROKER_CANARY_REPOSITORY=bayleaf/<repo> \
     /projects/dev/appservice/docs/scripts/cred-broker-forgejo-canary.sh <capability>
   ```
   Nothing broker-side can detect a mistyped claim rule: `audience_for()`
   resolves correctly either way, and the failure appears only as a 401 at the
   forge. Two of ten integrations created on 2026-08-29 shipped broken exactly
   that way while every broker-side check stayed green.

## Capabilities

`repo.read`, `repo.write`, `pr.merge` on forgejo repositories; `pr.manage` also
on github. A capability no binding grants for that repository is denied — that
is policy working, not an outage. Policy lives in
`appservice/clusters/main/kubernetes/apps/cred-broker/app/config.yaml`; a new
grant needs a binding, an `allow_authority_gap` flag for forgejo, and an
Authorized Integration audience.

## Troubleshooting

Each of these reads as something other than what it is.

| Symptom | It is not | It is |
|---|---|---|
| `could not read Username for 'https://git.apps.kotona.app'` | a missing credential | `credential.useHttpPath` unset, so the helper received no repository and returned nothing |
| `broker client unavailable: broker server CA bundle is not readable` | a broken identity | `server-ca.crt` missing; run the renewal, which installs it on every run |
| `required command not found: openssl` | a broker problem | a host package gap; `gitops-nixos` `modules/system/devtools.nix` |
| `identity directory must be a non-symlink directory` | corruption | the directory does not exist; `mkdir -p` then `chmod 700` (the renewal requires 0700 even though commissioning does not check) |
| 401 from Forgejo on a freshly minted token | broker misconfiguration | the integration's claim rules do not match the capability; run the canary |
| `not allowed to merge [reason: Not all required status checks successful]` | a credential failure | branch protection. The credential worked — a credential failure is a 401 |

**Never print a Forgejo error body while holding a brokered token.** Forgejo
echoes the whole bearer token back in its 401 message. Assert on
`%{http_code}`; read `.message` only after confirming it carries no token.

## Setting it up

`appservice/docs/runbooks/cred-broker-host-identity.md`. Renewal is
`docs/scripts/cred-broker-refresh-identity.sh`, safe at any frequency and
idempotent; the one-time ceremony is
`docs/scripts/openbao-commission-host-enrollment.sh`, run it with no argument
first so it probes for the PKI role name rather than guessing.

Custody of the private key is the operator's. It is generated on the host and
never transmitted — OpenBao signs a CSR, it does not issue a key. **Do not
generate, read, copy or move it.** If the ceremony is needed, hand the operator
the commands; do not run them on their behalf.

If an agent finds the broker missing or broken, the correct move is to say so
and offer the runbook — not to fall back to hunting for a static token. The
static-token path in `vuoro-cloud/scripts/ff-merge-pr.sh` is deliberately loud
and gated behind `FF_MERGE_ALLOW_STATIC_TOKEN`, and the file it wants does not
exist on the workstation.
