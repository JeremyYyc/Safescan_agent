"""Package every downloaded source image, preserving associations and raw metadata."""
from collections import Counter, defaultdict
import csv
from html import escape
import json
from pathlib import Path
import shutil
from PIL import Image
from collect import digest, write_json

BASE = Path('data/collection-pilot')
OUT = Path('outputs/collected-data-20261009')
LABELS = {'repair': '维修图片', 'student': '学生公寓', 'general': '社会公寓'}
EXT = {'.jpg', '.jpeg', '.png', '.webp'}


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = defaultdict(list)
    for p in BASE.rglob('*'):
        if p.is_file() and p.suffix.lower() in EXT:
            files[digest(p.read_bytes())].append(p)
    metadata = defaultdict(list)
    for p in BASE.rglob('*.json'):
        for obj in walk(read(p)):
            sha = obj.get('sha256')
            if sha in files and (obj.get('url') or obj.get('image_url')):
                metadata[sha].append((p, obj))
    records = {k: {} for k in LABELS}
    assets = {k: {} for k in LABELS}
    excluded = set()
    links = {k: set() for k in LABELS}

    def add(group, parent, asset, batch, source_json, key=None):
        sha = asset.get('sha256')
        if sha not in files:
            return
        if asset.get('category') == 'Algae' or parent.get('category') == 'Algae':
            excluded.add(sha)
            return
        rid = key or str(parent.get('id') or parent.get('question_id') or parent.get('source_listing_id') or parent.get('source_url') or asset.get('id'))
        if rid not in records[group]:
            records[group][rid] = {
                'id': rid, 'name': parent.get('name') or parent.get('address') or parent.get('title') or rid,
                'record_type': parent.get('record_type') or ('repair_post' if group=='repair' else 'source_record'),
                'city': parent.get('city'), 'region': parent.get('state_code') or parent.get('jurisdiction'),
                'address': parent.get('address'), 'property_id': parent.get('property_id'),
                'category': parent.get('category_zh') or parent.get('category') or parent.get('property_type'),
                'source_url': parent.get('source_url') or parent.get('url') or asset.get('listing_url') or asset.get('source_url'),
                'unit_number': parent.get('unit_number'), 'floor': parent.get('assigned_floor') or parent.get('floor_text'),
                'bedrooms': parent.get('bedrooms'), 'bathrooms': parent.get('bathrooms'), 'area_sqm': parent.get('area_sqm'),
                'price_raw': parent.get('offers') or parent.get('offer') or parent.get('price_raw') or parent.get('weekly_rent'),
                'author': parent.get('author'), 'license': parent.get('content_license') or parent.get('rights_status'),
                'license_url': parent.get('license_url'),
                'notes': parent.get('review_note') or parent.get('flags') or parent.get('limitations') or parent.get('association_status'),
                'source_batch': batch, 'source_metadata': str(source_json.relative_to(BASE)),
                'image_ids': [], 'original_record': parent,
            }
        a = assets[group].get(sha)
        if not a:
            src = files[sha][0]
            with Image.open(src) as im:
                width, height = im.size
                im.verify()
            rel = 'images/' + sha + src.suffix.lower()
            dest = OUT/group/rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            a = assets[group][sha] = {'id': sha, 'path': rel, 'width': width, 'height': height,
                 'url': asset.get('url') or asset.get('image_url'),
                 'role': asset.get('role') or asset.get('category') or asset.get('kind'),
                 'review': asset.get('review') or asset.get('visual_review') or asset.get('review_status'),
                 'rights_status': asset.get('rights_status') or 'unknown',
                 'record_ids': [], 'source_files': [str(p.relative_to(BASE)) for p in files[sha]],
                 'source_metadata': [{'file': str(p.relative_to(BASE)), 'record': obj} for p,obj in metadata[sha]]}
        if (rid, sha) not in links[group]:
            links[group].add((rid, sha))
            records[group][rid]['image_ids'].append(sha)
            a['record_ids'].append(rid)

    # Use the richest existing record sets first, without completeness filtering.
    for batch in ['indoor-repair-20261009', 'used-fixtures-20261009', 'used-toilets-20261009']:
        p = BASE/batch/'dataset.json'
        for r in read(p):
            for a in r['assets']:
                add('repair', r, a, batch, p, 'diy-'+str(r['question_id']))
    p = BASE/'repair-bd3-20261005/clean.json'
    for a in read(p):
        add('repair', a, a, p.parent.name, p, 'bd3-'+a['id'])
    p = BASE/'unilodge-catalog-20260930/dataset.json'
    for r in read(p):
        for a in r['downloaded_assets']:
            add('student', r, a, p.parent.name, p)
    for batch in ['housing-20260928T094923Z', 'home-20260928T102421Z']:
        folder = BASE/batch
        rooms = {r['id']: r for r in read(folder/'room_types.json')}
        properties = {r['id']: r for r in read(folder/'properties.json')}
        for a in read(folder/'assets.json'):
            r = rooms.get(a.get('room_type_id'), {})
            prop = properties.get(r.get('property_id'), {})
            r = {**prop, **r}
            if batch.startswith('housing'):
                r['city'] = 'Sydney'
            add('student' if batch.startswith('housing') else 'general', r, a, batch, folder/'assets.json')
    p = BASE/'general-raw-clean-20261001/clean/dataset.json'
    for r in read(p):
        r['city'] = 'Melbourne'
        for a in r['assets']:
            add('general', r, a, p.parent.parent.name, p)
    for batch in ['general-batch02-20261001', 'general-batch03-light-20261001']:
        folder = BASE/batch
        rr = {r['id']: r for r in read(folder/'raw_records.json')}
        for p in folder.glob('media/*/outcomes.json'):
            for a in read(p):
                add('general', rr[a['sample_id']], a, batch, p)
    for p in (BASE/'general-verification-20261001').rglob('outcomes.json'):
        for a in read(p):
            key = a.get('id', '').split('-')[0]
            if key in {'hotham', 'elgin'} and a.get('kind') == 'image':
                add('general', records['general'][key]['original_record'], a, p.relative_to(BASE).parts[0], p, key)
    p = BASE/'novus-20260929/sample.json'
    r = read(p)
    r['city'] = 'Melbourne'
    for a in read(BASE/'multimodal-fit-20260929/outcomes.json'):
        if a['id'].startswith('novus'):
            add('general', r, a, p.parent.name, p)

    # Recover any older downloaded variants not already represented by image bytes.
    covered = set().union(*(set(a) for a in assets.values())) | excluded
    for sha, entries in metadata.items():
        if sha in covered:
            continue
        p, a = entries[0]
        text = json.dumps(a).lower() + str(p).lower()
        group = 'repair' if any(s in text for s in ['repair-', 'diy.stackexchange', 'used-fixtures', 'used-toilets']) else ('student' if any(s in text for s in ['unilodge', 'flagstaff', 'kensington']) else 'general')
        parent = {'id': 'legacy-'+sha[:16], 'name': a.get('label') or a.get('id') or '早期采集图片',
                  'record_type': 'legacy_image_unresolved_record', 'source_url': a.get('source_url') or a.get('listing_url'),
                  'notes': '早期采集补充图片；不臆测其精确房型或房源归属。'}
        add(group, parent, a, p.relative_to(BASE).parts[0], p)

    overview = []
    for group, label in LABELS.items():
        folder = OUT/group
        rr, aa = list(records[group].values()), list(assets[group].values())
        for r in rr:
            r['image_count'] = len(r['image_ids'])
        write_json(folder/'records.json', rr)
        write_json(folder/'images.json', aa)
        # Preserve all raw metadata for the source batches used by these images.
        batches = {Path(item['file']).parts[0] for a in aa for item in a['source_metadata']}
        for batch in batches:
            for p in (BASE/batch).rglob('*.json'):
                dest = folder/'source_metadata'/p.relative_to(BASE)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
        record_rows = [[r['id'], r['name'], r['city'], r['region'], r['category'], r['record_type'], r['image_count'], r['address'], r['unit_number'], r['floor'], r['area_sqm'], r['price_raw'], r['source_url'], r['notes']] for r in rr]
        image_rows = [[a['id'], a['role'], a['width'], a['height'], a['path'], a['record_ids'], a['url'], a['rights_status']] for a in aa]
        headers = ['记录ID','名称或地址','城市','区域','类别','记录类型','图片数','地址','房号','楼层','面积㎡','原始报价','来源链接','备注']
        ih = ['图片SHA256','图片角色','宽度px','高度px','本地图片路径','关联记录ID','图片来源链接','权属状态']
        def flat(v):
            return json.dumps(v, ensure_ascii=False) if isinstance(v, (dict,list)) else v
        record_rows = [[flat(v) for v in row] for row in record_rows]
        image_rows = [[flat(v) for v in row] for row in image_rows]
        for filename, data in [('总表.csv', [headers]+record_rows), ('图片索引.csv',[ih]+image_rows)]:
            with (folder/filename).open('w',encoding='utf-8-sig',newline='') as f:
                csv.writer(f).writerows([["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in row] for row in data])
        write_json(folder/'workbook_input.json', {'label':label,'records':[headers]+record_rows,'images':[ih]+image_rows})
        blocks = []
        for r in rr:
            blocks.append(f'<section><h2>{escape(str(r["name"]))}</h2><p>{escape(str(r["city"] or "城市未记录"))} · {r["image_count"]} 张</p><div class="gallery">')
            for sha in r['image_ids']:
                a = assets[group][sha]
                blocks.append(f'<a href="{a["path"]}"><img loading="lazy" src="{a["path"]}" alt="{escape(str(a["role"] or "图片"))}"></a>')
            blocks.append('</div></section>')
        (folder/'index.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+label+'</title><style>body{font:16px sans-serif;margin:24px;overflow-wrap:anywhere}h2{font-size:18px}section{border-top:1px solid #ddd;padding:16px 0}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(260px,100%),1fr));gap:12px}img{width:100%;height:240px;object-fit:contain}</style><h1>'+label+'</h1><p>全部有本地图片的采集记录；不按完整度筛选。表格保留来源与原始备注，藻斑除外。</p>'+''.join(blocks),encoding='utf-8')
        overview.append({'dataset': group, 'name':label, 'records':len(rr), 'unique_images':len(aa), 'image_associations':len(links[group]), 'unresolved_legacy_records':sum(r['record_type']=='legacy_image_unresolved_record' for r in rr)})
    write_json(OUT/'summary.json',overview)
    unreferenced = [str(p.relative_to(BASE)) for sha,pp in files.items() if sha not in metadata for p in pp]
    write_json(OUT/'coverage_audit.json', {'downloaded_unique_images_with_metadata':len(metadata), 'exported_unique_images':len(set().union(*(set(a) for a in assets.values()))), 'excluded_algae_hashes':sorted(excluded),'unreferenced_image_files':unreferenced})
    assert set(metadata) == set().union(*(set(a) for a in assets.values())) | excluded
    text = '# 采集数据交付\n\n采集阶段结束。三套数据均按“有本地图片即可”收录，不以完整度筛除。藻斑按此前要求排除；历史、示意、背景、近重复、未核验图片保留原备注。相同字节图片每套只保存一份，保留全部已整理关联。\n\n'
    for s in overview:
        text += f'- [{s["name"]}]({s["dataset"]}/index.html)：{s["records"]} 条记录，{s["unique_images"]} 张独立图片，{s["image_associations"]} 个图片关联。\n'
    text += '\n每套包含：总表.xlsx、总表.csv、图片索引.csv、images/、records.json、images.json、source_metadata/、index.html。原始批次未修改。表中缺失值保留为空；维修帖子不是已认证工单，房源照片可能为样板间或历史照片。报价不是当前可租报价，来源许可沿用原记录。\n\n记录数不等于独立实物住房数，旧版无法定位的图片明确列为待关联记录。维修中也保留示意图与背景图。\n'
    (OUT/'README.md').write_text(text,encoding='utf-8')
    print(json.dumps(overview,ensure_ascii=True,indent=2))
    print('UNREFERENCED',json.dumps(unreferenced,ensure_ascii=True))


if __name__ == '__main__':
    main()
