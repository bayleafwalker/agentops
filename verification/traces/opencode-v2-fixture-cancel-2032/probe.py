#!/usr/bin/env python3
"""Portable synthetic cancellation-branch qualification on OpenCode 2.0.32."""
import base64,hashlib,http.server,importlib.util,json,pathlib,secrets,socket,subprocess,sys,tempfile,threading,time,urllib.error,urllib.parse,urllib.request,shutil
BINARY="/nix/store/9ysv2ynpka84idp745mcd8l0ayc2f102-opencode-2.0.32/bin/opencode"
SOURCE=pathlib.Path("/tmp/fixture")
EXPECTED={"host_adapter":"f963419e2dcf4be2f09982d764ea99216c2f3691ee5f923b19b4d035455bf575","opencode_v2":"be29305b7ec8167495eea1fa8e0bc50b6f8937815466a7dfc00260ecd6848766","validate_vuoro_profiles":"110a7583802157a446fbd327acb06940916d29334a8fa8772d3fa90dd709cd56"}
DENY=[{"action":"*","resource":"*","effect":"deny"}]

def need(ok,msg):
 if not ok:raise AssertionError(msg)
def load(name):
 p=SOURCE/(name+".py");need(hashlib.sha256(p.read_bytes()).hexdigest()==EXPECTED[name],name+" source hash mismatch")
 spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def port():
 s=socket.socket();s.bind(("127.0.0.1",0));p=s.getsockname()[1];s.close();return p

MARKERS=("RUNNING_CANCEL","FOREIGN_ACTIVE","CANCEL_SUCCESS")
held={m:threading.Event() for m in MARKERS};release={m:threading.Event() for m in MARKERS};provider_inputs=[]
class Provider(http.server.BaseHTTPRequestHandler):
 protocol_version="HTTP/1.1"
 daemon_threads=True
 def do_POST(self):
  req=json.loads(self.rfile.read(int(self.headers.get("content-length","0"))));body=json.dumps(req.get("messages",[]))
  found=[(body.rfind(m),m) for m in MARKERS if m in body];marker=max(found)[1] if found else "SUCCESS";provider_inputs.append(marker)
  if marker in held:held[marker].set();release[marker].wait(20)
  chunks=[{"id":"fake","object":"chat.completion.chunk","created":1,"model":"fake","choices":[{"index":0,"delta":{"role":"assistant","content":"synthetic response"},"finish_reason":None}]},{"id":"fake","object":"chat.completion.chunk","created":1,"model":"fake","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}]
  data=("".join("data: "+json.dumps(c)+"\n\n" for c in chunks)+"data: [DONE]\n\n").encode()
  try:
   self.send_response(200);self.send_header("Content-Type","text/event-stream");self.send_header("Content-Length",str(len(data)));self.send_header("Connection","close");self.end_headers();self.wfile.write(data)
  except (BrokenPipeError,ConnectionResetError):pass
 def log_message(self,*args):pass

class Owner:
 def __init__(self,mid,body):
  self.mid=mid;self.receipts=[];self.principals={};self.results=[];self.revoke_keys=set();self.revoke_attempts=[];self.delegation=None;self.run_calls=0
  self.message={"schema":"agent-message/v1","message_id":mid,"recipient":{"principal_id":"iss:devbox:fixture"},"kind":"continue","mode":"request","context":{"item_id":"fixture","predecessor_run_id":"previous"},"body":{"text":body},"sender_principal_id":"iss:workstation:fixture","repo_id":"agentops","inbox_seq":1}
 def agent_register(self,repo,*,instance_id,declaration,idempotency_key):self.principals[instance_id]="iss:devbox:fixture";return {"ok":True}
 def agent_observe(self,*a,**kw):return {"ok":True}
 def message_read(self,repo,*,after_seq,limit,instance_id):
  rows=[] if after_seq>=1 else [dict(self.message,receipts=list(self.receipts))]
  return {"messages":rows,"next_after_seq":1 if rows else after_seq}
 def message_status(self,repo,*,message_id):return {"message":self.message,"receipts":list(self.receipts)}
 def message_receipt(self,repo,*,message_id,instance_id,kind,**fields):
  old=next((x for x in self.receipts if x["kind"]==kind),None)
  if old:
   if kind=="result-linked" and any(old.get(k)!=v for k,v in fields.items()):raise ha.OwnerError("already-resulted")
   return dict(old,replayed=True)
  if kind=="run-linked" and not any(x["kind"]=="accepted" for x in self.receipts):raise ha.OwnerError("not-accepted")
  row={"kind":kind,"instance_id":instance_id,"principal_id":"iss:devbox:fixture",**fields};self.receipts.append(row)
  if kind=="result-linked":self.results.append(row)
  return dict(row,replayed=False)
 def run_register(self,repo,args):self.run_calls+=1;return {"repo_id":repo,"run":{"run_id":"run_"+self.mid}}
 def run_delegate(self,repo,*,run_id,creator_instance_id,operations,ttl_seconds,idempotency_key):
  need(self.principals.get(creator_instance_id)=="iss:devbox:fixture","synthetic principal mismatch")
  self.delegation={"delegation_id":"dlg_"+self.mid,"run_id":run_id,"operations":operations,"expires_at":"2027-01-01T00:00:00Z","revoked":False}
  return {**self.delegation,"token":"vrd_"+"A"*52}
 def run_delegation_get(self,repo,*,delegation_id):return dict(self.delegation)
 def run_delegation_revoke(self,repo,*,delegation_id,reason,idempotency_key):
  self.revoke_attempts.append({"reason":reason,"key":idempotency_key})
  if idempotency_key not in self.revoke_keys:self.revoke_keys.add(idempotency_key);self.delegation["revoked"]=True
  return {"delegation_id":delegation_id,"revoked":True}
 def cancel(self):self.receipts.append({"kind":"cancel-requested","principal_id":"iss:workstation:fixture","reason":"synthetic cancel"})

class Transport:
 permissions=DENY
 def __init__(self,client,origin,auth):self.client=client;self.origin=origin;self.auth=auth;self.interrupt_calls=0;self.delete_calls=0;self.submit_calls=0;self.inspect_statuses=[];self.lose_interrupt=False;self.acks=[]
 def server_version(self):
  req=urllib.request.Request(self.origin+"/api/info",headers={"Authorization":self.auth})
  with urllib.request.urlopen(req,timeout=5) as r:return json.loads(r.read())["version"]
 def create_session(self,*a):return self.client.create_session(*a)
 def find_sessions(self,*a):return self.client.find_sessions(*a)
 def validate_session(self,*a):return self.client.validate_session(*a)
 def empty_session_observed(self,*a):return self.client.empty_session_observed(*a)
 def submit_prompt(self,*a):self.submit_calls+=1;return self.client.submit_prompt(*a)
 def observe_admission(self,*a):return self.client.observe_admission(*a)
 def observe_terminal(self,*a):return self.client.observe_terminal(*a)
 def inspect_cancellation_target(self,*a):
  result=self.client.inspect_cancellation_target(*a);self.inspect_statuses.append(result.get("status"));return result
 def interrupt_session(self,sid):
  self.interrupt_calls+=1;ack=self.client.interrupt_session(sid);self.acks.append(ack)
  if self.lose_interrupt:self.lose_interrupt=False;raise RuntimeError("synthetic lost interrupt response after accepted response")
  return ack
 def request_pending_deletion(self,sid,pid):
  self.delete_calls+=1;return self.client.request_pending_deletion(sid,pid)

def main():
 global ha
 ha=load("host_adapter");v2=load("opencode_v2");root=pathlib.Path(tempfile.mkdtemp(prefix="opencode-v2-cancel-",dir="/tmp"));server=None;provider=None
 try:
  for n in ("home","config","data","state","cache","work"): (root/n).mkdir(mode=0o700)
  provider=http.server.ThreadingHTTPServer(("127.0.0.1",0),Provider);threading.Thread(target=provider.serve_forever,daemon=True).start()
  cfg_model={"model":"mock/fake","provider":{"mock":{"npm":"@ai-sdk/openai-compatible","name":"loopback only","options":{"baseURL":f"http://127.0.0.1:{provider.server_address[1]}/v1","apiKey":"synthetic-only"},"models":{"fake":{"name":"Fake","limit":{"context":128000,"output":4096}}}}}}
  (root/"work"/"opencode.json").write_text(json.dumps(cfg_model));(root/"config"/"opencode").mkdir(mode=0o700);(root/"config"/"opencode"/"opencode.json").write_text(json.dumps(cfg_model))
  user="opencode";password=secrets.token_urlsafe(32);auth="Basic "+base64.b64encode((user+":"+password).encode()).decode();p=port();origin=f"http://127.0.0.1:{p}"
  env={"PATH":"/run/current-system/sw/bin:/usr/bin:/bin","HOME":str(root/"home"),"XDG_CONFIG_HOME":str(root/"config"),"XDG_DATA_HOME":str(root/"data"),"XDG_STATE_HOME":str(root/"state"),"XDG_CACHE_HOME":str(root/"cache"),"OPENCODE_SERVER_USERNAME":user,"OPENCODE_SERVER_PASSWORD":password}
  server=subprocess.Popen([BINARY,"serve","--hostname","127.0.0.1","--port",str(p)],env=env,cwd=str(root/"work"),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  def call(method,path,body=None):
   req=urllib.request.Request(origin+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={"Authorization":auth,"Content-Type":"application/json"})
   try:
    with urllib.request.urlopen(req,timeout=6) as r:
     data=r.read();return r.status,json.loads(data) if data else None
   except urllib.error.HTTPError as e:
    data=e.read()
    try:v=json.loads(data) if data else None
    except ValueError:v=None
    return e.code,v
  info=None
  for _ in range(100):
   if server.poll() is not None:raise RuntimeError("OpenCode exited before readiness")
   try:
    status,info=call("GET","/api/info")
    if status==200 and info.get("version")=="2.0.32":break
   except Exception:pass
   time.sleep(.1)
  need(info and info.get("version")=="2.0.32","pinned server version mismatch")
  client=v2.OpenCodeV2(origin,user,password,timeout=8)
  delete_requests=[0];original_delete=client.request_pending_deletion
  def counted_delete(*args):
   delete_requests[0]+=1;return original_delete(*args)
  client.request_pending_deletion=counted_delete
  class Harness:
   prompts=[]
   def health(self):return True
  def boot(name,mid,body,*,owner=None,transport=None):
   folder=root/name;folder.mkdir(exist_ok=True);runs=folder/"runs";runs.mkdir(exist_ok=True)
   profile=folder/"profile.json";profile.write_text(json.dumps({"schema_version":"vuoro-client-profile/v1","id":"fixture","revision":1,"source_environment_id":"devbox","target":{"environment_id":"synthetic-owner","environment_class":"test","endpoint":"http://fixture.invalid"},"credential_ref":"file:/never-read","required_authorities":["work:read","work:evidence"],"production_endpoint_denied":True}))
   authority={"standing_read":{"operations":["work.run.resolve-v1"]},"scoped_execution":{"repositories":["agentops"],"operations":["work.effect.attempt-open-v1","agentops.dispatch.publish-v1",ha.LAUNCH_OPERATION],"publication_operation":"agentops.dispatch.publish-v1","max_ttl_seconds":3600},"explicit_approval":[{"transition":"rollout-resume","operations":["rollout.resume-*"],"approvers":["fixture"],"max_approval_age_seconds":3600}]}
   (folder/"environment.json").write_text(json.dumps({"schema_version":"environment-record/v1","id":"devbox","roles":["unattended-agent-host"],"authority":authority}))
   policy={"enabled":True,"launches_enabled":True,"run_delegation_qualified":True,"allowed_senders":["iss:workstation:fixture"],"allowed_repos":["agentops"],"kinds":["continue"],"max_concurrent":2,"environment_record":str(folder/"environment.json"),"harness":{"harness_id":"opencode","harness_build":"2.0.32","model_id":"mock/fake","recipe_id":"inbox-continue-v1","observed_profile":{"sandbox":"fixture-only"}}}
   (folder/"policy.json").write_text(json.dumps(policy))
   owner=owner or Owner(mid,body);transport=transport or Transport(client,origin,auth);state=ha.State(folder/"db",clock=lambda:1800000000.0)
   config=ha.Config(poll_interval=10,directory=str(root/"work"),run_root=str(runs),adapter_profile=str(profile))
   adapter=ha.Adapter(owner=owner,harness=Harness(),state=state,policy_path=folder/"policy.json",config=config,clock=lambda:1800000000.0,log=lambda _:None,
     experimental_v2_session_transport=transport,experimental_v2_prompt_admission=True,experimental_v2_terminal_completion=True,experimental_v2_cancellation=True)
   return {"folder":folder,"runs":runs,"owner":owner,"transport":transport,"state":state,"adapter":adapter}
  def row(c):return c["state"].get("agentops",c["owner"].mid)
  def tick_until(c,predicate,label,limit=240):
   for _ in range(limit):
    c["adapter"].tick();r=row(c)
    if predicate(r):return r
    time.sleep(.05)
   raise AssertionError(label+" timeout")

  # Sole running prompt: server accepts interrupt; response is lost; restart must not repeat it.
  running=boot("running_cancel","msg_cancel_running","RUNNING_CANCEL");running["adapter"].tick()
  need(held["RUNNING_CANCEL"].wait(8),"provider did not hold running cancellation target")
  r=row(running);need(r["prompt_admission"]=="admitted" and running["transport"].inspect_cancellation_target(r["session_id"],r["prompt_id"],r["prompt_sha256"],json.loads(r["v2_launch_binding"])["directory"],"mock/fake",DENY)["status"]=="running","target not solely running")
  running["owner"].cancel();running["transport"].lose_interrupt=True;running["adapter"].tick();r=row(running)
  need(r["v2_interrupt_state"]=="unknown" and running["transport"].interrupt_calls==1 and running["owner"].results==[] and r["v2_terminal_evidence"] is None and not r["closed"],"lost interrupt response state mismatch")
  need(running["transport"].acks[-1]=={"status":"acknowledged","interrupted":True},"server interrupt was not accepted before lost response")
  running["state"].close();release["RUNNING_CANCEL"].set()
  recovered=boot("running_cancel","msg_cancel_running","RUNNING_CANCEL",owner=running["owner"],transport=running["transport"])
  end=tick_until(recovered,lambda x:x["closed"],"running cancel closeout")
  need(end["outcome"]=="canceled" and end["v2_interrupt_state"]=="unknown" and recovered["transport"].interrupt_calls==1 and recovered["transport"].submit_calls==1,"interrupt/prompt was retried or outcome wrong")
  need(end["v2_terminal_evidence"] is not None and len(recovered["owner"].results)==1 and len(recovered["owner"].revoke_keys)==1 and recovered["transport"].delete_calls==0,"terminal evidence/result/revoke missing or unqualified delete sent")
  running_result={"outcome":end["outcome"],"prompt_submissions":recovered["transport"].submit_calls,"interrupt_requests":recovered["transport"].interrupt_calls,"interrupt_state":end["v2_interrupt_state"],"result_receipts":len(recovered["owner"].results),"effective_revokes":len(recovered["owner"].revoke_keys),"terminal_evidence_present":True}
  recovered["state"].close()

  # Active foreign prompt plus queued input makes the adapter refuse session-wide interrupt.
  foreign=boot("foreign_queue","msg_foreign_active","FOREIGN_ACTIVE");foreign["adapter"].tick()
  need(held["FOREIGN_ACTIVE"].wait(8),"provider did not hold foreign-queue active input")
  frow=row(foreign);queue_id="msg_foreign_queued"
  st,ack=call("POST",f"/api/session/{frow['session_id']}/prompt",{"id":queue_id,"text":"SYNTHETIC FOREIGN QUEUE","delivery":"queue"})
  need(st==200,"foreign queue request not accepted")
  foreign["owner"].cancel();foreign["adapter"].tick();frow=row(foreign)
  inbox=(call("GET",f"/api/session/{frow['session_id']}/inbox")[1] or {}).get("data",[])
  need(frow["v2_interrupt_state"]=="not_requested" and foreign["transport"].interrupt_calls==0 and foreign["transport"].delete_calls==0,"foreign queued work did not block interrupt/delete")
  need(not frow["closed"] and frow["v2_terminal_evidence"] is None and foreign["owner"].results==[] and not foreign["owner"].revoke_keys,"foreign queue led to closeout")
  need(any(x.get("id")==queue_id for x in inbox) and "unknown" in foreign["transport"].inspect_statuses,"foreign queue evidence missing")
  foreign_result={"state":frow["state"],"closed":False,"inspect_statuses":foreign["transport"].inspect_statuses,"queued_input_present":True,"interrupt_requests":0,"owner_result_receipts":0,"effective_revokes":0}
  foreign["state"].close();release["FOREIGN_ACTIVE"].set()

  # Cancellation racing a native success must settle what actually happened.
  race=boot("cancel_success","msg_cancel_success","CANCEL_SUCCESS");race["adapter"].tick()
  need(held["CANCEL_SUCCESS"].wait(8),"provider did not hold cancel-success race")
  race["owner"].cancel();release["CANCEL_SUCCESS"].set()
  success_row=tick_until(race,lambda x:x["closed"],"cancel-success closeout")
  need(success_row["outcome"]=="completed" and race["transport"].interrupt_calls==0 and race["transport"].delete_calls==0 and len(race["owner"].results)==1,"cancel race overwrote success or sent unqualified delete")
  race_result={"owner_cancel_recorded":True,"native_outcome":"succeeded","owner_outcome":success_row["outcome"],"interrupt_requests":race["transport"].interrupt_calls,"result_receipts":len(race["owner"].results),"effective_revokes":len(race["owner"].revoke_keys)}
  race["state"].close()

  # Try the real API's queue delivery on an otherwise empty idle session.
  qdir=root/"sole_queue_directory";qdir.mkdir();qsid=client.create_session("sole-queue-probe",str(qdir),"mock/fake",DENY);qid="msg_sole_queue_probe";qtext="synthetic sole queue probe"
  qstatus,qack=call("POST",f"/api/session/{qsid}/prompt",{"id":qid,"text":qtext,"delivery":"queue"})
  need(qstatus==200,"real server rejected queue probe")
  qtarget=client.inspect_cancellation_target(qsid,qid,hashlib.sha256(qtext.encode()).hexdigest(),str(qdir),"mock/fake",DENY)
  _,q_inbox_response=call("GET",f"/api/session/{qsid}/inbox");q_inbox=(q_inbox_response or {}).get("data",[])
  _,q_rows_response=call("GET",f"/api/session/{qsid}/message");q_rows=(q_rows_response or {}).get("data",[])
  _,q_active_response=call("GET","/api/session/active");q_active=(q_active_response or {}).get("data",{})
  queue_projection={"active":qsid in q_active,"inbox_count":len(q_inbox),"target_in_inbox":any(x.get("id")==qid for x in q_inbox),"transcript_types":[x.get("type") for x in q_rows]}
  sole_queue={"queue_post_status":qstatus,"inspection_status":qtarget["status"],"projection":queue_projection,"deletion_qualified":False,"delete_request_sent":False}
  if qtarget.get("status")=="queued":
   sole_queue["reason"]="target appeared queued, but fixture deletion dispatch is intentionally disabled"
  else:
   sole_queue["reason"]="server did not expose a sole queued target"

  need(delete_requests[0]==0,"unqualified queued deletion request was sent")
  result={"result":"PASS","binary":"OpenCode 2.0.32","source_sha256":EXPECTED,"running_cancel_lost_response_restart":running_result,"foreign_queue_blocks_interrupt":foreign_result,"cancel_race_success":race_result,"sole_queued_deletion":sole_queue,"delete_requests":delete_requests[0],"provider_calls":len(provider_inputs),"provider_markers":{x:provider_inputs.count(x) for x in sorted(set(provider_inputs))},"external_network":False,"password":"not emitted","limits":["synthetic owner/delegation only","terminal API snapshots are observational and non-atomic"]}
  print(json.dumps(result,sort_keys=True))
 finally:
  for e in release.values():e.set()
  if server is not None:
   server.terminate()
   try:server.wait(timeout=5)
   except subprocess.TimeoutExpired:server.kill();server.wait()
  if provider is not None:provider.shutdown();provider.server_close()
  shutil.rmtree(root,ignore_errors=True)
if __name__=="__main__":main()
