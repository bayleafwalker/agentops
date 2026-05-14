"use client";

import { useEffect, useState } from "react";
import { buildCommandPaletteEntries, DEFAULT_TWEAKS, getPollIntervalMs, getVisibilityBackoffMultiplier, pickSprintSelection, SPRINT_VIEW_MODES, summarizeReviewWorktrees } from "../../lib/cockpit/client-state.js";
import { CockpitNav } from "./cockpit-nav";
import { CockpitStatusBar } from "./cockpit-status-bar";
import { CommandPalette } from "./command-palette";
import { DegradedSourceBanner } from "./degraded-source-banner";
import { DispatchComposer } from "./dispatch-composer";
import { SourceTruthTag } from "./source-truth-tag";
import { TweaksPanel } from "./tweaks-panel";

function isoLabel(value) {
  if (!value) {
    return "n/a";
  }
  return new Date(value).toISOString();
}

async function readJson(url, init = {}) {
  const response = await fetch(url, { cache: "no-store", ...init });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error?.message || `request failed: ${response.status}`);
  }
  return payload;
}

const MODE_LABELS = {
  active: "Active",
  backlog: "Backlog",
  history: "History"
};

function durationLabel(start, end) {
  if (!start) {
    return "n/a";
  }
  const started = Date.parse(start);
  const ended = end ? Date.parse(end) : Date.now();
  if (Number.isNaN(started) || Number.isNaN(ended) || ended < started) {
    return "n/a";
  }
  const seconds = Math.round((ended - started) / 1000);
  if (seconds < 90) {
    return `${seconds}s`;
  }
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) {
    return `${minutes}m`;
  }
  return `${Math.round(minutes / 60)}h`;
}

function secondsLabel(value) {
  if (value == null || !Number.isFinite(Number(value))) {
    return "unknown";
  }
  const seconds = Math.max(0, Math.round(Number(value)));
  if (seconds < 90) {
    return `${seconds}s`;
  }
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) {
    return `${minutes}m`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 48) {
    return `${hours}h`;
  }
  return `${Math.round(hours / 24)}d`;
}

function ageLabel(value) {
  if (!value) {
    return "never";
  }
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    return "unknown";
  }
  const seconds = Math.max(0, Math.round((Date.now() - parsed) / 1000));
  if (seconds < 90) {
    return `${seconds}s ago`;
  }
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) {
    return `${minutes}m ago`;
  }
  return `${Math.round(minutes / 60)}h ago`;
}

function percentLabel(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${Math.round(number)}%` : "unknown";
}

function groupDispatches(rows) {
  const groups = new Map();
  for (const row of rows) {
    const key = row.dispatch_group_id || "ungrouped";
    const bucket = groups.get(key) || [];
    bucket.push(row);
    groups.set(key, bucket);
  }
  return [...groups.entries()];
}

function claimLivenessLabel(session) {
  if (!session) {
    return "missing";
  }
  if (session.is_stale) {
    return "stale";
  }
  if (session.ttl_remaining_seconds != null) {
    return `${secondsLabel(session.ttl_remaining_seconds)} left`;
  }
  return "alive";
}

function ModelHeadroomPanel({ data, refreshing, onRefresh }) {
  const snapshot = data?.snapshot;
  const codex = snapshot?.providers?.codex;
  const claude = snapshot?.providers?.claude;
  return (
    <section className="item-card">
      <div className="title-row">
        <strong>Model Headroom</strong>
        <button className="mode-button" type="button" onClick={onRefresh} disabled={refreshing}>
          {refreshing ? "Refreshing" : "Refresh"}
        </button>
      </div>
      <div className="small muted">
        refreshed={ageLabel(snapshot?.refreshed_at)}{snapshot?.stale ? " stale" : ""}
      </div>
      <div className="small muted">
        codex 5h={percentLabel(codex?.rate_limit?.primary_window?.used_percent)} weekly={percentLabel(codex?.rate_limit?.secondary_window?.used_percent)} credits={codex?.credits?.unlimited ? "unlimited" : codex?.credits?.balance ?? "unknown"}
      </div>
      <div className="small muted">
        claude 5h={percentLabel(claude?.current_window?.used_percent)} opus-weekly={percentLabel(claude?.weekly_limit?.opus?.used_percent)} other-weekly={percentLabel(claude?.weekly_limit?.other?.used_percent)}
      </div>
      {data?.degraded ? <div className="small muted">{data.degraded.message}</div> : null}
    </section>
  );
}

export function CockpitShell() {
  const [reposData, setReposData] = useState({ repos: [], degraded: null });
  const [selectedRepo, setSelectedRepo] = useState("ALL");
  const [selectedMode, setSelectedMode] = useState("active");
  const [selectedSprint, setSelectedSprint] = useState("");
  const [sprintsData, setSprintsData] = useState({ sprints: [], degraded: null });
  const [takeupData, setTakeupData] = useState({ active_takeups: [], released_takeups: [], degraded: null });
  const [claimsData, setClaimsData] = useState({ claims: [], degraded: null });
  const [dispatchesData, setDispatchesData] = useState({ dispatches: [], degraded: null });
  const [eventsData, setEventsData] = useState({ events: [], degraded: null });
  const [auditData, setAuditData] = useState({ events: [], degraded: null });
  const [costData, setCostData] = useState({ summary: null, degraded: null });
  const [headroomData, setHeadroomData] = useState({ snapshot: null, degraded: null });
  const [headroomRefreshing, setHeadroomRefreshing] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [dispatchData, setDispatchData] = useState({ manifests: [], warnings: [], degraded: null });
  const [dispatcherPauseData, setDispatcherPauseData] = useState({ paused: false, pause_file: null, updated_at: null, degraded: null });
  const [pauseUpdating, setPauseUpdating] = useState(false);
  const [activatingSprint, setActivatingSprint] = useState(null);
  const [refreshedAt, setRefreshedAt] = useState(null);
  const [fatalError, setFatalError] = useState("");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [visibilityState, setVisibilityState] = useState("visible");
  const [tweaks, setTweaks] = useState(DEFAULT_TWEAKS);

  const pollMultiplier = getVisibilityBackoffMultiplier(visibilityState);
  const effectiveSprintMode = selectedMode;

  async function loadHeadroom(force = false) {
    setHeadroomRefreshing(true);
    try {
      const data = await readJson("/cockpit/api/headroom", {
        method: force ? "POST" : "GET"
      });
      setHeadroomData(data);
    } catch (error) {
      setHeadroomData((current) => ({
        ...current,
        degraded: { source: "model-headroom", message: error.message }
      }));
    } finally {
      setHeadroomRefreshing(false);
    }
  }

  async function loadDispatcherPause() {
    try {
      const data = await readJson("/cockpit/api/dispatcher/pause");
      setDispatcherPauseData(data);
      return data;
    } catch (error) {
      setDispatcherPauseData((current) => ({
        ...current,
        degraded: { source: "fs://dispatcher-pause", message: error.message }
      }));
      return null;
    }
  }

  function loadAll() {
    setRefreshKey((k) => k + 1);
    loadHeadroom(false);
    loadDispatcherPause();
  }

  async function toggleDispatcherPause(nextPaused) {
    setPauseUpdating(true);
    try {
      const data = await readJson("/cockpit/api/dispatcher/pause", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ paused: nextPaused })
      });
      setDispatcherPauseData(data);
    } catch (error) {
      setDispatcherPauseData((current) => ({
        ...current,
        degraded: { source: "fs://dispatcher-pause", message: error.message }
      }));
    } finally {
      setPauseUpdating(false);
    }
  }

  async function handleActivateSprint(repoId, sprintId) {
    setActivatingSprint(sprintId);
    try {
      await readJson("/cockpit/api/sprints/activate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ repo_id: repoId, sprint_id: sprintId })
      });
      setSelectedMode("active");
    } catch (error) {
      console.error("Sprint activation failed:", error.message);
    } finally {
      setActivatingSprint(null);
    }
  }

  useEffect(() => {
    function onVisibilityChange() {
      setVisibilityState(document.visibilityState || "visible");
    }

    onVisibilityChange();
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
  }, []);

  useEffect(() => {
    function onKeyDown(event) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
      if (event.key === "Escape") {
        setPaletteOpen(false);
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    loadHeadroom(false);
    loadDispatcherPause();
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer;

    async function pollPause() {
      if (!cancelled) {
        await loadDispatcherPause();
      }
      if (!cancelled && tweaks.pollAll) {
        timer = setTimeout(pollPause, getPollIntervalMs("claims", document.visibilityState || "visible"));
      }
    }

    timer = setTimeout(pollPause, getPollIntervalMs("claims", document.visibilityState || "visible"));
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [tweaks.pollAll, visibilityState]);

  useEffect(() => {
    if (!tweaks.pollAll) {
      return undefined;
    }
    let cancelled = false;
    let timer;

    async function pollHeadroom() {
      if (!cancelled) {
        await loadHeadroom(false);
      }
      if (!cancelled) {
        timer = setTimeout(pollHeadroom, getPollIntervalMs("headroom", document.visibilityState || "visible"));
      }
    }

    timer = setTimeout(pollHeadroom, getPollIntervalMs("headroom", document.visibilityState || "visible"));
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [tweaks.pollAll, visibilityState]);

  useEffect(() => {
    let cancelled = false;
    let timer;

    async function loadRepos() {
      try {
        const data = await readJson("/cockpit/api/repos");
        if (cancelled) {
          return;
        }
        setReposData(data);
        if (selectedRepo !== "ALL" && !data.repos.some((repo) => repo.repo_id === selectedRepo)) {
          setSelectedRepo("ALL");
          setSelectedSprint("");
        }
        setFatalError("");
      } catch (error) {
        if (!cancelled) {
          setFatalError(error.message);
        }
      } finally {
        if (!cancelled && tweaks.pollAll) {
          timer = setTimeout(loadRepos, getPollIntervalMs("repos", document.visibilityState || "visible"));
        }
      }
    }

    loadRepos();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [selectedRepo, tweaks.pollAll, refreshKey, visibilityState]);

  useEffect(() => {
    let cancelled = false;
    let timer;

    async function loadPrimary() {
      const params = new URLSearchParams({
        repo_id: selectedRepo,
        mode: effectiveSprintMode,
        limit: String(tweaks.eventLimit)
      });
      try {
        const [sprints, events] = await Promise.all([
          readJson(`/cockpit/api/sprints?${params}`),
          readJson(`/cockpit/api/events?${params}`),
        ]);
        if (cancelled) {
          return;
        }
        setSprintsData(sprints);
        setEventsData(events);
        setSelectedSprint((current) => pickSprintSelection(sprints.sprints, current));
        setRefreshedAt(new Date().toISOString());
      } catch (error) {
        if (!cancelled) {
          setFatalError(error.message);
        }
      } finally {
        if (!cancelled && tweaks.pollAll) {
          timer = setTimeout(loadPrimary, getPollIntervalMs("primary", document.visibilityState || "visible"));
        }
      }
    }

    loadPrimary();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [effectiveSprintMode, selectedRepo, tweaks.eventLimit, tweaks.pollAll, refreshKey, visibilityState]);

  useEffect(() => {
    let cancelled = false;
    let timer;

    async function loadClaims() {
      const params = new URLSearchParams({ repo_id: selectedRepo });
      if (selectedRepo !== "ALL" && selectedSprint && effectiveSprintMode === "active") {
        params.set("sprint_id", selectedSprint);
      }
      try {
        const claims = await readJson(`/cockpit/api/claims?${params}`);
        if (cancelled) {
          return;
        }
        setClaimsData(claims);
        setRefreshedAt(new Date().toISOString());
      } catch (error) {
        if (!cancelled) {
          setFatalError(error.message);
        }
      } finally {
        if (!cancelled && tweaks.pollAll) {
          timer = setTimeout(loadClaims, getPollIntervalMs("claims", document.visibilityState || "visible"));
        }
      }
    }

    loadClaims();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [effectiveSprintMode, selectedRepo, selectedSprint, tweaks.pollAll, refreshKey, visibilityState]);

  useEffect(() => {
    let cancelled = false;
    let timer;

    async function loadDispatchesAndCost() {
      const params = new URLSearchParams({ repo_id: selectedRepo, limit: "100" });
      try {
        const [dispatches, costs] = await Promise.all([
          readJson(`/cockpit/api/dispatches?${params}`),
          readJson("/cockpit/api/costs/summary"),
        ]);
        if (cancelled) {
          return;
        }
        setDispatchesData(dispatches);
        setCostData(costs);
        setRefreshedAt(new Date().toISOString());
      } catch (error) {
        if (!cancelled) {
          setFatalError(error.message);
        }
      } finally {
        if (!cancelled && tweaks.pollAll) {
          timer = setTimeout(loadDispatchesAndCost, getPollIntervalMs("claims", document.visibilityState || "visible"));
        }
      }
    }

    loadDispatchesAndCost();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [selectedRepo, tweaks.pollAll, refreshKey, visibilityState]);

  useEffect(() => {
    let cancelled = false;
    let timer;

    async function loadDispatchManifests() {
      const params = new URLSearchParams({ repo_id: selectedRepo });
      try {
        const manifests = await readJson(`/cockpit/api/dispatch-manifests?${params}`);
        if (cancelled) {
          return;
        }
        setDispatchData(manifests);
      } catch (error) {
        if (!cancelled) {
          setFatalError(error.message);
        }
      } finally {
        if (!cancelled && tweaks.pollAll) {
          timer = setTimeout(loadDispatchManifests, getPollIntervalMs("primary", document.visibilityState || "visible"));
        }
      }
    }

    loadDispatchManifests();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [selectedRepo, tweaks.pollAll, refreshKey, visibilityState]);

  useEffect(() => {
    if (sprintsData.sprints.length === 0) {
      if (selectedSprint) {
        setSelectedSprint("");
      }
      return;
    }
    const nextSelection = pickSprintSelection(sprintsData.sprints, selectedSprint);
    if (nextSelection !== selectedSprint) {
      setSelectedSprint(nextSelection);
    }
  }, [selectedRepo, selectedSprint, sprintsData.sprints]);

  useEffect(() => {
    if (!selectedSprint || selectedRepo === "ALL") {
      setTakeupData({ active_takeups: [], released_takeups: [], degraded: null });
      setAuditData({ events: [], degraded: null });
      return;
    }

    let cancelled = false;
    const sprintId = selectedSprint;
    let timer;

    async function loadSecondary() {
      const takeupParams = new URLSearchParams({ repo_id: selectedRepo, sprint_id: sprintId });
      const auditParams = new URLSearchParams({ repo_id: selectedRepo, days: "3", limit: String(tweaks.eventLimit) });
      try {
        const [takeup, audit] = await Promise.all([
          readJson(`/cockpit/api/takeup?${takeupParams}`),
          readJson(`/cockpit/api/audit?${auditParams}`),
        ]);
        if (cancelled) {
          return;
        }
        setTakeupData(takeup);
        setAuditData(audit);
        setRefreshedAt(new Date().toISOString());
      } catch (error) {
        if (!cancelled) {
          setFatalError(error.message);
        }
      } finally {
        if (!cancelled && tweaks.pollAll) {
          timer = setTimeout(loadSecondary, getPollIntervalMs("secondary", document.visibilityState || "visible"));
        }
      }
    }

    loadSecondary();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [selectedRepo, selectedSprint, tweaks.eventLimit, tweaks.pollAll, refreshKey, visibilityState]);

  const activeSprint = sprintsData.sprints.find((sprint) => String(sprint.id) === selectedSprint);
  const sprintsWithItems = sprintsData.sprints.filter((sprint) => sprint.summary.total_items > 0).length;
  const emptySprints = sprintsData.sprints.length - sprintsWithItems;
  const cleanupRequiredCount = sprintsData.sprints.filter((sprint) => sprint.attention?.level === "warn").length;
  const paletteEntries = buildCommandPaletteEntries({
    repos: reposData.repos,
    sprints: sprintsData.sprints,
    selectedRepo,
    sprintMode: effectiveSprintMode
  });
  const health = {
    pg: reposData.degraded ? "degraded" : "ok",
    actionq: claimsData.degraded ? "degraded" : "ok",
    audit: auditData.degraded ? "degraded" : "ok"
  };
  const activeDispatchManifest =
    selectedRepo === "ALL"
      ? null
      : dispatchData.manifests.find((manifest) => manifest.repo_id === selectedRepo);
  const dispatchGroups = groupDispatches(dispatchesData.dispatches);
  const costsBySession = costData.summary?.by_session || {};
  const reviewWorktrees = summarizeReviewWorktrees(dispatchesData.dispatches);

  const sprintModeNote = selectedRepo === "ALL"
    ? "ALL aggregates remote repos only; dispatch remains repo-scoped."
    : effectiveSprintMode === "active"
      ? "active repo sprints, claims, takeup, live work posture"
      : effectiveSprintMode === "backlog"
        ? "planned backlog sprints ordered for readiness"
        : "closed and archived sprint records";

  return (
    <div className={`cockpit-shell ${tweaks.compact ? "compact" : ""}`}>
      <CommandPalette
        entries={paletteEntries}
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onPick={(entry) => {
          if (entry.kind === "repo") {
            setSelectedRepo(entry.value);
            setSelectedSprint("");
            return;
          }
          setSelectedRepo(entry.repo_id);
          setSelectedSprint(entry.value);
        }}
      />
      <aside className="cockpit-pane">
        <div className="cockpit-paneInner">
          <section className="cockpit-section">
            <p className="eyebrow">read-only cockpit</p>
            <div className="title-row">
              <h1 className="pane-title">Repo Strip</h1>
              {tweaks.alwaysShowSources ? <SourceTruthTag source="pg://sprintctl" /> : null}
            </div>
            <p className="small muted">Remote mode only</p>
            <DegradedSourceBanner message={reposData.degraded?.message || fatalError} />
          </section>
          <section className="cockpit-section">
            <CockpitNav />
          </section>
          <section className="cockpit-section repo-list">
            <button
              className={`repo-button ${selectedRepo === "ALL" ? "active" : ""}`}
              type="button"
              onClick={() => {
                setSelectedRepo("ALL");
                setSelectedSprint("");
              }}
            >
              <div className="title-row">
                <strong>ALL</strong>
                <span className="status-chip ok">virtual</span>
              </div>
            </button>
            {reposData.repos.map((repo) => (
              <button
                key={repo.repo_id}
                className={`repo-button ${selectedRepo === repo.repo_id ? "active" : ""}`}
                type="button"
                onClick={() => {
                  setSelectedRepo(repo.repo_id);
                  setSelectedSprint(
                    effectiveSprintMode === "active" && repo.active_sprints[0] ? String(repo.active_sprints[0].id) : ""
                  );
                }}
              >
                <div className="title-row">
                  <strong>{repo.repo_id}</strong>
                  <span className={`status-chip ${repo.source_health.status === "ok" ? "ok" : "warn"}`}>
                    {repo.active_sprint_count} active
                  </span>
                </div>
                <div className="small muted">latest {isoLabel(repo.latest_update_at)}</div>
              </button>
            ))}
          </section>
        </div>
      </aside>

      <section className="cockpit-pane">
        <div className="cockpit-paneInner">
          <section className="cockpit-section" id="overview">
            <div className="ops-head">
              <div>
                <div className="title-row title-row-start">
                  <h2 className="pane-title">Sprints</h2>
                  {tweaks.alwaysShowSources ? <SourceTruthTag source="pg://sprintctl" /> : null}
                </div>
                <div className="ops-summary-line table-mono">
                  repo={selectedRepo} mode={effectiveSprintMode} sprints={sprintsData.sprints.length} cleanup={cleanupRequiredCount} claims={claimsData.claims.length} events={eventsData.events.length}
                </div>
                <div className="small muted">{sprintModeNote}</div>
              </div>
              <div className="mode-toggle mode-toggle-inline" role="tablist" aria-label="Sprint view mode">
                {SPRINT_VIEW_MODES.map((mode) => (
                  <button
                    key={mode}
                    className={`mode-button ${effectiveSprintMode === mode ? "active" : ""}`}
                    type="button"
                    onClick={() => {
                      setSelectedMode(mode);
                      setSelectedSprint("");
                    }}
                  >
                    {MODE_LABELS[mode]}
                  </button>
                ))}
              </div>
            </div>
            <DegradedSourceBanner message={sprintsData.degraded?.message} />
          </section>
          <section className="cockpit-section live-section" id="claims">
            <div className="title-row">
              <h3 className="section-title">Claims</h3>
              {tweaks.alwaysShowSources ? <SourceTruthTag source="actionq://sessions + pg://sprintctl" /> : null}
            </div>
            <DegradedSourceBanner message={claimsData.degraded?.message} />
            {effectiveSprintMode !== "active" ? (
              <div className="empty-state small muted">Claims stay attached to the Active view; planning and history modes do not filter by sprint claims.</div>
            ) : (
              <>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Item</th>
                        <th>Actor</th>
                        <th>Session</th>
                        <th>Heartbeat</th>
                        <th>TTL</th>
                      </tr>
                    </thead>
                    <tbody>
                      {claimsData.claims.map((row) => (
                        <tr key={row.claim.claim_id} className={row.session?.is_stale ? "row-muted" : ""}>
                          <td>#{row.claim.work_item_id} {row.claim.item_title}</td>
                          <td>{row.claim.actor}</td>
                          <td className="table-mono">{row.session?.runtime_session_id || "unknown"}</td>
                          <td>
                            <div>{row.session?.heartbeat_at || "unknown"}</div>
                            {row.session?.deadline_at ? <div className="small muted">deadline={row.session.deadline_at}</div> : null}
                          </td>
                          <td>
                            <span className={`status-chip ${row.session?.is_stale ? "error" : row.session ? "ok" : "warn"}`}>
                              {claimLivenessLabel(row.session)}
                            </span>
                            <div className="small muted">ttl={row.session?.ttl_seconds ?? "unknown"}</div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {claimsData.claims.length === 0 ? (
                  <div className="empty-state small muted">No active claims match the current repo filter.</div>
                ) : null}
              </>
            )}
          </section>
          <section className="cockpit-section reference-section" id="sprints">
            <div className="title-row">
              <div className="title-row title-row-start">
                <h3 className="section-title">{MODE_LABELS[effectiveSprintMode]} Sprint Tabs</h3>
                <span className="small muted">{sprintsWithItems} with-items / {emptySprints} empty</span>
              </div>
              <span className="small muted">{selectedRepo}</span>
            </div>
            <div className="repo-list">
              {sprintsData.sprints.map((sprint) => (
                <div key={`${sprint.repo_id}:${sprint.id}`} className="sprint-item">
                  <button
                    className={`sprint-button ${String(sprint.id) === selectedSprint ? "active" : ""}`}
                    type="button"
                    onClick={() => setSelectedSprint(String(sprint.id))}
                  >
                    <div className="title-row">
                      <strong>#{sprint.id} {sprint.name}</strong>
                      <span className="small muted">{sprint.repo_id}</span>
                    </div>
                    <div className="small muted">
                      items {sprint.summary.total_items} / done {sprint.summary.done_items} / open {sprint.summary.pending_items + sprint.summary.active_items + sprint.summary.blocked_items}
                    </div>
                    {sprint.attention?.reasons?.length ? (
                      <div className="small muted">attention: {sprint.attention.reasons.join("; ")}</div>
                    ) : null}
                  </button>
                  {effectiveSprintMode === "backlog" ? (
                    <button
                      className="mode-button"
                      type="button"
                      disabled={activatingSprint === sprint.id}
                      onClick={() => handleActivateSprint(sprint.repo_id, sprint.id)}
                    >
                      {activatingSprint === sprint.id ? "Activating…" : "Activate"}
                    </button>
                  ) : null}
                </div>
              ))}
            </div>
            {sprintsData.sprints.length === 0 ? (
              <div className="empty-state small muted">
                No {effectiveSprintMode} remote sprints are visible for this repo filter.
              </div>
            ) : null}
          </section>
          <section className="cockpit-section live-section" id="dispatch">
            <div className="title-row">
              <h3 className="section-title">Dispatch</h3>
              {tweaks.alwaysShowSources ? <SourceTruthTag source={dispatchData.source || "dispatch-manifest"} /> : null}
            </div>
            <DegradedSourceBanner message={dispatchData.degraded?.message} />
            <div className="item-list">
              {selectedRepo === "ALL" ? (
                <div className="item-card">
                  <div className="title-row">
                    <strong>Dispatch Manifests</strong>
                    <span className="status-chip ok">{dispatchData.manifests.length} visible</span>
                  </div>
                  <div className="small muted">
                    Select a repo to inspect routing defaults, adoption level, hooks, and selected shared skills.
                  </div>
                </div>
              ) : activeDispatchManifest ? (
                <div className="item-card">
                  <div className="title-row">
                    <strong>{activeDispatchManifest.adoption_level}</strong>
                    <span className="status-chip ok">{activeDispatchManifest.routing.default_harness}</span>
                  </div>
                  <div className="small muted">
                    default_model={activeDispatchManifest.routing.default_model_alias}
                  </div>
                  <div className="small muted">
                    classes={Object.entries(activeDispatchManifest.routing.action_classes)
                      .filter(([, actionClass]) => actionClass.enabled)
                      .map(([name]) => name)
                      .join(", ")}
                  </div>
                  <div className="small muted">
                    hooks={activeDispatchManifest.hooks.level} / {activeDispatchManifest.hooks.publishers.join(", ")}
                  </div>
                </div>
              ) : (
                <div className="empty-state small muted">No dispatch manifest is registered for {selectedRepo}.</div>
              )}
              <ModelHeadroomPanel
                data={headroomData}
                refreshing={headroomRefreshing}
                onRefresh={() => loadHeadroom(true)}
              />
            </div>
            <DispatchComposer
              repoId={selectedRepo}
              sprintId={effectiveSprintMode === "active" || effectiveSprintMode === "backlog" ? selectedSprint : ""}
              mode={effectiveSprintMode}
              headroom={headroomData.snapshot}
              onRefreshHeadroom={() => loadHeadroom(true)}
              dispatcherPause={dispatcherPauseData}
              pauseUpdating={pauseUpdating}
              onTogglePause={toggleDispatcherPause}
              disabledReason={
                selectedRepo === "ALL"
                  ? "Dispatch remains scoped to one concrete repo; ALL is browse-only."
                  : effectiveSprintMode === "history"
                    ? "History is read-only; use Active or Backlog for dispatch."
                  : null
              }
            />
          </section>
          <section className="cockpit-section reference-section" id="work-items">
            <div className="title-row">
              <h3 className="section-title">Work Items</h3>
              <span className="small muted">{activeSprint ? activeSprint.repo_id : selectedRepo}</span>
            </div>
            <div className="item-list">
              {(activeSprint?.work_items || []).map((item) => (
                <div key={item.id} className="item-card">
                  <div className="title-row">
                    <strong>#{item.id} {item.title}</strong>
                    <span className={`status-chip ${item.status === "done" ? "ok" : item.status === "blocked" ? "error" : "warn"}`}>
                      {item.status}
                    </span>
                  </div>
                  <div className="small muted">
                    track={item.track_name} assignee={item.assignee || "none"}
                  </div>
                </div>
              ))}
            </div>
            {!activeSprint ? (
              <div className="empty-state small muted">Select a repo sprint to inspect its work items.</div>
            ) : activeSprint.work_items.length === 0 ? (
              <div className="empty-state small muted">
                Sprint #{activeSprint.id} has no work items yet. This is valid live data, not a loading gap.
              </div>
            ) : null}
          </section>
          <section className="cockpit-section" id="dispatches">
            <div className="title-row">
              <h3 className="section-title">Dispatches</h3>
              {tweaks.alwaysShowSources ? <SourceTruthTag source="actionq://dispatches" /> : null}
            </div>
            <DegradedSourceBanner message={dispatchesData.degraded?.message} />
            <div className="item-card review-worktrees">
              <div className="title-row">
                <strong>Review Worktrees</strong>
                <span className={`status-chip ${reviewWorktrees.count ? "warn" : "ok"}`}>
                  {reviewWorktrees.count} abandoned
                </span>
              </div>
              <div className="small muted">
                oldest={reviewWorktrees.oldest_age_seconds == null ? "none" : `${secondsLabel(reviewWorktrees.oldest_age_seconds)} ago`}
              </div>
              {reviewWorktrees.rows.length ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Action</th>
                        <th>State</th>
                        <th>Age</th>
                        <th>Branch / worktree</th>
                        <th>Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reviewWorktrees.rows.map((row) => (
                        <tr key={`${row.action_id}:${row.worktree}`}>
                          <td>#{row.action_id} {row.repo_id}</td>
                          <td><span className="status-chip error">{row.status}</span></td>
                          <td>{row.age_seconds == null ? "unknown" : `${secondsLabel(row.age_seconds)} ago`}</td>
                          <td className="table-mono path-cell">
                            <div>{row.branch || "unknown branch"}</div>
                            <div className="small muted">{row.worktree}</div>
                          </td>
                          <td>{row.failure_reason || "runbook review required"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty-state small muted">No failed or rejected dispatch worktrees are visible in the current dispatch window.</div>
              )}
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Action</th>
                    <th>Repo / target</th>
                    <th>State</th>
                    <th>Wall</th>
                    <th>Session</th>
                    <th>Result</th>
                    <th>Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {dispatchGroups.flatMap(([groupId, rows]) => [
                    <tr key={`group:${groupId}`}>
                      <td colSpan="7" className="table-mono muted">group={groupId} count={rows.length}</td>
                    </tr>,
                    ...rows.map((row) => {
                      const sessionId = row.session?.runtime_session_id || row.session?.session_id || "";
                      const sessionCost = sessionId && costsBySession[sessionId] != null ? `$${Number(costsBySession[sessionId]).toFixed(2)}` : "unknown";
                      return (
                        <tr key={row.id}>
                          <td>
                            <div>#{row.id} {row.kind || row.action_type}</div>
                            <div className="small muted">{row.output_expectation || row.action_type}</div>
                          </td>
                          <td>
                            <div>{row.project || "unknown"}</div>
                            <div className="small muted">{row.target_ref || row.source_refs?.join(" ") || "no target"}</div>
                          </td>
                          <td><span className={`status-chip ${row.status === "completed" ? "ok" : row.status === "failed" || row.status === "rejected" ? "error" : "warn"}`}>{row.status}</span></td>
                          <td>{durationLabel(row.claimed_at || row.created_at, row.completed_at)}</td>
                          <td className="table-mono">{sessionId || "unknown"}</td>
                          <td>{row.result_ref || row.failure_reason || row.audit_refs?.join(" ") || "pending"}</td>
                          <td>{sessionCost}</td>
                        </tr>
                      );
                    })
                  ])}
                </tbody>
              </table>
            </div>
            {dispatchesData.dispatches.length === 0 && !dispatchesData.degraded ? (
              <div className="empty-state small muted">No dispatch lifecycle rows match the current repo filter.</div>
            ) : null}
          </section>
          <section className="cockpit-section live-section" id="takeup">
            <div className="title-row">
              <h3 className="section-title">Takeup</h3>
              {tweaks.alwaysShowSources ? <SourceTruthTag source="pg://sprintctl" /> : null}
            </div>
            <DegradedSourceBanner message={takeupData.degraded?.message} />
            {effectiveSprintMode !== "active" ? (
              <div className="empty-state small muted">Takeup is only tracked in the Active view for a concrete repo sprint.</div>
            ) : (
              <>
                <div className="item-list">
                  {takeupData.active_takeups.map((takeup, index) => (
                    <div key={`${takeup.actor}:${takeup.instance_id || index}`} className="item-card">
                      <div className="title-row">
                        <strong>{takeup.actor}</strong>
                        <span className="small muted">{takeup.instance_id || "no-instance"}</span>
                      </div>
                      <div className="small muted">taken_up={takeup.taken_up_at}</div>
                    </div>
                  ))}
                </div>
                {selectedRepo === "ALL" ? (
                  <div className="empty-state small muted">Takeup is shown only for a concrete repo sprint, not the ALL view.</div>
                ) : takeupData.active_takeups.length === 0 && takeupData.released_takeups.length === 0 ? (
                  <div className="empty-state small muted">No takeup activity is recorded for the selected sprint.</div>
                ) : null}
              </>
            )}
          </section>
          <CockpitStatusBar repoId={selectedRepo} refreshedAt={refreshedAt} health={health} pollMultiplier={pollMultiplier} costSummary={costData.summary} dispatcherPause={dispatcherPauseData} />
        </div>
      </section>

      <aside className="cockpit-pane">
        <div className="cockpit-paneInner">
          <section className="cockpit-section">
            <div className="title-row">
              <h2 className="pane-title">Right Feed</h2>
              <span className="small muted">polling v1</span>
            </div>
          </section>
          <section className="cockpit-section feed-primary" id="outcomes">
            <div className="title-row">
              <h3 className="section-title">Outcomes & Review</h3>
              {tweaks.alwaysShowSources ? (
                <SourceTruthTag source={selectedRepo === "ALL" ? "artifact:audit/<repo>" : `artifact:audit/${selectedRepo}`} />
              ) : null}
            </div>
            <DegradedSourceBanner message={auditData.degraded?.message} />
            <div className="feed-list">
              {auditData.events.map((event) => (
                <div key={event.id} className="feed-item">
                  <div className="title-row">
                    <strong>{event.type}</strong>
                    <span className="small muted">{event.ts}</span>
                  </div>
                  <div>{event.summary}</div>
                  <div className="small muted">{event.source} / {event.actor}</div>
                </div>
              ))}
            </div>
            {selectedRepo === "ALL" ? (
              <div className="empty-state small muted">Audit feed activates after choosing a concrete repo.</div>
            ) : auditData.events.length === 0 && !auditData.degraded ? (
              <div className="empty-state small muted">No audit events were found in the current lookback window.</div>
            ) : null}
          </section>
          <section className="cockpit-section feed-secondary" id="events">
            <div className="title-row">
              <h3 className="section-title">Sprint Event Feed</h3>
              {tweaks.alwaysShowSources ? <SourceTruthTag source="pg://sprintctl" /> : null}
            </div>
            <div className="feed-list">
              {eventsData.events.map((event) => (
                <div key={`${event.repo_id}:${event.id}`} className="feed-item">
                  <div className="title-row">
                    <strong>{event.event_type}</strong>
                    <span className="small muted">{event.created_at}</span>
                  </div>
                  <div className="small muted">
                    repo={event.repo_id} sprint=#{event.sprint_id} actor={event.actor}
                  </div>
                </div>
              ))}
            </div>
            {eventsData.events.length === 0 ? (
              <div className="empty-state small muted">No sprint events match the current repo filter.</div>
            ) : null}
          </section>
          <section className="cockpit-section" id="tweaks">
            <TweaksPanel
              tweaks={tweaks}
              pollMultiplier={pollMultiplier}
              onChange={(patch) => setTweaks((current) => ({ ...current, ...patch }))}
              onRefreshAll={loadAll}
            />
          </section>
        </div>
      </aside>
    </div>
  );
}
