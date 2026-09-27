# vuoro.cloud principal classification report (read-only)

Slice 0 of the admin-identity design (`docs/plans/2026-09-27-admin-identity-and-vuoro-cli-design.md`, unit 0.1). The report lists:

1. principals whose subject would fail the generation-B CHECK (`^github:[0-9]+$` for humans; there are no test or agent principals yet);
2. workspaces with no authenticable owner (the blocker12 class);
3. what else each violating principal owns, belongs to or holds;
4. likely test data in ordinary workspaces.

It gates **generation B** (unit 2.4): that migration lands only after this report, run against production, lists no pattern violator. It does **not** gate slice 1.

## Where to run it

- **First** against a restore-drill copy, never production: follow vuoro-cloud `docs/runbooks/restore-drill.md` and connect to the drill cluster's control database.
- **Then**, read-only, against production, to produce the list that the reclassify step (`vuoro-cli admin principal reclassify`, slice 2) works from, and again after reclassification.
- Access is the operator's: WireGuard tunnel plus kubeconfig (vuoro-cloud `docs/runbooks/operator-access.md`). The query writes nothing: it runs in a `READ ONLY` transaction that is rolled back.

```sh
# drill copy (namespace per restore-drill.md); production: -n vuoro-data, pod of vuoro-postgres
kubectl -n <namespace> exec -i <postgres-pod> -- \
  psql -X -v ON_ERROR_STOP=1 -d vuoro_control -f - < classify.sql > classification-$(date -u +%F).txt
```

Record the output file's sha256 and the database it ran against in the handoff. The report contains user ids and subjects: keep it in the private vuoro-cloud evidence area, not in this public repo.

## The query (`classify.sql`)

```sql
BEGIN TRANSACTION READ ONLY;

-- 1. Subjects that fail the human pattern. Every users row is human until
--    unit 2.1 adds users.kind; afterwards, filter on kind='human'.
SELECT 'invalid-subject' AS finding, u.id AS user_id, u.external_subject,
       u.display_name, u.created_at,
       (SELECT count(*) FROM web_sessions s WHERE s.user_id = u.id) AS web_sessions,
       (SELECT max(s.last_used_at) FROM web_sessions s WHERE s.user_id = u.id) AS last_session_use,
       (SELECT count(*) FROM oauth_grants g WHERE g.user_id = u.id) AS oauth_grants
FROM users u
WHERE u.external_subject !~ '^github:[0-9]+$'
ORDER BY u.created_at;

-- 2. Workspaces with no authenticable owner: no active owner membership whose
--    user has a valid human subject. Deleted and retained workspaces are listed
--    too (state column), because retire has not existed.
SELECT 'orphaned-workspace' AS finding, w.id AS workspace_id, w.slug, w.state,
       w.desired_state, w.runtime_version, w.tenant_schema_version, w.created_at,
       array_agg(m.user_id || ':' || m.role || ':' || m.state ORDER BY m.role)
         FILTER (WHERE m.id IS NOT NULL) AS memberships
FROM workspaces w
LEFT JOIN memberships m ON m.workspace_id = w.id
GROUP BY w.id
HAVING NOT bool_or(
  m.role = 'owner' AND m.state = 'active'
  AND EXISTS (SELECT 1 FROM users u WHERE u.id = m.user_id
              AND u.external_subject ~ '^github:[0-9]+$')
) IS TRUE
ORDER BY w.created_at;

-- 3. Everything attached to each invalid-subject principal.
SELECT 'violator-attachment' AS finding, u.id AS user_id, 'membership' AS kind,
       m.workspace_id AS ref, m.role || ':' || m.state AS detail
FROM users u JOIN memberships m ON m.user_id = u.id
WHERE u.external_subject !~ '^github:[0-9]+$'
UNION ALL
SELECT 'violator-attachment', u.id, 'oauth-grant', g.workspace_id,
       g.client_id || ' revoked=' || (g.revoked_at IS NOT NULL)
FROM users u JOIN oauth_grants g ON g.user_id = u.id
WHERE u.external_subject !~ '^github:[0-9]+$'
UNION ALL
SELECT 'violator-attachment', u.id, 'api-token', t.workspace_id,
       'revoked=' || (t.revoked_at IS NOT NULL)
FROM users u JOIN api_tokens t ON t.actor = u.external_subject
WHERE u.external_subject !~ '^github:[0-9]+$'
UNION ALL
SELECT 'violator-attachment', u.id, 'principal-subject', ps.kind,
       'epoch=' || ps.epoch
FROM users u JOIN principal_subjects ps ON ps.subject = u.id
WHERE u.external_subject !~ '^github:[0-9]+$'
ORDER BY 2, 3;

-- 4. Likely test data outside test workspaces (heuristic; every hit needs a
--    human decision, none is acted on automatically).
SELECT 'possible-test-data' AS finding, w.id AS workspace_id, w.slug, u.id AS user_id,
       u.external_subject, u.display_name
FROM workspaces w
JOIN memberships m ON m.workspace_id = w.id
JOIN users u ON u.id = m.user_id
WHERE w.slug ~* '(test|canary|drill|blocker|smoke|e2e)'
   OR u.display_name ~* '(test|canary|drill|synthetic|smoke|e2e)'
ORDER BY w.slug;

ROLLBACK;
```

## Reading the result

- **Checked** on 2026-09-27 against a scratch PostgreSQL 18 with vuoro-cloud migrations `001`-`013` at `332faa4` and seeded rows (one valid owner, one non-numeric `github:` owner, one ownerless workspace): each section returned exactly the seeded violators, and the transaction ended in `ROLLBACK`.

- **Expected at vuoro-cloud `332faa4`:** section 1 lists the blocker12 owner (`01M14W25EYSZ…`, a non-numeric `github:` subject) and nothing else; section 2 lists `blocker12-canary` (`01M14W25EYKC…`) and nothing else. Anything else in sections 1-2 is unexplained and blocks generation B until it is classified.
- **Section 3** decides the reclassify disposition: a violator that holds live grants or tokens has them revoked by the reclassify (epoch bump), and every workspace it owns is listed in the retire plan.
- **Section 4** is advisory.
- **Done-check for generation B:** the production run after reclassification returns zero rows in section 1.
