# Lane 3 — Windmill Execution Probe

The locked Windmill image ran with a disposable PostgreSQL instance and one
unprivileged worker on an isolated Docker network. The server was bound only to
`127.0.0.1:18081`. No Docker socket, repository mount, production service,
or production credential was supplied to the worker.

## Result

The `CR-02` fixture reference was submitted as a pure receipt job twice with
the same `BATCH-02` idempotency key. Both completed:

```json
{"job_1":{"corpus_task":"CR-02","execution_receipt":"worker-completed","idempotency_key":"BATCH-02"},"job_2":{"corpus_task":"CR-02","execution_receipt":"worker-completed","idempotency_key":"BATCH-02"},"same_idempotency_key_accepted_twice":true,"worker_ready":true}
```

This is not a claim that the duplicate produced a domain-side duplicate—the
test function was intentionally pure. It is decisive evidence that Windmill
does not make the frozen R5 idempotency guarantee by itself. A claim-gated
completion callback or equivalent external idempotency authority must remain.

## Isolation result

The worker reported that its unshare test was not permitted and that unshare
isolation would not be available; its diagnostic says jobs configured for that
mode run without isolation. The probe did not enable the upstream privileged
worker configuration, because that would materially broaden host authority.
Therefore this configuration fails the R5 safety-envelope and R6 trust-boundary
gate, even though the worker can run jobs.

The image reported `Windmill Community Edition v1.767.0-15-gf02df7fc45`.
