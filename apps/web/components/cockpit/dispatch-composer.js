"use client";

export function DispatchComposer({ repoId, sprintId, disabledReason }) {
  return (
    <section className="dispatch-shell" aria-disabled="true">
      <div className="title-row">
        <div>
          <h3 className="section-title">Dispatch Composer</h3>
          <div className="small muted">
            repo={repoId} sprint={sprintId || "none"}
          </div>
        </div>
        <span className="status-chip warn">blocked</span>
      </div>
      <div className="dispatch-grid">
        <label className="field">
          <span className="small muted">Work item</span>
          <input disabled type="text" value="" placeholder="Select or enter work item id" readOnly />
        </label>
        <label className="field">
          <span className="small muted">Harness</span>
          <input disabled type="text" value="" placeholder="claude | codex | opencode" readOnly />
        </label>
        <label className="field">
          <span className="small muted">Prompt</span>
          <textarea disabled rows="4" value="" placeholder="Dispatch payload remains disabled until actionq-server exists." readOnly />
        </label>
      </div>
      <div className="empty-state small muted">{disabledReason}</div>
      <button className="dispatch-button" type="button" disabled>
        Queue dispatch
      </button>
    </section>
  );
}
