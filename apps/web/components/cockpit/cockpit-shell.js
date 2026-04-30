"use client";

import { useEffect, useState } from "react";
import { buildCommandPaletteEntries, DEFAULT_TWEAKS, getPollIntervalMs, getVisibilityBackoffMultiplier, pickSprintSelection, SPRINT_VIEW_MODES } from "../../lib/cockpit/client-state.js";
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

async function readJson(url) {
  const response = await fetch(url, { cache: "no-store" });
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

export function CockpitShell() {
  const [reposData, setReposData] = useState({ repos: [], degraded: null });
  const [selectedRepo, setSelectedRepo] = useState("ALL");
  const [selectedMode, setSelectedMode] = useState("active");
  const [selectedSprint, setSelectedSprint] = useState("");
  const [sprintsData, setSprintsData] = useState({ sprints: [], degraded: null });
  const [takeupData, setTakeupData] = useState({ active_takeups: [], released_takeups: [], degraded: null });
  const [claimsData, setClaimsData] = useState({ claims: [], degraded: null });
  const [eventsData, setEventsData] = useState({ events: [], degraded: null });
  const [auditData, setAuditData] = useState({ events: [], degraded: null });
  const [refreshedAt, setRefreshedAt] = useState(null);
  const [fatalError, setFatalError] = useState("");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [visibilityState, setVisibilityState] = useState("visible");
  const [tweaks, setTweaks] = useState(DEFAULT_TWEAKS);

  const pollMultiplier = getVisibilityBackoffMultiplier(visibilityState);
  const effectiveSprintMode = selectedRepo === "ALL" ? "active" : selectedMode;

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
    if (selectedRepo === "ALL" && selectedMode !== "active") {
      setSelectedMode("active");
    }
  }, [selectedMode, selectedRepo]);

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
        if (!cancelled) {
          timer = setTimeout(loadRepos, getPollIntervalMs("repos", document.visibilityState || "visible"));
        }
      }
    }

    loadRepos();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [selectedRepo, visibilityState]);

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
        if (!cancelled) {
          timer = setTimeout(loadPrimary, getPollIntervalMs("primary", document.visibilityState || "visible"));
        }
      }
    }

    loadPrimary();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [effectiveSprintMode, selectedRepo, tweaks.eventLimit, visibilityState]);

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
        if (!cancelled) {
          timer = setTimeout(loadClaims, getPollIntervalMs("claims", document.visibilityState || "visible"));
        }
      }
    }

    loadClaims();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [effectiveSprintMode, selectedRepo, selectedSprint, visibilityState]);

  useEffect(() => {
    if (selectedRepo === "ALL") {
      if (selectedSprint) {
        setSelectedSprint("");
      }
      return;
    }
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
        if (!cancelled) {
          timer = setTimeout(loadSecondary, getPollIntervalMs("secondary", document.visibilityState || "visible"));
        }
      }
    }

    loadSecondary();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [selectedRepo, selectedSprint, tweaks.eventLimit, visibilityState]);

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

  return (
    <div className={`cockpit-pane cockpit-shell ${tweaks.compact ? "compact" : ""}`}>
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
            <p className="small muted">Cmd/Ctrl+K opens repo and sprint jump.</p>
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
                setSelectedMode("active");
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
            <div className="title-row">
              <h2 className="pane-title">Sprint Overview</h2>
              {tweaks.alwaysShowSources ? <SourceTruthTag source="pg://sprintctl" /> : null}
            </div>
            <DegradedSourceBanner message={sprintsData.degraded?.message} />
          </section>
          <section className="cockpit-section">
            <div className="title-row">
              <h3 className="section-title">View Mode</h3>
              <span className="small muted">{selectedRepo}</span>
            </div>
            <div className="mode-toggle" role="tablist" aria-label="Sprint view mode">
              {SPRINT_VIEW_MODES.map((mode) => (
                <button
                  key={mode}
                  className={`mode-button ${effectiveSprintMode === mode ? "active" : ""}`}
                  type="button"
                  disabled={selectedRepo === "ALL" && mode !== "active"}
                  onClick={() => {
                    setSelectedMode(mode);
                    setSelectedSprint("");
                  }}
                >
                  {MODE_LABELS[mode]}
                </button>
              ))}
            </div>
            <div className="section-note small muted">
              {selectedRepo === "ALL"
                ? "ALL stays on Active so the aggregate view remains a live operations surface."
                : effectiveSprintMode === "active"
                  ? "Now view: active repo sprints, claims, takeup, and live work-item posture."
                  : effectiveSprintMode === "backlog"
                    ? "Queue view: planned backlog sprints for this repo, ordered for planning and readiness."
                    : "History view: closed and archived sprint records, including cleanup anomalies."}
            </div>
          </section>
          <section className="cockpit-section">
            <div className="metric-grid">
              <div className="metric-card">
                <div className="metric-value">{sprintsData.sprints.length}</div>
                <div className="small muted">visible sprints</div>
              </div>
              <div className="metric-card">
                <div className="metric-value">{cleanupRequiredCount}</div>
                <div className="small muted">cleanup required</div>
              </div>
              <div className="metric-card">
                <div className="metric-value">{claimsData.claims.length}</div>
                <div className="small muted">active claims</div>
              </div>
              <div className="metric-card">
                <div className="metric-value">{eventsData.events.length}</div>
                <div className="small muted">feed events</div>
              </div>
            </div>
            <div className="section-note small muted">
              {selectedRepo === "ALL"
                ? "ALL aggregates remote repos only."
                : `${sprintsWithItems} sprints with work items, ${emptySprints} currently empty.`}
            </div>
          </section>
          <section className="cockpit-section" id="sprints">
            <div className="title-row">
              <h3 className="section-title">{MODE_LABELS[effectiveSprintMode]} Sprint Tabs</h3>
              <span className="small muted">{selectedRepo}</span>
            </div>
            <div className="repo-list">
              {sprintsData.sprints.map((sprint) => (
                <button
                  key={`${sprint.repo_id}:${sprint.id}`}
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
              ))}
            </div>
            {sprintsData.sprints.length === 0 ? (
              <div className="empty-state small muted">
                No {effectiveSprintMode} remote sprints are visible for this repo filter.
              </div>
            ) : null}
          </section>
          <section className="cockpit-section" id="work-items">
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
          <section className="cockpit-section" id="claims">
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
                        <tr key={row.claim.claim_id}>
                          <td>#{row.claim.work_item_id} {row.claim.item_title}</td>
                          <td>{row.claim.actor}</td>
                          <td className="table-mono">{row.session?.runtime_session_id || "unknown"}</td>
                          <td>{row.session?.heartbeat_at || "unknown"}</td>
                          <td>{row.session?.ttl_seconds ?? "unknown"}</td>
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
          <section className="cockpit-section" id="takeup">
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
          <section className="cockpit-section" id="dispatch">
            <div className="title-row">
              <h3 className="section-title">Dispatch</h3>
              <span className="small muted">write path gated</span>
            </div>
            <DispatchComposer
              repoId={selectedRepo}
              sprintId={effectiveSprintMode === "active" ? selectedSprint : ""}
              disabledReason={
                effectiveSprintMode !== "active"
                  ? "Dispatch is intentionally limited to the Active view so backlog and history stay read-only planning surfaces."
                  : "Dispatch remains disabled in this tranche. The UI is present, but a live POST path depends on actionq-server or an explicitly documented interim bridge."
              }
            />
          </section>
          <CockpitStatusBar repoId={selectedRepo} refreshedAt={refreshedAt} health={health} pollMultiplier={pollMultiplier} />
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
          <section className="cockpit-section" id="outcomes">
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
          <section className="cockpit-section" id="events">
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
            />
          </section>
        </div>
      </aside>
    </div>
  );
}
