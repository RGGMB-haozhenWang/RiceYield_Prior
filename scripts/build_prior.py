#!/usr/bin/env python3
"""Build a portable evidence ledger from manually curated CSV tables."""
import argparse
import collections
import csv
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import digest, read_csv, write_csv, write_json

TABLES = {
    'genes': ('gene_id', 'symbol', 'species', 'identity_note'),
    'sources': ('source_id', 'doi', 'title', 'source_version', 'asset_sha256', 'availability', 'scope'),
    'events': ('event_id', 'gene_id', 'origin', 'kind', 'description', 'assembly', 'chromosome', 'position', 'ref', 'alt'),
    'claims': ('claim_id', 'source_id', 'gene_id', 'event_id', 'trait', 'causal_unit', 'comparison',
               'material', 'environment', 'effect', 'unit', 'source_locator', 'evidence_level',
               'review_state', 'independent_review', 'notes'),
    'relations': ('relation_id', 'left_event', 'right_event', 'relation', 'source_id', 'source_locator', 'review_state', 'notes'),
}
LEVELS = {'gene_functional', 'molecular_functional', 'association_only', 'allele_supported', 'event_causal', 'unresolved'}
STATES = {'reviewed', 'pending', 'conflict', 'excluded'}
RELATIONS = {'same_event', 'distinct_event', 'component_of', 'duplicate_representation', 'unresolved'}

DDL = '''
CREATE TABLE genes(gene_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, species TEXT NOT NULL, identity_note TEXT NOT NULL);
CREATE TABLE sources(source_id TEXT PRIMARY KEY, doi TEXT NOT NULL, title TEXT NOT NULL, source_version TEXT NOT NULL,
 asset_sha256 TEXT NOT NULL, availability TEXT NOT NULL, scope TEXT NOT NULL);
CREATE TABLE events(event_id TEXT PRIMARY KEY, gene_id TEXT NOT NULL REFERENCES genes(gene_id), origin TEXT NOT NULL,
 kind TEXT NOT NULL, description TEXT NOT NULL, assembly TEXT NOT NULL, chromosome TEXT NOT NULL,
 position TEXT NOT NULL, ref TEXT NOT NULL, alt TEXT NOT NULL);
CREATE TABLE claims(claim_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id),
 gene_id TEXT NOT NULL REFERENCES genes(gene_id), event_id TEXT REFERENCES events(event_id), trait TEXT NOT NULL,
 causal_unit TEXT NOT NULL, comparison TEXT NOT NULL, material TEXT NOT NULL, environment TEXT NOT NULL,
 effect TEXT NOT NULL, unit TEXT NOT NULL, source_locator TEXT NOT NULL, evidence_level TEXT NOT NULL,
 review_state TEXT NOT NULL, independent_review TEXT NOT NULL, notes TEXT NOT NULL);
CREATE TABLE relations(relation_id TEXT PRIMARY KEY, left_event TEXT NOT NULL REFERENCES events(event_id),
 right_event TEXT NOT NULL REFERENCES events(event_id), relation TEXT NOT NULL,
 source_id TEXT NOT NULL REFERENCES sources(source_id), source_locator TEXT NOT NULL,
 review_state TEXT NOT NULL, notes TEXT NOT NULL);
'''


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(rows):
    indexes = {}
    for table, columns in TABLES.items():
        key = columns[0]
        values = [r[key] for r in rows[table]]
        require(all(v.strip() and v == v.strip() for v in values), f'{table}: IDs must be nonempty and trimmed')
        require(len(values) == len(set(values)), f'{table}: duplicate ID')
        indexes[table] = {r[key]: r for r in rows[table]}
    genes, sources, events = (indexes[t] for t in ('genes', 'sources', 'events'))
    for row in genes.values():
        require(bool(row['symbol'].strip() and row['species'].strip()), 'gene needs symbol and species')
    for row in sources.values():
        require(bool(row['title'].strip()), f"source {row['source_id']}: title is required")
        require(row['scope'] in {'eligible', 'unresolved', 'excluded'}, f"source {row['source_id']}: invalid scope")
        require(not row['asset_sha256'] or bool(re.fullmatch(r'[0-9a-f]{64}', row['asset_sha256'])), 'asset_sha256 must be lowercase SHA-256 or empty')
    for row in events.values():
        require(row['gene_id'] in genes, f"event {row['event_id']}: unknown gene")
        require(row['origin'] in {'natural', 'engineered', 'unknown'}, f"event {row['event_id']}: invalid origin")
        require(row['kind'] in {'snp', 'indel', 'sv', 'cnv', 'complex', 'haplotype', 'other', 'unknown'}, f"event {row['event_id']}: invalid kind")
        require(bool(row['description'].strip()), f"event {row['event_id']}: description is required")
        require(not row['position'] or bool(re.fullmatch(r'[1-9]\d*', row['position'])), f"event {row['event_id']}: position must be a positive integer or empty")
    for row in rows['claims']:
        prefix = f"claim {row['claim_id']}: "
        require(row['gene_id'] in genes and row['source_id'] in sources, prefix + 'unknown gene or source')
        require(row['evidence_level'] in LEVELS and row['review_state'] in STATES, prefix + 'invalid level or review state')
        require(row['independent_review'] in {'pass', 'fail', 'pending', 'not_performed'}, prefix + 'invalid independent review state')
        if row['event_id']:
            require(row['event_id'] in events and events[row['event_id']]['gene_id'] == row['gene_id'], prefix + 'event does not belong to gene')
        if row['evidence_level'] in {'event_causal', 'allele_supported', 'association_only', 'molecular_functional'}:
            require(bool(row['event_id']), prefix + 'this evidence level needs an event')
        if row['evidence_level'] == 'event_causal':
            require(bool(row['causal_unit'].strip() and row['trait'].strip()), prefix + 'event-causal assertion needs causal unit and endpoint')
        if row['review_state'] == 'reviewed':
            require(bool(row['source_locator'].strip() and row['trait'].strip()), prefix + 'reviewed claim needs endpoint and source locator')
    for row in rows['relations']:
        prefix = f"relation {row['relation_id']}: "
        require(row['left_event'] in events and row['right_event'] in events and row['source_id'] in sources, prefix + 'unknown event or source')
        require(row['left_event'] != row['right_event'], prefix + 'self-link')
        require(row['relation'] in RELATIONS and row['review_state'] in STATES, prefix + 'invalid relation or review state')
        if row['review_state'] == 'reviewed':
            require(bool(row['source_locator'].strip()), prefix + 'reviewed relation needs a source locator')
            if row['relation'] == 'same_event':
                require(events[row['left_event']]['gene_id'] == events[row['right_event']]['gene_id'], prefix + 'cross-gene same-event mapping needs manual reconciliation')
    # Only reviewed, eligible same-event edges participate; no identities are merged by this check.
    parent = {event_id: event_id for event_id in events}
    def root(key):
        while parent[key] != key:
            key = parent[key]
        return key
    current = [r for r in rows['relations'] if r['review_state'] == 'reviewed' and sources[r['source_id']]['scope'] == 'eligible']
    for row in current:
        if row['relation'] == 'same_event':
            parent[root(row['left_event'])] = root(row['right_event'])
    for row in current:
        if row['relation'] == 'distinct_event':
            require(root(row['left_event']) != root(row['right_event']), f"relation {row['relation_id']}: distinct events conflict with same-event chain")
    return indexes


def doi_key(value):
    return re.sub(r'^https?://(?:dx\.)?doi\.org/', '', value.strip(), flags=re.I).lower().rstrip('.')


def run(inputs, output):
    inputs, output = Path(inputs), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    try:
        paths = {table: inputs / f'{table}.csv' for table in TABLES}
        before = {name: digest(path) for name, path in paths.items()}
        rows = {table: read_csv(paths[table], columns) for table, columns in TABLES.items()}
        indexes = validate(rows)
        db_path = output / 'prior.sqlite.partial'
        db = sqlite3.connect(db_path)
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.executescript(DDL)
            for table, columns in TABLES.items():
                placeholders = ','.join('?' for _ in columns)
                values = [[None if table == 'claims' and c == 'event_id' and not row[c] else row[c] for c in columns] for row in rows[table]]
                db.executemany(f"INSERT INTO {table} VALUES ({placeholders})", values)
            require(db.execute('PRAGMA foreign_key_check').fetchall() == [], 'foreign key check failed')
            require(db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'SQLite integrity check failed')
            for table in TABLES:
                require(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == len(rows[table]), f'{table}: row count mismatch')
            db.commit()
        finally:
            db.close()
        if before != {name: digest(path) for name, path in paths.items()}:
            raise ValueError('Input changed while building')
        db_path.replace(output / 'prior.sqlite')
        sources, events = indexes['sources'], indexes['events']
        classifications = {name: [] for name in ('natural_causal', 'natural_allele', 'natural_association',
            'molecular_or_engineered', 'functional_gene', 'unresolved', 'excluded_history')}
        fields = (*TABLES['claims'], 'source_scope', 'event_origin')
        for claim in rows['claims']:
            scope = sources[claim['source_id']]['scope']
            origin = events[claim['event_id']]['origin'] if claim['event_id'] else ''
            item = {**claim, 'source_scope': scope, 'event_origin': origin}
            if scope == 'excluded' or claim['review_state'] == 'excluded':
                classifications['excluded_history'].append(item)
                continue
            if scope != 'eligible' or claim['review_state'] != 'reviewed' or claim['independent_review'] in {'fail', 'pending'} or claim['evidence_level'] == 'unresolved':
                classifications['unresolved'].append(item)
                continue
            level = claim['evidence_level']
            if origin == 'natural' and level == 'event_causal': classifications['natural_causal'].append(item)
            if origin == 'natural' and level == 'allele_supported': classifications['natural_allele'].append(item)
            if origin == 'natural' and level == 'association_only': classifications['natural_association'].append(item)
            if origin == 'engineered' or level == 'molecular_functional': classifications['molecular_or_engineered'].append(item)
            if level == 'gene_functional': classifications['functional_gene'].append(item)
            # Reviewed unknown-origin event claims remain visible, but are never labelled natural.
            if origin == 'unknown' and level in {'event_causal', 'allele_supported', 'association_only'}:
                classifications['unresolved'].append(item)
        for name, subset in classifications.items():
            write_csv(output / f'view_{name}.csv', fields, sorted(subset, key=lambda r: r['claim_id']))
        by_doi = collections.defaultdict(list)
        for source in rows['sources']:
            if source['doi'].strip(): by_doi[doi_key(source['doi'])].append(source['source_id'])
        duplicates = [{'normalized_doi': doi, 'source_ids': ' | '.join(sorted(ids))}
                      for doi, ids in sorted(by_doi.items()) if len(ids) > 1]
        write_csv(output / 'possible_duplicate_dois.csv', ('normalized_doi', 'source_ids'), duplicates)
        products = ['prior.sqlite', 'possible_duplicate_dois.csv'] + [f'view_{name}.csv' for name in classifications]
        write_json(output / 'manifest.json', {'schema': 'rice-yield-prior-share-v1',
            'created_at_utc': datetime.now(timezone.utc).isoformat(), 'run_id': output.name,
            'input_sha256': before, 'script_sha256': {p.name: digest(p) for p in (Path(__file__), Path(__file__).with_name('common.py'))},
            'python': sys.version.split()[0], 'sqlite': sqlite3.sqlite_version,
            'row_counts': {t: len(v) for t, v in rows.items()},
            'view_counts': {t: len(v) for t, v in classifications.items()},
            'outputs': {p: digest(output / p) for p in products},
            'checks': ['unique keys', 'foreign keys', 'SQLite integrity', 'reviewed same/distinct relationship contradictions', 'input hashes unchanged'],
            'limitations': ['Evidence levels and review statuses are supplied by curators, not verified by this program',
                            'Views may overlap and must not be summed as independent events']})
        return {t: len(v) for t, v in rows.items()}
    except Exception as exc:
        write_json(output / 'failure.json', {'status': 'failed', 'error_type': type(exc).__name__, 'error': str(exc)})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='New directory; never overwrite an earlier run')
    args = parser.parse_args()
    print(json.dumps(run(args.input_dir, args.out), ensure_ascii=False))


if __name__ == '__main__':
    main()
