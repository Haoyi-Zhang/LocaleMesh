from __future__ import annotations
from pathlib import Path
import tomllib, xml.etree.ElementTree as ET
from .common import reset,route_file,html_page


def build(source_root: Path, build_root: Path) -> None:
    cfg=tomllib.loads((source_root/'site.toml').read_text(encoding='utf8'))
    reset(build_root); origin=cfg['site']['origin']; locales=cfg['site']['locales']; default=cfg['site']['default_locale']
    records=[]
    for locale in locales:
        for p in sorted((source_root/'content'/locale).glob('*.txt')):
            lines=p.read_text(encoding='utf8').splitlines(); key=p.stem; title=lines[0]
            path=f'/{key}/' if locale==default else f'/{locale}/{key}/'
            records.append({'key':key,'locale':locale,'title':title,'url':origin+path})
    grouped={}
    for r in records: grouped.setdefault(r['key'],{})[r['locale']]=r
    order=sorted(grouped)
    for i,key in enumerate(order):
        for locale in locales:
            r=grouped[key][locale]; nxt=grouped[order[(i+1)%len(order)]][locale]['url']
            dest=route_file(build_root,'.',r['url']);dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(html_page(lang=locale,key=key,title=r['title'],canonical=r['url'],alternates=[],links=[nxt]),encoding='utf8')
    ns='http://www.sitemaps.org/schemas/sitemap/0.9';xns='http://www.w3.org/1999/xhtml'
    ET.register_namespace('',ns);ET.register_namespace('xhtml',xns);root=ET.Element('{'+ns+'}urlset')
    for key in order:
        pairs=[(l,grouped[key][l]['url']) for l in locales]
        for locale in locales:
            route=grouped[key][locale]['url'];node=ET.SubElement(root,'{'+ns+'}url');ET.SubElement(node,'{'+ns+'}loc').text=route
            for label,target in pairs: ET.SubElement(node,'{'+xns+'}link',{'rel':'alternate','hreflang':label,'href':target})
    ET.ElementTree(root).write(build_root/'sitemap.xml',encoding='utf-8',xml_declaration=True)
