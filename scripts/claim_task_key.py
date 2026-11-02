#!/usr/bin/env python3
"""Create the existing workflow's stable key for a bounded review question."""
import argparse
import hashlib
import json
import re
from pathlib import Path

FIELDS = ('source_sha256', 'gene_or_event', 'endpoint', 'comparison', 'missing_fields', 'adjudication_version')


def identity_key(identity):
    if set(identity) != set(FIELDS) or any(not isinstance(identity[k], str) or not identity[k].strip() for k in FIELDS):
        raise ValueError('A task needs all six nonempty identity fields')
    if not re.fullmatch(r'[0-9a-f]{64}', identity['source_sha256']):
        raise ValueError('source_sha256 must be a lowercase SHA-256 hex string')
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return 'qtn_claim:' + hashlib.sha256(encoded).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('identity_json', type=Path)
    args = parser.parse_args()
    print(identity_key(json.loads(args.identity_json.read_text(encoding='utf-8'))))


if __name__ == '__main__':
    main()
