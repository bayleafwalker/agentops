from __future__ import annotations

import json
from pathlib import Path
import subprocess
import textwrap
import unittest


ROOT = Path(__file__).parents[3]
BUILD_WORKFLOW = ROOT / ".claude" / "workflows" / "vuoro-dispatch-build.js"
VERIFY_WORKFLOW = ROOT / ".claude" / "workflows" / "vuoro-dispatch-verify.js"
MODEL_ROUTING = ROOT / "templates" / "dispatch" / "model-routing.json"


NODE_HARNESS = r"""
const fs = require('fs')
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
const workflowPath = process.argv[1]
const workflowArgs = JSON.parse(process.argv[2])
const failUnit = process.argv[3] || ''
const evidenceMode = process.argv[4] || ''
const events = []

const idsFromBuildPrompt = prompt => [...new Set([...prompt.matchAll(/^- item_id=([0-9]+)/gm)].map(match => match[1]))]
const itemsFromVerifyPrompt = prompt => [...prompt.matchAll(/^- item_id=([0-9]+).*commit_sha=([0-9a-f]+)/gm)]
const closeEvidence = prompt => {
  const match = prompt.match(/<<<UNTRUSTED-DATA\n([\s\S]*?)\nUNTRUSTED-DATA>>>/)
  return match ? JSON.parse(match[1]) : []
}

async function agent(prompt, options) {
  events.push(options.label)
  const parts = options.label.split(':')
  if (parts[0] === 'triage') {
    return {repo: parts[1], unit: parts[2], tier: 'bounded', dispatch_ready: true, rationale: 'stub', concerns: []}
  }
  if (parts[0] === 'build') {
    const ids = idsFromBuildPrompt(prompt)
    return {
      repo: parts[1],
      unit: parts[2],
      items: ids.map((itemId, index) => ({
        item_id: itemId,
        claim_id: String(1000 + Number(itemId)),
        commit_sha: `abcdef${index + 1}`,
        files_changed: [`src/${itemId}.py`],
        verification_summary: 'stubbed targeted pass',
      })),
      shared_constraints: [],
    }
  }
  if (parts[0] === 'verify') {
    const items = itemsFromVerifyPrompt(prompt)
    const failed = parts[2] === failUnit
    return {
      repo: parts[1],
      unit: parts[2],
      results: items.map(match => ({
        item_id: match[1],
        commit_sha: match[2],
        verdict: failed ? 'issues_found' : 'confirmed',
        summary: failed ? 'stubbed defect' : 'stubbed independent pass',
        concerns: failed ? ['stubbed concern'] : [],
      })),
      checks_run: evidenceMode === 'empty' ? [] : [{command: 'stub-test', outcome: failed ? 'failed' : 'passed'}],
      full_suite: evidenceMode === 'empty'
        ? {outcome: 'not_available', reason: 'stubbed missing evidence'}
        : {outcome: failed ? 'failed' : 'passed', reason: 'stub'},
    }
  }
  if (parts[0] === 'publish') {
    return {repo: parts[1], published: true, action: 'pushed', head_sha: 'abcdef1'}
  }
  if (parts[0] === 'close') {
    const evidence = closeEvidence(prompt)
    const audit = prompt.includes('deterministic audit closeout')
    return {
      repo: parts[1],
      results: evidence.map(item => ({
        item_id: item.item_id,
        closed: !audit && item.verdict === 'confirmed',
        action: audit ? 'noted' : (item.verdict === 'confirmed' ? 'done-from-claim' : 'released'),
      })),
    }
  }
  throw new Error(`unexpected agent label ${options.label}`)
}

async function pipeline(collection, ...stages) {
  return Promise.all(collection.map(async (original, index) => {
    let value = original
    for (const stage of stages) value = await stage(value, original, index)
    return value
  }))
}

async function parallel(tasks) {
  return Promise.all(tasks.map(task => task()))
}

const source = fs.readFileSync(workflowPath, 'utf8').replace(/^export const meta =/m, 'const meta =')
const run = new AsyncFunction('args', 'agent', 'pipeline', 'parallel', 'log', 'phase', source)
run(workflowArgs, agent, pipeline, parallel, () => {}, () => {})
  .then(result => process.stdout.write(JSON.stringify({result, events})))
  .catch(error => {
    process.stderr.write(error.stack)
    process.exitCode = 1
  })
"""


def run_workflow(path: Path, args: dict, *, fail_unit: str = "", evidence_mode: str = "") -> dict:
    result = subprocess.run(
        ["node", "-e", NODE_HARNESS, str(path), json.dumps(args), fail_unit, evidence_mode],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


class SavedWorkflowTests(unittest.TestCase):
    def test_canonical_routing_keeps_provider_ladders_asymmetric(self) -> None:
        aliases = json.loads(MODEL_ROUTING.read_text(encoding="utf-8"))["aliases"]

        self.assertEqual(aliases["clerical"]["anthropic"]["model"], "claude-haiku-4-5-20251001")
        self.assertEqual(aliases["fast-build"]["anthropic"]["model"], "claude-sonnet-5")
        self.assertEqual(aliases["fast-build"]["codex"]["model"], "gpt-5.3-codex-spark")
        self.assertEqual(aliases["fast-build"]["codex"]["fallback"], "gpt-5.6-luna")
        self.assertEqual(aliases["standard-build"]["codex"]["model"], "gpt-5.6-terra")
        self.assertEqual(aliases["hard-build"]["codex"]["model"], "gpt-5.6-terra")
        self.assertEqual(aliases["frontier-plan"]["codex"]["model"], "gpt-5.6-sol")
        self.assertEqual(aliases["frontier-review"]["codex"]["model"], "gpt-5.6-sol")

    def test_build_uses_sequential_reasoning_units_and_one_repo_closeout(self) -> None:
        output = run_workflow(
            BUILD_WORKFLOW,
            {
                "items": [
                    {"repo": "example", "item_id": 1, "unit": "api", "tier": "bounded"},
                    {"repo": "example", "item_id": 2, "unit": "storage", "tier": "standard"},
                ]
            },
        )

        self.assertEqual(
            output["events"],
            [
                "build:example:api",
                "build:example:storage",
                "verify:example:api",
                "verify:example:storage",
                "close:example",
            ],
        )
        self.assertEqual(len(output["result"]["results"]), 2)
        self.assertTrue(all(item["closed"] for item in output["result"]["results"]))
        self.assertNotIn("claim_token", json.dumps(output["result"]))

    def test_requested_push_is_withheld_and_close_fails_closed_on_mixed_verdicts(self) -> None:
        output = run_workflow(
            BUILD_WORKFLOW,
            {
                "push": True,
                "items": [
                    {"repo": "example", "item_id": 1, "unit": "api", "tier": "bounded"},
                    {"repo": "example", "item_id": 2, "unit": "storage", "tier": "standard"},
                ],
            },
            fail_unit="storage",
        )

        self.assertNotIn("publish:example", output["events"])
        self.assertEqual(
            output["result"]["publication"],
            [{"repo": "example", "published": False, "action": "withheld-until-entire-repo-batch-clears"}],
        )
        self.assertFalse(any(item["closed"] for item in output["result"]["results"]))
        self.assertEqual(
            {item["verdict"] for item in output["result"]["results"]},
            {"issues_found", "inconclusive"},
        )

    def test_standalone_audit_verifies_units_sequentially_and_only_records_notes(self) -> None:
        output = run_workflow(
            VERIFY_WORKFLOW,
            {
                "mode": "audit",
                "items": [
                    {"repo": "example", "item_id": 1, "commit_sha": "abcdef1", "unit": "api", "tier": "bounded"},
                    {"repo": "example", "item_id": 2, "commit_sha": "abcdef2", "unit": "storage", "tier": "hard"},
                ],
            },
        )

        self.assertEqual(
            output["events"],
            ["verify:example:api", "verify:example:storage", "close:example"],
        )
        self.assertTrue(all(not item["closed"] and item["action"] == "noted" for item in output["result"]["results"]))

    def test_confirmation_without_command_evidence_fails_closed(self) -> None:
        output = run_workflow(
            BUILD_WORKFLOW,
            {"items": [{"repo": "example", "item_id": 1, "tier": "bounded"}]},
            evidence_mode="empty",
        )

        self.assertEqual(output["result"]["results"][0]["verdict"], "inconclusive")
        self.assertFalse(output["result"]["results"][0]["closed"])

    def test_invalid_repo_is_rejected_before_dispatch(self) -> None:
        result = subprocess.run(
            [
                "node",
                "-e",
                NODE_HARNESS,
                str(BUILD_WORKFLOW),
                json.dumps({"items": [{"repo": "../escape", "item_id": 1, "tier": "bounded"}]}),
                "",
                "",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("safe repository directory name", result.stderr)

    def test_workflows_compile_as_async_functions(self) -> None:
        script = textwrap.dedent(
            """
            const fs = require('fs')
            const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
            for (const path of process.argv.slice(1)) {
              const source = fs.readFileSync(path, 'utf8').replace(/^export const meta =/m, 'const meta =')
              new AsyncFunction('args', 'agent', 'pipeline', 'parallel', 'log', 'phase', source)
            }
            """
        )
        subprocess.run(
            ["node", "-e", script, str(BUILD_WORKFLOW), str(VERIFY_WORKFLOW)],
            cwd=ROOT,
            check=True,
        )

    def test_workflows_expose_focused_orchestration_services(self) -> None:
        build_source = BUILD_WORKFLOW.read_text(encoding="utf-8")
        verify_source = VERIFY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("const buildInputService = Object.freeze", build_source)
        self.assertIn("const buildExecutionService = Object.freeze", build_source)
        self.assertIn("const buildPublicationService = Object.freeze", build_source)
        self.assertIn("const verifyInputService = Object.freeze", verify_source)
        self.assertIn("const verificationService = Object.freeze", verify_source)
        self.assertIn("const verificationCloseoutService = Object.freeze", verify_source)


if __name__ == "__main__":
    unittest.main()
