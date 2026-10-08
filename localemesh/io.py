"""Offline ingestion for the explicitly documented static-publication profile.

This is not a browser or an HTML conformance checker. It requires explicit head
boundaries, treats template/noscript content as inactive, and resolves relevant
HTML references against the first active base href. HTTP Link fields instead use
the response URL. Anchored Link values are ignored in their entirety (RFC 8288).
Uncertain observations carry diagnostics; malformed external records fail closed.
"""
from __future__ import annotations
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
import copy
import json
import re
import xml.etree.ElementTree as ET
from .model import snapshot, url


class PageParser(HTMLParser):
    """Extract facts without last-value-wins loss of conflicting declarations."""
    INACTIVE = {'template', 'noscript', 'title', 'textarea', 'xmp', 'iframe',
                'noembed', 'noframes', 'plaintext', 'script', 'style', 'svg', 'math'}

    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = url(base)
        self.in_head = False
        self.head_count = 0
        self.html_count = 0
        self.lang = ''
        self.base_href: str | None = None
        self.markers: set[str] = set()
        self.references: list[tuple[str, str, str]] = []
        self.diagnostics: set[tuple[str, str]] = set()
        self.inactive: str | None = None
        self.depth = 0
        self.finished = False

    def handle_starttag(self, tag, attrs):
        if self.inactive:
            if tag == self.inactive:
                self.depth += 1
            return
        # HTML tokenization retains the first duplicate attribute, not the last.
        a = {}
        for name, value in attrs:
            if name not in a:
                a[name] = value
        if tag in {'svg', 'math', 'plaintext'}:
            self.diagnostics.add(('HTML_PROFILE', 'Foreign content or plaintext requires another extractor'))
        if tag == 'noscript':
            self.diagnostics.add(('HTML_PROFILE', 'noscript requires an explicit scripting-mode contract'))
        if self.in_head and tag not in {'html', 'head', 'base', 'link', 'meta', 'title', 'style', 'script', 'noscript', 'template'}:
            self.diagnostics.add(('HTML_PROFILE', 'Non-metadata element inside explicit head'))
        if tag in self.INACTIVE:
            self.inactive, self.depth = tag, 1
            return
        if tag == 'html':
            self.html_count += 1
            if self.html_count == 1:
                self.lang = a.get('lang') or ''
            else:
                self.diagnostics.add(('HTML_PROFILE', 'Multiple html start tags'))
        if tag == 'head':
            self.head_count += 1
            self.in_head = True
            if self.head_count > 1:
                self.diagnostics.add(('HTML_PROFILE', 'Multiple head start tags'))
        if tag == 'body' and self.in_head:
            self.in_head = False
            self.diagnostics.add(('HTML_PROFILE', 'Explicit head end tag required'))
        if 'data-content-key' in a:
            if a['data-content-key']:
                self.markers.add(a['data-content-key'])
            else:
                self.diagnostics.add(('CONTENT_MARKER_CONFLICT', 'Empty content marker'))
        if tag == 'base' and 'href' in a and self.base_href is None:
            self.base_href = a['href'] or ''
            if not self.in_head:
                self.diagnostics.add(('HTML_PROFILE', 'base outside explicit head'))
        if tag == 'link' and self.in_head:
            rel = (a.get('rel') or '').lower().split()
            canonical = 'canonical' in rel
            alternate = ('alternate' in rel and 'stylesheet' not in rel
                         and bool(a.get('hreflang')))
            if not canonical and not alternate:
                return  # A data: icon is not a publication URL.
            if alternate and (a.get('media') or '').strip():
                self.diagnostics.add(('HTML_PROFILE', 'Media-qualified language alternate'))
            if 'href' not in a:
                self.diagnostics.add(('HTML_REFERENCE', 'Relevant link lacks href'))
                return
            href = a.get('href') or ''
            if canonical:
                self.references.append(('canonical', '', href))
            if alternate:
                self.references.append(('alternate', a['hreflang'].lower(), href))
        if tag == 'a' and a.get('href'):
            href = a['href'].strip()
            if not href.startswith('#'):
                self.references.append(('link', '', href))
        if tag == 'meta' and self.in_head and (a.get('http-equiv') or '').lower() == 'refresh':
            content = a.get('content') or ''
            match = re.fullmatch(r'\s*0(?:\.0*)?\s*;\s*url\s*=\s*(.+?)\s*', content, re.I)
            if match:
                self.references.append(('redirect', '', match.group(1).strip('"\'')))
            else:
                self.diagnostics.add(('HTML_PROFILE', 'Only zero-delay URL refresh is modeled'))

    def handle_data(self, data):
        if self.in_head and not self.inactive and data.strip():
            self.diagnostics.add(('HTML_PROFILE', 'Non-whitespace text inside explicit head'))

    def handle_startendtag(self, tag, attrs):
        # HTML ignores the self-closing flag on non-void elements. In particular,
        # <template/> does NOT make its following links active.
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self.inactive:
            if tag == self.inactive:
                self.depth -= 1
                if self.depth == 0:
                    self.inactive = None
            return
        if tag == 'head':
            self.in_head = False

    def close(self):
        super().close()
        self.finished = True

    @property
    def obs(self):
        diagnostics = set(self.diagnostics)
        if not self.head_count:
            diagnostics.add(('HTML_PROFILE', 'Explicit head start tag required'))
        if self.finished and (self.in_head or self.inactive):
            diagnostics.add(('HTML_PROFILE', 'Unclosed head or inactive element'))
        if len(self.markers) > 1:
            diagnostics.add(('CONTENT_MARKER_CONFLICT', '|'.join(sorted(self.markers))))
        base = self.base
        if self.base_href is not None:
            try:
                base = url(self.base_href, self.base)
            except ValueError:
                diagnostics.add(('HTML_REFERENCE', 'Unsupported base href'))
        out = {'status': 200, 'lang': self.lang,
               'key': next(iter(self.markers)) if len(self.markers) == 1 else None,
               'canonical': {'html': []}, 'alternates': {'html': []}, 'links': []}
        redirects = set()
        for kind, label, raw in self.references:
            # Ordinary non-Web anchors are outside the release-link obligation.
            if kind == 'link' and urlsplit(raw).scheme.lower() not in ('', 'http', 'https'):
                continue
            try:
                target = url(raw, base)
            except ValueError:
                diagnostics.add(('HTML_REFERENCE', kind + ':' + raw))
                continue
            if kind == 'canonical': out['canonical']['html'].append(target)
            elif kind == 'alternate': out['alternates']['html'].append([label, target])
            elif kind == 'link': out['links'].append(target)
            else: redirects.add(target)
        if len(redirects) == 1:
            out['redirect'] = next(iter(redirects))
            out['redirect_transport'] = 'html-refresh'
        elif len(redirects) > 1:
            diagnostics.add(('HTML_REFERENCE', 'Conflicting refresh targets'))
        if diagnostics:
            out['diagnostics'] = [list(x) for x in sorted(diagnostics)]
        return out


def split_links(value: str) -> list[str]:
    """Split Link fields only outside URI references and quoted parameters."""
    pieces, start, quote, angle, escaped = [], 0, False, False, False
    for i, c in enumerate(value):
        if escaped:
            escaped = False
        elif c == '\\' and quote:
            escaped = True
        elif c == '"' and not angle:
            quote = not quote
        elif not quote and c == '<':
            if angle: raise ValueError('Nested Link URI bracket')
            angle = True
        elif not quote and c == '>':
            if not angle: raise ValueError('Unmatched Link URI bracket')
            angle = False
        elif c == ',' and not quote and not angle:
            pieces.append(value[start:i].strip()); start = i + 1
    if quote or angle or escaped:
        raise ValueError('Unterminated Link field')
    pieces.append(value[start:].strip())
    return [p for p in pieces if p]


TOKEN = r"[!#$%&'*+.^_`|~0-9A-Za-z-]+"
PARAM = re.compile(r';\s*(' + TOKEN + r')(?:\s*=\s*(?:"((?:[^"\\]|\\.)*)"|(' + TOKEN + r')))?\s*')


def parse_link_headers(values: list[str], base: str) -> tuple[list, list]:
    alternate, canonical = [], []
    if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
        raise ValueError('Link capture must be a list of complete field values')
    for value in values:
        for piece in split_links(value):
            match = re.fullmatch(r'\s*<([^>]*)>(.*)', piece, re.S)
            if match is None:
                raise ValueError(f'Malformed Link header: {piece!r}')
            tail, pos, params = match.group(2), 0, []
            while pos < len(tail):
                if not tail[pos:].strip(): break
                p = PARAM.match(tail, pos)
                if p is None:
                    raise ValueError(f'Malformed Link parameter near {tail[pos:]!r}')
                val = p.group(2) if p.group(2) is not None else p.group(3)
                if p.group(2) is not None:
                    val = re.sub(r'\\(.)', r'\1', val)
                params.append((p.group(1).lower(), val)); pos = p.end()
            # This consumer deliberately does not process non-default contexts.
            # RFC 8288 permits ignoring the entire link, not just its anchor.
            if any(k == 'anchor' for k, _ in params):
                continue
            rel = next((v for k, v in params if k == 'rel'), '') or ''
            rels = rel.lower().split()
            languages = [v.lower() for k, v in params if k == 'hreflang' and v]
            if 'canonical' not in rels and not ('alternate' in rels and languages):
                continue
            target = url(match.group(1), base)
            if 'canonical' in rels: canonical.append(target)
            if 'alternate' in rels:
                alternate.extend([language, target] for language in languages)
    return alternate, canonical


def safe_child(root: Path, rel: str) -> Path:
    result = (root / rel).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError('Path escapes its local build mount')
    return result


def read_local(path: Path, root: Path) -> str:
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('File symlink escapes its local build mount')
    return path.read_text(encoding='utf8')


def unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out: raise ValueError(f'Duplicate JSON member: {key!r}')
        out[key] = value
    return out


def read_json(path: Path, root: Path | None = None):
    text = read_local(path, root) if root is not None else path.read_text(encoding='utf8')
    return json.loads(text, object_pairs_hook=unique_object)


def load_build(manifest_path: Path | str, build_root: Path | str, *, html_extractor=None):
    manifest_path, build_root = Path(manifest_path), Path(build_root)
    manifest = read_json(manifest_path)
    # Validate before reading any files or enumerating mounts.
    from .schema import normalize_manifest
    manifest = normalize_manifest(manifest)
    observations, sitemaps = {}, {}
    for origin, relative_dir in manifest['config']['origins'].items():
        directory = safe_child(build_root, relative_dir)
        if not directory.is_dir():
            raise FileNotFoundError(f'Missing mounted origin directory: {directory}')
        for p in sorted(directory.rglob('*.html')):
            rel = p.relative_to(directory).as_posix()
            if rel == 'index.html': route_path = '/'
            elif rel.endswith('/index.html'): route_path = '/' + rel[:-10]
            elif manifest['config'].get('html_extension') == 'extensionless': route_path = '/' + rel[:-5]
            else: route_path = '/' + rel
            route = url(origin + route_path)
            if route in observations: raise ValueError(f'Two HTML files map to {route}')
            text = read_local(p, directory)
            if html_extractor is None:
                parser = PageParser(route)
                parser.feed(text); parser.close()
                observations[route] = parser.obs
            else:
                observations[route] = html_extractor(text, route)
        for p in sorted(directory.rglob('*.xml')):
            data = read_local(p, directory)
            if '<!DOCTYPE' in data.upper() or '<!ENTITY' in data.upper():
                raise ValueError('DTD/entity declarations are not accepted in local sitemaps')
            try: root = ET.fromstring(data)
            except ET.ParseError as exc: raise ValueError(f'Malformed XML: {p.name}: {exc}') from exc
            if root.tag not in ('{http://www.sitemaps.org/schemas/sitemap/0.9}urlset', 'urlset'):
                continue  # Local XML discovery never follows sitemap-index URLs.
            ns = root.tag[:-6]
            for entry in root:
                if entry.tag != ns + 'url': continue
                locations = [e.text for e in entry if e.tag == ns + 'loc']
                if len(locations) != 1 or not locations[0]:
                    raise ValueError('Sitemap url entry must have exactly one nonempty loc')
                route = url(locations[0].strip())
                links = []
                for child in entry:
                    if child.tag == '{http://www.w3.org/1999/xhtml}link':
                        if 'alternate' in child.get('rel', '').lower().split() and child.get('hreflang'):
                            if 'href' not in child.attrib:
                                raise ValueError('Sitemap alternate lacks href')
                            links.append([child.get('hreflang').lower(), url(child.attrib['href'], route)])
                sitemaps.setdefault(route, []).extend(links)
    headers_path = build_root / '_headers.json'
    if headers_path.exists():
        headers = read_json(headers_path, build_root)
        if not isinstance(headers, dict): raise ValueError('Header capture must be an object')
        seen = set()
        for raw_route, h in headers.items():
            route = url(raw_route)
            if route in seen: raise ValueError('Normalized duplicate header route')
            seen.add(route)
            if not isinstance(h, dict): raise ValueError('Header record must be an object')
            status = h.get('status', 200)
            if type(status) is not int or not 100 <= status <= 599:
                raise ValueError('HTTP status must be an integer in [100,599]')
            o = observations.setdefault(route, {'lang': '', 'key': None, 'links': [], 'alternates': {}, 'canonical': {}})
            o['status'] = status
            if h.get('location') and status in {301,302,303,307,308}:
                target = url(h['location'], route)
                # An HTTP redirect is authoritative over a captured response body.
                o['redirect'], o['redirect_transport'] = target, 'http-fixture'
            alts, canon = parse_link_headers(h.get('link', []), route)
            o['alternates']['http'] = alts
            o['canonical']['http'] = canon
    return snapshot(manifest, observations, sitemaps)
