export const BASE_INTERVALS_MS = {
  repos: 30000,
  primary: 30000,
  claims: 10000,
  secondary: 30000,
  headroom: 300000
};

export const DEFAULT_TWEAKS = {
  compact: false,
  alwaysShowSources: true,
  eventLimit: 20,
  headroomPoll: false
};

export const SPRINT_VIEW_MODES = ["active", "backlog", "history"];

export function getVisibilityBackoffMultiplier(visibilityState) {
  return visibilityState === "hidden" ? 4 : 1;
}

export function getPollIntervalMs(kind, visibilityState) {
  const base = BASE_INTERVALS_MS[kind];
  if (!base) {
    throw new Error(`unknown poll kind: ${kind}`);
  }
  return base * getVisibilityBackoffMultiplier(visibilityState);
}

export function pickSprintSelection(sprints, selectedSprint) {
  if (!Array.isArray(sprints) || sprints.length === 0) {
    return "";
  }
  if (selectedSprint && sprints.some((sprint) => String(sprint.id) === String(selectedSprint))) {
    return String(selectedSprint);
  }
  return String(sprints[0].id);
}

function parseAgeStart(row) {
  return row.completed_at || row.session?.exited_at || row.claimed_at || row.created_at || null;
}

export function summarizeReviewWorktrees(dispatches, { now = new Date() } = {}) {
  const rows = (dispatches || [])
    .filter((row) => ["failed", "rejected"].includes(row.status) && row.session?.worktree)
    .map((row) => {
      const lastSeenAt = parseAgeStart(row);
      const parsed = lastSeenAt ? Date.parse(lastSeenAt) : Number.NaN;
      const ageSeconds = Number.isNaN(parsed) ? null : Math.max(0, Math.round((now.getTime() - parsed) / 1000));
      return {
        action_id: row.id,
        repo_id: row.project || "unknown",
        status: row.status,
        branch: row.session?.branch || null,
        worktree: row.session.worktree,
        failure_reason: row.failure_reason || null,
        last_seen_at: lastSeenAt,
        age_seconds: ageSeconds
      };
    });
  rows.sort((a, b) => (b.age_seconds ?? -1) - (a.age_seconds ?? -1));
  return {
    count: rows.length,
    oldest_age_seconds: rows[0]?.age_seconds ?? null,
    rows
  };
}

export function buildCommandPaletteEntries({ repos, sprints, selectedRepo, sprintMode = "active" }) {
  const entries = [
    { id: "repo:ALL", kind: "repo", label: "ALL", meta: "remote aggregate", value: "ALL" }
  ];

  for (const repo of repos || []) {
    entries.push({
      id: `repo:${repo.repo_id}`,
      kind: "repo",
      label: repo.repo_id,
      meta: `${repo.active_sprint_count} active sprint${repo.active_sprint_count === 1 ? "" : "s"}`,
      value: repo.repo_id
    });
  }

  for (const sprint of sprints || []) {
    entries.push({
      id: `sprint:${sprint.repo_id}:${sprint.id}`,
      kind: "sprint",
      label: `#${sprint.id} ${sprint.name}`,
      meta: sprint.repo_id === selectedRepo ? `${sprintMode} / selected repo` : `${sprintMode} / ${sprint.repo_id}`,
      value: String(sprint.id),
      repo_id: sprint.repo_id
    });
  }

  return entries;
}
