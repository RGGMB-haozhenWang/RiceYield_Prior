#!/usr/bin/env python3
"""Turn saved Europe PMC search pages into a traceable, unreviewed source intake."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from build_prior import TABLES
from common import digest, write_csv, write_json
from search_europe_pmc import result_records


def run(search, output):
    search, output = Path(search), Path(output)
    manifest_path = search / 'manifest.json'
    manifest_before = digest(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    pages = manifest.get('pages')
    if not isinstance(pages, list):
        raise ValueError('Search manifest has no page list')
    catalog, lineage, conflicts = {}, [], []
    for page in pages:
        name = page['file']
        if Path(name).name != name:
            raise ValueError('Search page must be a filename in the search directory')
        path = search / name
        if digest(path) != page['sha256']:
            raise ValueError(f'Search page hash mismatch: {name}')
        records = result_records(json.loads(path.read_bytes()))
        if not isinstance(records, list) or len(records) != page['rows']:
            raise ValueError(f'Search page count mismatch: {name}')
        for number, record in enumerate(records, 1):
            source = str(record.get('source') or '').strip()
            identifier = str(record.get('id') or '').strip()
            key = f'epmc:{source}:{identifier}' if source and identifier else f'unresolved:{name}:{number}'
            title = str(record.get('title') or '').strip()
            doi = str(record.get('doi') or '').strip()
            candidate = {'source_id': key, 'doi': doi, 'title': title, 'source_version': '',
                         'asset_sha256': '', 'availability': 'metadata_only', 'scope': 'unresolved'}
            if key in catalog and (catalog[key]['title'] != title or catalog[key]['doi'] != doi):
                conflicts.append({'source_id': key, 'page': name, 'record_number': number,
                                  'first_title': catalog[key]['title'], 'observed_title': title,
                                  'first_doi': catalog[key]['doi'], 'observed_doi': doi})
            catalog.setdefault(key, candidate)
            lineage.append({'source_id': key, 'page': name, 'record_number': number, 'title': title,
                            'doi': doi, 'page_sha256': page['sha256']})
    if digest(manifest_path) != manifest_before:
        raise ValueError('Search manifest changed while reading')
    output.mkdir(parents=True, exist_ok=False)
    write_csv(output / 'sources.csv', TABLES['sources'], sorted(catalog.values(), key=lambda r: r['source_id']))
    write_csv(output / 'source_record_lineage.csv', ('source_id', 'page', 'record_number', 'title', 'doi', 'page_sha256'), lineage)
    write_csv(output / 'metadata_conflicts.csv', ('source_id', 'page', 'record_number', 'first_title', 'observed_title', 'first_doi', 'observed_doi'), conflicts)
    write_json(output / 'manifest.json', {'stage': 'unreviewed_source_intake',
        'created_at_utc': datetime.now(timezone.utc).isoformat(), 'search_manifest_sha256': manifest_before,
        'search_status': manifest.get('status'), 'source_records': len(lineage), 'source_ids': len(catalog), 'metadata_conflicts': len(conflicts),
        'script_sha256': digest(__file__), 'outputs': {name: digest(output / name) for name in ('sources.csv', 'source_record_lineage.csv', 'metadata_conflicts.csv')},
        'limitations': ['Source scope unresolved; no scientific review performed',
                        'Duplicate DOI and conflicting metadata require manual review',
                        'Missing titles must be resolved before building the prior']})
    return len(catalog)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--search-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(f'{run(args.search_dir, args.out)} unreviewed source records')


if __name__ == '__main__':
    main()
