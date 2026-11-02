#!/usr/bin/env python3
"""Recheck a previously recorded review receipt before an agent reuses it."""
import argparse
import json
import re
from pathlib import Path

from common import digest, strict_json
from validate_review import validate_response


def verify(path, expected_sha256):
    path = Path(path)
    if not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
        raise ValueError('Expected receipt SHA-256 must be lowercase hexadecimal')
    if digest(path) != expected_sha256:
        raise ValueError('receipt_hash_mismatch')
    receipt = strict_json(path.read_text(encoding='utf-8'))
    for name in ('response', 'evidence'):
        if digest(receipt['inputs'][name]) != receipt['input_sha256'][name]:
            raise ValueError(name + '_hash_mismatch')
    for name in ('validate_review.py', 'common.py'):
        if digest(Path(__file__).with_name(name)) != receipt['code_sha256'][name]:
            raise ValueError(name + '_hash_mismatch')
    response = strict_json(Path(receipt['inputs']['response']).read_text(encoding='utf-8'))
    evidence = strict_json(Path(receipt['inputs']['evidence']).read_text(encoding='utf-8'))
    current = validate_response(response, evidence)
    if current != receipt['result']:
        raise ValueError('replayed_result_mismatch')
    if digest(path) != expected_sha256:
        raise ValueError('receipt_changed_during_replay')
    for name in ('response', 'evidence'):
        if digest(receipt['inputs'][name]) != receipt['input_sha256'][name]:
            raise ValueError(name + '_changed_during_replay')
    for name in ('validate_review.py', 'common.py'):
        if digest(Path(__file__).with_name(name)) != receipt['code_sha256'][name]:
            raise ValueError(name + '_changed_during_replay')
    return {'status': 'receipt_matches_inputs_and_code', 'receipt_sha256': expected_sha256,
            'mechanical_status': current['mechanical_status'], 'scientific_status': current['scientific_status']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--sha256', required=True, help='Receipt hash recorded independently when produced')
    args = parser.parse_args()
    print(json.dumps(verify(args.receipt, args.sha256), ensure_ascii=False))


if __name__ == '__main__':
    main()
