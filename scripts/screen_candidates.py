#!/usr/bin/env python3
"""Screen source phenotype annotations using the project's direct/proxy TO rules."""
import argparse
import collections
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import digest, read_csv, write_csv, write_json

INPUT_COLUMNS = ('gene_id', 'symbol', 'phenotype')
RULE_COLUMNS = ('component', 'component_cn', 'relationship', 'trait_ontology_id',
                'expected_trait_label', 'interpretation')
MATCH_COLUMNS = ('source_row', 'gene_id', 'symbol', 'trait_label_in_record', *RULE_COLUMNS,
                 'effective_status', 'review_status')
LEDGER_COLUMNS = ('source_row', 'gene_id', 'symbol', 'phenotype', 'matched_rule_count', 'status')
# Same source notation used in the original RiceData index; source-specific labels are retained.
TRAIT = re.compile(r'([^,]+?)\(TO:(\d{7})\)')


def run(source, rules_path, output):
    source, rules_path, output = Path(source), Path(rules_path), Path(output)
    before = {p.name: digest(p) for p in (source, rules_path)}
    if source.name == rules_path.name:
        raise ValueError('Input and rule files must have distinct names')
    genes = read_csv(source, INPUT_COLUMNS)
    rules = read_csv(rules_path, RULE_COLUMNS)
    by_to = collections.defaultdict(list)
    for rule in rules:
        if rule['relationship'] not in ('direct', 'proxy') or not re.fullmatch(r'TO:\d{7}', rule['trait_ontology_id']):
            raise ValueError('Invalid trait rule')
        by_to[rule['trait_ontology_id']].append(rule)
    matches, ledger = [], []
    for line, row in enumerate(genes, 2):
        seen = set()
        count = 0
        for label, to in TRAIT.findall(row['phenotype']):
            for rule in by_to['TO:' + to]:
                key = (rule['component'], rule['relationship'], rule['trait_ontology_id'])
                if key in seen:
                    continue
                seen.add(key)
                matches.append({'source_row': line, 'gene_id': row['gene_id'], 'symbol': row['symbol'],
                                'trait_label_in_record': label.strip(), **rule,
                                'effective_status': 'unknown' if rule['component'] == 'effective_panicles' else 'not_applicable',
                                'review_status': 'screened_not_causally_verified'})
                count += 1
        ledger.append({'source_row': line, **row, 'matched_rule_count': count,
                       'status': 'matched' if count else 'no_rule_match'})
    if before != {p.name: digest(p) for p in (source, rules_path)}:
        raise ValueError('Input changed during screening')
    output.mkdir(parents=True, exist_ok=False)
    write_csv(output / 'candidate_annotations.csv', MATCH_COLUMNS, matches)
    write_csv(output / 'screening_ledger.csv', LEDGER_COLUMNS, ledger)
    write_json(output / 'manifest.json', {'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'stage': 'candidate_screening_only', 'input_sha256': before,
        'script_sha256': {p.name: digest(p) for p in (Path(__file__), Path(__file__).with_name('common.py'))},
        'python': sys.version.split()[0],
        'input_rows': len(ledger), 'matched_rows': sum(x['status'] == 'matched' for x in ledger),
        'annotation_rows': len(matches), 'outputs': {p: digest(output / p) for p in
            ('candidate_annotations.csv', 'screening_ledger.csv')},
        'limitations': ['No gene identity or causal claim is established', 'Rule nonmatches are retained in the ledger']})
    return len(matches), len(ledger)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--rules', type=Path, default=Path(__file__).resolve().parents[1] / 'config/trait_rules.csv')
    parser.add_argument('--out', type=Path, required=True, help='New directory; never overwrite an earlier run')
    args = parser.parse_args()
    matches, rows = run(args.input, args.rules, args.out)
    print(f'{rows} input rows; {matches} matched annotations; see {args.out}')


if __name__ == '__main__':
    main()
