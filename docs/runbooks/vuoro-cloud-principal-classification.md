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
# drill copy (namespace per restore-drill.md); production: -n vuoro-data, cluster vuoro-postgres
pod=$(kubectl -n <namespace> get pod -l cnpg.io/cluster=<cluster>,cnpg.io/instanceRole=primary -o name)
kubectl -n <namespace> exec -i "$pod" -c postgres -- \
  psql -X -v ON_ERROR_STOP=1 -d vuoro_control -f - < classify.sql > classification-$(date -u +%F).txt
```

Record the output file's sha256 and the database it ran against in the handoff. The report contains user ids and subjects: keep it in the private vuoro-cloud evidence area, not in this public repo. No row is written to `audit_events` for the run (decided 2026-09-28, addendum §8.1 Nit 6): a hand-written superuser `INSERT` would be self-attested and is a kubectl-plus-SQL write; the recorded sha256, database and time are the evidence.

## The query (`classify.sql`)

```sql
BEGIN TRANSACTION READ ONLY;

-- 1. Subjects that fail the human pattern. Every users row is human until
--    unit 2.1 adds users.kind; afterwards, filter on kind='human'.
SELECT 'invalid-subject' AS finding, u.id AS user_id, u.external_subject,
       u.display_name, u.created_at,
       (SELECT count(*) FROM web_sessions s WHERE s.user_id = u.id
          AND s.revoked_at IS NULL AND s.expires_at > now()) AS live_web_sessions,
       (SELECT max(s.last_used_at) FROM web_sessions s WHERE s.user_id = u.id) AS last_session_use,
       (SELECT count(*) FROM oauth_grants g WHERE g.user_id = u.id
          AND g.revoked_at IS NULL AND g.expires_at > now()
          AND g.last_used_at > now() - interval '7 days') AS live_oauth_grants,
       (SELECT count(*) FROM oauth_grants g WHERE g.user_id = u.id) AS all_oauth_grants,
       EXISTS (SELECT 1 FROM principal_subjects ps WHERE ps.subject = u.id) AS has_epoch_row
FROM users u
WHERE u.external_subject !~ '^github:[0-9]+$'
ORDER BY u.created_at;

-- 2. Workspaces with no authenticable owner: no active owner membership whose
--    user has a valid human subject and a principal_subjects row (without one,
--    authentication fails closed, principal.py). Deleted and retained workspaces are listed
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
              AND u.external_subject ~ '^github:[0-9]+$'
              AND EXISTS (SELECT 1 FROM principal_subjects ps WHERE ps.subject = u.id))
) IS TRUE
ORDER BY w.created_at;

-- 3. Everything attached to each invalid-subject principal.
SELECT 'violator-attachment' AS finding, u.id AS user_id, 'membership' AS kind,
       m.workspace_id AS ref, m.role || ':' || m.state AS detail
FROM users u JOIN memberships m ON m.user_id = u.id
WHERE u.external_subject !~ '^github:[0-9]+$'
UNION ALL
SELECT 'violator-attachment', u.id, 'oauth-grant', g.workspace_id,
       g.client_id || ' live=' || (g.revoked_at IS NULL AND g.expires_at > now()
         AND g.last_used_at > now() - interval '7 days')
FROM users u JOIN oauth_grants g ON g.user_id = u.id
WHERE u.external_subject !~ '^github:[0-9]+$'
UNION ALL
SELECT 'violator-attachment', u.id, 'api-token', t.workspace_id,
       'revoked=' || (t.revoked_at IS NOT NULL)
         || ' expired=' || coalesce(t.expires_at <= now(), false)
FROM users u JOIN api_tokens t ON t.actor = u.external_subject
WHERE u.external_subject !~ '^github:[0-9]+$'
UNION ALL
SELECT 'violator-attachment', u.id, 'connector', c.workspace_id,
       c.name || ' state=' || c.state
FROM users u JOIN connectors c ON c.enrolled_by = u.id
WHERE u.external_subject !~ '^github:[0-9]+$'
UNION ALL
SELECT 'violator-attachment', u.id, 'connector-enrollment', ce.workspace_id,
       'exchanged=' || (ce.exchanged_at IS NOT NULL)
FROM users u JOIN connector_enrollments ce ON ce.created_by = u.id
WHERE u.external_subject !~ '^github:[0-9]+$'
UNION ALL
SELECT 'violator-attachment', u.id, 'membership-invitation', mi.workspace_id,
       'invited_by role=' || mi.role || ' live=' || (mi.revoked_at IS NULL
         AND mi.accepted_at IS NULL AND mi.expires_at > now())
FROM users u JOIN membership_invitations mi ON mi.invited_by = u.id
WHERE u.external_subject !~ '^github:[0-9]+$'
UNION ALL
SELECT 'violator-attachment', u.id, 'membership-invitation-accepted', mi.workspace_id,
       'accepted_by'
FROM users u JOIN membership_invitations mi ON mi.accepted_by = u.id
WHERE u.external_subject !~ '^github:[0-9]+$'
UNION ALL
SELECT 'violator-attachment', u.id, 'admission-invitation', i.id, 'redeemed_by'
FROM users u JOIN invitations i ON i.redeemed_by = u.id
WHERE u.external_subject !~ '^github:[0-9]+$'
UNION ALL
SELECT 'violator-attachment', u.id, 'bootstrap-session', bs.workspace_id,
       'approved=' || (bs.approved_at IS NOT NULL)
         || ' exchanged=' || (bs.exchanged_at IS NOT NULL)
FROM users u JOIN bootstrap_sessions bs ON bs.actor = u.external_subject
WHERE u.external_subject !~ '^github:[0-9]+$'
UNION ALL
SELECT 'violator-attachment', u.id, 'principal-subject', ps.actor,
       'kind=' || ps.kind || ' epoch=' || ps.epoch
FROM users u JOIN principal_subjects ps ON ps.subject = u.id
WHERE u.external_subject !~ '^github:[0-9]+$'
ORDER BY 2, 3, 4, 5;

-- 3b. Connectors with no recorded enroller (enrolled before migration 011) in
--     workspaces a violator belongs to: attribution unknown, list for review.
--     Over-inclusive on purpose: revoked connectors are listed too.
SELECT 'unattributed-connector' AS finding, c.workspace_id, c.id AS connector_id,
       c.name, c.state
FROM connectors c
WHERE c.enrolled_by IS NULL
  AND EXISTS (SELECT 1 FROM memberships m JOIN users u ON u.id = m.user_id
              WHERE m.workspace_id = c.workspace_id
                AND u.external_subject !~ '^github:[0-9]+$')
ORDER BY c.workspace_id;

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

- **Checked** (this version) on 2026-09-28 against a scratch PostgreSQL 18.4 with vuoro-cloud migrations `001`-`014` at `2c58ce9` and seeded rows (valid owner, non-numeric `github:` owner with a connector, sessions, live, revoked, absolute-expired and idle-expired grants, live, revoked and accepted invitations and a bootstrap session, an owner without a `principal_subjects` row, an unattributed connector): each section returned the seeded rows, section 3 told the live grant and invitation apart from the dead ones and listed the bootstrap session, and the transaction ended in `ROLLBACK`. `live_oauth_grants` and the section 3 `live=` flag apply the refresh idle limit of 7 days (`oauth_server.py:38`, checked at `control.py:1186-1191`).

- **Expected at vuoro-cloud `2c58ce9`:** section 1 lists the blocker12 owner (`01M14W25EYSZ…`, a non-numeric `github:` subject) and nothing else; section 2 lists `blocker12-canary` (`01M14W25EYKC…`) and nothing else. Anything else in sections 1-2 is unexplained and blocks generation B until it is classified.
- **Section 3** decides the reclassify disposition: every live credential listed here must be revoked explicitly: an epoch bump alone does not revoke refresh grants, PATs or web sessions at vuoro-cloud `2c58ce9` (refresh and PAT paths stamp the epoch without comparing it; sessions are keyed by user id), and connectors authenticate as themselves. The admin reclassify and disable operations (unit 2.2) revoke them in the same transaction; until then, list each in the handoff. Every workspace the violator owns goes into the retire plan; section 3b's connectors need a human decision.
- **Section 4** is advisory.
- **Done-check for generation B:** the production run after reclassification returns zero rows in section 1.
