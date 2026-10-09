"""Offline, non-destructive raw/clean comparison for the bounded housing pilot."""
import argparse
from collections import Counter
from html import escape
import json
from pathlib import Path
import shutil

from collect import ROOT, digest, write_json


def export(output):
    reviews = json.loads((ROOT / 'scripts/data_collection/general_housing_reviews.json').read_text(encoding='utf-8'))
    candidates = json.loads((ROOT / 'scripts/data_collection/alternative_platform_candidates.json').read_text(encoding='utf-8'))
    source = ROOT / reviews['evidence_root']
    output.mkdir(parents=True, exist_ok=False)
    # Preserve original bytes, including failed attempts and rejected media.
    shutil.copytree(source, output / 'raw')
    write_json(output / 'raw/candidates.json', candidates)
    write_json(output / 'raw/reviews.json', reviews)
    assets = {}
    for folder in ('media', 'hotham-remaining'):
        for asset in json.loads((source / folder / 'outcomes.json').read_text(encoding='utf-8')):
            if asset['status'] != 'success':
                continue
            local = Path('raw') / folder / asset['local_path']
            if digest((output / local).read_bytes()) != asset['sha256']:
                raise ValueError('hash_mismatch:' + asset['id'])
            if asset['id'] in assets:
                raise ValueError('duplicate_asset_id')
            assets[asset['id']] = {**asset, 'local_path': local.as_posix()}
    clean, pending, audit, assigned = [], [], [], set()
    (output / 'clean').mkdir()
    for result in reviews['results']:
        if result['decision'] != 'accepted_with_limitations':
            pending.append(result)
            continue
        row = {**result, 'quality_accepted': True, 'release_approved': False,
               'rights_status': reviews['rights_status'], 'assets': []}
        groups = [('layout', [result['plan']['asset_id']]),
                  ('interior', result['interior_asset_ids']),
                  ('context', result['context_asset_ids']),
                  ('advertisement', result.get('excluded_asset_ids', []))]
        for category, ids in groups:
            for aid in ids:
                if aid in assigned:
                    raise ValueError('duplicate_classification:' + aid)
                assigned.add(aid)
                asset = assets[aid]
                keep = category in ('layout', 'interior')
                audit.append({'sample_id': result['id'], 'asset_id': aid, 'category': category,
                              'included_in_clean': keep, 'reason': 'core_media' if keep else 'not_interior_or_layout',
                              'raw_path': asset['local_path'], 'sha256': asset['sha256']})
                if keep:
                    dest = Path('clean') / result['id'] / (aid + Path(asset['local_path']).suffix)
                    (output / dest).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(output / asset['local_path'], output / dest)
                    row['assets'].append({**asset, 'category': category, 'raw_path': asset['local_path'], 'local_path': dest.as_posix()})
        clean.append(row)
    if assigned != set(assets):
        raise ValueError('unclassified_assets')
    outcomes = json.loads((source / 'outcomes.json').read_text(encoding='utf-8'))
    summary = {'candidate_properties': len(reviews['results']),
               'downloaded_listing_pages': sum(x['kind'] == 'html' and x['status'] == 'success' for x in outcomes),
               'raw_images': len(assets), 'quality_accepted_properties': len(clean),
               'pending_properties': len(pending), 'clean_images': sum(len(x['assets']) for x in clean),
               'image_categories': dict(Counter(x['category'] for x in audit)),
               'rights_cleared_properties': 0,
               'scope_note': 'Bounded pilot only; not a site-wide inventory or unbiased yield estimate.',
               'collection_gate': {'Homely': 'hold_bulk_collection_pending_permission',
                                   'terms_url': 'https://www.homely.com.au/terms-of-use',
                                   'reviewed_on': '2026-10-01', 'clause': '4.1(h)'}}
    write_json(output / 'clean/dataset.json', clean)
    write_json(output / 'clean/pending.json', pending)
    write_json(output / 'clean/audit.json', audit)
    write_json(output / 'summary.json', summary)
    blocks = []
    for row in clean:
        gallery = ''.join('<figure><a href="'+escape(a['local_path'])+'"><img loading="lazy" src="'+escape(a['local_path'])+'"></a><figcaption>'+escape(a['id']+' | '+a['category'])+'</figcaption></figure>' for a in row['assets'])
        original = [a for a in audit if a['sample_id'] == row['id']]
        raw_gallery = ''.join('<figure><a href="'+escape(a['raw_path'])+'"><img loading="lazy" src="'+escape(a['raw_path'])+'"></a><figcaption>'+escape(a['asset_id']+' | '+a['category']+' | '+('KEEP' if a['included_in_clean'] else 'RAW ONLY'))+'</figcaption></figure>' for a in original)
        blocks.append('<section><h2>'+escape(row['address'])+'</h2><p>Quality accepted with limitations. Rights not cleared.</p><p>'+escape(json.dumps(row['offer'], ensure_ascii=False))+'</p><details open><summary>Clean media</summary><div class="gallery">'+gallery+'</div></details><details><summary>All raw media, including exclusions</summary><div class="gallery">'+raw_gallery+'</div></details></section>')
    pending_html = ''.join('<li>'+escape(x['address']+': '+x['reason'])+'</li>' for x in pending)
    html = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Housing: Raw and Clean</title><style>body{font:15px system-ui;margin:0;background:#fafafa;color:#202020;letter-spacing:0}main{max-width:1200px;margin:auto;padding:24px}h1{font-size:26px}h2{font-size:20px}a{color:#17674e}section{border-top:1px solid #bbb;padding:24px 0}p,li{overflow-wrap:anywhere;line-height:1.6}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(260px,100%),1fr));gap:16px}figure{margin:0}img{width:100%;height:240px;object-fit:contain;background:#eee}figcaption{font-size:12px;padding:6px 0}summary{cursor:pointer;padding:12px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><main><h1>Housing: Raw and Clean</h1>'''
    html += '<p>5 candidates | 3 saved pages | 26 raw images | 2 quality-accepted samples | 19 clean images | 3 pending</p>'
    html += '<p>Local review only. No redistribution or training clearance. Homely bulk collection on hold pending permission.</p>'
    html += '<nav><a href="raw/candidates.json">Original candidates</a> | <a href="raw/outcomes.json">Fetch outcomes</a> | <a href="clean/dataset.json">Clean dataset</a> | <a href="clean/audit.json">Cleaning audit</a> | <a href="summary.json">Summary</a></nav>'
    html += ''.join(blocks) + '<section><h2>Pending</h2><ul>'+pending_html+'</ul></section></main></html>'
    (output / 'index.html').write_text(html, encoding='utf-8')
    write_json(output / 'manifest.json', {p.relative_to(output).as_posix(): digest(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()})
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    export(parser.parse_args().output.resolve())
