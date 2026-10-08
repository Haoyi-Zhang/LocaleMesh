"""Tracked-read incremental evaluator, separately coded from the full evaluator.

Reads of absent facts are recorded. A transaction takes invalidation from the OLD
reverse map before removing old reads. It then installs all fact changes atomically,
re-evaluates affected owners, and replaces their issue sets and read dependencies.
"""
from __future__ import annotations
from collections import defaultdict
from copy import deepcopy
from time import perf_counter_ns
from urllib.parse import urlsplit
from .model import FactMap, FactKey, Issue, owners


class Incremental:
    def __init__(self, facts: FactMap):
        self._facts = deepcopy(facts)
        self.reads: dict[str, set[FactKey]] = {}
        self.reverse: dict[FactKey, set[str]] = defaultdict(set)
        self.cache: dict[str, set[Issue]] = {}
        self.last = {}
        self.edge_count = 0
        self.all_issues: set[Issue] = set()
        for owner in sorted(owners(self._facts)):
            self._refresh(owner)

    @property
    def facts(self) -> FactMap:
        """Return an owned copy; callers cannot mutate cached evaluator state."""
        return deepcopy(self._facts)

    def _refresh(self, owner: str):
        self.edge_count -= len(self.reads.get(owner, ()))
        self.all_issues.difference_update(self.cache.get(owner, ()))
        for key in self.reads.get(owner, set()):
            self.reverse[key].discard(owner)
            if not self.reverse[key]:
                del self.reverse[key]
        used = set()
        def get(key, default=None):
            used.add(key)
            return self._facts.get(key, default)
        issues = check_owner(owner, get)
        self.reads[owner] = used
        self.edge_count += len(used)
        self.all_issues.update(issues)
        for key in used:
            self.reverse[key].add(owner)
        self.cache[owner] = issues

    def update(self, changes: dict[FactKey, object], *, broken_drop_old: bool = False):
        """Apply an exact fact delta. None means deletion; facts cannot hold None.

        broken_drop_old is an explicitly UNSOUND ablation, never the normal path.
        """
        begin = perf_counter_ns()
        changed = {k for k, v in changes.items() if self._facts.get(k) != v}
        impacted = {o for k in changed for o in self.reverse.get(k, ())}
        impacted |= {k[1] for k in changed if k[0] in ('m', 'o', 's')}
        invalidated_at = perf_counter_ns()
        for k in changed:
            if changes[k] is None:
                self._facts.pop(k, None)
            else:
                self._facts[k] = deepcopy(changes[k])
        if broken_drop_old:
            # Common deletion bug: forget incoming readers of removed facts.
            impacted = {o for k in changed if changes[k] is not None
                        for o in self.reverse.get(k, ())}
            impacted |= {k[1] for k in changed if k[0] in ('m', 'o', 's')}
        # An owner is active if any declaration, page, or sitemap entry remains.
        active = lambda o: any((kind, o) in self._facts for kind in ('m', 'o', 's'))
        for owner in sorted(impacted):
            if active(owner):
                self._refresh(owner)
            else:
                self.edge_count -= len(self.reads.get(owner, ()))
                self.all_issues.difference_update(self.cache.get(owner, ()))
                for k in self.reads.pop(owner, set()):
                    self.reverse[k].discard(owner)
                    if not self.reverse[k]:
                        del self.reverse[k]
                self.cache.pop(owner, None)
        finish = perf_counter_ns()
        self.last = {'changed_facts': len(changed), 'invalidated_owners': len(impacted),
                     'invalidation_ns': invalidated_at - begin, 'update_ns': finish - begin,
                     'dependency_edges': self.edge_count}
        return self.last

    def issues(self) -> set[Issue]:
        return set(self.all_issues)


def check_owner(owner, read):
    """Independently expressed owner rules; reads include failed lookups."""
    found = set()
    cfg = read(('cfg',))
    origins = cfg['origins']
    alias_map = cfg.get('aliases', {})
    def report(code, ch='', extra='', ambiguity=False):
        found.add(Issue('ambiguity' if ambiguity else 'release', code, owner, ch, str(extra)))
    def terminal(u):
        path = []
        while u not in path:
            path.append(u)
            p = urlsplit(u)
            if p.scheme + '://' + p.netloc not in origins:
                return u, 'external'
            a = alias_map.get(u)
            if a is not None:
                u = a
                continue
            observation = read(('o', u))
            if observation is None:
                return u, 'missing'
            redirect = observation.get('redirect')
            if redirect:
                u = redirect
                continue
            code = observation.get('status', 200)
            return (u, 'ok') if code >= 200 and code < 300 else (u, 'unavailable')
        return u, 'cycle'
    def resolve_or_report(u, rule, ch):
        end, status = terminal(u)
        if status == 'external':
            report('UNMOUNTED_TARGET', ch, u, True)
        elif status != 'ok':
            report(rule, ch, u)
        return end, status
    def alternatives(u, ch):
        if ch != 'sitemap':
            return read(('o', u), {}).get('alternates', {}).get(ch, [])
        return read(('s', u), [])

    spec = read(('m', owner))
    actual = read(('o', owner))
    sitemap = read(('s', owner))
    for code, detail in (actual or {}).get('diagnostics', []):
        report(code, 'ingestion', detail, True)
    if sitemap is not None:
        resolve_or_report(owner, 'SITEMAP_TARGET', 'sitemap')
    if spec is None:
        if cfg.get('complete_manifest', False):
            report('UNDECLARED_ROUTE', ambiguity=True)
        return found
    phase = spec.get('state', 'published')
    if spec.get('ambiguous'):
        report('DECLARATION_CONFLICT', ambiguity=True)
        return found
    if phase == 'published':
        peers = read(('g', spec['key'], spec['locale'].lower()), ())
        if len(peers) > 1:
            report('IDENTITY_COLLISION', extra=spec['key'] + ':' + spec['locale'], ambiguity=True)
            return found
    if phase in {'draft', 'removed'}:
        if actual is not None:
            report('UNEXPECTED_PUBLICATION')
        if sitemap is not None:
            report('SITEMAP_PUBLICATION', 'sitemap')
        return found
    if actual is None:
        report('MISSING_ROUTE')
        return found
    if phase == 'redirect':
        permitted = spec.get('redirect_allowed')
        if permitted is None:
            permitted = [spec.get('redirect_to')]
        if actual.get('redirect') not in permitted:
            report('REDIRECT_POLICY')
        resolve_or_report(owner, 'REDIRECT_TARGET', 'redirect')
        if sitemap is not None and not spec.get('sitemap', False):
            report('SITEMAP_REDIRECT', 'sitemap')
        if spec.get('sitemap', False) and sitemap is None:
            report('SITEMAP_MISSING', 'sitemap')
        return found
    if actual.get('redirect') or actual.get('status', 200) not in range(200, 300):
        report('ROUTE_STATE')
    valid_languages = {v.lower() for v in spec.get('represented_locales', [spec['locale']])}
    if actual.get('lang', '').lower() not in valid_languages:
        report('LANGUAGE', 'html')
    if 'key' in actual and actual['key'] is not None and actual['key'] != spec['key']:
        report('CONTENT_ID', 'html')
    if spec.get('sitemap') and sitemap is None:
        report('SITEMAP_MISSING', 'sitemap')
    allowed_canonical = spec.get('canonical_allowed')
    for c in spec.get('canonical_channels', ['html']):
        destinations = actual.get('canonical', {}).get(c, [])
        required = spec.get('canonical_required', allowed_canonical is not None)
        if required and not destinations:
            report('CANONICAL_MISSING', c)
        if len(set(destinations)) >= 2:
            report('CANONICAL_MULTIPLE', c)
        for destination in destinations:
            if allowed_canonical is not None and destination not in allowed_canonical:
                report('CANONICAL_POLICY', c, destination)
            resolve_or_report(destination, 'CANONICAL_TARGET', c)
    for c, requirements in spec.get('discovery', {}).items():
        data = alternatives(owner, c)
        grouped = defaultdict(set)
        for language, destination in data:
            grouped[language].add(destination)
        for language in requirements.get('required', []):
            if language.lower() not in grouped:
                report('DISCOVERY_MISSING', c, language.lower())
        for language, choices in grouped.items():
            if len(choices) >= 2:
                report('DISCOVERY_MULTIPLE', c, language)
        for language, destination in data:
            final, status = resolve_or_report(destination, 'DISCOVERY_TARGET', c)
            if status != 'ok':
                continue
            if language == 'x-default':
                if spec.get('x_default') is not None and spec['x_default'] != destination:
                    report('XDEFAULT_POLICY', c, destination)
                continue
            target = read(('m', final))
            uncertain = target is None or target.get('ambiguous')
            if not uncertain:
                bucket = read(('g', target['key'], target['locale'].lower()), ())
                uncertain = len(bucket) > 1
            if uncertain:
                report('TARGET_IDENTITY_UNKNOWN', c, destination, True)
                continue
            if target['key'] != spec['key']:
                report('DISCOVERY_ID', c, destination)
            possible = {language.lower()}
            possible.update(v.lower() for v in spec.get('fallbacks', {}).get(language, []))
            if target['locale'].lower() not in possible:
                report('DISCOVERY_LOCALE', c, destination)
            if target.get('state', 'published') != 'published':
                report('DISCOVERY_PUBLICATION', c, destination)
            if requirements.get('reciprocal') and final != owner:
                matched = False
                for back_language, back_url in alternatives(final, c):
                    if back_language == spec['locale'].lower() and terminal(back_url) == (owner, 'ok'):
                        matched = True
                        break
                if not matched:
                    report('RECIPROCITY', c, destination)
    agreement = spec.get('agree_channels', [])
    for ia in range(len(agreement)):
        for ib in range(ia + 1, len(agreement)):
            a, b = agreement[ia], agreement[ib]
            x, y = alternatives(owner, a), alternatives(owner, b)
            if x and y and set(map(tuple, x)) != set(map(tuple, y)):
                report('CHANNEL_CONFLICT', a + ':' + b)
    if cfg.get('check_links', True):
        for destination in actual.get('links', []):
            p = urlsplit(destination)
            if p.scheme + '://' + p.netloc in origins:
                resolve_or_report(destination, 'LINK_TARGET', 'html')
    return found
