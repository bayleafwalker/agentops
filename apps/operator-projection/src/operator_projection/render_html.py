"""HTML rendering of operator-projection/v1: the text sections as one element per line, plus the sources envelope."""

from __future__ import annotations

from datetime import datetime
from html import escape

from . import render_text

COVERS = render_text.COVERS | {"sources"}
STYLE = """
:root{--bg:#fbfaf7;--fg:#1f1e1b;--muted:#77736a;--warn:#8a5300;--stale:#b3261e;--rule:#e4e1d8}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161512;--fg:#e9e6de;--muted:#9a958a;--warn:#e0a54a;--stale:#f2867d;--rule:#2e2c27}}
:root[data-theme="dark"]{--bg:#161512;--fg:#e9e6de;--muted:#9a958a;--warn:#e0a54a;--stale:#f2867d;--rule:#2e2c27}
body{background:var(--bg);color:var(--fg);font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;padding-block:20px;padding-inline:16px;margin:0 auto;max-width:120ch}
section{border-top:1px solid var(--rule);padding-block:10px}section:first-of-type{border-top:0}
div{white-space:pre-wrap;overflow-wrap:anywhere}.head{font-weight:700}.sub{color:var(--muted)}.blind{color:var(--warn)}
.stale{color:var(--stale);font-weight:700}details{color:var(--muted)}.wide{overflow-x:auto}td{padding-inline:0 12px;vertical-align:top}
"""


def render(doc: dict, now: datetime | None = None) -> str:
    body = "".join(
        "<section>" + "".join(f'<div class="{cls}">{escape(text)}</div>' for cls, text in lines) + "</section>"
        for lines in render_text.sections(doc, now)
    )
    sources = "".join(
        "<tr>" + "".join(f"<td>{escape(str(v or ''))}</td>" for v in (s["id"], s["transport"], s["ref"], s["revision"], s["observed_at"],
                                                                     s["degraded"] and s["degraded"]["detail"])) + "</tr>"
        for s in doc["sources"]
    )
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>Operator projection</title><style>{STYLE}</style></head><body>{body}"
            f'<details><summary>sources ({len(doc["sources"])})</summary><div class="wide"><table>{sources}</table></div></details></body></html>\n')
