export function CockpitStatusBar({ repoId, refreshedAt, health, pollMultiplier, costSummary, dispatcherPause }) {
  const costToken = costSummary
    ? `cost-today=$${Number(costSummary.total_cost_usd || 0).toFixed(2)} sessions=${costSummary.sessions || 0}`
    : "cost-today=unknown";
  const pauseToken = dispatcherPause?.degraded
    ? "dispatcher-pause=unknown"
    : `dispatcher-pause=${dispatcherPause?.paused ? "on" : "off"}`;
  return (
    <footer className="status-bar">
      <span>repo={repoId}</span>
      <span>refresh={refreshedAt || "pending"}</span>
      <span>pg={health.pg} actionq={health.actionq} audit={health.audit}</span>
      <span>{pauseToken}</span>
      <span>{costToken}</span>
      <span>poll=x{pollMultiplier}</span>
    </footer>
  );
}
