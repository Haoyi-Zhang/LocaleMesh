#!/usr/bin/env python3
"""Offline native-browser differential extraction, not a framework build."""
from pathlib import Path
import sys,json,time,collections
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from localemesh.browser import BrowserExtractor,normalize_dom
from localemesh.io import PageParser,load_build
from localemesh.full import evaluate
BASE='https://dom.localemesh.test/page/'
CAN='<link rel="canonical" href="/page/">'
def doc(head='',body=''):return '<!doctype html><html lang=en data-content-key=x><head>'+head+'</head><body>'+body+'</body></html>'
def facts(obs):return {k:obs.get(k) for k in ['lang','key','canonical','alternates','links','redirect']}
def diagnostic_codes(obs):return sorted({entry[0] for entry in obs.get('diagnostics',[])})
CASES=[
('plain',doc(CAN)),('first_base',doc('<base href="/new/">'+CAN.replace('/page/','relative/'))),
('late_base',doc(CAN.replace('/page/','relative/')+'<base href="/new/">')),
('two_bases',doc('<base href="/a/"><base href="/b/">'+CAN.replace('/page/','relative/'))),
('template',doc('<template>'+CAN.replace('/page/','/wrong/')+'</template>'+CAN)),
('nested_template',doc('<template><template>'+CAN+'</template></template>'+CAN)),
('template_body',doc(CAN,'<template><a href="/wrong/">x</a><article data-content-key=y></article></template>')),
('script',doc('<script>globalThis.__localemeshInputExecuted=true;"<link rel=canonical href=/wrong/>"</script>'+CAN)),
('style',doc('<style>/* <link rel=canonical href=/wrong/> */</style>'+CAN)),
('comment',doc('<!-- '+CAN.replace('/page/','/wrong/')+' -->'+CAN)),
('title',doc('<title>&lt;link rel=canonical href=/wrong/&gt;</title>'+CAN)),
('textarea',doc(CAN,'<textarea><a href=/wrong/>x</a></textarea>')),
('duplicate_attribute',doc('<link rel=canonical href="/page/" href="/wrong/">')),
('duplicate_rel',doc('<link rel=canonical rel=alternate href="/page/" hreflang=de>')),
('entities',doc('<link rel=alternate hreflang=de href="/de/?a=1&amp;b=2">')),
('icon',doc('<link rel=icon href="data:image/png;base64,AA==">'+CAN)),
('alternate_stylesheet',doc('<link rel="alternate stylesheet" hreflang=de href="/style.css">'+CAN)),
('anchors',doc(CAN,'<a href="#local">local</a><a href="mailto:x@y.test">email</a><a href="../de/">de</a>')),
('refresh',doc('<meta http-equiv=refresh content="0; url=/target/">')),
('conflict_markers',doc(CAN,'<article data-content-key=y></article>')),
('omitted_head','<!doctype html><html lang=en data-content-key=x>'+CAN+'<body>Body</body></html>'),
('omitted_head_end','<!doctype html><html lang=en data-content-key=x><head>'+CAN+'<body>Body</body></html>'),
('body_metadata',doc(CAN,'<link rel=canonical href="/wrong/">')),
('foreign_content',doc(CAN,'<svg><foreignObject><a href="/other/">other</a></foreignObject></svg>')),
('plaintext',doc(CAN,'<plaintext><a href="/wrong/">literal')),
('noscript',doc('<noscript>'+CAN.replace('/page/','/fallback/')+'</noscript>'+CAN)),
('head_text',doc('text'+CAN)),
('nested_raw_title',doc('<title><title>literal</title>'+CAN)),
('select_anchor',doc(CAN,'<select><a href="/wrong/">ignored</a><option>x</option></select>')),
('head_image',doc('<img src="https://no-fetch.test/image.png">'+CAN)),
]

def main():
    start=time.perf_counter();rows=[]
    with BrowserExtractor() as browser:
        raw=browser.raw_many([x[1] for x in CASES])
        for (name,text),tree in zip(CASES,raw):
            p=PageParser(BASE);p.feed(text);p.close();light=p.obs;dom=normalize_dom(tree,BASE)
            same=facts(light)==facts(dom)
            rows.append({'case':name,'html':text,'response_url':BASE,'browser_tree':tree,'static':light,'browser':dom,
                         'same_selected_facts':same,'same_diagnostic_codes':diagnostic_codes(light)==diagnostic_codes(dom),
                         'static_diagnosed':bool(light.get('diagnostics')),'browser_diagnosed':bool(dom.get('diagnostics'))})
        # Actual retained Pandoc HTML outputs; no new native compiler execution here.
        candidates=sorted((ROOT/'pandoc_integration').rglob('*.html'))
        candidates=[p for p in candidates if 'output' in p.parts or 'build' in p.parts]
        # Locate explicit generated output hierarchy if fixtures use another name.
        if not candidates:candidates=sorted((ROOT/'results/pandoc').rglob('*.html'))
        corpus=[]
        for offset in range(0,len(candidates),20):
            batch=candidates[offset:offset+20];trees=browser.raw_many([p.read_text() for p in batch])
            for path,tree in zip(batch,trees):
                p=PageParser(BASE);p.feed(path.read_text());p.close();obs=p.obs;dom=normalize_dom(tree,BASE)
                corpus.append({'path':str(path.relative_to(ROOT)),'same_selected_facts':facts(obs)==facts(dom),
                               'static_diagnosed':bool(obs.get('diagnostics')),'browser_diagnosed':bool(dom.get('diagnostics'))})
        release_checks=[]
        for manifest in sorted((ROOT/'pandoc_integration/builds').glob('*/manifest.json')):
            build=manifest.parent/'build'
            static=load_build(manifest,build)
            native=load_build(manifest,build,html_extractor=browser.extract)
            equal=evaluate(static)==evaluate(native)
            assert equal,manifest.parent.name
            release_checks.append({'release':manifest.parent.name,'same_issue_set':equal,
                                  'same_normalized_snapshot':static==native,'findings':len(evaluate(native))})
        literal_checks=[]
        expected={'plain':[BASE],'first_base':['https://dom.localemesh.test/new/relative/'],
          'late_base':['https://dom.localemesh.test/new/relative/'],'two_bases':['https://dom.localemesh.test/a/relative/'],
          'template':[BASE],'nested_template':[BASE],'template_body':[BASE],'script':[BASE],
          'style':[BASE],'comment':[BASE],'title':[BASE],'textarea':[BASE],
          'duplicate_attribute':[BASE],'duplicate_rel':[BASE],'icon':[BASE],
          'alternate_stylesheet':[BASE],'omitted_head':[BASE],'omitted_head_end':[BASE]}
        for row in rows:
            if row['case'] in expected:
                assert row['browser']['canonical']['html']==expected[row['case']],row['case']
                literal_checks.append({'case':row['case'],'expected_canonical':expected[row['case']],'matches':True})
        events=browser.events;version=browser.version
        requested=[e for e in events if e.get('method')=='Network.requestWillBeSent']
        report={'version':version,'cases':rows,'compiled_output_checks':corpus,'native_gate_checks':release_checks,'literal_expectations':literal_checks,'network_requests':requested,
          'counts':{'edge_cases':len(rows),'same_selected_facts':sum(x['same_selected_facts'] for x in rows),
            'same_diagnostic_codes':sum(x['same_diagnostic_codes'] for x in rows),
            'undiagnosed_differences':sum(not x['same_selected_facts'] and not x['static_diagnosed'] and not x['browser_diagnosed'] for x in rows),
            'native_gate_releases':len(release_checks),'native_gate_agreement':sum(x['same_issue_set'] for x in release_checks),'literal_expectations':len(literal_checks),'compiled_outputs':len(corpus),'compiled_agreement':sum(x['same_selected_facts'] for x in corpus),
            'network_requests':len(requested)},'wall_s':time.perf_counter()-start,
          'scope':'Native Chromium inert tree parser; authored selectors and same URL normalizer. Constructed edge cases, retained Pandoc output. Not browser conformance, native i18n build, human oracle, or production crawl.'}
    (ROOT/'results/browser-differential.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['counts'],indent=2))
    for r in rows:
        if not r['same_selected_facts']:print('DIFFERENCE',r['case'],'diagnosed:',r['static_diagnosed'],r['browser_diagnosed'])
    assert not requested
    # Differences are preserved; only undiagnosed disagreements fail this check.
    assert report['counts']['undiagnosed_differences']==0
    noscript=next(row for row in rows if row['case']=='noscript')
    assert noscript['same_diagnostic_codes'] and 'HTML_PROFILE' in diagnostic_codes(noscript['static'])
    assert all(x['same_selected_facts'] for x in corpus)
if __name__=='__main__':main()
