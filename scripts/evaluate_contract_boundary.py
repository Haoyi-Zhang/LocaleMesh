#!/usr/bin/env python3
"""Replay the archived permissive boundary against explicit invalid-input cases."""
from pathlib import Path
import sys,copy,json,importlib.util
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from localemesh import schema
from localemesh.fixtures import make_site,to_facts
from localemesh.transaction import ReleaseSession
from localemesh.coalesced import CoalescedIncremental
from localemesh.full import evaluate

def main():
    spec=importlib.util.spec_from_file_location('localemesh._legacy_schema',ROOT/'vendor/legacy_schema.py')
    previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
    cases=[];base={'key':'x','locale':'en'}
    for key in ['canoncal_required','sitemp','discovry','fallback']:
        cases.append((key,'normalize_spec',{**base,key:True}))
    for key in ['require','recipocal']:
        cases.append((key,'normalize_spec',{**base,'discovery':{'html':{key:['de']}}}))
    for key in ['check_link','complete_manifst']:
        cases.append((key,'normalize_config',{'origins':{},key:True}))
    cases.append(('targetless_redirect','normalize_spec',{**base,'state':'redirect'}))
    for value in ['en',True,{},[None]]:
        cases.append(('locale_type_'+type(value).__name__,'normalize_config',{'origins':{},'locales':value}))
    rows=[]
    for name,method,value in cases:
        row={'case':name,'method':method,'input':value,'expected':'reject'}
        for label,module in [('legacy',previous),('current',schema)]:
            try:result=getattr(module,method)(value);row[label]={'accepted':True,'output':result}
            except ValueError as e:row[label]={'accepted':False,'reason':str(e)}
        assert row['legacy']['accepted'] and not row['current']['accepted'],name
        rows.append(row)
    initial=to_facts(make_site('A1',3));route=next(k for k in initial if k[0]=='m')
    bad=copy.deepcopy(initial[route]);bad['discovery']['html']['require']=['de']
    from localemesh.sliced import SlicedIncremental
    rollback_checks = 0
    for engine_class in (CoalescedIncremental, SlicedIncremental):
        session=ReleaseSession(initial,engine_class=engine_class)
        try:session.apply({('o',route[1]):None,route:bad})
        except ValueError:pass
        else:raise AssertionError('Malformed transaction was accepted')
        assert session.revision==0 and session.facts()==initial and session.issues()==evaluate(initial)
        rollback_checks += 1
    report={'cases':rows,'counts':{'legacy_accepted_invalid':len(rows),'strict_rejected':len(rows),'atomic_rollback_checks':rollback_checks},
       'scope':'Explicit schema cases from same research process. Archived LocaleMesh boundary code, not an upstream framework bug. Nonsemantic metadata remains permitted only in extensions at strict policy boundaries.'}
    (ROOT/'results/contract-boundary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report['counts']))
if __name__=='__main__':main()
