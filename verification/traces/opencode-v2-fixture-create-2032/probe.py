import base64, hashlib, importlib.util, json, pathlib, secrets, shutil, socket, subprocess, tempfile, time, urllib.request, threading, http.server

BINARY = "/nix/store/9ysv2ynpka84idp745mcd8l0ayc2f102-opencode-2.0.32/bin/opencode"
SOURCE_DIR = pathlib.Path("/tmp/fixture")
EXPECTED = {
    "host_adapter": "8d6da847311e09085528d2f9951c16afe77eb5a829290ae561ae135d95d13105",
    "opencode_v2": "95b7bca4ad30b304617241fcb7d900c169b9113a546a5066b94623f256346cad",
    "validate_vuoro_profiles": "110a7583802157a446fbd327acb06940916d29334a8fa8772d3fa90dd709cd56",
}
DENY = [{"action":"*","resource":"*","effect":"deny"}]

def require(ok, why):
    if not ok: raise AssertionError(why)

def module(name, path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    require(digest == EXPECTED[name], name + " source digest mismatch")
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    import sys; sys.modules[name] = result
    spec.loader.exec_module(result)
    return result

def free_port():
    s=socket.socket(); s.bind(("127.0.0.1",0)); p=s.getsockname()[1]; s.close(); return p

class ProviderHandler(http.server.BaseHTTPRequestHandler):
    seen=[]
    def do_POST(self):
        self.seen.append({"path":self.path,"bytes":int(self.headers.get("content-length","0"))})
        body=json.dumps({"choices":[{"message":{"role":"assistant","content":"synthetic"},"finish_reason":"stop"}]}).encode()
        self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def log_message(self,*args): pass

class Owner:
    def __init__(self):
        self.principal = {}; self.rs=[]; self.run_calls=0; self.run_args=None; self.delegate_calls=0
        self.seq=1; self.mid="msg_fixture_v2_create"
        self.message={"schema":"agent-message/v1","message_id":self.mid,
          "recipient":{"principal_id":"iss:devbox:fixture"},"kind":"continue","mode":"request",
          "context":{"item_id":"item_fixture","predecessor_run_id":"run_predecessor"},
          "body":{"text":"synthetic fixture only"},"sender_principal_id":"iss:workstation:fixture",
          "repo_id":"agentops","inbox_seq":1}
    def agent_register(self, repo, *, instance_id, declaration, idempotency_key):
        self.principal[instance_id]="iss:devbox:fixture"; return {"ok":True}
    def agent_observe(self, *a, **kw): return {"ok":True}
    def message_read(self, repo, *, after_seq, limit, instance_id):
        msgs=[] if after_seq>=1 else [dict(self.message, receipts=list(self.rs))]
        return {"messages":msgs,"next_after_seq":1 if msgs else after_seq}
    def message_status(self, repo, *, message_id): return {"message":self.message,"receipts":list(self.rs)}
    def message_receipt(self, repo, *, message_id, instance_id, kind, **fields):
        existing=next((r for r in self.rs if r["kind"]==kind),None)
        if existing: return dict(existing,replayed=True)
        if kind=="run-linked" and not any(r["kind"]=="accepted" for r in self.rs):
            raise ha.OwnerError("not-accepted")
        r={"kind":kind,"instance_id":instance_id,"principal_id":"iss:devbox:fixture",**fields}
        self.rs.append(r); return dict(r,replayed=False)
    def run_register(self, repo, arguments):
        self.run_calls += 1; self.run_args=arguments
        return {"repo_id":repo,"run":{"run_id":"run_fixture_v2"}}
    def run_delegate(self, repo, *, run_id, creator_instance_id, operations, ttl_seconds, idempotency_key):
        self.delegate_calls+=1
        require(self.principal.get(creator_instance_id)=="iss:devbox:fixture","synthetic owner principal mismatch")
        self.delegation={"delegation_id":"dlg_fixture","run_id":run_id,"operations":operations,
                         "expires_at":"2027-01-01T00:00:00Z","revoked":False}
        return {**self.delegation,"token":"vrd_"+"A"*52}
    def run_delegation_get(self, repo, *, delegation_id): return dict(self.delegation)
    def run_delegation_revoke(self, repo, *, delegation_id, reason, idempotency_key):
        self.delegation["revoked"]=True; return {"delegation_id":delegation_id,"revoked":True}

class VersionedTransport:
    permissions=DENY
    def __init__(self, client, origin, auth, directory):
        self.client=client; self.origin=origin; self.auth=auth; self.directory=directory
        self.creates=0; self.finds=0; self.lost=False; self.provider_calls=0
    def server_version(self):
        req=urllib.request.Request(self.origin+"/api/info",headers={"authorization":self.auth})
        with urllib.request.urlopen(req,timeout=5) as r: return json.loads(r.read())["version"]
    def create_session(self,*args):
        self.creates+=1; sid=self.client.create_session(*args)
        if not self.lost:
            self.lost=True
            raise RuntimeError("synthetic response lost after server commit")
        return sid
    def find_sessions(self,*args): self.finds+=1; return self.client.find_sessions(*args)
    def validate_session(self,*args): return self.client.validate_session(*args)

def main():
    root=pathlib.Path(tempfile.mkdtemp(prefix="agentops-v2-fixture-create-",dir="/tmp")); server=None; provider=None; provider_thread=None
    try:
        for n in ("home","config","data","state","cache","work","module"): (root/n).mkdir(mode=0o700)
        global ha
        ha=module("host_adapter",SOURCE_DIR/"host_adapter.py")
        v2=module("opencode_v2",SOURCE_DIR/"opencode_v2.py")
        provider= http.server.ThreadingHTTPServer(("127.0.0.1",0),ProviderHandler); provider_thread=threading.Thread(target=provider.serve_forever,daemon=True); provider_thread.start()
        port=free_port(); username="opencode"; password=secrets.token_urlsafe(32)
        auth="Basic "+base64.b64encode((username+":"+password).encode()).decode(); origin=f"http://127.0.0.1:{port}"
        work=root/"work"
        (work/"opencode.json").write_text(json.dumps({"model":"mock/fake","provider":{"mock":{
          "npm":"@ai-sdk/openai-compatible","name":"synthetic loopback provider",
          "options":{"baseURL":"http://127.0.0.1:"+str(provider.server_address[1])+"/v1","apiKey":"synthetic-only"},
          "models":{"fake":{"name":"Fake","tool_call":True,"limit":{"context":128000,"output":4096}}}}}}))
        env={"PATH":"/run/current-system/sw/bin:/usr/bin:/bin","HOME":str(root/"home"),
          "XDG_CONFIG_HOME":str(root/"config"),"XDG_DATA_HOME":str(root/"data"),"XDG_STATE_HOME":str(root/"state"),
          "XDG_CACHE_HOME":str(root/"cache"),"OPENCODE_SERVER_USERNAME":username,"OPENCODE_SERVER_PASSWORD":password}
        server=subprocess.Popen([BINARY,"serve","--hostname","127.0.0.1","--port",str(port)],cwd=str(work),env=env,
                                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        raw=lambda path: urllib.request.urlopen(urllib.request.Request(origin+path,headers={"authorization":auth}),timeout=5)
        for _ in range(100):
            if server.poll() is not None: raise RuntimeError("pinned server exited before readiness")
            try:
                with raw("/api/info") as r:
                    info=json.loads(r.read())
                if info.get("version")=="2.0.32": break
            except Exception: pass
            time.sleep(.1)
        require(info.get("version")=="2.0.32","exact OpenCode version mismatch")
        client=v2.OpenCodeV2(origin,username,password,timeout=8)
        transport=VersionedTransport(client,origin,auth,str(work))
        # Ensure module imports its real authority validator beside the embedded adapter bytes.
        import sys
        sys.path.insert(0,str(SOURCE_DIR))
        # Tenant-specific authority, owner profile, and policy are synthetic fixtures.
        launch=ha.LAUNCH_OPERATION
        authority={"standing_read":{"operations":["work.run.resolve-v1"]},
          "scoped_execution":{"repositories":["agentops"],"operations":["work.effect.attempt-open-v1","agentops.dispatch.publish-v1",launch],
          "publication_operation":"agentops.dispatch.publish-v1","max_ttl_seconds":3600},"explicit_approval":[{"transition":"rollout-resume","operations":["rollout.resume-*"],"approvers":["synthetic-approver"],"max_approval_age_seconds":3600}]}
        envrec={"schema_version":"environment-record/v1","id":"devbox","roles":["unattended-agent-host"],"authority":authority}
        (root/"environment.json").write_text(json.dumps(envrec))
        profile={"schema_version":"vuoro-client-profile/v1","id":"synthetic-profile","revision":1,
          "source_environment_id":"devbox","target":{"environment_id":"synthetic-owner","environment_class":"test","endpoint":"http://127.0.0.1.invalid"},
          "credential_ref":"file:/never-read/fixture","required_authorities":["work:read","work:evidence"],"production_endpoint_denied":True}
        (root/"adapter-profile.json").write_text(json.dumps(profile))
        policy={"enabled":True,"launches_enabled":True,"run_delegation_qualified":True,
          "allowed_senders":["iss:workstation:fixture"],"allowed_repos":["agentops"],"kinds":["continue"],"max_concurrent":2,
          "environment_record":str(root/"environment.json"),"harness":{"harness_id":"opencode","harness_build":"2.0.32",
          "model_id":"mock/fake","recipe_id":"inbox-continue-v1","observed_profile":{"sandbox":"fixture-only"}}}
        (root/"policy.json").write_text(json.dumps(policy))
        run_root=root/"runs"; run_root.mkdir(mode=0o700)
        class NoPromptHarness:
            prompts=[]
            def health(self): return True
        owner=Owner(); state=ha.State(root/"db",clock=lambda:1800000000.0)
        config=ha.Config(poll_interval=10,directory=str(work),run_root=str(run_root),adapter_profile=str(root/"adapter-profile.json"))
        logs=[]
        adapter=ha.Adapter(owner=owner,harness=NoPromptHarness(),state=state,policy_path=root/"policy.json",config=config,
                           clock=lambda:1800000000.0,log=logs.append,experimental_v2_session_transport=transport)
        adapter.tick()
        first=state.get("agentops",owner.mid)
        require(first["state"]==ha.S_LAUNCH_INTENT,"lost response did not leave launch intent: "+str({"state":first["state"],"reason_code":first["reason_code"],"reason_text":first["reason_text"],"last_error":first["last_error"],"logs":logs,"receipts":owner.rs}))
        require(first["session_id"] is None,"lost response unexpectedly persisted session id")
        require(transport.creates==1,"first path did not create exactly once")
        # Simulate process restart while preserving state, owner state and the server.
        state.close(); state=ha.State(root/"db",clock=lambda:1800000001.0)
        adapter2=ha.Adapter(owner=owner,harness=NoPromptHarness(),state=state,policy_path=root/"policy.json",config=config,
                            clock=lambda:1800000001.0,log=logs.append,experimental_v2_session_transport=transport)
        adapter2.tick()
        rec=state.get("agentops",owner.mid)
        sessions=client.find_sessions("vuoro-msg:"+owner.mid,str(run_root/owner.mid))
        require(rec["state"]==ha.S_LAUNCHED,"recovery did not reach LAUNCHED: "+str(rec["state"]))
        require(rec["session_id"]==sessions[0] and len(sessions)==1,"session discovery/adoption mismatch")
        client.validate_session(rec["session_id"],str(run_root/owner.mid),"mock/fake",DENY)
        require(transport.creates==1,"recovery attempted duplicate create")
        wrong_binding_rejected=False
        try: client.validate_session(rec["session_id"],str(run_root/owner.mid),"mock/changed",DENY)
        except v2.V2Error: wrong_binding_rejected=True
        require(wrong_binding_rejected,"negative control: changed model binding was accepted")
        require(transport.finds>=1,"recovery did not use exact client discovery")
        require(rec["prompt_sent"]==0 and rec["prompt_id"] is None,"fixture sent/recorded a prompt")
        require(owner.run_calls==1 and owner.delegate_calls==1,"synthetic owner/delegation count mismatch")
        require(any(r["kind"]=="accepted" for r in owner.rs) and any(r["kind"]=="run-linked" for r in owner.rs),"owner receipts incomplete")
        require(not any(r["kind"]=="result-linked" for r in owner.rs),"run got terminal/result receipt at LAUNCHED")
        require(NoPromptHarness.prompts==[],"legacy harness received prompt")
        require(not ProviderHandler.seen,"provider received an unexpected inference request")
        require(server.poll() is None,"server died during fixture")
        result={"binary":"OpenCode 2.0.32","binary_path":BINARY,"host_adapter_sha256":EXPECTED["host_adapter"],
          "opencode_v2_sha256":EXPECTED["opencode_v2"],"validator_sha256":EXPECTED["validate_vuoro_profiles"],
          "result":"PASS","record_state":rec["state"],"harness_api":rec["harness_api"],"session_id_present":bool(rec["session_id"]),
          "actual_session_count":len(sessions),"transport_create_calls":transport.creates,"recovery_find_calls":transport.finds,
          "synthetic_owner_run_register_calls":owner.run_calls,"synthetic_delegation_mints":owner.delegate_calls,
          "receipts":[r["kind"] for r in owner.rs],"prompt_sent":bool(rec["prompt_sent"]),"prompt_id_present":bool(rec["prompt_id"]),
          "provider_calls":len(ProviderHandler.seen),"wrong_model_binding_rejected":wrong_binding_rejected,"network_namespace":"bwrap --unshare-net","server_password":"not emitted","logs":[x.split(":",1)[0] for x in logs]}
        print(json.dumps(result,sort_keys=True))
        state.close()
    finally:
        if provider is not None:
            provider.shutdown(); provider.server_close()
        if server is not None:
            server.terminate()
            try: server.wait(timeout=5)
            except subprocess.TimeoutExpired: server.kill(); server.wait()
        shutil.rmtree(root,ignore_errors=True)

if __name__=="__main__": main()
