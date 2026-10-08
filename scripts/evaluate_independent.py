#!/usr/bin/env python3
"""Evaluate four separately implemented local emitter/adaptation families.

Three are original laboratory emitters.  The fourth preserves selected front-matter
facts from a pinned permissively licensed Jekyll Polyglot repository, but is still a
LocaleMesh local adaptation rather than a native Jekyll build.  Expected labels and
mutations remain authored by the same research team.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import copy,csv,json,re,shutil,tempfile,time,xml.etree.ElementTree as ET
from urllib.parse import urlsplit
from localemesh.emitters import json_html,toml_sitemap,csv_headers,polyglot_public
from localemesh.io import load_build
from localemesh.model import delta
from localemesh.full import evaluate
from localemesh.incremental import Incremental
from localemesh.faceted import FacetedIncremental
from localemesh.coalesced import CoalescedIncremental
from localemesh.sliced import SlicedIncremental
from localemesh.transaction import ReleaseSession
from localemesh.baselines import dead_links,html_annotations,policy_blind,manifest_presence,joint_output
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'independent_sources';OUT=ROOT/'results'
FAMILIES={
 'JH':(SRC/'json_html',json_html.build,'html'),
 'TS':(SRC/'toml_sitemap',toml_sitemap.build,'sitemap'),
 'CH':(SRC/'csv_headers',csv_headers.build,'http'),
 'PJ':(SRC/'polyglot_public',polyglot_public.build,'html'),
}
CASES=[
 ('clean','clean',None),('legal_partial','clean',None),('cross_locale_canonical_allowed','clean',None),
 ('identity_swap','defect','DISCOVERY_ID'),('removed_page','defect','MISSING_ROUTE'),
 ('wrong_lang','defect','LANGUAGE'),('wrong_canonical','defect','CANONICAL_POLICY'),
 ('missing_required','defect','DISCOVERY_MISSING'),('declaration_conflict','ambiguity','DECLARATION_CONFLICT'),
 ('duplicate_identity','ambiguity','IDENTITY_COLLISION'),
]

def record_csv(path,rows):
    with path.open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def route_file(manifest,build,route):
    p=urlsplit(route);origin=p.scheme+'://'+p.netloc;mount=manifest['config']['origins'][origin]
    rel=p.path.lstrip('/')
    if not rel or rel.endswith('/'):rel+='index.html'
    elif not rel.endswith('.html'):rel+='/index.html'
    return build/mount/rel

def grouped(manifest):
    result={}
    for route,s in manifest['pages'].items():result.setdefault(s['key'],{})[s['locale']]=route
    return result

def replace_html_alts(path,pairs):
    text=path.read_text(encoding='utf8')
    text=re.sub(r'\n?<link rel="alternate"[^>]*>', '', text)
    block=''.join(f'\n<link rel="alternate" hreflang="{l}" href="{u}">' for l,u in pairs)
    text=text.replace('</head>',block+'\n</head>')
    path.write_text(text,encoding='utf8')

def replace_sitemap_alts(build,route,pairs):
    path=build/'sitemap.xml';tree=ET.parse(path);root=tree.getroot();x='{http://www.w3.org/1999/xhtml}link'
    for node in root:
        loc=next((c.text for c in node if c.tag.rsplit('}',1)[-1]=='loc'),None)
        if loc!=route:continue
        for child in list(node):
            if child.tag==x:node.remove(child)
        for l,u in pairs:ET.SubElement(node,x,{'rel':'alternate','hreflang':l,'href':u})
        break
    tree.write(path,encoding='utf-8',xml_declaration=True)

def replace_http_alts(build,route,pairs):
    path=build/'_headers.json';data=json.loads(path.read_text())
    data.setdefault(route,{'status':200})['link']=[f'<{u}>; rel="alternate"; hreflang="{l}"' for l,u in pairs]
    path.write_text(json.dumps(data,indent=2)+'\n')

def set_pairs(manifest,build,channel,route,pairs):
    if channel=='html':replace_html_alts(route_file(manifest,build,route),pairs)
    elif channel=='sitemap':replace_sitemap_alts(build,route,pairs)
    elif channel=='http':replace_http_alts(build,route,pairs)
    else:raise ValueError(channel)

def patch_canonical(manifest,build,route,target):
    path=route_file(manifest,build,route);text=path.read_text(encoding='utf8')
    text=re.sub(r'<link rel="canonical" href="[^"]+">',f'<link rel="canonical" href="{target}">',text,count=1)
    path.write_text(text,encoding='utf8')

def patch_lang(manifest,build,route,locale):
    path=route_file(manifest,build,route);text=path.read_text(encoding='utf8')
    text=re.sub(r'<html lang="[^"]*">',f'<html lang="{locale}">',text,count=1)
    path.write_text(text,encoding='utf8')

def mutate(name,manifest,build,channel):
    groups=grouped(manifest);keys=sorted(groups);locales=list(manifest['config']['locales'])
    g0,g1=groups[keys[0]],groups[keys[1]];last=locales[-1]
    first=g0[locales[0]];last_route=g0[last]
    if name=='clean':return
    if name=='legal_partial':
        for locale,route in g0.items():
            set_pairs(manifest,build,channel,route,[(locale,route)])
            manifest['pages'][route]['discovery'][channel]={'required':[locale],'reciprocal':False}
    elif name=='cross_locale_canonical_allowed':
        target=g0[last];patch_canonical(manifest,build,first,target);manifest['pages'][first]['canonical_allowed']=[target]
    elif name=='identity_swap':
        cluster_a={l:g0[l] for l in locales[:-1]};cluster_a[last]=g1[last]
        cluster_b={l:g1[l] for l in locales[:-1]};cluster_b[last]=g0[last]
        for route in cluster_a.values():set_pairs(manifest,build,channel,route,list(cluster_a.items()))
        for route in cluster_b.values():set_pairs(manifest,build,channel,route,list(cluster_b.items()))
    elif name=='removed_page':
        route_file(manifest,build,last_route).unlink()
        if channel=='http':
            headers_path=build/'_headers.json';headers=json.loads(headers_path.read_text())
            headers.pop(last_route,None);headers_path.write_text(json.dumps(headers,indent=2)+'\n')
    elif name=='wrong_lang':
        patch_lang(manifest,build,first,last)
    elif name=='wrong_canonical':
        patch_canonical(manifest,build,first,g1[locales[0]])
    elif name=='missing_required':
        pairs=[(l,r) for l,r in g0.items() if l!=last];set_pairs(manifest,build,channel,first,pairs)
    elif name=='declaration_conflict':
        manifest['pages'][first]['ambiguous']=True
    elif name=='duplicate_identity':
        p=urlsplit(first);dup=p.scheme+'://'+p.netloc+'/duplicate-'+keys[0]+'/'
        spec=copy.deepcopy(manifest['pages'][first]);spec['canonical_allowed']=[dup];manifest['pages'][dup]=spec
        src=route_file(manifest,build,first);dest=route_file(manifest,build,dup);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest);patch_canonical(manifest,build,dup,dup)
    else:raise ValueError(name)

def main():
    OUT.mkdir(exist_ok=True);rows=[];sites=[];start=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='localemesh-independent-') as temp:
        temp=Path(temp)
        for family,(source,builder,channel) in FAMILIES.items():
            clean_build=temp/family/'baseline-build';builder(source,clean_build)
            clean_manifest=json.loads((source/'contract.json').read_text())
            clean_manifest_path=temp/family/'clean-manifest.json';clean_manifest_path.parent.mkdir(parents=True,exist_ok=True)
            clean_manifest_path.write_text(json.dumps(clean_manifest,indent=2)+'\n')
            base=load_build(clean_manifest_path,clean_build);assert not evaluate(base),(family,evaluate(base))
            family_start=time.perf_counter()
            for name,label,rule in CASES:
                build=temp/family/'cases'/name;build.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(clean_build,build)
                manifest=copy.deepcopy(clean_manifest);mutate(name,manifest,build,channel)
                mp=temp/family/f'{name}.manifest.json';mp.write_text(json.dumps(manifest,indent=2)+'\n')
                t=time.perf_counter_ns();facts=load_build(mp,build);parse_ns=time.perf_counter_ns()-t
                t=time.perf_counter_ns();full=evaluate(facts);full_ns=time.perf_counter_ns()-t
                inc=Incremental(base);stats=inc.update(delta(base,facts));same=full==inc.issues();assert same,(family,name,full^inc.issues())
                changes=delta(base,facts);projected=FacetedIncremental(base);projected.update(changes)
                safe=ReleaseSession(base,engine_class=FacetedIncremental);safe.apply({k:v for k,v in changes.items() if k[0]!='g'})
                assert projected.issues()==safe.issues()==full
                compact=CoalescedIncremental(base);compact.update(changes)
                compact_safe=ReleaseSession(base,engine_class=CoalescedIncremental);compact_safe.apply({k:v for k,v in changes.items() if k[0]!='g'})
                assert compact.issues()==compact_safe.issues()==full
                sliced=SlicedIncremental(base);sliced_stats=sliced.update(changes)
                sliced_safe=ReleaseSession(base,engine_class=SlicedIncremental);sliced_safe.apply({k:v for k,v in changes.items() if k[0]!='g'})
                assert sliced.issues()==sliced_safe.issues()==full
                release=any(i.category=='release' for i in full)
                if label=='clean':assert not full,(family,name,full)
                elif label=='defect':assert release and rule in {i.code for i in full},(family,name,rule,full)
                else:assert full and not release and rule in {i.code for i in full},(family,name,rule,full)
                controls={'manifest_detected':bool(manifest_presence(facts)),'deadlink_detected':bool(dead_links(facts)),
                          'html_detected':bool(html_annotations(facts)),'joint_detected':bool(joint_output(facts)),
                          'blind_detected':bool(policy_blind(facts))}
                rows.append({'site':family,'case':name,'label':label,'expected_rule':rule or '',
                    'routes':len(manifest['pages']),'emission_kind':clean_manifest['origin_kind'],'channel':channel,
                    'release_findings':sum(i.category=='release' for i in full),'ambiguities':sum(i.category=='ambiguity' for i in full),
                    'full_detected':int(release),'incremental_detected':int(any(i.category=='release' for i in inc.issues())),
                    **{k:int(v) for k,v in controls.items()},'agreement':int(same),'projected_agreement':1,'transaction_agreement':1,'coalesced_agreement':1,'coalesced_transaction_agreement':1,'sliced_agreement':1,'sliced_transaction_agreement':1,'sliced_invalidated_readers':sliced_stats['invalidated_readers'],'parse_snapshot_ns':parse_ns,'full_ns':full_ns,**stats})
            sites.append({'site':family,'origin_kind':clean_manifest['origin_kind'],'routes':len(clean_manifest['pages']),
                          'locales':','.join(clean_manifest['config']['locales']),'channel':channel,'release_cases':len(CASES),
                          'wall_s':time.perf_counter()-family_start})
            # Keep the clean emitted build in the artifact.
            target=ROOT/'independent_builds'/family
            if target.exists():shutil.rmtree(target)
            shutil.copytree(clean_build,target);(target/'manifest.json').write_text(json.dumps(clean_manifest,indent=2)+'\n')
            print('independent',family,len(clean_manifest['pages']),flush=True)
    record_csv(OUT/'independent_releases.csv',rows);record_csv(OUT/'independent_sites.csv',sites)
    (OUT/'independent_run.json').write_text(json.dumps({'wall_s':time.perf_counter()-start,'releases':len(rows),
      'families':len(sites),'scope':'three original local emitters plus one public-source front-matter adaptation; no native framework build, live-site observation, or industrial claim'},indent=2)+'\n')
    print('DONE independent',len(rows),'releases',flush=True)
if __name__=='__main__':main()
