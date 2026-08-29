# Session handoff — declaring what the vault should contain, and building the door devbox can use

**Date:** 2026-08-29 (late) · **Scope:** `appservice`, `cred-broker`, `gitops-nixos` (read only)
**Predecessor:** `session-handoff-2026-08-29-cred-broker-identity-and-integrations.md`

Everything below is landed on `main` at the canonical remote and verified at the
artifact unless explicitly marked outstanding.

| Repo | Commits |
|---|---|
| `appservice` | `9003002b`, `ab72b700`, `6a89956e`, `fc0db16d`, `b3c8b6d8`, `6bdc5c89` |
| `cred-broker` | `afe5e6b` |
| `agentops` | `2e87d33`, `c092204`, `88153c0`, `90eb8d7` |

---

## The through-line

The predecessor's was *a manual step is not a control, and a check that cannot
fail is not a check.* This session built the check the predecessor called for.
Its through-line is what happened next:

> **A record is only worth having if it can be proved wrong — and the first
> thing it proved wrong was the record.**

The OpenBao declaration was written from the repository. On its first live run
it found two things the repository could not have told it, and one of them was
a confident claim I had made in the commit that introduced the file. Every
useful result this session came from comparing a statement against the thing it
described, and three of them contradicted the statement.

---

## 1. External Secrets — renamed, and the "no root" claim corrected

**Landed** (`9003002b`). Policy and role are now `cred-broker-external-secrets`,
inside `operator-admin`'s `sys/policies/acl/cred-broker-*` and
`auth/kubernetes/role/cred-broker*` globs, with the matching `role:` in
`system/external-secrets/pilot/cluster-secret-store.yaml`. The pilot
Kustomization stays `suspend: true`; nothing reconciled.

**The predecessor's claim that this made the ceremony runnable "with no root and
no quorum" was wrong.** Checked against the `operator-admin` policy body rather
than reasoned about: `sys/mounts/<path>` create and any `kv/*` grant are both
absent, so the mount and the seed were still denied. The rename removed two of
four blockers, not four.

Then the live check found `kv/` already mounted (§3), which removed a third. The
seed is the only write left that `operator-admin` cannot make. The script header
and the pilot doc now carry a per-step table of which token each write needs, so
the next reader does not re-derive it.

---

## 2. devbox — the load-bearing question, answered

The predecessor recorded "does devbox hold a kubeconfig?" as unresolved and
load-bearing, framed as a choice between leaving devbox un-enrolled and granting
it cluster-admin.

**It holds none, and the more useful fact is that it could not use one.**
Measured on the host, not read off config:

- `~/.kube` absent, `KUBECONFIG` unset, `kubectl` present with nothing to point
  it at, `sudo` needs a password the `agent` user does not have.
- `modules/system/agent-egress.nix` drops private-space traffic outside
  `allowedLanHosts`, and `hosts/devbox/default.nix` lists exactly three: Forgejo
  `192.168.20.219`, `sprintctl-pg` `192.168.20.220`, `actionq-pg`
  `192.168.20.215`. Probed from devbox **with a positive control alongside**:
  `192.168.20.10:6443` blocked, `192.168.20.219:443` reachable.

So the framing was a false choice. The workstation ceremony cannot be copied
there at all, and Goal D stops being an eventual shape and becomes the only
path.

---

## 3. Goal C — the OpenBao declaration and its checker

**Landed** (`ab72b700`, corrected by `6a89956e` and `fc0db16d`).

`docs/openbao-declared-objects.json` records 21 objects: what creates each, what
uses it, **what renews it**, and whether it should exist now. `renewed_by` is
Goal A's test written into the schema — the checker rejects an entry that omits
it, and `null` is legal only with a note saying why. Four entries carry `null`,
and they are Goal A's remaining debt stated plainly.

`docs/scripts/openbao-check-declared-objects.py` compares it against live
OpenBao and fails in **both** directions: declared present and missing; declared
absent and present, so the file cannot rot when a gap is quietly closed; and a
policy or mount that exists in OpenBao and is named nowhere.

**The design turns on one rule.** `operator-admin` reads are glob-scoped, so a
refused read is *could not check* — a different fact from *absent*. Every probe
resolves to present / absent / denied, denied is never counted as either, and
the classifier is the one already proven in
`openbao-commission-host-enrollment.sh`. Two consequences stop this becoming
another check that cannot fail: a run resolving nothing exits 2, never 0; and
`--declaration-only` prints that no OpenBao state was consulted, so a green CI
badge cannot be read as a green vault.

**Fault-tested, not merely exercised.** 22 Python cases, 17 shell cases, each
asserting a rule *fires* on an injected fault. Verified by mutation: collapsing
403 into 404 fails 3 shell cases; treating denied as absent fails 4 Python
cases. The shell suite drives the in-pod script against a stub `bao`
deliberately — `userpass bayleaf` is the only operator identity, OpenBao's
default lockout trips after a few bad attempts, and there is no second operator
to unlock it, so testing the login-failure path for real could cause the outage
it exists to detect.

All offline halves run as `mise run cred-broker-checks`, a dependency of
`validate`. That also gave `cred-broker-check-audiences.py` its first caller: it
was referenced by no task, workflow or runbook — one step from being an un-run
ceremony itself.

### What the first live run found

Two things, and the second is mine.

- **`kv/` is mounted**, declared absent. Created by nothing recorded in Git, and
  not by the External Secrets ceremony, whose policy and role are both still
  absent. **"Mounted" is not "ready":** the pilot policy grants `kv/data/*` and
  `kv/metadata/*`, which are KV **v2** paths and grant nothing on a v1 mount,
  where the policy still writes cleanly and ESO fails at its first refresh days
  later. The script accepted any pre-existing mount without looking; it now
  confirms `version:2` or refuses, and refuses equally when the version cannot
  be read. All three branches exercised against a stub.
- **Step 7's snapshot role is not unimplemented, and I said it was**, in the
  commit that added the declaration. It exists as policy and role
  `openbao-snapshot`, bound to `openbao/openbao-snapshot-agent` and consumed by
  the chart's snapshot agent — and `openbao-operations.md`'s own snapshot gate
  says the agent is enabled only once its role exists, four sections below the
  line I edited to claim otherwise. The declaration missed it because it was
  built from `docs/scripts`, and this object was made by hand at commissioning.
  **The drift check found it in OpenBao under the name I had guessed wrong.**

That second finding is the argument for the drift half, which was the easiest
part of the design to skip. Comparing intent to live state corrected the
declaration, not the vault.

**Current live state:** `result=pass`, `resolved=17`, `could_not_check=2`
(`userpass-bayleaf` and `role-openbao-snapshot`, both outside `operator-admin`'s
globs and both correctly unknown rather than missing), three declared-absent
notes.

---

## 4. Goal D — designed, steps 1–2 built

Design: `appservice docs/migrations/2026-08-29-cred-broker-host-enrollment-service.md`
(`b3c8b6d8`).

**The design recorded in the predecessor does not work.** TokenReview
authenticates a Kubernetes ServiceAccount token; devbox cannot obtain one (§2),
and that is deliberate hardening rather than an oversight —
`hosts/devbox/default.nix` built it as "the credential-poor headless identity …
no kube/aws/age/tailnet state". A TokenReview-only enroller would have been
usable by the workstation, which already has a working path, and unusable by the
host the goal exists for. Right service, wrong door.

So it carries **two authenticators for one endpoint**: TokenReview for the
workstation, preserving its most important property — renewal mints a fresh SA
token and never depends on the certificate it replaces — and a sops-nix
enrollment secret for devbox, reaching that property by another route.

**Renewing devbox by mTLS with its current certificate was rejected in
writing.** If the only renewal credential is the certificate, an expired
certificate is a stuck state needing a person: the seventeen-day outage rebuilt
somewhere new. The cost of the alternative — a long-lived static credential on
devbox — is stated in the design rather than hidden.

**Two facts checked rather than assumed, both of which cut work.** No Nix egress
change is needed: the internal Gateway serves `git.apps.kotona.app` at
`GATEWAY_INTERNAL_IP` (192.168.20.219), already in devbox's allowlist, so a new
HTTPRoute lands on it — probed from the host. And devbox already receives
Git-committed encrypted secrets through sops-nix (host age key at
`/var/lib/sops-nix/key.txt`), which is how `opencode/agentworker/auth` reaches
the worker today.

**Step 1 — the service** (`cred-broker afe5e6b`,
`src/cred_broker/enrollment.py`, 31 tests). Sign, never issue. Host identity
resolved from the authenticated caller, never the request — a `host_id` in the
body is checked, not used. The TokenReview audience is required and asserted on
the way back, without which any SA token in the cluster enrolls a host. 401 and
403 stay distinct, a denial stops the authenticator chain rather than being
offered the next door, and an unreachable API server raises rather than denying.
OpenBao is not called until the CSR passes, asserted directly. `kubernetes_login`
was extracted from `OpenBaoTransitSigner` rather than copied.

**Step 2 — the devbox PKI role ceremony** (`appservice 6bdc5c89`, 16 cases).
`operator-admin`-runnable; the glob was checked before the name was chosen.
Mirrors the proven `cred-broker-workstation` role instead of inventing
parameters and stops if it cannot read it. Proves the result by signing, then
asks the role to sign a name it must refuse — **a success there is the
failure**. Its failure paths run against a stub, because a ceremony otherwise
executes them never; mutation-verified by disabling the negative control, which
fails 3 cases.

Both new OpenBao objects are declared `absent` with reasons pointing at the
build order, so the checker prints the plan's un-run state on every run. All
three suites gate merges, confirmed on the CI runner (`33273605224`).

---

## 5. Outstanding, in dependency order

### 1. Run the devbox PKI role ceremony (step 2)

```sh
export KUBECONFIG=/projects/dev/appservice/clusters/.kube/config
direnv exec /projects/dev/appservice docs/scripts/openbao-create-devbox-pki-role.sh
```

Needs the operator password. Worth doing before more is built on the assumption
the role can exist. Then flip `pki-role-cred-broker-devbox` to
`expect: present` — the checker fails on a present object declared absent, so it
cannot be quietly forgotten.

### 2. Goal D steps 3–7

Manifests (Deployment, SA, Service, HTTPRoute, NetworkPolicy, shipped inert);
the OpenBao policy and Kubernetes auth role (needs the password); the
**workstation cutover**, which is the step that actually delivers Goal D and is
reversible while both paths exist; devbox enrollment (sops secret, unit and
timer declared in `hosts/devbox/default.nix`, exporter, scrape config, alert);
and finally removing the `kubectl exec` path and the
`cred-broker-enroll-workstation` role. **Only after the last step is "no host
needs OpenBao access" true.**

### 3. The External Secrets seed

One write, `kv/appservice/media/recyclarr`, and the only thing in that ceremony
`operator-admin` cannot do. Either spend root once, or fold the `kv/*` grant
into the root ceremony (§Goal B).

### 4. Exercise the Forgejo sync shim's create path

Unchanged from the predecessor. Its login and create paths remain unexercised;
say so before trusting it for a batch.

### 5. Two things nobody can currently answer

- **Who mounted `kv/`, and with which KV version.** The script now refuses
  rather than guessing, but the history is gone.
- **Whether the snapshot role actually works.** `operator-admin` cannot read it,
  so the honest artifact is a successful nightly upload to
  `s3://…/openbao/raft/`, not any probe.

### Not carried forward

The upstream Forgejo issue is the owner's; dropped from this list at their
instruction.

---

## 6. Facts that will otherwise cost time again

- **`operator-admin` can list policies but not read most of them.**
  `sys/policies/acl` list is granted, so a policy's *existence* is visible while
  its body is not. This is why the drift check works at all, and why
  `policy-operator-admin` resolves `present` where a naive prediction says
  `denied`.
- **`operator-admin` has no `auth/userpass/*` path at all.** Not narrow — absent.
  So it cannot read its own user, cannot create a second operator, and cannot
  narrow itself.
- **devbox's egress is `chain output` only.** Ingress from the cluster is not
  blocked by it, which matters for scraping a devbox exporter later.
- **The internal Gateway is a shared address.** A new HTTPRoute reaches anything
  already allowed to talk to `git.apps.kotona.app`. Convenient here; worth
  remembering before exposing something that should not be that reachable.
- **`core.fileMode=false` in `appservice`** — still true. Every new script is
  invoked through `python3`/`bash` in `mise.toml` rather than relying on the
  exec bit.
- **A concurrent Claude session shares these repos.** One ran `git add -A` while
  an edit of mine sat in the working tree and swept it into an unrelated commit
  (`b6241be`). The content landed correctly; the commit message describing it
  belongs to someone else. Stage explicit paths, not `-A`, when another session
  may be active.

---

## 7. My errors this session

Recorded because the predecessor's §9 is right that a confident wrong cause
costs more than silence.

- **"Step 7 is unimplemented."** Stated in a commit message and in the runbook,
  contradicted by a line in the same file, and found by my own drift check three
  commits later. I built the inventory from `docs/scripts` and then described
  its blind spot as a fact about the world.
- **Two predictions about the live run, half right.** I predicted
  `policy-operator-admin` would come back denied. The refusal was real but landed
  on `userpass-bayleaf`; policies are readable by listing. The substance held —
  the operator cannot read its own authority — and the specific object was wrong.
- **A stale `absent_reason`** naming the `kv/` mount as a blocker survived one
  commit past the run that disproved it, and the checker prints that string on
  every run.

## 8. Credential exposure

**None.** No brokered token, operator password, or key material entered the
transcript. The one place it could have — provoking the ceremony's
login-failure path against the live vault — was avoided deliberately, and a stub
used instead.
