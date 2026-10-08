"""Literal expected facts, independent of the site/perturbation generators."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from localemesh.io import PageParser, parse_link_headers, load_build, read_json
from localemesh.full import evaluate
from localemesh.incremental import Incremental
from localemesh.transaction import ReleaseSession
from localemesh.model import snapshot, delta
from localemesh.fixtures import make_site, to_facts
from localemesh.cases import change

BASE = 'https://demo.test/page/'

def html(head='', body='', *, before=''):
    p = PageParser(BASE)
    p.feed('<html lang="en"><head>' + before + head + '</head><body data-content-key="x">' + body + '</body></html>')
    p.close()
    return p.obs

class Ingestion(unittest.TestCase):
    def test_noscript_is_a_diagnostic_boundary(self):
        o = html('<noscript><link rel=canonical href="/fallback/"></noscript><link rel=canonical href="/page/">')
        self.assertEqual(o['canonical']['html'], [BASE])
        self.assertEqual(o['diagnostics'], [['HTML_PROFILE', 'noscript requires an explicit scripting-mode contract']])
        facts = snapshot({'config': {'origins': {'https://demo.test': 'main'}},
                          'pages': {BASE: {'key': 'x', 'locale': 'en'}}}, {BASE: o})
        self.assertTrue(any(issue.category == 'ambiguity' for issue in evaluate(facts)))

    def test_schema_version_and_extension_types_are_rejected(self):
        from localemesh.schema import normalize_manifest, normalize_config
        for schema in (True, 1.0, "1", None):
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                normalize_manifest({'schema':schema,'config':{'origins':{}},'pages':{}})
        for extension in ([], {}, True, None):
            with self.subTest(extension=extension), self.assertRaises(ValueError):
                normalize_config({'origins':{},'html_extension':extension})

    def test_base_first_href_even_after_link(self):
        for head in ['<base href="/new/"><link rel=canonical href="page/">',
                     '<link rel=canonical href="page/"><base href="/new/">',
                     '<base target="_blank"><base href="/new/"><base href="/wrong/"><link rel=canonical href="page/">']:
            with self.subTest(head=head):
                self.assertEqual(html(head)['canonical']['html'], ['https://demo.test/new/page/'])
    def test_inactive_markers_and_links(self):
        for tag in ('template', 'noscript', 'title'):
            o=html(f'<{tag}><link rel=canonical href="/wrong/" data-content-key="bad"></{tag}><link rel=canonical href="/page/">')
            self.assertEqual(o['canonical']['html'],[BASE]); self.assertEqual(o['key'],'x')
        o=html('<template/><link rel=canonical href="/wrong/"></template><link rel=canonical href="/page/">')
        self.assertEqual(o['canonical']['html'], [BASE])
    def test_foreign_content_and_head_recovery_are_not_certified(self):
        for head in ('<svg><link rel=canonical href="/page/"></svg>', '<div></div><link rel=canonical href="/page/">', 'text<link rel=canonical href="/page/">'):
            self.assertIn('HTML_PROFILE', {x[0] for x in html(head)['diagnostics']})
        self.assertFalse(html('<script>var x="<link>";</script><style>p {display:none}</style>').get('diagnostics'))
    def test_duplicate_attribute_first_wins(self):
        self.assertEqual(html('<link rel="canonical" href="/page/" HREF="/wrong/">')['canonical']['html'],[BASE])
    def test_conflicting_content_markers_do_not_overwrite(self):
        o=html(body='<article data-content-key="other"></article>')
        self.assertIsNone(o['key']); self.assertIn('CONTENT_MARKER_CONFLICT',{x[0] for x in o['diagnostics']})
        facts=snapshot({'config':{'origins':{'https://demo.test':'main'}},'pages':{BASE:{'key':'x','locale':'en'}}},{BASE:o})
        self.assertTrue(any(i.category=='ambiguity' for i in evaluate(facts)))
        self.assertEqual(Incremental(facts).issues(),evaluate(facts))
    def test_irrelevant_nonweb_links(self):
        o=html('<link rel=icon href="data:image/png;base64,AA==">', '<a href="MAILTO:a@example.test">mail</a>')
        self.assertFalse(o.get('diagnostics')); self.assertFalse(o['links'])
    def test_unsupported_relevant_reference_does_not_pass(self):
        o=html('<link rel=canonical href="javascript:void(0)">')
        self.assertIn('HTML_REFERENCE',{x[0] for x in o['diagnostics']})
    def test_anchor_context_not_default(self):
        for anchor in ('/other/','/page/'):
            a,c=parse_link_headers([f'<../fr/>; rel="alternate canonical"; hreflang=fr; anchor="{anchor}"'],BASE)
            self.assertEqual((a,c),([],[]))
    def test_multiple_language_parameters_are_preserved(self):
        a,c=parse_link_headers(['<../en/>; rel=alternate; hreflang=en; hreflang=en-GB'],BASE)
        self.assertEqual(a,[['en','https://demo.test/en/'],['en-gb','https://demo.test/en/']])
    def test_first_relation_parameter_wins(self):
        a,c=parse_link_headers(['<../fr/>; rel=alternate; rel=canonical; hreflang=fr'],BASE)
        self.assertEqual(a,[['fr','https://demo.test/fr/']]); self.assertEqual(c,[])
    def test_quoted_delimiters_and_escaped_quote(self):
        a,c=parse_link_headers(['<../fr/>; title="a,;\\\"b"; ext; rel="alternate canonical"; hreflang="fr"'],BASE)
        self.assertEqual(a,[['fr','https://demo.test/fr/']]); self.assertEqual(c,['https://demo.test/fr/'])
    def test_header_parse_errors_are_not_silently_skipped(self):
        for value in ['<../fr/>; rel="alternate', '<../fr/>; rel=alternate garbage', '<../fr/; rel=alternate',
                      '<../fr/>; rel=alternate; hreflang=fr, garbage']:
            with self.subTest(value=value), self.assertRaises(ValueError):parse_link_headers([value],BASE)
    def test_duplicate_json_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json';p.write_text('{"state":"draft","state":"published"}')
            with self.assertRaises(ValueError):read_json(p)
    def test_all_local_file_types_obey_mount(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);build=root/'build';(build/'main').mkdir(parents=True)
            manifest={'schema':1,'config':{'origins':{'https://demo.test':'main'}},'pages':{}}
            m=root/'manifest.json';m.write_text(json.dumps(manifest))
            for name,content in [('outside.html','<html><head></head></html>'),('outside.xml','<urlset/>'),('headers','{}')]:
                p=root/name;p.write_text(content)
                link=build/'_headers.json' if name=='headers' else build/'main'/name
                link.symlink_to(p)
                with self.subTest(name=name), self.assertRaises(ValueError):load_build(m,build)
                link.unlink()
    def test_status_location_not_always_redirect(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'main').mkdir();(root/'main/index.html').write_text('<html lang=en><head></head><body></body></html>')
            m=root/'m.json';m.write_text(json.dumps({'schema':1,'config':{'origins':{'https://demo.test':'main'}},'pages':{}}))
            h=root/'_headers.json'
            h.write_text(json.dumps({'https://demo.test/':{'status':201,'location':'/created/'}}))
            self.assertNotIn('redirect',load_build(m,root)[('o','https://demo.test/')])
    def test_normalized_manifest_duplicates_and_bad_state(self):
        from localemesh.schema import normalize_manifest
        m={'schema':1,'config':{'origins':{'https://demo.test':'main'}},'pages':{BASE:{'key':'x','locale':'en'}}}
        bad=copy.deepcopy(m);bad['pages'][BASE]['state']='publshed'
        with self.assertRaises(ValueError):normalize_manifest(bad)
        bad=copy.deepcopy(m);bad['pages']['https://DEMO.test/page/']=bad['pages'][BASE]
        with self.assertRaises(ValueError):normalize_manifest(bad)

class Transaction(unittest.TestCase):
    def test_constructor_and_delta_are_owned(self):
        a=to_facts(make_site('A1',2));engine=Incremental(a)
        key=next(k for k in a if k[0]=='o');a[key]['lang']='wrong'
        self.assertFalse(engine.issues());self.assertNotEqual(a[key],engine.facts[key])
        d={key:copy.deepcopy(a[key])};engine.update(d);expected=engine.issues()
        d[key]['lang']='en';exposed=engine.facts;exposed[key]['lang']='en'
        self.assertEqual(expected,engine.issues());self.assertEqual(engine.facts[key]['lang'],'wrong')
    def test_session_derives_collision_bucket_without_g_delta(self):
        a=to_facts(make_site('A1',3));b=to_facts(change(make_site('A1',3),'identity_collision'))
        session=ReleaseSession(a);d={k:v for k,v in delta(a,b).items() if k[0]!='g'}
        session.apply(d);self.assertEqual(session.issues(),evaluate(b))
        session.apply({k:v for k,v in delta(b,a).items() if k[0]!='g'})
        self.assertFalse(session.issues())
    def test_invalid_transaction_is_atomic(self):
        a=to_facts(make_site('A1',2));session=ReleaseSession(a);key=next(k for k in a if k[0]=='o')
        bad=copy.deepcopy(a[key]);bad['status']='ok'
        with self.assertRaises(ValueError):session.apply({key:bad,('m',key[1]):None})
        self.assertEqual(session.facts(),a);self.assertEqual(session.revision,0)
        with self.assertRaises(ValueError):session.apply({('g','key','en'):()})
    def test_session_all_named_changes(self):
        from localemesh.cases import CASES
        for case,_,_ in CASES:
            a=to_facts(make_site('H2',3));b=to_facts(change(make_site('H2',3),case))
            session=ReleaseSession(a);session.apply({k:v for k,v in delta(a,b).items() if k[0]!='g'})
            self.assertEqual(session.issues(),evaluate(b),case)
