#!/usr/bin/env python3
"""Bounded offline evaluation. All site instances are explicitly authored fixtures."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import csv,json,time,tempfile,random,copy,resource,platform
from localemesh.fixtures import SITES,make_site,to_facts,write_fixture
from localemesh.cases import CASES,change
from localemesh.io import load_build
from localemesh.model import delta
from localemesh.full import evaluate
from localemesh.incremental import Incremental
from localemesh.faceted import FacetedIncremental
from localemesh.coalesced import CoalescedIncremental
from localemesh.sliced import SlicedIncremental
from localemesh.transaction import ReleaseSession
from localemesh.baselines import dead_links,html_annotations,policy_blind,manifest_presence,joint_output
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results'
def record_csv(path,rows):
    with path.open('w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
def main():
    start=time.perf_counter();OUT.mkdir(exist_ok=True);(OUT/'findings').mkdir(exist_ok=True)
    rows=[];site_rows=[]
    for row in SITES:
        site=row[0];base=make_site(site)
        write_fixture(ROOT/'inputs'/site,*base)
        a=load_build(ROOT/'inputs'/site/'manifest.json',ROOT/'inputs'/site/'build')
        assert not evaluate(a)
        site_begin=time.perf_counter()
        with tempfile.TemporaryDirectory(prefix='localemesh-case-') as temp:
            work=Path(temp)/'candidate'
            for name,label,rule in CASES:
                data=change(base,name)
                t=time.perf_counter_ns();write_fixture(work,*data);emit_ns=time.perf_counter_ns()-t
                t=time.perf_counter_ns();b=load_build(work/'manifest.json',work/'build');parse_ns=time.perf_counter_ns()-t
                t=time.perf_counter_ns();full=evaluate(b);full_ns=time.perf_counter_ns()-t
                t=time.perf_counter_ns();d=delta(a,b);diff_ns=time.perf_counter_ns()-t
                inc=Incremental(a);stats=inc.update(d);same=(full==inc.issues())
                assert same,(site,name,full^inc.issues())
                projected=FacetedIncremental(a);projected.update(d);assert projected.issues()==full
                safe=ReleaseSession(a,engine_class=FacetedIncremental);safe.apply({k:v for k,v in d.items() if k[0]!='g'});assert safe.issues()==full
                compact=CoalescedIncremental(a);compact_stats=compact.update(d);assert compact.issues()==full
                compact_safe=ReleaseSession(a,engine_class=CoalescedIncremental);compact_safe.apply({k:v for k,v in d.items() if k[0]!='g'});assert compact_safe.issues()==full
                sliced=SlicedIncremental(a);sliced_stats=sliced.update(d);assert sliced.issues()==full
                sliced_safe=ReleaseSession(a,engine_class=SlicedIncremental);sliced_safe.apply({k:v for k,v in d.items() if k[0]!='g'});assert sliced_safe.issues()==full
                if label=='clean':assert not full,(site,name,full)
                if label=='ambiguity':assert full and not any(i.category=='release' for i in full)
                if rule:assert rule in {i.code for i in full},(site,name,rule,full)
                broken=Incremental(a);broken.update(d,broken_drop_old=True)
                mp=manifest_presence(b);dl=dead_links(b);hc=html_annotations(b);joint=joint_output(b);blind=policy_blind(b)
                is_release=lambda seq:any(i.category=='release' for i in seq)
                no_identity=[i for i in full if i.code not in ('CONTENT_ID','DISCOVERY_ID','IDENTITY_COLLISION','TARGET_IDENTITY_UNKNOWN')]
                no_cross=[i for i in full if i.code!='CHANNEL_CONFLICT']
                rows.append({'site':site,'case':name,'label':label,'expected_rule':rule or '',
                    'routes':len(data[1]),'emission_kind':'authored_fixture','native_build_status':'UNAVAILABLE',
                    'release_findings':sum(i.category=='release' for i in full),'ambiguities':sum(i.category=='ambiguity' for i in full),
                    'full_detected':int(is_release(full)),'incremental_detected':int(is_release(inc.issues())),
                    'manifest_detected':int(bool(mp)),'deadlink_detected':int(bool(dl)),'html_detected':int(bool(hc)),'joint_detected':int(bool(joint)),'blind_detected':int(bool(blind)),
                    'no_identity_detected':int(is_release(no_identity)),'no_crosschannel_detected':int(is_release(no_cross)),
                    'agreement':int(same),'projected_agreement':int(projected.issues()==full),'transaction_agreement':int(safe.issues()==full),'coalesced_agreement':int(compact.issues()==full),'coalesced_transaction_agreement':int(compact_safe.issues()==full),'sliced_agreement':int(sliced.issues()==full),'sliced_transaction_agreement':int(sliced_safe.issues()==full),'sliced_invalidated_readers':sliced_stats['invalidated_readers'],'drop_old_agreement':int(full==broken.issues()),
                    'fixture_emit_ns':emit_ns,'parse_snapshot_ns':parse_ns,'snapshot_diff_ns':diff_ns,
                    'full_ns':full_ns,**stats})
                (OUT/'findings'/f'{site}.{name}.json').write_text(json.dumps({'site':site,'case':name,'label':label,
                    'full':[i.json() for i in sorted(full)],'manifest':sorted(mp),'deadlink':sorted(dl),'html':sorted(hc),'joint':sorted(joint),'blind':sorted(blind),
                    'incremental_difference':[], 'drop_old_difference':[i.json() for i in sorted(full^broken.issues())]},indent=2))
        site_rows.append({'site':site,'origin_kind':'authored-fixture','routes':len(base[1]),'content_keys':row[2],
            'locales':','.join(row[3]),'channels':','.join(row[4]),'origins':len(base[0]['config']['origins']),
            'release_cases':len(CASES),'wall_s':time.perf_counter()-site_begin})
        print('evaluated',site,len(base[1]),len(CASES),flush=True)
    record_csv(OUT/'releases.csv',rows);record_csv(OUT/'sites.csv',site_rows)
    held=[];rng=random.Random(27182818)
    clean_names=['partial_coverage','cross_locale_canonical_allowed','route_alias_allowed','missing_translation_allowed','fallback_allowed','redirect_alias_allowed','optional_xdefault']
    bad_names=['removed_stale','wrong_canonical','wrong_html_locale','missing_required_alternate','key_reassigned','missing_route']
    for row in SITES:
        base=make_site(row[0]);prior=to_facts(base);engine=Incremental(prior);projected=FacetedIncremental(prior);safe=ReleaseSession(prior,engine_class=FacetedIncremental);compact=CoalescedIncremental(prior);compact_safe=ReleaseSession(prior,engine_class=CoalescedIncremental);sliced=SlicedIncremental(prior);sliced_safe=ReleaseSession(prior,engine_class=SlicedIncremental)
        for j in range(16):
            data=copy.deepcopy(base);chosen=[];keys=rng.sample([0,3,6,9],k=3)
            for ki in keys:
                op=rng.choice(clean_names);data=change(data,op,ki);chosen.append([op,ki])
            label='clean'
            if j%2:
                untouched=next(x for x in [0,3,6,9] if x not in keys)
                op=rng.choice(bad_names);data=change(data,op,untouched);chosen.append([op,untouched]);label='defect'
            nxt=to_facts(data);d=delta(prior,nxt);stats=engine.update(d);verdict=evaluate(nxt)
            projected.update(d);safe.apply({k:v for k,v in d.items() if k[0]!='g'});assert projected.issues()==safe.issues()==verdict
            compact.update(d);compact_safe.apply({k:v for k,v in d.items() if k[0]!='g'});assert compact.issues()==compact_safe.issues()==verdict
            sliced_stats=sliced.update(d);sliced_safe.apply({k:v for k,v in d.items() if k[0]!='g'});assert sliced.issues()==sliced_safe.issues()==verdict
            expected=any(i.category=='release' for i in verdict)==(label=='defect');same=engine.issues()==verdict
            assert expected and same,(row[0],j,chosen,verdict^engine.issues())
            held.append({'site':row[0],'case':f'C{j+1:02d}','label':label,'operations':json.dumps(chosen),
                'agreement':int(same),'projected_agreement':1,'transaction_agreement':1,'coalesced_agreement':1,'coalesced_transaction_agreement':1,'sliced_agreement':1,'sliced_transaction_agreement':1,'sliced_invalidated_readers':sliced_stats['invalidated_readers'],'expected_outcome':int(expected),'release_findings':sum(i.category=='release' for i in verdict),**stats})
            prior=nxt
    record_csv(OUT/'composition_holdout.csv',held)
    (OUT/'evaluation_run.json').write_text(json.dumps({'wall_s':time.perf_counter()-start,
        'maxrss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'python':platform.python_version(),
        'named_releases':len(rows),'composition_holdout':len(held),'unit_suite':'results/tests.log',
        'corpus_kind':'authored fixtures; no public or industrial sites',
        'rule_freeze_status':'The 96 compositions are regression cases reused during development, not a fresh holdout.'},indent=2))
    print('DONE',len(rows),'named;',len(held),'composition regressions;',time.perf_counter()-start,'s',flush=True)
if __name__=='__main__':main()
