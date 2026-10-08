"""Validated release transactions with automatically maintained identity buckets.

The caller supplies a COMPLETE change set of primary records (cfg, m, o, s), not
filesystem events. No completeness claim is made about a caller's file watcher.
All normalization/validation happens before a mutation reaches the evaluator.
"""
from __future__ import annotations
from copy import deepcopy
from time import perf_counter_ns
from .incremental import Incremental
from .model import FactMap, FactKey, snapshot, url
from .schema import normalize_config, normalize_spec, normalize_observation, normalize_pairs


class ReleaseSession:
    def __init__(self, facts: FactMap, *, engine_class=Incremental):
        primary = self._normalize({k: v for k, v in facts.items() if k[0] != 'g'})
        if ('cfg',) not in primary or primary[('cfg',)] is None:
            raise ValueError('A release session requires a config fact')
        if any(v is None for v in primary.values()):
            raise ValueError('Initial facts cannot be deleted records')
        rebuilt = snapshot({'config': primary[('cfg',)],
                            'pages': {k[1]: v for k, v in primary.items() if k[0] == 'm'}},
                           {k[1]: v for k, v in primary.items() if k[0] == 'o'},
                           {k[1]: v for k, v in primary.items() if k[0] == 's'})
        self._engine = engine_class(rebuilt)
        self.revision = 0

    @staticmethod
    def _normalize(changes):
        if not isinstance(changes, dict): raise ValueError('Transaction must be a fact mapping')
        result = {}
        for k, v in changes.items():
            if not isinstance(k, tuple) or not k:
                raise ValueError('Malformed fact key')
            if k == ('cfg',):
                if v is None: raise ValueError('Configuration cannot be removed')
                key, val = k, normalize_config(v)
            elif len(k) == 2 and k[0] in ('m', 'o', 's'):
                key = (k[0], url(k[1]))
                fn = {'m': normalize_spec, 'o': normalize_observation, 's': normalize_pairs}[k[0]]
                val = None if v is None else fn(v)
            else:
                raise ValueError('Only primary cfg/m/o/s facts may be changed; g is derived')
            if key in result: raise ValueError('Normalized duplicate fact in transaction')
            result[key] = val
        return result

    def apply(self, changes: dict[FactKey, object]):
        start = perf_counter_ns()
        prepared = self._normalize(changes)  # Any input error leaves state unchanged.
        groups = {}
        # A move, removal, or reassignment reads both old and new identity buckets.
        # No whole-site scan is needed to maintain these derived facts.
        for k, new in list(prepared.items()):
            if k[0] != 'm': continue
            old = self._engine._facts.get(k)
            for spec, add in ((old, False), (new, True)):
                if spec is None or spec.get('state', 'published') != 'published': continue
                group = ('g', spec['key'], spec['locale'].lower())
                if group not in groups:
                    groups[group] = set(self._engine._facts.get(group, ()))
                if add: groups[group].add(k[1])
                else: groups[group].discard(k[1])
        for key, members in groups.items():
            prepared[key] = tuple(sorted(members)) if members else None
        prepared_at = perf_counter_ns()
        stats = dict(self._engine.update(prepared))
        self.revision += 1
        stats.update(preparation_ns=prepared_at - start,
                     transaction_ns=perf_counter_ns() - start,
                     derived_groups=len(groups), revision=self.revision)
        return stats

    def issues(self):
        return self._engine.issues()

    def facts(self):
        return self._engine.facts
