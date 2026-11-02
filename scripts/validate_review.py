#!/usr/bin/env python3
"""Check a model's quoted evidence; every conclusion remains pending review."""
import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from common import digest, strict_json, write_json

DIRECTION = re.compile(r'\b(increas\w*|decreas\w*|reduc\w*|enhanc\w*|higher|lower|larger|smaller|greater|less|more|improv\w*|suppress\w*)\b|提高|增加|降低|减少|更高|更低', re.I)
NO_EFFECT = re.compile(r'\b(does not affect|no effect|unaffected|unchanged|no difference)\b|无效应|不影响|没有差异', re.I)
UNCERTAIN = re.compile(r'\b(similar|not significant|no significant|non.significant)\b|不显著|无显著差异|相似', re.I)
CONTROL = re.compile(r'\b(WT|wild[ -]?type)\b|野生型', re.I)
GROUPS = {'knockout_group_not_in_quote': r'\b(KO|knock[ -]?out|mutants?)\b',
          'overexpression_group_not_in_quote': r'\b(OE|OX|over[ -]?express\w*)\b'}
FIGURE = re.compile(r'\bfig(?:ure)?[. ]*\d|图\s*\d', re.I)
DISTINCT_GENES = re.compile(r'\b(?:different|distinct|separate) genes?\b|不同(?:的)?基因|独立基因', re.I)
ALLELES_OF = re.compile(r'\balleles?\s+(?:of|at|for)\b|同一基因.*等位|等位.*同一基因', re.I)


def normalise_space(value):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', value)).strip()


def quote_match(quote, paragraph):
    if not isinstance(quote, str) or len(quote.strip()) < 8 or not isinstance(paragraph, str):
        return 'missing'
    if quote in paragraph:
        return 'exact'
    q, p = normalise_space(quote), normalise_space(paragraph)
    if q in p:
        return 'whitespace'
    # Preserve the hyphen and all letters/numbers; only spaces adjoining it change.
    clean = lambda s: re.sub(r'(?<=\w)\s*-\s*(?=\w)', '-', s)
    return 'hyphen_spacing' if clean(q) in clean(p) else 'missing'


def risk_flags(ob, evidence_kind=None):
    finding, quote = ob['finding'], ob['quote']
    flags = []
    if DIRECTION.search(finding):
        flags.append('direction_requires_context_review')
        if not DIRECTION.search(quote):
            flags.append('direction_not_explicit_in_quote')
    if NO_EFFECT.search(finding) and UNCERTAIN.search(quote):
        flags.append('non_significance_not_no_effect')
    if CONTROL.search(finding):
        flags.append('generic_control_background_requires_review')
    for flag, pattern in GROUPS.items():
        if re.search(pattern, finding, re.I) and not re.search(pattern, quote, re.I):
            flags.append(flag)
    if FIGURE.search(finding) or evidence_kind == 'figure_caption':
        flags.append('figure_not_verified_by_text_validator')
    if DISTINCT_GENES.search(finding) and ALLELES_OF.search(quote):
        flags.append('gene_identity_relation_conflicts_with_quote')
    if not isinstance(ob.get('comparison'), str) or not ob['comparison'].strip():
        flags.append('comparison_not_structured')
    return flags


def validate_response(response, evidence):
    kinds = {}
    if isinstance(evidence, dict) and isinstance(evidence.get('anchors'), dict):
        mapping = evidence.get('anchor_map', [])
        if not isinstance(mapping, list):
            raise ValueError('anchor_map must be a list')
        for row in mapping:
            if (not isinstance(row, dict) or not isinstance(row.get('anchor'), str)
                    or row['anchor'] not in evidence['anchors'] or row['anchor'] in kinds
                    or not isinstance(row.get('kind'), str)):
                raise ValueError('invalid or duplicate anchor_map entry')
            kinds[row['anchor']] = row['kind']
        evidence = evidence['anchors']
    if not isinstance(evidence, dict) or not all(isinstance(k, str) and k.strip() and isinstance(v, str) for k, v in evidence.items()):
        raise ValueError('Evidence must map nonempty anchor IDs to text')
    result = {'status': 'incomplete_response', 'mechanical_status': 'NOT_RUN',
              'scientific_status': 'PENDING_INDEPENDENT_REVIEW', 'checks': [],
              'scope': 'Quoted text check only; figures, complete article and scientific correctness not assessed'}
    if not isinstance(response, dict) or response.get('done') is not True:
        return result
    reason = response.get('done_reason')
    if reason != 'stop':
        result.update(status='output_truncated' if reason == 'length' else 'abnormal_completion', done_reason=reason)
        return result
    try:
        output = strict_json(response['message']['content'])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        result['status'] = 'invalid_json'
        return result
    if (not isinstance(output, dict) or not isinstance(output.get('gene'), str) or not output['gene'].strip()
            or not isinstance(output.get('observations'), list) or not output['observations']):
        result.update(status='invalid_schema', mechanical_status='FAIL')
        return result
    result['output'] = output
    for index, ob in enumerate(output['observations'], 1):
        if not isinstance(ob, dict) or any(not isinstance(ob.get(k), str) or not ob[k].strip()
                                           for k in ('trait', 'finding', 'anchor', 'quote')):
            result['checks'].append({'observation': index, 'quote_match': 'missing', 'risk_flags': ['invalid_observation_schema']})
            continue
        anchor = ob['anchor']
        match = quote_match(ob['quote'], evidence.get(anchor))
        result['checks'].append({'observation': index, 'anchor': anchor, 'quote_match': match, 'risk_flags': risk_flags(ob, kinds.get(anchor))})
    complete = all(check['quote_match'] != 'missing' for check in result['checks'])
    result.update(status='pending_review' if complete else 'citation_or_schema_failure',
                  mechanical_status='PASS' if complete else 'FAIL')
    return result


def run(response_path, evidence_path, output, retry_of=None):
    response_path, evidence_path, output = Path(response_path), Path(evidence_path), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    try:
        before = {'response': digest(response_path), 'evidence': digest(evidence_path)}
        code_paths = {name: Path(__file__).with_name(name) for name in ('validate_review.py', 'common.py')}
        code_hashes = {name: digest(path) for name, path in code_paths.items()}
        response = strict_json(response_path.read_text(encoding='utf-8'))
        evidence = strict_json(evidence_path.read_text(encoding='utf-8'))
        result = validate_response(response, evidence)
        if before != {'response': digest(response_path), 'evidence': digest(evidence_path)}:
            raise ValueError('Input changed while validating')
        if code_hashes != {name: digest(path) for name, path in code_paths.items()}:
            raise ValueError('Code changed while validating')
        receipt = {'created_at_utc': datetime.now(timezone.utc).isoformat(), 'input_sha256': before,
                   'inputs': {'response': str(response_path.resolve()), 'evidence': str(evidence_path.resolve())},
                   'code_sha256': code_hashes,
                   'python': sys.version.split()[0], 'retry_of': retry_of, 'result': result}
        write_json(output / 'review_receipt.json', receipt)
        return receipt
    except Exception as exc:
        write_json(output / 'failure.json', {'status': 'invalid_input_or_io', 'error_type': type(exc).__name__, 'error': str(exc)})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--response', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True, help='Anchor-to-text JSON or evidence.json with anchors and optional anchor_map')
    parser.add_argument('--out', type=Path, required=True, help='New directory; no existing result is overwritten')
    parser.add_argument('--retry-of', help='Previous attempt identifier; retry always uses a new directory')
    args = parser.parse_args()
    result = run(args.response, args.evidence, args.out, args.retry_of)['result']
    print(json.dumps({'status': result['status'], 'mechanical_status': result['mechanical_status'],
                      'scientific_status': result['scientific_status']}, ensure_ascii=False))
    if result['mechanical_status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
