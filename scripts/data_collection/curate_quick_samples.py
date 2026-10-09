"""Non-destructive light-review housing export and defect review sheets."""
from pathlib import Path
import json
import shutil
from html import escape
from PIL import Image, ImageDraw
from collect import digest, write_json

BASE = Path('data/collection-pilot')
OUT = BASE / 'housing-curated-20261005'


def copy_asset(source, asset, role, folder):
    origin = source / asset['local_path']
    sha = digest(origin.read_bytes())
    if asset.get('sha256') and sha != asset['sha256']:
        raise ValueError('asset_hash_mismatch')
    dest = folder / (sha[:20] + origin.suffix)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origin, dest)
    return {'role': role, 'path': dest.relative_to(OUT).as_posix(), 'sha256': sha,
            'source_path': origin.resolve().as_posix(), 'source_url': asset.get('url'),
            'source_review': asset.get('review')}


def housing():
    OUT.mkdir(parents=True, exist_ok=False)
    rows = []
    buildings = {
        'metro-adelaide': ('UniLodge Metro Adelaide', 'Adelaide', '30 Victoria Street, Adelaide SA 5000'),
        'south-bank': ('UniLodge South Bank', 'South Brisbane', '125 Colchester Street, South Brisbane QLD 4101'),
        'flagstaff': ('UniLodge Melbourne Flagstaff', 'Melbourne', '17 Wills Street, Melbourne VIC 3000'),
    }
    src = BASE / 'unilodge-catalog-20260930'
    for r in json.loads((src / 'dataset.json').read_text(encoding='utf-8')):
        if r['tier'] != 'core':
            continue
        plans = [a for a in r['downloaded_assets'] if a.get('review', {}).get('category') == 'layout_complete']
        photos = [a for a in r['downloaded_assets'] if a.get('review', {}).get('category') == 'interior'][:2]
        assert plans and photos
        building, suburb, address = buildings[r['property_id']]
        row = {'id': r['id'], 'record_type': 'room_type_sample', 'name': r['name'],
               'building': building, 'city': r['city'], 'region': suburb, 'state': r['state_code'],
               'address': address, 'unit_number': None, 'source_url': r['source_url'],
               'review_level': 'prior_assistant_visual_review_reused',
               'match_note': 'Source room-type association and prior complete-plan/interior review. Sample interiors, not allocated-unit evidence.',
               'source_dataset': str(src / 'dataset.json'), 'notes': r.get('quality_notes', []),
               'usage_approved': False, 'price_required': False, 'assets': []}
        row['assets'] = [copy_asset(src, a, role, OUT / 'media' / r['id']) for role, aa in [('layout', plans), ('interior', photos)] for a in aa]
        rows.append(row)
    src = BASE / 'general-raw-clean-20261001'
    for r in json.loads((src / 'clean/dataset.json').read_text(encoding='utf-8')):
        aa = [a for a in r['assets'] if a['category'] == 'layout'] + [a for a in r['assets'] if a['category'] == 'interior'][:2]
        rows.append({'id': r['id'], 'record_type': 'unit_listing_sample', 'name': r['address'],
                     'city': 'Melbourne', 'state': 'VIC', 'region': 'East Melbourne' if r['id'] == 'hotham' else 'Carlton',
                     'address': r['address'], 'unit_number': r['unit_number'],
                     'source_url': aa[0].get('listing_url'), 'review_level': 'prior_assistant_visual_review_reused',
                     'match_note': r['association'], 'notes': r['limitations'], 'usage_approved': False,
                     'price_required': False, 'source_dataset': str(src / 'clean/dataset.json'),
                     'assets': [copy_asset(src, a, a['category'], OUT / 'media' / r['id']) for a in aa]})
    src = BASE / 'general-batch02-20261001'
    r = next(r for r in json.loads((src / 'clean/provisional.json').read_text(encoding='utf-8')) if r['id'] == 'king-william')
    rows.append({'id': r['id'], 'record_type': 'unit_listing_sample', 'name': r['address'],
                 'city': 'Adelaide', 'region': 'Adelaide', 'state': 'SA', 'address': r['address'],
                 'unit_number': '1903', 'source_url': r['url'], 'review_level': 'assistant_light_visual_review_20261005',
                 'match_note': 'Same listing. Complete one-bedroom illustrative layout; linear kitchen facing living area and full-height glazing in living/bedroom broadly consistent. Balcony and bathroom not confirmed in selected photos.',
                 'notes': ['Historical listing; not confirmed current availability. No exact geometry verification.'],
                 'usage_approved': False, 'price_required': False,
                 'source_dataset': str(src / 'clean/provisional.json'),
                 'assets': [copy_asset(src, a, 'layout' if i == 0 else 'interior', OUT / 'media' / r['id']) for i, a in enumerate(r['assets'][:3])]})
    write_json(OUT / 'dataset.json', rows)
    write_json(OUT / 'summary.json', {'room_type_samples': 14, 'unit_listing_samples': 3, 'total_records': len(rows),
        'images': sum(len(r['assets']) for r in rows), 'price_excluded_from_acceptance': True,
        'review_scope': 'light content matching; no authenticity, safety, dimensions or availability certification'})
    write_json(OUT / 'held_out.json', [{'id': 'wellington', 'reason': 'Plan labels living carpet while photos show tiles; kitchen/door arrangement merits further check. Not included in light matched set.'},
        {'scope': 'other candidates', 'reason': 'Not reviewed in this quick curation; original datasets retained.'}])
    md = ['# 房源精选预览', '', '14个学生房型样本 + 3条具体住宅挂牌样本。价格不作门槛，原始报价仍保留在来源包。', '']
    html = []
    for i, r in enumerate(rows, 1):
        title = f"{i:02d} | {r['city']} / {r['region']} | {r['name']}"
        md += [f'## {title}', r['address'], f"记录类型：{r['record_type']}。房号：{r.get('unit_number') or '未公开，房型样本'}。", r['match_note'], '']
        html.append(f'<section><h2>{escape(title)}</h2><p>{escape(r["address"])}</p><p>{escape(r["record_type"])} | {escape(r["match_note"])}</p><div class="gallery">')
        for a in r['assets']:
            md += [f"![{a['role']}](<{(OUT / a['path']).resolve().as_posix()}>)", '']
            html.append(f'<figure><img src="{escape(a["path"])}"><figcaption>{a["role"]}</figcaption></figure>')
        html.append('</div></section>')
    (OUT / 'preview.md').write_text('\n'.join(md), encoding='utf-8')
    (OUT / 'index.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>房源精选</title><style>body{font:16px sans-serif;margin:24px}section{border-top:1px solid #ccc;padding:20px 0}h2{font-size:20px}p{overflow-wrap:anywhere}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(280px,100%),1fr));gap:14px}figure{margin:0}img{width:100%;height:300px;object-fit:contain}</style><h1>房源精选</h1><p>学生房型与具体挂牌分别标明。布局与图片基本匹配；非实时库存或现场认证。原始资料未改动，使用权待确认。</p>' + ''.join(html), encoding='utf-8')
    write_json(OUT / 'manifest.json', {p.relative_to(OUT).as_posix(): digest(p.read_bytes()) for p in OUT.rglob('*') if p.is_file()})


def sheets():
    root = BASE / 'repair-bd3-20261005'
    rows = json.loads((root / 'dataset.json').read_text(encoding='utf-8'))
    for category in sorted({r['category'] for r in rows}):
        group = [r for r in rows if r['category'] == category and r['status'] == 'success']
        sheet = Image.new('RGB', (1500, 335), 'white')
        draw = ImageDraw.Draw(sheet)
        for i, r in enumerate(group):
            with Image.open(root / r['local_path']) as im:
                im.thumbnail((294, 294))
                sheet.paste(im, (i * 300, 35))
            draw.text((i * 300 + 4, 8), category + ' / ' + r['id'], fill='black')
        sheet.save(root / (category.replace(' ', '_') + '-review.jpg'))


if __name__ == '__main__':
    housing()
    sheets()
