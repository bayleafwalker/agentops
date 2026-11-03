#!/usr/bin/env python3
"""Direct /api/session/active observations for pinned OpenCode 2.0.32.
Run on devbox inside bwrap --unshare-net. All auth/config/provider data synthetic.
"""
import base64, json, pathlib, secrets, socket, subprocess, tempfile, threading, time, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BINARY = "/nix/store/9ysv2ynpka84idp745mcd8l0ayc2f102-opencode-2.0.32/bin/opencode"

def port():
    s=socket.socket(); s.bind(("127.0.0.1",0)); p=s.getsockname()[1]; s.close(); return p

def need(ok, msg):
    if not ok: raise AssertionError(msg)

root=pathlib.Path(tempfile.mkdtemp(prefix="opencode-active-route-",dir="/tmp"))
for name in ("home","config","data","state","cache","work"):
    (root/name).mkdir(mode=0o700)
started={"HELD":threading.Event(),"RETRY":threading.Event()}
release={k:threading.Event() for k in started}
provider_state={"retry_calls":0}
class Provider(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers.get("content-length","0"))))
        text=json.dumps(body.get("messages",[]))
        marker="RETRY" if "RETRY" in text else "HELD" if "HELD" in text else "NORMAL"
        if marker=="RETRY":
            provider_state["retry_calls"]+=1
            started["RETRY"].set()
            # Return transient failures so OpenCode is observed during retry/backoff.
            self.send_response(503); self.send_header("Content-Length","0"); self.send_header("Connection","close"); self.end_headers(); return
        if marker=="HELD":
            started["HELD"].set(); release["HELD"].wait(25)
        content="synthetic reply: "+marker
        chunks=[
          {"id":"local","object":"chat.completion.chunk","created":1,"model":"fake","choices":[{"index":0,"delta":{"role":"assistant","content":content},"finish_reason":None}]},
          {"id":"local","object":"chat.completion.chunk","created":1,"model":"fake","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]},
        ]
        data=("".join("data: "+json.dumps(c)+"\n\n" for c in chunks)+"data: [DONE]\n\n").encode()
        try:
            self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.send_header("Content-Length",str(len(data))); self.send_header("Connection","close"); self.end_headers(); self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError): pass
    def log_message(self,*a): pass
provider=ThreadingHTTPServer(("127.0.0.1",port()),Provider)
threading.Thread(target=provider.serve_forever,daemon=True).start()
(root/"work"/"opencode.json").write_text(json.dumps({"model":"mock/fake","provider":{"mock":{"npm":"@ai-sdk/openai-compatible","name":"synthetic","options":{"baseURL":f"http://127.0.0.1:{provider.server_address[1]}/v1","apiKey":"synthetic-only"},"models":{"fake":{"name":"Fake","limit":{"context":128000,"output":4096}}}}}}))
password=secrets.token_urlsafe(32)
auth="Basic "+base64.b64encode(f"opencode:{password}".encode()).decode()
env={"PATH":"/run/current-system/sw/bin:/usr/bin:/bin","HOME":str(root/"home"),"XDG_CONFIG_HOME":str(root/"config"),"XDG_DATA_HOME":str(root/"data"),"XDG_STATE_HOME":str(root/"state"),"XDG_CACHE_HOME":str(root/"cache"),"OPENCODE_SERVER_PASSWORD":password}
server=None
origin=""
def call(method,path,body=None):
    req=urllib.request.Request(origin+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={"Authorization":auth,"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=4) as r:
            raw=r.read(); return r.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw=e.read()
        try: val=json.loads(raw) if raw else None
        except ValueError: val=None
        return e.code,val

def start():
    global server,origin
    p=port(); origin=f"http://127.0.0.1:{p}"
    server=subprocess.Popen([BINARY,"serve","--hostname","127.0.0.1","--port",str(p)],env=env,cwd=str(root/"work"),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for _ in range(120):
        if server.poll() is not None: raise RuntimeError("server exited")
        try:
            st,val=call("GET","/api/info")
            if st==200: return val
        except Exception: pass
        time.sleep(.1)
    raise RuntimeError("server readiness timeout")

def active(expected_session_id=None):
    st,val=call("GET","/api/session/active")
    data=val.get("data") if isinstance(val,dict) else None
    entries=[]
    if isinstance(data,dict):
        for sid,record in data.items():
            entries.append({"key_matches_expected_session":sid==expected_session_id,
                            "record":record})
    return {"http_status":st,"json_type":type(val).__name__,
            "data_type":type(data).__name__,"data_count":len(data) if isinstance(data,dict) else None,
            "entries":entries}

def create(title):
    st,val=call("POST","/api/session",{"title":title,"location":{"directory":str(root/"work")},"model":{"providerID":"mock","id":"fake"},"permissions":[{"action":"*","resource":"*","effect":"deny"}]})
    need(st==200,"create failed"); return val["data"]["id"]

def prompt(sid,text):
    st,val=call("POST",f"/api/session/{sid}/prompt",{"id":"msg_"+text.lower(),"text":text})
    need(st==200,"prompt failed")

def wait_idle(sid):
    for _ in range(250):
        st,val=call("GET",f"/api/session/{sid}/message")
        rows=(val or {}).get("data",[])
        if any(row.get("type")=="idle" for row in rows): return rows
        time.sleep(.04)
    raise AssertionError("turn did not reach idle")

try:
    info=start(); need(info.get("version")=="2.0.32","wrong pinned version")
    out={"version":info.get("version"),"direct_route":"/api/session/active","observations":{}}
    out["observations"]["idle_initial"]=active()
    need(out["observations"]["idle_initial"]["http_status"]==200 and
         out["observations"]["idle_initial"]["data_count"]==0,
         "idle active map unexpectedly nonempty")
    sid=create("active-held")
    out["observations"]["idle_with_session"]=active(sid)
    need(out["observations"]["idle_with_session"]["http_status"]==200 and
         out["observations"]["idle_with_session"]["data_count"]==0,
         "new idle session appeared in active map")
    prompt(sid,"HELD"); need(started["HELD"].wait(8),"held request never reached provider")
    out["observations"]["held_busy"]=active(sid)
    need(out["observations"]["held_busy"]["data_count"]==1 and
         out["observations"]["held_busy"]["entries"]==[{"key_matches_expected_session":True,"record":{"type":"running"}}],
         "held session missing expected running record")
    interrupt_status,interrupt=call("POST",f"/api/session/{sid}/interrupt")
    for _ in range(100):
        rows=call("GET",f"/api/session/{sid}/message")[1].get("data",[])
        if any(r.get("type")=="idle" and r.get("outcome")=="interrupted" for r in rows): break
        time.sleep(.05)
    out["observations"]["after_interrupt"]=active(sid)
    need(out["observations"]["after_interrupt"]["data_count"]==0,
         "interrupted terminal session remained active")
    out["observations"]["interrupt_ack"]={"status":interrupt_status,"payload":interrupt}
    release["HELD"].set()
    # Retry case: capture active state after server/provider begins the transient-failure loop.
    rsid=create("active-retry"); prompt(rsid,"RETRY")
    need(started["RETRY"].wait(8),"retry request never reached provider")
    retry_deadline=time.time()+5
    while provider_state["retry_calls"] < 2 and time.time() < retry_deadline:
        time.sleep(.05)
    out["observations"]["retrying_busy"]=active(rsid)
    need(out["observations"]["retrying_busy"]["data_count"]==1 and
         out["observations"]["retrying_busy"]["entries"]==[{"key_matches_expected_session":True,"record":{"type":"running"}}],
         "retrying session missing expected running record")
    out["retry_attempts_before_retry_snapshot"]=provider_state["retry_calls"]
    # Interrupt retries to keep fixture bounded; capture terminal result after interrupt.
    ist,ip=call("POST",f"/api/session/{rsid}/interrupt")
    for _ in range(100):
        rows=call("GET",f"/api/session/{rsid}/message")[1].get("data",[])
        if any(r.get("type")=="idle" for r in rows): break
        time.sleep(.05)
    out["observations"]["after_retry_interrupt"]=active(rsid)
    need(out["observations"]["after_retry_interrupt"]["data_count"]==0,
         "interrupted retry session remained active")
    out["observations"]["retry_interrupt_ack"]={"status":ist,"payload":ip}
    out["provider_retry_call_count"]=provider_state["retry_calls"]
    out["isolation"]={"network_unshared":True,"loopback_provider_only":True,"temporary_home_xdg":True,"synthetic_auth_not_recorded":True,"no_real_provider_config":True}
    print(json.dumps(out,sort_keys=True,indent=2))
finally:
    for e in release.values(): e.set()
    if server:
        server.terminate()
        try: server.wait(timeout=4)
        except subprocess.TimeoutExpired: server.kill(); server.wait()
    provider.shutdown(); provider.server_close()
