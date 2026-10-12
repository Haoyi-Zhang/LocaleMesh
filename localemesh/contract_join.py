"""Batch contract joins for the flat, published HTML profile.

This authored same-information baseline has no cache and imports no evaluator.
It accepts normalized facts with HTML canonicals/discovery, direct mounted URLs,
unique published identities, no aliases/redirects/sitemaps, and disabled ordinary
links. Unsupported policy is rejected, not silently ignored. It is not a vendor
product or a replacement for LocaleMesh's broader release semantics.
"""
from collections import Counter, defaultdict
from urllib.parse import urlsplit

from .model import Issue


def evaluate_html_contract(facts):
    config = facts[("cfg",)]
    if (config.get("aliases") or config.get("check_links", True)
            or config.get("complete_manifest", False)
            or config.get("extensions") or any(k[0] == "s" for k in facts)):
        raise ValueError("Batch join requires the flat HTML-only profile")
    specs = {k[1]: v for k, v in facts.items() if k[0] == "m"}
    observed = {k[1]: v for k, v in facts.items() if k[0] == "o"}
    supported = {"key", "locale", "state", "canonical_allowed", "canonical_required",
                 "canonical_channels", "discovery"}
    identities = Counter((s["key"], s["locale"].lower()) for s in specs.values())
    for spec in specs.values():
        discovery = spec.get("discovery", {})
        if (set(spec) - supported or spec.get("state", "published") != "published"
                or spec.get("canonical_channels", ["html"]) != ["html"]
                or set(discovery) - {"html"}
                or any(set(p) - {"required", "reciprocal"} for p in discovery.values())):
            raise ValueError("Batch join received unsupported page policy")
    if any(n != 1 for n in identities.values()):
        raise ValueError("Batch join requires unique declared identities")
    for obs in observed.values():
        if (obs.get("redirect") or set(obs.get("canonical", {})) - {"html"}
                or set(obs.get("alternates", {})) - {"html"}):
            raise ValueError("Batch join received non-flat observations")

    result = set()

    def emit(owner, code, channel="", detail="", category="release"):
        result.add(Issue(category, code, owner, channel, str(detail)))

    # Build shared relational indexes once; none uses expected case labels.
    pairs = {r: o.get("alternates", {}).get("html", []) for r, o in observed.items()}
    backs = {r: set(map(tuple, p)) for r, p in pairs.items()}
    for route, obs in observed.items():
        for code, detail in obs.get("diagnostics", []):
            emit(route, code, "ingestion", detail, "ambiguity")

    def live(owner, target, code):
        parsed = urlsplit(target)
        if parsed.scheme + "://" + parsed.netloc not in config["origins"]:
            emit(owner, "UNMOUNTED_TARGET", "html", target, "ambiguity")
            return False
        obs = observed.get(target)
        if obs is None or not 200 <= obs.get("status", 200) < 300:
            emit(owner, code, "html", target)
            return False
        return True

    for route, spec in specs.items():
        obs = observed.get(route)
        if obs is None:
            emit(route, "MISSING_ROUTE")
            continue
        if not 200 <= obs.get("status", 200) < 300:
            emit(route, "ROUTE_STATE")
        if obs.get("lang", "").lower() != spec["locale"].lower():
            emit(route, "LANGUAGE", "html")
        if obs.get("key") is not None and obs["key"] != spec["key"]:
            emit(route, "CONTENT_ID", "html")
        allowed = spec.get("canonical_allowed")
        targets = obs.get("canonical", {}).get("html", [])
        if spec.get("canonical_required", allowed is not None) and not targets:
            emit(route, "CANONICAL_MISSING", "html")
        if len(set(targets)) > 1:
            emit(route, "CANONICAL_MULTIPLE", "html")
        for target in targets:
            if allowed is not None and target not in allowed:
                emit(route, "CANONICAL_POLICY", "html", target)
            live(route, target, "CANONICAL_TARGET")
        policy = spec.get("discovery", {}).get("html")
        if policy is None:
            continue
        by_label = defaultdict(set)
        for label, target in pairs.get(route, []):
            by_label[label].add(target)
        for label in policy.get("required", []):
            if label.lower() not in by_label:
                emit(route, "DISCOVERY_MISSING", "html", label.lower())
        for label, choices in by_label.items():
            if len(choices) > 1:
                emit(route, "DISCOVERY_MULTIPLE", "html", label)
        for label, target in pairs.get(route, []):
            if not live(route, target, "DISCOVERY_TARGET") or label == "x-default":
                continue
            target_spec = specs.get(target)
            if target_spec is None:
                emit(route, "TARGET_IDENTITY_UNKNOWN", "html", target, "ambiguity")
                continue
            if target_spec["key"] != spec["key"]:
                emit(route, "DISCOVERY_ID", "html", target)
            if target_spec["locale"].lower() != label:
                emit(route, "DISCOVERY_LOCALE", "html", target)
            if (policy.get("reciprocal", False) and target != route
                    and (spec["locale"].lower(), route) not in backs.get(target, set())):
                emit(route, "RECIPROCITY", "html", target)
    return result
