#!/usr/bin/env python3
"""Recompute internal relationships between raw observations and deliverables.

This audit verifies denominators, agreement flags, generated statistics, tests,
coverage, bibliography structure, and experiment completeness. It is deliberately
not an independent semantic oracle or evidence of production deployment.
"""
from __future__ import annotations

import collections
import csv
import gzip
import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
PAPER = ROOT.parent / "paper"
SCALES = (100, 1_000, 10_000)
AGREEMENT_COLUMNS = (
    "agreement",
    "projected_agreement",
    "transaction_agreement",
    "coalesced_agreement",
    "coalesced_transaction_agreement",
    "sliced_agreement",
    "sliced_transaction_agreement",
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf8"))


def csv_rows(name: str):
    with (RESULTS / name).open(newline="", encoding="utf8") as stream:
        return list(csv.DictReader(stream))


def macros(name: str):
    text = (PAPER / "generated" / name).read_text(encoding="utf8")
    return dict(re.findall(r"\\newcommand\{\\(\w+)\}\{([^}]+)\}", text))


def verify_score_population(rows, counts, scores):
    for score in scores:
        key = score["key"]
        tp = sum(int(row[key]) for row in rows if row["label"] == "defect")
        fp = sum(int(row[key]) for row in rows if row["label"] == "clean")
        assert (tp, fp) == (score["tp"], score["fp"])
        assert score["recall"] == tp / counts["defect"]
        assert score["fpr"] == fp / counts["clean"]


def require_agreement(rows):
    for row in rows:
        for column in AGREEMENT_COLUMNS:
            assert row[column] == "1", (row.get("site"), row.get("case"), column)


def check_baseline_results():
    rows = csv_rows("releases.csv")
    independent = csv_rows("independent_releases.csv")
    compositions = csv_rows("composition_holdout.csv")
    counts = collections.Counter(row["label"] for row in rows)
    independent_counts = collections.Counter(row["label"] for row in independent)
    summary = read_json(RESULTS / "summary.json")

    assert len(rows) == 174 and len(independent) == 40 and len(compositions) == 96
    assert dict(counts) == summary["counts"]
    assert dict(independent_counts) == summary["independent_counts"]
    require_agreement(rows + independent + compositions)

    for row in rows:
        raw = read_json(RESULTS / "findings" / f"{row['site']}.{row['case']}.json")
        assert raw["site"] == row["site"] and raw["case"] == row["case"]
        release_count = sum(issue["category"] == "release" for issue in raw["full"])
        ambiguity_count = sum(issue["category"] == "ambiguity" for issue in raw["full"])
        assert release_count == int(row["release_findings"])
        assert ambiguity_count == int(row["ambiguities"])
        assert bool(release_count) == bool(int(row["full_detected"]))
        assert not raw["incremental_difference"]
        if row["expected_rule"]:
            assert row["expected_rule"] in {issue["code"] for issue in raw["full"]}

    verify_score_population(rows, counts, summary["scores"])
    verify_score_population(independent, independent_counts, summary["independent_scores"])
    return rows, independent, compositions, counts, independent_counts, summary


def check_record_benchmarks(summary):
    update_count = 0
    for scale in summary["scale"]:
        raw = read_json(RESULTS / scale["source"])["rows"]
        update_count += len(raw)
        assert len(raw) == 12 and all(row["agreement"] == 1 for row in raw)
        for source, destination in (
            ("full_ns", "full_ms"),
            ("update_ns", "update_ms"),
            ("snapshot_diff_ns", "snapshot_diff_ms"),
        ):
            expected = statistics.median(row[source] / 1e6 for row in raw)
            assert scale[destination]["median"] == expected
        combined = statistics.median(
            (row["update_ns"] + row["snapshot_diff_ns"]) / 1e6 for row in raw
        )
        assert scale["diff_update_ms"]["median"] == combined
        assert scale["speedup_ratio_medians_with_diff"] == scale["full_ms"]["median"] / combined

    fanout = read_json(RESULTS / "fanout-sweep-10000.json")
    assert fanout["complete"] is True and fanout["repeats"] == 12
    assert all(row["agreement"] == 1 for row in fanout["rows"])
    values = sorted({row["declared_fanout"] for row in fanout["rows"]})
    assert all(sum(row["declared_fanout"] == value for row in fanout["rows"]) == 12 for value in values)
    first_combined = next(
        (row["declared_fanout"] for row in fanout["summary"] if row["with_diff_ratio"] <= 1),
        None,
    )
    first_update = next(
        (row["declared_fanout"] for row in fanout["summary"] if row["update_only_ratio"] <= 1),
        None,
    )
    assert fanout["first_measured_diff_plus_update_not_faster"] == first_combined
    assert fanout["first_measured_update_only_not_faster"] == first_update
    return update_count, fanout


def check_field_benchmarks():
    projected_rows = []
    for routes in SCALES:
        raw = read_json(RESULTS / f"projected-{routes}.json")
        assert len(raw["rows"]) == 6 * raw["repeats"]
        assert all(row["agreement"] for row in raw["rows"])
        projected_rows.extend(raw["rows"])
    projected_summary = read_json(RESULTS / "revision-summary.json")
    for item in projected_summary["projected"]:
        selected = [
            row for row in projected_rows
            if row["routes"] == item["routes"] and row["kind"] == item["kind"]
        ]
        expected = statistics.median(
            (row["snapshot_diff_ns"] + row["safe_projected_ns"]) / 1e6
            for row in selected
        )
        assert item["combined_ms"]["median"] == expected

    coalesced_rows = []
    for routes in SCALES:
        raw = read_json(RESULTS / f"coalesced-{routes}.json")
        assert len(raw["rows"]) == 72
        assert all(
            row["agreement"]
            and row["projected_owners"] == row["coalesced_owners"]
            and row["expanded_edges_projected"] == row["expanded_edges_coalesced"]
            for row in raw["rows"]
        )
        coalesced_rows.extend(raw["rows"])
    coalesced_summary = read_json(RESULTS / "coalesced-summary.json")
    for item in coalesced_summary["matched"]:
        selected = [
            row for row in coalesced_rows
            if row["routes"] == item["routes"] and row["kind"] == item["kind"]
        ]
        expected = statistics.median(
            (row["snapshot_diff_ns"] + row["safe_coalesced_ns"]) / 1e6
            for row in selected
        )
        assert item["combined_ms"]["median"] == expected
    return projected_rows, coalesced_rows


def check_sliced_results():
    rows = []
    for routes in SCALES:
        raw = read_json(RESULTS / f"sliced-{routes}.json")
        assert raw["routes"] == routes and raw["repeats"] == 12
        assert len(raw["rows"]) == 72
        assert all(
            row["agreement"]
            and row["coalesced_issues"] == row["sliced_issues"] == row["issues"]
            for row in raw["rows"]
        )
        rows.extend(raw["rows"])

    summary = read_json(RESULTS / "sliced-summary.json")
    for item in summary["matched"]:
        selected = [
            row for row in rows
            if row["routes"] == item["routes"] and row["kind"] == item["kind"]
        ]
        assert len(selected) == 12
        expected = statistics.median(
            (row["snapshot_diff_ns"] + row["safe_sliced_ns"]) / 1e6
            for row in selected
        )
        assert item["combined_sliced_ms"]["median"] == expected
        expected_ratio = item["full_ms"]["median"] / item["combined_sliced_ms"]["median"]
        assert item["ratio_of_medians_full_over_combined_sliced"] == expected_ratio

    state_space = read_json(RESULTS / "state-space.json")
    assert state_space["states"] == 5_120
    assert state_space["transitions"] == 5_119
    assert state_space["cold_reconstructions"] == 20
    assert state_space["gray_adjacency"] is True
    assert state_space["all_issue_sets_equal"] is True
    assert state_space["all_sliced_read_unions_equal_coalesced"] is True

    generated = macros("sliced-numbers.tex")
    assert int(generated["SlicedUpdates"].replace(",", "")) == len(rows)
    assert int(generated["StateSpaceStates"].replace(",", "")) == state_space["states"]
    assert int(generated["StateSpaceTransitions"].replace(",", "")) == state_space["transitions"]
    return rows, state_space


def check_external_and_ingestion():
    ingestion = read_json(RESULTS / "ingestion-replay.json")
    assert all(row["current"]["matches_literal_expectation"] for row in ingestion["regressions"])
    assert all(not row["legacy"]["matches_literal_expectation"] for row in ingestion["regressions"])

    contract = read_json(RESULTS / "contract-boundary.json")
    assert contract["counts"] == {
        "legacy_accepted_invalid": 13,
        "strict_rejected": 13,
        "atomic_rollback_checks": 2,
    }
    assert len(contract["cases"]) == 13
    assert all(row["legacy"]["accepted"] and not row["current"]["accepted"] for row in contract["cases"])

    browser = read_json(RESULTS / "browser-differential.json")
    assert browser["counts"] == {
        "edge_cases": 30,
        "same_selected_facts": 25,
        "undiagnosed_differences": 0,
        "native_gate_releases": 11,
        "native_gate_agreement": 11,
        "literal_expectations": 18,
        "compiled_outputs": 53,
        "compiled_agreement": 53,
        "network_requests": 0,
    }
    assert not browser["network_requests"]

    external = read_json(RESULTS / "external-page-summary.json")
    assert external["external_network_requests"] == 0
    assert external["shared_reachability_releases"] == 15
    assert external["shared_upstream_detected"] == external["shared_localemesh_detected"] == 15
    assert external["contrasts"]["coherent_identity_swap"]["upstream_errors"] == 0
    assert external["contrasts"]["coherent_identity_swap"]["localemesh_errors"] == 6
    raw_path = RESULTS / "external-page-raw.jsonl.gz"
    external_rows = [json.loads(line) for line in gzip.open(raw_path, "rt") if line.strip()]
    assert len(external_rows) == external["releases"]
    assert sum(len(row["results"]) for row in external_rows) == external["page_invocations"]
    assert sum(row["requests"] for row in external_rows) == external["local_response_requests"]
    assert not any(result["truncated"] for row in external_rows for result in row["results"])

    pandoc = read_json(RESULTS / "pandoc-run.json")
    assert len(pandoc["rows"]) == 11 and pandoc["native_compile_calls"] == 53
    assert all(command["returncode"] == 0 for command in pandoc["commands"])
    assert collections.Counter(row["label"] for row in pandoc["rows"]) == {
        "clean": 4,
        "defect": 6,
        "ambiguity": 1,
    }
    for row in pandoc["rows"]:
        assert row["compiler_exit_zero"]
        assert all(row[column] for column in (
            "agreement",
            "coalesced_agreement",
            "coalesced_transaction_agreement",
            "sliced_agreement",
            "sliced_transaction_agreement",
        ))

    integrations = read_json(RESULTS / "integration-probes.json")
    assert integrations["offline_only"] is True
    assert integrations["successful_native_builds"] == 0
    assert {row["family"] for row in integrations["probes"]} == {"astro", "hugo", "nextjs"}
    assert all(
        row["native_status"] == "NOT_EXECUTED_DEPENDENCIES_UNAVAILABLE"
        for row in integrations["probes"]
    )
    return ingestion, contract, browser, external, external_rows, pandoc, integrations


def check_tests_references_and_coverage():
    tests_log = (RESULTS / "tests.log").read_text(errors="replace")
    match = re.search(r"Ran (\d+) tests", tests_log)
    assert match and int(match.group(1)) >= 73
    assert re.search(r"\nOK\s*$", tests_log)

    coverage = read_json(RESULTS / "coverage.json")
    assert coverage["totals"]["percent_covered"] >= 85.0
    assert coverage["files"]["localemesh/sliced.py"]["summary"]["percent_covered"] >= 94.0

    references = read_json(RESULTS / "reference-audit.json")
    assert references["bibliography_entries"] >= 61
    assert references["bibliography_entries"] == references["in_text_citations"]
    return int(match.group(1)), coverage, references


def check_generated_counts(rows, independent, compositions, counts, pandoc, fanout):
    base = macros("numbers.tex")
    assert int(base["NamedReleases"]) == len(rows)
    assert int(base["IndependentReleases"]) == len(independent)
    assert int(base["AllNamedReleases"]) == len(rows) + len(independent)
    assert int(base["AllCheckedTransitions"]) == len(rows) + len(independent) + len(compositions)
    assert int(base["SeededDefects"]) == counts["defect"]
    assert int(base["CleanCases"]) == counts["clean"]
    assert int(base["AmbiguousCases"]) == counts["ambiguity"]
    assert int(base["FanoutTotalLastFast"]) < int(base["FanoutTotalFirstSlow"])
    assert int(base["FanoutTotalFirstSlow"]) == fanout["first_measured_diff_plus_update_not_faster"]

    revision = macros("revision-numbers.tex")
    expected_snapshots = len(rows) + len(independent) + len(compositions) + len(pandoc["rows"])
    assert int(revision["ReleaseSnapshots"]) == expected_snapshots
    assert int(revision["PandocCalls"]) == pandoc["native_compile_calls"]
    return expected_snapshots


def main():
    rows, independent, compositions, counts, independent_counts, summary = check_baseline_results()
    record_updates, fanout = check_record_benchmarks(summary)
    projected_rows, coalesced_rows = check_field_benchmarks()
    sliced_rows, state_space = check_sliced_results()
    ingestion, contract, browser, external, external_rows, pandoc, integrations = check_external_and_ingestion()
    tests, coverage, references = check_tests_references_and_coverage()
    snapshots = check_generated_counts(rows, independent, compositions, counts, pandoc, fanout)

    report = {
        "release_snapshots_compared": snapshots,
        "primary_named_releases": len(rows),
        "primary_label_counts": dict(counts),
        "separate_emitter_or_adaptation_releases": len(independent),
        "separate_emitter_or_adaptation_label_counts": dict(independent_counts),
        "composition_regressions": len(compositions),
        "bounded_state_space_states": state_space["states"],
        "bounded_state_space_transitions": state_space["transitions"],
        "record_scale_updates": record_updates,
        "fanout_updates": len(fanout["rows"]),
        "field_projection_updates": len(projected_rows),
        "coalesced_updates": len(coalesced_rows),
        "obligation_sliced_updates": len(sliced_rows),
        "pandoc_releases": len(pandoc["rows"]),
        "pandoc_native_writer_invocations": pandoc["native_compile_calls"],
        "external_page_invocations": sum(len(row["results"]) for row in external_rows),
        "external_response_requests": external["local_response_requests"],
        "browser_differential_counts": browser["counts"],
        "contract_boundary_counts": contract["counts"],
        "ingestion_regression_cases": len(ingestion["regressions"]),
        "unit_test_methods": tests,
        "unit_coverage_percent": coverage["totals"]["percent_covered"],
        "sliced_unit_coverage_percent": coverage["files"]["localemesh/sliced.py"]["summary"]["percent_covered"],
        "native_integration_builds": integrations["successful_native_builds"],
        "bibliography_entries": references["bibliography_entries"],
        "doi_entries": references["doi_entries"],
        "scope": (
            "Internal bookkeeping audit. It verifies reproducibility relationships, not "
            "independent editorial truth, natural-fault prevalence, or field deployment."
        ),
    }
    (RESULTS / "result-audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
