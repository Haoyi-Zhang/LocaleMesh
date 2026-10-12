#!/usr/bin/env python3
"""Measure differential slice maintenance against the previous refresh routine.

No generator, network, source adaptation, publication or dependency installation.
Native inputs replay retained Hugo outputs; synthetic inputs remain laboratory
graphs. Both caches reevaluate the same rules and use the same old-read index.
"""
from pathlib import Path
import argparse
import copy
import gc
import hashlib
import inspect
import json
import os
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from localemesh.coalesced import FootprintMapping
from localemesh.contract_join import evaluate_html_contract
from localemesh.faceted import MISSING
from localemesh.fixtures import make_site, to_facts
from localemesh.cases import change
from localemesh.full import evaluate
from localemesh.io import load_build
from localemesh.model import delta
from localemesh.sliced import SlicedIncremental, check_shard
from localemesh.transaction import ReleaseSession


class RebuildSliced(SlicedIncremental):
    """Exact pre-repair _refresh_reader; all other mechanisms are shared.

    This is an internal maintenance baseline, not an independent checker. The
    previous engine removed and reinserted all memberships and issue references.
    """
    def _refresh_reader(self, reader):
        owner, shard = reader
        trace = {}

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
        footprints = []
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


def export(issues):
    return json.dumps([i.json() for i in sorted(issues)], sort_keys=True)


def timed(fn):
    start = time.perf_counter_ns()
    result = fn()
    return result, time.perf_counter_ns() - start


def spread(values):
    q = statistics.quantiles(values, n=4, method="inclusive")
    return {"median": statistics.median(values), "q1": q[0], "q3": q[2],
            "min": min(values), "max": max(values)}


def synthetic(routes, kind):
    data = make_site("A1", routes // 2)
    hub = next(iter(data[1]))
    if kind.startswith("hub_"):
        for observation in data[1].values():
            observation["links"] = [hub]
    clean = to_facts(data)
    if kind in {"local_canonical", "hub_canonical"}:
        target = to_facts(change(data, "wrong_canonical"))
    elif kind == "deleted_page":
        target = to_facts(change(data, "removed_stale"))
    else:
        target = copy.deepcopy(clean)
        if kind == "unused_alias":
            target[("cfg",)]["aliases"][hub + "unused-alias/"] = hub
        elif kind == "global_link_policy":
            target[("cfg",)]["check_links"] = False
        elif kind == "hub_status":
            target[("o", hub)]["status"] = 404
        else:
            raise ValueError(kind)
    return clean, target


def validate_structure(engine, expected):
    from collections import Counter
    assert engine.issues() == expected
    assert engine.edge_count == sum(map(len, engine.reads.values()))
    assert engine.projection_edges == sum(len(fp) for v in engine.reads.values() for _, fp in v)
    assert engine.reverse_groups == sum(map(len, engine.reverse.values()))
    refs = Counter()
    memberships = 0
    for reader, records in engine.reads.items():
        for fact, fp in records:
            assert reader in engine.reverse[fact][fp]
            assert fp is engine._pool[fp][0]
            refs[fp] += 1
    for fact, groups in engine.reverse.items():
        for fp, readers in groups.items():
            assert readers
            memberships += len(readers)
    assert memberships == engine.edge_count
    assert dict(refs) == {fp: value[1] for fp, value in engine._pool.items()}
    assert engine.issue_counts == Counter(i for issues in engine.cache.values() for i in issues)


def run_pair(clean, target, repeats, index, native=False):
    raw = [delta(clean, target), delta(target, clean)]
    primary = [{k: v for k, v in patch.items() if k[0] != "g"} for patch in raw]
    goals = [target, clean]
    expected = [evaluate(goal) for goal in goals]
    reference = [export(issues) for issues in expected]
    rows = [{"repeat": r, "direction": "forward" if r % 2 == 0 else "reverse"}
            for r in range(repeats)]
    names = ["full", "rebuild", "differential"] + (["join"] if native else [])
    shift = index % len(names)
    order = names[shift:] + names[:shift]
    cold = {}
    # Block-rotated, one cache at a time; not independent-process or site samples.
    for name in order:
        if name in {"rebuild", "differential"}:
            cls = RebuildSliced if name == "rebuild" else SlicedIncremental

            def initialize():
                session = ReleaseSession(clean, engine_class=cls)
                return session, export(session.issues())

            (session, initial), cold[name] = timed(initialize)
            assert initial == reference[1]
            for direction in (0, 1):
                session.apply(primary[direction])
                validate_structure(session._engine, expected[direction])
            for r, row in enumerate(rows):
                direction = r % 2

                def update():
                    stats = session.apply(primary[direction])
                    return export(session.issues()), stats

                (actual, stats), elapsed = timed(update)
                assert actual == reference[direction]
                row[name + "_ns"] = elapsed
                row[name + "_stats"] = stats
            validate_structure(session._engine, expected[1])
            del session
            gc.collect()
        else:
            fn = evaluate if name == "full" else evaluate_html_contract
            _, cold[name] = timed(lambda: export(fn(clean)))
            for r, row in enumerate(rows):
                direction = r % 2
                actual, row[name + "_ns"] = timed(lambda: export(fn(goals[direction])))
                assert actual == reference[direction]
    for r, row in enumerate(rows):
        direction = r % 2
        computed, row["difference_ns"] = timed(lambda: delta(goals[1 - direction], goals[direction]))
        assert computed == raw[direction]
        row["series_order"] = order
        row["exact_agreement"] = True
    summaries = {name + "_ms": spread([row[name + "_ns"] / 1e6 for row in rows]) for name in names}
    summaries["difference_ms"] = spread([row["difference_ns"] / 1e6 for row in rows])
    for name in ("rebuild", "differential"):
        summaries["difference_plus_" + name + "_ms"] = spread([
            (row["difference_ns"] + row[name + "_ns"]) / 1e6 for row in rows])
    summaries["paired_rebuild_over_differential"] = spread([
        row["rebuild_ns"] / row["differential_ns"] for row in rows])
    finite = {name: (cold[name] + sum(row[name + "_ns"] +
              (row["difference_ns"] if name in {"rebuild", "differential"} else 0) for row in rows)) / 1e6
              for name in names}
    return {"rows": rows, "summaries": summaries, "cold_check_and_export_ns": cold,
            "cold_plus_updates_ms": finite, "findings": [[i.json() for i in sorted(s)] for s in expected]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--routes", type=int, default=10000)
    p.add_argument("--repeats", type=int, default=12)
    p.add_argument("--native-run", type=Path, default=ROOT / "results/native-hugo-12")
    args = p.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "results").resolve()) or output.exists():
        raise ValueError("Use a new file under this artifact's results directory")
    if args.routes < 4 or args.routes % 2 or args.repeats < 2 or args.repeats % 2:
        raise ValueError("Even routes >= 4 and even repetitions >= 2 required")
    native = args.native_run.resolve()
    if not native.is_relative_to(ROOT.resolve()):
        raise ValueError("Native replay inputs must stay inside this artifact")
    source_record = json.loads((native / "results.json").read_text(encoding="utf-8"))
    result = {"python": sys.version, "platform": platform.platform(),
              "hash_seed": os.environ.get("PYTHONHASHSEED"), "repeats": args.repeats,
              "native_run": str(native.relative_to(ROOT)), "native_builds_executed": 0,
              "source_repository": source_record["source_repository"],
              "source_commit": source_record["source_commit"],
              "baseline_refresh": inspect.getsource(RebuildSliced._refresh_reader),
              "differential_refresh": inspect.getsource(SlicedIncremental._refresh_reader),
              "synthetic": {}, "native_replay": {},
              "cost_boundary": "Validated checking plus deterministic JSON export; cached paths also report complete differencing and cold setup. Generation and extraction are NOT timed: native candidates are reloaded before the check series. No historic build cost is relabeled as a new workflow measurement. Normalization/owned copies/derived buckets in ReleaseSession are charged. Fixture construction, input loading, full oracle, assertions, two-way warm-up, GC between blocks and report writing are excluded. One process, block-rotated series, one cache at a time; repetitions are not independent sites or machine confidence intervals."}
    result["source_files_sha256"] = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for path in ("localemesh/sliced.py", "localemesh/transaction.py", "localemesh/full.py", "scripts/benchmark_maintenance.py")}
    started = time.perf_counter()
    kinds = ("local_canonical", "deleted_page", "unused_alias", "global_link_policy", "hub_canonical", "hub_status")
    for index, kind in enumerate(kinds):
        clean, target = synthetic(args.routes, kind)
        result["synthetic"][kind] = run_pair(clean, target, args.repeats, index)
        print(args.routes, kind, "exact agreement", flush=True)
        del clean, target
        gc.collect()
    clean = load_build(native / "sources/clean/manifest.json", native / "builds/initial-clean")
    assert evaluate(clean) == evaluate_html_contract(clean) == set()
    for index, case in enumerate(source_record["cases"]):
        kind = case["case"]
        target = load_build(native / "sources" / kind / "manifest.json", native / "builds" / ("warm-" + kind))
        assert [i.json() for i in sorted(evaluate(target))] == case["findings"]
        result["native_replay"][kind] = run_pair(clean, target, args.repeats, index, native=True)
        print("retained native", kind, "exact agreement", flush=True)
    result["synthetic_routes"] = args.routes
    result["measured_updates_per_path"] = len(kinds) * args.repeats + len(source_record["cases"]) * args.repeats
    result["wall_s"] = time.perf_counter() - started
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print("Saved", output, flush=True)


if __name__ == "__main__":
    main()
