"""Validated raw-collection compiler and compatibility entry to the manual sync tool.

The canonical CLI is scripts/data/sync.py. No deployment hook imports this module.
Raw source tables use repeatable upserts; operational tables are handled separately.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

from audit_collected_data import audit, parse_inserts

HEADER_SHA256 = '437ab8411a62e61004a750e966ca168ad4845fb3bcaf058bdca36160456b5f06'
KEYS = {
    'media_assets': ['id'], 'repair_cases': ['id'],
    'repair_media': ['repair_id', 'media_id'], 'housing_records': ['id'],
    'housing_media': ['housing_id', 'media_id'], 'knowledge_documents': ['id'],
    'knowledge_steps': ['document_id', 'step_number'],
}
COLUMNS = {
    'media_assets': {'id', 'bucket', 'object_key', 'mime_type', 'byte_size', 'width', 'height', 'source_url', 'metadata'},
    'housing_records': {'id', 'dataset_type', 'name', 'city', 'region', 'address', 'source_url', 'metadata'},
    'repair_cases': {'id', 'name', 'category', 'source_url', 'actual_work_order', 'metadata'},
    'housing_media': {'housing_id', 'media_id', 'role'},
    'repair_media': {'repair_id', 'media_id', 'role'},
    'knowledge_documents': {'id', 'title', 'title_zh', 'document_type', 'body', 'english_words', 'source_url', 'jurisdiction', 'license_info', 'metadata'},
    'knowledge_steps': {'document_id', 'step_number', 'title', 'body', 'metadata'},
}


def literal(value, json_field=False):
    if value is None:
        return 'NULL'
    if json_field:
        value = json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, (int, float)):
        return str(value)
    if '\x00' in value:
        raise ValueError('NUL in text')
    return "'" + value.replace("'", "''") + "'"


def prepare(root, output):
    report = audit(root)
    if set(report['failures']) - {'duplicate_key:knowledge_steps'}:
        raise RuntimeError('Audit failed: ' + repr(report['failures']))
    source = (root / 'dataset.sql').read_text()
    header = source[:source.index('INSERT INTO ')]
    if hashlib.sha256(header.encode()).hexdigest() != HEADER_SHA256:
        raise RuntimeError('Unrecognized SQL schema; review before import')
    rows = parse_inserts(source)
    if set(rows) != set(KEYS):
        raise RuntimeError('Unexpected table set')
    if any(set(row) != COLUMNS[table] for table, records in rows.items() for row in records):
        raise RuntimeError('Unexpected columns in the source export')
    steps = defaultdict(list)
    for row in rows['knowledge_steps']:
        steps[row['document_id']].append(row)
    fixes = []
    for document_id, records in steps.items():
        if len({r['step_number'] for r in records}) == len(records):
            continue
        # Only the known exporter defect is corrected, preserving source order.
        if document_id != '44146' or len(records) != 5 or any(r['step_number'] != 1 for r in records):
            raise RuntimeError('Unexpected step numbering defect')
        for position, row in enumerate(records, 1):
            row['metadata'] = dict(row['metadata'], source_step_number=row['step_number'],
                                   import_step_position=position)
            row['step_number'] = position
        fixes.append({'document_id': document_id, 'source_numbers': [1] * 5,
                      'import_numbers': list(range(1, 6)), 'reason': 'preserve all source steps in source array order'})
    statements = [header]
    for table, records in rows.items():
        for row in records:
            columns = list(row)
            values = ', '.join(literal(row[c], c in ('metadata', 'address', 'license_info')) for c in columns)
            updates = ', '.join(f'{c}=EXCLUDED.{c}' for c in columns if c not in KEYS[table])
            statements.append(f'INSERT INTO collected_data.{table} ({", ".join(columns)}) VALUES ({values}) '
                              f'ON CONFLICT ({", ".join(KEYS[table])}) DO UPDATE SET {updates};')
    statements += ['CREATE INDEX IF NOT EXISTS housing_city_idx ON collected_data.housing_records(city);',
                   'CREATE INDEX IF NOT EXISTS repair_category_idx ON collected_data.repair_cases(category);', 'COMMIT;']
    sql = '\n\n'.join(statements) + '\n'
    reparsed = parse_inserts(sql)
    for table, records in reparsed.items():
        if len({tuple(r[k] for k in KEYS[table]) for r in records}) != len(records):
            raise RuntimeError('Duplicate after preparation: ' + table)
    if reparsed != rows:
        raise RuntimeError('SQL literal roundtrip changed data')
    output.mkdir(parents=True, exist_ok=True)
    sql_path = output / 'dataset.import.sql'
    sql_path.write_text(sql)
    report['import_fixes'] = fixes
    report['prepared_sql_sha256'] = hashlib.sha256(sql.encode()).hexdigest()
    (output / 'quality-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return sql_path, report



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--project-name')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--create-buckets', action='store_true')
    args = parser.parse_args()
    from sync import main as sync_main
    command = ['--steps', 'collection,media', '--source-dir', str(args.root),
               '--output-dir', str(args.output), '--apply' if args.apply else '--dry-run']
    if args.env_file:
        command += ['--env-file', str(args.env_file)]
    if args.project_name:
        command += ['--project-name', args.project_name]
    if args.create_buckets:
        command += ['--create-buckets']
    return sync_main(command)


if __name__ == '__main__':
    sys.exit(main())
