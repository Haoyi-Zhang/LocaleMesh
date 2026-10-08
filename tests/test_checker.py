from __future__ import annotations
import copy, itertools, random, tempfile, unittest
from pathlib import Path
from localemesh.fixtures import make_site, to_facts, SITES, write_fixture
from localemesh.cases import CASES, change
from localemesh.full import evaluate
from localemesh.incremental import Incremental
from localemesh.model import snapshot, delta, url
from localemesh.io import load_build, parse_link_headers, PageParser, safe_child
from localemesh.baselines import manifest_presence, joint_output, policy_blind
from localemesh.emitters import json_html, toml_sitemap, csv_headers, polyglot_public

ROOT=Path(__file__).resolve().parents[1]

class Semantics(unittest.TestCase):
    def test_all_named_expected_outcomes(self):
        for row in SITES:
            base=make_site(row[0],size=3)
            f0=to_facts(base)
            self.assertEqual(evaluate(f0),set())
            for name,label,code in CASES:
                with self.subTest(site=row[0],case=name):
                    f=to_facts(change(base,name))
                    out=evaluate(f)
                    if label=='clean':self.assertFalse(out)
                    if label=='ambiguity':self.assertTrue(out);self.assertFalse(any(i.category=='release' for i in out))
                    if code:self.assertIn(code,{i.code for i in out})
                    inc=Incremental(f0);inc.update(delta(f0,f))
                    self.assertEqual(out,inc.issues())
                    self.assertEqual(inc.edge_count,sum(map(len,inc.reads.values())))
                    inc.update(delta(f,f0));self.assertFalse(inc.issues())
    def test_removed_dependencies_are_necessary(self):
        old=to_facts(make_site('A1',3));new=to_facts(change(make_site('A1',3),'removed_stale'))
        good=Incremental(old);bad=Incremental(old)
        good.update(delta(old,new));bad.update(delta(old,new),broken_drop_old=True)
        self.assertEqual(evaluate(new),good.issues())
        self.assertNotEqual(evaluate(new),bad.issues())
    def test_absent_target_becomes_present(self):
        base=make_site('A1',3);after=change(base,'removed_stale')
        f0=to_facts(after);f1=to_facts(base)
        inc=Incremental(f0);inc.update(delta(f0,f1));self.assertFalse(inc.issues())
    def test_collision_bucket_addition(self):
        a=to_facts(make_site('A2',3));b=to_facts(change(make_site('A2',3),'identity_collision'))
        inc=Incremental(a);inc.update(delta(a,b));self.assertEqual(evaluate(b),inc.issues())
    def test_delta_order_atomicity(self):
        a=to_facts(make_site('H2',3));b=to_facts(change(make_site('H2',3),'prefix_stale'))
        d=delta(a,b);inc=Incremental(a)
        inc.update(dict(reversed(list(d.items()))))
        self.assertEqual(evaluate(b),inc.issues())
    def test_no_change(self):
        a=to_facts(make_site('N2',3));b=to_facts(change(make_site('N2',3),'identical_rebuild'))
        self.assertEqual(delta(a,b),{})
        inc=Incremental(a);stats=inc.update({});self.assertEqual(stats['invalidated_owners'],0)
    def test_global_config_change(self):
        a=to_facts(make_site('A1',3));b=copy.deepcopy(a)
        b[('cfg',)]['origins']={}
        inc=Incremental(a);inc.update(delta(a,b));self.assertEqual(evaluate(b),inc.issues())
    def test_optional_channels_and_xdefault(self):
        for name in ['no_optional_channels','optional_xdefault']:
            self.assertFalse(evaluate(to_facts(change(make_site('A1',3),name))))
    def test_reference_boundaries_are_observable(self):
        base=make_site('A1',3)
        swapped=to_facts(change(base,'coherent_identity_swap'))
        self.assertTrue(any(i.code=='DISCOVERY_ID' for i in evaluate(swapped)))
        self.assertFalse(manifest_presence(swapped))
        self.assertFalse(joint_output(swapped))
        partial=to_facts(change(base,'partial_coverage'))
        self.assertFalse(evaluate(partial))
        self.assertTrue(policy_blind(partial))

    def test_separate_local_emitters_build_cleanly(self):
        families=[('json_html',json_html.build,'html'),('toml_sitemap',toml_sitemap.build,'sitemap'),
                  ('csv_headers',csv_headers.build,'http'),
                  ('polyglot_public',polyglot_public.build,'html')]
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            for name,builder,channel in families:
                with self.subTest(family=name):
                    source=ROOT/'independent_sources'/name;dest=tmp/name
                    builder(source,dest)
                    manifest=source/'contract.json';facts=load_build(manifest,dest)
                    self.assertFalse(evaluate(facts))
                    configured={ch for k,spec in facts.items() if k[0]=='m'
                                for ch in spec.get('discovery',{})}
                    self.assertEqual(configured,{channel})

    def test_parser_roundtrip_every_case(self):
        # Actual disk HTML/XML/header fixtures, not direct generated fact equality only.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for row in SITES:
                for name,label,_ in CASES:
                    with self.subTest(site=row[0],case=name):
                        data=change(make_site(row[0],3),name)
                        write_fixture(root/'case',*data)
                        direct=evaluate(to_facts(data))
                        loaded=evaluate(load_build(root/'case/manifest.json',root/'case/build'))
                        self.assertEqual(direct,loaded)

class ParserTests(unittest.TestCase):
    def test_header_comma_and_multiple_rel(self):
        alt,can=parse_link_headers(['<https://x.test/a,b/>; rel="alternate canonical"; hreflang="en"; title="a,b"'], 'https://x.test/')
        self.assertEqual(alt,[['en','https://x.test/a,b/']]);self.assertEqual(can,['https://x.test/a,b/'])
    def test_relative_url_and_fragment(self):
        self.assertEqual(url('../b/#x','https://x.test/a/c/'),'https://x.test/a/b/')
    def test_alias_not_path_normalization(self):
        self.assertNotEqual(url('https://x.test/a/'),url('https://x.test/a'))
        self.assertNotEqual(url('https://x.test/A/'),url('https://x.test/a/'))
    def test_bad_url(self):
        for s in ['file:///etc/passwd','javascript:alert(1)','https://u:p@x.test/']:
            with self.assertRaises(ValueError):url(s)
    def test_head_only(self):
        p=PageParser('https://x.test/')
        p.feed('<html lang="en"><head></head><body><link rel="alternate" hreflang="de" href="/de/"></body></html>')
        self.assertFalse(p.obs['alternates']['html'])
    def test_mount_escape(self):
        with self.assertRaises(ValueError):safe_child(Path('/tmp/site'),'../secrets')
    def test_header_malformed(self):
        with self.assertRaises(ValueError):parse_link_headers(['not-a-link'],'https://x.test/')

class Differential(unittest.TestCase):
    def test_exhaustive_observation_deletions(self):
        base=make_site('H1',size=2);a=to_facts(base);routes=sorted(base[1])
        for flags in itertools.product([False,True],repeat=len(routes)):
            b=copy.deepcopy(a)
            for r,remove in zip(routes,flags):
                if remove:b.pop(('o',r))
            inc=Incremental(a);inc.update(delta(a,b))
            self.assertEqual(evaluate(b),inc.issues())
    def test_random_stateful_transactions_all_configurations(self):
        rng=random.Random(314159);available=[c[0] for c in CASES]
        for site,*_ in SITES:
            f=to_facts(make_site(site,size=5));inc=Incremental(f)
            for step in range(100):
                new=to_facts(change(make_site(site,5),rng.choice(available),rng.randrange(4)))
                d=list(delta(f,new).items());rng.shuffle(d)
                inc.update(dict(d));self.assertEqual(evaluate(new),inc.issues(),(site,step));f=new

if __name__=='__main__':unittest.main(verbosity=2)
