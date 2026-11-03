#!/usr/bin/env python3
"""Acquire one prequalified Europe PMC OA XML, or retain a precise failure receipt."""
import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from common import NoRedirect, copy_bounded, digest, strict_json, write_json
from literature_links import normalize_doi

MAX_BYTES = 15_000_000
BASE = 'https://www.ebi.ac.uk/europepmc/webservices/rest/'


def local(tag):
    return tag.rsplit('}', 1)[-1]


def validate_jats(raw, doi, pmcid):
    doi = normalize_doi(doi)
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
        raise ValueError('empty_or_oversized_xml')
    if not re.fullmatch(r'PMC[1-9]\d*', pmcid, re.I):
        raise ValueError('invalid_pmcid')
    # Restrict the parser to UTF-8 so encoded entity declarations cannot bypass this check.
    if b'\x00' in raw:
        raise ValueError('xml_not_utf8')
    try:
        raw.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('xml_not_utf8') from exc
    # External DTDs are not fetched by ElementTree; reject internal entity declarations.
    if b'<!ENTITY' in raw.upper():
        raise ValueError('xml_entity_declaration_not_supported')
    root = ET.fromstring(raw)
    if local(root.tag) != 'article':
        raise ValueError('not_jats_article')
    front = next((x for x in root if local(x.tag) == 'front'), None)
    meta = next((x for x in front if local(x.tag) == 'article-meta'), None) if front is not None else None
    body = next((x for x in root if local(x.tag) == 'body'), None)
    if meta is None or body is None:
        raise ValueError('missing_article_metadata_or_body')
    ids = {}
    for node in meta:
        if local(node.tag) == 'article-id':
            ids.setdefault(node.attrib.get('pub-id-type', '').lower(), set()).add(''.join(node.itertext()).strip().lower())
    if doi.casefold() not in ids.get('doi', set()):
        raise ValueError('doi_mismatch_in_article_metadata')
    pmc_ids = set(ids.get('pmcid', set())) | set(ids.get('pmc', set()))
    pmc_ids = {value if value.startswith('pmc') else 'pmc' + value for value in pmc_ids}
    if pmcid.lower() not in pmc_ids:
        raise ValueError('pmcid_mismatch_in_article_metadata')
    chars = len(''.join(body.itertext()).strip())
    if chars < 500:
        raise ValueError('missing_or_sparse_body')
    return {'doi': doi, 'pmcid': pmcid.upper(), 'body_characters': chars,
            'sha256': hashlib.sha256(raw).hexdigest(), 'identity_scope': 'article-meta IDs and body only'}


def acquire(source_path, output):
    source_path, output = Path(source_path), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    receipt = {'status': 'in_progress', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
               'source_path': str(source_path.resolve()), 'route': 'Europe PMC fullTextXML',
               'attempts': 0, 'max_bytes': MAX_BYTES, 'timeout_seconds': 25,
               'scope': 'transport and article identity only; scientific review not performed'}
    partial = output / 'fulltext.xml.partial'
    start = time.monotonic()
    try:
        source_hash = digest(source_path)
        source = strict_json(source_path.read_text(encoding='utf-8'))
        if not isinstance(source, dict):
            raise ValueError('source_manifest_must_be_object')
        receipt['source_sha256'] = source_hash
        code_paths = {name: Path(__file__).with_name(name) for name in ('acquire_fulltext.py', 'literature_links.py', 'common.py')}
        code_hashes = {name: digest(path) for name, path in code_paths.items()}
        receipt['code_sha256'] = code_hashes
        if source.get('access_status') == 'stopped':
            receipt['status'] = 'access_stop'
        elif source.get('scope') != 'eligible' or source.get('access_status') != 'allowed' or source.get('open_access') is not True:
            receipt['status'] = 'source_not_eligible'
        else:
            if not isinstance(source.get('doi'), str) or not isinstance(source.get('pmcid'), str):
                raise ValueError('doi_and_pmcid_must_be_strings')
            doi = normalize_doi(source['doi'])
            pmcid = source['pmcid'].upper()
            if not re.fullmatch(r'PMC[1-9]\d*', pmcid):
                raise ValueError('invalid_pmcid')
            receipt.update(doi=doi, pmcid=pmcid)
            req = urllib.request.Request(BASE + pmcid + '/fullTextXML',
                headers={'User-Agent': 'RiceYieldPrior/1.0', 'Accept': 'application/xml'})
            if digest(source_path) != source_hash:
                raise ValueError('source_manifest_changed_before_request')
            if code_hashes != {name: digest(path) for name, path in code_paths.items()}:
                raise ValueError('code_changed_before_request')
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            receipt['attempts'] = 1
            with opener.open(req, timeout=25) as response, partial.open('xb') as stream:
                status = getattr(response, 'status', 200)
                receipt['http_status'] = status
                if status != 200:
                    raise urllib.error.HTTPError(req.full_url, status, 'HTTP request failed', {}, None)
                copy_bounded(response, stream, MAX_BYTES, 'response_over_limit')
            raw = partial.read_bytes()
            sample = raw[:4096].lower().lstrip()
            if (sample.startswith(b'<html') or sample.startswith(b'<!doctype html')) and any(
                    marker in sample for marker in (b'captcha', b'cloudflare', b'verify you are human', b'access denied')):
                receipt['status'] = 'access_stop'
            else:
                try:
                    identity = validate_jats(raw, doi, pmcid)
                    if digest(source_path) != source_hash:
                        raise ValueError('source_manifest_changed')
                    if code_hashes != {name: digest(path) for name, path in code_paths.items()}:
                        raise ValueError('code_changed')
                    os.replace(partial, output / 'fulltext.xml')
                    receipt.update(status='valid_fulltext_xml', identity=identity,
                                   asset='fulltext.xml', sha256=identity['sha256'])
                except (ValueError, ET.ParseError) as exc:
                    state = 'source_changed' if str(exc).startswith('source_manifest_changed') else 'code_changed' if str(exc).startswith('code_changed') else 'invalid_asset'
                    receipt.update(status=state, error_type=type(exc).__name__, error=str(exc))
    except urllib.error.HTTPError as exc:
        receipt.update(status='access_stop' if exc.code in (401, 403, 429) else 'redirect_requires_review' if 300 <= exc.code < 400 else 'transport_failed',
                       http_status=exc.code, error_type='HTTPError')
        if exc.fp is not None:
            exc.close()
    except (OSError, TimeoutError) as exc:
        receipt.update(status='transport_failed' if receipt['attempts'] else 'invalid_source',
                       error_type=type(exc).__name__, error=str(exc))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        state = 'source_changed' if str(exc).startswith('source_manifest_changed') else 'code_changed' if str(exc).startswith('code_changed') else 'invalid_asset' if receipt['attempts'] else 'invalid_source'
        receipt.update(status=state, error_type=type(exc).__name__, error=str(exc))
    receipt['elapsed_seconds'] = round(time.monotonic() - start, 3)
    if partial.exists():
        try:
            receipt.update(partial='fulltext.xml.partial', partial_bytes=partial.stat().st_size, partial_sha256=digest(partial))
        except OSError:
            receipt['partial_hash_status'] = 'unavailable'
    write_json(output / 'acquisition_receipt.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Prequalified source JSON; see agent runbook')
    parser.add_argument('--out', type=Path, required=True, help='New directory; one attempt only')
    args = parser.parse_args()
    receipt = acquire(args.source, args.out)
    print(json.dumps({'status': receipt['status'], 'attempts': receipt['attempts']}, ensure_ascii=False))
    if receipt['status'] != 'valid_fulltext_xml':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
