import importlib.util
from pathlib import Path
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('alias_report',ROOT/'scripts/evaluate_alias_report.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class AliasReportTests(unittest.TestCase):
    def observation(self,locale):
        return module.alias_observation('<html><head><link rel="canonical" href="https://example.org/'+locale+'about/">'
            '<meta http-equiv="refresh" content="0; url=https://example.org/'+locale+'about/"></head></html>')
    def test_target_is_checked_against_contract_not_reachability(self):
        self.assertFalse(module.same_information_target_control(self.observation('')))
        self.assertTrue(module.same_information_target_control(self.observation('fr/')))
    def test_missing_redirect_is_not_admitted(self):
        self.assertTrue(module.same_information_target_control({'status':200}))
    def test_toggle_keeps_english_alias_policy_fixed(self):
        for disabled in (False,True):
            self.assertEqual(module.contract(disabled)['schema'],1)
            self.assertEqual(module.contract(disabled)['pages'][module.ORIGIN+'/info/']['redirect_to'],module.ORIGIN+'/about/')
    def test_unreviewed_archive_is_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'source.zip';p.write_bytes(b'not the inspected input')
            with self.assertRaisesRegex(ValueError,'differs'):module.extract_inspected(p,Path(t)/'site')
