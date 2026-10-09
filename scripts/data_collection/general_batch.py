"""Collect explicitly linked media, then export provisional cleaning separately."""
import argparse
from collections import Counter
from html import escape
import json
from pathlib import Path

from bs4 import BeautifulSoup
from collect import digest, write_json
from verify_general_housing import run


def select_media(listing, gallery_limit=None):
    plans = [('layout_candidate', m['contentUrl']) for m in listing.get('associatedMedia', [])
             if 'floorplan' in m.get('name', '').lower() and m.get('contentUrl')]
    gallery = [('gallery_candidate', m['url']) for m in listing.get('image', []) if isinstance(m, dict) and m.get('url')]
    return plans + (gallery if gallery_limit is None else gallery[:gallery_limit]), len(plans) + len(gallery)


def prepare(root, gallery_limit=None):
    rows, targets = [], []
    for page in json.loads((root / 'pages/outcomes.json').read_text(encoding='utf-8')):
        row = {**page, 'visual_status': 'pending', 'quality_accepted': False,
               'rights_status': 'unknown', 'release_approved': False}
        if page['status'] != 'success':
            rows.append(row)
            continue
        body = (root / 'pages' / page['local_path']).read_bytes()
        if digest(body) != page['sha256']:
            raise ValueError('page_hash_mismatch')
        soup = BeautifulSoup(body, 'html.parser')
        listing = None
        for script in soup.find_all('script', type='application/ld+json'):
            data = json.loads(script.text)
            for node in data.get('@graph', [data]):
                if node.get('@type') == 'RealEstateListing':
                    listing = node
                    break
        if listing is None:
            row['parse_error'] = 'listing_jsonld_missing'
            rows.append(row)
            continue
        row.update(address=soup.h1.get_text(' ', strip=True) if soup.h1 else listing['name'],
                   property_type=listing.get('additionalType'), description=listing.get('description'),
                   offer=listing.get('offers'), page_title=soup.title.get_text() if soup.title else '',
                   source_modified_at=listing.get('dateModified'))
        desc = (row.get('description') or '').lower()
        row['flags'] = []
        if 'illustration' in desc or 'indicative' in desc:
            row['flags'].append('illustrative_media_disclaimer_review_required')
        if 'virtually staged' in desc or 'ai-generated' in desc:
            row['flags'].append('virtual_staging_or_ai_disclaimer_review_required')
        if 'leased' in row['page_title'].lower():
            row['flags'].append('historical_leased_not_current_offer')
        if row['address'].lower().startswith('id:'):
            row['flags'].append('listing_id_must_not_be_treated_as_unit_number')
        media, linked_count = select_media(listing, gallery_limit)
        row['linked_media_count'] = linked_count
        row['selected_media_count'] = len(media)
        row['selection_policy'] = 'all_linked_plans_and_first_gallery_candidates' if gallery_limit is not None else 'all_linked_media'
        row['gallery_limit'] = gallery_limit
        row['linked_layout_count'] = sum(role == 'layout_candidate' for role, _ in media)
        for i, (role, url) in enumerate(media):
            targets.append({'id': page['id'] + '-' + str(i), 'sample_id': page['id'],
                            'kind': 'image', 'role': role, 'url': url,
                            'listing_url': page['url'], 'source_html_sha256': page['sha256']})
        rows.append(row)
    if len(targets) > 120:
        raise ValueError('batch_exceeds_120_image_budget')
    write_json(root / 'raw_records.json', rows)
    write_json(root / 'media_targets.json', targets)
    return rows, targets


def export(root, rows):
    assets = []
    for path in sorted((root / 'media').glob('*/outcomes.json')):
        for item in json.loads(path.read_text(encoding='utf-8')):
            item = dict(item)
            if item['status'] == 'success':
                local = path.parent / item['local_path']
                if digest(local.read_bytes()) != item['sha256']:
                    raise ValueError('media_hash_mismatch')
                item['local_path'] = local.relative_to(root).as_posix()
            assets.append(item)
    seen, clean, audit = {}, [], []
    for row in rows:
        row = dict(row)
        key = ' '.join(row.get('address', row['url']).casefold().split())
        if key in seen:
            audit.append({'id': row['id'], 'action': 'duplicate', 'duplicate_of': seen[key]})
            continue
        seen[key] = row['id']
        linked = [a for a in assets if a['sample_id'] == row['id']]
        successful = [a for a in linked if a['status'] == 'success']
        row['assets'] = successful
        row['failed_assets'] = [a for a in linked if a['status'] != 'success']
        row['download_complete'] = len(successful) == row.get('linked_media_count', -1)
        row['selected_download_complete'] = len(successful) == row.get('selected_media_count', row.get('linked_media_count', -1))
        row['candidate_pair_present'] = any(a['role'] == 'layout_candidate' for a in successful) and any(a['role'] == 'gallery_candidate' for a in successful)
        row['cleaning_stage'] = 'structural_only_visual_review_pending'
        clean.append(row)
        audit.append({'id': row['id'], 'action': 'retain_pending_visual_review', 'flags': row.get('flags', []),
                      'download_complete': row['download_complete'], 'image_deduplication': 'sha256_index_only_no_raw_deletion'})
    (root / 'clean').mkdir(exist_ok=True)
    write_json(root / 'clean/provisional.json', clean)
    write_json(root / 'clean/audit.json', audit)
    hash_index = {}
    for a in assets:
        if a['status'] == 'success':
            hash_index.setdefault(a['sha256'], []).append(a['id'])
    write_json(root / 'clean/shared_media.json', {k: v for k, v in hash_index.items() if len(v) > 1})
    summary = {'candidate_properties': len(rows), 'pages_saved': sum(r['status'] == 'success' for r in rows),
               'unique_candidate_properties': len(clean),
               'unique_properties': sum(bool(r.get('address')) for r in clean),
               'failed_or_unparsed_properties': sum(not r.get('address') for r in clean),
               'linked_images': sum(r.get('linked_media_count', 0) for r in rows),
               'saved_images': sum(a['status'] == 'success' for a in assets),
               'selected_images': sum(r.get('selected_media_count', r.get('linked_media_count', 0)) for r in rows),
               'selected_download_complete_properties': sum(r['selected_download_complete'] for r in clean),
               'failed_images': sum(a['status'] != 'success' for a in assets),
               'all_linked_media_downloaded_properties': sum(r['download_complete'] for r in clean),
               'layout_gallery_candidate_pairs': sum(r['candidate_pair_present'] for r in clean),
               'new_visually_accepted_samples': 0,
               'candidate_by_city': dict(Counter(r['city'] for r in clean)),
               'by_city': dict(Counter(r['city'] for r in clean if r.get('address'))),
               'rights_status': 'unknown', 'authorization': 'user_authorized_operation_not_platform_license',
               'full_site_capacity': 'unknown_no_extrapolation_from_this_selected_batch'}
    write_json(root / 'summary.json', summary)
    sections = []
    for row in clean:
        gallery = ''.join('<figure><a href="'+escape(a['local_path'])+'"><img loading="lazy" src="'+escape(a['local_path'])+'"></a><figcaption>'+escape(a['id']+' | '+a['role'])+'</figcaption></figure>' for a in row['assets'])
        raw_link = '<a href="pages/'+escape(row['local_path'])+'">Raw HTML</a>' if row.get('local_path') else '<p>'+escape(row.get('error', 'No saved page'))+'</p>'
        sections.append('<section><h2>'+escape(row.get('address', row['id']))+'</h2><p>'+escape(row.get('page_title', ''))+'</p><p>'+escape(', '.join(row.get('flags', [])))+'</p><p>Visual review pending; not accepted.</p>'+raw_link+'<details open><summary>Photos and floorplans</summary><div class="gallery">'+gallery+'</div></details></section>')
    html = '<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Housing batch</title><style>body{font:15px system-ui;max-width:1200px;margin:auto;padding:20px;letter-spacing:0;background:#fafafa;color:#222}section{padding:20px 0;border-top:1px solid #aaa}h1{font-size:26px}h2{font-size:20px}p{overflow-wrap:anywhere}a{color:#17674e}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(260px,100%),1fr));gap:16px}figure{margin:0}img{width:100%;height:230px;object-fit:contain}summary{cursor:pointer;padding:12px}pre{white-space:pre-wrap}</style><h1>Housing batch: Raw / Provisional</h1><p>All downloaded original files retained. Selected gallery images remain interior candidates until visual review. Structural cleaning only.</p><nav><a href="raw_records.json">Raw extracted records</a> | <a href="clean/provisional.json">Provisional cleaned records</a> | <a href="clean/audit.json">Audit</a> | <a href="summary.json">Summary</a></nav><pre>'+escape(json.dumps(summary, indent=2))+'</pre>'+''.join(sections)+'</html>'
    document = BeautifulSoup(html, 'html.parser')
    statistics = document.find('pre')
    if statistics:
        details = document.new_tag('details')
        label = document.new_tag('summary')
        label.string = 'Collection statistics'
        details.append(label)
        statistics.wrap(details)
    (root / 'index.html').write_text(str(document), encoding='utf-8')
    preview = ['# Housing image preview', '', 'Visual review pending. Original files retained.', '']
    for row in clean:
        preview += ['## ' + row.get('address', row['id']), '']
        if not row['assets']:
            preview += ['No downloaded images: ' + row.get('error', 'pending'), '']
        for asset in row['assets']:
            absolute = (root / asset['local_path']).resolve().as_posix()
            preview += ['### ' + asset['role'], '', '![' + asset['id'] + '](<' + absolute + '>)', '']
    (root / 'preview.md').write_text('\n'.join(preview), encoding='utf-8')
    write_json(root / 'manifest.json', {p.relative_to(root).as_posix(): digest(p.read_bytes()) for p in sorted(root.rglob('*')) if p.is_file() and p != root / 'manifest.json'})
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--gallery-limit', type=int, choices=(1, 2))
    args = parser.parse_args()
    rows, targets = prepare(args.root, args.gallery_limit)
    print('Linked media:', len(targets), flush=True)
    for start in range(0, len(targets), 20):
        folder = args.root / 'media' / str(start).zfill(3)
        if folder.exists():
            raise ValueError('existing_media_batch_use_fresh_output')
        run(targets[start:start + 20], folder)
        outcomes = json.loads((folder / 'outcomes.json').read_text(encoding='utf-8'))
        if any(any(t in x.get('error', '') for t in ('host_forbidden', 'host_stopped', 'rate_limited', 'robots_')) for x in outcomes):
            print('Access stop: no further batches', flush=True)
            break
    export(args.root, rows)
