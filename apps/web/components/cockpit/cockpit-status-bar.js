export function CockpitStatusBar({ repoId, refreshedAt, health, pollMultiplier }) {
  return (
    <footer className="status-bar">
      <span>repo={repoId}</span>
      <span>refresh={refreshedAt || "pending"}</span>
      <span>pg={health.pg} actionq={health.actionq} audit={health.audit}</span>
      <span>poll=x{pollMultiplier}</span>
    </footer>
  );
}
