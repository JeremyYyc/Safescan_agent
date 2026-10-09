"""Export the prior light visual review without altering original downloads."""
import json
from pathlib import Path
from html import escape
from PIL import Image
from collect import digest, write_json

ROOT = Path('data/collection-pilot/repair-bd3-20261005')
LABELS = {
    'Algae': ('墙面藻斑', '可见绿色或深色附着斑块，不等同已鉴定的室内霉菌。'),
    'major crack': ('明显裂缝', '沿用来源分类，不据图片判断结构危险等级。'),
    'minor crack': ('细裂缝', '没有比例尺，不输出实际宽度或安全等级。'),
    'peeling': ('涂层剥落', '可见表面涂层缺失或翘起。'),
    'spalling': ('表层材料脱落', '可见材料缺失或基层暴露，其中1张偏暗仅作补充。'),
    'stain': ('墙面污渍与涂写', '包含划痕、涂写和染色，不标作漏水证据。'),
}


def main():
    rows = json.loads((ROOT / 'dataset.json').read_text(encoding='utf-8'))
    clean = []
    for r in rows:
        if r['status'] != 'success':
            continue
        p = ROOT / r['local_path']
        assert digest(p.read_bytes()) == r['sha256'], p
        with Image.open(p) as im:
            im.verify()
        label, note = LABELS[r['category']]
        clean.append({**r, 'category_zh': label, 'match_note': note,
                      'review_status': 'assistant_light_visual_match',
                      'reviewed_on': '2026-10-05', 'exported_on': '2026-10-09',
                      'clarity': 'low_supplementary' if r['id'] == 'cls05_060' else 'adequate_for_category_preview',
                      'usage_approved': False, 'actual_work_order': False,
                      'country': None, 'related_housing_id': None})
    write_json(ROOT / 'clean.json', clean)
    summary = {'downloaded_images': len(clean), 'unique_sha256': len({r['sha256'] for r in clean}),
               'review': 'Prior review of all 30 images in category contact sheets; light matching only',
               'rights_status': 'unknown_pending_permission', 'by_category': []}
    md = ['# 维修相关故障图例', '', '已下载30张，六类各5张；29张基本清晰，1张偏暗仅作补充。不是实际工单，不与房源关联，来源许可待确认。', '']
    blocks = []
    for category, (label, note) in LABELS.items():
        group = [r for r in clean if r['category'] == category]
        good = sum(r['clarity'] != 'low_supplementary' for r in group)
        summary['by_category'].append({'category': category, 'label': label, 'downloaded': len(group),
                                      'clear_examples': good, 'low_clarity_supplementary': len(group)-good,
                                      'five_clear_examples_met': good >= 5})
        md += [f'## {label}：{len(group)}张', note, '']
        blocks.append(f'<section><h2>{label}：{len(group)}张</h2><p>{note}</p><div class="gallery">')
        for r in group:
            caption = r['id'] + ('，偏暗，仅补充参考' if r['clarity'] == 'low_supplementary' else '')
            md += [f"![{caption}](<{(ROOT/r['local_path']).resolve().as_posix()}>)", caption, '']
            blocks.append(f'<figure><a href="{escape(r["local_path"])}"><img src="{escape(r["local_path"])}" alt="{escape(caption)}"></a><figcaption>{escape(caption)}</figcaption></figure>')
        blocks.append('</div></section>')
    md += ['来源：[BD3作者仓库](https://github.com/Praveenkottari/BD3-Dataset)。原始标签保留，中文名称及判读为本地整理。']
    (ROOT / 'preview.md').write_text('\n'.join(md), encoding='utf-8')
    (ROOT / 'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>故障图例</title><style>body{font:16px sans-serif;margin:24px}h2{font-size:21px}section{border-top:1px solid #ccc;padding:20px 0}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(240px,100%),1fr));gap:14px}figure{margin:0}img{width:100%;height:240px;object-fit:contain}</style><h1>维修相关故障图例</h1><p>已下载30张；29张基本清晰、1张偏暗。基本类型匹配，不是实际工单，不诊断原因或结构风险。来源许可待确认，未导入知识库。</p><p><a href="https://github.com/Praveenkottari/BD3-Dataset">BD3作者仓库</a> | <a href="clean.json">清理数据</a></p>'+''.join(blocks)+'</html>', encoding='utf-8')
    write_json(ROOT / 'review_summary.json', summary)
    write_json(ROOT / 'manifest.json', {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in ROOT.rglob('*') if p.is_file() and p.name != 'manifest.json'})
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
