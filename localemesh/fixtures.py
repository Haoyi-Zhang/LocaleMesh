"""Authored laboratory inputs and a transparent HTML fixture emitter.

This module is NOT Astro, Hugo, or Next.js. Its outputs must never be described as
outputs of those builders, public sites, field releases, or discovered upstream bugs.
"""
from __future__ import annotations
from pathlib import Path
from urllib.parse import urlsplit
from html import escape
import json, copy, shutil
import xml.etree.ElementTree as ET
from .model import snapshot

SITES = [
    ('A1', 'Atlas manuals', 12, ('en','de'), ('html',), False, False),
    ('A2', 'Atlas reference', 24, ('en','fr'), ('html','sitemap'), True, False),
    ('H1', 'Handbook', 32, ('en','fr','de'), ('sitemap',), False, False),
    ('H2', 'Multihost guide', 50, ('en','fr','de'), ('sitemap','http'), True, True),
    ('N1', 'Regional catalog', 80, ('en','fr','ja'), ('html','http'), True, False),
    ('N2', 'Header-only catalog', 120, ('en','de','ja'), ('http',), False, True),
]

def make_site(site_id='A1', size=None):
    row = next(x for x in SITES if x[0] == site_id)
    _, title, keys, locales, channels, prefix, multihost = row
    if size is not None: keys = size
    origins = {f'https://{site_id.lower()}.test': 'main'}
    if multihost:
        origins = {f'https://{l}.{site_id.lower()}.test': l for l in locales}
    config = {'origins': origins, 'aliases': {}, 'locales': list(locales),
              'complete_manifest': True, 'check_links': True}
    manifest = {'schema':1, 'fixture_id':site_id, 'origin_kind':'authored-fixture', 'config':config, 'pages':{}}
    obs, sm, groups = {}, {}, []
    for i in range(keys):
        pairs=[]
        for locale in locales:
            origin = f'https://{locale}.{site_id.lower()}.test' if multihost else next(iter(origins))
            path = f'/{locale}/item-{i:04d}/' if prefix or locale != locales[0] else f'/item-{i:04d}/'
            route=origin+path
            pairs.append([locale,route])
        groups.append(pairs)
    for i,pairs in enumerate(groups):
        for locale,route in pairs:
            discovery={c:{'required':list(locales),'reciprocal':True} for c in channels}
            manifest['pages'][route]={'key':f'item-{i:04d}', 'locale':locale, 'state':'published',
                'canonical_allowed':[route], 'canonical_channels':['html'], 'sitemap':True,
                'discovery':discovery, 'agree_channels':list(channels), 'fallbacks':{}}
            obs[route]={'status':200,'lang':locale,'key':f'item-{i:04d}',
                'canonical':{'html':[route]},'alternates':{c:copy.deepcopy(pairs) for c in channels if c!='sitemap'},
                'links':[dict(groups[(i+1)%len(groups)])[locale]],
                'body':f'{title}. Authored release fixture, content {i}, locale {locale}.'}
            sm[route]=copy.deepcopy(pairs) if 'sitemap' in channels else []
    return manifest,obs,sm


def write_fixture(directory:Path, manifest:dict, obs:dict, sm:dict):
    directory=Path(directory)
    if directory.exists(): shutil.rmtree(directory)
    build=directory/'build'; build.mkdir(parents=True)
    (directory/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf8')
    # Publication source is separate from the checker contract; changes may affect either.
    (directory/'publication.json').write_text(json.dumps({'pages':obs,'sitemap':sm},indent=2,ensure_ascii=False),encoding='utf8')
    headers={}
    for origin,rel in manifest['config']['origins'].items(): (build/rel).mkdir(parents=True,exist_ok=True)
    for route,o in obs.items():
        p=urlsplit(route); origin=p.scheme+'://'+p.netloc
        rel=manifest['config']['origins'].get(origin)
        if rel is None: raise ValueError('Cannot emit into an unmounted origin')
        if o.get('redirect_transport')=='http-fixture' or o.get('status',200)!=200:
            headers[route]={'status':o.get('status',302),'location':o.get('redirect'),'link':[]}
        else:
            path=p.path.lstrip('/')
            if not path or path.endswith('/'): path+='index.html'
            elif not path.endswith('.html'): path+='/index.html'
            file=build/rel/path; file.parent.mkdir(parents=True,exist_ok=True)
            tags=['<!doctype html>',f'<html lang="{escape(o.get("lang",""),quote=True)}"><head>','<meta charset="utf-8">']
            for can in o.get('canonical',{}).get('html',[]): tags.append(f'<link rel="canonical" href="{escape(can,quote=True)}">')
            for locale,target in o.get('alternates',{}).get('html',[]): tags.append(f'<link rel="alternate" hreflang="{escape(locale,quote=True)}" href="{escape(target,quote=True)}">')
            if o.get('redirect'): tags.append(f'<meta http-equiv="refresh" content="0;url={escape(o["redirect"],quote=True)}">')
            attr='' if o.get('key') is None else f' data-content-key="{escape(o["key"],quote=True)}"'
            tags.extend(['</head><body>',f'<main{attr}>{escape(o.get("body","Authored laboratory fixture."))}</main>'])
            tags.extend(f'<a href="{escape(x,quote=True)}">Related</a>' for x in o.get('links',[]))
            tags.append('</body></html>')
            file.write_text('\n'.join(tags),encoding='utf8')
        if 'http' in o.get('alternates',{}) or 'http' in o.get('canonical',{}):
            h=headers.setdefault(route,{'status':o.get('status',200),'link':[]})
            h['link'] += [f'<{target}>; rel="alternate"; hreflang="{locale}"' for locale,target in o.get('alternates',{}).get('http',[])]
            h['link'] += [f'<{target}>; rel="canonical"' for target in o.get('canonical',{}).get('http',[])]
    ns='http://www.sitemaps.org/schemas/sitemap/0.9'; xns='http://www.w3.org/1999/xhtml'
    ET.register_namespace('',ns); ET.register_namespace('xhtml',xns)
    for origin,rel in manifest['config']['origins'].items():
        root=ET.Element('{'+ns+'}urlset')
        for route,pairs in sm.items():
            p=urlsplit(route)
            if p.scheme+'://'+p.netloc != origin: continue
            e=ET.SubElement(root,'{'+ns+'}url'); ET.SubElement(e,'{'+ns+'}loc').text=route
            for locale,target in pairs:
                ET.SubElement(e,'{'+xns+'}link',{'rel':'alternate','hreflang':locale,'href':target})
        ET.ElementTree(root).write(build/rel/'sitemap.xml',encoding='utf-8',xml_declaration=True)
    if headers: (build/'_headers.json').write_text(json.dumps(headers,indent=2),encoding='utf8')


def to_facts(data):
    return snapshot(*data)
