"""Bounded Flagstaff media collection and offline HTML evidence preview."""
import argparse
from html import escape
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from collect import ROOT, digest, write_json
from source_fit_probe import run

PLAN_NAMES = {'Studio Standard': 'studio-standard-fp', 'Studio Terrace': 'studio-terrace-fp',
              '2 Bedroom Apartment': '2-br-apt-fp', '4 Bedroom Apartment': '4-br-apt-fp'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def targets(source):
    items = {}
    for room in read(source / 'room_types.json'):
        for photo in room['photos']:
            items.setdefault(photo['url'], {'id': 'asset-' + digest(photo['url'].encode())[:16],
                                           'url': photo['url'], 'kind': 'image'})
    for asset in read(source / 'media_candidates.json'):
        if asset['kind'] == 'floorplan_candidate' and any(token in urlsplit(asset['url']).path for token in PLAN_NAMES.values()):
            items.setdefault(asset['url'], {'id': 'asset-' + digest(asset['url'].encode())[:16],
                                           'url': asset['url'], 'kind': 'image'})
    if len(items) > 23:
        raise ValueError('fixed_media_scope_exceeded')
    return list(items.values())


def link(url, label):
    if urlsplit(url).scheme not in ('http', 'https'):
        return escape(label)
    return '<a target="_blank" rel="noopener noreferrer" href="' + escape(url, quote=True) + '">' + escape(label) + '</a>'


def render(source, media):
    rooms = read(source / 'room_types.json')
    assets = read(source / 'media_candidates.json')
    outcomes = read(media / 'outcomes.json')
    downloaded = {a['url']: a for a in outcomes if a['state'] == 'success'}
    reviews = read(ROOT / 'scripts/data_analysis/source_fit_reviews.json')['media']
    for item in downloaded.values():
        if digest((media / item['local_path']).read_bytes()) != item['sha256']:
            raise ValueError('media_hash_mismatch')
    sections, records = [], []
    for room in rooms:
        figures, room_media = [], []
        token = PLAN_NAMES.get(room['name'])
        plans = [a for a in assets if token and token in urlsplit(a['url']).path and a['kind'] == 'floorplan_candidate']
        selected = [(a['url'], '完整布局图候选 · 楼盘页标签关联') for a in plans]
        selected += [(a['url'], '房型图库 · 尚待内容分类') for a in room['photos']]
        seen = set()
        for url, label in selected:
            item = downloaded.get(url)
            if not item or item['sha256'] in seen:
                continue
            seen.add(item['sha256'])
            review = reviews.get(item['sha256'])
            if review:
                label = {'interior': '室内图 · 助手复核，非实况证明',
                         'interior_with_person': '生活方式图片 · 不计入核心室内图',
                         'floorplan_cropped': '裁切户型缩略图 · 不作为完整布局图',
                         'floorplan': '完整布局图 · 无尺寸标注'}[review['category']]
            elif '-fp' in urlsplit(url).path.lower():
                label = '户型图候选 · 关联及裁切待审核'
            path = Path(os.path.relpath(media / item['local_path'], source)).as_posix()
            caption = f'{label} · {item["width"]} × {item["height"]}'
            figures.append(f'<figure><a href="{escape(path, quote=True)}" target="_blank"><img src="{escape(path, quote=True)}" alt="{escape(room["name"] + " - " + label, quote=True)}" loading="lazy"></a><figcaption>{escape(caption)} · {link(url, "原图来源")}</figcaption></figure>')
            room_media.append({**item, 'preview_label': label, 'review': review, 'human_approved': False})
        offers = ''.join('<tr>' + ''.join('<td>' + escape(str(v)) + '</td>' for v in (
            o['amount'], '每周' if o['period'] == 'week' else '周期待确认',
            '每人' if o['basis'] == 'person' else '待确认', o['lease_label'],
            (o['default_start'] or '未知') + ' / ' + (o['default_end'] or '未知'))) + '</tr>' for o in room['offers'])
        prices = ('<div class="scroll"><table><thead><tr><th>金额 $</th><th>周期</th><th>计价对象</th><th>租期方案</th><th>页面默认起止日期</th></tr></thead><tbody>' + offers + '</tbody></table></div>') if offers else '<p class="notice">当前页面未提取到报价；不沿用旧价格，也不代表租金为零。</p>'
        area = str(room['area_sqm']) + ' m²' if room['area_sqm'] is not None else '未知'
        scope = {'bedroom': '单间卧室面积，非整套', 'studio': 'Studio 面积', 'unknown': '口径未知'}[room['area_scope']]
        features = ' · '.join(room['room_features']) or '未提取到设施信息'
        tours = ' / '.join(link(u, 'VR ' + str(i+1)) for i, u in enumerate(room['vr_links'])) or '未发现 VR 入口'
        sections.append(f'''<section id="{escape(room['id'])}"><h2>{escape(room['name'])}</h2>
<p class="metadata">{escape(area)} · {escape(scope)} · {escape(room['bedding'] or '床型未知')} · {escape(room['max_guests_raw'] or '人数未知')}</p>
<p>{link(room['source_url'], '房型原始页面')} · {tours}</p>{prices}
<details><summary>房间设施与采集信息</summary><p>{escape(features)}</p><p>采集时间：{escape(room['retrieved_at'])}</p><p>房型 ID：{escape(room['id'])}</p></details>
<div class="gallery">{''.join(figures) or '<p>暂无下载成功的图片。</p>'}</div></section>''')
        records.append({'room_id': room['id'], 'media': room_media, 'production_import_allowed': False})
    summary = {'room_types': len(rooms), 'offers': sum(len(r['offers']) for r in rooms),
               'rooms_with_offers': sum(bool(r['offers']) for r in rooms),
               'planned_media': len(outcomes), 'downloaded_media': len(downloaded),
               'unique_content_hashes': len({a['sha256'] for a in downloaded.values()}),
               'failed_media': len(outcomes)-len(downloaded), 'video_files': 0,
               'vr_links': len({u for r in rooms for u in r['vr_links']}),
               'rights_status': 'unknown', 'publication_status': 'not_released'}
    nav = ''.join(f'<a href="#{escape(r["id"])}">{escape(r["name"])}</a>' for r in rooms)
    html = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UniLodge Flagstaff | 采集结果</title><style>
*{box-sizing:border-box}body{margin:0;background:#fafbfc;color:#20272b;font:15px/1.6 system-ui,"Microsoft YaHei",sans-serif;letter-spacing:0}
main{max-width:1240px;margin:auto;padding:30px 24px}h1{font-size:30px;line-height:1.25;margin:0 0 10px}h2{font-size:23px;margin:0 0 8px}
a{color:#006d77;overflow-wrap:anywhere}header{border-bottom:2px solid #253c43;padding-bottom:22px}nav{display:flex;gap:10px 24px;flex-wrap:wrap;padding:20px 0;border-bottom:1px solid #d8dee3}
section{padding:30px 0;border-bottom:1px solid #d8dee3;scroll-margin-top:20px}.metadata{color:#525f68}.notice{color:#704515;background:#fff4dd;padding:12px;border-left:3px solid #b88028}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:630px;margin:16px 0}td,th{text-align:left;padding:10px 12px;border-bottom:1px solid #d8dee3}th{background:#edf1f4;font-weight:600}
.gallery{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;margin-top:22px}figure{margin:0;min-width:0}figure img{display:block;width:100%;aspect-ratio:16/10;object-fit:contain;background:#fff;border:1px solid #e1e5e8}figcaption{font-size:13px;padding-top:7px;color:#55616b;overflow-wrap:anywhere}summary{cursor:pointer}details{margin:15px 0}p{overflow-wrap:anywhere}footer{padding:20px 0;color:#56636c}
@media(max-width:850px){.gallery{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:560px){main{padding:22px 16px}.gallery{grid-template-columns:1fr}h1{font-size:26px}}
</style></head><body><main><header><h1>UniLodge Melbourne Flagstaff</h1>
<p>公开页面采集快照 · 学生公寓房型</p>'''
    html += f'<p>{summary["room_types"]} 个房型 · {summary["offers"]} 条报价 · {summary["downloaded_media"]}/{summary["planned_media"]} 个图片文件 · {summary["vr_links"]} 个 VR 入口</p>'
    html += '<p class="notice">本地研究样例，内容复用权限未确认，未公开发布。图库为样板间/示意内容，不代表具体房号现状。$ 的币种仍待确认；页面默认日期不等于已确认合同。VR 不是已下载的视频文件。</p></header><nav>' + nav + '</nav>' + ''.join(sections)
    html += '<footer><a href="room_types.json">房型 JSON</a> · <a href="preview_summary.json">采集统计</a> · <a href="preview_media.json">媒体追溯记录</a></footer></main></body></html>'
    (source / 'preview.html').write_text(html, encoding='utf-8')
    write_json(source / 'preview_media.json', records)
    write_json(source / 'preview_summary.json', summary)
    write_json(source / 'preview_manifest.json', {'script_sha256': digest(Path(__file__).read_bytes()),
        'inputs': {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in (source / 'room_types.json', source / 'media_candidates.json', media / 'outcomes.json', ROOT / 'scripts/data_analysis/source_fit_reviews.json')},
        'outputs': {n: digest((source / n).read_bytes()) for n in ('preview.html', 'preview_media.json', 'preview_summary.json')}})
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--media', type=Path, required=True)
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args()
    if args.fetch:
        run(args.media.resolve(), targets(args.source.resolve()))
    render(args.source.resolve(), args.media.resolve())
