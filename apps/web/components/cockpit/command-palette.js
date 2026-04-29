"use client";

import { useMemo, useState } from "react";

function matches(entry, query) {
  const haystack = `${entry.label} ${entry.meta || ""}`.toLowerCase();
  return haystack.includes(query.toLowerCase());
}

export function CommandPalette({ entries, onPick, open, onClose }) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    if (!query) {
      return entries.slice(0, 12);
    }
    return entries.filter((entry) => matches(entry, query)).slice(0, 12);
  }, [entries, query]);

  if (!open) {
    return null;
  }

  return (
    <div className="palette-backdrop" role="presentation" onClick={onClose}>
      <div
        className="palette-shell"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="palette-head">
          <strong>Command Palette</strong>
          <span className="small muted">repo and sprint jump</span>
        </div>
        <input
          autoFocus
          className="palette-input"
          type="text"
          value={query}
          placeholder="Filter repos or sprints"
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              onClose();
            }
          }}
        />
        <div className="palette-results">
          {filtered.map((entry) => (
            <button
              key={entry.id}
              className="palette-item"
              type="button"
              onClick={() => {
                onPick(entry);
                onClose();
              }}
            >
              <div className="title-row">
                <strong>{entry.label}</strong>
                <span className="status-chip">{entry.kind}</span>
              </div>
              <div className="small muted">{entry.meta}</div>
            </button>
          ))}
          {filtered.length === 0 ? <div className="empty-state small muted">No repo or sprint matches.</div> : null}
        </div>
      </div>
    </div>
  );
}
