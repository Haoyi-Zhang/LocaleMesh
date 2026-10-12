import copy
import unittest

from localemesh.contract_join import evaluate_html_contract
from localemesh.full import evaluate
from localemesh.model import snapshot


def flat_release():
    origin = "https://join.localemesh.test"
    specs, observations = {}, {}
    for key in ("intro", "guide"):
        pairs = [[locale, f"{origin}/{locale}/{key}/"] for locale in ("en", "de")]
        for locale, route in pairs:
            specs[route] = {"key": key, "locale": locale, "state": "published",
                            "canonical_allowed": [route], "canonical_channels": ["html"],
                            "discovery": {"html": {"required": ["en", "de"], "reciprocal": True}}}
            observations[route] = {"status": 200, "lang": locale, "key": key,
                                   "canonical": {"html": [route]}, "alternates": {"html": copy.deepcopy(pairs)}, "links": []}
    return snapshot({"config": {"origins": {origin: "."}, "aliases": {}, "check_links": False,
                                 "complete_manifest": False}, "pages": specs}, observations)


class ContractJoinTests(unittest.TestCase):
    def assert_agreement(self, facts):
        self.assertEqual(evaluate_html_contract(facts), evaluate(facts))

    def test_clean_and_no_input_mutation(self):
        facts = flat_release()
        before = copy.deepcopy(facts)
        self.assert_agreement(facts)
        self.assertEqual(evaluate_html_contract(facts), set())
        self.assertEqual(facts, before)

    def test_same_information_catches_coherent_swap(self):
        facts = flat_release()
        specs = {k[1]: s for k, s in facts.items() if k[0] == "m"}
        intro = {s["locale"]: r for r, s in specs.items() if s["key"] == "intro"}
        guide = {s["locale"]: r for r, s in specs.items() if s["key"] == "guide"}
        intro["de"], guide["de"] = guide["de"], intro["de"]
        for group in (intro, guide):
            for route in group.values():
                facts[("o", route)]["alternates"]["html"] = [list(p) for p in group.items()]
        self.assert_agreement(facts)
        self.assertEqual({i.code for i in evaluate_html_contract(facts)}, {"DISCOVERY_ID"})

    def test_canonical_and_missing_output(self):
        facts = flat_release()
        routes = sorted(k[1] for k in facts if k[0] == "m")
        facts[("o", routes[0])]["canonical"]["html"] = [routes[-1]]
        facts.pop(("o", routes[1]))
        self.assert_agreement(facts)
        self.assertIn("MISSING_ROUTE", {i.code for i in evaluate_html_contract(facts)})

    def test_explicit_partial_coverage_and_canonical_exception(self):
        facts = flat_release()
        for key, spec in facts.items():
            if key[0] == "m":
                spec["discovery"]["html"]["required"] = [spec["locale"]]
                route = key[1]
                facts[("o", route)]["alternates"]["html"] = [[spec["locale"], route]]
        routes = sorted(k[1] for k in facts if k[0] == "m")
        facts[("o", routes[0])]["canonical"]["html"] = [routes[-1]]
        facts[("m", routes[0])]["canonical_allowed"] = [routes[-1]]
        self.assert_agreement(facts)
        self.assertFalse(evaluate_html_contract(facts))

    def test_literal_missing_language_and_reciprocity(self):
        facts = flat_release()
        route = next(k[1] for k in facts if k[0] == "o")
        facts[("o", route)]["alternates"]["html"] = []
        facts[("o", route)]["lang"] = "fr"
        self.assert_agreement(facts)
        self.assertTrue({"DISCOVERY_MISSING", "LANGUAGE", "RECIPROCITY"} <= {i.code for i in evaluate_html_contract(facts)})

    def test_diagnostics_and_external_targets_remain_ambiguities(self):
        facts = flat_release()
        route = next(k[1] for k in facts if k[0] == "o")
        facts[("o", route)]["diagnostics"] = [["HTML_PROFILE", "Expected literal diagnostic"]]
        external = "https://unmounted.invalid/preferred/"
        facts[("m", route)]["canonical_allowed"] = [external]
        facts[("o", route)]["canonical"]["html"] = [external]
        self.assert_agreement(facts)
        self.assertEqual({i.category for i in evaluate_html_contract(facts)}, {"ambiguity"})

    def test_unsupported_profiles_are_not_silent_passes(self):
        facts = flat_release()
        route = next(k[1] for k in facts if k[0] == "m")
        variants = []
        for field, value in (("fallbacks", {"fr": ["en"]}), ("state", "removed"),
                             ("canonical_channels", ["http"]), ("ambiguous", True)):
            altered = copy.deepcopy(facts)
            altered[("m", route)][field] = value
            variants.append(altered)
        altered = copy.deepcopy(facts)
        altered[("cfg",)]["check_links"] = True
        variants.append(altered)
        altered = copy.deepcopy(facts)
        altered[("o", route)]["redirect"] = route
        variants.append(altered)
        for variant in variants:
            with self.assertRaises(ValueError):
                evaluate_html_contract(variant)


if __name__ == "__main__":
    unittest.main()
