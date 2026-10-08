from __future__ import annotations
from pathlib import Path
import csv,json
from .common import reset,route_file,html_page,write_json


def build(source_root: Path, build_root: Path) -> None:
    cfg=json.loads((source_root/'site.json').read_text(encoding='utf8'))
    with (source_root/'catalog.csv').open(encoding='utf8',newline='') as f: records=list(csv.DictReader(f))
    reset(build_root);locales=cfg['locales'];grouped={}
    for r in records:
        r['url']=cfg['origins'][r['locale']]+f"/item/{r['key']}/"; grouped.setdefault(r['key'],{})[r['locale']]=r
    order=sorted(grouped);headers={}
    for i,key in enumerate(order):
        pairs=[(l,grouped[key][l]['url']) for l in locales]
        for locale in locales:
            r=grouped[key][locale];mount=locale;nxt=grouped[order[(i+1)%len(order)]][locale]['url']
            dest=route_file(build_root,mount,r['url']);dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(html_page(lang=locale,key=key,title=r['title'],canonical=r['url'],alternates=[],links=[nxt]),encoding='utf8')
            headers[r['url']]={'status':200,'link':[f'<{target}>; rel="alternate"; hreflang="{label}"' for label,target in pairs]}
    write_json(build_root/'_headers.json',headers)
