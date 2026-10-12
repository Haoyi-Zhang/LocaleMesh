#!/usr/bin/env python3
"""Recheck repaired maintenance on retained cases; never rebuild native tools.

Primary/composition snapshots are reconstructed from their recorded operators.
Secondary candidates are mutated in a private temporary copy of retained clean
emissions. Pandoc and Hugo candidates are reloaded without invoking generators.
"""
from pathlib import Path
import argparse
import copy
import csv
import json
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from localemesh.cases import change
from localemesh.fixtures import make_site, to_facts
from localemesh.full import evaluate
from localemesh.io import load_build
from localemesh.model import delta
from localemesh.sliced import SlicedIncremental
from localemesh.transaction import ReleaseSession
from benchmark_maintenance import RebuildSliced, validate_structure
from evaluate_independent import mutate, CASES, FAMILIES


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify(base, candidate):
    expected = evaluate(candidate)
    patch = delta(base, candidate)
    prior_reads = None
    for cls in (RebuildSliced, SlicedIncremental):
        engine = cls(base)
        engine.update(patch)
        validate_structure(engine, expected)
        if prior_reads is None:
            prior_reads = dict(engine.reads)
        else:
            assert engine.reads == prior_reads, "Maintenance changed the sliced trace"
        session = ReleaseSession(base, engine_class=cls)
        session.apply({k: v for k, v in patch.items() if k[0] != "g"})
        validate_structure(session._engine, expected)
        assert session.facts() == candidate
        engine.update(delta(candidate, base))
        validate_structure(engine, evaluate(base))
    return [i.json() for i in sorted(expected)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "results").resolve()) or output.exists():
        raise ValueError("Use a new artifact/results file")
    counts = {}
    with (ROOT / "results/releases.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        base = to_facts(make_site(row["site"]))
        candidate = to_facts(change(make_site(row["site"]), row["case"]))
        findings = verify(base, candidate)
        assert findings == read_json(ROOT / "results/findings" / (row["site"] + "." + row["case"] + ".json"))["full"]
    counts["primary"] = len(rows)
    print("primary", len(rows), "tuple and trace agreement", flush=True)
    with (ROOT / "results/composition_holdout.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    previous = {}
    for row in rows:
        site = row["site"]
        data = make_site(site)
        for operation, index in json.loads(row["operations"]):
            data = change(data, operation, index)
        candidate = to_facts(data)
        findings = verify(previous.get(site, to_facts(make_site(site))), candidate)
        assert sum(i["category"] == "release" for i in findings) == int(row["release_findings"])
        previous[site] = candidate
    counts["compositions"] = len(rows)
    print("compositions", len(rows), "tuple and trace agreement", flush=True)
    count = 0
    with tempfile.TemporaryDirectory(prefix="maintenance-", dir=ROOT / ".test-tmp") as tmp:
        for family, (_, _, channel) in FAMILIES.items():
            retained = ROOT / "independent_builds" / family
            base = load_build(retained / "manifest.json", retained)
            for name, label, rule in CASES:
                build = Path(tmp) / (family + "-" + name)
                shutil.copytree(retained, build)
                manifest = read_json(retained / "manifest.json")
                mutate(name, manifest, build, channel)
                path = build / "manifest.json"
                path.write_text(json.dumps(manifest), encoding="utf-8")
                findings = verify(base, load_build(path, build))
                if rule:
                    assert rule in {i["code"] for i in findings}
                assert any(i["category"] == "release" for i in findings) == (label == "defect")
                count += 1
    counts["secondary"] = count
    print("secondary", count, "tuple and trace agreement", flush=True)
    pandoc = read_json(ROOT / "results/pandoc-run.json")
    clean = ROOT / "pandoc_integration/builds/clean"
    base = load_build(clean / "manifest.json", clean / "build")
    for row in pandoc["rows"]:
        case = ROOT / "pandoc_integration/builds" / row["case"]
        assert verify(base, load_build(case / "manifest.json", case / "build")) == row["findings"]
    counts["pandoc"] = len(pandoc["rows"])
    print("retained Pandoc", len(pandoc["rows"]), "tuple and trace agreement", flush=True)
    assert sum(counts.values()) == 321
    native = ROOT / "results/native-hugo-12"
    record = read_json(native / "results.json")
    base = load_build(native / "sources/clean/manifest.json", native / "builds/initial-clean")
    cases = {case["case"]: case["findings"] for case in record["cases"]}
    for command in record["commands"]:
        candidate = load_build(native / "sources" / command["case"] / "manifest.json", native / "builds" / command["tag"])
        assert verify(base, candidate) == cases.get(command["case"], [])
    result = {"historical_populations": counts, "total": sum(counts.values()),
              "native_retained_candidates": len(record["commands"]), "native_builds_executed": 0,
              "all_issue_sets_equal": True, "all_repaired_traces_equal_pre_repair": True,
              "all_reference_counts_consistent": True,
              "scope": "Replay after maintenance repair, not new independent releases, a fresh holdout, native builds or scientific closure. Primary/composition inputs reconstructed from recorded operators; full tuple matching where retained tuples exist. Composition checks also match stored release-finding counts, not an independent complete tuple oracle. Secondary inputs remutated from retained clean emissions."}
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
