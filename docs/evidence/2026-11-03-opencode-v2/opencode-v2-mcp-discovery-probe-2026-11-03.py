import base64,http.server,json,pathlib,secrets,shutil,socket,subprocess,tempfile,threading,time,urllib.error,urllib.parse,urllib.request
B='/nix/store/9ysv2ynpka84idp745mcd8l0ayc2f102-opencode-2.0.32/bin/opencode'
def port():
 s=socket.socket();s.bind(('127.0.0.1',0));p=s.getsockname()[1];s.close();return p
root=pathlib.Path(tempfile.mkdtemp(prefix='oc-v2-mcp-',dir='/tmp'));srv=provider=None
try:
 for n in ('home','config','data','state','cache','work'):(root/n).mkdir(mode=0o700)
 work=root/'work'; calls=root/'mcp-calls.jsonl';mcp=root/'fake_mcp.py'
 mcp.write_text('''import json,sys,pathlib\nlog=pathlib.Path(%r)\ndef send(x): sys.stdout.write(json.dumps(x,separators=(",",":"))+"\\n");sys.stdout.flush()\nfor line in sys.stdin:\n try: m=json.loads(line)\n except: continue\n meth=m.get("method"); i=m.get("id")\n if meth=="initialize": send({"jsonrpc":"2.0","id":i,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"synthetic","version":"1"}}})\n elif meth=="tools/list": send({"jsonrpc":"2.0","id":i,"result":{"tools":[{"name":"echo","description":"synthetic marker","inputSchema":{"type":"object","properties":{},"additionalProperties":False}}]}})\n elif meth=="tools/call":\n  with log.open("a") as f:f.write(json.dumps({"method":meth,"name":m.get("params",{}).get("name")})+"\\n")\n  send({"jsonrpc":"2.0","id":i,"result":{"content":[{"type":"text","text":"mcp-synthetic-called"}],"isError":False}})\n elif meth and i is not None: send({"jsonrpc":"2.0","id":i,"result":{}})\n''' % str(calls),encoding='utf-8')
 (work/'opencode.json').write_text(json.dumps({'model':'mock/fake','provider':{'mock':{'npm':'@ai-sdk/openai-compatible','name':'Loopback synthetic','options':{'baseURL':'PLACE','apiKey':'synthetic-only'},'models':{'fake':{'name':'Fake','tool_call':True,'limit':{'context':128000,'output':4096}}}}}}))
 (root/'config'/'opencode').mkdir(parents=True)
 (root/'config'/'opencode'/'opencode.json').write_text(json.dumps({'mcp':{'servers':{'localtest':{'type':'local','command':['python3',str(mcp)],'enabled':True}}}}))
 provider_requests=[]
 class Fake(http.server.BaseHTTPRequestHandler):
  protocol_version='HTTP/1.1'
  def do_POST(self):
   req=json.loads(self.rfile.read(int(self.headers.get('content-length','0'))));msgs=req.get('messages',[]);ser=json.dumps(msgs);case='discover' if 'CASE:discover' in ser else 'deny' if 'CASE:deny' in ser else 'allow' if 'CASE:allow' in ser else 'other';tools=req.get('tools',[]);names=[t.get('function',{}).get('name') for t in tools];provider_requests.append({'case':case,'tools':names})
   calls=any(m.get('role')=='tool' or m.get('tool_call_id') for m in msgs)
   if case in ('deny','allow') and not calls:
    name=next((n for n in names if 'echo' in str(n).lower()),'mcp__localtest__echo');delta={'role':'assistant','tool_calls':[{'index':0,'id':'mcp-call-'+case,'type':'function','function':{'name':name,'arguments':'{}'}}]};finish='tool_calls'
   else:delta={'role':'assistant','content':'synthetic done'};finish='stop'
   body=(''.join('data: '+json.dumps({'id':'synthetic','object':'chat.completion.chunk','created':1,'model':'fake','choices':[{'index':0,'delta':d,'finish_reason':f}]})+'\n\n' for d,f in ((delta,None),({},finish)))+'data: [DONE]\n\n').encode();self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(body)));self.send_header('Connection','close');self.end_headers();self.wfile.write(body)
  def log_message(self,*a):pass
 provider=http.server.ThreadingHTTPServer(('127.0.0.1',port()),Fake);threading.Thread(target=provider.serve_forever,daemon=True).start()
 cfg=json.loads((work/'opencode.json').read_text());cfg['mcp']={'servers':{'localtest':{'type':'local','command':['python3',str(mcp)],'enabled':True}}};cfg['provider']['mock']['options']['baseURL']=f'http://127.0.0.1:{provider.server_address[1]}/v1';(work/'opencode.json').write_text(json.dumps(cfg))
 password=secrets.token_urlsafe(32);auth='Basic '+base64.b64encode(('opencode:'+password).encode()).decode();base='http://127.0.0.1:'+str(port());env={'PATH':'/run/current-system/sw/bin:/usr/bin:/bin','HOME':str(root/'home'),'XDG_CONFIG_HOME':str(root/'config'),'XDG_DATA_HOME':str(root/'data'),'XDG_STATE_HOME':str(root/'state'),'XDG_CACHE_HOME':str(root/'cache'),'OPENCODE_SERVER_PASSWORD':password}
 def start():return subprocess.Popen([B,'serve','--hostname','127.0.0.1','--port',str(urllib.parse.urlsplit(base).port)],cwd=work,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 def call(method,path,body=None):
  req=urllib.request.Request(base+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'content-type':'application/json','authorization':auth})
  try:
   with urllib.request.urlopen(req,timeout=8) as r:raw=r.read();return r.status,json.loads(raw) if raw else None
  except urllib.error.HTTPError as e:
   try:return e.code,json.loads(e.read())
   except:return e.code,None
 mcp_list=subprocess.run([B,'mcp','list'],cwd=work,env=env,text=True,capture_output=True,timeout=15); mcp_cli={'returncode':mcp_list.returncode,'stdout':mcp_list.stdout[-2000:],'stderr':mcp_list.stderr[-2000:]}; srv=start()
 for _ in range(100):
  if srv.poll() is not None:raise RuntimeError('OpenCode exited')
  try:
   if call('GET','/openapi.json')[0]==200:break
  except:pass
  time.sleep(.1)
 def run(label,perms):
  _,c=call('POST','/api/session',{'title':label,'location':{'directory':str(work)},'model':{'id':'fake','providerID':'mock'},'agent':'build','permissions':perms});sid=c['data']['id'];call('POST',f'/api/session/{sid}/prompt',{'text':'CASE:'+label});messages=[]
  for _ in range(100):
   _,r=call('GET',f'/api/session/{sid}/message');messages=(r or {}).get('data',[])
   if any(m.get('type')=='idle' for m in messages):break
   time.sleep(.1)
  parts=[p for m in messages if m.get('type')=='assistant' for p in m.get('content',[]) if p.get('type')=='tool'];return {'parts':[{'name':p.get('name'),'status':(p.get('state') or {}).get('status'),'error':((p.get('state') or {}).get('error') or {}).get('message'),'marker':'mcp-synthetic-called' in json.dumps(p)} for p in parts]}
 wildcard_allow=[{'action':'*','resource':'*','effect':'allow'}];discover=run('discover',wildcard_allow);mcp_tool=next((name for name in provider_requests[-1]['tools'] if 'echo' in name.lower()),None)
 deny=[{'action':'*','resource':'*','effect':'deny'}];denied=run('deny',deny)
 rule_candidates=['mcp',f'mcp__localtest__echo','mcp.localtest.echo','localtest.echo',mcp_tool]
 allowed={}
 for action in rule_candidates:
  if not action:continue
  perms=deny+[{'action':action,'resource':'*','effect':'allow'}];allowed[action]=run('allow',perms)
 result={'schema':'opencode-v2-mcp-discovery-probe/v1','version':call('GET','/api/info')[1].get('version'),'mcp_tool_name':mcp_tool,'discovery_tool_names':provider_requests[0]['tools'],'denied':denied,'allow_rule_candidates':allowed,'mcp_calls':calls.read_text().splitlines() if calls.exists() else [],'mcp_cli':mcp_cli,'config_mode':'temporary local stdio server configured in project and XDG global config; synthetic echo only','limitation':'The server was not discovered, so these are unknown-tool rejections; MCP permission allow/deny was not tested.'}
 assert result['version']=='2.0.32'
 assert result['mcp_cli']['returncode']==0 and 'No MCP servers configured' in result['mcp_cli']['stdout']
 assert 'mcp__localtest__echo' not in result['discovery_tool_names'] and result['mcp_tool_name'] is None
 assert result['mcp_calls']==[]
 assert denied['parts'] and 'currently available' in denied['parts'][0]['error']
 assert allowed and all(v['parts'] and 'currently available' in v['parts'][0]['error'] for v in allowed.values())
 assert all(not part['marker'] for v in [denied,*allowed.values()] for part in v['parts'])
 print(json.dumps(result,indent=2,sort_keys=True))
finally:
 if srv:srv.terminate();srv.wait(timeout=5)
 if provider:provider.shutdown();provider.server_close()
 shutil.rmtree(root,ignore_errors=True)
