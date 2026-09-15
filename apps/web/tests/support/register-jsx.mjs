// Entry point passed to `node --import` so the jsx-hooks loader is active
// for the whole test run (loader hooks must run in a dedicated thread that
// is registered before the test files are loaded).
import { register } from "node:module";

register("./jsx-hooks.mjs", import.meta.url);
