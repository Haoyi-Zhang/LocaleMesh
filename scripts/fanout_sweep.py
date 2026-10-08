#!/usr/bin/env python3
"""Bounded semantic fan-out sweep for the incremental evaluator.

The sweep varies only the number of owners that read one changed page observation.
It uses authored in-memory facts (no framework build or HTML parsing) so the result
isolates invalidation/update cost from snapshot construction and I/O.
"""
from __future__ import annotations
import copy,json,platform,resource,statistics,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from localemesh.model import snapshot,delta
from localemesh.full import evaluate
from localemesh.incremental import Incremental

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results'/'fanout-sweep-10000.json'
ROUTES=10_000
FANOUTS=[0,16,64,256,512,1024,1536,2048,3072,4096,6144,9999]
REPEATS=12
ORIGIN='https://fanout.localemesh.test'

def make_base():
    config={'schema':1,'config':{'locales':['en'],'origins':{ORIGIN:'site'},'aliases':{},
        'complete_manifest':True,'check_links':True},'pages':{}}
    observations={};routes=[f'{ORIGIN}/p/{i:05d}/' for i in range(ROUTES)]
    for i,route in enumerate(routes):
        key=f'k{i:05d}'
        config['pages'][route]={'key':key,'locale':'en','state':'published',
            'canonical_allowed':[route],'canonical_channels':['html'],'discovery':{}}
        observations[route]={'status':200,'lang':'en','key':key,
            'canonical':{'html':[route]},'alternates':{},'links':[]}
    return snapshot(config,observations,{}),routes,routes[-1]

BASE,ROUTE_LIST,HUB=make_base()

def make(fanout:int):
    # Shallow-copy immutable-by-convention facts, then replace only observations
    # whose link set differs. This avoids rebuilding 10,000 manifest/group facts
    # for every fan-out point while preserving exact fact equality semantics.
    old=dict(BASE)
    for route in ROUTE_LIST[:fanout]:
        key=('o',route);obs=copy.deepcopy(old[key]);obs['links']=[HUB];old[key]=obs
    new=dict(old);hub_key=('o',HUB);changed=copy.deepcopy(old[hub_key]);changed['status']=503;new[hub_key]=changed
    # Parsed builds create independent but equal value objects. Materialize two
    # independent snapshots outside the timed region so delta() does not benefit
    # from object-identity short cuts unavailable in normal before/after parses.
    return copy.deepcopy(old),copy.deepcopy(new),HUB

def stats(values):
    values=sorted(values);q=statistics.quantiles(values,n=4,method='inclusive')
    return {'median':statistics.median(values),'q1':q[0],'q3':q[2],
            'min':values[0],'max':values[-1],'n':len(values)}

def main():
    started=time.perf_counter();rows=[];summaries=[]
    for fanout in FANOUTS:
        old,new,hub=make(fanout);forward=delta(old,new);backward=delta(new,old)
        assert len(forward)==1 and ('o',hub) in forward
        engine=Incremental(old);assert not engine.issues()
        # Warm each direction while proving equivalence before measurement.
        engine.update(forward);assert engine.issues()==evaluate(new)
        engine.update(backward);assert engine.issues()==evaluate(old)
        current=old
        for repeat in range(REPEATS):
            target=new if repeat%2==0 else old;known=forward if repeat%2==0 else backward
            t=time.perf_counter_ns();fresh=delta(current,target);diff_ns=time.perf_counter_ns()-t
            assert fresh==known
            # Alternate order to reduce fixed ordering bias.
            if repeat%2==0:
                t=time.perf_counter_ns();full=evaluate(target);full_ns=time.perf_counter_ns()-t
                update=engine.update(known)
            else:
                update=engine.update(known)
                t=time.perf_counter_ns();full=evaluate(target);full_ns=time.perf_counter_ns()-t
            assert full==engine.issues(),(fanout,repeat,full^engine.issues())
            rows.append({'routes':ROUTES,'declared_fanout':fanout,'repeat':repeat,
                'direction':'forward' if repeat%2==0 else 'reverse','changed_facts':len(known),
                'full_ns':full_ns,'snapshot_diff_ns':diff_ns,**update,'agreement':1})
            current=target
        rr=[r for r in rows if r['declared_fanout']==fanout]
        summaries.append({'declared_fanout':fanout,
            'invalidated_owners':stats([r['invalidated_owners'] for r in rr]),
            'full_ms':stats([r['full_ns']/1e6 for r in rr]),
            'update_ms':stats([r['update_ns']/1e6 for r in rr]),
            'diff_update_ms':stats([(r['snapshot_diff_ns']+r['update_ns'])/1e6 for r in rr]),
            'update_only_ratio':statistics.median([r['full_ns']/r['update_ns'] for r in rr]),
            'with_diff_ratio':statistics.median([r['full_ns']/(r['snapshot_diff_ns']+r['update_ns']) for r in rr])})
        print('fanout',fanout,'invalidated',summaries[-1]['invalidated_owners']['median'],
              'full_ms',round(summaries[-1]['full_ms']['median'],3),
              'diff+update_ms',round(summaries[-1]['diff_update_ms']['median'],3),flush=True)
        # Durable partial measurements are explicitly marked incomplete until the final write.
        OUT.write_text(json.dumps({'complete':False,'scope':'authored in-memory semantic sweep',
            'routes':ROUTES,'fanouts_completed':[x['declared_fanout'] for x in summaries],
            'repeats':REPEATS,'rows':rows,'summary':summaries},indent=2)+'\n')
    first_update=next((x['declared_fanout'] for x in summaries if x['update_ms']['median']>=x['full_ms']['median']),None)
    first_total=next((x['declared_fanout'] for x in summaries if x['diff_update_ms']['median']>=x['full_ms']['median']),None)
    result={'complete':True,'scope':'authored in-memory semantic sweep; no parsing, framework build, public site, or deployment',
      'routes':ROUTES,'fanouts':FANOUTS,'repeats':REPEATS,'rows':rows,'summary':summaries,
      'first_measured_update_only_not_faster':first_update,
      'first_measured_diff_plus_update_not_faster':first_total,
      'python':platform.python_version(),'maxrss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
      'wall_s':time.perf_counter()-started,
      'interpretation_limit':'Measured grid crossing, not an analytic universal threshold; timings are repeated in one process.'}
    OUT.write_text(json.dumps(result,indent=2)+'\n')
    print('DONE',OUT,result['wall_s'],'s','crossings',first_update,first_total,flush=True)
if __name__=='__main__':main()
