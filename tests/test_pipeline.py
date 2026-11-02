import contextlib
import csv
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_prior
import claim_task_key
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
