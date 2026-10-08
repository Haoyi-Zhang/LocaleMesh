import copy, unittest
from localemesh.fixtures import make_site, to_facts
from localemesh.schema import normalize_spec, normalize_config
from localemesh.transaction import ReleaseSession
from localemesh.coalesced import CoalescedIncremental
from localemesh.full import evaluate

class StrictContractTests(unittest.TestCase):
    def test_unknown_policy_keys_do_not_silently_remove_obligations(self):
        base={'key':'x','locale':'en'}
        for typo in ('canoncal_required','sitemp','discovry','fallback'):
            with self.subTest(typo=typo),self.assertRaises(ValueError):normalize_spec({**base,typo:True})
        for typo in ('require','recipocal'):
            with self.subTest(typo=typo),self.assertRaises(ValueError):
                normalize_spec({**base,'discovery':{'html':{typo:['fr']}}})
        for typo in ('check_link','complete_manifst'):
            with self.subTest(typo=typo),self.assertRaises(ValueError):normalize_config({'origins':{},typo:True})

    def test_redirect_without_a_target_is_rejected(self):
        for extra in ({},{'redirect_to':None},{'redirect_allowed':[]}):
            with self.subTest(extra=extra),self.assertRaises(ValueError):
                normalize_spec({'key':'x','locale':'en','state':'redirect',**extra})
        a=normalize_spec({'key':'x','locale':'en','state':'redirect','redirect_to':'https://a.test/'})
        self.assertEqual(a['redirect_to'],'https://a.test/')

    def test_extensions_are_explicit_and_nonsemantic(self):
        a=to_facts(make_site('A1',2));b=copy.deepcopy(a)
        b[('cfg',)]['extensions']={'check_links':False,'note':'metadata only'}
        route=next(k for k in b if k[0]=='m');b[route]['extensions']={'sitemap':False}
        session=ReleaseSession(b,engine_class=CoalescedIncremental)
        self.assertEqual(session.issues(),evaluate(a))
        for obj,fun in [({'origins':{},'extensions':[]},normalize_config),
                        ({'key':'x','locale':'en','extensions':'x'},normalize_spec)]:
            with self.assertRaises(ValueError):fun(obj)

    def test_mixed_valid_invalid_patch_rolls_back_all_records(self):
        a=to_facts(make_site('A1',2));s=ReleaseSession(a,engine_class=CoalescedIncremental)
        k=next(k for k in a if k[0]=='m');o=('o',k[1]);bad=copy.deepcopy(a[k])
        bad['discovery']['html']['require']=['fr']
        with self.assertRaises(ValueError):s.apply({o:None,k:bad})
        self.assertEqual(s.facts(),a);self.assertEqual(s.revision,0)
        self.assertEqual(s.issues(),evaluate(a))

    def test_locale_metadata_type_is_checked(self):
        for val in ('en',True,{},[None]):
            with self.subTest(val=val),self.assertRaises(ValueError):normalize_config({'origins':{},'locales':val})
