#!/usr/bin/env python3
"""OpenCode 2.0.32 ascending transcript pagination and active/inbox probe."""
import base64,json,pathlib,re,secrets,socket,subprocess,tempfile,threading,time,urllib.error,urllib.parse,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
BINARY="/nix/store/9ysv2ynpka84idp745mcd8l0ayc2f102-opencode-2.0.32/bin/opencode"
DENY=[{"action":"*","resource":"*","effect":"deny"}]
def need(ok,msg):
 if not ok:raise AssertionError(msg)
def port():
 s=socket.socket();s.bind(("127.0.0.1",0));p=s.getsockname()[1];s.close();return p
root=pathlib.Path(tempfile.mkdtemp(prefix="opencode-pagination-active-",dir="/tmp"))
for n in ("home","config","data","state","cache","work"):(root/n).mkdir(mode=0o700)
race_started=threading.Event();active_started=threading.Event();race_release=threading.Event();active_release=threading.Event();provider_inputs=[]
class Provider(BaseHTTPRequestHandler):
 protocol_version="HTTP/1.1"
 def do_POST(self):
  req=json.loads(self.rfile.read(int(self.headers.get("content-length","0"))))
  serialized=json.dumps(req.get("messages",[]))
  matches=re.findall(r"BASE-TURN-[0-9]{2}|RACE-HOLD|ACTIVE-HOLD|ACTIVE-QUEUED",serialized)
  marker=matches[-1] if matches else "OTHER"
  provider_inputs.append(marker)
  if marker=="RACE-HOLD":race_started.set();race_release.wait(25)
  if marker=="ACTIVE-HOLD":active_started.set();active_release.wait(25)
  chunks=[{"id":"local","object":"chat.completion.chunk","created":1,"model":"fake","choices":[{"index":0,"delta":{"role":"assistant","content":"synthetic reply: "+marker},"finish_reason":None}]},{"id":"local","object":"chat.completion.chunk","created":1,"model":"fake","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}]
  raw=("".join("data: "+json.dumps(c)+"\n\n" for c in chunks)+"data: [DONE]\n\n").encode()
  try:
   self.send_response(200);self.send_header("Content-Type","text/event-stream");self.send_header("Content-Length",str(len(raw)));self.send_header("Connection","close");self.end_headers();self.wfile.write(raw)
  except (BrokenPipeError,ConnectionResetError):pass
 def log_message(self,*a):pass
provider=ThreadingHTTPServer(("127.0.0.1",port()),Provider);threading.Thread(target=provider.serve_forever,daemon=True).start()
(root/"work"/"opencode.json").write_text(json.dumps({"model":"mock/fake","provider":{"mock":{"npm":"@ai-sdk/openai-compatible","name":"synthetic","options":{"baseURL":f"http://127.0.0.1:{provider.server_address[1]}/v1","apiKey":"synthetic-only"},"models":{"fake":{"name":"Fake","limit":{"context":128000,"output":4096}}}}}}))
password=secrets.token_urlsafe(32);auth="Basic "+base64.b64encode(f"opencode:{password}".encode()).decode();env={"PATH":"/run/current-system/sw/bin:/usr/bin:/bin","HOME":str(root/"home"),"XDG_CONFIG_HOME":str(root/"config"),"XDG_DATA_HOME":str(root/"data"),"XDG_STATE_HOME":str(root/"state"),"XDG_CACHE_HOME":str(root/"cache"),"OPENCODE_SERVER_PASSWORD":password}
p=port();origin=f"http://127.0.0.1:{p}";server=subprocess.Popen([BINARY,"serve","--hostname","127.0.0.1","--port",str(p)],env=env,cwd=str(root/"work"),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def call(method,path,body=None,query=None):
 url=origin+path
 if query:url+="?"+urllib.parse.urlencode(query)
 req=urllib.request.Request(url,method=method,data=None if body is None else json.dumps(body).encode(),headers={"Authorization":auth,"Content-Type":"application/json"})
 try:
  with urllib.request.urlopen(req,timeout=5) as r:
   raw=r.read();return r.status,json.loads(raw) if raw else None
 except urllib.error.HTTPError as e:
  raw=e.read()
  try:v=json.loads(raw) if raw else None
  except ValueError:v=None
  return e.code,v
try:
 info=None
 for _ in range(120):
  try:
   st,v=call("GET","/api/info")
   if st==200:info=v;break
  except (OSError,urllib.error.URLError):pass
  if server.poll() is not None:raise RuntimeError("server exited before readiness")
  time.sleep(.1)
 need(info and info.get("version")=="2.0.32","pinned version mismatch")
 def create(title):
  st,v=call("POST","/api/session",{"title":title,"location":{"directory":str(root/"work")},"model":{"providerID":"mock","id":"fake"},"permissions":DENY});need(st==200,"session create failed");return v["data"]["id"]
 def prompt(sid,mid,text,delivery=None):
  b={"id":mid,"text":text}
  if delivery:b["delivery"]=delivery
  st,v=call("POST",f"/api/session/{sid}/prompt",b);need(st==200,"prompt failed");return v
 def messages(sid,query=None):
  st,v=call("GET",f"/api/session/{sid}/message",query=query);need(st==200 and isinstance(v.get("data"),list),f"message read failed: {st} {v}");return v
 def wait(sid,pred,timeout=8):
  end=time.time()+timeout
  while time.time()<end:
   rows=messages(sid)["data"]
   if pred(rows):return rows
   time.sleep(.03)
  raise AssertionError("transcript condition timed out")
 def wait_idle(sid,outcome=None):return wait(sid,lambda rs:any(r.get("type")=="idle" and (outcome is None or r.get("outcome")==outcome) for r in rs),timeout=12)
 def page(sid,cursor=None):
  q={"limit":50}
  if cursor is None:q["order"]="asc"
  else:q["cursor"]=cursor
  return messages(sid,q)
 result={"version":info["version"],"observations":{}}
 sid=create("pagination-order-asc")
 input_ids=[]
 for i in range(18):
  mid=f"msg_base_{i:02d}";marker=f"BASE-TURN-{i:02d}";input_ids.append(mid)
  prompt(sid,mid,marker)
  rows=wait(sid,lambda rs,m=marker:any(r.get("type")=="assistant" and m in json.dumps(r) for r in rs))
  need(any(r.get("type")=="idle" for r in rows),"base turn lacks idle record")
 p1=page(sid);p1rows=p1["data"]; cursor=(p1.get("cursor") or {}).get("next")
 need(len(p1rows)==50 and isinstance(cursor,str),"asc first page/cursor unexpected")
 cursor_order_status,cursor_order_error=call("GET",f"/api/session/{sid}/message",query={"limit":50,"order":"asc","cursor":cursor})
 need(cursor_order_status==400 and (cursor_order_error or {}).get("_tag")=="InvalidCursorError","cursor plus order negative control did not reject")
 p2=page(sid,cursor);p2rows=p2["data"]; cursor2=(p2.get("cursor") or {}).get("next")
 p3=page(sid,cursor2) if cursor2 else {"data":[],"cursor":{"next":None}}
 base_user_order=[r.get("id") for r in p1rows+p2rows if r.get("type")=="user" and r.get("id") in input_ids]
 need(base_user_order==input_ids,"order=asc did not return base inputs in creation order")
 base_ids={r.get("id") for r in p1rows+p2rows}
 need(len(base_ids)==54 and len(p2rows)==4 and len(p3["data"])==0,"baseline asc pagination did not total 54 as 50/4/0")
 # Add a running user after page one; replay the opaque next cursor while active and after terminal.
 prompt(sid,"msg_race_hold","RACE-HOLD")
 need(race_started.wait(8),"race provider call did not start")
 active_snapshot=call("GET","/api/session/active")[1]
 race_page_active=page(sid,cursor)["data"]
 race_release.set()
 terminal_rows=wait_idle(sid)
 race_page_terminal=page(sid,cursor)["data"]
 ids_active={r.get("id") for r in race_page_active};ids_terminal={r.get("id") for r in race_page_terminal}
 result["observations"]["ascending_pagination"]={"baseline_page_counts":[len(p1rows),len(p2rows),len(p3["data"])],"baseline_total_rows":len(base_ids),"cursor_plus_order_status":cursor_order_status,"cursor_plus_order_error_tag":cursor_order_error.get("_tag"),"first_page_user_ids_in_creation_order":[i for i in base_user_order[:16]],"oldest_input_on_first_page":input_ids[0] in {r.get("id") for r in p1rows},"last_input_on_second_page":input_ids[-1] in {r.get("id") for r in p2rows},"same_cursor_page2_count_while_active":len(race_page_active),"same_cursor_page2_count_after_terminal":len(race_page_terminal),"same_cursor_page2_identity_set_stable":ids_active==ids_terminal,"same_cursor_page2_identity_set_changed":ids_active!=ids_terminal,"page2_active_known_inputs":[r.get("id") for r in race_page_active if r.get("type")=="user" and r.get("id") in input_ids+["msg_race_hold"]],"page2_terminal_known_inputs":[r.get("id") for r in race_page_terminal if r.get("type")=="user" and r.get("id") in input_ids+["msg_race_hold"]],"page2_includes_race_user_while_active":any(r.get("id")=="msg_race_hold" for r in race_page_active),"page2_includes_race_user_after_terminal":any(r.get("id")=="msg_race_hold" for r in race_page_terminal),"active_map_during_race":{"data_count":len(active_snapshot.get("data",{})),"entry_types":sorted({v.get("type") for v in active_snapshot.get("data",{}).values()})}}
 # Demonstrate active map absence while a queued item remains in inbox after interruption.
 qsid=create("active-empty-with-inbox")
 prompt(qsid,"msg_active_hold","ACTIVE-HOLD");need(active_started.wait(8),"active hold provider did not start")
 prompt(qsid,"msg_active_queued","ACTIVE-QUEUED","queue")
 before_inbox=call("GET",f"/api/session/{qsid}/inbox")[1]["data"]
 active_before=call("GET","/api/session/active")[1]
 int_status,int_response=call("POST",f"/api/session/{qsid}/interrupt")
 # wait for interrupted terminal; previous completed turn rows are in a different session.
 terminal=wait_idle(qsid,"interrupted")
 active_after=call("GET","/api/session/active")[1]
 after_inbox=call("GET",f"/api/session/{qsid}/inbox")[1]["data"]
 time.sleep(2.0)
 active_after_delay=call("GET","/api/session/active")[1]
 result["observations"]["active_empty_with_pending_inbox"]={"inbox_id_before_present":any(r.get("id")=="msg_active_queued" for r in before_inbox),"active_count_before_interrupt":len(active_before.get("data",{})),"interrupt_status":int_status,"interrupt_response":int_response,"terminal_idle_outcome":[r.get("outcome") for r in terminal if r.get("type")=="idle"],"inbox_id_after_terminal_present":any(r.get("id")=="msg_active_queued" for r in after_inbox),"queued_id_in_transcript":any(r.get("type")=="user" and r.get("id")=="msg_active_queued" for r in terminal),"active_count_after_terminal":len(active_after.get("data",{})),"active_count_after_2s":len(active_after_delay.get("data",{}))}
 need(result["observations"]["ascending_pagination"]["same_cursor_page2_count_while_active"]==5 and result["observations"]["ascending_pagination"]["same_cursor_page2_count_after_terminal"]==7 and result["observations"]["ascending_pagination"]["same_cursor_page2_identity_set_changed"],"cursor stability observation mismatch")
 need(result["observations"]["active_empty_with_pending_inbox"]["inbox_id_before_present"] and result["observations"]["active_empty_with_pending_inbox"]["inbox_id_after_terminal_present"] and result["observations"]["active_empty_with_pending_inbox"]["active_count_after_terminal"]==0,"active/inbox pending control mismatch")
 result["isolation"]={"network_unshared":True,"loopback_fake_provider":True,"temporary_home_xdg":True,"synthetic_password_not_recorded":True,"no_real_credentials":True}
 print(json.dumps(result,sort_keys=True,indent=2))
finally:
 race_release.set();active_release.set();server.terminate()
 try:server.wait(timeout=4)
 except subprocess.TimeoutExpired:server.kill();server.wait()
 provider.shutdown();provider.server_close()
