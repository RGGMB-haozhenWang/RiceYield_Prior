#!/usr/bin/env python3
"""Save bounded Europe PMC search pages as unreviewed discovery metadata."""
import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from common import atomic_bytes, digest, write_json

BASE = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search'
MAX_BYTES = 20_000_000


class AccessStop(ValueError):
    pass


def result_records(body):
    result_list = body.get('resultList', {})
    if not isinstance(result_list, dict):
        raise ValueError('unexpected result list')
    records = result_list.get('result')
    if records is None and body.get('hitCount') == 0:
        return []
    if not isinstance(records, list):
        raise ValueError('unexpected result list')
    return records


def run(query, output, max_pages=1, page_size=100):
    if not query.strip() or not 1 <= max_pages <= 20 or not 1 <= page_size <= 1000:
        raise ValueError('A query, max-pages 1–20 and page-size 1–1000 are required')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    receipt = {'query': query, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
               'status': 'partial', 'purpose': 'candidate metadata only; not reviewed evidence', 'pages': [],
               'max_pages': max_pages, 'page_size': page_size, 'script_sha256': digest(__file__)}
    cursor = '*'
    try:
        for page in range(max_pages):
            params = {'query': query, 'format': 'json', 'resultType': 'core', 'pageSize': page_size, 'cursorMark': cursor}
            url = BASE + '?' + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers={'User-Agent': 'RiceYieldPrior/1.0', 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=25) as response:
                raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError('response exceeds 20 MB; no truncated page accepted')
            head = raw[:4096].lower()
            if (head.lstrip().startswith(b'<html') or head.lstrip().startswith(b'<!doctype html')) and any(marker in head for marker in (b'captcha', b'cloudflare', b'verify you are human', b'access denied')):
                raise AccessStop('Human verification or access restriction detected')
            body = json.loads(raw)
            records = result_records(body)
            dest = output / f'page_{page + 1:03}.json'
            atomic_bytes(dest, raw)
            receipt['pages'].append({'file': dest.name, 'sha256': digest(dest), 'bytes': len(raw),
                                     'cursor': cursor, 'rows': len(records), 'hit_count': body.get('hitCount')})
            seen = sum(item['rows'] for item in receipt['pages'])
            count = body.get('hitCount')
            if isinstance(count, int) and seen == count:
                receipt['status'] = 'reported_hit_count_reached'
                break
            next_cursor = body.get('nextCursorMark')
            if not records or not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
            if page + 1 < max_pages:
                time.sleep(1)
        receipt['rows_received'] = sum(item['rows'] for item in receipt['pages'])
        receipt['next_cursor'] = cursor
        write_json(output / 'manifest.json', receipt)
        return receipt
    except urllib.error.HTTPError as exc:
        receipt.update(status='access_stop' if exc.code in (401, 403, 429) else 'failed',
                       error_type='HTTPError', http_status=exc.code)
        write_json(output / 'manifest.json', receipt)
        if exc.fp is not None:
            exc.close()
        raise
    except AccessStop as exc:
        receipt.update(status='access_stop', error_type='AccessStop', error=str(exc))
        write_json(output / 'manifest.json', receipt)
        raise
    except Exception as exc:
        receipt.update(status='failed', error_type=type(exc).__name__, error=str(exc))
        write_json(output / 'manifest.json', receipt)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--query', required=True, help='Europe PMC query; do not include credentials or sensitive material')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--max-pages', type=int, default=1)
    parser.add_argument('--page-size', type=int, default=100)
    args = parser.parse_args()
    receipt = run(args.query, args.out, args.max_pages, args.page_size)
    print(json.dumps({'status': receipt['status'], 'rows_received': receipt['rows_received']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
