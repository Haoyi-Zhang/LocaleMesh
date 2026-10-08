"""Transparent local reference baselines, NOT executed third-party products.

Their findings are used for seeded-release detection, not speed claims. Framework
native and third-party binaries are reported unavailable separately, never as passes.
"""
from urllib.parse import urlsplit
from .model import owners


def dead_links(facts):
    cfg=facts[('cfg',)];out=set()
    def reachable(t):
        seen=set()
        while t not in seen:
            seen.add(t)
            p=urlsplit(t)
            if p.scheme+'://'+p.netloc not in cfg['origins']:return True  # not probed
            if t in cfg.get('aliases',{}):t=cfg['aliases'][t];continue
            o=facts.get(('o',t))
            if not o:return False
            if o.get('redirect'):t=o['redirect'];continue
            return 200<=o.get('status',200)<300
        return False
    for k,o in facts.items():
        if k[0]!='o':continue
        targets=list(o.get('links',[]))
        targets += [x for values in o.get('canonical',{}).values() for x in values]
        targets += [t for values in o.get('alternates',{}).values() for _,t in values]
        if o.get('redirect'):targets.append(o['redirect'])
        for t in targets:
            if not reachable(t):out.add((k[1],t))
    return out


def html_annotations(facts):
    out=set();cfg=facts[('cfg',)]
    def resolve(t):
        seen=set()
        while t not in seen:
            seen.add(t)
            t1=cfg.get('aliases',{}).get(t)
            if t1 is not None:t=t1;continue
            o=facts.get(('o',t))
            if o is None:return None
            if o.get('redirect'):t=o['redirect'];continue
            return t if 200<=o.get('status',200)<300 else None
        return None
    for k,o in facts.items():
        if k[0]!='o':continue
        r=k[1];pairs=o.get('alternates',{}).get('html',[])
        if not pairs:continue
        if not any(resolve(t)==r for _,t in pairs):out.add((r,'self'))
        for label,t in pairs:
            if label=='x-default':continue
            target=resolve(t)
            if target is None:out.add((r,'target'));continue
            to=facts[('o',target)]
            if to.get('lang','').lower()!=label:out.add((r,'locale'))
            back=to.get('alternates',{}).get('html',[])
            if not any(l==o.get('lang','').lower() and resolve(v)==r for l,v in back):out.add((r,'reciprocity'))
    return out


def policy_blind(facts):
    """A deliberately strict global-locale/self-canonical heuristic, not a vendor."""
    out=set();cfg=facts[('cfg',)]
    for k,o in facts.items():
        if k[0]!='o' or o.get('redirect'):continue
        r=k[1]
        pairs=o.get('alternates',{}).get('html',[]) or o.get('alternates',{}).get('http',[]) or facts.get(('s',r),[])
        if pairs and {l for l,t in pairs if l!='x-default'} != set(cfg['locales']):out.add((r,'incomplete'))
        for cs in o.get('canonical',{}).values():
            if any(t!=r for t in cs):out.add((r,'cross-canonical'))
        for label,t in pairs:
            to=facts.get(('o',t))
            if to and label!='x-default' and to.get('lang')!=label:out.add((r,'fallback'))
    return out


def manifest_presence(facts):
    """Route/state-only control approximating what a builder can establish locally.

    It intentionally ignores content identity, alternate annotations, canonicals, and
    cross-channel policy. This is an authored control, not a measured framework tool.
    """
    out=set()
    for k,spec in facts.items():
        if k[0] != 'm':
            continue
        route=k[1]; obs=facts.get(('o',route)); state=spec.get('state','published')
        if state == 'published':
            if obs is None:
                out.add((route,'missing'))
            elif obs.get('redirect') or not 200 <= obs.get('status',200) < 300:
                out.add((route,'state'))
        elif state in ('draft','removed'):
            if obs is not None:
                out.add((route,'unexpected'))
        elif state == 'redirect':
            if obs is None or not obs.get('redirect'):
                out.add((route,'redirect'))
    return out


def joint_output(facts):
    """Joint output-only annotation control with no release contract semantics.

    It checks locally observable reachability, labels, self links, reciprocity,
    canonical multiplicity, and pair agreement across nonempty channels. It cannot
    know required coverage, stable content identity, allowed fallback/canonical
    policy, publication intent, or redirect intent.
    """
    out=set(); cfg=facts[('cfg',)]; origins=set(cfg['origins']); aliases=cfg.get('aliases',{})
    def resolve(start):
        seen=set(); cur=start
        while cur not in seen:
            seen.add(cur)
            p=urlsplit(cur); origin=p.scheme+'://'+p.netloc
            if origin not in origins:
                return cur,'external'
            if cur in aliases:
                cur=aliases[cur]; continue
            obs=facts.get(('o',cur))
            if obs is None:
                return cur,'missing'
            if obs.get('redirect'):
                cur=obs['redirect']; continue
            return (cur,'ok') if 200 <= obs.get('status',200) < 300 else (cur,'unavailable')
        return cur,'cycle'
    def channels(route):
        obs=facts.get(('o',route),{})
        result={k:list(v) for k,v in obs.get('alternates',{}).items() if v}
        sm=facts.get(('s',route))
        if sm:
            result['sitemap']=list(sm)
        return result
    for k,obs in facts.items():
        if k[0] != 'o':
            continue
        route=k[1]
        # Canonicals: purely structural/reachability checks.
        for ch,targets in obs.get('canonical',{}).items():
            if len(set(targets)) > 1:
                out.add((route,ch,'canonical-multiple'))
            for target in targets:
                _,status=resolve(target)
                if status not in ('ok','external'):
                    out.add((route,ch,'canonical-target'))
        actual=channels(route); lang=obs.get('lang','').lower()
        for ch,pairs in actual.items():
            grouped={}
            for label,target in pairs:
                grouped.setdefault(label,set()).add(target)
            if any(len(v)>1 for v in grouped.values()):
                out.add((route,ch,'multiple'))
            if lang and lang in grouped and not any(resolve(t)==(route,'ok') for t in grouped[lang]):
                out.add((route,ch,'self'))
            for label,target in pairs:
                terminal,status=resolve(target)
                if status not in ('ok','external'):
                    out.add((route,ch,'target'))
                    continue
                if status != 'ok' or label == 'x-default':
                    continue
                target_obs=facts.get(('o',terminal),{})
                if target_obs.get('lang','').lower() != label:
                    out.add((route,ch,'label'))
                if terminal != route and lang:
                    back=channels(terminal).get(ch,[])
                    if not any(l==lang and resolve(t)==(route,'ok') for l,t in back):
                        out.add((route,ch,'reciprocity'))
        nonempty=list(actual)
        for i,a in enumerate(nonempty):
            for b in nonempty[i+1:]:
                if set(map(tuple,actual[a])) != set(map(tuple,actual[b])):
                    out.add((route,a+':'+b,'agreement'))
        for target in obs.get('links',[]):
            p=urlsplit(target)
            if p.scheme+'://'+p.netloc in origins and resolve(target)[1] != 'ok':
                out.add((route,'html','link'))
    return out
