# Session handoff — host identity, the Forgejo credential path, and what onboarding should become

**Date:** 2026-08-29 (evening) · **Scope:** `appservice`, `cred-broker`
**Predecessor:** `session-handoff-2026-08-29-landing-forges-and-credentials.md`

Everything below is landed on `main` and verified at the artifact unless
explicitly marked outstanding.

- `appservice` `bc4b9609`
- `cred-broker` `c0c927c`

---

## The through-line

The predecessor's through-line was *state that reports success while doing
nothing.* This session's is narrower and sharper:

> **A manual step is not a control, and a check that cannot fail is not a
> check.**

Every problem here was one of those two. A 24-hour credential renewed by a
human, which meant it was not renewed. A negative control that returned the
expected answer for the wrong reason. Ten forms typed by hand, two of them
wrong. An error message that named the wrong cause with total confidence.

The fixes that stuck replaced a human step with a mechanism, or made a check
capable of failing.

---

## 1. Workstation host identity — the 17-day outage, closed

**The state at the start.** Client certificate expired 2026-08-12, session
expired 2026-08-11, both dead for seventeen days. Nothing noticed. This blocked
the entire Forgejo credential path.

**Landed.** A sign-only enrollment path, and renewal that needs no human.

| Artifact | Role |
|---|---|
| `apps/cred-broker/app/host-enrollment-service-account.yaml` | SA `cred-broker-enroll-workstation`, no RBAC |
| `docs/scripts/openbao-commission-host-enrollment.sh` | One-time ceremony, named-operator auth |
| `docs/scripts/cred-broker-refresh-identity.sh` | Unattended, idempotent renewal |
| `docs/systemd/user/cred-broker-identity.{service,timer}` | The schedule |
| `docs/runbooks/cred-broker-host-identity.md` | The contract |

**Design decisions worth not re-litigating.**

- **`sign`, not `issue`.** The workstation generates its own EC P-256 key and
  OpenBao signs a CSR. The private key never crosses `kubectl exec`, which the
  original hand ceremony did do.
- **Named-operator auth, never root.** The ceremony logs in as userpass
  `bayleaf` with `-no-store`. The initial root token was revoked at
  commissioning and regenerating one from the recovery quorum is *not* part of
  any routine procedure.
- **Per-host names.** Policy `cred-broker-enroll-workstation` grants exactly
  one path. This is accurate labelling, **not** a security boundary: everyone
  who can mint that token also holds a cluster-admin kubeconfig. Do not
  document it as protection.
- **The ceremony proves the grant** by running the real renewal before
  reporting success. Everything else only confirms OpenBao stored what it was
  told, and the one input most likely to be wrong — the PKI role name — cannot
  be read back under `operator-admin` at all.

**The PKI role is `cred-broker-workstation`.** Resolved by probing:
`workstation` returns *denied — existence unknown* (outside the
`cred-broker-*` glob), `cred-broker-workstation` is readable.

**Downtime is handled, and this took two fixes.** The service was ordered
`After=network-online.target`; at the **user** manager level that target has no
unit file, no `Wants`, no `Requires` and never activates, so the ordering was
decorative on the one run most likely to need it. And `Type=oneshot` with
`Restart=no` meant one failed boot attempt waited six hours. Now `OnBootSec=3min`
alongside `Persistent`, plus `Restart=on-failure` / `RestartSec=60` bounded by
`StartLimitBurst=30`.

**An expired certificate is not a stuck state.** Renewal mints a fresh key and
CSR and authenticates with a new ServiceAccount token, so it never needs the
certificate it replaces — demonstrated by minting one after seventeen days of
expiry.

**Verified now:** certificate `notAfter=Aug 30 18:16:56 2026`, session live,
timer enabled and has run successfully.

---

## 2. The Forgejo credential path — all ten integrations live

**Landed.** Eight of nine Forgejo repositories configured for `repo.read` and
`repo.write`; `wizard-valley-world-window` remains the standing negative
control. Sixteen integrations on the forge, verified in the running broker
process (not the ConfigMap) with distinct audiences per repository.

**The canary caught two real errors, which is the whole argument for the
sequencing.** `cred-broker-knowledge-base-repo-write` and
`cred-broker-litany-repo-write` both had the `capability` claim rule left at
the copied `repo.read`. Forgejo names it exactly:

```
claim mismatch: claim "capability" must be "repo.read", but was "repo.write"
```

Nothing broker-side could see this — `audience_for` resolved correctly, the
ConfigMap was right, `cred-broker-check-audiences.py` passed. Both corrected;
all ten now pass read and write.

**A correction to the predecessor.** It instructed confirming that a
vuoro-cloud token is *refused* against `bayleaf/cred-broker`. That test can
neither pass nor fail: `bayleaf/cred-broker` is **public**, as are `litany` and
`worldwindow-kernel`. Every token reads a public repo. Isolation targets must
be private — the canary's default `bayleaf/appservice` is correct. This cost a
detour and a false "repository pinning is broken" alarm before a visibility
check settled it.

---

## 3. Typed provider-not-configured — deployed

An unconfigured repository answered redemption with **HTTP 500
`internal-error`**: the adapter raised a bare `RuntimeError` and the transport
boundary's catch-all swept it up. So the negative control produced a response
indistinguishable from an outage, and could not prove anything.

Now `ProviderNotConfigured` → **409** with
`reason_code: forgejo-authorized-integration-unconfigured`, the same string
`translate()` reports in the authority gap. It inherits from `Exception`, not
`RuntimeError`/`ValueError`, so it cannot be silently recaptured — asserted in
a test. Client gains `BrokerNotConfiguredError`, separate from
`BrokerServiceError` because the two demand opposite responses.

Deployed `0.1.0-eb7b48d` (`sha256:1510b168…`), digest resolved at the registry,
rollout confirmed at the pod's `imageID`. 144 tests pass. Verified live: the
control returns 409, configured repositories still redeem.

---

## 4. Checks that can fail

- **`cred-broker-check-audiences.py`** — orphaned audiences, duplicates across
  repositories *and* capabilities, bindings with no audience, audiences no
  binding reaches, the return of the flat legacy default, and an audience on
  the declared control. Tested against injected faults. Currently passes; it
  was a worklist that became a gate.
- **`cred-broker-forgejo-sync.py`** — batches integration creation through the
  web form, generating claim rules from the same config the broker reads.
  Password via `getpass` only, never stored anywhere by design. Plan mode needs
  no password: desired state from config, actual state from Forgejo's database.
  **Its login and create paths are unexercised** — say so before trusting it
  for a batch.
- **Forgejo's database is the reconciliation gap-closer.** `select name from
  authorized_integration` sees an integration that exists on the forge and is
  named by nothing in config — which the predecessor recorded as unclosable.

---

## 5. Detection — live

`cred-broker-refresh-identity.sh` writes expiry to
`~/.local/state/cred-broker/identity.prom` on **every** run including the no-op
one. A stdlib exporter (`docs/systemd/user/cred-broker-identity-exporter.py`,
port 9111, `/metrics` and `/healthz` only, LAN-restricted) serves it;
`scrapeconfig-cred-broker-identity-workstation.yaml` scrapes it by name;
`CredBrokerHostCertificateExpiring` alerts on `notAfter`.

It watches the **artifact**, not a job's exit status — a renewal that runs and
renews nothing exits 0, and this fires anyway.

**No `absent()` alert on the certificate metric, deliberately.** A workstation
is off overnight; an absent rule would page nightly for a non-event, get
silenced, and then protect nothing. When the host is off nothing needs the
credential.

**Live and verified end to end**, at each link rather than at the config:
exporter `active`, reachable from the Prometheus pod's network namespace,
Prometheus target `health: up`, and both rules loaded and `inactive`. The first
scrape after enablement returned `connection refused` because it predated the
exporter by three minutes — worth knowing, since with a 5-minute interval a
freshly enabled target looks broken for a cycle.

---

## 6. Outstanding, in dependency order

### 1. External Secrets is unrunnable, not merely un-run

`openbao-commission-external-secrets.sh` creates policy `external-secrets` and
role `external-secrets`. `operator-admin` globs
`sys/policies/acl/cred-broker-*` and `auth/kubernetes/role/cred-broker*`.
Neither matches, so **both writes are denied without root** — which is why the
role does not exist. Rename both to `cred-broker-external-secrets` (and the
matching `role:` in `system/external-secrets/pilot/cluster-secret-store.yaml`)
and it becomes runnable with no root and no quorum.

This is the same never-landed shape as the certificate: a committed ceremony
nobody could run and nothing recorded as missing.

### 2. File the upstream Forgejo issue

Draft: `cred-broker/docs/upstream/forgejo-cli-authorized-integration-allowed-domains.md`.
Hostnames genericised, ready to publish. Conclusion:
`forgejo admin user create-authorized-integration` never loads
`[authorized_integration] ALLOWED_DOMAINS`, so its allowlist is empty and every
HTTPS issuer is refused. Proven by running the identical command with
`urn:forgejo:authorized-integrations:actions`, which skips discovery — it
succeeds. **From the CLI, the only issuer that works is the one that skips the
fetch.**

### 3. Exercise the sync shim's create path

Use it when the next repository is added, then verify with the canary.

### 4. devbox is entirely un-enrolled

`policy.hosts` has devbox `active: true`, `development-bounded`, with one
binding. It has no certificate and no renewal. **Unresolved and load-bearing:
does devbox hold a kubeconfig?** The workstation path works only because it can
`kubectl exec` into `openbao-0`, and giving a `development-bounded` host that
access would trade a 24-hour outage for a permanent boundary breach. Also, its
`pki-broker` role naming is unknown — `cred-broker-devbox` is *absent*, bare
`devbox` is *denied, existence unknown*.

Devbox is NixOS: any unit must be declared in
`gitops-nixos/hosts/devbox/default.nix`, not symlinked by hand.

---

## 7. Long goals — onboarding is the real subject

A planner ran on this. Its findings are recorded below; its recommendations
were **deliberately filtered**, because the owner's standing instruction is
*"sanity, not security theatre."* Do not re-adopt the filtered items without a
reason.

### The shape of the defect

> Authority in this system is created by a human running a script once. Nothing
> records that the script should have run, nothing checks that it did, and
> nothing renews what it created.

Three failures, one shape: the workstation certificate, the API session, and
the External Secrets pilot. Only one Kubernetes auth role has ever existed in
OpenBao (`cred-broker`) plus the one created today.

### Goal A — every credential renews by default, or is loudly absent

The certificate is done. The remaining instances are devbox and any future
host or workload. The test for a new credential: *what renews this, and what
fires if that stops?* An answer of "a person" is a defect.

### Goal B — operator identity should stop being one password

**`operator-admin` is root-equivalent in practice.** It holds
`sys/policies/acl/cred-broker-*` and `auth/kubernetes/role/cred-broker*`
create/update, and OpenBao does not constrain a policy body by the writer's own
capabilities — so it can write a policy granting `*`, bind a role to any
ServiceAccount, and mint a root-equivalent token. It also holds **no** grant on
its own policy, so it cannot narrow itself.

It also has **no `auth/userpass/*` path at all**, so it cannot create a second
operator. For most of this session the system's effective root was one password
whose availability was in doubt.

Authentik runs in this cluster and `bao login -method=oidc` does not require an
external OpenBao route (the CLI listens on `localhost:8250`; OpenBao is reached
by port-forward). But enabling it needs `sys/auth` write — not grantable to
`operator-admin`.

**So this is the designated content of any future root ceremony**, and the
argument for using the quorum *once*: `auth/oidc` against Authentik, a second
`operator-admin` userpass, `pki-broker` auto-tidy, and narrowing
`operator-admin` so it is no longer root-equivalent. Do not spend the quorum on
less than all four. Not recommended now; recorded so the cost of the current
constraint is visible.

### Goal C — make an un-run ceremony visible

External Secrets was committed and never run, and nothing said so. The cheapest
mechanism that would surface it is the one already built for audiences: a check
that compares declared intent against live state and can fail. Extending
`cred-broker-check-audiences.py` toward OpenBao objects is the natural path.

### Goal D — a host should not need `kubectl exec` into the vault

The current design works because the workstation is effectively cluster-admin.
That does not generalise to devbox and should not. The eventual shape is a
separate `cred-broker-enroll` workload holding the sign-only policy and
exposing a CSR endpoint authenticated by TokenReview — then no host needs
OpenBao access, the API deployment keeps Transit-only, the enroller keeps
sign-only, and neither holds both. This is the literal implementation of
`openbao-operations.md`'s own sentence about separated responsibilities.

### Explicitly declined — do not re-adopt without a reason

An enrollment registry file, RBAC scanning for token-mint grants, a new
threat-model invariant, Loki rules on the OpenBao audit log, custom token
audiences, issuing-CA fingerprint pinning, splitting the timer into two units,
a lazy-renewal wrapper, and dropping the certificate TTL to 12h. None would
have caught the outage; each is another thing to maintain and to go quiet on
its own.

---

## 8. Facts that will otherwise cost time again

- **`core.fileMode=false` in `appservice`.** A local `chmod` is invisible to
  git, so committed scripts land non-executable. Helper scripts are now invoked
  through `bash` rather than relying on the bit. This broke the first real
  enrollment *after* the certificate had already been signed.
- **Forgejo echoes the entire bearer token in 401 bodies.** Printing
  `.message` while holding a brokered credential puts a live token in a
  transcript. The canary avoids this by asserting on status codes and keeping
  bodies in tmpfs — which is also why it fails silently.
- **Public repositories break negative controls.** `cred-broker`, `litany` and
  `worldwindow-kernel` are public. Any isolation test must target a private
  repository.
- **`operator-admin` cannot list `pki-broker/roles`.** A denied read is *could
  not check*, not *absent*. The ceremony reports the two differently.
- **The broker's own policy is `cred-broker-sign` — Transit only.** It has no
  PKI authority; `openbao-operations.md`'s example policy shape showing
  `pki-broker/issue/workstation` under the broker does not match production,
  correctly so.
- **Config changes need `cred-broker/config-revision` bumped** in
  `deployment.yaml` or the pod does not roll and the change stays inert.

---

## 9. A diagnosis stated without evidence is worse than none

The enrollment ceremony failed with `Permission denied` on a helper script and
announced that *"the most likely cause by far is a wrong PKI role name."* The
role name was correct, the certificate was already installed, and the actual
cause was a missing execute bit. The owner was sent to re-run a ceremony that
had succeeded.

The message now points at the underlying error and says explicitly that it does
not know the cause. Worth generalising: a confident wrong cause costs more than
silence, because it displaces the real error the reader would otherwise have
read.

---

## 10. Credential exposure — mine

Two brokered JWTs reached the session transcript while diagnosing the two wrong
claim rules, because a debug command printed Forgejo's 401 `.message` and
Forgejo echoes the full bearer token there. Both were repository-scoped
five-minute leases, both were *refused* by the forge (which is why they were in
an error at all), and both are long expired. No rotation needed.

Same cause as the predecessor's two exposures: dumping a broad response when
one field was wanted. The rule that would have prevented all three is to select
the field, never print the envelope.
