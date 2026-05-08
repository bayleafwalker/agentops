"use client";

import { useState } from "react";

const KINDS = ["implement", "review", "test", "investigate", "document", "custom"];
const HARNESSES = ["claude", "codex", "copilot-cli", "codestral"];

function blankForm() {
  return { kind: "implement", work_item_id: "", title: "", harness: "claude", priority: "normal", model: "", prompt: "" };
}

export function DispatchComposer({ repoId, sprintId, disabledReason }) {
  const [form, setForm] = useState(blankForm());
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  const blocked = !!disabledReason;
  const noSprint = !sprintId;
  const allRepo = repoId === "ALL";
  const inactive = allRepo || noSprint;

  function field(name) {
    return (e) => setForm((f) => ({ ...f, [name]: e.target.value }));
  }

  async function submit(e) {
    e.preventDefault();
    setSubmitting(true);
    setResult(null);
    try {
      const body = {
        repo_id: repoId,
        sprint_id: Number(sprintId),
        work_item_id: form.work_item_id.trim() || null,
        kind: form.kind,
        title: form.title.trim(),
        harness: form.harness,
        priority: form.priority,
        prompt: form.prompt,
        refs: form.work_item_id.trim() ? [form.work_item_id.trim(), `sprint:${sprintId}`] : [`sprint:${sprintId}`]
      };
      if (form.model.trim()) {
        body.model = form.model.trim();
      }
      const res = await fetch("/cockpit/api/dispatch", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body)
      });
      const payload = await res.json();
      setResult({ ok: payload.accepted, source: payload.source, action: payload.action, error: payload.degraded?.message });
      if (payload.accepted) {
        setForm(blankForm());
      }
    } catch (err) {
      setResult({ ok: false, error: err.message });
    } finally {
      setSubmitting(false);
    }
  }

  if (blocked) {
    return (
      <section className="dispatch-shell" aria-disabled="true">
        <div className="title-row">
          <h3 className="section-title">Dispatch Composer</h3>
          <span className="status-chip warn">read-only</span>
        </div>
        <div className="empty-state small muted">{disabledReason}</div>
      </section>
    );
  }

  const holdup = allRepo ? "Select a repo to enable dispatch." : noSprint ? "Select an active sprint to enable dispatch." : null;

  return (
    <section className="dispatch-shell">
      <div className="title-row">
        <div>
          <h3 className="section-title">Dispatch Composer</h3>
          <div className="small muted">repo={repoId} sprint={sprintId || "none"}</div>
        </div>
        {holdup ? <span className="status-chip warn">waiting</span> : <span className="status-chip ok">ready</span>}
      </div>

      {holdup ? (
        <div className="empty-state small muted">{holdup}</div>
      ) : (
        <form className="dispatch-grid" onSubmit={submit}>
          <label className="field">
            <span className="small muted">Kind</span>
            <select value={form.kind} onChange={field("kind")} disabled={submitting}>
              {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
          </label>

          <label className="field">
            <span className="small muted">Work item</span>
            <input type="text" value={form.work_item_id} onChange={field("work_item_id")} placeholder="wi:123" disabled={submitting} />
          </label>

          <label className="field">
            <span className="small muted">Title <span className="required">*</span></span>
            <input type="text" value={form.title} onChange={field("title")} placeholder="One-line goal" required disabled={submitting} />
          </label>

          <label className="field">
            <span className="small muted">Harness</span>
            <select value={form.harness} onChange={field("harness")} disabled={submitting}>
              {HARNESSES.map((h) => <option key={h} value={h}>{h}</option>)}
            </select>
          </label>

          <label className="field">
            <span className="small muted">Priority</span>
            <select value={form.priority} onChange={field("priority")} disabled={submitting}>
              <option value="normal">normal</option>
              <option value="high">high</option>
            </select>
          </label>

          <label className="field">
            <span className="small muted">Model override</span>
            <input type="text" value={form.model} onChange={field("model")} placeholder="leave blank for project default" disabled={submitting} />
          </label>

          <label className="field" style={{ gridColumn: "1 / -1" }}>
            <span className="small muted">Prompt</span>
            <textarea rows="4" value={form.prompt} onChange={field("prompt")} placeholder="Additional context for the dispatched session." disabled={submitting} />
          </label>

          <button className="dispatch-button" type="submit" disabled={submitting || !form.title.trim()}>
            {submitting ? "Queuing…" : "Queue dispatch"}
          </button>

          {result && (
            <div className={`dispatch-result small ${result.ok ? "ok" : "error"}`} style={{ gridColumn: "1 / -1" }}>
              {result.ok
                ? `Accepted via ${result.source}. Action id: ${result.action?.id ?? "—"}`
                : `Rejected: ${result.error || "unknown error"}`}
            </div>
          )}
        </form>
      )}
    </section>
  );
}
