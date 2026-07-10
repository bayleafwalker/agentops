export const WRITE_TOKEN_STORAGE_KEY = "cockpit_write_token";

function defaultStorage() {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage;
}

export function getStoredWriteToken(storage = defaultStorage()) {
  if (!storage) {
    return null;
  }
  try {
    const value = storage.getItem(WRITE_TOKEN_STORAGE_KEY);
    return value && value.trim() ? value.trim() : null;
  } catch {
    return null;
  }
}

export function withWriteToken(headers = {}, storage = defaultStorage()) {
  const token = getStoredWriteToken(storage);
  if (!token) {
    return { ...headers };
  }
  return { ...headers, "x-cockpit-write-token": token };
}
