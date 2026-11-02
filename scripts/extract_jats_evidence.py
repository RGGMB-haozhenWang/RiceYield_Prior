#!/usr/bin/env python3
"""Extract anchored JATS body paragraphs and captions for bounded model review."""
import argparse
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from acquire_fulltext import MAX_BYTES, local, validate_jats
from common import digest, write_json


def extract(raw):
    root = ET.fromstring(raw)
    body = next(x for x in root if local(x.tag) == 'body')
    anchors, mapping = {}, []
    excluded = {'table', 'graphic', 'inline-graphic', 'media', 'supplementary-material', 'ref-list'}
    elements = list(body.iter())
    omitted = {'table_elements': sum(local(x.tag) == 'table' for x in elements),
               'graphics': sum(local(x.tag) in ('graphic', 'inline-graphic', 'media') for x in elements),
               'supplementary_elements': sum(local(x.tag) == 'supplementary-material' for x in elements),
               'reference_lists': sum(local(x.tag) == 'ref-list' for x in elements),
               'captions_without_paragraph': sum(local(x.tag) == 'caption' and not any(local(y.tag) == 'p' for y in x.iter()) for x in elements)}
    def text_only(node):
        parts = [node.text or '']
        for child in node:
            if local(child.tag) not in excluded:
                parts.append(text_only(child))
            parts.append(child.tail or '')
        return ''.join(parts)
    def visit(node, sections, in_figure=False, in_caption=False):
        tag = local(node.tag)
        if tag in excluded:
            return
        if tag == 'sec':
            title = next((x for x in node if local(x.tag) == 'title'), None)
            if title is not None:
                sections = sections + [' '.join(''.join(title.itertext()).split())]
        in_figure = in_figure or tag in ('fig', 'fig-group')
        in_caption = in_caption or tag == 'caption'
        if tag == 'p':
            text = ' '.join(text_only(node).split())
            if text:
                key = f'xml-{len(anchors) + 1:05d}'
                anchors[key] = text
                mapping.append({'anchor': key, 'kind': 'figure_caption' if in_figure and in_caption else
                                'caption' if in_caption else 'paragraph',
                                'section_path': sections, 'source_element_id': node.get('id')})
            return
        for child in node:
            visit(child, sections, in_figure, in_caption)
    visit(body, [])
    if not anchors:
        raise ValueError('no_body_paragraphs_or_captions')
    return anchors, mapping, omitted


def run(source, doi, pmcid, output):
    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    try:
        if source.stat().st_size > MAX_BYTES:
            raise ValueError('xml_over_size_limit')
        source_sha = digest(source)
        code_paths = {name: Path(__file__).with_name(name) for name in
                      ('extract_jats_evidence.py', 'acquire_fulltext.py', 'literature_links.py', 'common.py')}
        code_sha = {name: digest(path) for name, path in code_paths.items()}
        raw = source.read_bytes()
        identity = validate_jats(raw, doi, pmcid)
        anchors, mapping, omitted = extract(raw)
        if digest(source) != source_sha or identity['sha256'] != source_sha:
            raise ValueError('source_changed_during_extraction')
        if code_sha != {name: digest(path) for name, path in code_paths.items()}:
            raise ValueError('code_changed_during_extraction')
        evidence = {'source_sha256': source_sha, 'coverage': 'selected_paragraphs', 'anchors': anchors,
                    'anchor_map': mapping, 'omitted_counts': omitted,
                    'limitations': ['Only body p elements, including p captions; images, table cells and non-p captions are not extracted',
                                    'Inline markup including super/subscripts and formulas is flattened; original figure, table, supplement and transcript accuracy need review']}
        write_json(output / 'evidence.json', evidence)
        receipt = {'status': 'extracted_text_only', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
                   'input_path': str(source.resolve()), 'input_sha256': source_sha, 'identity': identity,
                   'code_sha256': code_sha, 'anchor_count': len(anchors), 'omitted_counts': omitted,
                   'output': 'evidence.json', 'output_sha256': digest(output / 'evidence.json')}
        write_json(output / 'extraction_receipt.json', receipt)
        return receipt
    except Exception as exc:
        write_json(output / 'failure.json', {'status': 'failed', 'error_type': type(exc).__name__, 'error': str(exc)})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--doi', required=True)
    parser.add_argument('--pmcid', required=True)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    result = run(args.source, args.doi, args.pmcid, args.out)
    print(json.dumps({'status': result['status'], 'anchor_count': result['anchor_count'],
                      'omitted_counts': result['omitted_counts']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
