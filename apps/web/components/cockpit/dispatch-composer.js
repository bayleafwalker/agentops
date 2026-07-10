"use client";

import { useEffect, useState } from "react";

const EXPECTATIONS = [
  ["implementation", "Implementation"],
  ["review", "Review"],
  ["plan", "Plan / audit event"],
  ["draft-work-items", "Draft work items"],
  ["sprint-proposal", "Sprint proposal"]
];
const HARNESSES = ["claude", "codex", "copilot-cli", "codestral"];

const PROMPT_TEMPLATES = {
  implementation: "Initiate dispatch on sprint scope: implement the assigned work item per project workflow. Deliver working, tested code satisfying the acceptance criteria.",
  review: "Initiate dispatch on sprint scope: review the implementation for correctness, test coverage, and contract compliance.",
  plan: "Initiate dispatch on sprint scope: produce an audit event and plan for the assigned work. Map acceptance criteria to concrete implementation steps.",
  "draft-work-items": "Initiate dispatch on sprint scope: draft structured work item proposals from the current sprint context and backlog.",
  "sprint-proposal": "Initiate dispatch on sprint scope: propose a sprint plan based on current project state and backlog priorities."
};

const TEMPLATE_VALUES = new Set(Object.values(PROMPT_TEMPLATES));

function blankForm() {
  return {
    output_expectation: "implementation",
    no_sprint: false,
    work_item_id: "",
    title: "",
    harness: "claude",
    priority: "normal",
    model: "",
    dispatch_group_id: "",
    prompt: PROMPT_TEMPLATES.implementation
  };
}

function kindForExpectation(expectation) {
  if (expectation === "review") {
    return "review";
  }
  if (expectation === "implementation") {
    return "implement";
  }
  if (expectation === "plan" || expectation === "draft-work-items" || expectation === "sprint-proposal") {
    return "investigate";
  }
  return "custom";
}

function minutesSince(value) {
  const parsed = Date.parse(value || "");
  if (Number.isNaN(parsed)) {
    return null;
  }
  return Math.round((Date.now() - parsed) / 60000);
}

function headroomWarning(headroom, harness, expectation) {
  if (harness !== "codex" && harness !== "claude") {
    return null;
  }
  const provider = headroom?.providers?.[harness];
  if (!provider?.available) {
    return `${harness} headroom unavailable; refresh before dispatching quota-sensitive work.`;
  }
  const ageMinutes = minutesSince(headroom.refreshed_at);
  const ageLabel = ageMinutes == null ? "unknown age" : `${ageMinutes}m old`;
  if (headroom.stale || ageMinutes == null || ageMinutes > 30) {
    return `${harness} headroom is stale (${ageLabel}); refresh before trusting quota signals.`;
  }
  const primaryUsed = harness === "codex"
    ? provider.rate_limit?.primary_window?.used_percent
    : provider.current_window?.used_percent;
  if (Number(primaryUsed) >= 90) {
    return `${harness} 5h window is ${Math.round(Number(primaryUsed))}% used (${ageLabel}).`;
  }
  if (harness === "codex" && expectation === "review" && Number(provider.code_review_rate_limit?.used_percent) >= 90) {
    return `codex review limit is ${Math.round(Number(provider.code_review_rate_limit.used_percent))}% used (${ageLabel}).`;
  }
  return `${harness} headroom refreshed ${ageLabel}.`;
}

function normalizeWorkItemInput(raw) {
  const trimmed = raw.trim();
  if (/^wi:/i.test(trimmed)) {
    return trimmed.slice(trimmed.indexOf(":") + 1).trim();
  }
  return trimmed;
}

export function DispatchComposer({
  repoId,
  sprintId,
  mode,
  disabledReason,
  headroom = null,
  onRefreshHeadroom = null,
  dispatcherPause = null,
  pauseUpdating = false,
  onTogglePause = null,
  onDispatched = null,
  externalWorkItemId = null
}) {
  const [form, setForm] = useState(blankForm());
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (externalWorkItemId != null && externalWorkItemId !== "") {
      setForm((f) => ({ ...f, work_item_id: externalWorkItemId }));
    }
  }, [externalWorkItemId]);

  useEffect(() => {
    const template = PROMPT_TEMPLATES[form.output_expectation];
    if (template && (form.prompt === "" || TEMPLATE_VALUES.has(form.prompt))) {
      setForm((f) => ({ ...f, prompt: template }));
    }
  }, [form.output_expectation]);

  const blocked = !!disabledReason;
  const paused = Boolean(dispatcherPause?.paused);
  const noSprint = !sprintId && mode === "active" && !form.no_sprint;
  const allRepo = repoId === "ALL";
  const quotaNote = headroomWarning(headroom, form.harness, form.output_expectation);

  const normalizedWorkItemId = normalizeWorkItemInput(form.work_item_id);
  const needsWorkItem = form.output_expectation === "implementation" || form.output_expectation === "review";
  const workItemMissing = needsWorkItem && !normalizedWorkItemId;
  const workItemInvalid = normalizedWorkItemId !== "" && !/^\d+$/.test(normalizedWorkItemId);

  function field(name) {
    return (e) => setForm((f) => ({ ...f, [name]: e.target.value }));
  }

  const pauseButton = onTogglePause ? (
    <button
      className="mode-button pause-toggle"
      type="button"
      onClick={() => onTogglePause(!paused)}
      disabled={pauseUpdating}
    >
      {pauseUpdating ? "Updating" : paused ? "Resume dispatcher" : "Pause dispatcher"}
    </button>
  ) : null;

  async function submit(e) {
    e.preventDefault();
    if (paused) {
      setResult({ ok: false, error: "Dispatcher is paused." });
      return;
    }
    setSubmitting(true);
    setResult(null);
    try {
      const targetSprintId = form.no_sprint || !sprintId ? null : Number(sprintId);
      const refs = [];
      const resolvedWorkItemId = normalizeWorkItemInput(form.work_item_id);
      if (resolvedWorkItemId) {
        refs.push(resolvedWorkItemId);
      }
      if (targetSprintId != null) {
        refs.push(`sprint:${targetSprintId}`);
      }
      const body = {
        repo_id: repoId,
        sprint_id: targetSprintId,
        work_item_id: resolvedWorkItemId || null,
        kind: kindForExpectation(form.output_expectation),
        output_expectation: form.output_expectation,
        title: form.title.trim(),
        harness: form.harness,
        priority: form.priority,
        prompt: form.prompt,
        refs
      };
      if (form.model.trim()) {
        body.model = form.model.trim();
      }
      if (form.dispatch_group_id.trim()) {
        body.dispatch_group_id = form.dispatch_group_id.trim();
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
        onDispatched?.();
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
          <span className={`status-chip ${paused ? "error" : "warn"}`}>{paused ? "paused" : "read-only"}</span>
        </div>
        <div className={`dispatch-result small ${paused ? "error" : "ok"}`}>
          dispatcher={paused ? "paused" : "running"} pause_file={dispatcherPause?.pause_file || "unknown"}
          {pauseButton}
          {dispatcherPause?.degraded ? <div>{dispatcherPause.degraded.message}</div> : null}
        </div>
        <div className="empty-state small muted">{disabledReason}</div>
      </section>
    );
  }

  const holdup = allRepo ? "Select a repo to enable dispatch." : noSprint ? "Select a sprint or choose no-sprint refinement." : null;

  return (
    <section className="dispatch-shell">
      <div className="title-row">
        <div>
          <h3 className="section-title">Dispatch Composer</h3>
          <div className="small muted">repo={repoId} sprint={sprintId || "none"}</div>
        </div>
        {paused ? <span className="status-chip error">paused</span> : holdup ? <span className="status-chip warn">waiting</span> : <span className="status-chip ok">ready</span>}
      </div>
      <div className={`dispatch-result small ${paused ? "error" : "ok"}`}>
        dispatcher={paused ? "paused" : "running"} pause_file={dispatcherPause?.pause_file || "unknown"}
        {pauseButton}
        {dispatcherPause?.degraded ? <div>{dispatcherPause.degraded.message}</div> : null}
      </div>

      {result && (
        <div className={`dispatch-result small ${result.ok ? "ok" : "error"}`}>
          {result.ok
            ? `Queued. Action id: ${result.action?.id ?? "—"} via ${result.source}`
            : `Rejected: ${result.error || "unknown error"}`}
        </div>
      )}

      {holdup ? (
        <div className="empty-state small muted">{holdup}</div>
      ) : (
        <form className="dispatch-grid" onSubmit={submit}>
          <label className="field">
            <span className="small muted">Output</span>
            <select value={form.output_expectation} onChange={field("output_expectation")} disabled={submitting}>
              {EXPECTATIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>

          <label className="field">
            <span className={`small ${workItemMissing ? "text-warn" : workItemInvalid ? "text-danger" : "muted"}`}>
              Work item{needsWorkItem ? " *" : ""}
              {workItemMissing ? " — required for implementation/review" : ""}
              {workItemInvalid ? " — must be numeric" : ""}
            </span>
            <input
              type="text"
              value={form.work_item_id}
              onChange={field("work_item_id")}
              placeholder="item id (e.g. 1234 or wi:1234)"
              disabled={submitting}
            />
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

          {quotaNote ? (
            <div className="dispatch-result small warn" style={{ gridColumn: "1 / -1" }}>
              {quotaNote}
              {onRefreshHeadroom ? (
                <button className="mode-button" type="button" onClick={onRefreshHeadroom} disabled={submitting}>
                  Refresh
                </button>
              ) : null}
            </div>
          ) : null}

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

          <label className="field">
            <span className="small muted">Group id</span>
            <input type="text" value={form.dispatch_group_id} onChange={field("dispatch_group_id")} placeholder="optional dispatch_group_id" disabled={submitting} />
          </label>

          <label className="toggle-row small muted">
            <input
              type="checkbox"
              checked={form.no_sprint}
              onChange={(e) => setForm((f) => ({ ...f, no_sprint: e.target.checked }))}
              disabled={submitting}
            />
            no sprint target
          </label>

          <label className="field" style={{ gridColumn: "1 / -1" }}>
            <span className="small muted">Prompt</span>
            <textarea rows="4" value={form.prompt} onChange={field("prompt")} disabled={submitting} />
          </label>

          <button
            className="dispatch-button"
            type="submit"
            disabled={submitting || paused || !form.title.trim() || workItemInvalid}
          >
            {submitting ? "Queuing…" : "Queue dispatch"}
          </button>
        </form>
      )}
    </section>
  );
}
