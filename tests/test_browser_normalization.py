import unittest
from localemesh.browser import normalize_dom
class BrowserNormalizationTests(unittest.TestCase):
    def raw(self,**changes):
        r={'lang':'en','markers':['x'],'bases':[],'links':[],'anchors':[],'refresh':[],'has_noscript':False}
        r.update(changes);return r
    def test_base_url_and_duplicates(self):
        got=normalize_dom(self.raw(bases=['/new/','/ignored/'],links=[{'rel':'canonical','href':'p/'}]),'https://a.test/old/')
        self.assertEqual(got['canonical']['html'],['https://a.test/new/p/'])
    def test_nonsemantic_links_are_not_errors(self):
        got=normalize_dom(self.raw(links=[{'rel':'icon','href':'data:x'}],anchors=['mailto:x@y','/p/','#x']),'https://a.test/')
        self.assertEqual(got['links'],['https://a.test/p/']);self.assertNotIn('diagnostics',got)
    def test_noscript_and_conflicting_identity_remain_ambiguous(self):
        got=normalize_dom(self.raw(markers=['x','y'],has_noscript=True),'https://a.test/')
        self.assertIsNone(got['key']);self.assertEqual({x[0] for x in got['diagnostics']},{'HTML_PROFILE','CONTENT_MARKER_CONFLICT'})
    def test_malformed_relevant_reference_does_not_disappear(self):
        got=normalize_dom(self.raw(links=[{'rel':'canonical'}]),'https://a.test/')
        self.assertEqual(got['canonical']['html'],[]);self.assertEqual(got['diagnostics'][0][0],'HTML_REFERENCE')
