"""Create a portable, attributed repair collection while preserving raw batches."""
from collections import Counter
from html import escape
import json
from pathlib import Path
import shutil
from PIL import Image
from collect import digest, write_json

BASE = Path('data/collection-pilot')
OUT = BASE / 'repair-integrated-20261009'
KEEP_NEW = {'276839-0', '276839-1', '103738-0', '200955-0', '271554-0',
            '147127-0', '298906-0', '298906-1'}


def main():
    OUT.mkdir(exist_ok=False)
    (OUT / 'images').mkdir()
    rows, excluded, supplementary, seen = [], [], [], set()

    def add(asset, parent, folder, group):
        src = folder / asset['local_path']
        sha = digest(src.read_bytes())
        assert sha == asset['sha256'], src
        with Image.open(src) as im:
            im.verify()
        if sha in seen:
            excluded.append({'source_asset': str(src), 'reason': 'exact_duplicate'})
            return
        seen.add(sha)
        name = f'{group}-{asset["id"]}{src.suffix}'
        target = OUT / 'images' / name
        shutil.copy2(src, target)
        evidence = asset.get('evidence_level', 'user_report_not_verified_diagnosis')
        if group == 'building':
            evidence = 'source_dataset_category_with_basic_visual_review'
        row = {
            'id': f'{group}-{asset["id"]}', 'group': group,
            'category': parent['category'], 'category_zh': parent['category_zh'],
            'title': parent.get('title', parent['category_zh']),
            'reported_symptom': parent.get('reported_symptom'),
            'display_label': parent['category_zh'], 'label_basis': evidence,
            'demo_status': '待维修（演示设定）', 'demo_status_is_synthetic': True,
            'actual_work_order': False, 'diagnosis_confirmed': False,
            'source_url': parent['source_url'], 'image_url': asset['url'],
            'author': parent.get('author'), 'content_license': parent.get('content_license'),
            'license_url': parent.get('license_url'),
            'image_rights_status': 'not_independently_verified',
            'source_record_file': str((folder / ('clean.json' if (folder/'clean.json').exists() else 'dataset.json')).resolve()),
            'source_image_path': str(src.resolve()),
            'review_note': parent.get('review_note', parent.get('match_note', '现场设备或部件照片；故障依据原帖，不要求照片直接展示故障。')),
            'local_path': 'images/' + name, 'sha256': sha, 'country': parent.get('country'),
        }
        if asset.get('clarity') == 'low_supplementary':
            supplementary.append(row)
        else:
            rows.append(row)

    for name in ['indoor-repair-20261009', 'used-fixtures-20261009', 'used-toilets-20261009']:
        folder = BASE / name
        filename = 'clean.json' if name.startswith('indoor') else 'dataset.json'
        for parent in json.loads((folder / filename).read_text(encoding='utf-8')):
            for asset in parent['assets']:
                if not name.startswith('indoor') and asset['id'] not in KEEP_NEW:
                    excluded.append({'source_batch': name, 'id': asset['id'],
                                     'reason': '非目标设备现场图、近重复图或新装设备，保留在原始批次。'})
                    continue
                add(asset, parent, folder, 'indoor')
    folder = BASE / 'repair-bd3-20261005'
    for asset in json.loads((folder / 'clean.json').read_text(encoding='utf-8')):
        if asset['category'] == 'Algae':
            excluded.append({'source_batch': folder.name, 'id': asset['id'], 'reason': '按用户要求移除藻斑；仅原始批次留档。'})
            continue
        add(asset, asset, folder, 'building')
    assert not any(r['category'] == 'Algae' for r in rows + supplementary)
    assert len({r['sha256'] for r in rows + supplementary}) == len(rows + supplementary)
    counts = Counter(r['category_zh'] for r in rows)
    summary = {'main_images': len(rows), 'supplementary_images': len(supplementary),
               'by_group': dict(Counter(r['group'] for r in rows)), 'by_category': dict(counts),
               'new_selected_images': len(KEEP_NEW), 'removed_algae_images': 5,
               'all_local_images_decode_and_sha256_verified': True}
    write_json(OUT / 'dataset.json', rows)
    write_json(OUT / 'supplementary.json', supplementary)
    write_json(OUT / 'excluded.json', excluded)
    write_json(OUT / 'summary.json', summary)
    intro = f'主样本 {len(rows)} 张，偏暗补充图 {len(supplementary)} 张。藻斑已从整合版移除，原始采集留档。故障标签来自原帖报告或原数据集；“待维修”仅为演示状态，不是真实工单。图片不必直接显示损坏，不据此确认诊断。设备使用年限未知，新增样本排除了明确新装设备。'
    md = ['# 维修图片整合预览', '', intro, '', '## 分类数量', '']
    md += [f'- {k}：{v} 张' for k, v in counts.items()]
    blocks = []
    for group, title in [('indoor', '室内日常报修'), ('building', '墙面缺陷补充')]:
        md += ['', '## ' + title, '']
        blocks.append('<h2>' + title + '</h2>')
        for r in rows:
            if r['group'] != group:
                continue
            credit = (r['author'] or 'BD3 Dataset') + ' | ' + (r['content_license'] or '许可待确认')
            md += [f"### {r['category_zh']} · {r['id']}", r['review_note'],
                   f"[{credit}]({r['source_url']})", f"![{r['id']}](<{(OUT/r['local_path']).resolve().as_posix()}>)", '']
            if r['license_url']:
                md += [f"[帖子许可]({r['license_url']})", '']
            blocks.append(f'<section><h3>{escape(r["category_zh"])} · {escape(r["id"])}</h3><p>{escape(r["title"])}</p><p>{escape(r["review_note"])}</p><a href="{escape(r["source_url"])}">{escape(credit)}</a>')
            if r['license_url']:
                blocks.append(f'<a href="{escape(r["license_url"])}"> · 帖子许可</a>')
            blocks.append(f'<div><img loading="lazy" src="{escape(r["local_path"])}" alt="{escape(r["category_zh"])}"></div></section>')
    (OUT / 'preview.md').write_text('\n'.join(md), encoding='utf-8')
    (OUT / 'index.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>维修整合预览</title><style>body{font:16px sans-serif;max-width:960px;margin:24px auto;padding:0 16px;overflow-wrap:anywhere}section{border-top:1px solid #ddd;padding:16px 0}h3{font-size:18px}img{width:640px;max-width:100%;height:360px;object-fit:contain}</style><h1>维修图片整合预览</h1><p>'+escape(intro)+'</p><p>保留原作者与许可信息。帖子许可不保证全部插图原创，BD3许可尚未确认；非澳洲专属样本，不作为维修操作指导。</p>'+''.join(blocks), encoding='utf-8')
    (OUT / 'README.md').write_text('# 维修整合数据\n\n'+intro+'\n\n- dataset.json：主样本，每行一张图，保留类别、原文、来源、标签依据。\n- images/：本地图片，可与整合目录一起搬运。\n- supplementary.json：偏暗图片，不计入主样本。\n- excluded.json：本次整合排除项；早期筛除项见原批次。\n- preview.md / index.html：图文预览。\n- 原始数据保留在相邻的 indoor-repair、used-fixtures、used-toilets、repair-bd3 批次目录。\n\n不得把演示状态解释成来源已确认的故障；未绑定真实房源或租户，未导入生产数据库。\n', encoding='utf-8')
    write_json(OUT / 'manifest.json', {p.relative_to(OUT).as_posix(): digest(p.read_bytes()) for p in OUT.rglob('*') if p.is_file() and p.name != 'manifest.json'})
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
