#!/usr/bin/env python3
"""Actually run Pandoc over complete, pinned public Markdown sources.

This is an authored publishing pipeline using Pandoc, NOT execution of the
upstream Jekyll/Polyglot site, nor an industrial deployment. Contract and header
integration are study-authored; the five Markdown bodies are unchanged upstream.
"""
from pathlib import Path
import copy,hashlib,html,json,shutil,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from localemesh.io import load_build
from localemesh.full import evaluate
from localemesh.incremental import Incremental
from localemesh.faceted import FacetedIncremental
from localemesh.coalesced import CoalescedIncremental
from localemesh.sliced import SlicedIncremental
from localemesh.transaction import ReleaseSession
from localemesh.model import delta
D=ROOT/'pandoc_integration';ORIGIN='https://pandoc.localemesh.test'
CASES=[('clean','clean',None),('partial_translation','clean',None),('no_xdefault','clean',None),
 ('cross_locale_canonical_allowed','clean',None),('omit_source','defect','MISSING_ROUTE'),
 ('wrong_canonical','defect','CANONICAL_POLICY'),('wrong_language','defect','LANGUAGE'),
 ('missing_required','defect','DISCOVERY_MISSING'),('coherent_cluster_swap','defect','DISCOVERY_ID'),
 ('rename_stale_contract','defect','MISSING_ROUTE'),('declaration_conflict','ambiguity','DECLARATION_CONFLICT')]

def scalar(meta,key):
    v=meta[key]
    if v['t']=='MetaString':return v['c']
    if v['t']!='MetaInlines':raise ValueError((key,v))
    return ''.join(x['c'] if x['t']=='Str' else ' ' for x in v['c'])

def command(args,log):
    start=time.perf_counter_ns();r=subprocess.run(args,capture_output=True,text=True,timeout=30)
    log.append({'command':args,'returncode':r.returncode,'wall_ns':time.perf_counter_ns()-start,'stderr':r.stderr})
    r.check_returncode();return r.stdout

def route(lang,slug):return ORIGIN+'/'+('' if lang=='en' else lang+'/')+slug

def main():
    executable=shutil.which('pandoc')
    if not executable:raise RuntimeError('Pandoc is required for this measured integration; no synthetic fallback.')
    logs=[];version=command([executable,'--version'],logs).splitlines()[0]
    index=json.loads((D/'source-index.json').read_text());pages={};contract={'schema':1,'config':{'origins':{ORIGIN:'main'},'check_links':False},'pages':{}}
    for r in index['records']:
        p=D/'source'/Path(r['path']).name;b=p.read_bytes()
        assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==r['sha']
        # Pandoc itself reads source metadata. The frozen contract below instead
        # comes from the separately retained source-index facts.
        ast=json.loads(command([executable,'--sandbox','-f','markdown','-t','json',str(p)],logs))
        m=ast['meta'];lang=scalar(m,'lang');slug=scalar(m,'permalink')
        k=scalar(m,'page_id') if 'page_id' in m else slug.strip('/')
        pages[route(lang,slug)]={'key':k,'locale':lang,'source':str(p),'lang':lang}
        cr=route(r['locale'],r['permalink']);contract['pages'][cr]={'key':r['key'],'locale':r['locale'],'canonical_allowed':[cr],'canonical_required':True}
    def groups(data):
        g={}
        for u,p in data.items():g.setdefault(p['key'],{})[p['locale']]=u
        return g
    for u,p in contract['pages'].items():p['discovery']={'html':{'required':list(groups(contract['pages'])[p['key']]),'reciprocal':True}}
    for u,p in pages.items():p.update(canonical=u,alternates=list(groups(pages)[p['key']].items()))
    complex_en=next(u for u,p in pages.items() if p['key']=='complex-permalink' and p['locale']=='en')
    de=next(u for u,p in pages.items() if p['locale']=='de')
    about=next(u for u,p in pages.items() if p['key']=='about')
    out=D/'builds'
    if out.exists():shutil.rmtree(out)
    out.mkdir();rows=[];baseline=None
    for case,label,expected in CASES:
        current=copy.deepcopy(pages);manifest=copy.deepcopy(contract)
        if case=='partial_translation':
            current.pop(de);manifest['pages'].pop(de)
            for p in current.values():p['alternates']=[(l,u) for l,u in p['alternates'] if l!='de']
            for p in manifest['pages'].values():p['discovery']['html']['required']=[l for l in p['discovery']['html']['required'] if l!='de']
        elif case=='cross_locale_canonical_allowed':current[complex_en]['canonical']=de;manifest['pages'][complex_en]['canonical_allowed']=[de]
        elif case=='omit_source':current.pop(de)
        elif case=='wrong_canonical':current[complex_en]['canonical']=about
        elif case=='wrong_language':current[complex_en]['lang']='de'
        elif case=='missing_required':current[complex_en]['alternates']=[(l,u) for l,u in current[complex_en]['alternates'] if l!='de']
        elif case=='coherent_cluster_swap':
            cluster=[(p['locale'],u) for u,p in current.items() if p['key']=='complex-permalink'];cluster=[(l,about if u==complex_en else u) for l,u in cluster]
            for _,u in cluster:current[u]['alternates']=cluster
            current[complex_en]['alternates']=[('en',complex_en)]
        elif case=='rename_stale_contract':current[de+'renamed/']=current.pop(de)
        elif case=='declaration_conflict':manifest['pages'][complex_en]['ambiguous']=True
        case_root=out/case;build=case_root/'build';(build/'main').mkdir(parents=True);headerdir=case_root/'headers';headerdir.mkdir()
        start=time.perf_counter_ns();before=len(logs)
        for i,(u,p) in enumerate(current.items()):
            header=headerdir/f'{i}.html'
            pairs=p['alternates']+([] if case=='no_xdefault' else [('x-default',p['alternates'][0][1])])
            lines=['<link rel="canonical" href="'+html.escape(p['canonical'],quote=True)+'">']
            lines+=['<link rel="alternate" hreflang="'+html.escape(l,quote=True)+'" href="'+html.escape(t,quote=True)+'">' for l,t in pairs]
            header.write_text('\n'.join(lines)+'\n')
            target=build/'main'/u.removeprefix(ORIGIN+'/')/'index.html';target.parent.mkdir(parents=True,exist_ok=True)
            command([executable,'--sandbox','-f','markdown','-t','html5','--standalone','--template',str(D/'publisher.html'),
               '--include-in-header',str(header),'--metadata','lang='+p['lang'],'--variable','content-key='+p['key'],'--output',str(target),p['source']],logs)
        native_ns=time.perf_counter_ns()-start;manifest_path=case_root/'manifest.json';manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
        t=time.perf_counter_ns();facts=load_build(manifest_path,build);parse_ns=time.perf_counter_ns()-t
        t=time.perf_counter_ns();full=evaluate(facts);full_ns=time.perf_counter_ns()-t
        if baseline is None:baseline=facts
        d=delta(baseline,facts)
        for cls in (Incremental,FacetedIncremental,CoalescedIncremental,SlicedIncremental):e=cls(baseline);e.update(d);assert e.issues()==full
        session=ReleaseSession(baseline,engine_class=FacetedIncremental);session.apply({k:v for k,v in d.items() if k[0]!='g'});assert session.issues()==full
        compact_safe=ReleaseSession(baseline,engine_class=CoalescedIncremental);compact_safe.apply({k:v for k,v in d.items() if k[0]!='g'});assert compact_safe.issues()==full
        sliced_safe=ReleaseSession(baseline,engine_class=SlicedIncremental);sliced_safe.apply({k:v for k,v in d.items() if k[0]!='g'});assert sliced_safe.issues()==full
        if label=='clean':assert not full,(case,full)
        elif label=='ambiguity':assert full and all(i.category=='ambiguity' for i in full)
        else:assert expected in {i.code for i in full}
        rows.append({'case':case,'label':label,'routes':len(current),'expected_rule':expected,'compiler_invocations':len(logs)-before,
          'compiler_exit_zero':all(x['returncode']==0 for x in logs[before:]),'native_pipeline_ns':native_ns,'parse_ns':parse_ns,'full_ns':full_ns,
          'agreement':True,'coalesced_agreement':True,'coalesced_transaction_agreement':True,'sliced_agreement':True,'sliced_transaction_agreement':True,'findings':[i.json() for i in sorted(full)]})
    result={'version':version,'source_files':len(pages),'rows':rows,'commands':logs,'native_compile_calls':sum(r['compiler_invocations'] for r in rows),
      'scope':'Executed authored Pandoc pipeline using five full public Markdown sources from the PJ upstream; NOT native Jekyll, Astro, Hugo, Next.js, or industry. Ordinary body links and Liquid rendering are outside the chosen contract.'}
    (ROOT/'results/pandoc-run.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows','commands')}));print('compiler success',len(rows),'releases')
if __name__=='__main__':main()
