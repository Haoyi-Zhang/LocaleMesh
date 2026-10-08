from __future__ import annotations
from html import escape
from pathlib import Path
from urllib.parse import urlsplit
import json, shutil


def reset(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def route_file(build: Path, mount: str, route: str) -> Path:
    p=urlsplit(route); rel=p.path.lstrip('/')
    if not rel or rel.endswith('/'):
        rel += 'index.html'
    elif not rel.endswith('.html'):
        rel += '/index.html'
    return build/mount/rel


def html_page(*,lang: str,key: str,title: str,canonical: str,alternates: list[tuple[str,str]],links: list[str]) -> str:
    lines=['<!doctype html>',f'<html lang="{escape(lang,quote=True)}"><head>','<meta charset="utf-8">',
           f'<title>{escape(title)}</title>',f'<link rel="canonical" href="{escape(canonical,quote=True)}">']
    lines += [f'<link rel="alternate" hreflang="{escape(l,quote=True)}" href="{escape(u,quote=True)}">' for l,u in alternates]
    lines += ['</head><body>',f'<main data-content-key="{escape(key,quote=True)}"><h1>{escape(title)}</h1></main>']
    lines += [f'<a href="{escape(u,quote=True)}">Next</a>' for u in links]
    lines += ['</body></html>']
    return '\n'.join(lines)+'\n'


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
