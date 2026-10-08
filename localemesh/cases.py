"""Named, authored releases with explicit labels, not prevalence estimates.

Labels are attached to release operators independently of evaluator verdicts.
Development cases target individual obligations. Holdout uses unrevealed parameter
compositions after the rule implementation is fixed (same author, not blind review).
"""
from __future__ import annotations
from copy import deepcopy

# name, expected outcome, minimum decisive rule (not a full oracle issue set)
CASES = [
 ('clean','clean',None),
 ('partial_coverage','clean',None),
 ('missing_translation_allowed','clean',None),
 ('cross_locale_canonical_allowed','clean',None),
 ('fallback_allowed','clean',None),
 ('route_alias_allowed','clean',None),
 ('redirect_alias_allowed','clean',None),
 ('optional_xdefault','clean',None),
 ('no_optional_channels','clean',None),
 ('identical_rebuild','clean',None),
 ('declaration_conflict','ambiguity','DECLARATION_CONFLICT'),
 ('identity_collision','ambiguity','IDENTITY_COLLISION'),
 ('unmounted_canonical','ambiguity','UNMOUNTED_TARGET'),
 ('coherent_identity_swap','defect','DISCOVERY_ID'),
 ('removed_stale','defect','DISCOVERY_TARGET'),
 ('rename_stale','defect','DISCOVERY_TARGET'),
 ('wrong_canonical','defect','CANONICAL_POLICY'),
 ('stale_sitemap','defect','SITEMAP_TARGET'),
 ('channel_drift','defect','CHANNEL_CONFLICT'),
 ('broken_redirect','defect','REDIRECT_TARGET'),
 ('redirect_cycle','defect','REDIRECT_TARGET'),
 ('wrong_html_locale','defect','LANGUAGE'),
 ('draft_published','defect','UNEXPECTED_PUBLICATION'),
 ('prefix_stale','defect','DISCOVERY_TARGET'),
 ('key_reassigned','defect','DISCOVERY_ID'),
 ('missing_required_alternate','defect','DISCOVERY_MISSING'),
 ('missing_required_sitemap','defect','SITEMAP_MISSING'),
 ('missing_route','defect','MISSING_ROUTE'),
 ('redirect_wrong_live_target','defect','REDIRECT_POLICY'),
]


def change(data, name, key_index=0):
    m,o,s=deepcopy(data)
    pages=m['pages']; locales=m['config']['locales']; key=f'item-{key_index:04d}'
    group={d['locale']:r for r,d in pages.items() if d['key']==key and d.get('state')=='published'}
    src=group[locales[0]]; victim=group[locales[-1]]
    other_key=f'item-{(key_index+1):04d}'
    other={d['locale']:r for r,d in pages.items() if d['key']==other_key}
    def channels(r):
        return list(pages[r]['discovery'])
    def get(r,c): return s.get(r,[]) if c=='sitemap' else o[r].get('alternates',{}).get(c,[])
    def put(r,c,pairs):
        if c=='sitemap': s[r]=deepcopy(pairs)
        else: o[r].setdefault('alternates',{})[c]=deepcopy(pairs)
    def all_pairs_rewrite(old,new):
        for r in o:
            for c in list(o[r].get('alternates',{})):
                o[r]['alternates'][c]=[[l,new if t==old else t] for l,t in o[r]['alternates'][c]]
            o[r]['links']=[new if t==old else t for t in o[r].get('links',[])]
        for r in s:s[r]=[[l,new if t==old else t] for l,t in s[r]]
    def move(old,new):
        pages[new]=pages.pop(old); o[new]=o.pop(old)
        if old in s:s[new]=s.pop(old)
        pages[new]['canonical_allowed']=[new]; o[new]['canonical']['html']=[new]
    if name=='clean':pass
    elif name=='partial_coverage':
        # A legitimate disconnected subset, not mandatory global all-to-all coverage.
        for loc,r in group.items():
            keep={loc} if r==victim else set(locales[:-1])
            for c in channels(r):
                put(r,c,[[l,t] for l,t in get(r,c) if l in keep])
                pages[r]['discovery'][c]['required']=sorted(keep)
    elif name=='missing_translation_allowed':
        pages.pop(victim);o.pop(victim);s.pop(victim,None)
        for r in o:
            o[r]['links']=[t for t in o[r]['links'] if t!=victim]
        for r in group.values():
            if r==victim:continue
            for c in channels(r):
                put(r,c,[[l,t] for l,t in get(r,c) if t!=victim])
                pages[r]['discovery'][c]['required']=[l for l in locales if l!=locales[-1]]
    elif name=='cross_locale_canonical_allowed':
        pages[victim]['canonical_allowed']=[src];o[victim]['canonical']['html']=[src]
    elif name=='fallback_allowed':
        pages.pop(victim);o.pop(victim);s.pop(victim,None)
        all_pairs_rewrite(victim,src)
        for r in group.values():
            if r!=victim: pages[r]['fallbacks'][locales[-1]]=[locales[0]]
    elif name=='route_alias_allowed':
        alias=victim+'index.html';m['config']['aliases'][alias]=victim
        all_pairs_rewrite(victim,alias)
    elif name=='redirect_alias_allowed':
        old=src+'old-alias/'
        pages[old]={'key':key,'locale':locales[0],'state':'redirect','redirect_to':src,'sitemap':False}
        o[old]={'status':200,'lang':locales[0],'key':None,'redirect':src,'canonical':{},'alternates':{},'links':[]}
    elif name=='optional_xdefault':
        for r in group.values():
            for c in channels(r):put(r,c,get(r,c)+[['x-default',src]])
    elif name=='no_optional_channels':
        # An explicitly selected HTTP channel alone is a legal publication choice.
        for r,d in pages.items():
            pairs=get(r,channels(r)[0])
            d['discovery']={'http':{'required':list(locales),'reciprocal':True}}
            d['agree_channels']=[];d['sitemap']=False
            o[r]['alternates']={'http':deepcopy(pairs)}
        s={}
    elif name=='identical_rebuild':
        for r in o:
            for c in o[r].get('alternates',{}):
                o[r]['alternates'][c]=list(reversed(o[r]['alternates'][c]))*2
            o[r]['links']=list(reversed(o[r]['links']))*2
        for r in s:s[r]=list(reversed(s[r]))*2
    elif name=='declaration_conflict':pages[src]['ambiguous']=True
    elif name=='identity_collision':
        new=src+'duplicate/'
        pages[new]=deepcopy(pages[src]);o[new]=deepcopy(o[src]);s[new]=deepcopy(s[src])
        pages[new]['canonical_allowed']=[new];o[new]['canonical']['html']=[new]
    elif name=='unmounted_canonical':
        external='https://unmounted.invalid/selector/'
        pages[src]['canonical_allowed']=[external];o[src]['canonical']['html']=[external]
    elif name=='coherent_identity_swap':
        # Two internally reciprocal, reachable clusters with one swapped content identity.
        members_a=dict(group);members_b=dict(other)
        last=locales[-1]
        members_a[last],members_b[last]=members_b[last],members_a[last]
        for members in (members_a,members_b):
            pairs=list(map(list,members.items()))
            for r in members.values():
                for c in channels(r):put(r,c,pairs)
    elif name=='removed_stale':pages.pop(victim);o.pop(victim);s.pop(victim,None)
    elif name=='rename_stale':move(victim,victim.rstrip('/')+'-renamed/')
    elif name=='wrong_canonical':o[src]['canonical']['html']=[other[locales[0]]]
    elif name=='stale_sitemap':s[src+'retired/']=[]
    elif name=='channel_drift':
        # Both channels individually permit partial sets, but explicit agreement does not.
        for r,d in pages.items():
            pairs=get(r,channels(r)[0])
            for c in ('html','sitemap'):
                put(r,c,pairs);d['discovery'][c]={'required':[],'reciprocal':False}
            d['agree_channels']=['html','sitemap']
            for c in d['discovery']:d['discovery'][c]['reciprocal']=False
        s[src]=[p for p in s[src] if p[0]!=locales[-1]]
    elif name in ('broken_redirect','redirect_cycle','redirect_wrong_live_target'):
        r1=src+'old/';r2=src+'older/'
        target=(r2 if name=='redirect_cycle' else src+'missing/')
        if name=='redirect_wrong_live_target':target=other[locales[0]]
        expected=src if name=='redirect_wrong_live_target' else target
        pages[r1]={'key':key,'locale':locales[0],'state':'redirect','redirect_to':expected,'sitemap':False}
        o[r1]={'status':200,'lang':locales[0],'key':None,'redirect':target,'canonical':{},'alternates':{},'links':[]}
        if name=='redirect_cycle':
            pages[r2]={'key':key,'locale':locales[0],'state':'redirect','redirect_to':r1,'sitemap':False}
            o[r2]={'status':200,'lang':locales[0],'key':None,'redirect':r1,'canonical':{},'alternates':{},'links':[]}
    elif name=='wrong_html_locale':o[src]['lang']=locales[-1]
    elif name=='draft_published':pages[victim]['state']='draft'
    elif name=='prefix_stale':
        selected=[r for r,d in pages.items() if d['locale']==locales[0]]
        from urllib.parse import urlsplit
        for r in selected:
            p=urlsplit(r);move(r,p.scheme+'://'+p.netloc+'/default'+p.path)
    elif name=='key_reassigned':pages[victim]['key']='reassigned-key'
    elif name=='missing_required_alternate':
        c=channels(src)[0];put(src,c,[p for p in get(src,c) if p[0]!=locales[-1]])
    elif name=='missing_required_sitemap':s.pop(src)
    elif name=='missing_route':o.pop(victim)
    else:raise ValueError(name)
    return m,o,s
