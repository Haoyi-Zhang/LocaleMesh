#!/usr/bin/env python3
"""Synthetic scaling only. Parsing/differencing and initialization are separate."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,copy,gc,json,resource,tempfile,time,tracemalloc
from localemesh.fixtures import make_site,to_facts,write_fixture
from localemesh.cases import change
from localemesh.full import evaluate
from localemesh.incremental import Incremental
from localemesh.model import delta
from localemesh.io import load_build
ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--routes',type=int,required=True)
    parser.add_argument('--repeats',type=int,default=12);parser.add_argument('--kind',default='all');a=parser.parse_args()
    if a.routes%2:raise ValueError('Use an even route count for two locale variants')
    start=time.perf_counter();print('start',a.routes,flush=True);data=make_site('A1',a.routes//2);f0=to_facts(data)
    t=time.perf_counter_ns();initial=Incremental(f0);init_ns=time.perf_counter_ns()-t
    assert not initial.issues();del initial;gc.collect()
    tracemalloc.start();memory_engine=Incremental(f0)
    live,peak=tracemalloc.get_traced_memory();tracemalloc.stop();edges=memory_engine.edge_count
    del memory_engine;gc.collect();rows=[]
    print('memory indexed',a.routes,time.perf_counter()-start,flush=True)
    for kind in ['local_canonical','deleted_page','global_alias_policy','hub_observation']:
        if a.kind!='all' and kind!=a.kind:continue
        print('kind',kind,'elapsed',time.perf_counter()-start,flush=True)
        baseline=copy.deepcopy(data)
        if kind=='hub_observation':
            hub=next(iter(baseline[1]))
            for ob in baseline[1].values():ob['links']=[hub]
        old=to_facts(baseline)
        if kind in ('local_canonical','hub_observation'):candidate=change(baseline,'wrong_canonical')
        elif kind=='deleted_page':candidate=change(baseline,'removed_stale')
        else:
            candidate=copy.deepcopy(baseline);first=next(iter(candidate[1]))
            candidate[0]['config']['aliases'][first+'index.html']=first
        new=to_facts(candidate);forward=delta(old,new);backward=delta(new,old)
        engine=Incremental(old)
        engine.update(forward);assert engine.issues()==evaluate(new)
        engine.update(backward);assert engine.issues()==evaluate(old)
        current=old
        for repeat in range(a.repeats):
            target=new if repeat%2==0 else old;d=forward if repeat%2==0 else backward
            t=time.perf_counter_ns();fresh_delta=delta(current,target);diff_ns=time.perf_counter_ns()-t
            assert fresh_delta==d
            if repeat%2==0:
                t=time.perf_counter_ns();full=evaluate(target);full_ns=time.perf_counter_ns()-t
                stats=engine.update(d)
            else:
                stats=engine.update(d)
                t=time.perf_counter_ns();full=evaluate(target);full_ns=time.perf_counter_ns()-t
            assert full==engine.issues(),(a.routes,kind,repeat)
            rows.append({'routes':a.routes,'kind':kind,'repeat':repeat,'direction':'forward' if repeat%2==0 else 'reverse',
                'full_ns':full_ns,'snapshot_diff_ns':diff_ns,**stats,'agreement':1})
            current=target
    print('timing finished',time.perf_counter()-start,flush=True)
    io_rows=[]
    with tempfile.TemporaryDirectory(prefix='localemesh-scale-') as tmp:
        p=Path(tmp)/'case'
        t=time.perf_counter_ns();write_fixture(p,*data);emission_ns=time.perf_counter_ns()-t
        bytes_on_disk=sum(x.stat().st_size for x in (p/'build').rglob('*') if x.is_file())
        for j in range(3):
            print('parse',j,'elapsed',time.perf_counter()-start,flush=True)
            t=time.perf_counter_ns();parsed=load_build(p/'manifest.json',p/'build');parse_ns=time.perf_counter_ns()-t
            t=time.perf_counter_ns();out=evaluate(parsed);validation_ns=time.perf_counter_ns()-t
            assert not out
            io_rows.append({'repeat':j,'parse_snapshot_ns':parse_ns,'full_ns':validation_ns})
        count=sum(1 for _ in (p/'build').rglob('*.html'));assert count==a.routes
    result={'routes':a.routes,'kind':'synthetic-authored','repeats':a.repeats,'rows':rows,
        'index_init_ns':init_ns,'index_live_python_bytes':live,'index_peak_python_bytes':peak,
        'dependency_edges':edges,'maxrss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'disk_build_bytes':bytes_on_disk,'emitted_html_files':count,'fixture_emission_ns':emission_ns,
        'io':io_rows,'wall_s':time.perf_counter()-start}
    dest=ROOT/'results'/(f'scale-{a.routes}.json' if a.kind=='all' else f'scale-{a.routes}-{a.kind}.json');dest.write_text(json.dumps(result,indent=2))
    print(a.routes,'routes done',result['wall_s'],'seconds',flush=True)
if __name__=='__main__':main()
