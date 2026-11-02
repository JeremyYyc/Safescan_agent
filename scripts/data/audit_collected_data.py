"""Audit the portable SQL/MinIO collection without connecting to any service.

Usage: python audit_collected_data.py DATASET_DIRECTORY --output REPORT.json
Pillow is required only for decoding and verifying the delivered images.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re


def parse_inserts(sql):
    """Read the exporter's SQL literals, never evaluate or execute SQL."""
    tables = defaultdict(list)
    pattern = re.compile(r"INSERT INTO collected_data\.(\w+) \(([^)]+)\) VALUES \(")
    for match in pattern.finditer(sql):
        pos, values = match.end(), []
        while True:
            while sql[pos].isspace():
                pos += 1
            if sql[pos] == "'":
                pos += 1
                chars = []
                while True:
                    if sql[pos] == "'":
                        if sql[pos + 1] == "'":
                            chars.append("'")
                            pos += 2
                            continue
                        pos += 1
                        break
                    chars.append(sql[pos])
                    pos += 1
                value = "".join(chars)
            else:
                end = pos
                while sql[end] not in ',)':
                    end += 1
                token = sql[pos:end].strip()
                value = {"NULL": None, "TRUE": True, "FALSE": False}.get(token, token)
                if token not in {"NULL", "TRUE", "FALSE"}:
                    value = json.loads(token)
                pos = end
            values.append(value)
            while sql[pos].isspace():
                pos += 1
            if sql[pos] == ')':
                break
            assert sql[pos] == ',', (match.group(1), pos)
            pos += 1
        columns = [c.strip() for c in match.group(2).split(',')]
        assert len(columns) == len(values), match.group(1)
        row = dict(zip(columns, values))
        for field in ('metadata', 'license_info', 'address'):
            if isinstance(row.get(field), str):
                row[field] = json.loads(row[field])
        tables[match.group(1)].append(row)
    return dict(tables)


def present(value):
    return value is not None and value != '' and value != [] and value != {}


def completeness(rows):
    keys = sorted({key for row in rows for key in row})
    return {key: {'filled': sum(present(r.get(key)) for r in rows), 'total': len(rows)}
            for key in keys}


def distribution(rows, key):
    return dict(Counter(str(r.get(key)) for r in rows))


def audit(root):
    from PIL import Image
    root = root.resolve()
    manifest = json.loads((root / 'manifest.json').read_text())
    failures = []
    for relative, expected in manifest.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            failures.append('missing_or_unsafe:' + relative)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            failures.append('checksum:' + relative)
    rows = parse_inserts((root / 'dataset.sql').read_text())
    objects = json.loads((root / 'objects.json').read_text())
    assets = {r['id']: r for r in rows['media_assets']}
    object_checks = Counter()
    for obj in objects:
        path = (root / obj['local_path']).resolve()
        assert path.is_relative_to(root)
        data = path.read_bytes()
        asset = assets.get(obj['sha256'])
        if hashlib.sha256(data).hexdigest() != obj['sha256'] or len(data) != obj['byte_size']:
            failures.append('object_content:' + obj['local_path'])
        if not asset or any(asset[a] != obj[b] for a, b in (
                ('bucket', 'bucket'), ('object_key', 'object_key'),
                ('byte_size', 'byte_size'), ('mime_type', 'content_type'))):
            failures.append('object_sql_mismatch:' + obj['local_path'])
        try:
            with Image.open(path) as im:
                actual = im.size
                actual_mime = Image.MIME.get(im.format)
                im.verify()
            with Image.open(path) as im:
                im.load()
            if asset and actual != (asset['width'], asset['height']):
                failures.append('dimensions:' + obj['local_path'])
            if actual_mime != obj['content_type']:
                failures.append('mime:' + obj['local_path'])
            object_checks['decoded'] += 1
            if min(actual) < 256:
                object_checks['short_edge_below_256'] += 1
        except Exception as exc:
            failures.append('image_decode:' + obj['local_path'] + ':' + str(exc))
    housing = {r['id']: r for r in rows['housing_records']}
    repairs = {r['id']: r for r in rows['repair_cases']}
    documents = {r['id']: r for r in rows['knowledge_documents']}
    for table, fields in {
        'media_assets': ('id',), 'housing_records': ('id',), 'repair_cases': ('id',),
        'housing_media': ('housing_id', 'media_id'), 'repair_media': ('repair_id', 'media_id'),
        'knowledge_documents': ('id',), 'knowledge_steps': ('document_id', 'step_number'),
    }.items():
        counts = Counter(tuple(r[k] for k in fields) for r in rows[table])
        if any(n > 1 for n in counts.values()):
            failures.append('duplicate_key:' + table)
    linked = set()
    for table, records, fk in [('housing_media', housing, 'housing_id'),
                                ('repair_media', repairs, 'repair_id')]:
        links = defaultdict(list)
        for row in rows[table]:
            if row[fk] not in records or row['media_id'] not in assets:
                failures.append('broken_link:' + table)
            links[row[fk]].append(row['media_id'])
            linked.add(row['media_id'])
        for rid, record in records.items():
            if sorted(links[rid]) != sorted(record['metadata']['image_ids']):
                failures.append('metadata_image_ids:' + rid)
            if len(links[rid]) != record['metadata']['image_count']:
                failures.append('metadata_image_count:' + rid)
    for row in rows['knowledge_steps']:
        if row['document_id'] not in documents:
            failures.append('broken_document_link')
    groups = {}
    for group in ('student', 'general', 'repair'):
        records = list(repairs.values()) if group == 'repair' else [
            r for r in housing.values() if r['dataset_type'] == group]
        meta = [r['metadata'] for r in records]
        originals = [r.get('original_record') or {} for r in meta]
        group_assets = [assets[s] for s in {
            s for r in meta for s in r['image_ids']}]
        groups[group] = {
            'count': len(records), 'sql_fields': completeness(records),
            'metadata_fields': completeness(meta), 'record_types': distribution(meta, 'record_type'),
            'source_batches': distribution(meta, 'source_batch'),
            'original_fields': completeness(originals),
            'production_ready': distribution(originals, 'production_ready'),
            'association_status': distribution(originals, 'association_status'),
            'categories': distribution(meta, 'category'),
            'image_roles': dict(Counter(a['metadata'].get('role') for a in group_assets)),
            'image_rights_status': dict(Counter(str(a['metadata'].get('rights_status')) for a in group_assets)),
            'source_url_duplicates': [u for u, n in Counter(r['source_url'] for r in records).items() if n > 1],
        }
    return {
        'source_commit': 'c432901bb0952378201e68d6296643c0e1651fcf',
        'manifest_entries_checked': len(manifest), 'failures': failures,
        'table_rows': {t: len(r) for t, r in rows.items()},
        'object_checks': dict(object_checks), 'unreferenced_images': sorted(set(assets) - linked),
        'groups': groups,
        'knowledge': {'fields': completeness(rows['knowledge_documents']),
                      'types': distribution(rows['knowledge_documents'], 'document_type'),
                      'jurisdictions': distribution(rows['knowledge_documents'], 'jurisdiction'),
                      'documents': [{k: r[k] for k in ('id', 'title_zh', 'english_words', 'jurisdiction', 'license_info')}
                                    for r in rows['knowledge_documents']]},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('table_rows', 'object_checks', 'failures')}, ensure_ascii=False))
    raise SystemExit(bool(report['failures']))


if __name__ == '__main__':
    main()
