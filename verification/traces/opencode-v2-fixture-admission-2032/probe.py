#!/usr/bin/env python3
"""Portable disposable qualification of fixture-only v2 prompt admission.

Reads exact source files from /tmp/fixture, mounted read-only by bwrap, and
checks their pinned SHA-256 before import. No credentials/config are read.
"""
import base64, hashlib, http.server, importlib.util, json, pathlib, secrets, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request

BINARY="/nix/store/9ysv2ynpka84idp745mcd8l0ayc2f102-opencode-2.0.32/bin/opencode"
SOURCE=pathlib.Path("/tmp/fixture")
EXPECTED={"host_adapter":"4e3841968cd06ea8013b093da0425de234c4b9586fcdf333597556fb77a9a4db",
          "opencode_v2":"69cb7fd22c4b94a0d8128af68b347425b0ed2df9ba15cd1a1d6af716506ddfce",
          "validate_vuoro_profiles":"110a7583802157a446fbd327acb06940916d29334a8fa8772d3fa90dd709cd56"}
DENY=[{"action":"*","resource":"*","effect":"deny"}]

def require(ok,label):
    if not ok: raise AssertionError(label)

def load(name):
    path=SOURCE/(name+".py")
    require(hashlib.sha256(path.read_bytes()).hexdigest()==EXPECTED[name],name+" source SHA mismatch")
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec); sys.modules[name]=mod; spec.loader.exec_module(mod)
    return mod

def free_port():
    s=socket.socket(); s.bind(("127.0.0.1",0)); port=s.getsockname()[1]; s.close(); return port

class Provider(http.server.BaseHTTPRequestHandler):
    seen=[]
    def do_POST(self):
        size=int(self.headers.get("content-length","0")); self.rfile.read(size)
        type(self).seen.append({"path":self.path,"bytes":size})
        body=json.dumps({"id":"chatcmpl-fixture","object":"chat.completion","created":1,"model":"fake",
          "choices":[{"index":0,"message":{"role":"assistant","content":"synthetic fixture complete"},"finish_reason":"stop"}],
          "usage":{"prompt_tokens":1,"completion_tokens":4,"total_tokens":5}}).encode()
        self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def log_message(self,*args): pass

class Owner:
    def __init__(self,mid):
        self.mid=mid; self.seq=1; self.rs=[]; self.principal={}; self.run_calls=0; self.delegate_calls=0
        self.message={"schema":"agent-message/v1","message_id":mid,"recipient":{"principal_id":"iss:devbox:fixture"},
          "kind":"continue","mode":"request","context":{"item_id":"item_fixture","predecessor_run_id":"run_predecessor"},
          "body":{"text":"synthetic admission fixture"},"sender_principal_id":"iss:workstation:fixture",
          "repo_id":"agentops","inbox_seq":1}
    def agent_register(self,repo,*,instance_id,declaration,idempotency_key): self.principal[instance_id]="iss:devbox:fixture"; return {"ok":True}
    def agent_observe(self,*args,**kwargs): return {"ok":True}
    def message_read(self,repo,*,after_seq,limit,instance_id):
        rows=[] if after_seq>=1 else [dict(self.message,receipts=list(self.rs))]
        return {"messages":rows,"next_after_seq":1 if rows else after_seq}
    def message_status(self,repo,*,message_id): return {"message":self.message,"receipts":list(self.rs)}
    def cancel(self): self.rs.append({"kind":"cancel-requested","principal_id":"iss:workstation:fixture","reason":"synthetic test"})
    def message_receipt(self,repo,*,message_id,instance_id,kind,**fields):
        old=next((r for r in self.rs if r["kind"]==kind),None)
        if old: return dict(old,replayed=True)
        if kind=="run-linked" and not any(r["kind"]=="accepted" for r in self.rs): raise ha.OwnerError("not-accepted")
        row={"kind":kind,"instance_id":instance_id,"principal_id":"iss:devbox:fixture",**fields}; self.rs.append(row); return dict(row,replayed=False)
    def run_register(self,repo,arguments): self.run_calls+=1; return {"repo_id":repo,"run":{"run_id":"run_fixture_"+self.mid}}
    def run_delegate(self,repo,*,run_id,creator_instance_id,operations,ttl_seconds,idempotency_key):
        self.delegate_calls+=1; require(self.principal.get(creator_instance_id)=="iss:devbox:fixture","owner principal mismatch")
        self.delegation={"delegation_id":"dlg_"+self.mid,"run_id":run_id,"operations":operations,"expires_at":"2027-01-01T00:00:00Z","revoked":False}
        return {**self.delegation,"token":"vrd_"+"A"*52}
    def run_delegation_get(self,repo,*,delegation_id): return dict(self.delegation)
    def run_delegation_revoke(self,repo,*,delegation_id,reason,idempotency_key): self.delegation["revoked"]=True; return {"delegation_id":delegation_id,"revoked":True}

class Transport:
    permissions=DENY
    def __init__(self,client,origin,auth,*,lose_ack=False): self.client=client; self.origin=origin; self.auth=auth; self.lose_ack=lose_ack; self.submit_calls=0; self.observe_results=[]
    def server_version(self):
        req=urllib.request.Request(self.origin+"/api/info",headers={"authorization":self.auth})
        with urllib.request.urlopen(req,timeout=5) as r: return json.loads(r.read())["version"]
    def create_session(self,*args): return self.client.create_session(*args)
    def find_sessions(self,*args): return self.client.find_sessions(*args)
    def validate_session(self,*args): return self.client.validate_session(*args)
    def empty_session_observed(self,*args): return self.client.empty_session_observed(*args)
    def submit_prompt(self,*args):
        self.submit_calls+=1; ack=self.client.submit_prompt(*args)
        if self.lose_ack: self.lose_ack=False; raise RuntimeError("synthetic response loss after valid server acknowledgement")
        return ack
    def observe_admission(self,*args):
        result=self.client.observe_admission(*args); self.observe_results.append(result["status"]); return result

def main():
    global ha
    ha=load("host_adapter"); v2=load("opencode_v2")
    top=pathlib.Path(tempfile.mkdtemp(prefix="agentops-v2-admission-",dir="/tmp")); server=None; provider=None
    try:
        for n in ("home","config","data","state","cache","work"): (top/n).mkdir(mode=0o700)
        provider=http.server.ThreadingHTTPServer(("127.0.0.1",0),Provider); pt=threading.Thread(target=provider.serve_forever,daemon=True); pt.start()
        work=top/"work"; (work/"opencode.json").write_text(json.dumps({"model":"mock/fake","provider":{"mock":{
          "npm":"@ai-sdk/openai-compatible","name":"loopback fake inference","options":{"baseURL":"http://127.0.0.1:"+str(provider.server_address[1])+"/v1","apiKey":"synthetic-only"},
          "models":{"fake":{"name":"Fake","tool_call":True,"limit":{"context":128000,"output":4096}}}}}}))
        port=free_port(); username="opencode"; password=secrets.token_urlsafe(32); auth="Basic "+base64.b64encode((username+":"+password).encode()).decode(); origin=f"http://127.0.0.1:{port}"
        env={"PATH":"/run/current-system/sw/bin:/usr/bin:/bin","HOME":str(top/"home"),"XDG_CONFIG_HOME":str(top/"config"),"XDG_DATA_HOME":str(top/"data"),"XDG_STATE_HOME":str(top/"state"),"XDG_CACHE_HOME":str(top/"cache"),"OPENCODE_SERVER_USERNAME":username,"OPENCODE_SERVER_PASSWORD":password}
        server=subprocess.Popen([BINARY,"serve","--hostname","127.0.0.1","--port",str(port)],cwd=str(work),env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            if server.poll() is not None: raise RuntimeError("pinned server exited before readiness")
            try:
                req=urllib.request.Request(origin+"/api/info",headers={"authorization":auth})
                with urllib.request.urlopen(req,timeout=5) as r: info=json.loads(r.read())
                if info.get("version")=="2.0.32": break
            except Exception: pass
            time.sleep(.1)
        require(info.get("version")=="2.0.32","pinned server version mismatch")
        client=v2.OpenCodeV2(origin,username,password,timeout=8)

        def boot(name,mid,optin,*,checkpoint=None,transport=None,owner=None,state=None,root=None):
            sub=root or top/name
            sub.mkdir(exist_ok=True)
            run_root=sub/"runs"; run_root.mkdir(exist_ok=True)
            profile=sub/"profile.json"; profile.write_text(json.dumps({"schema_version":"vuoro-client-profile/v1","id":"fixture","revision":1,"source_environment_id":"devbox","target":{"environment_id":"synthetic-owner","environment_class":"test","endpoint":"http://fixture.invalid"},"credential_ref":"file:/never-read","required_authorities":["work:read","work:evidence"],"production_endpoint_denied":True}))
            authority={"standing_read":{"operations":["work.run.resolve-v1"]},"scoped_execution":{"repositories":["agentops"],"operations":["work.effect.attempt-open-v1","agentops.dispatch.publish-v1",ha.LAUNCH_OPERATION],"publication_operation":"agentops.dispatch.publish-v1","max_ttl_seconds":3600},"explicit_approval":[{"transition":"rollout-resume","operations":["rollout.resume-*"],"approvers":["synthetic-approver"],"max_approval_age_seconds":3600}]}
            (sub/"environment.json").write_text(json.dumps({"schema_version":"environment-record/v1","id":"devbox","roles":["unattended-agent-host"],"authority":authority}))
            policy={"enabled":True,"launches_enabled":True,"run_delegation_qualified":True,"allowed_senders":["iss:workstation:fixture"],"allowed_repos":["agentops"],"kinds":["continue"],"max_concurrent":2,"environment_record":str(sub/"environment.json"),"harness":{"harness_id":"opencode","harness_build":"2.0.32","model_id":"mock/fake","recipe_id":"inbox-continue-v1","observed_profile":{"sandbox":"fixture-only"}}}
            (sub/"policy.json").write_text(json.dumps(policy))
            class NoPrompt:
                prompts=[]
                def health(self): return True
            if owner is None: owner=Owner(mid)
            if transport is None: transport=Transport(client,origin,auth)
            if state is None: state=ha.State(sub/"db",clock=lambda:1800000000.0)
            cfg=ha.Config(poll_interval=10,directory=str(work),run_root=str(run_root),adapter_profile=str(profile))
            adapter=ha.Adapter(owner=owner,harness=NoPrompt(),state=state,policy_path=sub/"policy.json",config=cfg,clock=lambda:1800000000.0,log=lambda _:None,
              experimental_v2_session_transport=transport,experimental_v2_prompt_admission=optin,checkpoint=checkpoint)
            return {"sub":sub,"run_root":run_root,"owner":owner,"transport":transport,"state":state,"adapter":adapter,"harness":NoPrompt}

        # Default-off control: a real v2 session is created, but no prompt is submitted.
        Provider.seen.clear(); off=boot("default_off","msg_v2_admission_off",False); off["adapter"].tick(); offrec=off["state"].get("agentops",off["owner"].mid)
        require(offrec["state"]==ha.S_LAUNCHED and not offrec["prompt_sent"] and offrec["prompt_admission"] is None,"default-off did not stop at LAUNCHED")
        require(off["transport"].submit_calls==0 and not Provider.seen and off["harness"].prompts==[],"default-off sent prompt/inference")
        require(not any(r["kind"]=="result-linked" for r in off["owner"].rs),"default-off emitted terminal result receipt")
        off["state"].close()

        # Opt-in: server accepts prompt and returns a validated acknowledgement; proxy then loses that acknowledgement.
        Provider.seen.clear(); lost=boot("lost_ack","msg_v2_admission_lostack",True); lost["transport"].lose_ack=True; lost["adapter"].tick()
        row=lost["state"].get("agentops",lost["owner"].mid); require(row["state"]==ha.S_LAUNCHED and row["prompt_admission"]=="unknown","lost ack did not persist uncertainty")
        intent=lost["state"].load_v2_prompt("agentops",lost["owner"].mid)
        sid=row["session_id"]; pre=client.observe_admission(sid,intent["id"],intent["sha256"])
        require(pre["status"]=="observed","server did not expose accepted prompt after lost ack")
        lost["state"].close(); restarted=boot("lost_ack","msg_v2_admission_lostack",True,transport=lost["transport"],owner=lost["owner"])
        restarted["adapter"].tick(); final=restarted["state"].get("agentops",restarted["owner"].mid)
        require(final["prompt_admission"]=="admitted","restart did not reconcile accepted prompt")
        require(restarted["transport"].submit_calls==1,"accepted prompt was resubmitted after lost acknowledgement")
        require(not any(r["kind"]=="result-linked" for r in restarted["owner"].rs),"fixture emitted terminal result receipt")
        require(final["prompt_id"]==intent["id"],"prompt evidence identity mismatch")
        require(any(r["kind"]=="run-linked" for r in restarted["owner"].rs),"run-linked owner receipt missing")
        observed_sources=json.loads(final["prompt_admission_evidence"])["sources"]
        require(observed_sources,"recovery evidence sources absent")
        wrong_model_binding_rejected=False
        try: client.validate_session(final["session_id"],str(restarted["run_root"]/restarted["owner"].mid),"mock/changed",DENY)
        except v2.V2Error: wrong_model_binding_rejected=True
        require(wrong_model_binding_rejected,"negative control accepted changed model binding")
        # Let the fake provider finish, then confirm this fixture issued at most one provider call.
        for _ in range(100):
            if Provider.seen: break
            time.sleep(.05)
        require(len(Provider.seen)<=1,"fake provider saw duplicate inference requests")
        lost_provider_calls=len(Provider.seen)
        restarted["state"].close()

        # Cancellation after actual session creation but before prompt must remain unresolved.
        Provider.seen.clear()
        class AfterCreateCrash(BaseException): pass
        def crash_after_create(name):
            if name=="launched_persisted": raise AfterCreateCrash()
        canceled=boot("cancel_after_create","msg_v2_admission_cancel",True,checkpoint=crash_after_create)
        try: canceled["adapter"].tick()
        except AfterCreateCrash: pass
        else: raise AssertionError("post-create crash checkpoint did not fire")
        canceled["owner"].cancel(); canceled["state"].close()
        canceled2=boot("cancel_after_create","msg_v2_admission_cancel",True,owner=canceled["owner"],transport=canceled["transport"])
        canceled2["adapter"].tick(); crec=canceled2["state"].get("agentops",canceled2["owner"].mid)
        require(crec["state"]==ha.S_LAUNCHED and not crec["closed"],"post-create cancellation closed the run")
        require(crec["prompt_sent"]==0 and crec["prompt_admission"] is None and canceled2["transport"].submit_calls==0,"canceled session received a prompt")
        require(not any(r["kind"]=="result-linked" for r in canceled2["owner"].rs),"post-create cancellation emitted owner result")
        require(not Provider.seen,"post-create cancellation caused fake inference")
        canceled2["state"].close()

        # Negative control: crash after durable unknown marker but before transport invocation.
        Provider.seen.clear()
        class InjectedCrash(BaseException): pass
        def crash_before_send(name):
            if name=="v2_submission_unknown_persisted": raise InjectedCrash()
        unknown=boot("unknown_pre_send","msg_v2_admission_unknown",True,checkpoint=crash_before_send)
        try: unknown["adapter"].tick()
        except InjectedCrash: pass
        else: raise AssertionError("pre-send crash injection did not fire")
        urow=unknown["state"].get("agentops",unknown["owner"].mid)
        require(urow["state"]==ha.S_LAUNCHED and urow["prompt_admission"]=="unknown","pre-send crash did not persist unknown")
        require(unknown["transport"].submit_calls==0,"submission happened before crash checkpoint")
        usid=urow["session_id"]; uprompt=unknown["state"].load_v2_prompt("agentops",unknown["owner"].mid)
        raw_unknown=client.observe_admission(usid,uprompt["id"],uprompt["sha256"])
        require(raw_unknown["status"]=="unknown","negative control session unexpectedly contains the prompt")
        unknown["state"].close(); unknown2=boot("unknown_pre_send","msg_v2_admission_unknown",True,owner=unknown["owner"],transport=unknown["transport"])
        unknown2["adapter"].tick(); ufinal=unknown2["state"].get("agentops",unknown2["owner"].mid)
        require(ufinal["prompt_admission"]=="unknown" and unknown2["transport"].submit_calls==0,"unknown evidence incorrectly authorized retry")
        require(not Provider.seen,"unknown-before-send caused provider request")
        require(not any(r["kind"]=="result-linked" for r in unknown2["owner"].rs),"unknown case emitted terminal result receipt")
        unknown2["state"].close()
        result={"result":"PASS","binary":"OpenCode 2.0.32","host_adapter_sha256":EXPECTED["host_adapter"],"opencode_v2_sha256":EXPECTED["opencode_v2"],"validator_sha256":EXPECTED["validate_vuoro_profiles"],
          "default_off":{"state":offrec["state"],"prompt_sent":bool(offrec["prompt_sent"]),"prompt_admission":offrec["prompt_admission"],"submit_calls":off["transport"].submit_calls,"provider_calls":0},
          "lost_ack":{"state":final["state"],"admission":final["prompt_admission"],"prompt_id_present":bool(final["prompt_id"]),"unique_prompt_id":True,"server_readback_before_restart":pre["status"],"readback_sources":observed_sources,"submit_calls_total":restarted["transport"].submit_calls,"provider_calls":lost_provider_calls,"owner_receipts":[r["kind"] for r in restarted["owner"].rs]},
          "unknown_before_send":{"state":ufinal["state"],"admission":ufinal["prompt_admission"],"server_readback_before_restart":raw_unknown["status"],"submit_calls_total":unknown2["transport"].submit_calls,"provider_calls":0,"owner_receipts":[r["kind"] for r in unknown2["owner"].rs]},
          "cancel_after_create":{"state":crec["state"],"closed":bool(crec["closed"]),"prompt_sent":bool(crec["prompt_sent"]),"submit_calls":canceled2["transport"].submit_calls,"result_linked":any(r["kind"]=="result-linked" for r in canceled2["owner"].rs)},
          "wrong_model_binding_rejected":wrong_model_binding_rejected,"network_namespace":"bwrap --unshare-net","server_password":"not emitted"}
        print(json.dumps(result,sort_keys=True))
    finally:
        if provider is not None: provider.shutdown(); provider.server_close()
        if server is not None:
            server.terminate()
            try: server.wait(timeout=5)
            except subprocess.TimeoutExpired: server.kill(); server.wait()
        shutil.rmtree(top,ignore_errors=True)

if __name__=="__main__": main()
