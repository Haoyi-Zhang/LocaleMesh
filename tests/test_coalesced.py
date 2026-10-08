import copy, random, unittest
from localemesh.fixtures import make_site, to_facts, SITES
from localemesh.cases import CASES, change
from localemesh.full import evaluate
from localemesh.model import delta
from localemesh.faceted import FacetedIncremental
from localemesh.coalesced import CoalescedIncremental
from localemesh.transaction import ReleaseSession


class CoalescedTests(unittest.TestCase):
    def check_invariants(self, e, fine=None):
        self.assertEqual(e.edge_count, sum(len(v) for v in e.reads.values()))
        self.assertEqual(e.projection_edges, sum(len(fp) for d in e.reads.values() for fp in d.values()))
        self.assertEqual(e.reverse_groups, sum(len(v) for v in e.reverse.values()))
        counts = {}
        for owner, record in e.reads.items():
            for fact, footprint in record.items():
                self.assertIn(owner, e.reverse[fact][footprint])
                self.assertIs(footprint, e._pool[footprint][0])
                counts[footprint] = counts.get(footprint, 0) + 1
            if fine is not None:
                self.assertEqual(e.expanded_reads(owner), fine.reads[owner])
        self.assertEqual(counts, {k: v[1] for k, v in e._pool.items()})

    def test_named_transitions_and_exact_expanded_traces(self):
        for name, *_ in SITES:
            a = to_facts(make_site(name, 3)); e=CoalescedIncremental(a); f=FacetedIncremental(a)
            for case, *_ in CASES:
                b = to_facts(change(make_site(name, 3), case))
                e.update(delta(a,b)); f.update(delta(a,b))
                self.assertEqual(e.issues(), evaluate(b), (name,case))
                self.check_invariants(e, f)
                e.update(delta(b,a));f.update(delta(b,a))
                self.assertEqual(e.issues(),evaluate(a))
                self.check_invariants(e, f)

    def test_stateful_histories_include_absent_maps(self):
        rng=random.Random(40107)
        for name,*_ in SITES:
            a=to_facts(make_site(name,4)); e=CoalescedIncremental(a); f=FacetedIncremental(a)
            for i in range(100):
                b=to_facts(change(make_site(name,4),rng.choice(CASES)[0],rng.randrange(3)))
                if i%3==0: b[('cfg',)].pop('aliases',None)
                if i%5==0: b[('cfg',)]['check_links']=False
                patch=dict(reversed(list(delta(a,b).items())))
                e.update(patch);f.update(patch)
                self.assertEqual(e.issues(),evaluate(b),(name,i))
                self.check_invariants(e, f);a=b

    def test_no_dead_footprints_after_repeated_distinct_keys(self):
        a=to_facts(make_site('A1',2)); e=CoalescedIncremental(a)
        for i in range(150):
            b=copy.deepcopy(a);b[('cfg',)]['aliases']={'https://a1.test/new'+str(i)+'/':'https://a1.test/item-0000/'}
            e.update(delta(a,b));e.update(delta(b,a));self.check_invariants(e)
        fresh=CoalescedIncremental(a)
        self.assertEqual(set(e._pool),set(fresh._pool))
        self.assertEqual(e.reverse_groups,fresh.reverse_groups)

    def test_ownership_and_transaction_rollback(self):
        a=to_facts(make_site('A1',2));session=ReleaseSession(a,engine_class=CoalescedIncremental)
        a[('cfg',)]['check_links']=False
        self.assertTrue(session.facts()[('cfg',)]['check_links'])
        before=session.facts()
        with self.assertRaises(ValueError):session.apply({('cfg',):{'origins':{},'check_links':'yes'}})
        self.assertEqual(before,session.facts());self.assertEqual(session.revision,0)

    def test_delete_every_owner_then_reinsert(self):
        a=to_facts(make_site('A1',2)); e=CoalescedIncremental(a)
        b={('cfg',):copy.deepcopy(a[('cfg',)])}
        e.update(delta(a,b));self.assertEqual(e.issues(),set())
        self.assertEqual(e.edge_count,0);self.assertEqual(e.reverse_groups,0);self.assertEqual(e._pool,{})
        e.update(delta(b,a));self.assertEqual(e.issues(),evaluate(a));self.check_invariants(e)

    def test_hub_field_selectivity_is_preserved(self):
        data=make_site('A1',30);hub=next(iter(data[1]))
        for o in data[1].values():o['links']=[hub]
        a=to_facts(data);b=to_facts(change(data,'wrong_canonical'))
        e=CoalescedIncremental(a);f=FacetedIncremental(a)
        es=e.update(delta(a,b));fs=f.update(delta(a,b))
        self.assertEqual(es['invalidated_owners'],1)
        self.assertEqual(es['invalidated_owners'],fs['invalidated_owners'])
        self.assertEqual(e.issues(),evaluate(b));self.check_invariants(e,f)
