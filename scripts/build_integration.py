#!/usr/bin/env python3
"""Build a source kit only using installed tools, or explicitly install dependencies.
No production crawling. Builder failure is not converted into a simulated success.
"""
from pathlib import Path
import argparse, json, os, subprocess, sys, time
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('family',choices=['astro','hugo','nextjs']);p.add_argument('--allow-install',action='store_true');a=p.parse_args()
    cwd=ROOT/'integrations'/a.family; env=dict(os.environ,NEXT_TELEMETRY_DISABLED='1',ASTRO_TELEMETRY_DISABLED='1')
    begin=time.perf_counter();log=[]
    commands=[]
    if a.family=='hugo':commands=[['hugo','version'],['hugo','--destination','public']];output='public'
    else:
        if a.allow_install:commands.append(['npm','install','--no-audit','--no-fund'])
        commands.append(['npm','run','build']);output='dist' if a.family=='astro' else 'out'
    status='BUILD_FAILED';exitcode=3
    for cmd in commands:
        try:r=subprocess.run(cmd,cwd=cwd,env=env,text=True,capture_output=True,timeout=180)
        except (OSError,subprocess.TimeoutExpired) as e:log.append({'command':cmd,'error':str(e)});break
        log.append({'command':cmd,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
        if r.returncode:break
        if a.family=='hugo' and cmd==['hugo','version'] and 'v0.147.9' not in r.stdout:
            log.append({'error':'Wrong Hugo version; require 0.147.9 for this source kit.'});break
    else:
        sys.path.insert(0,str(ROOT))
        from localemesh.io import load_build
        from localemesh.full import evaluate
        try:
            facts=load_build(cwd/'manifest.json',cwd/output);issues=evaluate(facts)
            log.append({'findings':[x.json() for x in sorted(issues)]});status='BUILT_AND_CHECKED';exitcode=1 if issues else 0
        except (OSError,ValueError,KeyError) as e:status='PARSE_FAILED';log.append({'error':str(e)})
    record={'family':a.family,'status':status,'wall_s':time.perf_counter()-begin,'log':log}
    dest=ROOT/'results'/f'integration-{a.family}.json';dest.write_text(json.dumps(record,indent=2))
    print(json.dumps(record,indent=2));return exitcode
if __name__=='__main__':sys.exit(main())
