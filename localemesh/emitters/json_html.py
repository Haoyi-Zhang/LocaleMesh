from __future__ import annotations
from pathlib import Path
import json
from .common import reset,route_file,html_page


def build(source_root: Path, build_root: Path) -> None:
    data=json.loads((source_root/'content.json').read_text(encoding='utf8'))
    reset(build_root); origin=data['origin']; mount='.'
    grouped={}
    for page in data['pages']:
        grouped.setdefault(page['key'],{})[page['locale']]=page
    order=sorted(grouped)
    for i,key in enumerate(order):
        pairs=[(l,grouped[key][l]['url']) for l in data['locales']]
        next_key=order[(i+1)%len(order)]
        for locale in data['locales']:
            page=grouped[key][locale]
            link=grouped[next_key][locale]['url']
            dest=route_file(build_root,mount,page['url']);dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(html_page(lang=locale,key=key,title=page['title'],canonical=page['url'],alternates=pairs,links=[link]),encoding='utf8')
