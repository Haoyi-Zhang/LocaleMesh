#!/usr/bin/env python3
"""Paired exact-footprint representation experiment; identical owner predicate.

All paths materialize issue sets. Core comparisons rotate execution order;
transaction comparisons rotate both safe engines. Diff is separately charged.
Memory includes each cache's owned facts, measured without retaining other caches.
"""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import argparse,copy,gc,json,platform,resource,time,tracemalloc
from localemesh.fixtures import make_site,to_facts
from localemesh.cases import change
from localemesh.model import delta
from localemesh.full import evaluate
from localemesh.incremental import Incremental
from localemesh.faceted import FacetedIncremental
from localemesh.coalesced import CoalescedIncremental
from localemesh.transaction import ReleaseSession
KINDS=['local_canonical','deleted_page','unused_alias','global_link_policy','hub_canonical','hub_status']

def main():
    p=argparse.ArgumentParser();p.add_argument('--routes',type=int,required=True);p.add_argument('--repeats',type=int,default=12);a=p.parse_args()
    if a.routes%2 or a.routes<4 or a.repeats<2:raise ValueError('Even routes >=4 and repeats >=2 required')
    start=time.perf_counter();rows=[];memory={};clean=to_facts(make_site('A1',a.routes//2))
    for name,cls in [('record',Incremental),('projected',FacetedIncremental),('coalesced',CoalescedIncremental)]:
        gc.collect();tracemalloc.start();t=time.perf_counter_ns();engine=cls(clean);init=time.perf_counter_ns()-t
        live,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        memory[name]={'live_python_bytes':live,'peak_python_bytes':peak,'dependency_edges':engine.edge_count,
          'logical_projection_edges':getattr(engine,'projection_edges',None),'reverse_groups':getattr(engine,'reverse_groups',None),
          'interned_footprints':len(engine._pool) if hasattr(engine,'_pool') else None,
          'traced_init_ns':init,'includes_owned_fact_copy':True}
        del engine;gc.collect()
    for kind in KINDS:
        data=make_site('A1',a.routes//2);hub=next(iter(data[1]))
        if kind.startswith('hub_'):
            for obs in data[1].values():obs['links']=[hub]
        old=to_facts(data)
        if kind in {'local_canonical','hub_canonical'}:new=to_facts(change(data,'wrong_canonical'))
        elif kind=='deleted_page':new=to_facts(change(data,'removed_stale'))
        else:
            new=copy.deepcopy(old)
            if kind=='unused_alias':new[('cfg',)]['aliases'][hub+'unused-alias/']=hub
            elif kind=='global_link_policy':new[('cfg',)]['check_links']=False
            else:new[('o',hub)]['status']=404
        engines={'projected':FacetedIncremental(old),'coalesced':CoalescedIncremental(old)}
        safe={'projected':ReleaseSession(old,engine_class=FacetedIncremental),
              'coalesced':ReleaseSession(old,engine_class=CoalescedIncremental)}
        forward,reverse=delta(old,new),delta(new,old)
        for goal,patch in [(new,forward),(old,reverse)]:
            expected=evaluate(goal)
            for engine in engines.values():engine.update(patch);assert engine.issues()==expected
            for engine in safe.values():engine.apply({k:v for k,v in patch.items() if k[0]!='g'});assert engine.issues()==expected
        current=old
        for repeat in range(a.repeats):
            goal,patch=(new,forward) if repeat%2==0 else (old,reverse)
            t=time.perf_counter_ns();computed=delta(current,goal);diff=time.perf_counter_ns()-t;assert computed==patch
            names=['full','projected','coalesced'];order=names[repeat%3:]+names[:repeat%3]
            times={};results={};stats={}
            for name in order:
                t=time.perf_counter_ns()
                if name=='full':results[name]=evaluate(goal)
                else:stats[name]=engines[name].update(patch);results[name]=engines[name].issues()
                times[name]=time.perf_counter_ns()-t
            assert results['full']==results['projected']==results['coalesced']
            assert stats['projected']['invalidated_owners']==stats['coalesced']['invalidated_owners']
            primary={k:v for k,v in patch.items() if k[0]!='g'}
            safe_order=['projected','coalesced'] if repeat%2==0 else ['coalesced','projected'];safe_times={}
            for name in safe_order:
                t=time.perf_counter_ns();safe[name].apply(primary);got=safe[name].issues();safe_times[name]=time.perf_counter_ns()-t
                assert got==results['full']
            rows.append({'routes':a.routes,'kind':kind,'repeat':repeat,'direction':'forward' if repeat%2==0 else 'reverse',
              'core_order':order,'safe_order':safe_order,'snapshot_diff_ns':diff,
              **{k+'_ns':v for k,v in times.items()},**{'safe_'+k+'_ns':v for k,v in safe_times.items()},
              'projected_owners':stats['projected']['invalidated_owners'],'coalesced_owners':stats['coalesced']['invalidated_owners'],
              'expanded_edges_projected':engines['projected'].edge_count,'expanded_edges_coalesced':engines['coalesced'].projection_edges,
              'coalesced_group_edges':engines['coalesced'].edge_count,'coalesced_reverse_groups':engines['coalesced'].reverse_groups,
              'coalesced_interned_footprints':len(engines['coalesced']._pool),
              'projected_comparisons':stats['projected']['projected_reads_compared'],
              'coalesced_comparisons':stats['coalesced']['projected_reads_compared'],
              'issues':len(results['full']),'agreement':True})
            assert rows[-1]['expanded_edges_projected']==rows[-1]['expanded_edges_coalesced']
            current=goal
        del engines,safe;gc.collect()
        print(a.routes,kind,'completed',round(time.perf_counter()-start,2),'s',flush=True)
    result={'routes':a.routes,'repeats':a.repeats,'python':platform.python_version(),'rows':rows,'memory':memory,
      'wall_s':time.perf_counter()-start,'maxrss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
      'scope':'Synthetic routes. Same check_owner and exact projected reads; compressed representation only. Complete-snapshot diff charged separately; no page parse or builder cost in update measurements.',
      'timing':'Two-direction warmup; rotating core engine and transaction order; issue sets materialized on every path. Repeated timings are not independent sites.'}
    (ROOT/'results'/f'coalesced-{a.routes}.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
