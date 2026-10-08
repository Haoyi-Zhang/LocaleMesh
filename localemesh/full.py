"""Independent full evaluator: straightforward whole-snapshot pass.

It deliberately neither imports incremental.py nor calls its predicate functions.
Only the fact representation and Issue value type are shared.
"""
from __future__ import annotations
from urllib.parse import urlsplit
from .model import FactMap, Issue, owners


def evaluate(facts: FactMap) -> set[Issue]:
    out: set[Issue] = set()
    config = facts[('cfg',)]
    mounts = set(config['origins'])
    aliases = config.get('aliases', {})

    def emit(code, owner, channel='', detail='', category='release'):
        out.add(Issue(category, code, owner, channel, str(detail)))

    def resolve(start):
        current = start
        seen = set()
        while True:
            if current in seen:
                return current, 'cycle'
            seen.add(current)
            if f'{urlsplit(current).scheme}://{urlsplit(current).netloc}' not in mounts:
                return current, 'external'
            if current in aliases:
                current = aliases[current]
                continue
            rec = facts.get(('o', current))
            if rec is None:
                return current, 'missing'
            if rec.get('redirect'):
                current = rec['redirect']
                continue
            if not 200 <= rec.get('status', 200) < 300:
                return current, 'unavailable'
            return current, 'ok'

    def channel(route, name):
        if name == 'sitemap':
            return facts.get(('s', route), [])
        obs = facts.get(('o', route), {})
        return obs.get('alternates', {}).get(name, [])

    def reachable(owner, target, code, ch):
        terminal, why = resolve(target)
        if why != 'ok':
            if why == 'external':
                emit('UNMOUNTED_TARGET', owner, ch, target, 'ambiguity')
            else:
                emit(code, owner, ch, target)
        return terminal, why

    for route in owners(facts):
        m = facts.get(('m', route))
        o = facts.get(('o', route))
        sm_present = ('s', route) in facts
        for code, detail in (o or {}).get('diagnostics', []):
            emit(code, route, 'ingestion', detail, 'ambiguity')
        if sm_present:
            reachable(route, route, 'SITEMAP_TARGET', 'sitemap')
        if m is None:
            if config.get('complete_manifest', False):
                emit('UNDECLARED_ROUTE', route, category='ambiguity')
            continue
        state = m.get('state', 'published')
        if m.get('ambiguous', False):
            emit('DECLARATION_CONFLICT', route, category='ambiguity')
            continue
        if state == 'published' and len(facts.get(('g', m['key'], m['locale'].lower()), ())) > 1:
            emit('IDENTITY_COLLISION', route, detail=m['key'] + ':' + m['locale'], category='ambiguity')
            continue
        if state in ('draft', 'removed'):
            if o is not None:
                emit('UNEXPECTED_PUBLICATION', route)
            if sm_present:
                emit('SITEMAP_PUBLICATION', route, 'sitemap')
            continue
        if o is None:
            emit('MISSING_ROUTE', route)
            continue
        if state == 'redirect':
            permitted = m.get('redirect_allowed')
            if permitted is None: permitted = [m.get('redirect_to')]
            if o.get('redirect') not in permitted:
                emit('REDIRECT_POLICY', route)
            reachable(route, route, 'REDIRECT_TARGET', 'redirect')
            if sm_present and not m.get('sitemap', False):
                emit('SITEMAP_REDIRECT', route, 'sitemap')
            if m.get('sitemap', False) and not sm_present:
                emit('SITEMAP_MISSING', route, 'sitemap')
            continue
        if o.get('redirect') or not 200 <= o.get('status', 200) < 300:
            emit('ROUTE_STATE', route)
        accepted_lang = m.get('represented_locales', [m['locale']])
        if o.get('lang', '').lower() not in [l.lower() for l in accepted_lang]:
            emit('LANGUAGE', route, 'html')
        if o.get('key') is not None and o['key'] != m['key']:
            emit('CONTENT_ID', route, 'html')
        if m.get('sitemap', False) and not sm_present:
            emit('SITEMAP_MISSING', route, 'sitemap')
        allowed = m.get('canonical_allowed')
        for ch in m.get('canonical_channels', ['html']):
            actual = o.get('canonical', {}).get(ch, [])
            if m.get('canonical_required', allowed is not None) and not actual:
                emit('CANONICAL_MISSING', route, ch)
            if len(set(actual)) > 1:
                emit('CANONICAL_MULTIPLE', route, ch)
            for target in actual:
                if allowed is not None and target not in allowed:
                    emit('CANONICAL_POLICY', route, ch, target)
                reachable(route, target, 'CANONICAL_TARGET', ch)
        selected = m.get('discovery', {})
        for ch, policy in selected.items():
            entries = channel(route, ch)
            labels = {l for l, _ in entries}
            for wanted in policy.get('required', []):
                if wanted.lower() not in labels:
                    emit('DISCOVERY_MISSING', route, ch, wanted.lower())
            for label in labels:
                if len({t for l, t in entries if l == label}) > 1:
                    emit('DISCOVERY_MULTIPLE', route, ch, label)
            for label, target in entries:
                terminal, why = reachable(route, target, 'DISCOVERY_TARGET', ch)
                if why != 'ok':
                    continue
                if label == 'x-default':
                    if m.get('x_default') is not None and target != m['x_default']:
                        emit('XDEFAULT_POLICY', route, ch, target)
                    continue
                tm = facts.get(('m', terminal))
                if tm is None or tm.get('ambiguous'):
                    emit('TARGET_IDENTITY_UNKNOWN', route, ch, target, 'ambiguity')
                    continue
                target_group = facts.get(('g', tm['key'], tm['locale'].lower()), ())
                if len(target_group) > 1:
                    emit('TARGET_IDENTITY_UNKNOWN', route, ch, target, 'ambiguity')
                    continue
                if tm['key'] != m['key']:
                    emit('DISCOVERY_ID', route, ch, target)
                permitted = [label] + m.get('fallbacks', {}).get(label, [])
                if tm['locale'].lower() not in [x.lower() for x in permitted]:
                    emit('DISCOVERY_LOCALE', route, ch, target)
                if tm.get('state', 'published') != 'published':
                    emit('DISCOVERY_PUBLICATION', route, ch, target)
                if policy.get('reciprocal', False) and terminal != route:
                    back = [t for l, t in channel(terminal, ch) if l == m['locale'].lower()]
                    if not any(resolve(b) == (route, 'ok') for b in back):
                        emit('RECIPROCITY', route, ch, target)
        channels = m.get('agree_channels', [])
        for i, a in enumerate(channels):
            for b in channels[i + 1:]:
                left, right = channel(route, a), channel(route, b)
                # Agreement is required only when both channels have data.
                if left and right and sorted(left) != sorted(right):
                    emit('CHANNEL_CONFLICT', route, a + ':' + b)
        if config.get('check_links', True):
            for target in o.get('links', []):
                if f'{urlsplit(target).scheme}://{urlsplit(target).netloc}' in mounts:
                    reachable(route, target, 'LINK_TARGET', 'html')
    return out
