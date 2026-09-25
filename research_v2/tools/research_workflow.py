# research_v2 local workflow utilities
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, tempfile
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent / '_repo_量化交易ai改进'
STATUS = ROOT / 'CURRENT_STATUS.json'; LOG = ROOT / 'TASK_LOG.jsonl'
def utc(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def sha256(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def git(args):
 try: return subprocess.run(['git','-c',f'safe.directory={REPO}','-C',str(REPO),*args],text=True,capture_output=True,check=False).stdout.strip()
 except Exception: return 'UNKNOWN'
def atomic_json(path,obj):
 fd,tmp=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
 try:
  with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f: json.dump(obj,f,ensure_ascii=False,indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp): os.unlink(tmp)
def load_status(): return json.loads(STATUS.read_text(encoding='utf-8')) if STATUS.exists() else {}
def cmd_status(_): print(json.dumps(load_status(),ensure_ascii=False,indent=2))
def cmd_next(_): print((ROOT/'NEXT_ACTION.md').read_text(encoding='utf-8'))
def cmd_verify(_):
 required=['START_HERE.md','LOCAL_TASK_AUTHORIZATION.md','CURRENT_STATUS.json','NEXT_ACTION.md','TASK_LOG.jsonl','DECISIONS.md','BLOCKERS.md','CHANGELOG.md','protocol/RESEARCH_PROTOCOL.md','protocol/METRIC_DEFINITIONS.md','protocol/DATA_ACCESS_POLICY.json','protocol/PARAMETER_SPACE.json','protocol/EXPERIMENT_PLAN.jsonl','protocol/APPROVAL.json','inventory/ENVIRONMENT.json','inventory/DATASET_INVENTORY.csv','inventory/STRATEGY_LIBRARY.csv','inventory/HISTORICAL_RESULTS_INDEX.csv','inventory/DATA_EXPOSURE_REGISTER.csv','reports/P1_INVENTORY_REPORT.md','reports/P3_APPROVAL_PACKAGE.md']
 missing=[x for x in required if not (ROOT/x).exists()]
 assert not missing, f'missing: {missing}'
 s=load_status(); assert s['current_stage'] in ('P3','P4','P5','P6'); assert s['authorization_status'] in ('READY_FOR_EXPERIMENT_APPROVAL','P4_EXECUTED_INCONCLUSIVE_COST_INCOMPLETE','RESEARCH_COMPLETE_INCONCLUSIVE'); assert s['completed_run_count'] >= 0
 print('VERIFY PASS: records, protocol, inventory, and approval gate are present; formal runs remain blocked.')
def cmd_run(a):
 s=load_status(); run=ROOT/'runs'/a.run_id
 if s.get('authorization_status')!='APPROVED_FOR_P4': raise SystemExit('BLOCKED: authorization is not APPROVED_FOR_P4')
 if run.exists(): raise SystemExit('BLOCKED: run_id output already exists')
 raise SystemExit('BLOCKED: formal execution runner is intentionally disabled until P4 implementation approval')
def main():
 p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True)
 for n,fn in [('status',cmd_status),('verify',cmd_verify),('next',cmd_next)]: sub.add_parser(n).set_defaults(fn=fn)
 r=sub.add_parser('run'); r.add_argument('--run-id',required=True); r.set_defaults(fn=cmd_run)
 a=p.parse_args(); a.fn(a)
if __name__=='__main__': main()
