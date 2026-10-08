"""Validate and normalize the public manifest boundary, not semantic policies.

Conflicting *valid* declarations are evaluator ambiguities. Structurally invalid
records must not silently change the evaluator's obligations.
"""
from __future__ import annotations
from copy import deepcopy
from urllib.parse import urlsplit
from .model import url

CHANNELS = {'html', 'http', 'sitemap'}


def text(value, context):
    if not isinstance(value, str) or not value:
        raise ValueError(f'{context} must be a nonempty string')
    return value


def strings(value, context):
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
        raise ValueError(f'{context} must be a list of nonempty strings')
    return value


def normalize_spec(spec):
    if not isinstance(spec, dict): raise ValueError('Page specification must be an object')
    s = deepcopy(spec)
    state = s.get('state', 'published')
    if not isinstance(state, str) or state not in {'published', 'redirect', 'draft', 'removed'}:
        raise ValueError(f'Unknown publication state: {state!r}')
    text(s.get('key'), 'Content key'); text(s.get('locale'), 'Locale')
    for k in ('ambiguous', 'sitemap', 'canonical_required'):
        if k in s and type(s[k]) is not bool: raise ValueError(f'{k} must be Boolean')
    for k in ('canonical_allowed', 'redirect_allowed'):
        if k in s and s[k] is not None:
            s[k] = [url(x) for x in strings(s[k], k)]
    for k in ('redirect_to', 'x_default'):
        if s.get(k) is not None: s[k] = url(text(s[k], k))
    if 'represented_locales' in s: strings(s['represented_locales'], 'represented_locales')
    for k in ('canonical_channels', 'agree_channels'):
        if k in s:
            strings(s[k], k)
            allowed = {'html', 'http'} if k == 'canonical_channels' else CHANNELS
            if not set(s[k]) <= allowed: raise ValueError(f'Unsupported {k}')
    discovery = s.get('discovery', {})
    if not isinstance(discovery, dict) or not set(discovery) <= CHANNELS:
        raise ValueError('Unsupported discovery channel')
    for ch, d in discovery.items():
        if not isinstance(d, dict): raise ValueError('Discovery obligation must be an object')
        strings(d.get('required', []), 'required locales')
        if 'reciprocal' in d and type(d['reciprocal']) is not bool:
            raise ValueError('reciprocal must be Boolean')
    fallback = s.get('fallbacks', {})
    if not isinstance(fallback, dict): raise ValueError('fallbacks must be an object')
    normalized = {}
    for label, langs in fallback.items():
        key = text(label, 'Fallback label').lower()
        if key in normalized: raise ValueError('Case-equivalent duplicate fallback labels')
        normalized[key] = strings(langs, 'Fallback languages')
    if 'fallbacks' in s: s['fallbacks'] = normalized
    return s


def normalize_config(config):
    if not isinstance(config, dict) or not isinstance(config.get('origins'), dict):
        raise ValueError('config.origins must be an object')
    c = deepcopy(config); mounts = {}
    for origin, path in c['origins'].items():
        text(path, 'Mount directory')
        u = url(origin); p = urlsplit(u)
        if p.path != '/' or p.query or '#' in origin:
            raise ValueError('Origin must not include a path, query, or fragment')
        key = p.scheme + '://' + p.netloc
        if key in mounts: raise ValueError('Normalized duplicate origin')
        mounts[key] = path
    c['origins'] = mounts
    aliases = c.get('aliases', {})
    if not isinstance(aliases, dict): raise ValueError('aliases must be an object')
    normalized = {}
    for source, dest in aliases.items():
        key = url(source)
        if key in normalized: raise ValueError('Normalized duplicate alias')
        normalized[key] = url(dest)
    if 'aliases' in c: c['aliases'] = normalized
    for k in ('complete_manifest', 'check_links'):
        if k in c and type(c[k]) is not bool: raise ValueError(f'{k} must be Boolean')
    if 'html_extension' in c and (not isinstance(c['html_extension'], str) or c['html_extension'] not in {'extensionless', 'html'}):
        raise ValueError('Unsupported html_extension policy')
    return c


def normalize_manifest(manifest):
    if not isinstance(manifest, dict) or type(manifest.get('schema')) is not int or manifest.get('schema') != 1:
        raise ValueError('Expected manifest schema 1')
    m = deepcopy(manifest)
    m['config'] = normalize_config(m.get('config'))
    if not isinstance(m.get('pages'), dict): raise ValueError('pages must be an object')
    pages = {}
    for raw, spec in m['pages'].items():
        key = url(raw)
        if key in pages: raise ValueError(f'Normalized duplicate manifest route: {key}')
        pages[key] = normalize_spec(spec)
    m['pages'] = pages
    return m


def normalize_observation(observation):
    if not isinstance(observation, dict): raise ValueError('Observation must be an object')
    o = deepcopy(observation)
    status = o.get('status', 200)
    if type(status) is not int or not 100 <= status <= 599:
        raise ValueError('Observation status must be an HTTP integer')
    if not isinstance(o.get('lang', ''), str): raise ValueError('Observed language must be a string')
    if o.get('key') is not None: text(o['key'], 'Observed content key')
    for kind, allowed in (('canonical', {'html', 'http'}), ('alternates', {'html', 'http'})):
        mapping = o.get(kind, {})
        if not isinstance(mapping, dict) or not set(mapping) <= allowed:
            raise ValueError(f'Unsupported observed {kind} channel')
        for ch, values in mapping.items():
            if kind == 'canonical':
                mapping[ch] = sorted(set(url(x) for x in strings(values, 'Canonical targets')))
            else:
                mapping[ch] = normalize_pairs(values)
    o['links'] = sorted(set(url(x) for x in strings(o.get('links', []), 'Links')))
    if o.get('redirect') is not None: o['redirect'] = url(text(o['redirect'], 'Redirect target'))
    diagnostics = o.get('diagnostics', [])
    if not isinstance(diagnostics, list) or any(not isinstance(x, (list, tuple)) or len(x) != 2
            or not all(isinstance(v, str) for v in x) for x in diagnostics):
        raise ValueError('Diagnostics must be code/detail pairs')
    return o


def normalize_pairs(pairs):
    if not isinstance(pairs, (list, tuple)):
        raise ValueError('Alternate declarations must be a sequence')
    result = set()
    for pair in pairs:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError('Alternate declaration must be a label/URL pair')
        result.add((text(pair[0], 'Alternate label').lower(), url(pair[1])))
    return [list(x) for x in sorted(result)]
