#!/usr/bin/env python3
"""Reproduce seven ingestion regressions in the archived LocaleMesh parser.

The archived module is a legacy implementation, not a historical upstream
bug. Literal expected facts are independent of fixtures.py/cases.py, but were
specified by the same research process. No native build or human oracle implied.
"""
from pathlib import Path
import sys,importlib.util,json,itertools
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from localemesh.io import PageParser,parse_link_headers

def main():
    spec=importlib.util.spec_from_file_location('localemesh._legacy_io',ROOT/'vendor/legacy_io.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    base='https://demo.test/page/'
    def doc(head='',body=''):
        return '<html lang="en" data-content-key="x"><head>'+head+'</head><body>'+body+'</body></html>'
    cases=[
      ('base_url','html',doc('<base href="/new/"><link rel=canonical href="page/">'),lambda x:x['canonical']['html']==['https://demo.test/new/page/']),
      ('inert_template','html',doc('<template><link rel=canonical href="/wrong/"></template><link rel=canonical href="/page/">'),lambda x:x['canonical']['html']==[base]),
      ('nested_identity','html',doc(body='<article data-content-key="unrelated"></article>'),lambda x:x['key'] is None and 'CONTENT_MARKER_CONFLICT' in {d[0] for d in x.get('diagnostics',[])}),
      ('data_icon','html',doc('<link rel=icon href="data:image/png;base64,AA==">'),lambda x:not x.get('diagnostics') and not x['canonical']['html']),
      ('anchor','header','<../fr/>; rel=alternate; hreflang=fr; anchor="/other/"',lambda x:x==([],[])),
      ('repeat_hreflang','header','<../en/>; rel=alternate; hreflang=en; hreflang=en-GB',lambda x:x==([['en','https://demo.test/en/'],['en-gb','https://demo.test/en/']],[])),
      ('repeat_rel','header','<../fr/>; rel=alternate; rel=canonical; hreflang=fr',lambda x:x==([['fr','https://demo.test/fr/']],[])),
    ];rows=[]
    for name,kind,text,expected in cases:
        row={'case':name,'kind':kind,'input':text,'response_url':base}
        for label,parser,headers in [('legacy',old.PageParser,old.parse_link_headers),('current',PageParser,parse_link_headers)]:
            try:
                if kind=='html':p=parser(base);p.feed(text);p.close();value=p.obs
                else:value=headers([text],base)
                row[label]={'output':value,'matches_literal_expectation':bool(expected(value))}
            except Exception as e:
                row[label]={'exception':type(e).__name__+': '+str(e),'matches_literal_expectation':False}
        assert row['current']['matches_literal_expectation'],name
        assert not row['legacy']['matches_literal_expectation'],name
        rows.append(row)
    # Cartesian serialization variants: attribute order, tag/attribute case,
    # quote style, and whitespace do not change these well-formed local facts.
    variants=[]
    for order,upper,quote,space in itertools.product([0,1],[False,True],['"',"'"],[' ','\n  ']):
        attrs=[('rel','alternate'),('hreflang','FR'),('href','https://demo.test/fr/?a=1&amp;b=2')]
        if order:attrs.reverse()
        tag='LINK' if upper else 'link'
        rendered='<'+tag+space+space.join((k.upper() if upper else k)+'='+quote+v+quote for k,v in attrs)+'>'
        p=PageParser(base);p.feed(doc(rendered));p.close()
        assert p.obs['alternates']['html']==[['fr','https://demo.test/fr/?a=1&b=2']]
        assert not p.obs.get('diagnostics')
        variants.append({'html':rendered,'expected_alternates':p.obs['alternates']['html'],'matches':True})
    result={'regressions':rows,'serialization_variants':variants,
            'counts':{'legacy_failures':len(rows),'current_passes':len(rows),'serialization_checks':len(variants)},
            'scope':'Literal same-team regression facts; archived LocaleMesh parser; no external oracle or browser-conformance certification.'}
    (ROOT/'results/ingestion-replay.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['counts']))
if __name__=='__main__':main()
