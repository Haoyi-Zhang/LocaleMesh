"""Coalesce equal field read footprints per fact without dropping observations.

Unlike FacetedIncremental, reverse edges are fact/footprint/owner groups, not one
Python object per owner/field. Footprints are immutable and reference counted.
Invalidation is exactly the disjunction of the old projected reads. No digest-based equality,
probabilistic equality, predicate specialization, or outcome oracle are used.
"""
from __future__ import annotations
from collections.abc import Mapping
from copy import deepcopy
from time import perf_counter_ns
from .faceted import MISSING, project
from .incremental import check_owner
from .model import owners


class FootprintMapping(Mapping):
    __slots__ = ('_data', '_path', '_trace')

    def __init__(self, data, path, trace):
        self._data, self._path, self._trace = data, path, trace

    def __getitem__(self, key):
        path = self._path + (key,)
        self._trace.add((path, 'value'))
        value = self._data[key]
        return FootprintMapping(value, path, self._trace) if isinstance(value, dict) else value

    def __contains__(self, key):
        self._trace.add((self._path + (key,), 'present'))
        return key in self._data

    def __iter__(self):
        self._trace.add((self._path, 'keys'))
        return iter(self._data)

    def __len__(self):
        self._trace.add((self._path, 'keys'))
        return len(self._data)


class CoalescedIncremental:
    """Exact old-footprint invalidation for the existing read-only predicate.

    ``edge_count`` counts owner/fact groups; ``projection_edges`` counts the
    expanded logical owner/projection edges. Pools contain only live footprints.
    Lower-level calls require normalized facts; use ReleaseSession at boundaries.
    """
    def __init__(self, facts):
        self._facts = deepcopy(facts)
        self.reads = {}                 # owner -> {fact: canonical footprint}
        self.reverse = {}               # fact -> {footprint: owner set}
        self._pool = {}                 # footprint -> [canonical object, references]
        self.cache = {}
        self.all_issues = set()
        self.edge_count = 0
        self.projection_edges = 0
        self.reverse_groups = 0
        self.last = {}
        for owner in sorted(owners(self._facts)):
            self._refresh(owner)

    @property
    def facts(self):
        return deepcopy(self._facts)

    def _intern(self, values):
        footprint = frozenset(values)
        entry = self._pool.get(footprint)
        if entry is None:
            entry = [footprint, 0]
            self._pool[footprint] = entry
        entry[1] += 1
        return entry[0]

    def _forget(self, owner):
        self.all_issues.difference_update(self.cache.pop(owner, ()))
        previous = self.reads.pop(owner, {})
        self.edge_count -= len(previous)
        for fact, footprint in previous.items():
            self.projection_edges -= len(footprint)
            groups = self.reverse[fact]
            readers = groups[footprint]
            readers.remove(owner)
            if not readers:
                del groups[footprint]
                self.reverse_groups -= 1
                if not groups:
                    del self.reverse[fact]
            entry = self._pool[footprint]
            entry[1] -= 1
            if not entry[1]:
                del self._pool[footprint]

    def _refresh(self, owner):
        # Evaluate before discarding this owner's previous footprint.
        trace = {}
        def read(key, default=None):
            observations = trace.setdefault(key, set())
            observations.add(((), 'value'))
            value = self._facts.get(key, MISSING)
            if value is MISSING:
                return default
            if isinstance(value, dict):
                return FootprintMapping(value, (), observations)
            return value
        issues = check_owner(owner, read)
        self._forget(owner)
        footprints = {}
        for fact, observations in trace.items():
            footprint = self._intern(observations)
            footprints[fact] = footprint
            groups = self.reverse.setdefault(fact, {})
            if footprint not in groups:
                groups[footprint] = set()
                self.reverse_groups += 1
            groups[footprint].add(owner)
            self.projection_edges += len(footprint)
        self.edge_count += len(footprints)
        self.reads[owner] = footprints
        self.cache[owner] = issues
        self.all_issues.update(issues)

    def expanded_reads(self, owner):
        """For tests only: recover the exact field-level trace representation."""
        return {(fact, path, mode) for fact, fp in self.reads[owner].items()
                for path, mode in fp}

    def update(self, changes):
        start = perf_counter_ns()
        changed = {k: deepcopy(v) for k, v in changes.items()
                   if self._facts.get(k) != v}
        affected = {k[1] for k in changed if k[0] in ('m', 'o', 's')}
        compared = groups_checked = changed_groups = 0
        for fact, new in changed.items():
            old = self._facts.get(fact, MISSING)
            future = MISSING if new is None else new
            # Equal projections used by several footprints are compared once.
            memo = {}
            for footprint, readers in self.reverse.get(fact, {}).items():
                groups_checked += 1
                differs = False
                for observation in footprint:
                    if observation not in memo:
                        path, mode = observation
                        memo[observation] = project(old, path, mode) != project(future, path, mode)
                        compared += 1
                    if memo[observation]:
                        differs = True
                        break
                if differs:
                    affected.update(readers)
                    changed_groups += 1
        invalidated_at = perf_counter_ns()
        for key, value in changed.items():
            if value is None:
                self._facts.pop(key, None)
            else:
                self._facts[key] = value
        for owner in sorted(affected):
            if any((kind, owner) in self._facts for kind in ('m', 'o', 's')):
                self._refresh(owner)
            else:
                self._forget(owner)
        self.last = {
            'changed_facts': len(changed), 'invalidated_owners': len(affected),
            'projected_reads_compared': compared, 'footprints_compared': groups_checked,
            'changed_footprints': changed_groups, 'invalidation_ns': invalidated_at-start,
            'update_ns': perf_counter_ns()-start, 'dependency_edges': self.edge_count,
            'projection_edges': self.projection_edges, 'reverse_groups': self.reverse_groups,
            'interned_footprints': len(self._pool),
        }
        return dict(self.last)

    def issues(self):
        return set(self.all_issues)
