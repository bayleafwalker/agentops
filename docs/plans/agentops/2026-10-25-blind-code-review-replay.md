# Blind historical code-review replay

Status: generic replay tooling and schemas are implemented. A model score is
not a production qualification, route change, or coordinator-tier change.

## Purpose

Use source-pinned code artifacts to measure whether a named reviewer model
recognizes previously adjudicated correctness defects and avoids false
positives on corrected controls. The review prompt and source artifact are
inputs; expected finding identities and severity labels are a separate scoring
input. The reviewer request must never contain the answer key.

The general CLI in `scripts/blind_review_replay.py` prepares digest-bound blind
requests and scores externally collected, independently adjudicated
observations. It has no model-provider client and makes no network call.

## Data and authority boundary

Project-specific historical artifacts, prompt records, expected labels, and
raw model responses stay with the owning project unless that owner explicitly
authorizes their transfer. This public repository carries only generic
tooling, schemas, synthetic tests, and this procedure. Do not copy source
artifacts or project-specific expected labels into the generic test suite.

Before a provider call, obtain explicit authorization for the identified
artifact payload and destination. Broad approval to review or edit code does
not by itself authorize exporting historical source to an external provider.
Use the pinned input set, one named model/runtime per observation, and no
silent fallback. Preserve request/response digests, actual model and runtime
identities, request ID, latency, and provider-reported usage. Missing usage or
latency remains unknown; it is never zero.

Keep cards (`blind-review-card/v1`) free of expected finding IDs, severity
labels, task names, and journal references. Keep the private label set
(`blind-review-label-set/v1`) physically separate from reviewer request files.
The output of `prepare` contains only the card payload, its input digest, and a
request digest. All observations must be bound to the exact card input digest.

## Qualification interpretation

The qualification report is a gate for operator review only. It checks:

- recall of every distinct expected HIGH finding at HIGH severity;
- actual target-model and runtime coverage of every card;
- unsupported and unadjudicated HIGH findings;
- negative-control false positives;
- measured latency and provider-reported token-usage coverage.

Unknown labels remain unscored and appear as an explicit count. A syntactically
valid observation does not prove a finding: confirmed findings need an
independent adjudicator plus file, line, and mechanism support. Unknown or
unsupported HIGH claims fail the gate. A passing report does not select a
model, update `model-routing.json`, or change an active dispatch policy.

## Generic workflow

1. The owning project pins vulnerable source revisions, relevant parent/tip
   relationships, artifact bytes, source paths, and a neutral review prompt.
2. It creates opaque cards and a separate owner-held answer key. The card
   builder binds source and artifact digests in `input_digest`.
3. The owner authorizes the exact transmission scope and destinations before
   any external call. Reviewers receive only prepared request records.
4. The runtime records actual model/provider/runtime identity, request ID,
   response digest, usage, and latency for every call. Incomplete receipts stay
   unknown.
5. A separate adjudicator maps supported findings to source evidence. The
   project supplies private labels only to the qualification command after
   review observations are complete.
6. An operator reviews the report. No command in this workflow changes a model
   route or coordinator tier.

Example local commands:

```sh
python scripts/blind_review_replay.py prepare \
  --cards /owner-private/review-cards.jsonl \
  --output /owner-private/blind-requests.jsonl

python scripts/blind_review_replay.py qualify \
  --cards /owner-private/review-cards.jsonl \
  --labels /owner-private/expected-labels.json \
  --observations /owner-private/adjudicated-observations.jsonl \
  --target-model <exact-model-id> \
  --output /owner-private/qualification-report.json
```

## Mars Founder proposal

The initial Mars Founder proposal is a project-local, source-pinned set of
neutral code cards, with a corrected-code control. The source artifacts and
expected finding labels remain outside this public repository. This proposal
does not by itself establish model recall, provider qualification, or a
coordinator-tier change. The project owner must authorize the precise artifact
transfer and destination before any replay. Synthetic tests cannot substitute
for that authorization or for actual model observations.
