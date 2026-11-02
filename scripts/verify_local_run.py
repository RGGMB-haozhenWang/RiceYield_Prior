#!/usr/bin/env python3
"""Verify a local model run and its validation receipt for agent handoff."""
import argparse
import json
import re
from pathlib import Path

from common import digest, strict_json
from verify_review import verify as verify_validation


def verify(path, expected_sha256):
    path = Path(path)
    if not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
        raise ValueError('expected_receipt_hash_invalid')
    if digest(path) != expected_sha256:
        raise ValueError('receipt_hash_mismatch')
    rec = strict_json(path.read_text(encoding='utf-8'))
    for name in ('task', 'evidence', 'asset'):
        if digest(rec['input_paths'][name]) != rec['input_sha256'][name]:
            raise ValueError(name + '_hash_mismatch')
    for name, expected in rec['code_sha256'].items():
        if name not in ('local_model_review.py', 'validate_review.py', 'verify_local_run.py', 'verify_review.py', 'common.py'):
            raise ValueError('unexpected_code_key')
        if digest(Path(__file__).with_name(name)) != expected:
            raise ValueError(name + '_hash_mismatch')
    if set(rec['code_sha256']) != {'local_model_review.py', 'validate_review.py', 'verify_local_run.py', 'verify_review.py', 'common.py'}:
        raise ValueError('code_bindings_incomplete')
    run = path.parent
    for field, filename in (('request_sha256', 'request.json'), ('response_sha256', 'response.raw'),
                            ('partial_sha256', 'response.raw.partial')):
        if field in rec and digest(run / filename) != rec[field]:
            raise ValueError(filename + '_hash_mismatch')
    if 'validation_receipt_sha256' in rec:
        if not {'request_sha256', 'response_sha256'} <= set(rec):
            raise ValueError('completed_attempt_bindings_incomplete')
        validation_path = run / 'validation/review_receipt.json'
        validation = verify_validation(validation_path, rec['validation_receipt_sha256'])
        content = strict_json(validation_path.read_text(encoding='utf-8'))
        if digest(validation_path) != rec['validation_receipt_sha256']:
            raise ValueError('validation_receipt_changed')
        if content['result'] != rec.get('result') or rec['status'] != content['result']['status']:
            raise ValueError('model_and_validation_results_differ')
        if validation['scientific_status'] != 'PENDING_INDEPENDENT_REVIEW':
            raise ValueError('unexpected_scientific_status')
    elif rec['status'] == 'pending_review':
        raise ValueError('validation_receipt_missing')
    if digest(path) != expected_sha256:
        raise ValueError('receipt_changed_during_verification')
    for name in ('task', 'evidence', 'asset'):
        if digest(rec['input_paths'][name]) != rec['input_sha256'][name]:
            raise ValueError(name + '_changed_during_verification')
    for name, expected in rec['code_sha256'].items():
        if digest(Path(__file__).with_name(name)) != expected:
            raise ValueError(name + '_changed_during_verification')
    return {'status': 'recorded_files_match', 'attempt_status': rec['status'],
            'scientific_status': 'PENDING_INDEPENDENT_REVIEW',
            'reuse_decision': 'REUSE_CANDIDATE_ONLY' if rec['status'] == 'pending_review' else 'DO_NOT_REUSE_AS_SUCCESS',
            'limitation': 'Historical model identity was service-reported; current model and source eligibility were not reverified'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--sha256', required=True, help='Receipt hash recorded independently at handoff')
    args = parser.parse_args()
    print(json.dumps(verify(args.receipt, args.sha256), ensure_ascii=False))


if __name__ == '__main__':
    main()
