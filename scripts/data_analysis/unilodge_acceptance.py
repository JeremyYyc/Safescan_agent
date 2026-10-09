"""Frozen UniLodge cohort acceptance: auditable JSON and self-contained local HTML."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys

from bs4 import BeautifulSoup
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/data_collection'))
from flagstaff_collect import parse_rooms

SOURCE = ROOT / 'data/collection-pilot/unilodge-20260929-v2'
PREVIOUS = ROOT / 'data/collection-pilot/flagstaff-20260929-v1'
REVIEWS = Path(__file__).with_name('unilodge_acceptance_reviews.json')
LABELS = {'layout': '完整布局图', 'interior': '核心室内图候选', 'lifestyle': '人物 / 生活方式图',
          'cropped_plan': '裁切布局图', 'low_resolution': '低分辨率室内图'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def media_package(categories):
    return categories.get('layout', 0) >= 1 and categories.get('interior', 0) >= 2


def offer_key(offer):
    return (offer['lease_label'], offer['amount'], offer['period'], offer['basis'], offer['currency'])


def validate_asset(item, path):
    if sha(path) != item['sha256']:
        raise ValueError('media_hash_mismatch:' + item['id'])
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        if (image.width, image.height) != (item['width'], item['height']):
            raise ValueError('media_dimensions_mismatch')


def analyze(output):
    review = read(REVIEWS)
    outcomes_path = SOURCE / 'media/outcomes.json'
    if sha(outcomes_path) != review['snapshot_outcomes_sha256']:
        raise ValueError('review_snapshot_mismatch')
    rooms = read(SOURCE / 'room_types.json')
    previous = {r['id']: r for r in read(PREVIOUS / 'room_types.json')}
    pages = read(SOURCE / 'pages.json')
    parsed, raw_counts = [], {}
    for page in pages:
        if page['state'] != 'success':
            raise ValueError('source_page_failed')
        path = SOURCE / 'raw' / (page['id'] + '.html')
        if sha(path) != page['sha256']:
            raise ValueError('html_hash_mismatch')
        if page['id'] in ('studios', 'two-bedroom', 'four-bedroom'):
            parsed.extend(parse_rooms(path.read_bytes(), page))
            for block in BeautifulSoup(path.read_bytes(), 'html.parser').select('.ul_room'):
                name = block.select_one('h2')
                if name:
                    raw_counts[name.get_text(' ', strip=True)] = len(block.select('.ul_stay'))
    if parsed != rooms:
        raise ValueError('frozen_parser_output_mismatch')
    assets = []
    for item in read(outcomes_path):
        if item['state'] != 'success':
            raise ValueError('media_download_incomplete')
        path = SOURCE / 'media' / item['local_path']
        validate_asset(item, path)
        category = review['categories'][item['id']]
        if category == 'interior' and (max(item['width'], item['height']) < 640 or min(item['width'], item['height']) < 360):
            raise ValueError('interior_below_review_threshold')
        assets.append({**item, 'category': category, 'category_label': LABELS[category],
                       'note': review['category_notes'][category],
                       'path': Path(os.path.relpath(path, output)).as_posix(), 'human_approved': False})
    if {a['id'] for a in assets} != set(review['categories']):
        raise ValueError('review_asset_membership_mismatch')
    by_url = {a['url']: a for a in assets}
    associations = read(SOURCE / 'preview_media.json')
    result = []
    for room in rooms:
        if raw_counts[room['name']] != len(room['offers']):
            raise ValueError('raw_offer_count_mismatch')
        links = next(r['media'] for r in associations if r['room_id'] == room['id'])
        found = {by_url[m['url']]['sha256']: by_url[m['url']] for m in links}
        counts = Counter(m['category'] for m in found.values())
        old = previous[room['id']]
        old_keys, new_keys = {offer_key(o) for o in old['offers']}, {offer_key(o) for o in room['offers']}
        missing = []
        if not room['offers']:
            missing.append('报价缺失')
        if counts['layout'] == 0:
            missing.append('完整布局图缺失')
        if counts['interior'] < 2:
            missing.append('核心室内图不足2张')
        result.append({**room, 'assets': list(found.values()), 'category_counts': dict(counts),
                       'media_package': media_package(counts),
                       'technical_demo_candidate': media_package(counts) and bool(room['offers']),
                       'raw_offer_count': raw_counts[room['name']], 'previous_offer_count': len(old['offers']),
                       'removed_offer_count': len(old_keys-new_keys), 'added_offer_count': len(new_keys-old_keys),
                       'default_dates_changed': sum(any(o.get(k) != n.get(k) for k in ('default_start','default_end'))
                           for o in old['offers'] for n in room['offers'] if offer_key(o) == offer_key(n)),
                       'gaps': missing, 'production_ready': False})
    count = len(rooms)
    coverage = [
        ('房型名称 / 面积口径 / 床型', sum(bool(r['name']) and r['area_sqm'] is not None and r['area_scope'] != 'unknown' and bool(r['bedding']) for r in result)),
        ('至少一条当前报价', sum(bool(r['offers']) for r in result)),
        ('完整布局图（助手复核）', sum(r['category_counts'].get('layout',0)>0 for r in result)),
        ('至少两张核心室内图候选', sum(r['category_counts'].get('interior',0)>=2 for r in result)),
        ('布局图＋两张室内图＋报价', sum(r['technical_demo_candidate'] for r in result)),
        ('VR 入口（非视频文件）', sum(bool(r['vr_links']) for r in result)),
        ('完整报价口径：币种＋计价对象', sum(any(o['currency'] and o['basis'] and o['period'] for o in r['offers']) for r in result)),
        ('实际巡检视频文件', 0),
        ('获准业务导入', 0)]
    classes = Counter(a['category'] for a in assets)
    return {'cohort': 'UniLodge Melbourne Flagstaff · v2', 'snapshot_start': min(r['retrieved_at'] for r in rooms),
            'review_method': review['method'], 'rooms': result, 'assets': assets,
            'categories': [{'id': k, 'label': LABELS[k], 'count': classes[k]} for k in LABELS],
            'coverage': [{'label': k, 'count': v, 'denominator': count, 'percent': round(v/count*100,1)} for k,v in coverage],
            'metrics': {'room_types': count, 'properties': 1, 'actual_unit_ids': 0,
                'offers': sum(len(r['offers']) for r in result), 'previous_offers': sum(r['previous_offer_count'] for r in result),
                'downloaded_images': len(assets), 'unique_hashes': len({a['sha256'] for a in assets}),
                'core_images': classes['layout']+classes['interior'],
                'media_packages': sum(r['media_package'] for r in result),
                'technical_demo_candidates': sum(r['technical_demo_candidate'] for r in result),
                'independent_human_approvals': 0, 'production_ready': 0},
            'preview_path': Path(os.path.relpath(SOURCE/'preview.html', output)).as_posix(),
            'rules': {'min_interiors': 2, 'min_interior_long_side': 640, 'min_interior_short_side': 360,
                      'people_images_count_as_core': False, 'layout_requires_measurements': False,
                      'generalizes_to_platform': False, 'publication_status': 'not_released'}}


def run(output):
    data = analyze(output)
    output.mkdir(parents=True, exist_ok=False)
    template = Path(__file__).with_name('unilodge_acceptance.html').read_text(encoding='utf-8')
    payload = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c')
    (output/'index.html').write_text(template.replace('__AUDIT_DATA__', payload), encoding='utf-8')
    (output/'acceptance.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    inputs = [Path(__file__), REVIEWS, Path(__file__).with_name('unilodge_acceptance.html'),
              ROOT/'scripts/data_collection/flagstaff_collect.py', PREVIOUS/'room_types.json']
    inputs.extend(p for p in SOURCE.rglob('*') if p.is_file())
    manifest = {'inputs':{str(p.relative_to(ROOT)):sha(p) for p in sorted(set(inputs))},
                'outputs':{p.name:sha(p) for p in sorted(output.iterdir())}, 'network_requests':0}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'metrics':data['metrics'],'categories':data['categories'],'coverage':data['coverage']},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
