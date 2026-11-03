"""Dormant OpenCode 2.0.32 session transport; not wired to the adapter."""

import base64
import http.client
import hashlib
import json
import math
import posixpath
import re
import urllib.error
import urllib.parse
import urllib.request


class V2Error(Exception):
    """A sanitized transport or binding failure; never contains server output."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OpenCodeV2:
    MAX_RESPONSE = 1024 * 1024
    MAX_PAGES = 100
    PAGE_SIZE = 50

    def __init__(self, url, username, password, timeout=5):
        try:
            parsed = urllib.parse.urlsplit(url)
            port = parsed.port
        except (TypeError, ValueError):
            raise V2Error("invalid server origin") from None
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
                or not port or parsed.username or parsed.password
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            raise V2Error("invalid server origin")
        self.origin = f"http://127.0.0.1:{port}"
        self.authorization = "Basic " + base64.b64encode(
            f"{username}:{password}".encode()).decode()
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def _request(self, method, path, query=None, body=None, *, empty_ok=False):
        url = self.origin + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        payload = None if body is None else json.dumps(body, separators=(",", ":")).encode()
        headers = {"Authorization": self.authorization, "Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                if empty_ok:
                    if response.status != 204 or response.read(1):
                        raise V2Error("unexpected server response")
                    return {}
                if response.status != 200 or response.headers.get_content_type() != "application/json":
                    raise V2Error("unexpected server response")
                raw = response.read(self.MAX_RESPONSE + 1)
            if len(raw) > self.MAX_RESPONSE:
                raise V2Error("response too large")
            result = json.loads(raw)
        except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError):
            raise V2Error("server request failed") from None
        if not isinstance(result, dict):
            raise V2Error("invalid response envelope")
        return result

    @staticmethod
    def _id(value):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", value):
            raise V2Error("invalid session identity")
        return value

    @staticmethod
    def _binding(directory, model_id, permissions):
        if (not isinstance(directory, str) or not directory.startswith("/")
                or "\0" in directory or posixpath.normpath(directory) != directory
                or not isinstance(model_id, str) or model_id.count("/") != 1
                or not all(part and part == part.strip() and not any(c.isspace() or c == "\0" for c in part)
                           for part in model_id.split("/"))
                or not isinstance(permissions, list)
                or any(not isinstance(rule, dict) or set(rule) != {"action", "resource", "effect"}
                       or any(not isinstance(rule[k], str) or not rule[k] for k in rule)
                       or rule["effect"] not in ("allow", "deny", "ask") for rule in permissions)):
            raise V2Error("invalid session binding")
        provider, model = model_id.split("/")
        return {"location": {"directory": directory},
                "model": {"providerID": provider, "id": model}, "permissions": permissions}

    def create_session(self, title, directory, model_id, permissions):
        if not isinstance(title, str) or not title:
            raise V2Error("invalid session title")
        binding = self._binding(directory, model_id, permissions)
        data = self._request("POST", "/api/session", body={"title": title, **binding}).get("data")
        if not isinstance(data, dict) or data.get("title") != title:
            raise V2Error("invalid created session")
        sid = self._id(data.get("id"))
        self._validate(data, binding)
        return sid

    def get_session(self, session_id):
        sid = self._id(session_id)
        data = self._request("GET", "/api/session/" + sid).get("data")
        if not isinstance(data, dict) or data.get("id") != sid:
            raise V2Error("invalid session response")
        return data

    @staticmethod
    def _validate(data, binding):
        model = data.get("model")
        expected_model = binding["model"]
        model_ok = (isinstance(model, dict)
                    and set(model) <= {"providerID", "id", "variant"}
                    and model.get("providerID") == expected_model["providerID"]
                    and model.get("id") == expected_model["id"]
                    and model.get("variant", "default") == "default")
        if (not model_ok or data.get("location") != binding["location"]
                or data.get("permissions") != binding["permissions"]):
            raise V2Error("session binding mismatch")

    def validate_session(self, session_id, directory, model_id, permissions):
        self._validate(self.get_session(session_id), self._binding(directory, model_id, permissions))

    def find_sessions(self, title, directory):
        if not isinstance(title, str) or not title or not isinstance(directory, str) or not directory.startswith("/"):
            raise V2Error("invalid discovery criteria")
        cursor = None
        seen = set()
        matches = []
        for _ in range(self.MAX_PAGES):
            query = {"search": title, "directory": directory, "limit": self.PAGE_SIZE}
            if cursor is not None:
                query["cursor"] = cursor
            page = self._request("GET", "/api/session", query=query)
            rows, paging = page.get("data"), page.get("cursor")
            if not isinstance(rows, list) or not isinstance(paging, dict) or "next" not in paging:
                raise V2Error("invalid discovery page")
            for row in rows:
                if not isinstance(row, dict):
                    raise V2Error("invalid discovery page")
                location = row.get("location")
                if (not isinstance(location, dict) or not isinstance(location.get("directory"), str)
                        or not isinstance(row.get("title"), str)):
                    raise V2Error("invalid discovery page")
                if row["title"] == title and location.get("directory") == directory:
                    matches.append(self._id(row.get("id")))
            cursor = paging["next"]
            if cursor is None:
                if len(matches) > 1:
                    raise V2Error("ambiguous session identity")
                return matches
            if not isinstance(cursor, str) or not cursor or cursor in seen:
                raise V2Error("invalid discovery cursor")
            seen.add(cursor)
        raise V2Error("discovery page limit exceeded")

    def submit_prompt(self, session_id, prompt_id, text):
        """Send once; callers must persist uncertainty before calling this method."""
        sid, pid = self._id(session_id), self._id(prompt_id)
        if not pid.startswith("msg_") or not isinstance(text, str) or not text:
            raise V2Error("invalid prompt")
        data = self._request("POST", f"/api/session/{sid}/prompt",
                             body={"id": pid, "text": text}).get("data")
        payload = data.get("payload") if isinstance(data, dict) else None
        timestamp = data.get("time") if isinstance(data, dict) else None
        created = timestamp.get("created") if isinstance(timestamp, dict) else None
        if (not isinstance(data, dict) or data.get("id") != pid or data.get("sessionID") != sid
                or data.get("type") != "user" or not isinstance(payload, dict)
                or payload != {"text": text} or data.get("delivery") not in ("steer", "queue")
                or isinstance(created, bool) or not isinstance(created, (int, float))):
            raise V2Error("invalid prompt acknowledgement")
        return {"id": pid, "session_id": sid, "sha256": hashlib.sha256(text.encode()).hexdigest()}

    def observe_admission(self, session_id, prompt_id, text_sha256):
        """Observe a text-only input, or return unknown; absence never authorizes retry.

        Inbox validation is deliberately restricted to user inputs; other
        variants are uncertainty, not evidence that an input is absent.
        """
        sid, pid = self._id(session_id), self._id(prompt_id)
        if not pid.startswith("msg_") or not isinstance(text_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", text_sha256):
            raise V2Error("invalid prompt digest")
        found = []
        inbox = self._request("GET", f"/api/session/{sid}/inbox").get("data")
        if not isinstance(inbox, list):
            raise V2Error("invalid inbox")
        inbox_ids = set()
        for item in inbox:
            if (not isinstance(item, dict) or not isinstance(item.get("id"), str)
                    or item.get("sessionID") != sid or item.get("type") != "user"
                    or not isinstance(item.get("payload"), dict)
                    or not isinstance(item["payload"].get("text"), str)):
                raise V2Error("invalid inbox")
            if item["id"] in inbox_ids:
                raise V2Error("duplicate input identity")
            inbox_ids.add(item["id"])
            if item["id"] == pid:
                if set(item["payload"]) != {"text"}:
                    raise V2Error("conflicting input payload")
                found.append(("inbox", item["payload"]["text"]))
        cursor, seen, message_ids = None, set(), set()
        for _ in range(self.MAX_PAGES):
            query = {"limit": self.PAGE_SIZE}
            if cursor is not None:
                query["cursor"] = cursor
            page = self._request("GET", f"/api/session/{sid}/message", query=query)
            rows, paging = page.get("data"), page.get("cursor")
            if not isinstance(rows, list) or not isinstance(paging, dict) or "next" not in paging:
                raise V2Error("invalid message page")
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not isinstance(row.get("type"), str):
                    raise V2Error("invalid message page")
                if row["id"] in message_ids:
                    raise V2Error("duplicate message identity")
                message_ids.add(row["id"])
                if row["id"] == pid:
                    if row["type"] != "user" or not isinstance(row.get("text"), str):
                        raise V2Error("conflicting input identity")
                    found.append(("message", row["text"]))
            cursor = paging["next"]
            if cursor is None:
                break
            if not isinstance(cursor, str) or not cursor or cursor in seen:
                raise V2Error("invalid message cursor")
            seen.add(cursor)
        else:
            raise V2Error("message page limit exceeded")
        if any(hashlib.sha256(text.encode()).hexdigest() != text_sha256 for _, text in found):
            raise V2Error("conflicting input payload")
        return {"status": "observed" if found else "unknown", "id": pid, "session_id": sid,
                "sha256": text_sha256, "sources": [source for source, _ in found]}

    def interrupt_session(self, session_id):
        """Request interruption; acknowledgement is not terminal evidence."""
        sid = self._id(session_id)
        response = self._request("POST", f"/api/session/{sid}/interrupt", query={"resume": "false"})
        if not isinstance(response.get("interrupted"), bool):
            raise V2Error("invalid interrupt acknowledgement")
        return {"status": "acknowledged", "interrupted": response["interrupted"]}

    def request_pending_deletion(self, session_id, prompt_id):
        """Request queue removal; only later readback can show its effect."""
        sid, pid = self._id(session_id), self._id(prompt_id)
        if not pid.startswith("msg_"):
            raise V2Error("invalid prompt")
        self._request("DELETE", f"/api/session/{sid}/inbox/{pid}", empty_ok=True)
        return {"status": "acknowledged"}

    def _active(self, sid):
        data = self._request("GET", "/api/session/active").get("data")
        if not isinstance(data, dict):
            raise V2Error("invalid active sessions")
        if sid not in data:
            return False
        row = data[sid]
        if not isinstance(row, dict) or row.get("type") != "running":
            raise V2Error("unknown active session state")
        return True

    def empty_session_observed(self, session_id):
        """Read-only empty-session observation; not an atomic exclusion fence."""
        sid = self._id(session_id)
        for _ in range(2):
            if self._active(sid):
                return False
            inbox = self._request("GET", f"/api/session/{sid}/inbox").get("data")
            if not isinstance(inbox, list):
                raise V2Error("invalid inbox")
            if inbox:
                return False
            seen, cursor = set(), None
            for _ in range(self.MAX_PAGES):
                query = {"limit": self.PAGE_SIZE}
                if cursor is not None:
                    query["cursor"] = cursor
                page = self._request("GET", f"/api/session/{sid}/message", query=query)
                rows, paging = page.get("data"), page.get("cursor")
                if not isinstance(rows, list) or not isinstance(paging, dict) or "next" not in paging:
                    raise V2Error("invalid message page")
                if rows:
                    return False
                cursor = paging["next"]
                if cursor is None:
                    break
                if not isinstance(cursor, str) or not cursor or cursor in seen:
                    raise V2Error("invalid message cursor")
                seen.add(cursor)
            else:
                raise V2Error("message page limit exceeded")
        inbox = self._request("GET", f"/api/session/{sid}/inbox").get("data")
        if not isinstance(inbox, list):
            raise V2Error("invalid inbox")
        return not inbox and not self._active(sid)

    def _terminal_snapshot(self, sid, binding):
        self._validate(self.get_session(sid), binding)
        if self._active(sid):
            return {"status": "active"}
        inbox = self._request("GET", f"/api/session/{sid}/inbox").get("data")
        if not isinstance(inbox, list):
            raise V2Error("invalid inbox")
        if inbox:
            return {"status": "unknown"}
        rows, ids, cursors, cursor = [], set(), set(), None
        for _ in range(self.MAX_PAGES):
            query = {"limit": self.PAGE_SIZE}
            if cursor is None:
                query["order"] = "asc"
            else:
                query["cursor"] = cursor
            page = self._request("GET", f"/api/session/{sid}/message", query=query)
            batch, paging = page.get("data"), page.get("cursor")
            if not isinstance(batch, list) or not isinstance(paging, dict) or "next" not in paging:
                raise V2Error("invalid message page")
            for row in batch:
                if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                        or row.get("type") not in ("user", "assistant", "idle") or row["id"] in ids):
                    raise V2Error("invalid message page")
                time = row.get("time")
                created = time.get("created") if isinstance(time, dict) else None
                try:
                    valid_time = not isinstance(created, bool) and isinstance(created, (int, float)) and math.isfinite(created)
                except OverflowError:
                    valid_time = False
                if not valid_time:
                    raise V2Error("invalid message time")
                if row["type"] == "user":
                    if set(row) != {"id", "type", "time", "text"} or not isinstance(row.get("text"), str):
                        raise V2Error("unexpected user payload")
                if row["type"] == "assistant":
                    model = row.get("model")
                    if (not isinstance(row.get("agent"), str) or not row["agent"]
                            or not isinstance(row.get("content"), list) or not isinstance(model, dict)
                            or set(model) - {"providerID", "id", "variant"}
                            or model.get("providerID") != binding["model"]["providerID"]
                            or model.get("id") != binding["model"]["id"]
                            or model.get("variant", "default") != "default"):
                        raise V2Error("invalid assistant binding")
                if row["type"] == "idle" and row.get("outcome") not in ("succeeded", "failed", "interrupted"):
                    raise V2Error("invalid idle outcome")
                ids.add(row["id"])
                rows.append(row)
            cursor = paging["next"]
            if cursor is None:
                break
            if not isinstance(cursor, str) or not cursor or cursor in cursors:
                raise V2Error("invalid message cursor")
            cursors.add(cursor)
        else:
            raise V2Error("message page limit exceeded")
        final_inbox = self._request("GET", f"/api/session/{sid}/inbox").get("data")
        if not isinstance(final_inbox, list):
            raise V2Error("invalid inbox")
        if final_inbox:
            return {"status": "unknown"}
        self._validate(self.get_session(sid), binding)
        if self._active(sid):
            return {"status": "active"}
        return {"status": "inactive", "rows": rows}

    def observe_terminal(self, session_id, prompt_id, text_sha256, directory, model_id, permissions):
        """Observe a single-input terminal twice; this is not owner settlement."""
        sid, pid = self._id(session_id), self._id(prompt_id)
        if not pid.startswith("msg_") or not isinstance(text_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", text_sha256):
            raise V2Error("invalid prompt digest")
        binding = self._binding(directory, model_id, permissions)
        first = self._terminal_snapshot(sid, binding)
        if first["status"] != "inactive":
            return {"status": first["status"]}
        rows = first["rows"]
        users = [row for row in rows if row["type"] == "user"]
        idles = [row for row in rows if row["type"] == "idle"]
        if (len(users) != 1 or users[0].get("id") != pid or not isinstance(users[0].get("text"), str)
                or hashlib.sha256(users[0]["text"].encode()).hexdigest() != text_sha256
                or len(idles) != 1 or not rows or rows[0] is not users[0] or rows[-1] is not idles[0]
                or idles[0].get("outcome") not in ("succeeded", "failed", "interrupted")):
            return {"status": "unknown"}
        second = self._terminal_snapshot(sid, binding)
        if second["status"] != "inactive":
            return {"status": second["status"]}
        if rows != second["rows"]:
            return {"status": "unknown"}
        try:
            interval = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            interval_digest = hashlib.sha256(interval.encode()).hexdigest()
        except (TypeError, ValueError, UnicodeError):
            raise V2Error("invalid terminal interval") from None
        return {"status": "terminal-observed", "outcome": idles[0]["outcome"],
                "session_id": sid, "prompt_id": pid, "text_sha256": text_sha256,
                "terminal_id": idles[0]["id"], "interval_sha256": interval_digest,
                "correlation": "single-input-two-snapshot", "atomicity": "not-established"}
