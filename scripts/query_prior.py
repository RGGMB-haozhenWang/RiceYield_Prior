#!/usr/bin/env python3
"""Query a portable prior database by exact gene ID or symbol, without identity merging."""
import argparse
import json
import sqlite3
from pathlib import Path


def query(path, gene, limit, offset):
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError('limit must be 1–100; offset must be nonnegative')
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('Database does not exist')
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        genes = [dict(r) for r in db.execute('SELECT * FROM genes WHERE lower(gene_id)=lower(?) OR lower(symbol)=lower(?) ORDER BY gene_id', (gene, gene))]
        ids = [r['gene_id'] for r in genes]
        if not ids:
            return {'genes': [], 'claims': [], 'events': [], 'total_claims': 0}
        marks = ','.join('?' for _ in ids)
        total = db.execute(f'SELECT count(*) FROM claims WHERE gene_id IN ({marks})', ids).fetchone()[0]
        claims = [dict(r) for r in db.execute(f'''SELECT c.*,s.doi,s.title,s.scope AS source_scope,
            e.origin AS event_origin,e.kind AS event_kind FROM claims c
            JOIN sources s ON c.source_id=s.source_id LEFT JOIN events e ON c.event_id=e.event_id
            WHERE c.gene_id IN ({marks}) ORDER BY c.claim_id LIMIT ? OFFSET ?''', (*ids, limit, offset))]
        events = [dict(r) for r in db.execute(f'SELECT * FROM events WHERE gene_id IN ({marks}) ORDER BY event_id', ids)]
        return {'genes': genes, 'events': events, 'claims': claims, 'total_claims': total,
                'offset': offset, 'next_offset': offset + len(claims) if offset + len(claims) < total else None,
                'scope': 'all states, including excluded history and unresolved; inspect each row'}
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--gene', required=True)
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--offset', type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(query(args.db, args.gene, args.limit, args.offset), indent=2))


if __name__ == '__main__':
    main()
