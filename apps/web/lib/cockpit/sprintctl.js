import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";
import { decodeCursor, encodeCursor } from "./http.js";
import { getConfig } from "./env.js";

const execFileAsync = promisify(execFile);

function summarizeWorkItems(items) {
  const summary = { total_items: items.length, pending_items: 0, active_items: 0, done_items: 0, blocked_items: 0 };
  for (const item of items) {
    const key = `${item.status}_items`;
    if (key in summary) summary[key] += 1;
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
  return { level: reasons.length > 0 ? "warn" : "ok", reasons };
}

function asIso(value) {
  if (!value) return null;
  return new Date(value).toISOString();
}

function repoOf(value) {
  return value.repo_id || value.origin_repo;
}

function byNewest(left, right) {
  const time = String(right.created_at).localeCompare(String(left.created_at));
  return time || Number(right.id) - Number(left.id);
}

async function runSprintctl(args, { cwd } = {}) {
  const config = getConfig();
  const result = await execFileAsync(config.sprintctlBin, args, {
    cwd: cwd || config.sprintctlRepoRoot,
    env: process.env,
    timeout: config.sprintctlTimeoutMs,
    maxBuffer: 16 * 1024 * 1024
  });
  try {
    return JSON.parse(result.stdout);
  } catch {
    throw new Error(`sprintctl returned invalid JSON for ${args.join(" ")}`);
  }
}

export function createSprintctlSource(run = runSprintctl, config = getConfig()) {
  const projectCwd = config.sprintctlRepoRoot;
  const repoCwd = (repoId) => path.join(config.workspaceRoot, repoId);

  async function projectSprints(mode = "all") {
    const args = ["sprint", "list", "--project", ".", "--json"];
    if (mode === "active") args.push("--active");
    if (mode === "backlog" || mode === "all") args.push("--include-backlog");
    if (mode === "history" || mode === "all") args.push("--include-archive");
    const values = await run(args, { cwd: projectCwd });
    if (mode === "backlog") return values.filter((value) => value.status === "planned" && value.kind === "backlog");
    if (mode === "history") return values.filter((value) => value.status === "closed" || value.kind === "archive");
    return values;
  }

  async function projectItems() {
    return run(["item", "list", "--project", ".", "--json"], { cwd: projectCwd });
  }

  async function listRepos() {
    const [sprints, items] = await Promise.all([projectSprints("all"), projectItems()]);
    const repos = new Map();
    for (const sprint of sprints) {
      const repoId = repoOf(sprint);
      const current = repos.get(repoId) || { latest_update_at: null, active_sprints: [] };
      current.latest_update_at = [current.latest_update_at, sprint.created_at].filter(Boolean).sort().at(-1) || null;
      if (sprint.status === "active" && sprint.kind === "active_sprint") current.active_sprints.push(sprint);
      repos.set(repoId, current);
    }
    for (const item of items) {
      const repoId = repoOf(item);
      const current = repos.get(repoId) || { latest_update_at: null, active_sprints: [] };
      current.latest_update_at = [current.latest_update_at, item.updated_at, item.created_at].filter(Boolean).sort().at(-1) || null;
      repos.set(repoId, current);
    }
    return [...repos.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([repo_id, value]) => ({
      repo_id,
      active_sprint_count: value.active_sprints.length,
      latest_update_at: asIso(value.latest_update_at),
      active_sprints: value.active_sprints.sort(byNewest).map((sprint) => ({
        id: Number(sprint.id),
        name: sprint.name,
        status: sprint.status,
        kind: sprint.kind,
        created_at: asIso(sprint.created_at)
      })),
      source_health: { source: "served://vuoro/work", status: "ok" }
    }));
  }

  async function listSprints(repoId = "ALL", mode = "active") {
    const [sprints, items] = await Promise.all([projectSprints(mode), projectItems()]);
    const selected = sprints.filter((sprint) => repoId === "ALL" || repoOf(sprint) === repoId);
    const itemBuckets = new Map();
    for (const item of items) {
      const key = `${repoOf(item)}:${item.sprint_id}`;
      const bucket = itemBuckets.get(key) || [];
      bucket.push({
        id: Number(item.id),
        sprint_id: Number(item.sprint_id),
        title: item.title,
        description: item.description,
        status: item.status,
        assignee: item.assignee,
        track_name: item.track_name,
        created_at: asIso(item.created_at),
        updated_at: asIso(item.updated_at)
      });
      itemBuckets.set(key, bucket);
    }
    return selected.map((sprint) => {
      const repo_id = repoOf(sprint);
      const work_items = itemBuckets.get(`${repo_id}:${sprint.id}`) || [];
      const summary = summarizeWorkItems(work_items);
      return {
        repo_id,
        id: Number(sprint.id),
        name: sprint.name,
        goal: sprint.goal,
        status: sprint.status,
        kind: sprint.kind,
        start_date: sprint.start_date,
        end_date: sprint.end_date,
        created_at: asIso(sprint.created_at),
        work_items,
        summary,
        attention: summarizeAttention({ status: sprint.status, kind: sprint.kind, summary })
      };
    });
  }

  async function sprintEvents(repoId, sprintId, limit = 500) {
    return run(
      ["event", "list", "--sprint-id", `${repoId}#${sprintId}`, "--limit", String(limit), "--json"],
      { cwd: repoCwd(repoId) }
    );
  }

  async function getTakeup(repoId, sprintId) {
    const rows = await sprintEvents(repoId, sprintId);
    const active = new Map();
    const released = [];
    const unmatched = [];
    for (const row of rows.slice().reverse()) {
      if (!["sprint-taken-up", "sprint-released"].includes(row.event_type)) continue;
      const payload = typeof row.payload === "string" ? JSON.parse(row.payload) : (row.payload || {});
      const key = `${row.actor}:${payload.instance_id || ""}`;
      if (row.event_type === "sprint-taken-up") {
        active.set(key, {
          repo_id: repoId, sprint_id: Number(sprintId), actor: row.actor,
          instance_id: payload.instance_id || null, runtime_session_id: payload.runtime_session_id || null,
          taken_up_at: asIso(row.created_at), source_event_id: Number(row.id)
        });
        continue;
      }
      const matched = active.get(key);
      const release = {
        repo_id: repoId, sprint_id: Number(sprintId), actor: row.actor,
        instance_id: payload.instance_id || null, runtime_session_id: payload.runtime_session_id || null,
        released_at: asIso(row.created_at), reason: payload.reason || null, source_event_id: Number(row.id)
      };
      if (matched) {
        active.delete(key);
        released.push({ ...matched, ...release });
      } else {
        unmatched.push(release);
      }
    }
    return { operation: "takeup_list", active_takeups: [...active.values()], released_takeups: released.reverse(), unmatched_releases: unmatched.reverse() };
  }

  async function listClaims(repoId = "ALL", sprintId = null) {
    let sprints = await projectSprints("active");
    if (repoId !== "ALL") sprints = sprints.filter((sprint) => repoOf(sprint) === repoId);
    if (sprintId != null) sprints = sprints.filter((sprint) => Number(sprint.id) === Number(sprintId));
    const pages = await Promise.all(sprints.map(async (sprint) => {
      const scopedRepo = repoOf(sprint);
      const claims = await run(
        ["claim", "list-sprint", "--sprint-id", `${scopedRepo}#${sprint.id}`, "--json"],
        { cwd: repoCwd(scopedRepo) }
      );
      return claims.map((claim) => ({
        repo_id: scopedRepo,
        sprint_id: Number(sprint.id),
        claim_id: Number(claim.claim_id || claim.id),
        work_item_id: Number(claim.work_item_id),
        item_title: claim.item_title,
        item_status: claim.item_status,
        actor: claim.actor || claim.agent,
        claim_type: claim.claim_type,
        exclusive: claim.exclusive,
        heartbeat: asIso(claim.heartbeat),
        expires_at: asIso(claim.expires_at),
        runtime_session_id: claim.runtime_session_id,
        instance_id: claim.instance_id,
        branch: claim.branch,
        commit_sha: claim.commit_sha
      }));
    }));
    return pages.flat().sort((a, b) => String(a.expires_at).localeCompare(String(b.expires_at)) || a.claim_id - b.claim_id);
  }

  async function listEvents({ repoId = "ALL", sprintId = null, limit = 100, cursor = null }) {
    let sprints = await projectSprints("active");
    if (repoId !== "ALL") sprints = sprints.filter((sprint) => repoOf(sprint) === repoId);
    if (sprintId != null) sprints = sprints.filter((sprint) => Number(sprint.id) === Number(sprintId));
    const pages = await Promise.all(sprints.map((sprint) => sprintEvents(repoOf(sprint), sprint.id, limit + 1)));
    const decoded = decodeCursor(cursor);
    let events = pages.flat().map((event) => ({
      repo_id: repoOf(event),
      id: Number(event.id),
      sprint_id: Number(event.sprint_id),
      work_item_id: event.work_item_id == null ? null : Number(event.work_item_id),
      source_type: event.source_type,
      actor: event.actor,
      event_type: event.event_type,
      payload: typeof event.payload === "string" ? JSON.parse(event.payload) : (event.payload || {}),
      created_at: asIso(event.created_at)
    })).sort(byNewest);
    if (decoded?.created_at && decoded?.id) {
      events = events.filter((event) =>
        event.created_at < decoded.created_at ||
        (event.created_at === decoded.created_at && event.id < Number(decoded.id))
      );
    }
    const hasMore = events.length > limit;
    const page = events.slice(0, limit);
    const last = page.at(-1);
    return { events: page, next_cursor: hasMore && last ? encodeCursor({ created_at: last.created_at, id: last.id }) : null };
  }

  async function activateSprint(repoId, sprintId, { actor = "operator:cockpit" } = {}) {
    const before = (await projectSprints("all")).find((sprint) => repoOf(sprint) === repoId && Number(sprint.id) === Number(sprintId));
    if (!before) throw new SprintNotFoundError(`Sprint ${sprintId} not found for repo ${repoId}`);
    try {
      await run(
        ["sprint", "status", "--id", `${repoId}#${sprintId}`, "--status", "active", "--actor", actor, "--json"],
        { cwd: repoCwd(repoId) }
      );
    } catch (error) {
      const detail = `${error.stderr || ""}\n${error.message || ""}`;
      if (/not found/i.test(detail)) throw new SprintNotFoundError(detail.trim());
      if (/cannot transition|invalid-transition|SP409/i.test(detail)) throw new SprintTransitionError(detail.trim());
      throw error;
    }
    return {
      id: Number(sprintId), repo_id: repoId, name: before.name, status: "active", kind: "active_sprint",
      previous_status: before.status, previous_kind: before.kind, actor
    };
  }

  return { listRepos, listSprints, getTakeup, listClaims, listEvents, activateSprint };
}

export class SprintNotFoundError extends Error {}
export class SprintTransitionError extends Error {}

const source = createSprintctlSource();
export const listRepos = source.listRepos;
export const listSprints = source.listSprints;
export const getTakeup = source.getTakeup;
export const listClaims = source.listClaims;
export const listEvents = source.listEvents;
export const activateSprint = source.activateSprint;
