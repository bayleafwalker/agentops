"""Rebuild frozen replay bytes from existing Git/served history; default writes nothing."""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]
sys.path.insert(0,str(REPO/'scripts'))
from jev_shadow import validate_decision

def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def stamp(value):return datetime.fromisoformat(value.replace('Z','+00:00'))
def historical(snapshot,when):
 item=snapshot['item'];description=item['description'];revision=item['edit_revision'];rewound=0
 for event in sorted(snapshot['events'],key=lambda e:(e['created_at'],e['id']),reverse=True):
  if event.get('event_type')!='item-edited':continue
  payload=event['payload'];payload=json.loads(payload) if isinstance(payload,str) else payload
  if payload.get('field')!='description':continue
  if stamp(event['created_at'])<=stamp(when):break
  if payload.get('revision')!=revision or payload.get('description')!=description:raise ValueError('incomplete historical edit chain')
  description=payload.get('previous_description');revision=payload.get('previous_revision');rewound+=1
 if not isinstance(description,str) or not revision or digest(description)!=revision.rsplit(':',1)[-1]:raise ValueError('historical revision mismatch')
 return {'title':item['title'],'description':description,'source_revision':revision,'rewound_edits':rewound}

def deidentify(text):
 text=re.sub(r'https?://\S+','[url]',text)
 text=re.sub(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}','[email]',text)
 text=re.sub(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b','[ip]',text)
 text=re.sub(r'/(?:projects/dev|home|Users)/[^\s`"\']+','[workspace-path]',text)
 text=re.sub(r'(?i)bayleaf(?:walker)?','operator',text)
 text=re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})\b','[credential-redacted]',text)
 return re.sub(r'(?<![A-Za-z0-9])(?:agentops|vuoro|sprintctl|appservice|gitops-nixos)?#[0-9]+','[work-item]',text)

def build(rows,seed):
 parents={}
 def find(a):
  parents.setdefault(a,a)
  if parents[a]!=a:parents[a]=find(parents[a])
  return parents[a]
 for row in rows:
  nodes=[row['repo']+':'+i for i in row['item_ids']]
  for node in nodes[1:]:parents[find(node)]=find(nodes[0])
 components={}
 for node in list(parents):components.setdefault(find(node),set()).add(node)
 for row in rows:
  for i in row['item_ids']:
   node=row['repo']+':'+i;components.setdefault(find(node),set()).add(node)
 ordered=sorted(components.values(),key=lambda v:sorted(v))
 groups={node:('group-'+str(n+1).zfill(3),'|'.join(sorted(group))) for n,group in enumerate(ordered) for node in group}
 cases=[]
 for n,row in enumerate(rows,1):
  group,raw=groups[row['repo']+':'+row['item_ids'][0]]
  split='calibration' if int(digest(seed+raw),16)%5<2 else 'heldout'
  cases.append({'case_id':f'case-{n:03}','group_id':group,'split':split,'items':[{'title':deidentify(i['title']),'description':deidentify(i['description'])} for i in row['historical_items']],'caller_tier':row['tier'] if row['source']=='explicit' else None,'source_snapshot_sha256':digest(json.dumps(row,sort_keys=True,separators=(',',':')))})
 return ''.join(json.dumps(case,sort_keys=True)+'\n' for case in cases)

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--tracker-root',type=Path,default=Path('/projects/dev/agentops'));parser.add_argument('--profile',type=Path,default=Path('/projects/dev/agentops/environment-record/profiles/workstation-vuoro-shared.json'));parser.add_argument('--existing-snapshots',type=Path,help='optional already captured host-private snapshots; no new reads or copies');parser.add_argument('--restore-ignored-input',action='store_true');args=parser.parse_args()
 manifest=json.loads((ROOT/'corpus.json').read_text());protocol=json.loads((ROOT/'protocol.json').read_text());rows=[]
 for day in manifest['source_shards']:
  raw=subprocess.check_output(['git','-C',str(REPO),'show',manifest['source_git_sha']+':_artifacts/agentops/audit/events-'+day+'.ndjson'],text=True)
  for line in raw.splitlines():
   event=json.loads(line)
   if (event.get('event_type') or event.get('type'))!='dispatch.route.decision' or event.get('source')!='jev-shadow':continue
   try:decision=validate_decision(event.get('metadata'))
   except ValueError:continue
   rows.append({**decision,'event_id':event.get('event_id'),'occurred_at':str(event.get('occurred_at') or event.get('ts') or '')})
 rows=sorted(rows,key=lambda r:(r['occurred_at'],r['event_id']))[:50]
 snapshots={};env={**os.environ,'SPRINTCTL_BACKEND':'served','SPRINTCTL_VUORO_PROFILE':str(args.profile)}
 def served(arguments):return json.loads(subprocess.check_output(['sprintctl']+arguments,cwd=args.tracker_root,env=env,text=True))
 for row in rows:
  items=[]
  for item_id in row['item_ids']:
   if item_id not in snapshots:
    if args.existing_snapshots:snapshots[item_id]=json.loads((args.existing_snapshots/(item_id+'.json')).read_text())
    else:
     item=served(['item','show','--id',item_id,'--json'])['item']
     snapshots[item_id]={'item':item,'events':served(['event','list','--sprint-id',str(item['sprint_id']),'--item-id',item_id,'--limit','10000','--json'])}
   items.append(historical(snapshots[item_id],row['occurred_at']))
  row['historical_items']=items
 text=build(rows,protocol['split']['seed']);actual=digest(text)
 if actual!=manifest['files']['cases.jsonl']:raise ValueError('reconstructed input differs from frozen SHA256')
 if args.restore_ignored_input:
  target=ROOT/'cases.jsonl'
  if target.exists() and target.read_text()!=text:raise ValueError('refusing to replace different replay inputs')
  target.write_text(text);target.chmod(0o600)
 print(json.dumps({'cases':len(rows),'sha256':actual,'matches_frozen_input':True,'wrote_ignored_input':args.restore_ignored_input}))
if __name__=='__main__':main()
