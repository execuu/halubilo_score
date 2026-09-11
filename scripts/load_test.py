#!/usr/bin/env python3
"""Run against a seeded disposable rehearsal host, NEVER a real event."""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import threading
import time
import requests
from dotenv import load_dotenv

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url', default='http://127.0.0.1:8081')
parser.add_argument('--seconds', type=int, default=900)
parser.add_argument('--output', default='output/load-test.json')
parser.add_argument('--env-file', default='.env.rehearsal')
parser.add_argument('--p95-ms', type=int, default=1000, help='Use 1000 for LAN, 2000 for the online pilot.')
parser.add_argument('--confirm-rehearsal', action='store_true', required=True)
args = parser.parse_args()
load_dotenv(args.env_file)
password = os.environ.get('REHEARSAL_PASSWORD')
if not password:
    raise SystemExit('Set REHEARSAL_PASSWORD.')
base=args.url.rstrip('/')
metrics={'score':[], 'leaderboard':[], 'score_form':[]}
errors=[]
lock=threading.Lock()

def token(html):
    return re.search(r'name="csrf_token" value="([^"]+)"',html).group(1)

def authenticated(username):
    session=requests.Session()
    session.headers['Referer']=base+'/login'
    response=session.get(base+'/login',timeout=15)
    response.raise_for_status()
    response=session.post(base+'/login', data={'username':username,'password':password,'csrf_token':token(response.text)}, allow_redirects=False, timeout=15)
    if response.status_code!=302:
        raise RuntimeError(f'Login failed: {username}, HTTP {response.status_code}')
    return session

heads={i:authenticated(f'head{i:02}') for i in range(1,21)}
initial=requests.get(base+'/api/leaderboard',timeout=15).json()
if len(initial)!=30 or any(row['activities_completed'] for row in initial) or [row['name'] for row in initial] != [f'Team {i:02}' for i in range(1,31)]:
    raise SystemExit('Refusing: host is not the expected empty 30-team rehearsal.')
start=time.monotonic()
end=start+args.seconds
started=datetime.now(timezone.utc).isoformat()

def measured(session, kind, method, path, expected, **kwargs):
    before=time.monotonic()
    try:
        response=session.request(method,base+path,timeout=15,allow_redirects=False,**kwargs)
        duration=time.monotonic()-before
        with lock:
            metrics[kind].append(duration)
            if response.status_code!=expected:
                errors.append({'kind':kind,'status':response.status_code,'path':path,'body':response.text[:120]})
        return response
    except Exception as error:
        with lock: errors.append({'kind':kind,'error':str(error)})
        return None

def scorekeeper(index):
    for step in range(60):
        deadline=start+(args.seconds/60)*step
        time.sleep(max(0,deadline-time.monotonic()))
        activity=index+1+(10 if step>=30 else 0)
        team=(step%30)+1
        session=heads[activity]
        if step == 30:
            # These accounts were authenticated before the measured window and
            # their TCP pools have been idle for 7.5 minutes. Retain cookies but
            # reconnect, as an activity head returning in a browser would do.
            # No failed request or submitted score is retried or hidden.
            session.close()
        response=measured(session,'score_form','GET','/scores',200)
        if response is None or response.status_code!=200: continue
        measured(session,'score','POST','/scores',302,data={'csrf_token':token(response.text),'team_id':team,'activity_id':activity,'score':(team*7+activity*3)%101,'notes':'15-minute disposable rehearsal'})

def viewer(index):
    session=requests.Session()
    deadline=start+(index/50)*min(10,args.seconds)
    while deadline<end:
        time.sleep(max(0,deadline-time.monotonic()))
        measured(session,'leaderboard','GET','/api/leaderboard',200)
        deadline+=10

with ThreadPoolExecutor(max_workers=60) as pool:
    jobs=[pool.submit(scorekeeper,i) for i in range(10)] + [pool.submit(viewer,i) for i in range(50)]
    pending=set(jobs)
    while pending:
        _, pending=wait(pending,timeout=30)
        with lock:
            progress={'elapsed_seconds':round(time.monotonic()-start,1),
                      'requests':{kind:len(values) for kind,values in metrics.items()},'errors':len(errors)}
            checkpoint={'started_at':started,'progress':progress,'metrics':metrics,'errors':errors}
            checkpoint_path=Path(args.output).with_suffix('.progress.json')
            checkpoint_path.parent.mkdir(parents=True,exist_ok=True)
            temporary=checkpoint_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(checkpoint))
            temporary.replace(checkpoint_path)
        print(json.dumps(progress),flush=True)
    for job in jobs: job.result()
time.sleep(max(0, end-time.monotonic()))
elapsed=time.monotonic()-start
actual=requests.get(base+'/api/leaderboard',timeout=15).json()
expected={team:sum((team*7+activity*3)%101 for activity in range(1,21)) for team in range(1,31)}
correct=len(actual)==30 and all(row['total_score']==expected[row['id']] and row['activities_completed']==20 for row in actual)
ranked=sorted(expected.items(),key=lambda pair:(-pair[1],pair[0]))
ranks={}; last=None; rank=0
for i,(team,total) in enumerate(ranked,1):
    if total!=last: rank=i
    ranks[team]=rank; last=total
correct=correct and all(row['rank']==ranks[row['id']] for row in actual)

def summary(values):
    ordered=sorted(values)
    return {'requests':len(values),'p95_ms':round(ordered[math.ceil(.95*len(ordered))-1]*1000,2) if ordered else None,'max_ms':round(max(ordered)*1000,2) if ordered else None}
report={'started_at':started,'url':base,'requested_seconds':args.seconds,'elapsed_seconds':round(elapsed,2),'workload':{'teams':30,'activities':20,'concurrent_scorekeepers':10,'viewers':50,'viewer_poll_seconds':10},'metrics':{name:summary(values) for name,values in metrics.items()},'errors':errors,'totals_and_ranks_match':correct,'accepted_expected_scores':600}
report['p95_limit_ms']=args.p95_ms
report['pass']=not errors and correct and len(metrics['score'])==600 and all(report['metrics'][name]['p95_ms']<args.p95_ms for name in ['score','leaderboard'])
target=Path(args.output); target.parent.mkdir(parents=True,exist_ok=True); target.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)
raise SystemExit(0 if report['pass'] else 1)
