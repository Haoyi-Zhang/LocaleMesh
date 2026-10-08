#!/usr/bin/env python3
"""Isolated worker for one obligation-slicing benchmark change kind."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import argparse
import gc
import json
import time

from localemesh.coalesced import CoalescedIncremental
from localemesh.full import evaluate
from localemesh.model import delta
from localemesh.sliced import SlicedIncremental
from localemesh.transaction import ReleaseSession
from benchmark_sliced import _pair, _goals


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--routes", type=int, required=True)
    parser.add_argument("--repeats", type=int, required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--kind-index", type=int, required=True)
    args = parser.parse_args()

    old, new, hub = _pair(args.routes, args.kind)
    sequence, forward, reverse = _goals(old, new, args.repeats)
    rows = [{
        "routes": args.routes,
        "kind": args.kind,
        "hub": hub,
        "repeat": repeat,
        "direction": direction,
    } for repeat, (_, _, direction) in enumerate(sequence)]
    expected = [evaluate(goal) for goal, _, _ in sequence]

    def full_series():
        current = old
        for repeat, (goal, patch, _) in enumerate(sequence):
            started = time.perf_counter_ns()
            computed = delta(current, goal)
            rows[repeat]["snapshot_diff_ns"] = time.perf_counter_ns() - started
            assert computed == patch
            started = time.perf_counter_ns()
            got = evaluate(goal)
            rows[repeat]["full_ns"] = time.perf_counter_ns() - started
            assert got == expected[repeat]
            rows[repeat]["issues"] = len(got)
            current = goal

    def core_series(name, cls):
        engine = cls(old)
        for goal, patch in ((new, forward), (old, reverse)):
            engine.update(patch)
            assert engine.issues() == evaluate(goal)
        for repeat, (goal, patch, _) in enumerate(sequence):
            started = time.perf_counter_ns()
            stats = engine.update(patch)
            got = engine.issues()
            rows[repeat][name + "_ns"] = time.perf_counter_ns() - started
            assert got == expected[repeat]
            rows[repeat][name + "_issues"] = len(got)
            if name == "coalesced":
                rows[repeat].update({
                    "coalesced_owners": stats["invalidated_owners"],
                    "coalesced_readers": stats["invalidated_owners"],
                    "coalesced_comparisons": stats["projected_reads_compared"],
                    "coalesced_groups_checked": stats["footprints_compared"],
                    "coalesced_edges": engine.edge_count,
                    "coalesced_projection_edges": engine.projection_edges,
                    "coalesced_cached_readers": len(engine.reads),
                })
            else:
                rows[repeat].update({
                    "sliced_owners": stats["invalidated_owners"],
                    "sliced_readers": stats["invalidated_readers"],
                    "sliced_comparisons": stats["projected_reads_compared"],
                    "sliced_groups_checked": stats["footprints_compared"],
                    "sliced_edges": engine.edge_count,
                    "sliced_projection_edges": engine.projection_edges,
                    "sliced_cached_readers": len(engine.reads),
                })
        del engine
        gc.collect()

    def safe_series(name, cls):
        session = ReleaseSession(old, engine_class=cls)
        for goal, patch in ((new, forward), (old, reverse)):
            session.apply({key: value for key, value in patch.items() if key[0] != "g"})
            assert session.issues() == evaluate(goal)
        for repeat, (goal, patch, _) in enumerate(sequence):
            primary = {key: value for key, value in patch.items() if key[0] != "g"}
            started = time.perf_counter_ns()
            session.apply(primary)
            got = session.issues()
            rows[repeat]["safe_" + name + "_ns"] = time.perf_counter_ns() - started
            assert got == expected[repeat]
        del session
        gc.collect()

    series = [
        ("full", full_series),
        ("coalesced", lambda: core_series("coalesced", CoalescedIncremental)),
        ("sliced", lambda: core_series("sliced", SlicedIncremental)),
        ("safe_coalesced", lambda: safe_series("coalesced", CoalescedIncremental)),
        ("safe_sliced", lambda: safe_series("sliced", SlicedIncremental)),
    ]
    shift = args.kind_index % len(series)
    series = series[shift:] + series[:shift]
    order = [name for name, _ in series]
    for _, runner in series:
        runner()
    for row in rows:
        row["agreement"] = True
        row["series_order"] = order
        required = {
            "full_ns", "snapshot_diff_ns", "coalesced_ns", "sliced_ns",
            "safe_coalesced_ns", "safe_sliced_ns", "coalesced_owners",
            "sliced_owners", "sliced_readers",
        }
        assert required <= row.keys()
    print(json.dumps({"rows": rows, "series_order": order}))


if __name__ == "__main__":
    main()
