const CACHE = globalThis.__AGENTOPS_COCKPIT_CACHE__ || new Map();

if (!globalThis.__AGENTOPS_COCKPIT_CACHE__) {
  globalThis.__AGENTOPS_COCKPIT_CACHE__ = CACHE;
}

export function getCached(key) {
  const entry = CACHE.get(key);
  if (!entry) {
    return null;
  }
  if (entry.expiresAt <= Date.now()) {
    CACHE.delete(key);
    return null;
  }
  return entry.value;
}

export function setCached(key, value, ttlMs) {
  CACHE.set(key, { value, expiresAt: Date.now() + ttlMs });
  return value;
}
