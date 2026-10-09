"""Offline quality audit of frozen housing snapshots; no network access."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

from bs4 import BeautifulSoup
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
VERSION = 'housing-baseline-v2'
CORE = ('id', 'name', 'property_id', 'location', 'source_url', 'retrieved_at')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('path_outside_input: ' + str(relative))
    return path


def ratio(n, d, reason='empty_denominator'):
    return {'numerator': n, 'denominator': d, 'value': n / d if d else None,
            'reason': reason if not d else None}


def known(value):
    return value is not None and value != '' and value != 'unknown' and value != {} and value != []


def money(value):
    if value is None:
        return None
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ValueError('invalid_price')
    return format(amount, 'f')


def home_address(body):
    for node in BeautifulSoup(body, 'html.parser').find_all('script', type='application/ld+json'):
        try:
            value = json.loads(node.string or 'null')
        except json.JSONDecodeError:
            continue
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, dict) and item.get('name') == 'Home Docklands':
                return item.get('address')
    return None


def offer(record, sample_id, source_id, unit_id=None):
    basis = record.get('price_basis')
    return {'id': source_id + ':' + record['id'] + ':offer', 'sample_id': sample_id,
            'unit_id': unit_id, 'amount': money(record.get('price_amount')),
            'currency': record.get('currency'), 'period': record.get('price_period'),
            'basis': basis if basis in ('person', 'room', 'unit') else None,
            'lease_condition': None, 'raw': record.get('price_raw'),
            'source_url': record['source_url'], 'retrieved_at': record.get('retrieved_at'),
            'missing_reason': 'not_recorded_in_legacy_snapshot_requires_source_review'}


def offer_complete(row):
    return all(known(row.get(k)) for k in ('amount', 'currency', 'period', 'basis', 'lease_condition'))


def audit_assets(directory, source_id, records, reviews, improved):
    assets, issues = [], []
    for row in records:
        item = {'id': source_id + ':' + row['id'], 'source_id': source_id,
                'sample_id': source_id + ':' + row['room_type_id'] if row.get('room_type_id') else None,
                'kind': row['kind'], 'url': row['url'], 'label': row.get('label'),
                'category': 'unreviewed', 'review_status': 'pending',
                'association': row.get('scope'), 'usable': None, 'human_approved': False,
                'integrity': 'not_downloaded', 'content_key': 'url:' + row['url'],
                'source_file': str(directory / 'assets.json'), 'local_path': row.get('local_path')}
        if row.get('local_path'):
            path = safe_path(directory, row['local_path'])
            try:
                actual = sha(path)
                with Image.open(path) as image:
                    width, height = image.size
                    image.verify()
                if actual != row.get('sha256'):
                    raise ValueError('hash_mismatch')
                if (width, height) != (row.get('width'), row.get('height')):
                    raise ValueError('dimension_mismatch')
                item.update(integrity='verified', content_key='sha256:' + actual, width=width, height=height)
                review = reviews.get(actual) if improved and source_id == 'home' else None
                if review:
                    item.update({k: review[k] for k in ('category', 'association', 'usable', 'reason') if k in review},
                                review_status='assistant_reviewed_pending_human')
            except (OSError, ValueError) as exc:
                item['integrity'] = 'failed'
                issues.append({'id': item['id'], 'rule': 'media_integrity', 'detail': str(exc)})
        assets.append(item)
    return assets, issues


def ensure_unique(rows, label):
    ids = [r['id'] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate_id_in_' + label)


def normalize(root, config, review_data, improved=True):
    data = {'samples': [], 'offers': [], 'units': [], 'assets': [], 'issues': [], 'inputs': []}
    # This historical audit deliberately has no authority to approve source rights.
    if any(s['rights_status'] != 'unknown' or s['approved_scopes'] for s in config['sources']):
        raise ValueError('rights_approval_requires_separate_validated_release_workflow')
    for dataset in config['datasets']:
        directory = safe_path(root, dataset['path'])
        source = dataset['source_id']
        for path in sorted(directory.glob('*.json')):
            data['inputs'].append({'path': str(path.relative_to(root)), 'sha256': sha(path)})
        properties, rooms = read(directory / 'properties.json'), read(directory / 'room_types.json')
        units = read(directory / 'units.json') if (directory / 'units.json').exists() else []
        assets = read(directory / 'assets.json')
        for name, records in [('properties', properties), ('rooms', rooms), ('units', units), ('assets', assets)]:
            ensure_unique(records, source + '_' + name)
        by_property = {p['id']: p for p in properties}
        if dataset['adapter'] == 'home':
            snapshots = [('raw/c04.html', read(directory / 'source.json'))]
            if (directory / 'gallery-source.json').exists():
                snapshots.append(('raw/gallery.html', read(directory / 'gallery-source.json')))
        else:
            snapshots = [('raw/' + p['id'] + '.html', p) for p in read(directory / 'pages.json')]
        for filename, meta in snapshots:
            path = safe_path(directory, filename)
            if sha(path) != meta['sha256']:
                raise ValueError('raw_snapshot_hash_mismatch: ' + filename)
            data['inputs'].append({'path': str(path.relative_to(root)), 'sha256': sha(path)})
        for room in rooms:
            prop = by_property[room['property_id']]
            location = prop.get('address')
            location_basis = 'legacy_property_record'
            if improved and dataset['adapter'] == 'home' and not location:
                location = home_address((directory / 'raw/c04.html').read_bytes())
                location_basis = 'raw/c04.html JSON-LD ApartmentComplex.address'
            sample = {'id': source + ':' + room['id'], 'source_id': source,
                      'property_id': source + ':' + room['property_id'], 'name': room['name'],
                      'location': location, 'location_basis': location_basis,
                      'source_url': room.get('source_url'), 'retrieved_at': room.get('retrieved_at'),
                      'record_type': 'room_type', 'bedrooms': room.get('bedrooms'),
                      'bathrooms': room.get('bathrooms'), 'area_sqm': room.get('area_sqm'),
                      'rights_status': 'unknown', 'approved_scopes': [],
                      'source_file': str(directory / 'room_types.json')}
            data['samples'].append(sample)
            if room.get('price_amount') is not None:
                data['offers'].append(offer(room, sample['id'], source))
        for unit in units:
            sid = source + ':' + unit['room_type_id']
            uid = source + ':' + unit['id']
            data['units'].append({'id': uid, 'sample_id': sid, 'unit_number_raw': unit.get('unit_number_raw'),
                                  'area_sqm': unit.get('area_sqm'), 'area_scope': 'unknown'})
            if unit.get('price_amount') is not None:
                data['offers'].append(offer(unit, sid, source, uid))
        normalized, issues = audit_assets(directory, source, assets, review_data['reviews'], improved)
        data['assets'].extend(normalized)
        data['issues'].extend(issues)
    sample_ids = {s['id'] for s in data['samples']}
    ensure_unique(data['samples'], 'samples')
    for key in ('offers', 'units', 'assets'):
        for row in data[key]:
            if row.get('sample_id') and row['sample_id'] not in sample_ids:
                raise ValueError('orphan_' + key + ': ' + row['id'])
    return data


def evaluate(data):
    checks = []
    for sample in data['samples']:
        sid = sample['id']
        offers = [o for o in data['offers'] if o['sample_id'] == sid]
        assets = [a for a in data['assets'] if a['sample_id'] == sid]
        core = {key: known(sample.get(key)) for key in CORE}
        verified = [a for a in assets if a['integrity'] == 'verified' and a['human_approved']
                    and a['usable'] and a['association'] == 'room_type_marketing']
        interiors = {a['content_key'] for a in verified if a['category'] == 'interior'}
        floorplans = {a['content_key'] for a in verified if a['category'] == 'floorplan'}
        reasons = ['missing_core:' + k for k, v in core.items() if not v]
        if not any(offer_complete(o) for o in offers):
            reasons.append('missing_price' if not offers else 'incomplete_price_basis_or_lease')
        if not floorplans:
            reasons.append('no_verified_readable_floorplan')
        if len(interiors) < 2:
            reasons.append('fewer_than_two_human_verified_interior_images')
        if any(a['integrity'] == 'failed' for a in assets):
            reasons.append('media_integrity_failure')
        checks.append({'sample_id': sid, 'core_fields': core, 'reasons': reasons,
                       'quality_pass': not reasons, 'approved_for_use': False,
                       'interior_count': len(interiors), 'floorplan_count': len(floorplans), 'offer_count': len(offers)})
    images = [a for a in data['assets'] if a['local_path']]
    valid = [a for a in images if a['integrity'] == 'verified']
    unique = {a['content_key']: a for a in valid}
    home = {a['content_key']: a for a in valid if a['source_id'] == 'home'}
    quality = sum(c['quality_pass'] for c in checks)
    metrics = {
        'identity_completeness': ratio(sum(sum(c['core_fields'].values()) for c in checks), len(checks) * len(CORE)),
        'room_parameter_completeness': ratio(sum(known(s.get(k)) for s in data['samples'] for k in ('bedrooms', 'bathrooms', 'area_sqm')), len(checks) * 3),
        'quality_pass_rate': ratio(quality, len(checks)),
        'use_admission_rate': ratio(0, quality, 'no_quality_qualified_samples'),
        'offer_completeness': ratio(sum(offer_complete(o) for o in data['offers']), len(data['offers'])),
        'image_integrity': ratio(len(valid), len(images)),
        'exact_image_duplicate_rate': ratio(len(valid) - len(unique), len(valid)),
        'verified_floorplan_coverage': ratio(sum(c['floorplan_count'] > 0 for c in checks), len(checks)),
        'verified_interior_coverage': ratio(sum(c['interior_count'] >= 2 for c in checks), len(checks)),
        'human_association_accuracy': ratio(0, 0, 'no_independent_human_review'),
        'request_success_rate': ratio(0, 0, 'legacy_snapshots_do_not_record_all_attempts'),
        'sample_cost': {'value': None, 'reason': 'legacy_work_time_not_recorded'},
        'home_assistant_suggested_core_media': ratio(sum(a['category'] in ('interior', 'floorplan') and a['usable'] is True for a in home.values()), len(home))}
    return checks, {'version': VERSION,
        'counts': {'properties': len({s['property_id'] for s in data['samples']}), 'samples': len(checks),
                   'units': len(data['units']), 'offers': len(data['offers']), 'asset_records': len(data['assets']),
                   'image_records': len(images), 'unique_verified_images': len(unique),
                   'vr_link_records': sum(a['kind'] == 'virtual_tour' for a in data['assets'])},
        'metrics': metrics, 'blockers': dict(Counter(r for c in checks for r in c['reasons'])),
        'home_unique_media_categories': dict(Counter(a['category'] for a in home.values())),
        'network_requests_this_analysis': 0, 'publication_status': 'not_released'}


def markdown(summary, checks, data, before):
    lines = ['# Existing Housing Snapshots: Offline Baseline', '',
             'Metadata audit only; no network collection or production release.', '',
             '## A. Inventory', '', '| Item | Count |', '|---|---:|']
    lines += [f'| {k} | {v} |' for k, v in summary['counts'].items()]
    lines += ['', '## B. Quality', '', '| Metric | n/N | Value |', '|---|---|---|']
    for key, metric in summary['metrics'].items():
        value = f"{metric['value']:.2%}" if metric['value'] is not None else 'N/A: ' + str(metric.get('reason'))
        lines.append(f"| {key} | {metric.get('numerator', '-')}/{metric.get('denominator', '-')} | {value} |")
    lines += ['', '## C. Gaps and Evidence', '', '| Sample | Unresolved | Evidence |', '|---|---|---|']
    by_id = {s['id']: s for s in data['samples']}
    for check in checks:
        sample = by_id[check['sample_id']]
        name = sample['name'].replace('|', '\\|')
        lines.append(f"| {name} | {', '.join(check['reasons']) or 'None'} | [Source]({sample['source_url']}) |")
    lines += ['', '## Same-snapshot Recheck', '']
    for stage, result in [('Before', before), ('After', summary)]:
        metric = result['metrics']['identity_completeness']
        lines.append(f"- {stage}: identity/location fields {metric['numerator']}/{metric['denominator']} (not overall quality).")
    lines += ['', 'HOME address was recovered from the saved JSON-LD; no inferred address or new fetch.',
              'Image deduplication uses content hashes, not URLs. Visual review labels are assistant suggestions, not human sign-off.',
              'A floorplan URL is not a readable approved floorplan. VR links were not opened in this audit.',
              '', '## Decisions', '', '- Keep room types separate from unit offers.',
              '- Review price basis and lease conditions before comparing prices.',
              '- Obtain readable matching floorplans and complete media association checks.',
              '- Confirm source-use scope before additional media collection or application publication.',
              '- Missing request/time logs remain N/A. This is not a capture-success or market-representative report.', '']
    return '\n'.join(lines)


def write_database(path, data, checks):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('CREATE TABLE samples (id TEXT PRIMARY KEY, source_id TEXT NOT NULL, payload TEXT NOT NULL)')
        db.executemany('INSERT INTO samples VALUES (?,?,?)', [(s['id'], s['source_id'], json.dumps(s)) for s in data['samples']])
        for table in ('offers', 'units', 'assets'):
            db.execute(f'CREATE TABLE {table} (id TEXT PRIMARY KEY, sample_id TEXT REFERENCES samples(id), payload TEXT NOT NULL)')
            db.executemany(f'INSERT INTO {table} VALUES (?,?,?)', [(r['id'], r.get('sample_id'), json.dumps(r)) for r in data[table]])
        db.execute('CREATE TABLE checks (sample_id TEXT PRIMARY KEY REFERENCES samples(id), quality_pass INTEGER, payload TEXT NOT NULL)')
        db.executemany('INSERT INTO checks VALUES (?,?,?)', [(c['sample_id'], int(c['quality_pass']), json.dumps(c)) for c in checks])
        if db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('database_foreign_key_failure')


def build(output, config_path=HERE / 'cohort.json', review_path=HERE / 'home_reviews.json', root=ROOT):
    config, reviews = read(config_path), read(review_path)
    _, before = evaluate(normalize(root, config, reviews, improved=False))
    data = normalize(root, config, reviews, improved=True)
    checks, summary = evaluate(data)
    summary['by_source'] = {}
    for source in config['sources']:
        ids = {s['id'] for s in data['samples'] if s['source_id'] == source['id']}
        subset = {'samples': [s for s in data['samples'] if s['id'] in ids],
                  'offers': [o for o in data['offers'] if o['sample_id'] in ids],
                  'units': [u for u in data['units'] if u['sample_id'] in ids],
                  'assets': [a for a in data['assets'] if a['source_id'] == source['id']], 'issues': []}
        _, summary['by_source'][source['id']] = evaluate(subset)
    output = output.resolve()
    for dataset in config['datasets']:
        source = safe_path(root, dataset['path'])
        if output.is_relative_to(source) or source.is_relative_to(output):
            raise ValueError('output_overlaps_input')
    output.mkdir(parents=True, exist_ok=False)
    for name, value in [('samples', data['samples']), ('offers', data['offers']), ('units', data['units']),
                        ('assets', data['assets']), ('issues', data['issues']), ('checks', checks),
                        ('summary', summary), ('before', before), ('source_registry', config['sources'])]:
        (output / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    write_database(output / 'analysis.sqlite', data, checks)
    (output / 'report.md').write_text(markdown(summary, checks, data, before), encoding='utf-8')
    def git(*args):
        result = subprocess.run(['git', *args], cwd=root, text=True, capture_output=True)
        return result.stdout.strip() if result.returncode == 0 else None
    manifest = {'cohort_id': config['cohort_id'], 'version': VERSION, 'created_at': datetime.now(timezone.utc).isoformat(),
                'git_sha': git('rev-parse', 'HEAD'), 'git_status': git('status', '--short'),
                'inputs': data['inputs'], 'config_sha256': sha(config_path), 'reviews_sha256': sha(review_path),
                'script_sha256': sha(Path(__file__)), 'outputs': {p.name: sha(p) for p in sorted(output.iterdir())},
                'network_requests': 0}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output), **summary}, ensure_ascii=False, indent=2))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.output)
