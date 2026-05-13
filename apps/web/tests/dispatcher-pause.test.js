import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createGetHandler, createPostHandler } from "../app/cockpit/api/dispatcher/pause/route.js";
import { readDispatcherPause, setDispatcherPause } from "../lib/cockpit/dispatcher-pause.js";

function jsonRequest(url, body) {
  return new Request(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body)
  });
}

test("dispatcher pause route reads and toggles the pause file", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "agentops-pause-"));
  try {
    const config = {
      dispatcherPauseFile: path.join(root, "state", "PAUSED"),
      dispatcherPauseFileExplicit: true
    };
    const env = { HOME: root };
    const GET = createGetHandler({
      readDispatcherPause: () => readDispatcherPause(config, env)
    });
    const POST = createPostHandler({
      setDispatcherPause: (paused) => setDispatcherPause(paused, config, env)
    });

    const initial = await (await GET(new Request("http://localhost/cockpit/api/dispatcher/pause"))).json();
    assert.equal(initial.paused, false);
    assert.equal(initial.updated_at, null);

    const paused = await (await POST(jsonRequest("http://localhost/cockpit/api/dispatcher/pause", { paused: true }))).json();
    assert.equal(paused.paused, true);
    assert.match(await fs.readFile(config.dispatcherPauseFile, "utf8"), /paused by cockpit/);

    const resumed = await (await POST(jsonRequest("http://localhost/cockpit/api/dispatcher/pause", { paused: false }))).json();
    assert.equal(resumed.paused, false);

    const resumedAgain = await (await POST(jsonRequest("http://localhost/cockpit/api/dispatcher/pause", { paused: false }))).json();
    assert.equal(resumedAgain.paused, false);
  } finally {
    await fs.rm(root, { recursive: true, force: true });
  }
});

test("dispatcher pause route rejects invalid payload", async () => {
  const POST = createPostHandler({
    setDispatcherPause: async () => {
      throw new Error("should not write");
    }
  });
  const response = await POST(jsonRequest("http://localhost/cockpit/api/dispatcher/pause", { paused: "yes" }));
  const payload = await response.json();
  assert.equal(response.status, 400);
  assert.match(payload.degraded.message, /paused must be a boolean/);
});
