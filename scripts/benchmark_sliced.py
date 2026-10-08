#!/usr/bin/env python3
"""Paired obligation-slicing experiment over exact field footprints.

The coalesced and sliced engines observe the same normalized snapshots and emit the
same issue set as the independent full evaluator. Slicing changes only the cached
computation unit: a route-wide predicate versus independent release obligations.
To bound peak memory at 10,000 routes, timing series run in rotated blocks and hold
one cache at a time. Every series alternates forward/reverse updates after a two-way
warmup; rows remain paired by change, direction and repetition.
"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import argparse
import copy
import gc
import json
import platform
import resource
import subprocess
import time
import sys as _sys

from localemesh.cases import change
from localemesh.coalesced import CoalescedIncremental
from localemesh.fixtures import make_site, to_facts
from localemesh.full import evaluate
from localemesh.model import delta
from localemesh.sliced import SlicedIncremental
from localemesh.transaction import ReleaseSession

KINDS = [
    "local_canonical",
    "deleted_page",
    "unused_alias",
    "global_link_policy",
    "hub_canonical",
    "hub_status",
]


def _deep_size(root):
    """Count retained Python objects reachable from selected cache roots once."""
    seen = set()
    stack = [root]
    total = 0
    objects = 0
    while stack:
        value = stack.pop()
        identity = id(value)
        if identity in seen:
            continue
        seen.add(identity)
        objects += 1
        total += _sys.getsizeof(value)
        if isinstance(value, dict):
            stack.extend(value.keys())
            stack.extend(value.values())
        elif isinstance(value, (list, tuple, set, frozenset)):
            stack.extend(value)
        elif type(value).__module__.startswith("localemesh") and hasattr(value, "__dict__"):
            stack.append(vars(value))
    return total, objects


def _memory(clean, name, cls):
    gc.collect()
    started = time.perf_counter_ns()
    engine = cls(clean)
    init_ns = time.perf_counter_ns() - started
    roots = {key: value for key, value in vars(engine).items() if key != "last"}
    retained, object_count = _deep_size(roots)
    result = {
        "retained_python_bytes": retained,
        "retained_python_objects": object_count,
        "dependency_edges": engine.edge_count,
        "logical_projection_edges": getattr(engine, "projection_edges", None),
        "reverse_groups": getattr(engine, "reverse_groups", None),
        "interned_footprints": len(engine._pool),
        "cached_readers": len(engine.reads),
        "init_ns": init_ns,
        "includes_owned_fact_copy": True,
        "measurement": "recursive sys.getsizeof over cache-owned roots with identity deduplication",
    }
    del engine
    gc.collect()
    return name, result


def _pair(routes: int, kind: str):
    data = make_site("A1", routes // 2)
    hub = next(iter(data[1]))
    if kind.startswith("hub_"):
        for observation in data[1].values():
            observation["links"] = [hub]
    old = to_facts(data)
    if kind in {"local_canonical", "hub_canonical"}:
        new = to_facts(change(data, "wrong_canonical"))
    elif kind == "deleted_page":
        new = to_facts(change(data, "removed_stale"))
    else:
        new = copy.deepcopy(old)
        if kind == "unused_alias":
            new[("cfg",)]["aliases"][hub + "unused-alias/"] = hub
        elif kind == "global_link_policy":
            new[("cfg",)]["check_links"] = False
        elif kind == "hub_status":
            new[("o", hub)]["status"] = 404
        else:
            raise ValueError(kind)
    return old, new, hub


def _goals(old, new, repeats):
    forward, reverse = delta(old, new), delta(new, old)
    return [
        (new, forward, "forward") if repeat % 2 == 0 else (old, reverse, "reverse")
        for repeat in range(repeats)
    ], forward, reverse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--routes", type=int, required=True)
    parser.add_argument("--repeats", type=int, default=12)
    parser.add_argument("--memory-engine", choices=("coalesced", "sliced"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.routes % 2 or args.routes < 4 or args.repeats < 2:
        raise ValueError("Even routes >= 4 and repeats >= 2 required")
    if args.memory_engine:
        clean = to_facts(make_site("A1", args.routes // 2))
        cls = CoalescedIncremental if args.memory_engine == "coalesced" else SlicedIncremental
        _, result = _memory(clean, args.memory_engine, cls)
        print(json.dumps(result))
        return

    started = time.perf_counter()
    memory = {}
    for name in ("coalesced", "sliced"):
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--routes", str(args.routes),
             "--repeats", "2", "--memory-engine", name],
            capture_output=True, text=True, check=True, cwd=ROOT,
        )
        memory[name] = json.loads(completed.stdout)

    rows = []
    orders = {}
    worker = Path(__file__).with_name("benchmark_sliced_kind.py")
    for kind_index, kind in enumerate(KINDS):
        completed = subprocess.run(
            [sys.executable, str(worker), "--routes", str(args.routes),
             "--repeats", str(args.repeats), "--kind", kind,
             "--kind-index", str(kind_index)],
            capture_output=True, text=True, check=True, cwd=ROOT,
        )
        payload = json.loads(completed.stdout)
        rows.extend(payload["rows"])
        orders[kind] = payload["series_order"]
        print(args.routes, kind, "completed", round(time.perf_counter() - started, 2), "s", flush=True)

    result = {
        "routes": args.routes,
        "repeats": args.repeats,
        "python": platform.python_version(),
        "rows": rows,
        "memory": memory,
        "series_orders": orders,
        "wall_s": time.perf_counter() - started,
        "maxrss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "scope": (
            "Synthetic routes. Coalesced and sliced engines use exact projected reads and "
            "the same release obligations; sliced evaluation changes the cached computation "
            "unit. Complete-snapshot difference is charged separately. Page parsing and "
            "builder time are excluded."
        ),
        "timing": (
            "Each change kind runs in an isolated process. Within a kind, each timing series "
            "uses a two-direction warmup and alternating paired updates; series order rotates "
            "by kind and only one cache is retained at a time. Issue sets are materialized on "
            "every path. Repeats are process observations, not independent sites."
        ),
    }
    (ROOT / "results" / f"sliced-{args.routes}.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
