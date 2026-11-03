#!/usr/bin/env python3
"""Qualify frozen terminal observer on OpenCode 2.0.32; no egress or real credentials."""
import base64,hashlib,importlib.util,json,pathlib,secrets,socket,subprocess,tempfile,threading,time,urllib.error,urllib.parse,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
MODULE_SHA256="4d9f05e108540ea49db62923c59696b77a3eca05333c37e2f4d6b6ed5096d1a0"
MODULE_PATH=pathlib.Path("/tmp/fixture/opencode_v2.py")
MODULE=None
BINARY="/nix/store/9ysv2ynpka84idp745mcd8l0ayc2f102-opencode-2.0.32/bin/opencode"
DENY=[{"action":"*","resource":"*","effect":"deny"}]
def need(ok,msg):
 if not ok:raise AssertionError(msg)
def port():
 s=socket.socket();s.bind(("127.0.0.1",0));p=s.getsockname()[1];s.close();return p
root=pathlib.Path(tempfile.mkdtemp(prefix="opencode-terminal-client-",dir="/tmp"))
for n in ("home","config","data","state","cache","work"):(root/n).mkdir(mode=0o700)
held={"INTERRUPT":threading.Event(),"QUEUED":threading.Event(),"FOREIGN":threading.Event()};release={k:threading.Event() for k in held}; provider_inputs=[]
class Provider(BaseHTTPRequestHandler):
 protocol_version="HTTP/1.1"
 def do_POST(self):
  req=json.loads(self.rfile.read(int(self.headers.get("content-length","0"))));text=json.dumps(req.get("messages",[]))
  matches=[(text.rfind(m),m) for m in held if m in text]
  marker=max(matches)[1] if matches else "SUCCESS"
  provider_inputs.append(marker)
  if marker in held:held[marker].set();release[marker].wait(20)
  chunks=[{"id":"local","object":"chat.completion.chunk","created":1,"model":"fake","choices":[{"index":0,"delta":{"role":"assistant","content":"synthetic reply: "+marker},"finish_reason":None}]},{"id":"local","object":"chat.completion.chunk","created":1,"model":"fake","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}]
  raw=("".join("data: "+json.dumps(c)+"\n\n" for c in chunks)+"data: [DONE]\n\n").encode()
  try:self.send_response(200);self.send_header("Content-Type","text/event-stream");self.send_header("Content-Length",str(len(raw)));self.send_header("Connection","close");self.end_headers();self.wfile.write(raw)
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
 module_path=MODULE_PATH;MODULE=str(module_path)
 src=module_path.read_bytes();module_sha=hashlib.sha256(src).hexdigest();need(module_sha==MODULE_SHA256,"mounted module digest mismatch")
 spec=importlib.util.spec_from_file_location("terminal_v2_under_test",MODULE);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 client=mod.OpenCodeV2(origin,"opencode",password,timeout=5);directory=str(root/"work")
 def create(title,model_id="mock/fake"):return client.create_session(title,directory,model_id,DENY)
 def wait_idle(sid,outcome=None):
  for _ in range(300):
   st,v=call("GET",f"/api/session/{sid}/message");rows=(v or {}).get("data",[])
   if any(r.get("type")=="idle" and (outcome is None or r.get("outcome")==outcome) for r in rows):return rows
   time.sleep(.04)
  raise AssertionError("terminal idle timeout")
 def capture_rows(sid):
  rows=[];cursor=None;seen=set()
  for _ in range(100):
   query={"limit":50}
   if cursor is None:query["order"]="asc"
   else:query["cursor"]=cursor
   st,page=call("GET",f"/api/session/{sid}/message",query=query)
   need(st==200 and isinstance(page.get("data"),list) and isinstance(page.get("cursor"),dict),"independent transcript page invalid")
   rows.extend(page["data"]);cursor=page["cursor"].get("next")
   if cursor is None:return rows
   need(isinstance(cursor,str) and cursor not in seen,"independent transcript cursor invalid")
   seen.add(cursor)
  raise AssertionError("independent transcript pagination exceeded")
 def independent_interval(sid):
  rows=capture_rows(sid)
  canonical=json.dumps(rows,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
  idle=[row for row in rows if row.get("type")=="idle"]
  need(len(idle)==1,"independent transcript does not have exactly one idle")
  users=[row for row in rows if row.get("type")=="user"]
  need(len(users)==1,"independent transcript must have one user row")
  return {"row_count":len(rows),"ordered_types":[row.get("type") for row in rows],"terminal_id":idle[0]["id"],
    "user_id":users[0]["id"],"user_text_sha256":hashlib.sha256(users[0]["text"].encode()).hexdigest(),
    "interval_sha256":hashlib.sha256(canonical.encode()).hexdigest()}
 def check_independent(observation,capture):
  return observation.get("terminal_id")==capture["terminal_id"] and observation.get("interval_sha256")==capture["interval_sha256"]
 def check_producer(observation,sid,pid,text,capture):
  expected=hashlib.sha256(text.encode()).hexdigest()
  return (observation.get("session_id")==sid and observation.get("prompt_id")==pid==capture["user_id"]
    and observation.get("text_sha256")==expected==capture["user_text_sha256"])
 def report(observation,sid,pid,text,capture):
  return {"status":observation.get("status"),"outcome":observation.get("outcome"),
    "session_id_matches_created":observation.get("session_id")==sid,
    "prompt_id_matches_submitted_and_transcript":observation.get("prompt_id")==pid==capture.get("user_id"),
    "text_sha256_matches_submitted_and_transcript":observation.get("text_sha256")==hashlib.sha256(text.encode()).hexdigest()==capture.get("user_text_sha256"),
    "terminal_id":observation.get("terminal_id"),"interval_sha256":observation.get("interval_sha256"),
    "terminal_id_and_interval_match_independent_rows":check_independent(observation,capture)}
 def submit(sid,pid,text):return client.submit_prompt(sid,pid,text)
 def observe(sid,pid,text,model_id="mock/fake"):
  return client.observe_terminal(sid,pid,hashlib.sha256(text.encode()).hexdigest(),directory,model_id,DENY)
 result={"version":info["version"],"module_sha256":module_sha,"cases":{}}
 # Stable success: method internally takes two snapshots; repeated external call should match.
 sid=create("success");submit(sid,"msg_success","SUCCESS-INPUT");wait_idle(sid,"succeeded")
 success_capture=independent_interval(sid)
 success1=observe(sid,"msg_success","SUCCESS-INPUT");success2=observe(sid,"msg_success","SUCCESS-INPUT")
 success_fields=check_producer(success1,sid,"msg_success","SUCCESS-INPUT",success_capture)
 result["cases"]["success"]={"first":report(success1,sid,"msg_success","SUCCESS-INPUT",success_capture),"repeat_matches_first":success2==success1,"independent_capture":{k:success_capture[k] for k in ("row_count","ordered_types","interval_sha256")},"producer_fields_match_transcript":success_fields}
 need(success1.get("status")=="terminal-observed" and success1.get("outcome")=="succeeded" and success2==success1 and check_independent(success1,success_capture) and success_fields,"success terminal/producer/digest mismatch")
 # No matching provider route should produce failed idle; qualify that transcript shape.
 fsid=create("failure","mock/no-route");submit(fsid,"msg_failure","FAILURE-INPUT");wait_idle(fsid,"failed")
 failure_capture=independent_interval(fsid)
 failure=observe(fsid,"msg_failure","FAILURE-INPUT","mock/no-route")
 failure_fields=check_producer(failure,fsid,"msg_failure","FAILURE-INPUT",failure_capture)
 result["cases"]["failure"]={"observation":report(failure,fsid,"msg_failure","FAILURE-INPUT",failure_capture),"independent_capture":{k:failure_capture[k] for k in ("row_count","ordered_types","interval_sha256")},"producer_fields_match_transcript":failure_fields}
 need(failure.get("status")=="terminal-observed" and failure.get("outcome")=="failed" and check_independent(failure,failure_capture) and failure_fields,"failure terminal/producer/digest mismatch")
 # Active turn is not terminal; after interruption, terminal outcome is observed.
 isid=create("interrupted");submit(isid,"msg_interrupt","INTERRUPT");need(held["INTERRUPT"].wait(8),"interrupt provider did not hold")
 while_active=observe(isid,"msg_interrupt","INTERRUPT");interrupt=client.interrupt_session(isid);wait_idle(isid,"interrupted")
 interrupt_capture=independent_interval(isid)
 after_interrupt=observe(isid,"msg_interrupt","INTERRUPT")
 interrupt_fields=check_producer(after_interrupt,isid,"msg_interrupt","INTERRUPT",interrupt_capture)
 result["cases"]["interruption"]={"active_observation":while_active,"interrupt_ack":interrupt,"terminal_observation":report(after_interrupt,isid,"msg_interrupt","INTERRUPT",interrupt_capture),"independent_capture":{k:interrupt_capture[k] for k in ("row_count","ordered_types","interval_sha256")},"producer_fields_match_transcript":interrupt_fields}
 need(while_active=={"status":"active"} and interrupt.get("interrupted") is True and after_interrupt.get("status")=="terminal-observed" and after_interrupt.get("outcome")=="interrupted" and check_independent(after_interrupt,interrupt_capture) and interrupt_fields,"interrupted terminal/producer/digest mismatch")
 # Queued inbox keeps terminal result unknown even after active turn is interrupted.
 qsid=create("same-session-queue");submit(qsid,"msg_queued_active","QUEUED");need(held["QUEUED"].wait(8),"queued-case provider did not hold")
 st,ack=call("POST",f"/api/session/{qsid}/prompt",{"id":"msg_queued_successor","text":"QUEUED-SUCCESSOR","delivery":"queue"});need(st==200,"queue prompt ack failed")
 queue_active=observe(qsid,"msg_queued_active","QUEUED")
 qinterrupt=client.interrupt_session(qsid);wait_idle(qsid,"interrupted")
 queue_after=observe(qsid,"msg_queued_active","QUEUED")
 inbox=(call("GET",f"/api/session/{qsid}/inbox")[1] or {}).get("data",[])
 result["cases"]["same_session_queued"]={"active_observation":queue_active,"interrupt_ack":qinterrupt,"after_interrupt_observation":queue_after,"queued_id_still_in_inbox":any(r.get("id")=="msg_queued_successor" for r in inbox)}
 need(queue_active=={"status":"active"} and queue_after=={"status":"unknown"} and result["cases"]["same_session_queued"]["queued_id_still_in_inbox"],"queued terminal should be unknown")
 # A's stable terminal observation is not contaminated by B's pending queue.
 foreign=create("foreign-queue-owner");submit(foreign,"msg_foreign_active","FOREIGN-HOLD");need(held["FOREIGN"].wait(8),"foreign provider did not hold")
 st,_=call("POST",f"/api/session/{foreign}/prompt",{"id":"msg_foreign_queued","text":"FOREIGN-QUEUED","delivery":"queue"});need(st==200,"foreign queue prompt ack failed")
 foreign_inbox=(call("GET",f"/api/session/{foreign}/inbox")[1] or {}).get("data",[])
 unrelated=create("unrelated-success");submit(unrelated,"msg_unrelated","UNRELATED-SUCCESS");wait_idle(unrelated,"succeeded")
 unrelated_capture=independent_interval(unrelated)
 unrelated_observation=observe(unrelated,"msg_unrelated","UNRELATED-SUCCESS")
 unrelated_fields=check_producer(unrelated_observation,unrelated,"msg_unrelated","UNRELATED-SUCCESS",unrelated_capture)
 result["cases"]["foreign_session_queue"]={"foreign_queue_present":any(r.get("id")=="msg_foreign_queued" for r in foreign_inbox),"unrelated_terminal":report(unrelated_observation,unrelated,"msg_unrelated","UNRELATED-SUCCESS",unrelated_capture),"independent_capture":{k:unrelated_capture[k] for k in ("row_count","ordered_types","interval_sha256")},"producer_fields_match_transcript":unrelated_fields}
 need(result["cases"]["foreign_session_queue"]["foreign_queue_present"] and unrelated_observation.get("status")=="terminal-observed" and unrelated_observation.get("outcome")=="succeeded" and check_independent(unrelated_observation,unrelated_capture) and unrelated_fields,"foreign session/producer/digest mismatch")
 result["isolation"]={"network_unshared":True,"loopback_fake_provider":True,"temporary_home_xdg":True,"synthetic_password_not_recorded":True,"no_real_provider_credentials":True}
 print(json.dumps(result,sort_keys=True,indent=2))
finally:
 for e in release.values():e.set()
 server.terminate()
 try:server.wait(timeout=4)
 except subprocess.TimeoutExpired:server.kill();server.wait()
 provider.shutdown();provider.server_close()
