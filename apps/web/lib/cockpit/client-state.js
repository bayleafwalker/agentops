export const BASE_INTERVALS_MS = {
  repos: 30000,
  primary: 30000,
  claims: 10000,
  secondary: 30000
};

export const DEFAULT_TWEAKS = {
  compact: false,
  alwaysShowSources: true,
  eventLimit: 20
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
