// Node module customization hook that lets `node --test` import project .js
// files containing JSX without a build step. Next's own bundled SWC binary
// (already a transitive dependency of `next`) does the transform, so no new
// dependency is added just for tests. Only local, non-node_modules .js files
// are touched; everything else (react, node:*, etc.) passes through
// unchanged. See tests/README.md for how to enable this for `node --test`.
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

let transformSync;

export async function load(url, context, nextLoad) {
  if (url.startsWith("file://") && url.endsWith(".js") && !url.includes("/node_modules/")) {
    if (!transformSync) {
      ({ transformSync } = await import("next/dist/build/swc/index.js"));
    }
    const filename = fileURLToPath(url);
    const source = await readFile(filename, "utf8");
    const { code } = transformSync(source, {
      filename,
      jsc: {
        parser: { syntax: "ecmascript", jsx: true },
        target: "es2020",
        transform: { react: { runtime: "automatic", importSource: "react" } }
      },
      module: { type: "es6" }
    });
    return { format: "module", source: code, shortCircuit: true };
  }
  return nextLoad(url, context);
}
