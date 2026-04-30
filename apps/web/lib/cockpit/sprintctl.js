import pg from "pg";
import { decodeCursor, encodeCursor } from "./http.js";
import { getConfig } from "./env.js";

const { Pool } = pg;

let pool;

function getPool() {
  if (pool) {
    return pool;
  }
  const { sprintctlUrl } = getConfig();
  if (!sprintctlUrl) {
    throw new Error("SPRINTCTL_URL is required");
  }
  pool = new Pool({ connectionString: sprintctlUrl });
  return pool;
}

async function query(text, values = []) {
  const client = await getPool().connect();
  try {
    const result = await client.query(text, values);
    return result.rows;
  } finally {
    client.release();
  }
}

function summarizeWorkItems(items) {
  const summary = { total_items: items.length, pending_items: 0, active_items: 0, done_items: 0, blocked_items: 0 };
  for (const item of items) {
    const key = `${item.status}_items`;
    if (key in summary) {
      summary[key] += 1;
    }
  }
  return summary;
}

function summarizeAttention({ status, kind, summary }) {
  const reasons = [];
  if (status === "closed" && (summary.pending_items > 0 || summary.active_items > 0 || summary.blocked_items > 0)) {
    reasons.push("closed sprint still has open work items");
  }
  if (status === "planned" && summary.blocked_items > 0) {
    reasons.push("planned sprint contains blocked items");
  }
  if (kind === "archive" && summary.total_items === 0) {
    reasons.push("archive sprint has no recorded work items");
  }
  return {
    level: reasons.length > 0 ? "warn" : "ok",
    reasons
  };
}

function buildSprintWhereClause(mode, repoFilter) {
  if (mode === "backlog") {
    return `WHERE s.status = 'planned' AND s.kind = 'backlog' ${repoFilter}`;
  }
  if (mode === "history") {
    return `WHERE (s.status = 'closed' OR s.kind = 'archive') ${repoFilter}`;
  }
  return `WHERE s.status = 'active' AND s.kind = 'active_sprint' ${repoFilter}`;
}

function buildSprintOrderClause(mode) {
  if (mode === "backlog") {
    return "ORDER BY s.repo_id ASC, s.start_date ASC NULLS LAST, s.created_at ASC, s.id ASC";
  }
  if (mode === "history") {
    return "ORDER BY s.repo_id ASC, COALESCE(s.end_date, s.start_date, s.created_at::text) DESC, s.id DESC";
  }
  return "ORDER BY s.repo_id ASC, s.created_at DESC, s.id DESC";
}

export async function listRepos() {
  const rows = await query(
    `
      SELECT
        s.repo_id,
        MAX(GREATEST(
          s.created_at,
          COALESCE(wi.updated_at, s.created_at),
          COALESCE(ev.created_at, s.created_at)
        )) AS latest_update_at
      FROM sprint s
      LEFT JOIN work_item wi ON wi.repo_id = s.repo_id AND wi.sprint_id = s.id
      LEFT JOIN event ev ON ev.repo_id = s.repo_id AND ev.sprint_id = s.id
      GROUP BY s.repo_id
      ORDER BY s.repo_id ASC
    `
  );

  const activeSprints = await query(
    `
      SELECT repo_id, id, name, status, kind, created_at
      FROM sprint
      WHERE status = 'active' AND kind = 'active_sprint'
      ORDER BY repo_id ASC, created_at DESC, id DESC
    `
  );

  const byRepo = new Map();
  for (const sprint of activeSprints) {
    const bucket = byRepo.get(sprint.repo_id) || [];
    bucket.push(sprint);
    byRepo.set(sprint.repo_id, bucket);
  }

  return rows.map((row) => ({
    repo_id: row.repo_id,
    active_sprint_count: (byRepo.get(row.repo_id) || []).length,
    latest_update_at: row.latest_update_at?.toISOString?.() || null,
    active_sprints: (byRepo.get(row.repo_id) || []).map((sprint) => ({
      id: Number(sprint.id),
      name: sprint.name,
      status: sprint.status,
      kind: sprint.kind,
      created_at: sprint.created_at.toISOString()
    })),
    source_health: { source: "pg://sprintctl", status: "ok" }
  }));
}

export async function listSprints(repoId = "ALL", mode = "active") {
  const values = [];
  let repoFilter = "";
  if (repoId !== "ALL") {
    values.push(repoId);
    repoFilter = "AND s.repo_id = $1";
  }
  const sprints = await query(
    `
      SELECT s.*
      FROM sprint s
      ${buildSprintWhereClause(mode, repoFilter)}
      ${buildSprintOrderClause(mode)}
    `,
    values
  );
  if (sprints.length === 0) {
    return [];
  }
  const sprintIds = sprints.map((sprint) => Number(sprint.id));
  const repos = sprints.map((sprint) => sprint.repo_id);
  const items = await query(
    `
      SELECT wi.*, t.name AS track_name
      FROM work_item wi
      JOIN track t ON wi.repo_id = t.repo_id AND wi.track_id = t.id
      WHERE wi.repo_id = ANY($1::text[]) AND wi.sprint_id = ANY($2::bigint[])
      ORDER BY wi.created_at ASC, wi.id ASC
    `,
    [repos, sprintIds]
  );
  const itemsBySprint = new Map();
  for (const item of items) {
    const key = `${item.repo_id}:${item.sprint_id}`;
    const bucket = itemsBySprint.get(key) || [];
    bucket.push({
      id: Number(item.id),
      sprint_id: Number(item.sprint_id),
      title: item.title,
      description: item.description,
      status: item.status,
      assignee: item.assignee,
      track_name: item.track_name,
      created_at: item.created_at.toISOString(),
      updated_at: item.updated_at.toISOString()
    });
    itemsBySprint.set(key, bucket);
  }

  return sprints.map((sprint) => {
    const key = `${sprint.repo_id}:${sprint.id}`;
    const workItems = itemsBySprint.get(key) || [];
    return {
      repo_id: sprint.repo_id,
      id: Number(sprint.id),
      name: sprint.name,
      goal: sprint.goal,
      status: sprint.status,
      kind: sprint.kind,
      start_date: sprint.start_date,
      end_date: sprint.end_date,
      created_at: sprint.created_at.toISOString(),
      work_items: workItems,
      summary: summarizeWorkItems(workItems),
      attention: summarizeAttention({
        status: sprint.status,
        kind: sprint.kind,
        summary: summarizeWorkItems(workItems)
      })
    };
  });
}

function parsePayload(payload) {
  if (!payload) {
    return {};
  }
  if (typeof payload === "string") {
    return JSON.parse(payload);
  }
  return payload;
}

export async function getTakeup(repoId, sprintId) {
  const rows = await query(
    `
      SELECT repo_id, sprint_id, actor, event_type, payload, created_at, id
      FROM event
      WHERE repo_id = $1
        AND sprint_id = $2
        AND event_type IN ('sprint-taken-up', 'sprint-released')
      ORDER BY created_at ASC, id ASC
    `,
    [repoId, sprintId]
  );
  const active = new Map();
  const released = [];
  const unmatched = [];

  for (const row of rows) {
    const payload = parsePayload(row.payload);
    const key = `${row.actor}:${payload.instance_id || ""}`;
    if (row.event_type === "sprint-taken-up") {
      active.set(key, {
        repo_id: row.repo_id,
        sprint_id: Number(row.sprint_id),
        actor: row.actor,
        instance_id: payload.instance_id || null,
        runtime_session_id: payload.runtime_session_id || null,
        taken_up_at: row.created_at.toISOString(),
        source_event_id: Number(row.id)
      });
      continue;
    }
    const matched = active.get(key);
    const releaseRow = {
      repo_id: row.repo_id,
      sprint_id: Number(row.sprint_id),
      actor: row.actor,
      instance_id: payload.instance_id || null,
      runtime_session_id: payload.runtime_session_id || null,
      released_at: row.created_at.toISOString(),
      reason: payload.reason || null,
      source_event_id: Number(row.id)
    };
    if (matched) {
      active.delete(key);
      released.push({ ...matched, ...releaseRow });
    } else {
      unmatched.push(releaseRow);
    }
  }

  return {
    operation: "takeup_list",
    active_takeups: [...active.values()],
    released_takeups: released.reverse(),
    unmatched_releases: unmatched.reverse()
  };
}

export async function listClaims(repoId = "ALL", sprintId = null) {
  const values = [];
  const where = ["c.expires_at > now()"];
  if (repoId !== "ALL") {
    values.push(repoId);
    where.push(`c.repo_id = $${values.length}`);
  }
  if (sprintId != null) {
    values.push(sprintId);
    where.push(`wi.sprint_id = $${values.length}`);
  }
  const rows = await query(
    `
      SELECT c.*, wi.sprint_id, wi.title AS item_title, wi.status AS item_status
      FROM claim c
      JOIN work_item wi ON wi.repo_id = c.repo_id AND wi.id = c.work_item_id
      WHERE ${where.join(" AND ")}
      ORDER BY c.expires_at ASC, c.id ASC
    `,
    values
  );
  return rows.map((row) => ({
    repo_id: row.repo_id,
    sprint_id: Number(row.sprint_id),
    claim_id: Number(row.id),
    work_item_id: Number(row.work_item_id),
    item_title: row.item_title,
    item_status: row.item_status,
    actor: row.agent,
    claim_type: row.claim_type,
    exclusive: row.exclusive,
    heartbeat: row.heartbeat.toISOString(),
    expires_at: row.expires_at.toISOString(),
    runtime_session_id: row.runtime_session_id,
    instance_id: row.instance_id,
    branch: row.branch,
    commit_sha: row.commit_sha
  }));
}

export async function listEvents({ repoId = "ALL", sprintId = null, limit = 100, cursor = null }) {
  const decodedCursor = decodeCursor(cursor);
  const values = [];
  const where = [];
  if (repoId !== "ALL") {
    values.push(repoId);
    where.push(`e.repo_id = $${values.length}`);
  }
  if (sprintId != null) {
    values.push(sprintId);
    where.push(`e.sprint_id = $${values.length}`);
  } else {
    where.push(`EXISTS (
      SELECT 1 FROM sprint s
      WHERE s.repo_id = e.repo_id
        AND s.id = e.sprint_id
        AND s.status = 'active'
        AND s.kind = 'active_sprint'
    )`);
  }
  if (decodedCursor?.created_at && decodedCursor?.id) {
    values.push(decodedCursor.created_at);
    values.push(decodedCursor.id);
    where.push(`(e.created_at, e.id) < ($${values.length - 1}::timestamptz, $${values.length}::bigint)`);
  }
  values.push(limit + 1);
  const rows = await query(
    `
      SELECT e.*
      FROM event e
      ${where.length ? `WHERE ${where.join(" AND ")}` : ""}
      ORDER BY e.created_at DESC, e.id DESC
      LIMIT $${values.length}
    `,
    values
  );
  const hasMore = rows.length > limit;
  const page = rows.slice(0, limit).map((row) => ({
    repo_id: row.repo_id,
    id: Number(row.id),
    sprint_id: Number(row.sprint_id),
    work_item_id: row.work_item_id == null ? null : Number(row.work_item_id),
    source_type: row.source_type,
    actor: row.actor,
    event_type: row.event_type,
    payload: parsePayload(row.payload),
    created_at: row.created_at.toISOString()
  }));
  const last = page[page.length - 1];
  return {
    events: page,
    next_cursor: hasMore && last ? encodeCursor({ created_at: last.created_at, id: last.id }) : null
  };
}
