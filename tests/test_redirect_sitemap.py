import copy
import unittest
from localemesh.cases import change
from localemesh.fixtures import SITES, make_site, to_facts
from localemesh.full import evaluate
from localemesh.incremental import Incremental
from localemesh.faceted import FacetedIncremental
from localemesh.coalesced import CoalescedIncremental
from localemesh.sliced import SlicedIncremental
from localemesh.model import delta


class RedirectSitemapTests(unittest.TestCase):
    def test_explicit_obligation_and_restoration_all_engines(self):
        base = to_facts(change(make_site(SITES[0][0], 1), 'redirect_alias_allowed'))
        route = next(key[1] for key, value in base.items() if key[0] == 'm' and value.get('state') == 'redirect')
        for transport in ('http-fixture', 'html-refresh'):
            for required in (False, True):
                for present in (False, True):
                    facts = copy.deepcopy(base)
                    facts[('m', route)]['sitemap'] = required
                    facts[('o', route)]['redirect_transport'] = transport
                    if present: facts[('s', route)] = []
                    else: facts.pop(('s', route), None)
                    expected = any(i.code == 'SITEMAP_MISSING' and i.owner == route for i in evaluate(facts))
                    self.assertEqual(expected, required and not present)
                    for cls in (Incremental, FacetedIncremental, CoalescedIncremental, SlicedIncremental):
                        engine = cls(facts)
                        self.assertEqual(engine.issues(), evaluate(facts))
                        toggled = copy.deepcopy(facts)
                        if present: toggled.pop(('s', route))
                        else: toggled[('s', route)] = []
                        engine.update(delta(facts, toggled))
                        self.assertEqual(engine.issues(), evaluate(toggled))
                        engine.update(delta(toggled, facts))
                        self.assertEqual(engine.issues(), evaluate(facts))
