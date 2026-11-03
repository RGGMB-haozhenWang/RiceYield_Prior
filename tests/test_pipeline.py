import contextlib
import csv
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_prior
import claim_task_key
import literature_links
import query_prior
import prepare_sources
import screen_candidates
import search_europe_pmc

EXAMPLE = ROOT / 'examples/synthetic'


def table(name):
    with (EXAMPLE / f'{name}.csv').open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def read_rows(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def write_rows(path, rows, fields):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


class PipelineTest(unittest.TestCase):
    def test_screen_preserves_direct_proxy_and_nonmatches(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'screen'
            count, total = screen_candidates.run(EXAMPLE / 'annotations.csv', ROOT / 'config/trait_rules.csv', out)
            self.assertEqual((count, total), (4, 3))
            results = read_rows(out / 'candidate_annotations.csv')
            tier = {(r['trait_ontology_id'], r['relationship']) for r in results}
            self.assertIn(('TO:0000346', 'proxy'), tier)
            self.assertIn(('TO:0000382', 'direct'), tier)
            self.assertTrue(all(r['effective_status'] == 'unknown' for r in results if r['component'] == 'effective_panicles'))
            self.assertEqual(read_rows(out / 'screening_ledger.csv')[-1]['status'], 'no_rule_match')

    def test_build_query_and_view_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'prior'
            self.assertEqual(build_prior.run(EXAMPLE, out)['claims'], 7)
            self.assertEqual([r['claim_id'] for r in read_rows(out / 'view_natural_causal.csv')], ['C7'])
            self.assertEqual([r['claim_id'] for r in read_rows(out / 'view_natural_association.csv')], ['C6'])
            self.assertEqual([r['claim_id'] for r in read_rows(out / 'view_molecular_or_engineered.csv')], ['C3'])
            self.assertEqual([r['claim_id'] for r in read_rows(out / 'view_unresolved.csv')], ['C4'])
            self.assertEqual([r['claim_id'] for r in read_rows(out / 'view_excluded_history.csv')], ['C5'])
            self.assertEqual(len(read_rows(out / 'possible_duplicate_dois.csv')), 1)
            result = query_prior.query(out / 'prior.sqlite', 'DEMO1', 2, 0)
            self.assertEqual(result['total_claims'], 4)
            self.assertEqual(result['next_offset'], 2)
            self.assertEqual(query_prior.query(out / 'prior.sqlite', 'absent', 2, 0)['total_claims'], 0)
            with contextlib.closing(sqlite3.connect(out / 'prior.sqlite')) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(db.execute('SELECT effect FROM claims WHERE claim_id=?', ('C2',)).fetchone()[0], 'no difference reported')
            with self.assertRaises(FileExistsError):
                build_prior.run(EXAMPLE, out)

    def test_query_handles_unicode_in_legacy_server_locale(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inputs = root / 'inputs'
            inputs.mkdir()
            for name, fields in build_prior.TABLES.items():
                rows = table(name)
                if name == 'claims':
                    rows[0]['notes'] = '水稻产量证据'
                write_rows(inputs / f'{name}.csv', rows, fields)
            out = root / 'output'
            build_prior.run(inputs, out)
            env = dict(os.environ, LC_ALL='C', LANG='C', PYTHONUTF8='0', PYTHONCOERCECLOCALE='0')
            command = [sys.executable, str(ROOT / 'scripts/query_prior.py'), '--db', str(out / 'prior.sqlite'),
                       '--gene', 'DEMO1']
            result = subprocess.run(command, cwd=root, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode('ascii', errors='replace'))
            self.assertEqual(json.loads(result.stdout)['claims'][0]['notes'], '水稻产量证据')

    def test_server_cli_from_unicode_path_and_other_working_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'server 数据 with spaces'
            inputs, work = root / '输入', root / '工作目录'
            inputs.mkdir(parents=True)
            work.mkdir()
            for name, fields in build_prior.TABLES.items():
                rows = table(name)
                if name == 'genes':
                    rows[0]['symbol'] = '示例基因1'
                write_rows(inputs / f'{name}.csv', rows, fields)
            env = dict(os.environ, LC_ALL='C', LANG='C', PYTHONUTF8='1')
            screen, output = root / '筛选', root / '数据库'
            commands = [
                ['screen_candidates.py', '--input', str(EXAMPLE / 'annotations.csv'), '--out', str(screen)],
                ['build_prior.py', '--input-dir', str(inputs), '--out', str(output)],
                ['query_prior.py', '--db', str(output / 'prior.sqlite'), '--gene', '示例基因1'],
            ]
            for command in commands:
                result = subprocess.run([sys.executable, str(ROOT / 'scripts' / command[0]), *command[1:]],
                                        cwd=work, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
            self.assertEqual(json.loads(result.stdout)['total_claims'], 4)

    def test_review_conflict_and_event_identity_guards(self):
        rows = {t: table(t) for t in build_prior.TABLES}
        rows['claims'][0]['independent_review'] = 'fail'
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            inputs, output = tmp / 'input', tmp / 'output'
            inputs.mkdir()
            for name, fields in build_prior.TABLES.items():
                write_rows(inputs / f'{name}.csv', rows[name], fields)
            build_prior.run(inputs, output)
            self.assertIn('C1', [r['claim_id'] for r in read_rows(output / 'view_unresolved.csv')])
            self.assertNotIn('C1', [r['claim_id'] for r in read_rows(output / 'view_natural_allele.csv')])
        rows = {t: table(t) for t in build_prior.TABLES}
        rows['relations'].extend([
            {'relation_id': 'R2', 'left_event': 'E1', 'right_event': 'E2', 'relation': 'same_event', 'source_id': 'SRC1', 'source_locator': 'synthetic fig', 'review_state': 'reviewed', 'notes': ''},
            {'relation_id': 'R3', 'left_event': 'E1', 'right_event': 'E2', 'relation': 'distinct_event', 'source_id': 'SRC1', 'source_locator': 'synthetic fig', 'review_state': 'reviewed', 'notes': ''}])
        with self.assertRaisesRegex(ValueError, 'conflict with same-event chain'):
            build_prior.validate(rows)
        rows['relations'][-1]['review_state'] = 'pending'
        build_prior.validate(rows)  # Pending counterevidence stays in the ledger, not silently merged.
        rows['claims'][0]['gene_id'] = 'DEMO_G2'
        with self.assertRaisesRegex(ValueError, 'event does not belong to gene'):
            build_prior.validate(rows)

    def test_failed_build_retains_diagnostic_without_release(self):
        rows = {t: table(t) for t in build_prior.TABLES}
        rows['claims'][-1]['causal_unit'] = ''
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            inputs, output = tmp / 'input', tmp / 'output'
            inputs.mkdir()
            for name, fields in build_prior.TABLES.items():
                write_rows(inputs / f'{name}.csv', rows[name], fields)
            with self.assertRaisesRegex(ValueError, 'causal unit'):
                build_prior.run(inputs, output)
            self.assertEqual(json.loads((output / 'failure.json').read_text())['status'], 'failed')
            self.assertFalse((output / 'prior.sqlite').exists())

    def test_task_key_binds_every_identity_field(self):
        identity = json.loads((EXAMPLE / 'review_task.json').read_text())
        key = claim_task_key.identity_key(identity)
        self.assertEqual(key, claim_task_key.identity_key(dict(reversed(list(identity.items())))))
        self.assertNotEqual(key, claim_task_key.identity_key({**identity, 'endpoint': 'another endpoint'}))
        with self.assertRaises(ValueError):
            claim_task_key.identity_key({**identity, 'source_sha256': 'no-hash'})

    def test_literature_links_are_encoded_and_do_not_claim_availability(self):
        from urllib.parse import parse_qs, unquote, urlsplit
        result = literature_links.links('https://doi.org/10.1234/example%28a%29', '12345', 'pmc12345')
        self.assertEqual(result['identifiers']['doi'], '10.1234/example(a)')
        self.assertEqual(result['identifiers']['pmcid'], 'PMC12345')
        self.assertTrue(all(link['availability'] == 'not_checked' for link in result['links']))
        crossref = next(link['url'] for link in result['links'] if link['source'] == 'Crossref')
        self.assertEqual(unquote(urlsplit(crossref).path), '/works/10.1234/example(a)')
        pubmed = next(link['url'] for link in result['links'] if link['source'] == 'PubMed' and link['role'] == 'search')
        self.assertEqual(parse_qs(urlsplit(pubmed).query)['term'], ['"10.1234/example(a)"[aid]'])
        with self.assertRaises(ValueError): literature_links.links('https://example.org/10.1234/other')
        with self.assertRaises(ValueError): literature_links.links('10.1234/x" OR all')
        with self.assertRaises(ValueError): literature_links.links(pmcid='PMC1/../../')
        with self.assertRaises(ValueError): literature_links.links()

    def test_public_source_link_catalogue_and_identifiers(self):
        from urllib.parse import parse_qs, urlsplit
        result = literature_links.links(doi='10.1234/example', pmid='12345', pmcid='PMC12345')
        by_route = {(link['source'], link['role']): link for link in result['links']}
        expected = {
            ('DOI resolver', 'publisher_or_source_landing_page'): 'doi.org',
            ('Crossref', 'metadata_if_registered'): 'api.crossref.org',
            ('OpenAlex', 'metadata_and_possible_open_access_locations'): 'api.openalex.org',
            ('PubMed', 'search'): 'pubmed.ncbi.nlm.nih.gov',
            ('PubMed', 'record'): 'pubmed.ncbi.nlm.nih.gov',
            ('PubMed Central', 'possible_full_text'): 'pmc.ncbi.nlm.nih.gov',
            ('Europe PMC', 'search'): 'europepmc.org',
            ('Europe PMC', 'possible_full_text'): 'europepmc.org',
        }
        self.assertEqual(len(result['links']), len(expected))
        self.assertEqual(set(by_route), set(expected))
        for route, host in expected.items():
            with self.subTest(route=route):
                parsed = urlsplit(by_route[route]['url'])
                self.assertEqual((parsed.scheme, parsed.hostname), ('https', host))
                self.assertEqual(by_route[route]['availability'], 'not_checked')
        self.assertEqual(urlsplit(by_route['PubMed', 'record']['url']).path, '/12345/')
        self.assertEqual(urlsplit(by_route['PubMed Central', 'possible_full_text']['url']).path,
                         '/articles/PMC12345/')
        self.assertEqual(parse_qs(urlsplit(by_route['Europe PMC', 'search']['url']).query)['query'],
                         ['DOI:"10.1234/example"'])

    def test_metadata_intake_preserves_lineage_and_rejects_tampering(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, size):
                return json.dumps({'hitCount': 2, 'resultList': {'result': [
                    {'id': '1', 'source': 'MED', 'title': 'Synthetic title', 'doi': '10.0000/fake'},
                    {'id': '1', 'source': 'MED', 'title': 'Conflicting title', 'doi': '10.0000/fake'}]}}).encode()
        with tempfile.TemporaryDirectory() as tmp, patch.object(search_europe_pmc.urllib.request, 'urlopen', return_value=Response()):
            tmp = Path(tmp)
            search_europe_pmc.run('synthetic', tmp / 'search', 1, 10)
            self.assertEqual(prepare_sources.run(tmp / 'search', tmp / 'intake'), 1)
            source = read_rows(tmp / 'intake/sources.csv')[0]
            self.assertEqual(source['scope'], 'unresolved')
            self.assertEqual(len(read_rows(tmp / 'intake/source_record_lineage.csv')), 2)
            self.assertEqual(len(read_rows(tmp / 'intake/metadata_conflicts.csv')), 1)
            (tmp / 'search/page_001.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                prepare_sources.run(tmp / 'search', tmp / 'intake2')

    def test_empty_metadata_result(self):
        self.assertEqual(search_europe_pmc.result_records({'hitCount': 0}), [])
        with self.assertRaises(ValueError):
            search_europe_pmc.result_records({'hitCount': 1})

    def test_metadata_pagination_is_not_review(self):
        class Response:
            def __init__(self, data): self.data = data
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, size): return json.dumps(self.data).encode()
        pages = [Response({'hitCount': 3, 'resultList': {'result': [{}, {}]}, 'nextCursorMark': 'next'}),
                 Response({'hitCount': 3, 'resultList': {'result': [{}]}, 'nextCursorMark': 'done'})]
        with tempfile.TemporaryDirectory() as tmp, patch.object(search_europe_pmc.urllib.request, 'urlopen', side_effect=pages), patch.object(search_europe_pmc.time, 'sleep'):
            receipt = search_europe_pmc.run('synthetic query', Path(tmp) / 'search', 2, 2)
            self.assertEqual(receipt['status'], 'reported_hit_count_reached')
            self.assertEqual(receipt['rows_received'], 3)
            self.assertIn('not reviewed', receipt['purpose'])


if __name__ == '__main__':
    unittest.main()
