"""Field-projection invalidation for the same owner predicate as Incremental.

The full evaluator remains separately implemented. This engine records what a
read observes: a leaf value, mapping shape, key membership, or missing path. A
canonical-only edit therefore need not invalidate readers of status/redirect.
Old observations of absent paths are retained until after atomic invalidation.
"""
from __future__ import annotations
from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from time import perf_counter_ns
from .model import owners
from .incremental import check_owner

MISSING = object()
MAP = object()
# A dependency is (primary fact key, nested mapping path, observation mode).

def project(record, path, mode):
    current = record
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return MISSING
        current = current[key]
    if mode == 'keys':
        return tuple(current) if isinstance(current, dict) else MISSING
    if mode == 'present':
        return current is not MISSING
    return MAP if isinstance(current, dict) else current


class ReadMapping(Mapping):
    """No raw mutable dictionary escapes into the owner predicate."""
    def __init__(self, data, fact, path, trace):
        self.data, self.fact, self.path, self.trace = data, fact, path, trace

    def __getitem__(self, key):
        path = self.path + (key,)
        self.trace.add((self.fact, path, 'value'))
        value = self.data[key]  # Missing keys were recorded before KeyError.
        if isinstance(value, dict):
            return ReadMapping(value, self.fact, path, self.trace)
        return value

    def __contains__(self, key):
        self.trace.add((self.fact, self.path + (key,), 'present'))
        return key in self.data

    def __iter__(self):
        self.trace.add((self.fact, self.path, 'keys'))
        return iter(self.data)

    def __len__(self):
        self.trace.add((self.fact, self.path, 'keys'))
        return len(self.data)


class FacetedIncremental:
    def __init__(self, facts):
        self._facts = deepcopy(facts)
        self.reads = {}
        self.reverse = defaultdict(set)
        self.by_fact = defaultdict(set)
        self.cache = {}
        self.all_issues = set()
        self.edge_count = 0
        self.last = {}
        for owner in sorted(owners(self._facts)):
            self._refresh(owner)

    @property
    def facts(self):
        return deepcopy(self._facts)

    def _forget(self, owner):
        self.all_issues.difference_update(self.cache.pop(owner, ()))
        previous = self.reads.pop(owner, ())
        self.edge_count -= len(previous)
        for dep in previous:
            self.reverse[dep].discard(owner)
            if not self.reverse[dep]:
                del self.reverse[dep]
                self.by_fact[dep[0]].discard(dep)
                if not self.by_fact[dep[0]]:
                    del self.by_fact[dep[0]]

    def _refresh(self, owner):
        self._forget(owner)
        trace = set()
        def read(key, default=None):
            trace.add((key, (), 'value'))
            value = self._facts.get(key, MISSING)
            if value is MISSING: return default
            if isinstance(value, dict): return ReadMapping(value, key, (), trace)
            return value
        issues = check_owner(owner, read)
        self.reads[owner] = trace
        self.cache[owner] = issues
        self.all_issues.update(issues)
        self.edge_count += len(trace)
        for dep in trace:
            self.reverse[dep].add(owner)
            self.by_fact[dep[0]].add(dep)

    def update(self, changes, *, broken_drop_absent=False):
        start = perf_counter_ns()
        changed = {k: deepcopy(v) for k,v in changes.items() if self._facts.get(k) != v}
        impacted = {k[1] for k in changed if k[0] in ('m','o','s')}
        checked = 0
        changed_projections = 0
        for key, new in changed.items():
            old = self._facts.get(key, MISSING)
            future = MISSING if new is None else new
            # Snapshot the OLD projected reads before installing any changes.
            for dep in self.by_fact.get(key, ()):
                checked += 1
                before = project(old, dep[1], dep[2])
                after = project(future, dep[1], dep[2])
                if before != after:
                    changed_projections += 1
                    if not (broken_drop_absent and before is MISSING):
                        impacted.update(self.reverse[dep])
        invalidated = perf_counter_ns()
        for key, value in changed.items():
            if value is None: self._facts.pop(key, None)
            else: self._facts[key] = value
        for owner in sorted(impacted):
            if any((kind,owner) in self._facts for kind in ('m','o','s')):
                self._refresh(owner)
            else:
                self._forget(owner)
        self.last = {'changed_facts':len(changed),'invalidated_owners':len(impacted),
            'projected_reads_compared':checked,'changed_projections':changed_projections,
            'invalidation_ns':invalidated-start,'update_ns':perf_counter_ns()-start,
            'dependency_edges':self.edge_count}
        return dict(self.last)

    def issues(self):
        return set(self.all_issues)
