"use client";

export function TweaksPanel({ tweaks, onChange, pollMultiplier, onRefreshAll }) {
  return (
    <section className="tweaks-shell">
      <div className="title-row">
        <h3 className="section-title">Tweaks</h3>
        <span className="small muted">poll x{pollMultiplier}</span>
      </div>
      <div className="tweaks-grid">
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={tweaks.compact}
            onChange={(event) => onChange({ compact: event.target.checked })}
          />
          <span>compact density</span>
        </label>
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={tweaks.alwaysShowSources}
            onChange={(event) => onChange({ alwaysShowSources: event.target.checked })}
          />
          <span>always show source tags</span>
        </label>
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={tweaks.pollAll}
            onChange={(event) => onChange({ pollAll: event.target.checked })}
          />
          <span>auto-poll all sources</span>
        </label>
        <label className="field">
          <span className="small muted">feed page size</span>
          <select
            value={tweaks.eventLimit}
            onChange={(event) => onChange({ eventLimit: Number(event.target.value) })}
          >
            <option value="10">10</option>
            <option value="20">20</option>
            <option value="50">50</option>
          </select>
        </label>
      </div>
      <div className="tweaks-actions">
        <button className="mode-button" type="button" onClick={onRefreshAll}>
          Refresh all
        </button>
      </div>
    </section>
  );
}
