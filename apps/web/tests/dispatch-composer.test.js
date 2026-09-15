import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { DispatchComposer } from "../components/cockpit/dispatch-composer.js";

const h = createElement;

const RETIRED_REASON =
  "Dispatch is retired (agentops#2409): actionq-server was removed from the cluster on 2026-09-01. " +
  "Dispatch is done by native harness sessions coordinated through sprintctl; see docs/runbooks/maintenance-lane.md.";

test("dispatch composer shows a retired notice and no dispatch control when disabled", () => {
  const html = renderToStaticMarkup(h(DispatchComposer, {
    repoId: "alpha",
    sprintId: 12,
    mode: "active",
    disabledReason: RETIRED_REASON
  }));

  // The write control itself must be gone: no submit button, no form to POST from.
  assert.doesNotMatch(html, /Queue dispatch/);
  assert.doesNotMatch(html, /<form/);

  // A short retired notice pointing at the current path must be shown instead.
  assert.match(html, /retired/i);
  assert.match(html, /maintenance-lane\.md/);
  assert.match(html, /read-only/);
});

test("dispatch composer renders the live form only when nothing disables it (regression guard)", () => {
  const html = renderToStaticMarkup(h(DispatchComposer, {
    repoId: "alpha",
    sprintId: 12,
    mode: "active",
    disabledReason: null
  }));

  assert.match(html, /Queue dispatch/);
  assert.match(html, /<form/);
});
