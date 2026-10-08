#!/usr/bin/env python3
"""Pinned, executed upstream page API; no sitemap or complete-CLI claims."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import csv,gzip,json,subprocess,tempfile,time
from collections import Counter
from localemesh.fixtures import SITES,make_site,write_fixture
from localemesh.cases import CASES,change
from localemesh.io import load_build
from localemesh.full import evaluate
ROOT=Path(__file__).resolve().parents[1]

# The shared denominator is selected from semantics, not from baseline outcomes:
# reachable HTML/HTTP alternates and reciprocal link obligations; canonical is
# excluded because an explicit allowed set and self-canonical are not equivalent.
SHARED={'removed_stale','rename_stale','prefix_stale'}

def response_capture(manifest,build):
    responses={}
    for origin,dirname in manifest['config']['origins'].items():
        directory=build/dirname
        for p in sorted(directory.rglob('*.html')):
            name=p.relative_to(directory).as_posix()
            if name=='index.html':path='/'
            elif name.endswith('/index.html'):path='/'+name[:-10]
            else:path='/'+name
            responses[origin+path]={'status':200,'headers':{'content-type':'text/html'},'body':p.read_text()}
    h=build/'_headers.json'
    if h.exists():
        for route,record in json.loads(h.read_text()).items():
            r=responses.setdefault(route,{'status':200,'headers':{},'body':''})
            r['status']=record.get('status',200)
            if record.get('location'):r['headers']['location']=record['location']
            if record.get('link'):r['headers']['link']=', '.join(record['link'])
    # Starting points are emitted HTML pages, NOT missing manifest declarations.
    return responses

def main():
    t=time.perf_counter();out=ROOT/'results';out.mkdir(exist_ok=True)
    subprocess.run([sys.executable,str(ROOT/'vendor/crawlcove/prepare.py')],check=True)
    rows=[];requests=0;pages=0;node=None
    with tempfile.TemporaryDirectory(prefix='localemesh-external-') as temp, gzip.open(out/'external-page-raw.jsonl.gz','wt',encoding='utf8') as raw:
        work=Path(temp)/'case'
        for site,*_ in SITES:
            base=make_site(site)
            for name,label,rule in CASES:
                data=change(base,name);write_fixture(work,*data)
                manifest=json.loads((work/'manifest.json').read_text())
                capture=response_capture(manifest,work/'build')
                routes=sorted(capture)
                payload={'responses':capture,'routes':routes}
                process=subprocess.run(['node',str(ROOT/'scripts/external_page_harness.mjs')],input=json.dumps(payload),
                                       text=True,capture_output=True,check=True,timeout=60)
                result=json.loads(process.stdout);node=result['node'];requests+=result['requests'];pages+=len(routes)
                errors=[f for page in result['results'] for f in page['findings'] if f['severity']=='error']
                warnings=[f for page in result['results'] for f in page['findings'] if f['severity']=='warning']
                findings=evaluate(load_build(work/'manifest.json',work/'build'))
                selected={ch for s in manifest['pages'].values() for ch in s.get('discovery',{})}
                shared=name in SHARED and bool(selected & {'html','http'})
                rows.append({'site':site,'case':name,'label':label,'observed_routes':len(routes),
                             'selected_channels':'+'.join(sorted(selected)),'shared_reachability_scope':int(shared),
                             'upstream_error':int(bool(errors)),'upstream_errors':len(errors),'upstream_warnings':len(warnings),
                             'localemesh_error':int(any(i.category=='release' for i in findings)),
                             'error_codes':'+'.join(sorted({f['code'] for f in errors})),
                             'warning_codes':'+'.join(sorted({f['code'] for f in warnings}))})
                raw.write(json.dumps({'site':site,'case':name,'label':label,**result})+'\n')
            print('upstream page-mode',site,len(CASES),'releases',flush=True)
    with (out/'external-page-releases.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    shared=[r for r in rows if r['shared_reachability_scope']]
    contrasts={}
    for name in ['coherent_identity_swap','cross_locale_canonical_allowed','partial_coverage','missing_translation_allowed','optional_xdefault','no_optional_channels']:
        group=[r for r in rows if r['case']==name]
        contrasts[name]={'releases':len(group),'upstream_errors':sum(r['upstream_error'] for r in group),
                         'localemesh_errors':sum(r['localemesh_error'] for r in group)}
    summary={'scope':'Executed unchanged upstream checkPage functions via dependency-pruned module; no CLI/sitemap/native-builder evidence',
        'version':'1.0.0','commit':'ffa29b71872755977068ad3246000f88450dec22','node':node,
        'releases':len(rows),'page_invocations':pages,'local_response_requests':requests,'external_network_requests':0,
        'shared_reachability_releases':len(shared),'shared_upstream_detected':sum(r['upstream_error'] for r in shared),
        'shared_localemesh_detected':sum(r['localemesh_error'] for r in shared),'contrasts':contrasts,
        'warning_threshold':'Only upstream severity=error counts; warnings retained verbatim',
        'wall_s':time.perf_counter()-t}
    (out/'external-page-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
