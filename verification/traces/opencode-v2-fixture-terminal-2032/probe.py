#!/usr/bin/env python3
"""Exact 2.0.32 fixture-only terminal closeout qualification; no egress."""
import base64,hashlib,http.server,importlib.util,json,pathlib,secrets,socket,subprocess,sys,tempfile,threading,time,urllib.error,urllib.parse,urllib.request,shutil

BINARY="/nix/store/9ysv2ynpka84idp745mcd8l0ayc2f102-opencode-2.0.32/bin/opencode"
SOURCE=pathlib.Path("/tmp/fixture")
EXPECTED={"host_adapter":"d9cf372f2877be8e3502b4b14e775231e63ac3b08244201b1717fce42a123473",
 "opencode_v2":"4d9f05e108540ea49db62923c59696b77a3eca05333c37e2f4d6b6ed5096d1a0",
 "validate_vuoro_profiles":"110a7583802157a446fbd327acb06940916d29334a8fa8772d3fa90dd709cd56"}
DENY=[{"action":"*","resource":"*","effect":"deny"}]

def need(ok,label):
 if not ok:raise AssertionError(label)
def load(name):
 p=SOURCE/(name+".py");need(hashlib.sha256(p.read_bytes()).hexdigest()==EXPECTED[name],name+" source hash mismatch")
 spec=importlib.util.spec_from_file_location(name,p);mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod
def port():
 s=socket.socket();s.bind(("127.0.0.1",0));p=s.getsockname()[1];s.close();return p

MARKERS=("INTERRUPT_CASE","QUEUED_CASE","CANCEL_SUCCESS")
held={m:threading.Event() for m in MARKERS};release={m:threading.Event() for m in MARKERS};provider_inputs=[]
class Provider(http.server.BaseHTTPRequestHandler):
 protocol_version="HTTP/1.1"
 daemon_threads=True
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers.get("content-length","0"))));content=json.dumps(body.get("messages",[]))
  found=[(content.rfind(m),m) for m in MARKERS if m in content];marker=max(found)[1] if found else "SUCCESS"
  provider_inputs.append(marker)
  if marker in held:held[marker].set();release[marker].wait(20)
  chunks=[{"id":"fake","object":"chat.completion.chunk","created":1,"model":"fake","choices":[{"index":0,"delta":{"role":"assistant","content":"synthetic result"},"finish_reason":None}]},
          {"id":"fake","object":"chat.completion.chunk","created":1,"model":"fake","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}]
  data=("".join("data: "+json.dumps(x)+"\n\n" for x in chunks)+"data: [DONE]\n\n").encode()
  try:
   self.send_response(200);self.send_header("Content-Type","text/event-stream");self.send_header("Content-Length",str(len(data)));self.send_header("Connection","close");self.end_headers();self.wfile.write(data)
  except (BrokenPipeError,ConnectionResetError):pass
 def log_message(self,*args):pass

class Owner:
 def __init__(self,mid,body):
  self.mid=mid;self.seq=1;self.rows=[];self.principals={};self.run_calls=0;self.revoke_attempts=[];self.revoked=set();self.results=[];self.messages=[]
  self.message={"schema":"agent-message/v1","message_id":mid,"recipient":{"principal_id":"iss:devbox:fixture"},"kind":"continue","mode":"request",
   "context":{"item_id":"fixture_item","predecessor_run_id":"fixture_predecessor"},"body":{"text":body},"sender_principal_id":"iss:workstation:fixture","repo_id":"agentops","inbox_seq":1}
 def agent_register(self,repo,*,instance_id,declaration,idempotency_key):self.principals[instance_id]="iss:devbox:fixture";return {"ok":True}
 def agent_observe(self,*a,**kw):return {"ok":True}
 def message_read(self,repo,*,after_seq,limit,instance_id):
  msgs=[] if after_seq>=1 else [dict(self.message,receipts=list(self.rows))]
  return {"messages":msgs,"next_after_seq":1 if msgs else after_seq}
 def message_status(self,repo,*,message_id):return {"message":self.message,"receipts":list(self.rows)}
 def message_receipt(self,repo,*,message_id,instance_id,kind,**fields):
  old=next((x for x in self.rows if x["kind"]==kind),None)
  if old:
   if kind=="result-linked" and any(old.get(k)!=v for k,v in fields.items()):raise ha.OwnerError("already-resulted")
   return dict(old,replayed=True)
  if kind=="run-linked" and not any(x["kind"]=="accepted" for x in self.rows):raise ha.OwnerError("not-accepted")
  row={"kind":kind,"instance_id":instance_id,"principal_id":"iss:devbox:fixture",**fields};self.rows.append(row)
  if kind=="result-linked":self.results.append(row)
  return dict(row,replayed=False)
 def run_register(self,repo,args):
  self.run_calls+=1;return {"repo_id":repo,"run":{"run_id":"run_"+self.mid}}
 def run_delegate(self,repo,*,run_id,creator_instance_id,operations,ttl_seconds,idempotency_key):
  need(self.principals.get(creator_instance_id)=="iss:devbox:fixture","owner principal mismatch")
  self.delegation={"delegation_id":"dlg_"+self.mid,"run_id":run_id,"operations":operations,"expires_at":"2027-01-01T00:00:00Z","revoked":False}
  return {**self.delegation,"token":"vrd_"+"A"*52}
 def run_delegation_get(self,repo,*,delegation_id):return dict(self.delegation)
 def run_delegation_revoke(self,repo,*,delegation_id,reason,idempotency_key):
  self.revoke_attempts.append({"reason":reason,"idempotency_key":idempotency_key})
  if idempotency_key not in self.revoked:self.revoked.add(idempotency_key);self.delegation["revoked"]=True
  return {"delegation_id":delegation_id,"revoked":True,"already_revoked":len(self.revoked)>1}
 def cancel(self):self.rows.append({"kind":"cancel-requested","principal_id":"iss:workstation:fixture","reason":"synthetic cancellation"})

class Transport:
 permissions=DENY
 def __init__(self,client,origin,auth):self.client=client;self.origin=origin;self.auth=auth;self.outage=False;self.create_calls=0;self.submit_calls=0;self.terminal_calls=0;self.native_after_outage=0
 def server_version(self):
  if self.outage:return "2.0.33"
  req=urllib.request.Request(self.origin+"/api/info",headers={"authorization":self.auth})
  with urllib.request.urlopen(req,timeout=4) as r:return json.loads(r.read())["version"]
 def _native(self):
  if self.outage:self.native_after_outage+=1;raise RuntimeError("fixture native API outage")
 def create_session(self,*a):self._native();self.create_calls+=1;return self.client.create_session(*a)
 def find_sessions(self,*a):self._native();return self.client.find_sessions(*a)
 def validate_session(self,*a):self._native();return self.client.validate_session(*a)
 def empty_session_observed(self,*a):self._native();return self.client.empty_session_observed(*a)
 def submit_prompt(self,*a):self._native();self.submit_calls+=1;return self.client.submit_prompt(*a)
 def observe_admission(self,*a):self._native();return self.client.observe_admission(*a)
 def observe_terminal(self,*a):self._native();self.terminal_calls+=1;return self.client.observe_terminal(*a)

def main():
 global ha
 ha=load("host_adapter");v2=load("opencode_v2");root=pathlib.Path(tempfile.mkdtemp(prefix="agentops-v2-terminal-closeout-",dir="/tmp"));server=None;provider=None
 try:
  for n in ("home","config","data","state","cache","work"): (root/n).mkdir(mode=0o700)
  provider=http.server.ThreadingHTTPServer(("127.0.0.1",0),Provider);threading.Thread(target=provider.serve_forever,daemon=True).start()
  opencode_config={"model":"mock/fake","provider":{"mock":{"npm":"@ai-sdk/openai-compatible","name":"synthetic loopback only","options":{"baseURL":f"http://127.0.0.1:{provider.server_address[1]}/v1","apiKey":"synthetic-only"},"models":{"fake":{"name":"Fake","limit":{"context":128000,"output":4096}}}}}}
  (root/"work"/"opencode.json").write_text(json.dumps(opencode_config));(root/"config"/"opencode").mkdir(mode=0o700);(root/"config"/"opencode"/"opencode.json").write_text(json.dumps(opencode_config))
  username="opencode";password=secrets.token_urlsafe(32);auth="Basic "+base64.b64encode((username+":"+password).encode()).decode();p=port();origin=f"http://127.0.0.1:{p}"
  env={"PATH":"/run/current-system/sw/bin:/usr/bin:/bin","HOME":str(root/"home"),"XDG_CONFIG_HOME":str(root/"config"),"XDG_DATA_HOME":str(root/"data"),"XDG_STATE_HOME":str(root/"state"),"XDG_CACHE_HOME":str(root/"cache"),"OPENCODE_SERVER_USERNAME":username,"OPENCODE_SERVER_PASSWORD":password}
  server=subprocess.Popen([BINARY,"serve","--hostname","127.0.0.1","--port",str(p)],cwd=str(root/"work"),env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  def call(method,path,body=None,query=None):
   url=origin+path
   if query:url+="?"+urllib.parse.urlencode(query)
   req=urllib.request.Request(url,method=method,data=None if body is None else json.dumps(body).encode(),headers={"Authorization":auth,"Content-Type":"application/json"})
   try:
    with urllib.request.urlopen(req,timeout=6) as r:
     data=r.read();return r.status,json.loads(data) if data else None
   except urllib.error.HTTPError as e:
    data=e.read()
    try:value=json.loads(data) if data else None
    except ValueError:value=None
    return e.code,value
  info=None
  for _ in range(100):
   if server.poll() is not None:raise RuntimeError("OpenCode exited before readiness")
   try:
    status,info=call("GET","/api/info")
    if status==200 and info.get("version")=="2.0.32":break
   except Exception:pass
   time.sleep(.1)
  need(info and info.get("version")=="2.0.32","pinned version mismatch")
  client=v2.OpenCodeV2(origin,username,password,timeout=8)
  class NoPromptHarness:
   prompts=[]
   def health(self):return True

  def boot(name,mid,body,*,checkpoint=None,owner=None,transport=None):
   folder=root/name;folder.mkdir(exist_ok=True);runs=folder/"runs";runs.mkdir(exist_ok=True)
   profile=folder/"profile.json";profile.write_text(json.dumps({"schema_version":"vuoro-client-profile/v1","id":"fixture","revision":1,"source_environment_id":"devbox","target":{"environment_id":"synthetic-owner","environment_class":"test","endpoint":"http://fixture.invalid"},"credential_ref":"file:/never-read","required_authorities":["work:read","work:evidence"],"production_endpoint_denied":True}))
   authority={"standing_read":{"operations":["work.run.resolve-v1"]},"scoped_execution":{"repositories":["agentops"],"operations":["work.effect.attempt-open-v1","agentops.dispatch.publish-v1",ha.LAUNCH_OPERATION],"publication_operation":"agentops.dispatch.publish-v1","max_ttl_seconds":3600},"explicit_approval":[{"transition":"rollout-resume","operations":["rollout.resume-*"],"approvers":["synthetic-approver"],"max_approval_age_seconds":3600}]}
   (folder/"environment.json").write_text(json.dumps({"schema_version":"environment-record/v1","id":"devbox","roles":["unattended-agent-host"],"authority":authority}))
   policy={"enabled":True,"launches_enabled":True,"run_delegation_qualified":True,"allowed_senders":["iss:workstation:fixture"],"allowed_repos":["agentops"],"kinds":["continue"],"max_concurrent":2,"environment_record":str(folder/"environment.json"),"harness":{"harness_id":"opencode","harness_build":"2.0.32","model_id":"mock/fake","recipe_id":"inbox-continue-v1","observed_profile":{"sandbox":"fixture-only"}}}
   (folder/"policy.json").write_text(json.dumps(policy))
   if owner is None:owner=Owner(mid,body)
   if transport is None:transport=Transport(client,origin,auth)
   state=ha.State(folder/"db",clock=lambda:1800000000.0)
   cfg=ha.Config(poll_interval=10,directory=str(root/"work"),run_root=str(runs),adapter_profile=str(profile))
   adapter=ha.Adapter(owner=owner,harness=NoPromptHarness(),state=state,policy_path=folder/"policy.json",config=cfg,clock=lambda:1800000000.0,checkpoint=checkpoint,log=lambda _:None,
      experimental_v2_session_transport=transport,experimental_v2_prompt_admission=True,experimental_v2_terminal_completion=True)
   return {"folder":folder,"runs":runs,"owner":owner,"transport":transport,"state":state,"adapter":adapter}

  def step_until(case,predicate,label,limit=240):
   for _ in range(limit):
    case["adapter"].tick()
    row=case["state"].get("agentops",case["owner"].mid)
    if predicate(row):return row
    time.sleep(.05)
   raise AssertionError(label+" timeout; state="+str(case["state"].get("agentops",case["owner"].mid)["state"]))
  def end_state(case):return case["state"].get("agentops",case["owner"].mid)
  def linked_outcome(case):return next((r.get("outcome") for r in case["owner"].results),None)

  # Native success and failure both settle once from terminal transcript evidence.
  cases={};provider_inputs.clear()
  success=boot("success","msg_terminal_success","SUCCESS_CASE")
  srow=step_until(success,lambda x:x["closed"],"success closeout")
  need(srow["outcome"]=="completed" and success["transport"].submit_calls==1 and success["transport"].terminal_calls>=1,"success closeout values mismatch")
  need(len(success["owner"].results)==1 and len(success["owner"].revoked)==1 and len(success["owner"].revoke_attempts)==1,"success result/revoke not exactly once")
  cases["success"]={"outcome":srow["outcome"],"closed":bool(srow["closed"]),"prompt_submissions":success["transport"].submit_calls,"terminal_observations":success["transport"].terminal_calls,"result_receipts":len(success["owner"].results),"effective_revokes":len(success["owner"].revoked),"revoke_attempts":len(success["owner"].revoke_attempts)}
  success["state"].close()

  failure=boot("failure","msg_terminal_failure","FAILURE_CASE")
  fpolicy=failure["folder"]/"policy.json";pol=json.loads(fpolicy.read_text());pol["harness"]["model_id"]="mock/no-route";fpolicy.write_text(json.dumps(pol))
  frow=step_until(failure,lambda x:x["closed"],"failure closeout")
  need(frow["outcome"]=="failed" and failure["transport"].submit_calls==1 and len(failure["owner"].results)==1 and len(failure["owner"].revoked)==1 and len(failure["owner"].revoke_attempts)==1,"failure closeout values mismatch")
  cases["failure"]={"outcome":frow["outcome"],"closed":bool(frow["closed"]),"prompt_submissions":failure["transport"].submit_calls,"result_receipts":len(failure["owner"].results),"effective_revokes":len(failure["owner"].revoked),"revoke_attempts":len(failure["owner"].revoke_attempts)}
  failure["state"].close()

  # Persist terminal evidence, simulate native outage, then close from persisted evidence only.
  class CrashEvidence(BaseException):pass
  def crash_at_evidence(name):
   if name=="v2_terminal_evidence_persisted":raise CrashEvidence()
  outage=boot("outage_recovery","msg_terminal_outage","OUTAGE_SUCCESS",checkpoint=crash_at_evidence)
  crashed=False
  for _ in range(240):
   try:outage["adapter"].tick()
   except CrashEvidence:crashed=True;break
   time.sleep(.05)
  need(crashed,"terminal evidence checkpoint did not fire")
  orow=end_state(outage);need(orow["v2_terminal_evidence"] is not None and orow["state"]==ha.S_LAUNCHED,"terminal evidence was not persisted")
  outage["state"].close();outage["transport"].outage=True
  recovered=boot("outage_recovery","msg_terminal_outage","OUTAGE_SUCCESS",owner=outage["owner"],transport=outage["transport"])
  rrow=step_until(recovered,lambda x:x["closed"],"outage recovery closeout")
  need(rrow["outcome"]=="completed" and recovered["transport"].submit_calls==1 and recovered["transport"].terminal_calls==1 and recovered["transport"].native_after_outage==0,"recovery made native call or repeated prompt")
  need(len(recovered["owner"].results)==1 and len(recovered["owner"].revoked)==1 and len(recovered["owner"].revoke_attempts)==1,"recovery result/revoke not exactly once")
  cases["persisted_terminal_checkpoint_native_outage"]={"outcome":rrow["outcome"],"closed":bool(rrow["closed"]),"prompt_submissions":recovered["transport"].submit_calls,"native_calls_after_outage":recovered["transport"].native_after_outage,"result_receipts":len(recovered["owner"].results),"effective_revokes":len(recovered["owner"].revoked),"revoke_attempts":len(recovered["owner"].revoke_attempts)}
  recovered["state"].close()

  # Interrupted native execution maps to canceled, and an owner cancel does not override success.
  interruption=boot("interruption","msg_terminal_interrupt","INTERRUPT_CASE")
  interruption["adapter"].tick()
  interrupt_held=held["INTERRUPT_CASE"].wait(8); ir_now=end_state(interruption); need(interrupt_held,"synthetic provider did not hold interruption case; seen="+repr(provider_inputs)+" state="+repr(None if ir_now is None else ir_now["state"]) + " receipts="+repr(interruption["owner"].rows))
  irow=end_state(interruption);need(irow["state"]==ha.S_LAUNCHED and irow["prompt_admission"]=="admitted","interruption prompt was not admitted")
  interruption["transport"].client.interrupt_session(irow["session_id"])
  release["INTERRUPT_CASE"].set()
  irow=step_until(interruption,lambda x:x["closed"],"interruption closeout")
  need(irow["outcome"]=="canceled" and len(interruption["owner"].results)==1 and len(interruption["owner"].revoked)==1 and len(interruption["owner"].revoke_attempts)==1,"interruption mapping mismatch")
  cases["interruption"]={"outcome":irow["outcome"],"closed":bool(irow["closed"]),"prompt_submissions":interruption["transport"].submit_calls,"result_receipts":len(interruption["owner"].results),"effective_revokes":len(interruption["owner"].revoked),"revoke_attempts":len(interruption["owner"].revoke_attempts)}
  interruption["state"].close()

  cancellation=boot("cancel_vs_success","msg_terminal_cancel_success","CANCEL_SUCCESS")
  cancellation["adapter"].tick()
  cancel_held=held["CANCEL_SUCCESS"].wait(8); cr_now=end_state(cancellation); need(cancel_held,"synthetic provider did not hold cancel-success case; seen="+repr(provider_inputs)+" state="+repr(None if cr_now is None else cr_now["state"]))
  cancellation["owner"].cancel();release["CANCEL_SUCCESS"].set()
  crow=step_until(cancellation,lambda x:x["closed"],"cancel-versus-success closeout")
  need(crow["outcome"]=="completed" and len(cancellation["owner"].results)==1 and len(cancellation["owner"].revoked)==1 and len(cancellation["owner"].revoke_attempts)==1,"cancel overrode observed success or duplicate settlement")
  cases["cancel_vs_success"]={"cancel_receipt_seen":True,"native_outcome":"succeeded","owner_outcome":crow["outcome"],"result_receipts":len(cancellation["owner"].results),"effective_revokes":len(cancellation["owner"].revoked),"revoke_attempts":len(cancellation["owner"].revoke_attempts)}
  cancellation["state"].close()

  # Same-session queued input prevents terminal evidence and settlement after active prompt interruption.
  queued=boot("queued_unknown","msg_terminal_queue","QUEUED_CASE")
  queued["adapter"].tick()
  queue_held=held["QUEUED_CASE"].wait(8); qr_now=end_state(queued); need(queue_held,"synthetic provider did not hold queued case; seen="+repr(provider_inputs)+" state="+repr(None if qr_now is None else qr_now["state"]))
  qrow=end_state(queued);need(qrow["prompt_admission"]=="admitted","queued active prompt not admitted")
  st,qack=call("POST",f"/api/session/{qrow['session_id']}/prompt",{"id":"msg_queued_extra","text":"SYNTHETIC-QUEUED","delivery":"queue"})
  need(st==200,"same-session queue admission failed")
  queued["transport"].client.interrupt_session(qrow["session_id"]);release["QUEUED_CASE"].set()
  deadline=time.time()+8
  while time.time()<deadline:
   queued["adapter"].tick();qrow=end_state(queued)
   if qrow["v2_terminal_evidence"] is not None:break
   time.sleep(.05)
  inbox=(call("GET",f"/api/session/{qrow['session_id']}/inbox")[1] or {}).get("data",[])
  need(qrow["v2_terminal_evidence"] is None and not qrow["closed"] and linked_outcome(queued) is None,"queued input did not keep terminal unresolved")
  need(any(x.get("id")=="msg_queued_extra" for x in inbox) and not queued["owner"].revoked,"queued input not preserved or delegation revoked")
  cases["same_session_queue"]={"state":qrow["state"],"closed":bool(qrow["closed"]),"terminal_evidence_present":False,"queued_input_present":True,"owner_result_receipts":len(queued["owner"].results),"effective_revokes":len(queued["owner"].revoked),"prompt_submissions":queued["transport"].submit_calls}
  queued["state"].close()

  # Ensure a real provider call occurred, and each completed/failed path created one input.
  need("SUCCESS" in provider_inputs or "SUCCESS_CASE" in provider_inputs,"no success fake-provider request observed")
  need(sum(1 for x in provider_inputs if x in ("SUCCESS","SUCCESS_CASE"))>=2,"success recovery/cases did not exercise provider")
  cases["provider"]={"loopback_calls":len(provider_inputs),"calls_by_marker":{m:provider_inputs.count(m) for m in sorted(set(provider_inputs))},"external_egress":False}
  result={"result":"PASS","binary":"OpenCode 2.0.32","source_sha256":EXPECTED,"cases":cases,"limitations":["terminal evidence is two-snapshot observational evidence; atomicity is not established","fixture uses a synthetic owner/delegation, not Vuoro RPC","no production credentials or production services are used"]}
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
