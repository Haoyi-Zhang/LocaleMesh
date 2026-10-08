import copy
import random
import unittest

from localemesh.cases import CASES, change
from localemesh.fixtures import SITES, make_site, to_facts
from localemesh.full import evaluate
from localemesh.model import Issue, delta
from localemesh.sliced import LIVE_SHARDS, SlicedIncremental
from localemesh.transaction import ReleaseSession


class SlicedIncrementalTests(unittest.TestCase):
    def check_invariants(self, engine):
        self.assertEqual(engine.edge_count, sum(len(v) for v in engine.reads.values()))
        self.assertEqual(
            engine.projection_edges,
            sum(len(footprint) for records in engine.reads.values() for _, footprint in records),
        )
        self.assertEqual(engine.reverse_groups, sum(len(groups) for groups in engine.reverse.values()))
        references = {}
        for reader, records in engine.reads.items():
            for fact, footprint in records:
                self.assertIn(reader, engine.reverse[fact][footprint])
                self.assertIs(footprint, engine._pool[footprint][0])
                references[footprint] = references.get(footprint, 0) + 1
        self.assertEqual(references, {key: value[1] for key, value in engine._pool.items()})
        counted = set(engine.issue_counts)
        self.assertEqual(counted, engine.issues())
        self.assertTrue(all(value > 0 for value in engine.issue_counts.values()))

    def test_all_named_transitions_all_configurations(self):
        for site, *_ in SITES:
            clean = to_facts(make_site(site, 3))
            for case, *_ in CASES:
                with self.subTest(site=site, case=case):
                    changed = to_facts(change(make_site(site, 3), case))
                    engine = SlicedIncremental(clean)
                    engine.update(delta(clean, changed))
                    self.assertEqual(engine.issues(), evaluate(changed))
                    self.check_invariants(engine)
                    engine.update(delta(changed, clean))
                    self.assertEqual(engine.issues(), evaluate(clean))
                    self.check_invariants(engine)

    def test_stateful_histories_and_dynamic_shard_sets(self):
        rng = random.Random(20271025)
        for site, *_ in SITES:
            current = to_facts(make_site(site, 4))
            engine = SlicedIncremental(current)
            for step in range(100):
                candidate = to_facts(change(make_site(site, 4), rng.choice(CASES)[0], rng.randrange(3)))
                if step % 4 == 0:
                    candidate[("cfg",)].pop("aliases", None)
                if step % 5 == 0:
                    candidate[("cfg",)]["check_links"] = False
                engine.update(dict(reversed(list(delta(current, candidate).items()))))
                self.assertEqual(engine.issues(), evaluate(candidate), (site, step))
                self.check_invariants(engine)
                current = candidate

    def test_global_policy_rechecks_only_link_slices(self):
        clean = to_facts(make_site("A1", 50))
        changed = copy.deepcopy(clean)
        changed[("cfg",)]["check_links"] = False
        engine = SlicedIncremental(clean)
        stats = engine.update(delta(clean, changed))
        self.assertEqual(engine.issues(), evaluate(changed))
        self.assertEqual(stats["invalidated_owners"], 100)
        self.assertEqual(stats["invalidated_readers"], 100)
        self.assertEqual(stats["invalidated_readers"], stats["invalidated_owners"])

    def test_local_canonical_rechecks_one_slice(self):
        clean = to_facts(make_site("A1", 50))
        changed = to_facts(change(make_site("A1", 50), "wrong_canonical"))
        engine = SlicedIncremental(clean)
        stats = engine.update(delta(clean, changed))
        self.assertEqual(engine.issues(), evaluate(changed))
        self.assertEqual(stats["invalidated_owners"], 1)
        self.assertEqual(stats["invalidated_readers"], 1)

    def test_duplicate_issue_reference_count_across_slices(self):
        clean = to_facts(make_site("A1", 2))
        owner = next(key[1] for key in clean if key[0] == "m")
        external = "https://outside.invalid/same/"
        changed = copy.deepcopy(clean)
        changed[("m", owner)]["canonical_allowed"] = [external]
        changed[("o", owner)]["canonical"]["html"] = [external]
        pairs = changed[("o", owner)]["alternates"]["html"]
        pairs[0][1] = external
        engine = SlicedIncremental(changed)
        duplicate = Issue("ambiguity", "UNMOUNTED_TARGET", owner, "html", external)
        self.assertEqual(engine.issue_counts[duplicate], 2)
        repaired = copy.deepcopy(changed)
        repaired[("m", owner)]["canonical_allowed"] = [owner]
        repaired[("o", owner)]["canonical"]["html"] = [owner]
        engine.update(delta(changed, repaired))
        self.assertEqual(engine.issues(), evaluate(repaired))
        self.assertEqual(engine.issue_counts[duplicate], 1)

    def test_manifest_state_reconciles_obligation_families(self):
        clean = to_facts(make_site("A1", 2))
        owner = next(key[1] for key in clean if key[0] == "m")
        engine = SlicedIncremental(clean)
        self.assertGreater(len(engine._all_reader_ids(owner)), 1)
        redirect = copy.deepcopy(clean)
        redirect[("m", owner)] = {
            "key": redirect[("m", owner)]["key"],
            "locale": redirect[("m", owner)]["locale"],
            "state": "redirect",
            "redirect_to": owner,
            "sitemap": False,
        }
        redirect[("o", owner)]["redirect"] = owner
        redirect.pop(("s", owner), None)
        engine.update(delta(clean, redirect))
        self.assertEqual(engine.issues(), evaluate(redirect))
        self.assertEqual(engine._all_reader_ids(owner), {(owner, "gate")})
        engine.update(delta(redirect, clean))
        self.assertEqual(engine.issues(), evaluate(clean))
        self.assertGreater(len(engine._all_reader_ids(owner)), 1)

    def test_safe_transaction_and_ownership(self):
        clean = to_facts(make_site("A1", 3))
        changed = to_facts(change(make_site("A1", 3), "key_reassigned"))
        session = ReleaseSession(clean, engine_class=SlicedIncremental)
        session.apply({key: value for key, value in delta(clean, changed).items() if key[0] != "g"})
        self.assertEqual(session.issues(), evaluate(changed))
        self.assertEqual(session.facts(), changed)
        before = session.facts()
        with self.assertRaises(ValueError):
            session.apply({("cfg",): {"origins": {}, "check_links": "yes"}})
        self.assertEqual(session.facts(), before)

    def test_delete_every_owner_then_reinsert(self):
        clean = to_facts(make_site("A1", 2))
        empty = {("cfg",): copy.deepcopy(clean[("cfg",)])}
        engine = SlicedIncremental(clean)
        engine.update(delta(clean, empty))
        self.assertEqual(engine.issues(), set())
        self.assertEqual(engine.reads, {})
        self.assertEqual(engine.reverse, {})
        self.assertEqual(engine._pool, {})
        engine.update(delta(empty, clean))
        self.assertEqual(engine.issues(), evaluate(clean))
        self.check_invariants(engine)


if __name__ == "__main__":
    unittest.main()
