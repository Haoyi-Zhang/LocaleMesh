#!/usr/bin/env python3
"""Bounded mixed-radix state-space agreement experiment.

The experiment enumerates 5,120 structurally valid two-locale release states in a
reflected mixed-radix Gray order, so each successive state changes one dimension.
It compares four incremental implementations with the independent full evaluator
and verifies that obligation slicing preserves the union of exact logical reads.
This is bounded model exploration, not a proof for arbitrary Web releases.
"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import copy
import json
import resource
import statistics
import time
from collections import Counter
from itertools import product

from localemesh.coalesced import CoalescedIncremental
from localemesh.faceted import FacetedIncremental
from localemesh.fixtures import make_site, to_facts
from localemesh.full import evaluate
from localemesh.incremental import Incremental
from localemesh.model import delta, owners
from localemesh.sliced import SlicedIncremental

DIMENSIONS = {
    "target_manifest": ("published", "draft", "removed", "redirect", "absent"),
    "target_observation": ("live", "missing", "unavailable", "redirect"),
    "source_canonical": ("self", "target", "missing", "external"),
    "source_alternate": ("target", "self", "missing", "external"),
    "required_target": (False, True),
    "reciprocal": (False, True),
    "source_sitemap": (False, True),
    "check_links": (False, True),
}


def mixed_gray(radices):
    """Return a reflected mixed-radix Gray sequence.

    Every neighboring tuple differs in exactly one coordinate by one step.
    """
    sequence = [()]
    for radix in radices:
        expanded = []
        for value in range(radix):
            block = sequence if value % 2 == 0 else reversed(sequence)
            expanded.extend(prefix + (value,) for prefix in block)
        sequence = expanded
    return sequence


def make_state(indices):
    names = list(DIMENSIONS)
    choices = {name: DIMENSIONS[name][index] for name, index in zip(names, indices)}
    manifest, observations, sitemap = make_site("A1", 1)
    routes = sorted(manifest["pages"], key=lambda route: manifest["pages"][route]["locale"])
    target = next(route for route in routes if manifest["pages"][route]["locale"] == "de")
    source = next(route for route in routes if manifest["pages"][route]["locale"] == "en")
    external = "https://outside.invalid/state-space/"

    # Exercise link reachability under the target observation and global policy.
    observations[source]["links"] = [target]
    manifest["config"]["check_links"] = choices["check_links"]

    target_spec = manifest["pages"][target]
    state = choices["target_manifest"]
    if state == "absent":
        manifest["pages"].pop(target)
    elif state in {"draft", "removed"}:
        target_spec["state"] = state
    elif state == "redirect":
        manifest["pages"][target] = {
            "key": target_spec["key"],
            "locale": target_spec["locale"],
            "state": "redirect",
            "redirect_to": source,
            "redirect_allowed": [source],
            "sitemap": False,
        }

    observation = choices["target_observation"]
    if observation == "missing":
        observations.pop(target)
    elif observation == "unavailable":
        observations[target]["status"] = 404
    elif observation == "redirect":
        observations[target]["redirect"] = source

    canonical = choices["source_canonical"]
    observations[source]["canonical"]["html"] = {
        "self": [source],
        "target": [target],
        "missing": [],
        "external": [external],
    }[canonical]

    alternate = choices["source_alternate"]
    de_target = {
        "target": target,
        "self": source,
        "external": external,
    }.get(alternate)
    pairs = [["en", source]]
    if de_target is not None:
        pairs.append(["de", de_target])
    observations[source]["alternates"]["html"] = pairs
    policy = manifest["pages"][source]["discovery"]["html"]
    policy["required"] = ["en", "de"] if choices["required_target"] else ["en"]
    policy["reciprocal"] = choices["reciprocal"]

    if choices["source_sitemap"]:
        sitemap[source] = []
        manifest["pages"][source]["sitemap"] = True
    else:
        sitemap.pop(source, None)
        manifest["pages"][source]["sitemap"] = False

    return to_facts((manifest, observations, sitemap)), choices


def sliced_union(engine, owner):
    result = set()
    for reader in engine._all_reader_ids(owner):
        result.update(engine.expanded_reads(reader))
    return result


def main():
    started = time.perf_counter()
    names = list(DIMENSIONS)
    radices = [len(DIMENSIONS[name]) for name in names]
    sequence = mixed_gray(radices)
    assert len(sequence) == 5120
    assert len(set(sequence)) == len(sequence)
    for left, right in zip(sequence, sequence[1:]):
        changed = [index for index, pair in enumerate(zip(left, right)) if pair[0] != pair[1]]
        assert len(changed) == 1
        assert abs(left[changed[0]] - right[changed[0]]) == 1

    current, current_choices = make_state(sequence[0])
    engines = {
        "record": Incremental(current),
        "projected": FacetedIncremental(current),
        "coalesced": CoalescedIncremental(current),
        "sliced": SlicedIncremental(current),
    }
    expected = evaluate(current)
    assert all(engine.issues() == expected for engine in engines.values())

    unique_issue_sets = {tuple(sorted(expected))}
    issue_code_occurrences = Counter(issue.code for issue in expected)
    categories = Counter({"release" if any(i.category == "release" for i in expected) else "no-release": 1})
    transition_facts = []
    coalesced_owners = []
    sliced_owners = []
    sliced_readers = []
    cold_checks = 1

    for step, indices in enumerate(sequence[1:], start=1):
        candidate, choices = make_state(indices)
        patch = delta(current, candidate)
        expected = evaluate(candidate)
        stats = {name: engine.update(patch) for name, engine in engines.items()}
        for name, engine in engines.items():
            assert engine.issues() == expected, (step, name, current_choices, choices)
        # Slicing may duplicate a read across obligations, but its union must equal
        # the monolithic exact footprint for every owner.
        for owner in owners(candidate):
            assert engines["coalesced"].expanded_reads(owner) == sliced_union(engines["sliced"], owner), (step, owner)

        # Periodic independent cold construction checks catch transition-only bugs.
        if step % 257 == 0:
            cold = SlicedIncremental(candidate)
            assert cold.issues() == expected
            for owner in owners(candidate):
                assert engines["coalesced"].expanded_reads(owner) == sliced_union(cold, owner)
            cold_checks += 1

        unique_issue_sets.add(tuple(sorted(expected)))
        issue_code_occurrences.update(issue.code for issue in expected)
        categories["release" if any(i.category == "release" for i in expected) else "no-release"] += 1
        transition_facts.append(len(patch))
        coalesced_owners.append(stats["coalesced"]["invalidated_owners"])
        sliced_owners.append(stats["sliced"]["invalidated_owners"])
        sliced_readers.append(stats["sliced"]["invalidated_readers"])
        current, current_choices = candidate, choices

    assert len(sequence) == categories.total()
    result = {
        "dimensions": {name: list(values) for name, values in DIMENSIONS.items()},
        "states": len(sequence),
        "transitions": len(sequence) - 1,
        "cold_reconstructions": cold_checks,
        "gray_adjacency": True,
        "engines": list(engines),
        "all_issue_sets_equal": True,
        "all_sliced_read_unions_equal_coalesced": True,
        "unique_issue_sets": len(unique_issue_sets),
        "states_with_release_issues": categories["release"],
        "states_without_release_issues": categories["no-release"],
        "issue_code_state_occurrences": dict(sorted(issue_code_occurrences.items())),
        "transition_changed_facts": {
            "min": min(transition_facts),
            "median": statistics.median(transition_facts),
            "max": max(transition_facts),
        },
        "coalesced_invalidated_owners": {
            "min": min(coalesced_owners),
            "median": statistics.median(coalesced_owners),
            "max": max(coalesced_owners),
        },
        "sliced_invalidated_owners": {
            "min": min(sliced_owners),
            "median": statistics.median(sliced_owners),
            "max": max(sliced_owners),
        },
        "sliced_invalidated_readers": {
            "min": min(sliced_readers),
            "median": statistics.median(sliced_readers),
            "max": max(sliced_readers),
        },
        "wall_s": time.perf_counter() - started,
        "maxrss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "scope": (
            "Bounded two-locale state-space exploration over explicit manifest, observation, "
            "canonical, discovery, sitemap, reciprocity and link-policy dimensions. It checks "
            "implementation agreement and exact read preservation, not real-world prevalence "
            "or all possible Web states."
        ),
    }
    (ROOT / "results" / "state-space.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
