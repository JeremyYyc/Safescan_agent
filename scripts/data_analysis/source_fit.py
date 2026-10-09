"""Offline, sample-scoped Property contract checks; never imports into a database."""
import argparse
import ast
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/data_collection'))
from source_fit_probe import parse_home_index

DATA = ROOT / 'data/collection-pilot'
MODEL = ROOT / 'backend/services/property-leasing-service/app/models/tables.py'
PARKING = ROOT / 'backend/alembic/versions/20260914_0013_property_parking_legacy_compat.py'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract():
    node = next(n for n in ast.parse(MODEL.read_text(encoding='utf-8')).body
                if isinstance(n, ast.ClassDef) and n.name == 'Property')
    fields = {n.target.id: ast.unparse(n.annotation) for n in node.body if isinstance(n, ast.AnnAssign)}
    if 'IF NEW.parking_spaces IS NULL THEN' not in PARKING.read_text(encoding='utf-8'):
        raise ValueError('parking_contract_changed_review_required')
    return {'fields': fields, 'model_sha256': sha(MODEL), 'parking_migration_sha256': sha(PARKING),
            'parking_required_on_insert': True, 'scope': 'offline_subset_not_database_integration'}


def https(value):
    return isinstance(value, str) and urlsplit(value).scheme == 'https' and bool(urlsplit(value).hostname)


def validate(payload):
    """Check the fields used by these projections, plus conservative pilot gates."""
    errors = []
    for field in ('reference', 'address', 'currency', 'status', 'listing_visibility'):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            errors.append(field + ':required_string')
    for field in ('bedrooms', 'parking_spaces'):
        value = payload.get(field)
        if type(value) is not int or value < 0:
            errors.append(field + ':required_nonnegative_integer')
    for field, precision, scale, positive in [('bathrooms', 5, 1, False), ('weekly_rent', 14, 2, False),
                                             ('floor_area_sqm', 10, 2, True)]:
        value = payload.get(field)
        if field == 'floor_area_sqm' and value is None:
            continue
        try:
            number = Decimal(str(value))
            valid = (number.is_finite() and number >= 0 and (not positive or number > 0)
                     and number < Decimal(10) ** (precision - scale)
                     and number == number.quantize(Decimal(10) ** -scale))
        except (InvalidOperation, ValueError):
            valid = False
        if not valid:
            errors.append(field + ':invalid_decimal')
    if payload.get('status') not in ('draft', 'vacant', 'marketing', 'under_offer', 'occupied', 'maintenance', 'inactive'):
        errors.append('status:invalid_enum')
    if payload.get('listing_visibility') not in ('private', 'staff', 'public'):
        errors.append('listing_visibility:invalid_enum')
    currency = payload.get('currency')
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isascii() or not currency.isalpha() or not currency.isupper():
        errors.append('currency:unconfirmed_or_invalid')
    images = payload.get('display_image_urls')
    if not isinstance(images, list) or not images or not all(https(u) for u in images):
        errors.append('display_image_urls:pilot_requires_images')
    if not https(payload.get('floorplan_url')):
        errors.append('floorplan_url:pilot_requires_plan')
    if not isinstance(payload.get('attributes'), dict):
        errors.append('attributes:required_object')
    return sorted(set(errors))


def blockers(record_type, rights_approved=False, inspection_video_file=False):
    result = []
    if record_type != 'unit_listing':
        result.append('room_type_is_not_a_real_unit')
    if not rights_approved:
        result.append('application_reuse_rights_unverified')
    if not inspection_video_file:
        result.append('no_inspection_video_file')
    return result


def verified_media():
    reviews = read(Path(__file__).with_name('source_fit_reviews.json'))['media']
    found = {}
    for folder in ('source-fit-20260929', 'multimodal-fit-20260929'):
        for item in read(DATA / folder / 'outcomes.json'):
            if item['kind'] != 'image' or item['state'] != 'success':
                continue
            path = DATA / folder / item['local_path']
            checksum = sha(path)
            if checksum != item['sha256'] or checksum not in reviews:
                raise ValueError('media_hash_or_review_mismatch:' + item['id'])
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                if (image.width, image.height) != (item['width'], item['height']):
                    raise ValueError('media_dimensions_changed')
            found[item['id']] = {**item, 'local_path': str(path.relative_to(ROOT)),
                                 'review': reviews[checksum], 'human_approved': False}
    if set(reviews) != {m['sha256'] for m in found.values()}:
        raise ValueError('review_has_no_corresponding_asset')
    return found


def build():
    schema = contract()
    media = verified_media()
    room = next(r for r in read(DATA / 'flagstaff-20260929-v1/room_types.json') if r['name'] == 'Studio Standard')
    novus = read(DATA / 'novus-20260929/sample.json')
    studios = BeautifulSoup((DATA / 'flagstaff-20260929-v1/raw/studios.html').read_bytes(), 'html.parser')
    standard = next(n for n in studios.select('.ul_room') if n.select_one('h2') and n.select_one('h2').get_text(strip=True) == room['name'])
    if 'Private Ensuite Bathroom' not in standard.get_text():
        raise ValueError('studio_bathroom_evidence_changed')
    property_html = BeautifulSoup((DATA / 'flagstaff-20260929-v1/raw/property.html').read_bytes(), 'html.parser')
    business = None
    for script in property_html.select('script[type="application/ld+json"]'):
        items = json.loads(script.string or script.get_text())
        for item in items if isinstance(items, list) else [items]:
            if isinstance(item, dict) and item.get('@type') == 'LocalBusiness':
                business = item
    if not business:
        raise ValueError('building_address_evidence_missing')
    address = business['address']
    building_address = ', '.join(address[k] for k in ('streetAddress', 'addressLocality', 'postalCode'))
    groups = {'unilodge': ['unilodge-main-plan', 'unilodge-standard-1', 'unilodge-interior-extra-2'],
              'novus': ['novus-0', 'novus-1', 'novus-2']}
    observations = media['novus-0']['review']['observations']
    if Decimal(observations['internal_area_sqm']) + Decimal(observations['balcony_area_sqm']) != Decimal(novus['area_sqm']):
        raise ValueError('listing_plan_area_conflict')
    evidence = {
        'unilodge': {'record_type': 'room_type', 'source': room, 'building_address': building_address,
                     'bedrooms_normalized': 0, 'bathrooms_normalized': '1',
                     'normalization': 'studio -> zero separate bedrooms; private ensuite -> one bathroom',
                     'parking_spaces': None, 'selected_offer': room['offers'][0]},
        'novus': {'record_type': 'unit_listing', 'source': novus, 'floorplan_observations': observations,
                  'area_review_status': 'assistant_visual_read_requires_human_confirmation'}
    }
    samples, checks = {}, {}
    for key in groups:
        selected = [media[i] for i in groups[key]]
        if not all(m['review']['selected'] for m in selected):
            raise ValueError('unapproved_candidate_selected')
        is_uni = key == 'unilodge'
        raw = {'reference': None if is_uni else novus['source_listing_id'],
               'address': building_address if is_uni else novus['address'],
               'bedrooms': 0 if is_uni else novus['bedrooms'], 'bathrooms': '1' if is_uni else str(novus['bathrooms']),
               'parking_spaces': None if is_uni else novus['parking_spaces'],
               'floor_area_sqm': str(room['area_sqm']) if is_uni else observations['internal_area_sqm'],
               'weekly_rent': room['offers'][0]['amount'] if is_uni else novus['weekly_rent'],
               'currency': None, 'status': None, 'listing_visibility': None,
               'display_image_urls': [m['url'] for m in selected if m['review']['category'] == 'interior'],
               'floorplan_url': selected[0]['url'], 'attributes': {}}
        demo = deepcopy(raw)
        synthetic_fields = ['reference', 'currency', 'status', 'listing_visibility']
        demo.update(reference='DEMO-' + key.upper() + '-001', currency='AUD', status='draft', listing_visibility='private')
        if is_uni:
            demo['parking_spaces'] = 0
            synthetic_fields.append('parking_spaces')
        demo['attributes'] = {'synthetic': True, 'synthetic_fields': synthetic_fields,
                              'source_record_type': evidence[key]['record_type'],
                              'source_url': evidence[key]['source']['source_url'],
                              'source_reference': room['id'] if is_uni else novus['source_listing_id'],
                              'area_scope': 'studio_unspecified_internal_or_total' if is_uni else 'internal_visual_read',
                              'area_evidence': None if is_uni else observations,
                              'price_evidence': room['offers'][0] if is_uni else {
                                  k: novus[k] for k in ('weekly_rent', 'currency', 'period', 'rent_basis', 'lease_condition')},
                              'media_association': 'room_type_or_indicative_not_current_unit_condition',
                              'rights_approved': False, 'human_approved': False, 'publication_status': 'not_released'}
        unknown = set(demo) - set(schema['fields'])
        if unknown:
            raise ValueError('projection_fields_not_in_model:' + str(unknown))
        samples[key] = {'evidence': evidence[key], 'media': selected, 'observed_projection': raw,
                        'simulation_projection': demo, 'production_import_allowed': False}
        checks[key] = {'observed_projection_errors': validate(raw), 'simulation_projection_errors': validate(demo),
                       'semantic_blockers': blockers(evidence[key]['record_type']),
                       'layout_plan_count': 1, 'interior_count': 2, 'video_file_count': 0,
                       'human_approved_media_count': 0, 'unit_condition_evidence_count': 0}
    home = {p.stem: parse_home_index(p.read_bytes()) for p in sorted((DATA / 'source-fit-20260929/raw').glob('home-*.html'))}
    metrics = {'downloaded_images': len(media), 'unique_image_hashes': len({m['sha256'] for m in media.values()}),
               'selected_images': sum(m['review']['selected'] for m in media.values()),
               'sample_count': len(samples), 'home_index_reparsed': home,
               'home_floorplan_cards': sum(r['floorplan_card_count'] for r in home.values()),
               'home_availability_badges_not_unique_units': sum(r['availability_badge_sum'] for r in home.values()),
               'novus_first_page_listing_links': read(DATA / 'novus-20260929/index.json')['visible_listing_count'],
               'novus_sample_asset_candidates': len(novus['assets']), 'verified_100_complete_units': False}
    return samples, {'contract': schema, 'checks': checks, 'metrics': metrics,
                     'database_tested': False, 'production_import_allowed': False}


def run(output):
    samples, report = build()
    output.mkdir(parents=True, exist_ok=False)
    for name, value in {**{k + '-sample': v for k, v in samples.items()}, 'validation': report}.items():
        (output / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    inputs = [MODEL, PARKING, Path(__file__), Path(__file__).with_name('source_fit_reviews.json'),
              ROOT / 'scripts/data_collection/source_fit_probe.py']
    for folder in ('flagstaff-20260929-v1', 'source-fit-20260929', 'multimodal-fit-20260929', 'novus-20260929'):
        inputs.extend(p for p in (DATA / folder).rglob('*') if p.is_file())
    manifest = {'inputs': {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(inputs))},
                'outputs': {p.name: sha(p) for p in sorted(output.glob('*.json'))},
                'scope': 'offline_contract_subset_and_assistant_media_review_not_production_release'}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'checks': report['checks'], 'metrics': report['metrics']}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
