export function ok(payload) {
  return Response.json(payload);
}

export function errorPayload(message, source, details = {}) {
  return {
    message,
    source,
    ...details
  };
}

export function parseRepoId(request) {
  return getSearchParams(request).get("repo_id") || "ALL";
}

export function parseEnumParam(request, name, allowed, fallback) {
  const raw = getSearchParams(request).get(name);
  if (raw == null || raw === "") {
    return fallback;
  }
  if (!allowed.includes(raw)) {
    throw new Error(`${name} must be one of: ${allowed.join(", ")}`);
  }
  return raw;
}

export function parseIntParam(request, name, fallback) {
  const raw = getSearchParams(request).get(name);
  if (raw == null || raw === "") {
    return fallback;
  }
  const value = Number(raw);
  if (!Number.isInteger(value)) {
    throw new Error(`${name} must be an integer`);
  }
  return value;
}

export function encodeCursor(value) {
  if (value == null) {
    return null;
  }
  return Buffer.from(JSON.stringify(value), "utf8").toString("base64url");
}

export function decodeCursor(raw) {
  if (!raw) {
    return null;
  }
  return JSON.parse(Buffer.from(raw, "base64url").toString("utf8"));
}

export function getSearchParams(request) {
  if (request.nextUrl?.searchParams) {
    return request.nextUrl.searchParams;
  }
  return new URL(request.url).searchParams;
}
