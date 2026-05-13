import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { getConfig } from "./env.js";

function expandHome(value, homeDir) {
  if (value === "~") {
    return homeDir;
  }
  if (value.startsWith("~/")) {
    return path.join(homeDir, value.slice(2));
  }
  return value;
}

function isInside(child, parent) {
  const rel = path.relative(parent, child);
  return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel));
}

export function resolvePauseFile(config = getConfig(), env = process.env) {
  const homeDir = env.HOME || os.homedir();
  const raw = config.dispatcherPauseFile || path.join(homeDir, ".local", "state", "actionq-dispatcher", "PAUSED");
  const expanded = expandHome(raw, homeDir);
  const pauseFile = path.resolve(expanded);
  if (!config.dispatcherPauseFileExplicit) {
    const allowedRoot = path.resolve(homeDir, ".local", "state", "actionq-dispatcher");
    if (!isInside(pauseFile, allowedRoot)) {
      throw new Error(`dispatcher pause file must stay under ${allowedRoot} unless COCKPIT_DISPATCHER_PAUSE_FILE is set`);
    }
  }
  return pauseFile;
}

export async function readDispatcherPause(config = getConfig(), env = process.env) {
  const pauseFile = resolvePauseFile(config, env);
  try {
    const stat = await fs.stat(pauseFile);
    return {
      paused: true,
      pause_file: pauseFile,
      updated_at: stat.mtime.toISOString()
    };
  } catch (error) {
    if (error?.code !== "ENOENT") {
      throw error;
    }
    return {
      paused: false,
      pause_file: pauseFile,
      updated_at: null
    };
  }
}

export async function setDispatcherPause(paused, config = getConfig(), env = process.env) {
  if (typeof paused !== "boolean") {
    throw new Error("paused must be a boolean");
  }
  const pauseFile = resolvePauseFile(config, env);
  if (paused) {
    await fs.mkdir(path.dirname(pauseFile), { recursive: true });
    const tmpFile = `${pauseFile}.${process.pid}.${Date.now()}.tmp`;
    await fs.writeFile(tmpFile, `paused by cockpit at ${new Date().toISOString()}\n`, { flag: "wx" });
    await fs.rename(tmpFile, pauseFile);
  } else {
    try {
      await fs.unlink(pauseFile);
    } catch (error) {
      if (error?.code !== "ENOENT") {
        throw error;
      }
    }
  }
  return readDispatcherPause(config, env);
}
