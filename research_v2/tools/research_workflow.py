from __future__ import annotations
import argparse, hashlib, json, os, subprocess, tempfile
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent / '_repo_量化交易ai改进'
STATUS = ROOT / 'CURRENT_STATUS.json'; LOG = ROOT / 'TASK_LOG.jsonl'; LOCK = ROOT / '.engineering_run.lock'

def utc(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def sha256(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def hash_tree(paths):
 out={}
 for root in paths:
  for p in sorted(root.rglob('*')):
   if p.is_file() and '__pycache__' not in p.parts: out[str(p.relative_to(ROOT))]=sha256(p)
 return hashlib.sha256(json.dumps(out,sort_keys=True).encode()).hexdigest()
def git(args):
 return subprocess.run(['git','-c',f'safe.directory={REPO}','-C',str(REPO),*args],text=True,capture_output=True,check=False).stdout.strip()
def atomic_json(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True); fd,tmp=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
 try:
  with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f: json.dump(obj,f,ensure_ascii=False,indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp): os.unlink(tmp)
def load_status(): return json.loads(STATUS.read_text(encoding='utf-8')) if STATUS.exists() else {}
def append_log(event):
 with LOG.open('a',encoding='utf-8',newline='\n') as f: f.write(json.dumps(event,ensure_ascii=False,separators=(',',':'))+'\n')
def reserve(run_id, protocol_hash='UNKNOWN', plan_hash='UNKNOWN', engine_hash='UNKNOWN', data_identity='synthetic_only', parameters=None, command='engineering_synthetic', process_identity='UNKNOWN_ACCESS_DENIED'):
 target=ROOT/'runs'/'engineering'/run_id
 if target.exists():
  if (target/'run_state.json').exists():
   state=json.loads((target/'run_state.json').read_text(encoding='utf-8'))
   if state.get('status')=='COMPLETED': return state
  raise RuntimeError('BLOCKED: output exists with non-completed or unknown state')
 if LOCK.exists(): raise RuntimeError('BLOCKED: active engineering lock exists')
 target.mkdir(parents=True,exist_ok=True); LOCK.mkdir()
 state={'run_id':run_id,'status':'RESERVED','protocol_hash':protocol_hash,'plan_hash':plan_hash,'engine_hash':engine_hash,'data_identity':data_identity,'parameters':parameters or {},'command':command,'start_time':utc(),'process_identity':process_identity,'execution_attempt':1}
 atomic_json(target/'run_state.json',state); append_log({'seq':next_seq(),'timestamp_utc':utc(),'stage':'R1','step_id':'R1.RESERVE','event':'RUN_RESERVED','input_identity':data_identity,'output_paths':[str((target/'run_state.json').relative_to(ROOT))],'result':'OK','next_action':'execute_or_recover'})
 return state
def finish(run_id, status='COMPLETED', **extra):
 target=ROOT/'runs'/'engineering'/run_id; state=json.loads((target/'run_state.json').read_text(encoding='utf-8')); state.update(status=status,end_time=utc(),**extra); atomic_json(target/'run_state.json',state)
 if LOCK.exists(): LOCK.rmdir()
 append_log({'seq':next_seq(),'timestamp_utc':utc(),'stage':'R1','step_id':'R1.FINISH','event':'RUN_'+status,'input_identity':state['data_identity'],'output_paths':[str((target/'run_state.json').relative_to(ROOT))],'result':status,'next_action':'review'})
 return state
def next_seq():
 seq=0
 if LOG.exists():
  for line in LOG.read_text(encoding='utf-8').splitlines():
   try: seq=max(seq,int(json.loads(line).get('seq',0)))
   except Exception: pass
 return seq+1
def cmd_status(_): print(json.dumps(load_status(),ensure_ascii=False,indent=2))
def cmd_verify(_):
 required=['CURRENT_STATUS.json','TASK_LOG.jsonl','protocol/APPROVAL.json','inventory/XAUUSDm_ALLOWED_VALIDATION.json']
 missing=[x for x in required if not (ROOT/x).exists()]
 if missing: raise SystemExit('VERIFY FAIL: '+','.join(missing))
 print('VERIFY PASS: repair records and approval gate present; historical replay remains disabled.')
def cmd_run(a):
 if not a.synthetic: raise SystemExit('BLOCKED: only --synthetic engineering runs are authorized')
 state=reserve(a.run_id, data_identity='synthetic_only', parameters={'synthetic':True}); print(json.dumps(state,ensure_ascii=False,indent=2))
def main():
 p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True)
 for n,fn in [('status',cmd_status),('verify',cmd_verify)]: sub.add_parser(n).set_defaults(fn=fn)
 r=sub.add_parser('run'); r.add_argument('--run-id',required=True); r.add_argument('--synthetic',action='store_true'); r.set_defaults(fn=cmd_run)
 a=p.parse_args(); a.fn(a)
if __name__=='__main__': main()

