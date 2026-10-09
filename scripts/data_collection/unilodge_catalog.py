"""Build a self-contained regional catalog from hash-verified research snapshots."""
import argparse
from collections import Counter
from html import escape
from pathlib import Path
import shutil

from PIL import Image

from collect import ROOT, digest, write_json
from unilodge_regional_media import read, media_complete

REGIONAL = ROOT / 'data/collection-pilot/unilodge-regional-dataset-20260930'
FLAGSTAFF = ROOT / 'data/collection-pilot/unilodge-acceptance-20260929-final'
CATEGORIES = {'layout': 'layout_complete', 'interior': 'interior',
              'lifestyle': 'interior_with_people', 'cropped_plan': 'layout_cropped',
              'low_resolution': 'interior_low_resolution'}


def build(output):
    output.mkdir(parents=True, exist_ok=False)
    (output / 'media').mkdir()
    rooms = read(REGIONAL / 'dataset.json')
    for room in rooms:
        room['input_snapshot'] = str(REGIONAL.relative_to(ROOT))
        for asset in room['downloaded_assets']:
            asset['_source_path'] = REGIONAL / asset['local_path']
    for original in read(FLAGSTAFF / 'acceptance.json')['rooms']:
        room = {k: v for k, v in original.items() if k not in ('assets', 'category_counts', 'gaps', 'media_package', 'technical_demo_candidate')}
        room.update(city='Melbourne', state_code='VIC', property_id='flagstaff', record_type='room_type',
                    unit_number=None, assigned_floor=None, floor_range_source_text=[], quality_notes=[],
                    input_snapshot=str(FLAGSTAFF.relative_to(ROOT)), downloaded_assets=[])
        for original_asset in original['assets']:
            asset = dict(original_asset)
            category = CATEGORIES[asset.pop('category')]
            asset['role'] = 'layout' if category.startswith('layout') else 'interior_candidate'
            asset['review'] = {'category': category, 'status': 'assistant_reviewed',
                               'reviewer': 'assistant', 'note': asset['note'],
                               'inherited_from': str((FLAGSTAFF / 'acceptance.json').relative_to(ROOT))}
            asset['_source_path'] = FLAGSTAFF / asset.pop('path')
            room['downloaded_assets'].append(asset)
        rooms.append(room)
    if len({r['id'] for r in rooms}) != len(rooms):
        raise ValueError('duplicate_room_ids')
    assets_by_hash = {}
    for room in rooms:
        for asset in room['downloaded_assets']:
            source = asset.pop('_source_path').resolve()
            source.relative_to(ROOT / 'data/collection-pilot')
            if digest(source.read_bytes()) != asset['sha256']:
                raise ValueError('media_hash_mismatch:' + str(source))
            with Image.open(source) as im:
                im.verify()
            target = output / 'media' / (asset['sha256'] + source.suffix)
            if not target.exists():
                shutil.copyfile(source, target)
            asset['source_local_path'] = str(source.relative_to(ROOT))
            asset['local_path'] = target.relative_to(output).as_posix()
            assets_by_hash[asset['sha256']] = asset['local_path']
        room['media_review_complete'] = media_complete(room['downloaded_assets'])
        room['media_review_with_people_complete'] = media_complete(room['downloaded_assets'], True)
        room['core_interior_count'] = len({a['sha256'] for a in room['downloaded_assets'] if a['review']['category'] == 'interior'})
        room['tier'] = ('core' if room['media_review_complete'] else
                        'with_people' if room['media_review_with_people_complete'] else 'incomplete')
        room['human_approved'] = False
        room['production_ready'] = False
    rooms.sort(key=lambda r: (r['city'], r['property_id'], r['name']))
    offers = [{'room_type_id': r['id'], 'city': r['city'], 'source_url': r['source_url'],
               'retrieved_at': r['retrieved_at'], **o} for r in rooms for o in r['offers']]
    regions = []
    for city in sorted({r['city'] for r in rooms}):
        subset = [r for r in rooms if r['city'] == city]
        regions.append({'city': city, 'properties': len({r['property_id'] for r in subset}),
                        'room_types': len(subset), 'offers': sum(len(r['offers']) for r in subset),
                        'core_complete': sum(r['tier'] == 'core' for r in subset),
                        'additional_with_people': sum(r['tier'] == 'with_people' for r in subset),
                        'two_core_interiors': sum(r['tier'] == 'core' and r['core_interior_count'] >= 2 for r in subset)})
    summary = {'regions': regions, 'room_types': len(rooms), 'offers': len(offers),
               'unique_media_files': len(assets_by_hash), 'tiers': dict(Counter(r['tier'] for r in rooms)),
               'definition': 'Core: complete illustrative layout plus at least one clear no-person room interior. People tier is additional, not additive to core.',
               'provenance': 'Public room-type samples, not actual allocated units; offers retain their original snapshot timestamps.',
               'rights_status': 'unknown', 'publication_status': 'not_released'}
    outputs = {'dataset.json': rooms, 'offers.json': offers, 'summary.json': summary,
               'complete_room_types.json': [r for r in rooms if r['tier'] == 'core'],
               'supplementary_room_types.json': [r for r in rooms if r['tier'] == 'with_people'],
               'incomplete_room_types.json': [r for r in rooms if r['tier'] == 'incomplete']}
    for name, value in outputs.items():
        write_json(output / name, value)
    render(output, rooms, summary)
    write_json(output / 'manifest.json', {
        'script_sha256': digest(Path(__file__).read_bytes()),
        'inputs': {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in
                   (REGIONAL / 'dataset.json', REGIONAL / 'export_manifest.json', FLAGSTAFF / 'acceptance.json', FLAGSTAFF / 'manifest.json')},
        'outputs': {n: digest((output / n).read_bytes()) for n in [*outputs, 'index.html']},
        'media': {path: sha for sha, path in assets_by_hash.items()},
    })
    print(summary)


def render(output, rooms, summary):
    e = lambda value: escape(str(value), quote=True)
    labels = {'core': '完整布局 + 清晰室内图', 'with_people': '完整布局 + 含人物室内图', 'incomplete': '待补齐'}
    html = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>学生公寓房型数据集</title><style>*{box-sizing:border-box}body{margin:0;color:#24332d;background:white;font:15px/1.6 system-ui,"Microsoft YaHei",sans-serif;letter-spacing:0}main{max-width:1180px;margin:auto;padding:24px}h1{font-size:28px}h2{font-size:21px}a{color:#006e78;overflow-wrap:anywhere}section{border-top:1px solid #ccd5d0;padding:24px 0}.gallery{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}figure{margin:0}img{width:100%;aspect-ratio:4/3;object-fit:contain;background:#f3f5f4}figcaption{font-size:12px;overflow-wrap:anywhere}select{font:inherit;padding:6px;max-width:100%}.filters{display:flex;flex-wrap:wrap;gap:16px;margin:24px 0}table{border-collapse:collapse;width:100%;min-width:560px}td,th{padding:8px;border-bottom:1px solid #ccd5d0;text-align:left}.scroll{overflow:auto}.note{color:#805108}p{overflow-wrap:anywhere}summary{cursor:pointer}@media(max-width:650px){main{padding:16px}.gallery{grid-template-columns:1fr}h1{font-size:24px}}</style><main><h1>学生公寓房型数据集</h1>'''
    html += f"<p>{len(rooms)} 个房型 · {summary['offers']} 条历史快照报价 · {summary['unique_media_files']} 个图片文件 · 2026-09-30 整理</p>"
    html += '<p>房型样板资料；具体房号与分配楼层未知。图纸为示意图。币种、计价对象和面积差异保留原始状态。</p><p>'
    for filename, label in [('dataset.json', '全部房型'), ('complete_room_types.json', '核心完整集'), ('supplementary_room_types.json', '含人物补充集'), ('offers.json', '报价'), ('summary.json', '统计')]:
        html += f'<a href="{filename}">{label}</a>　'
    html += '</p><div class="scroll"><table><tr><th>城市</th><th>楼盘</th><th>房型</th><th>报价</th><th>核心完整</th><th>含人物补充</th></tr>'
    for row in summary['regions']:
        html += '<tr>' + ''.join(f'<td>{e(row[k])}</td>' for k in ('city', 'properties', 'room_types', 'offers', 'core_complete', 'additional_with_people')) + '</tr>'
    html += '</table></div><div class="filters"><label>城市 <select id="city"><option value="all">全部</option>'
    html += ''.join(f'<option>{e(r["city"])}</option>' for r in summary['regions'])
    html += '</select></label><label>完整性 <select id="tier"><option value="all">全部</option>'
    html += ''.join(f'<option value="{k}">{v}</option>' for k, v in labels.items()) + '</select></label><output id="count"></output></div>'
    for room in rooms:
        html += f'<section data-city="{e(room["city"])}" data-tier="{room["tier"]}"><h2>{e(room["city"])} / {e(room["property_id"])} / {e(room["name"])}</h2><p>{labels[room["tier"]]} · <a href="{e(room["source_url"])}">来源</a> · {len(room["offers"])} 条报价</p>'
        html += f'<p>楼层范围：{e("; ".join(room["floor_range_source_text"]) or "未知")}；房号：未知</p>'
        for note in room.get('quality_notes', []):
            html += f'<p class="note">{e(note)}</p>'
        html += '<div class="gallery">'
        for asset in room['downloaded_assets']:
            html += f'<figure><a href="{e(asset["local_path"])}"><img src="{e(asset["local_path"])}" alt="{e(room["name"])} {e(asset["review"]["category"])}"></a><figcaption>{e(asset["review"]["category"])} · {asset["width"]} × {asset["height"]}</figcaption></figure>'
        html += '</div><details><summary>报价明细与采集时间</summary>'
        html += f'<p>{e(room["retrieved_at"])}；报价是页面快照，不代表当前可订库存。</p>'
        for offer in room['offers']:
            html += f'<p>{e(offer["amount"])} / {e(offer["period"])} · {e(offer["lease_label"])} · 币种：{e(offer.get("currency") or "待核实")} · 计价对象：{e(offer.get("basis") or "待核实")}</p>'
        html += '</details></section>'
    html += '''<script>const city=document.getElementById('city'),tier=document.getElementById('tier');function filter(){let n=0;document.querySelectorAll('section').forEach(s=>{s.hidden=!(city.value==='all'||s.dataset.city===city.value)||!(tier.value==='all'||s.dataset.tier===tier.value);if(!s.hidden)n++});document.getElementById('count').textContent=n+' 个房型'}city.addEventListener('change',filter);tier.addEventListener('change',filter);filter();</script></main></html>'''
    (output / 'index.html').write_text(html, encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output.resolve())
