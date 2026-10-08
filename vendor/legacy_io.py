"""Read local build artifacts only. No sockets, browser execution, or external fetches."""
from __future__ import annotations
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
import json
import re
import xml.etree.ElementTree as ET
from .model import snapshot, url

class PageParser(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.obs = {'status': 200, 'lang': '', 'key': None,
                    'canonical': {'html': []}, 'alternates': {'html': []}, 'links': []}
        self.in_head = False
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'head': self.in_head = True
        if tag == 'html': self.obs['lang'] = a.get('lang', '')
        if 'data-content-key' in a: self.obs['key'] = a['data-content-key']
        if tag == 'link' and self.in_head and a.get('href'):
            rel = (a.get('rel') or '').lower().split()
            target = url(a['href'], self.base)
            if 'canonical' in rel: self.obs['canonical']['html'].append(target)
            if 'alternate' in rel and a.get('hreflang'):
                self.obs['alternates']['html'].append([a['hreflang'].lower(), target])
        if tag == 'a' and a.get('href'):
            href = a['href']
            if href.startswith(('mailto:', 'tel:', 'javascript:', 'data:', '#')): return
            try: self.obs['links'].append(url(href, self.base))
            except ValueError: pass
        if tag == 'meta' and (a.get('http-equiv') or '').lower() == 'refresh':
            content = a.get('content') or ''
            match = re.search(r'(?:^|;)\s*url\s*=\s*(.+)$', content, re.I)
            if match:
                self.obs['redirect'] = url(match.group(1).strip().strip('"\''), self.base)
                self.obs['redirect_transport'] = 'html-refresh'
    def handle_endtag(self, tag):
        if tag == 'head': self.in_head = False


def split_links(value: str) -> list[str]:
    """Split Link fields on commas outside URI brackets and quoted strings."""
    pieces, start, quote, angle, escaped = [], 0, False, False, False
    for i, c in enumerate(value):
        if escaped:
            escaped = False
            continue
        if c == '\\' and quote:
            escaped = True
        elif c == '"':
            quote = not quote
        elif not quote and c == '<': angle = True
        elif not quote and c == '>': angle = False
        elif c == ',' and not quote and not angle:
            pieces.append(value[start:i].strip()); start = i + 1
    pieces.append(value[start:].strip())
    return [p for p in pieces if p]


def parse_link_headers(values: list[str], base: str) -> tuple[list, list]:
    alternate, canonical = [], []
    for value in values:
        for piece in split_links(value):
            match = re.match(r'^\s*<([^>]*)>(.*)$', piece)
            if match is None:
                raise ValueError(f'Malformed Link header: {piece!r}')
            target = url(match.group(1), base)
            params = {}
            for param in re.finditer(r';\s*([\w*-]+)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|([^;\s]+))', match.group(2)):
                params[param.group(1).lower()] = param.group(2) if param.group(2) is not None else param.group(3)
            rels = params.get('rel', '').lower().split()
            if 'canonical' in rels: canonical.append(target)
            if 'alternate' in rels and 'hreflang' in params:
                alternate.append([params['hreflang'].lower(), target])
    return alternate, canonical


def safe_child(root: Path, rel: str) -> Path:
    result = (root / rel).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError('Origin directory escapes the build root')
    return result


def load_build(manifest_path: Path | str, build_root: Path | str):
    manifest_path, build_root = Path(manifest_path), Path(build_root)
    manifest = json.loads(manifest_path.read_text(encoding='utf8'))
    if manifest.get('schema') != 1:
        raise ValueError('Expected manifest schema 1')
    observations, sitemaps = {}, {}
    for origin, relative_dir in manifest['config']['origins'].items():
        directory = safe_child(build_root, relative_dir)
        if not directory.is_dir():
            raise FileNotFoundError(f'Missing mounted origin directory: {directory}')
        for p in sorted(directory.rglob('*.html')):
            # Symlinks outside the mount are rejected, not dereferenced.
            if not p.resolve().is_relative_to(directory.resolve()):
                raise ValueError('HTML symlink escapes origin mount')
            rel = p.relative_to(directory).as_posix()
            if rel == 'index.html': route_path = '/'
            elif rel.endswith('/index.html'): route_path = '/' + rel[:-10]
            elif manifest['config'].get('html_extension') == 'extensionless': route_path = '/' + rel[:-5]
            else: route_path = '/' + rel
            route = url(origin + route_path)
            parser = PageParser(route)
            parser.feed(p.read_text(encoding='utf8'))
            observations[route] = parser.obs
        for p in sorted(directory.rglob('*.xml')):
            data = p.read_text(encoding='utf8')
            if '<!DOCTYPE' in data.upper() or '<!ENTITY' in data.upper():
                raise ValueError('DTD/entity declarations are not accepted in local sitemaps')
            root = ET.fromstring(data)
            # All local XML files are discovered directly. No sitemap-index URL is fetched.
            if root.tag.rsplit('}', 1)[-1] != 'urlset': continue
            for entry in root:
                if entry.tag.rsplit('}', 1)[-1] != 'url': continue
                loc = next((e.text for e in entry if e.tag.rsplit('}', 1)[-1] == 'loc'), None)
                if not loc: continue
                route = url(loc)
                links = []
                for child in entry:
                    if child.tag == '{http://www.w3.org/1999/xhtml}link':
                        if 'alternate' in child.get('rel', '').lower().split() and child.get('hreflang'):
                            links.append([child.get('hreflang').lower(), url(child.attrib['href'], route)])
                sitemaps.setdefault(route, []).extend(links)
    headers_path = build_root / '_headers.json'
    if headers_path.exists():
        headers = json.loads(headers_path.read_text(encoding='utf8'))
        for route, h in headers.items():
            route = url(route)
            # Local HTTP capture/fixture may contain a redirect with no HTML file.
            o = observations.setdefault(route, {'lang': '', 'key': None, 'links': [], 'alternates': {}, 'canonical': {}})
            o['status'] = h.get('status', 200)
            if h.get('location'): o['redirect'] = url(h['location'], route); o['redirect_transport'] = 'http-fixture'
            alts, canon = parse_link_headers(h.get('link', []), route)
            o['alternates']['http'] = alts
            o['canonical']['http'] = canon
    return snapshot(manifest, observations, sitemaps)
