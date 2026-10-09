"""Bounded public API collection of indoor repair question/photo pairs."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from html import escape, unescape
import json
from pathlib import Path
import time
from urllib.parse import urlencode, urlsplit

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw
from collect import Fetcher, digest, write_json
from verify_general_housing import run

ROOT = Path('data/collection-pilot/indoor-repair-20261009')
QUERIES = {
    'pipe_leak': ('管道漏水', 'sink pipe leak'),
    'drain_blockage': ('排水堵塞', 'sink clogged'),
    'light_fault': ('灯具异常', 'light fixture not working'),
    'socket_damage': ('插座损伤', 'outlet burnt'),
    'door_fault': ('门锁与门闩异常', 'door latch stuck'),
    'appliance_leak': ('家电漏水', 'washing machine leak'),
}


def discover():
    ROOT.mkdir(parents=True, exist_ok=False)
    (ROOT / 'raw').mkdir()
    client = Fetcher(hosts={'api.stackexchange.com'})
    records, targets, seen = [], [], set()
    try:
        for category, (label, query) in QUERIES.items():
            url = 'https://api.stackexchange.com/2.3/search/advanced?' + urlencode({
                'site': 'diy', 'filter': 'withbody', 'q': query, 'sort': 'relevance', 'pagesize': 20})
            _, status, _, body = client.get(url)
            (ROOT / 'raw' / (category + '.json')).write_bytes(body)
            if status != 200:
                raise ValueError(f'api_http_{status}')
            data = json.loads(body)
            if data.get('error_id'):
                raise ValueError(str(data))
            if data.get('backoff'):
                time.sleep(data['backoff'])
            count = 0
            for q in data.get('items', []):
                soup = BeautifulSoup(q.get('body', ''), 'html.parser')
                text = soup.get_text(' ', strip=True)
                if any(s in text.lower() for s in ['not my photo', 'not mine', 'google image', 'stock photo']):
                    continue
                images = []
                for im in soup.find_all('img', src=True):
                    src = im['src']
                    if urlsplit(src).scheme != 'https' or urlsplit(src).hostname != 'i.sstatic.net' or src in seen:
                        continue
                    images.append((src, im.get('alt', '')))
                if not images or q['question_id'] in {r['question_id'] for r in records}:
                    continue
                row = {'question_id': q['question_id'], 'category': category, 'category_zh': label,
                       'title': unescape(q['title']), 'reported_symptom': text, 'source_url': q['link'],
                       'author': q.get('owner', {}).get('display_name'),
                       'author_url': q.get('owner', {}).get('link'), 'content_license': q.get('content_license'),
                       'created_at_unix': q['creation_date'], 'raw_path': 'raw/' + category + '.json',
                       'raw_sha256': digest(body), 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                       'evidence_level': 'user_report_with_associated_photos_not_verified_diagnosis',
                       'image_ownership_review': 'pending_originality_check', 'actual_work_order': False,
                       'visual_review': 'pending', 'country': None}
                records.append(row)
                for i, (src, alt) in enumerate(images[:min(2, 6-count)]):
                    targets.append({'id': f"{q['question_id']}-{i}", 'question_id': q['question_id'],
                                    'category': category, 'kind': 'image', 'url': src, 'alt': alt,
                                    'source_url': q['link'], 'role': 'reported_fault_context_candidate'})
                    seen.add(src)
                    count += 1
                if count >= 6:
                    break
            print(category, count, flush=True)
            if data.get('quota_remaining', 1) <= 0:
                break
    finally:
        client.close()
        write_json(ROOT / 'records.json', records)
        write_json(ROOT / 'targets.json', targets)


def download():
    targets = json.loads((ROOT / 'targets.json').read_text(encoding='utf-8'))
    for offset in range(0, len(targets), 20):
        folder = ROOT / 'media' / f'{offset:03d}'
        if folder.exists():
            raise ValueError('existing_batch_do_not_refetch')
        run(targets[offset:offset+20], folder)
        results = json.loads((folder / 'outcomes.json').read_text(encoding='utf-8'))
        if any('host_forbidden' in r.get('error', '') or 'host_rate_limited' in r.get('error', '') for r in results):
            break


def export():
    records = json.loads((ROOT / 'records.json').read_text(encoding='utf-8'))
    assets = []
    for p in sorted((ROOT / 'media').glob('*/outcomes.json')):
        for a in json.loads(p.read_text(encoding='utf-8')):
            if a['status'] == 'success':
                a['local_path'] = (p.parent / a['local_path']).relative_to(ROOT).as_posix()
            assets.append(a)
    md = ['# 室内日常报修图文候选', '', '原帖报告的症状与现场图关联，不是已确认诊断或真实维修工单。地区未确认，不冒充澳洲案例。', '']
    blocks = []
    for r in records:
        version = (r.get('content_license') or '').removeprefix('CC BY-SA ')
        r['license_url'] = f'https://creativecommons.org/licenses/by-sa/{version}/' if version in {'2.5', '3.0', '4.0'} else None
        r['assets'] = [a for a in assets if a['question_id'] == r['question_id'] and a['status'] == 'success']
        label = f"{r['category_zh']} | {r['title']}"
        credit = f"{r['author']} | {r['content_license']}"
        md += [f'## {label}', f"[{credit}]({r['source_url']})", '']
        if r['license_url']:
            md += [f"[帖子许可说明]({r['license_url']})；图片原创性仍待确认。", '']
        blocks.append(f'<section><h2>{escape(label)}</h2><a href="{escape(r["source_url"])}">{escape(credit)}</a><p>{escape(r["reported_symptom"])}</p><div class="gallery">')
        if r['license_url']:
            blocks.append(f'<a href="{escape(r["license_url"])}">帖子许可说明（图片原创性待确认）</a>')
        for a in r['assets']:
            md += [f"![{a['id']}](<{(ROOT/a['local_path']).resolve().as_posix()}>)", '']
            blocks.append(f'<figure><img src="{escape(a["local_path"])}"><figcaption>{escape(a["id"])}</figcaption></figure>')
        if not r['assets']:
            md += ['图片未下载成功。', '']
        blocks.append('</div></section>')
    write_json(ROOT / 'dataset.json', records)
    write_json(ROOT / 'summary.json', {'posts': len(records), 'downloaded_images': sum(len(r['assets']) for r in records),
                                     'by_category': dict(Counter(a['category'] for a in assets if a['status']=='success'))})
    (ROOT / 'preview.md').write_text('\n'.join(md), encoding='utf-8')
    (ROOT / 'index.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>室内报修候选</title><style>body{font:16px sans-serif;margin:24px}h2{font-size:20px}section{border-top:1px solid #bbb;padding:20px 0}p{overflow-wrap:anywhere}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr));gap:12px}figure{margin:0}img{width:100%;height:300px;object-fit:contain}</style><h1>室内报修图文候选</h1><p>用户报告＋关联照片，诊断及图片原创性待核实。保持原作者与许可，非澳洲特定案例，非维修操作建议。</p>'+''.join(blocks), encoding='utf-8')
    for category in QUERIES:
        group = [a for a in assets if a['category'] == category and a['status']=='success']
        if not group:
            continue
        sheet = Image.new('RGB', (1200, 650), 'white')
        draw = ImageDraw.Draw(sheet)
        for i, a in enumerate(group):
            with Image.open(ROOT/a['local_path']) as im:
                im.thumbnail((390, 285))
                sheet.paste(im, ((i%3)*400, (i//3)*325+30))
            draw.text(((i%3)*400+4,(i//3)*325+8), a['id'], fill='black')
        sheet.save(ROOT/(category+'-review.jpg'))
    write_json(ROOT / 'manifest.json', {p.relative_to(ROOT).as_posix():digest(p.read_bytes()) for p in ROOT.rglob('*') if p.is_file() and p.name!='manifest.json'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['discover','download','export'])
    args = parser.parse_args()
    globals()[args.phase]()
