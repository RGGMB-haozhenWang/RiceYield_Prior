"""Regression tests for failures observed in supervised literature review."""
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import search_europe_pmc
import validate_review
import verify_review
import acquire_fulltext
import extract_jats_evidence


def response(finding, quote, reason='stop', anchor='xml-1'):
    content = {'gene': 'DEMO1', 'observations': [{'trait': 'grain weight', 'finding': finding,
               'comparison': '', 'anchor': anchor, 'quote': quote}]}
    return {'done': True, 'done_reason': reason, 'message': {'content': json.dumps(content)}}


def xml(doi='10.1234/target', pmcid='PMC123', ref_doi=None):
    reference = f'<ref><article-id pub-id-type="doi">{ref_doi}</article-id></ref>' if ref_doi else ''
    return ('<article><front><article-meta><article-id pub-id-type="doi">' + doi +
            '</article-id><article-id pub-id-type="pmcid">' + pmcid +
            '</article-id></article-meta></front><body><p>' + ('body text ' * 80) +
            '</p>' + reference + '</body></article>').encode()


class ReviewRegressionTests(unittest.TestCase):
    def test_hyphen_spacing_is_normalized_without_dropping_the_hyphen(self):
        result = validate_review.validate_response(response('Observed edits', 'The GS3-edited line was measured'),
            {'xml-1': 'The GS3 -edited line was measured in the experiment.'})
        self.assertEqual(result['mechanical_status'], 'PASS')
        self.assertEqual(result['checks'][0]['quote_match'], 'hyphen_spacing')
        wrong = validate_review.validate_response(response('Observed edits', 'The GS3edited line was measured'),
            {'xml-1': 'The GS3 -edited line was measured in the experiment.'})
        self.assertEqual(wrong['mechanical_status'], 'FAIL')

    def test_citation_match_does_not_establish_direction(self):
        result = validate_review.validate_response(response('Hap2 had higher grain weight', 'Box plots for Hap1 and Hap2'),
            {'xml-1': 'Box plots for Hap1 and Hap2.'})
        self.assertEqual(result['mechanical_status'], 'PASS')
        self.assertIn('direction_not_explicit_in_quote', result['checks'][0]['risk_flags'])
        self.assertEqual(result['scientific_status'], 'PENDING_INDEPENDENT_REVIEW')

    def test_truncated_and_mislocated_results_never_pass(self):
        evidence = {'xml-1': 'Hap1 had higher grain weight than Hap2.'}
        truncated = validate_review.validate_response(response('Hap1 had higher grain weight', 'Hap1 had higher grain weight', reason='length'), evidence)
        self.assertEqual(truncated['status'], 'output_truncated')
        wrong_anchor = validate_review.validate_response(response('Hap1 had higher grain weight', 'Hap1 had higher grain weight', anchor='xml-2'), evidence)
        self.assertEqual(wrong_anchor['mechanical_status'], 'FAIL')
        self.assertEqual(wrong_anchor['scientific_status'], 'PENDING_INDEPENDENT_REVIEW')

    def test_caption_and_allelic_identity_risks_are_retained(self):
        evidence={'anchors':{'xml-1':'DEMO2 and DEMO3 are alleles of DEMO1.'},
                  'anchor_map':[{'anchor':'xml-1','kind':'figure_caption'}]}
        result=validate_review.validate_response(response('DEMO2 and DEMO3 are different genes',
            'DEMO2 and DEMO3 are alleles of DEMO1.'),evidence)
        flags=result['checks'][0]['risk_flags']
        self.assertIn('figure_not_verified_by_text_validator',flags)
        self.assertIn('gene_identity_relation_conflicts_with_quote',flags)
        self.assertEqual(result['scientific_status'],'PENDING_INDEPENDENT_REVIEW')

    def test_significance_and_generic_control_are_flagged(self):
        result = validate_review.validate_response(response('WT was unaffected', 'No significant difference from WT'),
            {'xml-1': 'No significant difference from WT was observed.'})
        flags = result['checks'][0]['risk_flags']
        self.assertIn('non_significance_not_no_effect', flags)
        self.assertIn('generic_control_background_requires_review', flags)

    def test_doi_in_references_is_not_article_identity(self):
        self.assertEqual(acquire_fulltext.validate_jats(xml(), '10.1234/target', 'PMC123')['doi'], '10.1234/target')
        with self.assertRaisesRegex(ValueError, 'doi_mismatch'):
            acquire_fulltext.validate_jats(xml('10.1234/wrong', ref_doi='10.1234/target'), '10.1234/target', 'PMC123')
        with self.assertRaises(ValueError):
            acquire_fulltext.validate_jats(b'<html>captcha</html>', '10.1234/target', 'PMC123')
        with self.assertRaisesRegex(ValueError, 'xml_not_utf8'):
            acquire_fulltext.validate_jats(xml().decode().encode('utf-16'), '10.1234/target', 'PMC123')
        with self.assertRaisesRegex(ValueError, 'entity_declaration'):
            acquire_fulltext.validate_jats(b'<!DOCTYPE article [<!ENTITY x "boom">]><article/>', '10.1234/target', 'PMC123')

    def test_search_access_stop_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'search'
            err = urllib.error.HTTPError('https://example.invalid', 403, 'denied', {}, None)
            with patch.object(search_europe_pmc.urllib.request, 'urlopen', side_effect=err):
                with self.assertRaises(urllib.error.HTTPError):search_europe_pmc.run('example', out)
            manifest = json.loads((out / 'manifest.json').read_text())
            self.assertEqual((manifest['status'], manifest['http_status']), ('access_stop', 403))

    def test_receipt_replay_detects_tampering(self):
        from common import digest
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); model = root / 'response.json'; evidence = root / 'evidence.json'
            model.write_text(json.dumps(response('Measured edits', 'The GS3-edited line was measured')))
            evidence.write_text(json.dumps({'xml-1': 'The GS3 -edited line was measured.'}))
            validate_review.run(model, evidence, root / 'run')
            receipt = root / 'run/review_receipt.json'; expected = digest(receipt)
            self.assertEqual(verify_review.verify(receipt, expected)['scientific_status'], 'PENDING_INDEPENDENT_REVIEW')
            evidence.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'evidence_hash_mismatch'):
                verify_review.verify(receipt, expected)
            receipt.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'receipt_hash_mismatch'):
                verify_review.verify(receipt, expected)

    def test_invalid_json_retains_a_failure_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); model = root / 'bad.json'; evidence = root / 'evidence.json'
            model.write_text('{broken'); evidence.write_text('{}')
            with self.assertRaises(ValueError):validate_review.run(model, evidence, root / 'run')
            self.assertEqual(json.loads((root / 'run/failure.json').read_text())['status'], 'invalid_input_or_io')

    def test_jats_extraction_labels_captions_and_omitted_tables(self):
        raw = ('<article><front><article-meta><article-id pub-id-type="doi">10.1234/target</article-id>'
               '<article-id pub-id-type="pmcid">PMC123</article-id></article-meta></front><body>'
               '<sec><title>Results</title><p>' + ('body text ' * 60) + '</p>'
               '<fig><caption><p>Figure caption with no direction.<inline-graphic>NOT_TEXT</inline-graphic></p></caption><graphic/></fig>'
               '<table-wrap><table><tr><td>42</td></tr></table></table-wrap></sec></body></article>').encode()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'article.xml';source.write_bytes(raw)
            result=extract_jats_evidence.run(source,'10.1234/target','PMC123',root/'run')
            evidence=json.loads((root/'run/evidence.json').read_text())
            self.assertEqual(result['anchor_count'],2)
            self.assertEqual(evidence['coverage'],'selected_paragraphs')
            self.assertEqual(evidence['anchor_map'][1]['kind'],'figure_caption')
            self.assertEqual(evidence['omitted_counts']['table_elements'],1)
            self.assertEqual(evidence['omitted_counts']['graphics'],2)
            self.assertNotIn('NOT_TEXT',' '.join(evidence['anchors'].values()))
            self.assertNotIn('42',' '.join(evidence['anchors'].values()))

    def test_acquisition_respects_stop_before_any_network(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'source.json'
            source.write_text(json.dumps({'doi':'10.1234/target', 'pmcid':'PMC123', 'scope':'eligible',
                                          'access_status':'stopped', 'open_access':True}))
            with patch.object(acquire_fulltext.urllib.request, 'build_opener') as opener:
                receipt = acquire_fulltext.acquire(source, root / 'out')
            opener.assert_not_called()
            self.assertEqual(receipt['status'], 'access_stop')
            self.assertFalse((root / 'out/fulltext.xml').exists())

    def test_duplicate_access_status_cannot_bypass_a_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source.json'
            source.write_text('{"access_status":"stopped","access_status":"allowed","scope":"eligible",'
                              '"open_access":true,"doi":"10.1234/target","pmcid":"PMC123"}')
            with patch.object(acquire_fulltext.urllib.request,'build_opener') as factory:
                rec=acquire_fulltext.acquire(source,root/'run')
                factory.assert_not_called()
            self.assertEqual(rec['status'],'invalid_source')

    def test_acquisition_access_gates_and_partial_failures(self):
        class Reply:
            status = 200
            def __init__(self, data):self.stream = io.BytesIO(data)
            def __enter__(self):return self
            def __exit__(self, *args):return False
            def read(self, n):return self.stream.read(n)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'source.json'
            source.write_text(json.dumps({'doi':'10.1234/target', 'pmcid':'PMC123', 'scope':'eligible',
                                          'access_status':'allowed', 'open_access':True}))
            with patch.object(acquire_fulltext.urllib.request, 'build_opener') as factory:
                op=factory.return_value
                op.open.side_effect=urllib.error.HTTPError('https://example.invalid',429,'rate',{},None)
                limited=acquire_fulltext.acquire(source,root/'limited')
                self.assertEqual(op.open.call_count,1)
                self.assertEqual((limited['status'],limited['http_status']),('access_stop',429))
                op.open.side_effect=None;op.open.return_value=Reply(b'<html>captcha required</html>')
                gate=acquire_fulltext.acquire(source,root/'gate')
                self.assertEqual(gate['status'],'access_stop')
                self.assertTrue((root/'gate/fulltext.xml.partial').exists())
            source.write_text(json.dumps({'access_status':'stopped'}))
            with patch.object(acquire_fulltext.urllib.request,'build_opener') as factory:
                stopped=acquire_fulltext.acquire(source,root/'stopped')
                factory.assert_not_called()
            self.assertEqual(stopped['status'],'access_stop')

    def test_discovery_html_gate_is_not_reported_as_generic_parse_failure(self):
        class Reply:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,n):return b'<html>captcha required</html>'
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'search'
            with patch.object(search_europe_pmc.urllib.request,'urlopen',return_value=Reply()):
                with self.assertRaises(search_europe_pmc.AccessStop):search_europe_pmc.run('example',out)
            self.assertEqual(json.loads((out/'manifest.json').read_text())['status'],'access_stop')

    def test_access_manifest_change_during_download_blocks_acceptance(self):
        class Reply:
            status=200
            def __init__(self,source):self.source=source;self.stream=io.BytesIO(xml())
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,n):
                self.source.write_text(json.dumps({'access_status':'stopped'}))
                return self.stream.read(n)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source.json'
            source.write_text(json.dumps({'doi':'10.1234/target','pmcid':'PMC123','scope':'eligible',
                                          'access_status':'allowed','open_access':True}))
            with patch.object(acquire_fulltext.urllib.request,'build_opener') as factory:
                factory.return_value.open.return_value=Reply(source)
                rec=acquire_fulltext.acquire(source,root/'run')
            self.assertEqual(rec['status'],'source_changed')
            self.assertTrue((root/'run/fulltext.xml.partial').exists())
            self.assertFalse((root/'run/fulltext.xml').exists())

    def test_acquisition_works_with_valid_source_and_preserves_wrong_identity(self):
        class Reply:
            status = 200
            def __init__(self, data):self.stream = io.BytesIO(data)
            def __enter__(self):return self
            def __exit__(self, *args):return False
            def read(self, n):return self.stream.read(n)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); source=root/'source.json'
            source.write_text(json.dumps({'doi':'10.1234/target', 'pmcid':'PMC123', 'scope':'eligible',
                                          'access_status':'allowed', 'open_access':True}))
            with patch.object(acquire_fulltext.urllib.request, 'build_opener') as factory:
                factory.return_value.open.return_value=Reply(xml())
                receipt=acquire_fulltext.acquire(source,root/'ok')
                self.assertEqual(receipt['status'],'valid_fulltext_xml')
                factory.return_value.open.return_value=Reply(xml('10.1234/wrong',ref_doi='10.1234/target'))
                rejected=acquire_fulltext.acquire(source,root/'bad')
            self.assertEqual(rejected['status'],'invalid_asset')
            self.assertTrue((root/'bad/fulltext.xml.partial').exists())
            self.assertFalse((root/'bad/fulltext.xml').exists())


if __name__ == '__main__':
    unittest.main()
