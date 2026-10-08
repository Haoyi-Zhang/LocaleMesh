#!/usr/bin/env python3
"""Recompute obligation-slicing tables, macros and vector plots from raw pairs."""
from pathlib import Path
import argparse
import json
import statistics

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
PAPER = ROOT.parent / "paper"
KINDS = [
    "local_canonical",
    "deleted_page",
    "unused_alias",
    "global_link_policy",
    "hub_canonical",
    "hub_status",
]
NAMES = {
    "local_canonical": "Local canonical",
    "deleted_page": "Page deletion",
    "unused_alias": "Unused alias",
    "global_link_policy": "Global link policy",
    "hub_canonical": "Hub canonical",
    "hub_status": "Hub status",
}


def stats(values):
    values = sorted(values)
    q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return {
        "median": statistics.median(values),
        "q1": q1,
        "q3": q3,
        "min": values[0],
        "max": values[-1],
        "n": len(values),
    }


def table(columns, headings, rows):
    lines = [r"\begin{tabular}{" + columns + "}", r"\toprule", " & ".join(headings) + r" \\", r"\midrule"]
    lines.extend(" & ".join(map(str, row)) + r" \\" for row in rows)
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plots", action="store_true")
    args = parser.parse_args()

    summaries = []
    memory = []
    all_rows = []
    for routes in (100, 1000, 10000):
        raw = json.loads((RESULTS / f"sliced-{routes}.json").read_text())
        assert len(raw["rows"]) == 6 * raw["repeats"] == 72
        assert all(row["agreement"] for row in raw["rows"])
        memory.append({"routes": routes, **raw["memory"]})
        all_rows.extend(raw["rows"])
        for kind in KINDS:
            rows = [row for row in raw["rows"] if row["kind"] == kind]
            assert len(rows) == 12
            summary = {"routes": routes, "kind": kind, "source": f"sliced-{routes}.json"}
            for key in ("full", "coalesced", "sliced", "safe_coalesced", "safe_sliced", "snapshot_diff"):
                summary[key + "_ms"] = stats([row[key + "_ns"] / 1e6 for row in rows])
            summary["combined_coalesced_ms"] = stats([
                (row["snapshot_diff_ns"] + row["safe_coalesced_ns"]) / 1e6 for row in rows
            ])
            summary["combined_sliced_ms"] = stats([
                (row["snapshot_diff_ns"] + row["safe_sliced_ns"]) / 1e6 for row in rows
            ])
            summary["paired_C_over_S"] = stats([
                row["safe_coalesced_ns"] / row["safe_sliced_ns"] for row in rows
            ])
            summary["paired_full_over_combined_sliced"] = stats([
                row["full_ns"] / (row["snapshot_diff_ns"] + row["safe_sliced_ns"]) for row in rows
            ])
            summary["ratio_of_medians_full_over_combined_sliced"] = (
                summary["full_ms"]["median"] / summary["combined_sliced_ms"]["median"]
            )
            summary["ratio_of_medians_C_over_S"] = (
                summary["safe_coalesced_ms"]["median"] / summary["safe_sliced_ms"]["median"]
            )
            summary["coalesced_owners"] = stats([row["coalesced_owners"] for row in rows])
            summary["sliced_owners"] = stats([row["sliced_owners"] for row in rows])
            summary["sliced_readers"] = stats([row["sliced_readers"] for row in rows])
            summaries.append(summary)

    selected = {item["kind"]: item for item in summaries if item["routes"] == 10000}
    out = PAPER / "generated"
    out.mkdir(exist_ok=True)

    numbers = {"SlicedUpdates": len(all_rows)}
    prefixes = {
        "local_canonical": "SLocal",
        "deleted_page": "SDelete",
        "unused_alias": "SAlias",
        "global_link_policy": "SPolicy",
        "hub_canonical": "SHubCanonical",
        "hub_status": "SHubStatus",
    }
    for kind, prefix in prefixes.items():
        row = selected[kind]
        metrics = {
            "Full": "full_ms",
            "Coalesced": "safe_coalesced_ms",
            "Sliced": "safe_sliced_ms",
            "Diff": "snapshot_diff_ms",
            "Combined": "combined_sliced_ms",
        }
        for suffix, metric in metrics.items():
            numbers[prefix + suffix] = f"{row[metric]['median']:.3f}"
        numbers[prefix + "FullOverCombined"] = f"{row['ratio_of_medians_full_over_combined_sliced']:.2f}"
        numbers[prefix + "COverS"] = f"{row['ratio_of_medians_C_over_S']:.2f}"
        numbers[prefix + "Owners"] = f"{int(row['sliced_owners']['median']):,}"
        numbers[prefix + "Readers"] = f"{int(row['sliced_readers']['median']):,}"

    last_memory = memory[-1]
    for key, prefix in (("coalesced", "SMCoalesced"), ("sliced", "SMSliced")):
        entry = last_memory[key]
        numbers[prefix + "MiB"] = f"{entry['retained_python_bytes'] / 2**20:.2f}"
        numbers[prefix + "Edges"] = f"{entry['dependency_edges']:,}"
        numbers[prefix + "Reads"] = f"{entry['logical_projection_edges']:,}"
        numbers[prefix + "Readers"] = f"{entry['cached_readers']:,}"
    numbers["SMMemoryRatio"] = f"{last_memory['sliced']['retained_python_bytes'] / last_memory['coalesced']['retained_python_bytes']:.2f}"
    numbers["StateSpaceStates"] = f"{json.loads((RESULTS / 'state-space.json').read_text())['states']:,}"
    numbers["StateSpaceTransitions"] = f"{json.loads((RESULTS / 'state-space.json').read_text())['transitions']:,}"

    (out / "sliced-numbers.tex").write_text(
        "".join(f"\\newcommand{{\\{key}}}{{{value}}}\n" for key, value in numbers.items())
    )

    time_rows = []
    dispersion_rows = []
    for kind in KINDS:
        row = selected[kind]
        time_rows.append([
            NAMES[kind],
            f"{row['full_ms']['median']:.2f}",
            f"{row['safe_coalesced_ms']['median']:.2f}",
            f"{row['safe_sliced_ms']['median']:.2f}",
            f"{row['combined_sliced_ms']['median']:.2f}",
            f"{row['ratio_of_medians_full_over_combined_sliced']:.2f}",
            f"{int(row['sliced_readers']['median']):,}",
        ])
        ratio = row["paired_full_over_combined_sliced"]
        sliced = row["safe_sliced_ms"]
        dispersion_rows.append([
            NAMES[kind],
            f"{sliced['q1']:.2f}--{sliced['q3']:.2f}",
            f"{ratio['median']:.2f}",
            f"{ratio['q1']:.2f}--{ratio['q3']:.2f}",
        ])

    (out / "sliced-times.tex").write_text(table(
        "lrrrrrr",
        ["Change", "Full", "C txn", "S txn", "Diff + S", "Full/(diff+S)", "Slices"],
        time_rows,
    ))
    (out / "sliced-dispersion.tex").write_text(table(
        "lrrr",
        ["Change", "S txn IQR (ms)", "Paired ratio", "Ratio IQR"],
        dispersion_rows,
    ))
    memory_rows = []
    for key, label in (("coalesced", "C"), ("sliced", "S")):
        entry = last_memory[key]
        memory_rows.append([
            label,
            f"{entry['cached_readers']:,}",
            f"{entry['dependency_edges']:,}",
            f"{entry['logical_projection_edges']:,}",
            f"{entry['retained_python_bytes'] / 2**20:.2f}",
        ])
    (out / "sliced-memory.tex").write_text(table(
        "lrrrr",
        ["Cache", "Readers", "Groups", "Reads", "MiB"],
        memory_rows,
    ))

    result = {
        "matched": summaries,
        "memory": memory,
        "numbers": numbers,
        "uncertainty": (
            "Twelve alternating paired updates per change and scale; rotating full/core "
            "execution order; validated-engine repetition blocks rotate across change kinds. Medians and "
            "inclusive IQRs are process observations, not independent-site estimates."
        ),
        "memory_scope": (
            "Recursive retained-object measurements include each cache's owned fact copy and use "
            "identity-deduplicated sys.getsizeof over cache roots; the caller's input, process RSS "
            "and browser memory are excluded."
        ),
        "measurement_scope": (
            "Complete normalized snapshot difference plus validated transaction and complete "
            "issue materialization. HTML parsing, framework builds and event acquisition are excluded."
        ),
    }
    (RESULTS / "sliced-summary.json").write_text(json.dumps(result, indent=2) + "\n")

    lines = [
        "# Obligation-sliced incremental evaluation",
        "",
        result["measurement_scope"],
        "",
        "| Change | Full ms | C txn ms | S txn ms | Diff + S ms | Full / combined | S slices |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in time_rows)
    lines.extend(["", result["uncertainty"], "", result["memory_scope"], ""])
    lines.extend(" / ".join(row) for row in memory_rows)
    lines.extend([
        "",
        "Slicing preserves the union of exact field reads in the bounded state-space experiment.",
        "It lowers broad-update recomputation but stores more reader records and can lose on changes "
        "that invalidate no reader yet require scanning many footprint groups.",
    ])
    (ROOT / "docs" / "SLICED-RESULTS.md").write_text("\n".join(lines) + "\n")

    if args.plots:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        for kind, filename in (("global_link_policy", "sliced-policy"), ("hub_status", "sliced-status")):
            rows = [next(item for item in summaries if item["routes"] == routes and item["kind"] == kind)
                    for routes in (100, 1000, 10000)]
            fig, ax = plt.subplots(figsize=(3.30, 2.58))
            series = [
                ("full_ms", "Full scan", "o", "-"),
                ("safe_coalesced_ms", "Route-wide txn", "s", "--"),
                ("safe_sliced_ms", "Sliced txn", "^", "-."),
                ("combined_sliced_ms", "Difference + sliced", "D", ":"),
            ]
            for metric, label, marker, linestyle in series:
                y = [row[metric]["median"] for row in rows]
                low = [row[metric]["median"] - row[metric]["q1"] for row in rows]
                high = [row[metric]["q3"] - row[metric]["median"] for row in rows]
                ax.errorbar(
                    [100, 1000, 10000], y, yerr=[low, high], marker=marker,
                    linestyle=linestyle, markersize=4, linewidth=1, capsize=2, label=label,
                )
            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.set_xticks([100, 1000, 10000], labels=["100", "1,000", "10,000"])
            ax.set_xlabel("Emitted routes", fontsize=9)
            ax.set_ylabel("Time (ms), median and IQR", fontsize=9)
            ax.tick_params(labelsize=8)
            ax.grid(axis="y", which="major", linewidth=0.35, alpha=0.4)
            ax.legend(
                fontsize=7.1, loc="lower center", bbox_to_anchor=(0.5, 1.01),
                ncol=2, frameon=False, columnspacing=1.0, handlelength=2.4,
            )
            fig.tight_layout(pad=0.65)
            fig.savefig(PAPER / "figures" / f"{filename}.pdf", bbox_inches="tight")
            fig.savefig(PAPER / "figures" / f"{filename}.png", dpi=220, bbox_inches="tight")
            plt.close(fig)

    print(json.dumps(numbers, indent=2))


if __name__ == "__main__":
    main()
