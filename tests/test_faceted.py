import copy,itertools,random,unittest
from localemesh.fixtures import make_site,to_facts,SITES
from localemesh.cases import CASES,change
from localemesh.model import delta
from localemesh.full import evaluate
from localemesh.incremental import Incremental
from localemesh.faceted import FacetedIncremental
from localemesh.transaction import ReleaseSession

class Faceted(unittest.TestCase):
    def test_named_changes_all_configurations(self):
        for site,*_ in SITES:
            a=to_facts(make_site(site,3))
            for case,_,_ in CASES:
                with self.subTest(site=site,case=case):
                    b=to_facts(change(make_site(site,3),case));e=FacetedIncremental(a)
                    e.update(delta(a,b));self.assertEqual(e.issues(),evaluate(b))
                    self.assertEqual(e.edge_count,sum(map(len,e.reads.values())))
                    e.update(delta(b,a));self.assertEqual(e.issues(),evaluate(a))
    def test_stateful_schema_and_missing_path_edits(self):
        rng=random.Random(8192)
        for site,*_ in SITES:
            current=to_facts(make_site(site,4));e=FacetedIncremental(current)
            for step in range(150):
                candidate=to_facts(change(make_site(site,4),rng.choice(CASES)[0],rng.randrange(3)))
                cfg=candidate[('cfg',)]
                # Include keys absent on the prior read, newly present mappings,
                # empty maps, and changes in iteration-key sets.
                if step%4==0:cfg.pop('aliases',None)
                if step%5==0:cfg['check_links']=False
                e.update(dict(reversed(list(delta(current,candidate).items()))))
                self.assertEqual(e.issues(),evaluate(candidate),(site,step));current=candidate
    def test_deleted_and_added_dependency_paths(self):
        a=to_facts(make_site('A1',2));route=next(k[1] for k in a if k[0]=='o')
        b=copy.deepcopy(a);b[('o',route)]['redirect']='https://a1.test/missing/'
        e=FacetedIncremental(a);e.update(delta(a,b));self.assertEqual(e.issues(),evaluate(b))
        e.update(delta(b,a));self.assertEqual(e.issues(),evaluate(a))
    def test_hub_canonical_change_does_not_invalidate_reachability_readers(self):
        data=make_site('A1',50);hub=next(iter(data[1]))
        for o in data[1].values():o['links']=[hub]
        a=to_facts(data);b=to_facts(change(data,'wrong_canonical'))
        coarse=Incremental(a);fine=FacetedIncremental(a)
        c=coarse.update(delta(a,b));f=fine.update(delta(a,b))
        self.assertEqual(fine.issues(),evaluate(b));self.assertGreater(c['invalidated_owners'],f['invalidated_owners'])
        self.assertEqual(f['invalidated_owners'],1)
    def test_hub_status_change_does_invalidate_reachability_readers(self):
        data=make_site('A1',20);hub=next(iter(data[1]))
        for o in data[1].values():o['links']=[hub]
        a=to_facts(data);b=copy.deepcopy(a);b[('o',hub)]['status']=404
        e=FacetedIncremental(a);stats=e.update(delta(a,b))
        self.assertEqual(e.issues(),evaluate(b));self.assertEqual(stats['invalidated_owners'],40)
    def test_unread_alias_is_not_global_semantic_change(self):
        a=to_facts(make_site('A1',3));b=copy.deepcopy(a)
        b[('cfg',)]['aliases']['https://a1.test/unused/']='https://a1.test/item-0000/'
        e=FacetedIncremental(a);s=e.update(delta(a,b))
        self.assertEqual(s['invalidated_owners'],0);self.assertEqual(e.issues(),evaluate(b))
    def test_previously_absent_alias_invalidates_existing_reader(self):
        data=make_site('A1',3);route=next(iter(data[1]));missing='https://a1.test/alias/'
        data[1][route]['links']=[missing]
        a=to_facts(data);b=copy.deepcopy(a);b[('cfg',)]['aliases'][missing]=route
        good=FacetedIncremental(a);bad=FacetedIncremental(a)
        good.update(delta(a,b));bad.update(delta(a,b),broken_drop_absent=True)
        self.assertEqual(good.issues(),evaluate(b));self.assertNotEqual(bad.issues(),evaluate(b))
    def test_bounded_deletion_lattice(self):
        a=to_facts(make_site('H1',2));keys=[k for k in a if k[0]=='o']
        for flags in itertools.product([False,True],repeat=len(keys)):
            b=copy.deepcopy(a)
            for k,remove in zip(keys,flags):
                if remove:del b[k]
            e=FacetedIncremental(a);e.update(delta(a,b));self.assertEqual(e.issues(),evaluate(b))
    def test_safe_transaction_with_fine_grained_engine(self):
        a=to_facts(make_site('A1',3));b=to_facts(change(make_site('A1',3),'key_reassigned'))
        s=ReleaseSession(a,engine_class=FacetedIncremental)
        s.apply({k:v for k,v in delta(a,b).items() if k[0]!='g'})
        self.assertEqual(s.issues(),evaluate(b));self.assertEqual(s.facts(),b)
