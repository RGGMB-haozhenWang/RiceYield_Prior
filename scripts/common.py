"""Small file helpers for a portable prior-curation run."""
import csv
import hashlib
import json
import os
from pathlib import Path


def strict_json(text):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError('Non-finite JSON value: ' + value)
    return json.loads(text, object_pairs_hook=object_pairs, parse_constant=reject_constant)


def digest(path):
    path = Path(path)
    if getattr(path.stat(), 'st_flags', 0) & 0x40000000:
        raise ValueError(f'Input is a cloud placeholder: {path.name}')
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_csv(path, columns):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(columns):
            raise ValueError(f'{Path(path).name}: expected columns {list(columns)}, got {reader.fieldnames}')
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f'{Path(path).name}: malformed row')
    return rows


def atomic_bytes(path, value):
    path = Path(path)
    partial = path.with_name(path.name + '.partial')
    with partial.open('xb') as stream:
        stream.write(value)
    os.replace(partial, path)


def write_json(path, value):
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8'))


def write_csv(path, columns, rows):
    path = Path(path)
    partial = path.with_name(path.name + '.partial')
    with partial.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    os.replace(partial, path)
