"""Data model only. No checking logic is shared by the two evaluators."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from collections import defaultdict
from typing import Any
from urllib.parse import urlsplit, urlunsplit, urljoin
import copy

FactKey = tuple[str, ...]
FactMap = dict[FactKey, Any]

@dataclass(frozen=True, order=True)
class Issue:
    category: str
    code: str
    owner: str
    channel: str = ''
    detail: str = ''
    def json(self) -> dict[str, str]:
        return asdict(self)

def url(value: str, base: str = '') -> str:
    """Resolve a URL without guessing path equivalence or fetching a target."""
    if not isinstance(value, str) or not isinstance(base, str):
        raise ValueError('Publication URL must be a string')
    p = urlsplit(urljoin(base, value))
    _ = p.port  # Validate malformed and out-of-range ports before accepting a URL.
    if p.scheme not in ('http', 'https') or not p.netloc or p.username or p.password:
        raise ValueError(f'Unsupported publication URL: {value!r}')
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or '/', p.query, ''))

def canon_pairs(pairs: list | tuple) -> list[list[str]]:
    # Ordering and exact repeated declarations are semantically idempotent.
    return [list(x) for x in sorted(set((str(a).lower(), str(b)) for a, b in pairs))]

def snapshot(manifest: dict, observations: dict, sitemaps: dict | None = None) -> FactMap:
    """Materialize an immutable-by-convention fact snapshot, including group buckets.

    Manifests originate outside generated HTML. Group keys are essential negative
    dependencies: adding a previously absent variant changes a previously empty read.
    """
    facts: FactMap = {('cfg',): copy.deepcopy(manifest['config'])}
    groups: dict[FactKey, list[str]] = defaultdict(list)
    for route, spec in manifest['pages'].items():
        route = url(route)
        if ('m', route) in facts:
            raise ValueError('Normalized duplicate manifest route')
        facts[('m', route)] = copy.deepcopy(spec)
        if spec.get('state', 'published') == 'published':
            groups[('g', spec['key'], spec['locale'].lower())].append(route)
    for key, routes in groups.items():
        facts[key] = tuple(sorted(routes))
    for route, obs in observations.items():
        o = copy.deepcopy(obs)
        o['alternates'] = {c: canon_pairs(p) for c, p in o.get('alternates', {}).items()}
        o['canonical'] = {c: sorted(set(v)) for c, v in o.get('canonical', {}).items()}
        o['links'] = sorted(set(o.get('links', [])))
        if ('o', url(route)) in facts:
            raise ValueError('Normalized duplicate observation route')
        facts[('o', url(route))] = o
    for route, pairs in (sitemaps or {}).items():
        if ('s', url(route)) in facts:
            raise ValueError('Normalized duplicate sitemap route')
        facts[('s', url(route))] = canon_pairs(pairs)
    return facts

def owners(facts: FactMap) -> set[str]:
    return {k[1] for k in facts if k[0] in ('m', 'o', 's')}

def delta(old: FactMap, new: FactMap) -> dict[FactKey, Any]:
    """Snapshot differencing is O(N), NOT included in update-only timing."""
    return {k: copy.deepcopy(new.get(k)) for k in old.keys() | new.keys()
            if old.get(k) != new.get(k)}

def release_issues(issues):
    return [i for i in issues if i.category == 'release']
