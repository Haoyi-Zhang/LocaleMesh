"""Obligation-sliced exact incremental evaluation.

The owner predicate is partitioned into independently cached release obligations.
Each obligation records the exact mapping projections that it observes.  A change
therefore re-evaluates only affected obligation slices rather than every rule for
an affected owner.  Footprints are coalesced exactly; no hashes or probabilistic
equality are used.

This module intentionally does not call :mod:`localemesh.incremental`'s monolithic
``check_owner``.  Equality is tested against the separately implemented full scan.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from time import perf_counter_ns
from urllib.parse import urlsplit

from .coalesced import FootprintMapping
from .faceted import MISSING, project
from .model import FactMap, Issue, owners

LIVE_SHARDS = ("route", "canonical", "discovery", "agreement", "links")
Reader = tuple[str, str]


def _report(found: set[Issue], owner: str, code: str, ch: str = "",
            extra: object = "", ambiguity: bool = False) -> None:
    found.add(Issue("ambiguity" if ambiguity else "release", code, owner, ch, str(extra)))


def _terminal(read, cfg, start: str) -> tuple[str, str]:
    origins = cfg["origins"]
    aliases = cfg.get("aliases", {})
    current = start
    seen: set[str] = set()
    while current not in seen:
        seen.add(current)
        p = urlsplit(current)
        if p.scheme + "://" + p.netloc not in origins:
            return current, "external"
        alias = aliases.get(current)
        if alias is not None:
            current = alias
            continue
        observation = read(("o", current))
        if observation is None:
            return current, "missing"
        redirect = observation.get("redirect")
        if redirect:
            current = redirect
            continue
        status = observation.get("status", 200)
        return (current, "ok") if 200 <= status < 300 else (current, "unavailable")
    return current, "cycle"


def _resolve(read, cfg, found: set[Issue], owner: str, target: str,
             code: str, channel: str) -> tuple[str, str]:
    terminal, status = _terminal(read, cfg, target)
    if status == "external":
        _report(found, owner, "UNMOUNTED_TARGET", channel, target, True)
    elif status != "ok":
        _report(found, owner, code, channel, target)
    return terminal, status


def _alternatives(read, route: str, channel: str):
    if channel == "sitemap":
        return read(("s", route), [])
    return read(("o", route), {}).get("alternates", {}).get(channel, [])


def _context(read, owner: str):
    """Read live records for an obligation whose gate has already passed.

    The cache reconciles obligation families whenever the gate's dependencies
    change. Individual obligations therefore retain only the fields that can
    change their own result, rather than re-reading every early-exit condition.
    """
    spec = read(("m", owner))
    actual = read(("o", owner))
    if spec is None or actual is None:
        return None
    return spec, actual


def check_shard(owner: str, shard: str, read) -> set[Issue]:
    """Evaluate one semantic obligation slice for one route owner."""
    found: set[Issue] = set()

    if shard == "gate":
        # Preserve the monolithic evaluator's ordering and early-return boundary.
        actual = read(("o", owner))
        for code, detail in (actual or {}).get("diagnostics", []):
            _report(found, owner, code, "ingestion", detail, True)
        sitemap = read(("s", owner))
        cfg = read(("cfg",))
        if sitemap is not None:
            _resolve(read, cfg, found, owner, owner, "SITEMAP_TARGET", "sitemap")
        spec = read(("m", owner))
        if spec is None:
            if cfg.get("complete_manifest", False):
                _report(found, owner, "UNDECLARED_ROUTE", ambiguity=True)
            return found
        state = spec.get("state", "published")
        if spec.get("ambiguous"):
            _report(found, owner, "DECLARATION_CONFLICT", ambiguity=True)
            return found
        if state == "published":
            peers = read(("g", spec["key"], spec["locale"].lower()), ())
            if len(peers) > 1:
                _report(found, owner, "IDENTITY_COLLISION", extra=spec["key"] + ":" + spec["locale"], ambiguity=True)
                return found
        if state in {"draft", "removed"}:
            if actual is not None:
                _report(found, owner, "UNEXPECTED_PUBLICATION")
            if sitemap is not None:
                _report(found, owner, "SITEMAP_PUBLICATION", "sitemap")
            return found
        if actual is None:
            _report(found, owner, "MISSING_ROUTE")
            return found
        if state == "redirect":
            permitted = spec.get("redirect_allowed")
            if permitted is None:
                permitted = [spec.get("redirect_to")]
            if actual.get("redirect") not in permitted:
                _report(found, owner, "REDIRECT_POLICY")
            _resolve(read, cfg, found, owner, owner, "REDIRECT_TARGET", "redirect")
            if sitemap is not None and not spec.get("sitemap", False):
                _report(found, owner, "SITEMAP_REDIRECT", "sitemap")
            if spec.get("sitemap", False) and sitemap is None:
                _report(found, owner, "SITEMAP_MISSING", "sitemap")
        return found

    context = _context(read, owner)
    if context is None:
        return found
    spec, actual = context

    if shard == "route":
        sitemap = read(("s", owner))
        if actual.get("redirect") or actual.get("status", 200) not in range(200, 300):
            _report(found, owner, "ROUTE_STATE")
        accepted = {v.lower() for v in spec.get("represented_locales", [spec["locale"]])}
        if actual.get("lang", "").lower() not in accepted:
            _report(found, owner, "LANGUAGE", "html")
        if "key" in actual and actual["key"] is not None and actual["key"] != spec["key"]:
            _report(found, owner, "CONTENT_ID", "html")
        if spec.get("sitemap") and sitemap is None:
            _report(found, owner, "SITEMAP_MISSING", "sitemap")
        return found

    if shard == "canonical":
        cfg = read(("cfg",))
        allowed = spec.get("canonical_allowed")
        for channel in spec.get("canonical_channels", ["html"]):
            destinations = actual.get("canonical", {}).get(channel, [])
            required = spec.get("canonical_required", allowed is not None)
            if required and not destinations:
                _report(found, owner, "CANONICAL_MISSING", channel)
            if len(set(destinations)) >= 2:
                _report(found, owner, "CANONICAL_MULTIPLE", channel)
            for destination in destinations:
                if allowed is not None and destination not in allowed:
                    _report(found, owner, "CANONICAL_POLICY", channel, destination)
                _resolve(read, cfg, found, owner, destination, "CANONICAL_TARGET", channel)
        return found

    if shard == "discovery":
        cfg = read(("cfg",))
        for channel, requirements in spec.get("discovery", {}).items():
            data = _alternatives(read, owner, channel)
            grouped: dict[str, set[str]] = defaultdict(set)
            for language, destination in data:
                grouped[language].add(destination)
            for language in requirements.get("required", []):
                if language.lower() not in grouped:
                    _report(found, owner, "DISCOVERY_MISSING", channel, language.lower())
            for language, choices in grouped.items():
                if len(choices) >= 2:
                    _report(found, owner, "DISCOVERY_MULTIPLE", channel, language)
            for language, destination in data:
                final, status = _resolve(read, cfg, found, owner, destination, "DISCOVERY_TARGET", channel)
                if status != "ok":
                    continue
                if language == "x-default":
                    if spec.get("x_default") is not None and spec["x_default"] != destination:
                        _report(found, owner, "XDEFAULT_POLICY", channel, destination)
                    continue
                target = read(("m", final))
                uncertain = target is None or target.get("ambiguous")
                if not uncertain:
                    bucket = read(("g", target["key"], target["locale"].lower()), ())
                    uncertain = len(bucket) > 1
                if uncertain:
                    _report(found, owner, "TARGET_IDENTITY_UNKNOWN", channel, destination, True)
                    continue
                if target["key"] != spec["key"]:
                    _report(found, owner, "DISCOVERY_ID", channel, destination)
                possible = {language.lower()}
                possible.update(v.lower() for v in spec.get("fallbacks", {}).get(language, []))
                if target["locale"].lower() not in possible:
                    _report(found, owner, "DISCOVERY_LOCALE", channel, destination)
                if target.get("state", "published") != "published":
                    _report(found, owner, "DISCOVERY_PUBLICATION", channel, destination)
                if requirements.get("reciprocal") and final != owner:
                    matched = False
                    for back_language, back_url in _alternatives(read, final, channel):
                        if back_language == spec["locale"].lower() and _terminal(read, cfg, back_url) == (owner, "ok"):
                            matched = True
                            break
                    if not matched:
                        _report(found, owner, "RECIPROCITY", channel, destination)
        return found

    if shard == "agreement":
        agreement = spec.get("agree_channels", [])
        for ia in range(len(agreement)):
            for ib in range(ia + 1, len(agreement)):
                left, right = agreement[ia], agreement[ib]
                a, b = _alternatives(read, owner, left), _alternatives(read, owner, right)
                if a and b and set(map(tuple, a)) != set(map(tuple, b)):
                    _report(found, owner, "CHANNEL_CONFLICT", left + ":" + right)
        return found

    if shard == "links":
        cfg = read(("cfg",))
        if cfg.get("check_links", True):
            origins = cfg["origins"]
            for destination in actual.get("links", []):
                p = urlsplit(destination)
                if p.scheme + "://" + p.netloc in origins:
                    _resolve(read, cfg, found, owner, destination, "LINK_TARGET", "html")
        return found

    raise ValueError(f"Unknown obligation shard: {shard}")

class SlicedIncremental:
    """Exact field invalidation with independently cached obligation slices."""

    def __init__(self, facts: FactMap):
        self._facts = deepcopy(facts)
        self.reads: dict[Reader, tuple[tuple[tuple[str, ...], frozenset], ...]] = {}
        self.reverse: dict[tuple[str, ...], dict[frozenset, set[Reader]]] = {}
        self._pool: dict[frozenset, list] = {}
        self.cache: dict[Reader, set[Issue]] = {}
        self.issue_counts: Counter[Issue] = Counter()
        self.edge_count = 0
        self.projection_edges = 0
        self.reverse_groups = 0
        self.last: dict[str, int] = {}
        for owner in sorted(owners(self._facts)):
            self._add_owner(owner)

    @property
    def facts(self):
        return deepcopy(self._facts)

    def _active(self, owner: str) -> bool:
        return any((kind, owner) in self._facts for kind in ("m", "o", "s"))


    def _desired_shards(self, owner: str) -> tuple[str, ...]:
        desired = ["gate"]
        spec = self._facts.get(("m", owner))
        actual = self._facts.get(("o", owner))
        if spec is None or actual is None or spec.get("ambiguous"):
            return tuple(desired)
        if spec.get("state", "published") != "published":
            return tuple(desired)
        bucket = self._facts.get(("g", spec["key"], spec["locale"].lower()), ())
        if len(bucket) > 1:
            return tuple(desired)
        # Keep dormant policy slices as readers of empty control fields. Adding a
        # channel or agreement rule then follows exact old-read invalidation.
        desired.extend(LIVE_SHARDS)
        return tuple(desired)

    def _intern(self, observations) -> frozenset:
        footprint = frozenset(observations)
        entry = self._pool.get(footprint)
        if entry is None:
            entry = [footprint, 0]
            self._pool[footprint] = entry
        entry[1] += 1
        return entry[0]

    def _drop_issues(self, reader: Reader) -> None:
        for issue in self.cache.pop(reader, ()):
            self.issue_counts[issue] -= 1
            if self.issue_counts[issue] <= 0:
                del self.issue_counts[issue]

    def _forget_reader(self, reader: Reader) -> None:
        self._drop_issues(reader)
        previous = self.reads.pop(reader, ())
        self.edge_count -= len(previous)
        for fact, footprint in previous:
            self.projection_edges -= len(footprint)
            groups = self.reverse[fact]
            readers = groups[footprint]
            readers.remove(reader)
            if not readers:
                del groups[footprint]
                self.reverse_groups -= 1
                if not groups:
                    del self.reverse[fact]
            entry = self._pool[footprint]
            entry[1] -= 1
            if not entry[1]:
                del self._pool[footprint]

    def _refresh_reader(self, reader: Reader) -> None:
        owner, shard = reader
        trace: dict[tuple[str, ...], set[tuple[tuple, str]]] = {}

        def read(key, default=None):
            observations = trace.setdefault(key, set())
            observations.add(((), "value"))
            value = self._facts.get(key, MISSING)
            if value is MISSING:
                return default
            if isinstance(value, dict):
                return FootprintMapping(value, (), observations)
            return value

        issues = check_shard(owner, shard, read)
        if reader in self.reads:
            self._forget_reader(reader)
        footprints: list[tuple[tuple[str, ...], frozenset]] = []
        for fact, observations in trace.items():
            footprint = self._intern(observations)
            footprints.append((fact, footprint))
            groups = self.reverse.setdefault(fact, {})
            if footprint not in groups:
                groups[footprint] = set()
                self.reverse_groups += 1
            groups[footprint].add(reader)
            self.projection_edges += len(footprint)
        self.edge_count += len(footprints)
        self.reads[reader] = tuple(footprints)
        if issues:
            self.cache[reader] = issues
            for issue in issues:
                self.issue_counts[issue] += 1

    def _add_owner(self, owner: str) -> None:
        for shard in self._desired_shards(owner):
            self._refresh_reader((owner, shard))

    def _all_reader_ids(self, owner: str) -> set[Reader]:
        return {(owner, shard) for shard in ("gate",) + LIVE_SHARDS if (owner, shard) in self.reads}

    def _reconcile_owner(self, owner: str) -> set[Reader]:
        desired = {(owner, shard) for shard in self._desired_shards(owner)}
        current = self._all_reader_ids(owner)
        for reader in sorted(current - desired):
            self._forget_reader(reader)
        added = desired - current
        for reader in sorted(added):
            self._refresh_reader(reader)
        return added

    def _forget_owner(self, owner: str) -> None:
        for reader in self._all_reader_ids(owner):
            self._forget_reader(reader)

    def expanded_reads(self, reader: Reader):
        return {(fact, path, mode) for fact, footprint in self.reads[reader]
                for path, mode in footprint}

    def update(self, changes):
        start = perf_counter_ns()
        changed = {key: deepcopy(value) for key, value in changes.items()
                   if self._facts.get(key) != value}
        primary_owners = {key[1] for key in changed if key[0] in {"m", "o", "s"}}
        was_active = {owner: self._active(owner) for owner in primary_owners}
        affected: set[Reader] = set()
        compared = groups_checked = changed_groups = 0

        for fact, new in changed.items():
            old = self._facts.get(fact, MISSING)
            future = MISSING if new is None else new
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

        removed = {owner for owner in primary_owners if was_active[owner] and not self._active(owner)}
        added_owners = {owner for owner in primary_owners if not was_active[owner] and self._active(owner)}
        removed_reader_count = sum(len(self._all_reader_ids(owner)) for owner in removed)
        for owner in removed:
            self._forget_owner(owner)
        added_readers: set[Reader] = set()
        # Any changed gate dependency may add or remove the live obligation family:
        # declaration/state, observation presence, or an identity-collision bucket.
        gate_owners = {owner for owner, shard in affected if shard == "gate"}
        reconcile = (primary_owners | gate_owners) - removed - added_owners
        for owner in sorted(reconcile):
            added_readers.update(self._reconcile_owner(owner))
        affected = {reader for reader in affected
                    if reader[0] not in removed and reader[0] not in added_owners
                    and reader not in added_readers and reader in self.reads}
        for reader in sorted(affected):
            if self._active(reader[0]):
                self._refresh_reader(reader)
        for owner in sorted(added_owners):
            before = self._all_reader_ids(owner)
            self._add_owner(owner)
            added_readers.update(self._all_reader_ids(owner) - before)

        invalidated_owners = {reader[0] for reader in affected | added_readers} | removed
        self.last = {
            "changed_facts": len(changed),
            "invalidated_readers": len(affected) + len(added_readers) + removed_reader_count,
            "invalidated_owners": len(invalidated_owners),
            "projected_reads_compared": compared,
            "footprints_compared": groups_checked,
            "changed_footprints": changed_groups,
            "invalidation_ns": invalidated_at - start,
            "update_ns": perf_counter_ns() - start,
            "dependency_edges": self.edge_count,
            "projection_edges": self.projection_edges,
            "reverse_groups": self.reverse_groups,
            "interned_footprints": len(self._pool),
            "cached_readers": len(self.reads),
        }
        return dict(self.last)

    def issues(self) -> set[Issue]:
        return set(self.issue_counts)
