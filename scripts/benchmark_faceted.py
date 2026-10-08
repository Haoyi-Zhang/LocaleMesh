#!/usr/bin/env python3
"""Matched-obligation record vs projected-read caches, including result export.

Every timed incremental check materializes its issue set, just as the full scan
does. Complete-snapshot diff and safe transaction normalization are reported
separately. Synthetic generated route sets are never labeled independent sites.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,copy,gc,json,platform,resource,time,tracemalloc
from localemesh.fixtures import make_site,to_facts
from localemesh.cases import change
from localemesh.model import delta
from localemesh.full import evaluate
from localemesh.incremental import Incremental
from localemesh.faceted import FacetedIncremental
from localemesh.transaction import ReleaseSession
ROOT=Path(__file__).resolve().parents[1]
KINDS=['local_canonical','deleted_page','unused_alias','global_link_policy','hub_canonical','hub_status']

def main():
    p=argparse.ArgumentParser();p.add_argument('--routes',type=int,required=True);p.add_argument('--repeats',type=int,default=12);a=p.parse_args()
    if a.routes%2 or a.routes<4:raise ValueError('Use an even route count >=4')
    start=time.perf_counter();rows=[];memory={}
    clean=to_facts(make_site('A1',a.routes//2))
    for name,cls in [('record',Incremental),('projected',FacetedIncremental)]:
        gc.collect();tracemalloc.start();t=time.perf_counter_ns();e=cls(clean);init=time.perf_counter_ns()-t
        live,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        memory[name]={'live_python_bytes':live,'peak_python_bytes':peak,'dependency_edges':e.edge_count,
                      'traced_init_ns':init,'includes_owned_fact_copy':True}
        del e;gc.collect()
    for kind in KINDS:
        data=make_site('A1',a.routes//2);hub=next(iter(data[1]))
        if kind.startswith('hub_'):
            for o in data[1].values():o['links']=[hub]
        old=to_facts(data)
        if kind in {'local_canonical','hub_canonical'}:new=to_facts(change(data,'wrong_canonical'))
        elif kind=='deleted_page':new=to_facts(change(data,'removed_stale'))
        else:
            new=copy.deepcopy(old)
            if kind=='unused_alias':new[('cfg',)]['aliases'][hub+'unused-alias/']=hub
            elif kind=='global_link_policy':new[('cfg',)]['check_links']=False
            else:new[('o',hub)]['status']=404
        engines={'record':Incremental(old),'projected':FacetedIncremental(old)}
        safe=ReleaseSession(old,engine_class=FacetedIncremental)
        forward,reverse=delta(old,new),delta(new,old)
        # Untimed warm-up reaches both directions, followed by steady-state pairs.
        for goal,changes in [(new,forward),(old,reverse)]:
            expected=evaluate(goal)
            for e in engines.values():e.update(changes);assert e.issues()==expected
            safe.apply({k:v for k,v in changes.items() if k[0]!='g'});assert safe.issues()==expected
        current=old
        for repeat in range(a.repeats):
            target,patch=(new,forward) if repeat%2==0 else (old,reverse)
            t=time.perf_counter_ns();computed=delta(current,target);diff=time.perf_counter_ns()-t
            assert computed==patch
            timed={};outputs={};stats={}
            order=['full','record','projected']
            order=order[repeat%3:]+order[:repeat%3]
            for name in order:
                t=time.perf_counter_ns()
                if name=='full':outputs[name]=evaluate(target)
                else:
                    stats[name]=engines[name].update(patch)
                    outputs[name]=engines[name].issues()
                timed[name]=time.perf_counter_ns()-t
            assert outputs['full']==outputs['record']==outputs['projected'],(a.routes,kind,repeat)
            primary={k:v for k,v in patch.items() if k[0]!='g'}
            t=time.perf_counter_ns();safe_stats=safe.apply(primary);safe_out=safe.issues();safe_ns=time.perf_counter_ns()-t
            assert safe_out==outputs['full']
            rows.append({'routes':a.routes,'kind':kind,'repeat':repeat,'direction':'forward' if repeat%2==0 else 'reverse',
                 'order':order,'full_ns':timed['full'],'record_ns':timed['record'],'projected_ns':timed['projected'],
                 'safe_projected_ns':safe_ns,'snapshot_diff_ns':diff,'record_owners':stats['record']['invalidated_owners'],
                 'projected_owners':stats['projected']['invalidated_owners'],
                 'compared_projections':stats['projected']['projected_reads_compared'],
                 'changed_projections':stats['projected']['changed_projections'],
                 'safe_preparation_ns':safe_stats['preparation_ns'],'issues':len(outputs['full']),'agreement':True})
            current=target
        print(a.routes,kind,'complete',round(time.perf_counter()-start,2),'s',flush=True)
    result={'python':platform.python_version(),'routes':a.routes,'repeats':a.repeats,'rows':rows,'memory':memory,
       'scope':'synthetic same-generator routes; no build, parsing, or missing-file detection in update timings',
       'timing':'full/record/projected rotation; all issue sets exported; safe API includes validation and derived identity buckets',
       'maxrss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'wall_s':time.perf_counter()-start}
    (ROOT/'results'/f'projected-{a.routes}.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
