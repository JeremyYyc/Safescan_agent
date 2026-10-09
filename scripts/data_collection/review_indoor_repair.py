"""Export the manually reviewed indoor repair subset without changing raw data."""
from collections import Counter
from html import escape
import json
from PIL import Image
from collect import digest, write_json
from indoor_repair_collect import ROOT, QUERIES

HELD = {
    '152547-0': '室外门廊灯故障，非本批室内灯具主样本。',
    '152547-1': '室外门廊灯故障，非本批室内灯具主样本。',
    '313310-1': '湿度曲线截图，不是门锁现场照片。',
    '132007-0': '门铰链照片，不直接展示门闩。',
    '278029-1': '供水表与管路背景，不直接展示排水问题。',
    '94434-0': '软管尺寸测量，保留连接处照片即可。',
}
NOTES = {
    'pipe_leak': '管道及接头照片与漏水帖子对应；不保证每张可见滴水。',
    'drain_blockage': '水槽或排水管照片；排水不畅依据原帖，照片不能确认堵塞原因。',
    'light_fault': '灯具拆卸或接线状态；不亮依据原帖，不能仅凭照片确认故障原因。',
    'socket_damage': '前五张可见明显焦黑或熔损；77410-0仅作线缆部位背景，不确认烧损。',
    'door_fault': '门闩或锁具拆卸状态；卡住或结冰依据原帖，不是经验证的诊断。',
    'appliance_leak': '洗衣机、软管连接或阀门照片；不能一律标成机器本体损坏。',
}


def main():
    records = json.loads((ROOT / 'dataset.json').read_text(encoding='utf-8'))
    clean, held, hashes = [], [], []
    for row in records:
        selected = []
        for asset in row['assets']:
            path = ROOT / asset['local_path']
            assert digest(path.read_bytes()) == asset['sha256'], path
            with Image.open(path) as im:
                im.verify()
            hashes.append(asset['sha256'])
            asset['visual_review'] = 'contact_sheet_review_2026-10-09'
            if asset['id'] in HELD:
                held.append({**asset, 'held_reason': HELD[asset['id']]})
            else:
                asset['review_note'] = NOTES[row['category']]
                asset['evidence_level'] = 'reported_symptom_context'
                if row['category'] == 'socket_damage' and asset['id'] != '77410-0':
                    asset['evidence_level'] = 'visible_discoloration_or_material_damage_cause_unconfirmed'
                selected.append(asset)
        if selected:
            clean.append({**row, 'assets': selected, 'visual_review': 'basic_type_context_match',
                          'review_note': NOTES[row['category']],
                          'category_zh': '排水不畅' if row['category']=='drain_blockage' else row['category_zh']})
    counts = Counter(a['category'] for r in clean for a in r['assets'])
    summary = {'raw_posts': len(records), 'raw_images': len(hashes), 'unique_image_hashes': len(set(hashes)),
               'selected_posts': len(clean), 'selected_images': sum(counts.values()),
               'held_images': len(held), 'selected_by_category': dict(counts),
               'below_five_images': [c for c in QUERIES if counts[c] < 5],
               'scope': 'Basic symptom/photo association only; not certified fault diagnosis or actual work orders.'}
    write_json(ROOT / 'clean.json', clean)
    write_json(ROOT / 'held_out.json', held)
    write_json(ROOT / 'review_summary.json', summary)
    intro = '室内日常报修：23 条原帖、36 张原图；初筛保留 22 条、30 张，6 张留作补充。按原帖症状关联，不等于确诊；来源地区不统一，不作为澳洲电气规范参考。帖子许可不保证所有插图原创，图片权属仍需确认。'
    md = ['# 室内日常报修预览', '', intro, '', '[原始图文预览](preview.md)', '']
    blocks = []
    for r in clean:
        label = r['category_zh'] + ' | ' + r['title']
        md += ['## ' + label, r['review_note'], f"[原帖及作者：{r['author']}]({r['source_url']})", f"[{r['content_license']}]({r['license_url']})", '']
        blocks.append(f'<section><h2>{escape(label)}</h2><p>{escape(r["review_note"])}</p><a href="{escape(r["source_url"])}">{escape(r["author"] or "Unknown")}: 原帖</a> · <a href="{escape(r["license_url"] or r["source_url"])}">{escape(r["content_license"] or "Unknown")}</a><div>')
        for a in r['assets']:
            md += [f"![{a['id']}](<{(ROOT/a['local_path']).resolve().as_posix()}>)", '']
            blocks.append(f'<img src="{escape(a["local_path"])}" alt="{escape(a["id"])}" loading="lazy">')
        blocks.append('</div></section>')
    (ROOT / 'reviewed-preview.md').write_text('\n'.join(md), encoding='utf-8')
    (ROOT / 'reviewed.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>室内报修初筛</title><style>body{font:16px sans-serif;margin:24px;overflow-wrap:anywhere}section{border-top:1px solid #bbb;padding:20px 0}h2{font-size:20px}section div{display:flex;flex-wrap:wrap;gap:12px}img{width:460px;max-width:100%;height:320px;object-fit:contain}</style><h1>室内日常报修初筛</h1><p>'+escape(intro)+'</p>'+''.join(blocks), encoding='utf-8')
    write_json(ROOT / 'manifest.json', {p.relative_to(ROOT).as_posix():digest(p.read_bytes()) for p in ROOT.rglob('*') if p.is_file() and p.name!='manifest.json'})
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
