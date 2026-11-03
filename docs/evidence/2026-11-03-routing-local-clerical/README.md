# Local worker-fast clerical pilot

On 2026-11-03, four synthetic, one-shot clerical requests were sent sequentially
to the existing workstation `worker-fast` OpenAI-compatible endpoint, with no
tools, temperature 0 and a 512-token cap. The [results](results.json) preserve
the exact prompts, expected JSON values, outputs, token usage and timings. A
strict `json.loads` followed by value equality was the predetermined oracle.
Three of four passed. The filter task returned the correct IDs in a Markdown
code fence, so its output was not valid JSON as requested. All calls completed;
the first took 14.0 seconds and the remaining calls took 0.28–0.34 seconds.
This small pilot supports only these observations, not a general quality or
latency claim. Coordinator review time and repeated-trial variance were not
measured.

The [replay script](replay.py) was run once to verify the recorded prompts and
oracle; it produced the same three strict passes and the same fenced filter
output. It prints responses rather than recording a new scored run.

At the time of the test, the running llama-swap unit used
`/nix/store/0vng2nh39lcqcd9qakv19z4kzn716pqw-config.yaml`, whose SHA-256
`d226e5734251ae4343cdf0d0689da7c563302f5f8b9b315708338a5f3c21204e`
matched `gitops-nixos/modules/system/llm-inference/config.yaml`. That config
names `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`, 65,536 context, one slot, q8_0 KV
cache, Jinja and thinking disabled. The named local file existed and was
17,730,509,792 bytes; its contents were not hashed. Config identity is not
independent attestation of the loaded weights. This complements, rather than
overrides, the separate six-item reasoning pilot.
