#!/usr/bin/env python3
"""Native Hugo builds, same-information joins and finite whole-workflow cost.

Uses five supplied public Markdown files, not synthetic route multiplication.
Only front matter is adapted for Hugo; baseline Markdown bodies are preserved.
No upstream Liquid, themes, plugins, remote resources or publishing are executed.
The authored variants are controlled cases, not discovered field incidents.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from localemesh.baselines import joint_output
from localemesh.coalesced import CoalescedIncremental
from localemesh.contract_join import evaluate_html_contract
from localemesh.full import evaluate
from localemesh.io import load_build
from localemesh.model import delta
from localemesh.sliced import SlicedIncremental
from localemesh.transaction import ReleaseSession

ORIGIN = "https://native-hugo.localemesh.test"
CASES = [
    ("body_edit", "clean", None),
    ("wrong_canonical", "defect", "CANONICAL_POLICY"),
    ("missing_alternate", "defect", "DISCOVERY_MISSING"),
    ("omitted_source", "defect", "MISSING_ROUTE"),
    ("identity_swap", "defect", "DISCOVERY_ID"),
    ("partial_translation", "clean", None),
    ("canonical_exception", "clean", None),
]


def put_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def export(issues):
    return json.dumps([i.json() for i in sorted(issues)], sort_keys=True)


def timed(fn):
    started = time.perf_counter_ns()
    result = fn()
    return result, time.perf_counter_ns() - started


def source_body(raw):
    lines = raw.splitlines(keepends=True)
    if not lines or lines[0].strip() != b"---":
        raise ValueError("Expected the supplied YAML-front-matter sources")
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == b"---")
    return b"".join(lines[end + 1:])


def prepare(output):
    source_root = ROOT / "pandoc_integration"
    index = json.loads((source_root / "source-index.json").read_text(encoding="utf-8"))
    records = index["records"]
    pages = {}
    source_checks = []
    for record in records:
        source = source_root / "source" / Path(record["path"]).name
        raw = source.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if blob != record["sha"]:
            raise ValueError(f"Pinned source mismatch: {source.name}")
        body = source_body(raw)
        route = ORIGIN + "/" + ("" if record["locale"] == "en" else record["locale"] + "/") + record["permalink"]
        pages[route] = dict(record, body=body, translation_key=record["key"])
        source_checks.append({"path": str(source.relative_to(ROOT)), "git_blob": blob,
                              "body_sha256": hashlib.sha256(body).hexdigest()})
    groups = {}
    for route, record in pages.items():
        groups.setdefault(record["key"], []).append(record["locale"])
    manifest = {"schema": 1, "source_kind": "public-markdown-hugo-adaptation",
                "config": {"origins": {ORIGIN: "."}, "locales": ["en", "de", "es", "fr"],
                           "aliases": {}, "complete_manifest": False, "check_links": False},
                "pages": {route: {"key": r["key"], "locale": r["locale"], "state": "published",
                                   "canonical_channels": ["html"], "canonical_allowed": [route],
                                   "discovery": {"html": {"required": list(groups[r["key"]]), "reciprocal": True}}}
                          for route, r in pages.items()}}
    english = next(u for u, r in pages.items() if r["key"] == "complex-permalink" and r["locale"] == "en")
    german = next(u for u, r in pages.items() if r["locale"] == "de")
    about = next(u for u, r in pages.items() if r["key"] == "about")
    kits = {}
    for case in ["clean"] + [c[0] for c in CASES]:
        current, contract = copy.deepcopy(pages), copy.deepcopy(manifest)
        if case == "body_edit":
            current[about]["body"] += b"\nA local editorial revision for the repeat-check experiment.\n"
        elif case in {"wrong_canonical", "canonical_exception"}:
            current[english]["canonical_override"] = about if case == "wrong_canonical" else german
            if case == "canonical_exception":
                contract["pages"][english]["canonical_allowed"] = [german]
        elif case == "missing_alternate":
            current[english]["omit_label"] = "de"
        elif case in {"omitted_source", "partial_translation"}:
            del current[german]
            if case == "partial_translation":
                del contract["pages"][german]
                for spec in contract["pages"].values():
                    spec["discovery"]["html"]["required"] = [l for l in spec["discovery"]["html"]["required"] if l != "de"]
        elif case == "identity_swap":
            # Swap generator translation grouping, not editorial content keys.
            current[english]["translation_key"], current[about]["translation_key"] = "about", "complex-permalink"
            # Predeclared optional coverage isolates identity from the unequal
            # group sizes. This contract is not inferred from generated HTML.
            for spec in contract["pages"].values():
                spec["discovery"]["html"]["required"] = []
        kit = output / "sources" / case
        (kit / "content").mkdir(parents=True)
        shutil.copyfile(ROOT / "native_hugo/hugo.toml", kit / "hugo.toml")
        (kit / "layouts/_default").mkdir(parents=True)
        shutil.copyfile(ROOT / "native_hugo/layouts/_default/single.html", kit / "layouts/_default/single.html")
        shutil.copyfile(source_root / "UPSTREAM-LICENSE", kit / "UPSTREAM-LICENSE")
        for route, record in current.items():
            meta = {"title": record["title"], "translationKey": record["translation_key"],
                    "content_key": record["key"], "url": route.removeprefix(ORIGIN)}
            for option in ("canonical_override", "omit_label"):
                if option in record:
                    meta[option] = record[option]
            # JSON-escaped strings are valid TOML basic strings for these sources.
            header = "+++\n" + "".join(k + " = " + json.dumps(v, ensure_ascii=False) + "\n" for k, v in meta.items()) + "+++\n"
            (kit / "content" / Path(record["path"]).name).write_bytes(header.encode("utf-8") + record["body"])
        manifest_path = kit / "manifest.json"
        put_json(manifest_path, contract)
        kits[case] = (kit, manifest_path)
    return kits, source_checks, index


def summary(values):
    quartiles = statistics.quantiles(values, n=4, method="inclusive")
    return {"median": statistics.median(values), "q1": quartiles[0], "q3": quartiles[2],
            "min": min(values), "max": max(values)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hugo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=12)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT.resolve()) or output == ROOT.resolve():
        raise ValueError("Output must be a new directory inside this artifact")
    if args.repeats < 2 or args.repeats % 2:
        raise ValueError("Even repetitions >= 2 required")
    executable = args.hugo.resolve()
    version = subprocess.run([str(executable), "version"], capture_output=True, text=True, check=True, timeout=10).stdout.strip()
    if not version.startswith("hugo v0.147.9-"):
        raise ValueError("This experiment requires the reviewed Hugo 0.147.9 pin")
    output.mkdir(parents=True, exist_ok=False)
    kits, checks, index = prepare(output)
    commands, rows, starts, cohort = [], [], [], []
    env = dict(os.environ, HUGO_CACHEDIR=str(output / "hugo-cache"), GOMAXPROCS="1")

    def build(case, tag):
        kit, contract = kits[case]
        destination = output / "builds" / tag
        command = [str(executable), "--source", str(kit), "--destination", str(destination),
                   "--cacheDir", str(output / "hugo-cache"), "--noBuildLock"]
        completed, native_ns = timed(lambda: subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False, timeout=30, env=env))
        commands.append({"command": command, "returncode": completed.returncode, "stdout": completed.stdout,
                         "stderr": completed.stderr, "native_ns": native_ns, "case": case, "tag": tag})
        put_json(output / "commands.json", commands)
        completed.check_returncode()
        facts, extraction_ns = timed(lambda: load_build(contract, destination))
        return facts, native_ns, extraction_ns

    clean, native_start, extraction_start = build("clean", "initial-clean")
    if evaluate(clean) or evaluate_html_contract(clean):
        raise AssertionError("Native clean adaptation did not satisfy its contract")
    for case_index, (case, label, expected) in enumerate(CASES):
        cold = {}
        sessions = {}
        for name, evaluator in (("full", evaluate), ("join", evaluate_html_contract)):
            _, cold[name] = timed(lambda fn=evaluator: export(fn(clean)))
        for name, cls in (("coalesced", CoalescedIncremental), ("sliced", SlicedIncremental)):
            def initialize(cls=cls):
                session = ReleaseSession(clean, engine_class=cls)
                return session, export(session.issues())
            (session, _), cold[name] = timed(initialize)
            sessions[name] = session
        # Untimed by the update series, but all builder commands remain recorded.
        warm, _, _ = build(case, "warm-" + case)
        expected_issues = evaluate(warm)
        if evaluate_html_contract(warm) != expected_issues:
            raise AssertionError("Same-information join differs on " + case)
        if label == "clean" and expected_issues:
            raise AssertionError((case, expected_issues))
        if expected and expected not in {i.code for i in expected_issues}:
            raise AssertionError((case, expected, expected_issues))
        blind = joint_output(warm)
        # The supplied excerpts contain links to pages outside this five-file
        # candidate. Retain those reports but compare annotations only, matching
        # the contract's disabled ordinary-link scope on every case.
        annotation_blind = {finding for finding in blind if finding[-1] != "link"}
        if case == "identity_swap":
            if annotation_blind or {i.code for i in expected_issues} != {"DISCOVERY_ID"}:
                raise AssertionError("Identity experiment is not coherent and identity-only")
        cohort.append({"case": case, "label": label, "declared_routes": sum(k[0] == "m" for k in warm),
                       "observed_routes": sum(k[0] == "o" for k in warm), "expected_rule": expected,
                       "same_information_exact_agreement": True, "output_only_annotations_rejected": bool(annotation_blind),
                       "output_only_annotation_findings": sorted(annotation_blind),
                       "excluded_body_link_findings": sorted(blind - annotation_blind),
                       "findings": [i.json() for i in sorted(expected_issues)]})
        for session in sessions.values():
            for previous, target in ((clean, warm), (warm, clean)):
                session.apply({k: v for k, v in delta(previous, target).items() if k[0] != "g"})
                if session.issues() != evaluate(target):
                    raise AssertionError("Warm-up cache disagreement")
        starts.append({"case": case, "native_ns": native_start, "extraction_ns": extraction_start,
                       "checking_and_export_ns": cold,
                       "whole_ns": {n: native_start + extraction_start + t for n, t in cold.items()}})
        previous = clean
        for repeat in range(args.repeats):
            direction = "forward" if repeat % 2 == 0 else "reverse"
            current, native_ns, extraction_ns = build(case if repeat % 2 == 0 else "clean", f"{case}-{repeat:02d}-{direction}")
            changes, diff_ns = timed(lambda: {k: v for k, v in delta(previous, current).items() if k[0] != "g"})
            reference = export(evaluate(current))
            names = ["full", "join", "coalesced", "sliced"]
            rotation = (case_index + repeat) % len(names)
            order = names[rotation:] + names[:rotation]
            measured, stats = {}, {}
            for name in order:
                if name in sessions:
                    def check(name=name):
                        stats[name] = sessions[name].apply(changes)
                        return export(sessions[name].issues())
                else:
                    evaluator = evaluate if name == "full" else evaluate_html_contract
                    def check(evaluator=evaluator):
                        return export(evaluator(current))
                actual, measured[name] = timed(check)
                if actual != reference:
                    raise AssertionError((case, repeat, name, "Exact issue-tuple mismatch"))
            whole = {n: native_ns + extraction_ns + t + (diff_ns if n in sessions else 0) for n, t in measured.items()}
            rows.append({"case": case, "repeat": repeat, "direction": direction, "series_order": order,
                         "native_ns": native_ns, "extraction_ns": extraction_ns, "difference_ns": diff_ns,
                         "primary_changes": len(changes), "checking_and_export_ns": measured,
                         "whole_ns": whole, "cache_stats": stats, "exact_agreement": True})
            previous = current
        print(case, args.repeats, "paired updates; exact agreement", flush=True)
    summaries = {}
    for case, _, _ in CASES:
        group = [r for r in rows if r["case"] == case]
        summaries[case] = {"whole_ms": {n: summary([r["whole_ns"][n] / 1e6 for r in group]) for n in ("full", "join", "coalesced", "sliced")},
                           "checking_and_export_ms": {n: summary([r["checking_and_export_ns"][n] / 1e6 for r in group]) for n in ("full", "join", "coalesced", "sliced")},
                           "paired_full_over_sliced": summary([r["whole_ns"]["full"] / r["whole_ns"]["sliced"] for r in group]),
                           "native_ms": summary([r["native_ns"] / 1e6 for r in group]),
                           "extraction_ms": summary([r["extraction_ns"] / 1e6 for r in group]),
                           "difference_ms": summary([r["difference_ns"] / 1e6 for r in group])}
    finite = {}
    for name in ("full", "join", "coalesced", "sliced"):
        finite[name] = {"seven_sequences_total_ms": (sum(s["whole_ns"][name] for s in starts) + sum(r["whole_ns"][name] for r in rows)) / 1e6,
                        "cold_check_and_export_ms": summary([s["checking_and_export_ns"][name] / 1e6 for s in starts])}
    result = {"version": version, "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
              "python": sys.version, "platform": platform.platform(), "hash_seed": os.environ.get("PYTHONHASHSEED"),
              "source_repository": index["source_repository"], "source_commit": index["source_commit"],
              "source_checks": checks, "cases": cohort, "rows": rows, "cold_starts": starts,
              "summaries": summaries, "finite_workflow": finite, "commands": commands,
              "native_build_calls": len(commands), "measured_updates": len(rows),
              "scope": "One five-file public-source adaptation; same upstream as Pandoc/PJ. Four controlled faults, three legitimate changes and a clean seed. Not field faults, deployment, native Jekyll, or additional independent sites. Liquid and whole-site body links excluded. Native Hugo handles translation grouping and routes; adapted front matter and templates are authored.",
              "cost_boundary": "Paired component-accounted workflow: generation including subprocess startup, full local extraction/normalization, checking and deterministic JSON issue export; cached paths also pay whole-snapshot difference and validated apply. Each path shares the same measured generation/extraction sample. Source preparation, dependency download, test assertions, warm-up, reporting and filesystem publication are excluded. Cold cache construction/normalization/export is charged once per finite 12-update sequence. The clean initial build is measured once and reused across the seven component-accounted cold-start sequences, not seven independently timed initial builds."}
    put_json(output / "results.json", result)
    print(json.dumps({"native_build_calls": len(commands), "measured_updates": len(rows), "finite_workflow": finite}, indent=2))


if __name__ == "__main__":
    main()
