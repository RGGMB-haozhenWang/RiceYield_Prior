#!/usr/bin/env python3
"""Construct public literature navigation links from explicitly supplied identifiers."""
import argparse
import json
import re
from urllib.parse import quote, unquote, urlencode, urlsplit


def normalize_doi(value):
    value = value.strip()
    if re.match(r'^https?://', value, re.I):
        parts = urlsplit(value)
        if parts.hostname not in {'doi.org', 'dx.doi.org'} or parts.query or parts.fragment:
            raise ValueError('DOI URL must use doi.org without a query or fragment')
        value = unquote(parts.path.lstrip('/'))
    else:
        value = re.sub(r'^doi:\s*', '', value, flags=re.I)
    if not re.fullmatch(r'10\.\d{4,9}/[^\s"\\]+', value):
        raise ValueError('DOI must include a valid-looking prefix and suffix without spaces or quotes')
    return value


def links(doi=None, pmid=None, pmcid=None):
    if not any((doi, pmid, pmcid)):
        raise ValueError('Provide at least one of DOI, PMID, or PMCID')
    result = []
    ids = {}
    def add(source, role, url):
        result.append({'source': source, 'role': role, 'url': url, 'availability': 'not_checked'})
    if doi:
        doi = normalize_doi(doi)
        ids['doi'] = doi
        encoded = quote(doi, safe='/')
        add('DOI resolver', 'publisher_or_source_landing_page', 'https://doi.org/' + encoded)
        add('Crossref', 'metadata_if_registered', 'https://api.crossref.org/works/' + encoded)
        add('OpenAlex', 'metadata_and_possible_open_access_locations', 'https://api.openalex.org/works/https://doi.org/' + encoded)
        add('PubMed', 'search', 'https://pubmed.ncbi.nlm.nih.gov/?' + urlencode({'term': f'"{doi}"[aid]'}))
        add('Europe PMC', 'search', 'https://europepmc.org/search?' + urlencode({'query': f'DOI:"{doi}"'}))
    if pmid:
        if not re.fullmatch(r'[1-9]\d*', pmid):
            raise ValueError('PMID must be a positive integer')
        ids['pmid'] = pmid
        add('PubMed', 'record', 'https://pubmed.ncbi.nlm.nih.gov/' + pmid + '/')
    if pmcid:
        if not re.fullmatch(r'PMC[1-9]\d*', pmcid, flags=re.I):
            raise ValueError('PMCID must be PMC followed by a positive integer')
        pmcid = pmcid.upper()
        ids['pmcid'] = pmcid
        add('PubMed Central', 'possible_full_text', 'https://pmc.ncbi.nlm.nih.gov/articles/' + pmcid + '/')
        add('Europe PMC', 'possible_full_text', 'https://europepmc.org/articles/' + pmcid)
    return {'identifiers': ids, 'links': result,
            'note': 'Navigation only. Availability, identifier identity, article version and reuse rights were not checked.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--doi')
    parser.add_argument('--pmid')
    parser.add_argument('--pmcid')
    args = parser.parse_args()
    try:
        result = links(args.doi, args.pmid, args.pmcid)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
