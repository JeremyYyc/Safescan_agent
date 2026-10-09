"""Collect a bounded iFixit review batch, without importing business records."""
import argparse
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
from urllib.robotparser import RobotFileParser

from collect import Fetcher, USER_AGENT, digest, write_json
from verify_general_housing import run

TARGETS = [
    ('wall_hole', 104072), ('leaky_faucet', 39117),
    ('sink_blockage', 182837), ('toilet_flapper', 44146),
    ('loose_toilet_seat', 140776), ('washer_drain_access', 105443),
    ('door_lock_replacement', 67174),
]
LICENSE = 'https://creativecommons.org/licenses/by-nc-sa/3.0/'


def select_images(steps, limit=6):
    groups, seen = [], set()
    for step in steps:
        group = []
        media = step.get('media') or {}
        if media.get('type') != 'image':
            continue
        for im in media.get('data', []):
            url = im.get('large') or im.get('standard')
            key = im.get('guid') or url
            if not url or key in seen:
                continue
            seen.add(key)
            group.append({'url': url, 'image_id': im.get('id'),
                          'step_id': step['stepid'], 'step_order': step['orderby']})
        if group:
            groups.append(group)
    # Prefer coverage across the procedure over the first gallery images.
    first = [g[0] for g in groups]
    if len(first) > limit:
        return [first[round(i * (len(first) - 1) / (limit - 1))] for i in range(limit)]
    return (first + [im for g in groups for im in g[1:]])[:limit]


def collect(root):
    root.mkdir(parents=True, exist_ok=False)
    (root / 'raw').mkdir()
    rows, targets = [], []
    client = Fetcher(hosts={'www.ifixit.com'})
    try:
        _, status, _, body = client.get('https://www.ifixit.com/robots.txt')
        (root / 'raw/robots.txt').write_bytes(body)
        if status != 200:
            raise ValueError('robots_unverified')
        rules = RobotFileParser()
        rules.parse(body.decode(errors='replace').splitlines())
        for category, guide_id in TARGETS:
            url = f'https://www.ifixit.com/api/2.0/guides/{guide_id}'
            row = dict(category=category, guide_id=guide_id, api_url=url,
                       status='failed', quality_accepted=False,
                       knowledge_base_imported=False, usage_approved=False,
                       license='CC-BY-NC-SA-3.0', license_url=LICENSE,
                       usage_status='project_noncommercial_status_unconfirmed',
                       record_type='repair_guide_not_work_order')
            try:
                final, status, _, body = client.get(url, permit=lambda u: rules.can_fetch(USER_AGENT, u))
                if status != 200:
                    raise ValueError(f'http_{status}')
                raw = root / 'raw' / f'{guide_id}.json'
                raw.write_bytes(body)
                data = json.loads(body)
                row.update(status='success', source_url=data['url'], title=data['title'],
                           author=data.get('author'), revision_id=data.get('revisionid'),
                           source_sha256=digest(body), raw_path=raw.relative_to(root).as_posix(),
                           retrieved_at=datetime.now(timezone.utc).isoformat(),
                           summary=data.get('summary'), introduction=data.get('introduction_raw'),
                           difficulty=data.get('difficulty'), tools=data.get('tools'),
                           steps=[{'step_id': s['stepid'], 'order': s['orderby'],
                                   'title': s.get('title'), 'lines': s.get('lines', [])}
                                  for s in data.get('steps', [])],
                           safety_review='pending_model_and_Australian_context_review')
                for i, im in enumerate(select_images(data.get('steps', []))):
                    targets.append(dict(im, id=f'{guide_id}-{i}', guide_id=guide_id,
                                        category=category, kind='image', role='procedure_image_candidate',
                                        source_url=data['url'], source_sha256=digest(body)))
            except Exception as exc:
                row['error'] = str(exc)
            rows.append(row)
            write_json(root / 'records.json', rows)
            print(category, row['status'], row.get('error', ''), flush=True)
    finally:
        client.close()
    write_json(root / 'media_targets.json', targets)
    for offset in range(0, len(targets), 20):
        folder = root / 'media' / f'{offset:03d}'
        run(targets[offset:offset + 20], folder)
        outcomes = json.loads((folder / 'outcomes.json').read_text(encoding='utf-8'))
        if any('host_forbidden' in r.get('error', '') or 'host_rate_limited' in r.get('error', '') for r in outcomes):
            break
    export(root, rows)


def export(root, rows):
    assets = []
    for path in sorted((root / 'media').glob('*/outcomes.json')):
        for a in json.loads(path.read_text(encoding='utf-8')):
            if a['status'] == 'success':
                a['local_path'] = (path.parent / a['local_path']).relative_to(root).as_posix()
            assets.append(a)
    attempted = {a['id'] for a in assets}
    for target in json.loads((root / 'media_targets.json').read_text(encoding='utf-8')):
        if target['id'] not in attempted:
            assets.append(dict(target, status='not_attempted', error='collection_stopped_after_media_host_denial'))
    write_json(root / 'media_audit.json', assets)
    summary, html, md = [], [], ['# Repair image review', '', 'Not work orders. Usage and visual review pending.', '']
    for row in rows:
        selected = [a for a in assets if a['guide_id'] == row['guide_id'] and a['status'] == 'success']
        count = len({a['sha256'] for a in selected})
        summary.append({'category': row['category'], 'images': len(selected), 'unique_hashes': count,
                        'minimum_five_files_met': count >= 5, 'visual_accepted': False})
        row['assets'] = selected
        row['media_failures'] = [a for a in assets if a['guide_id'] == row['guide_id'] and a['status'] != 'success']
        title = row.get('title', row['category'])
        attribution = f"iFixit | {row.get('author', {}).get('text', 'See source author')} | CC BY-NC-SA 3.0"
        html.append(f'<h2>{escape(title)}</h2><p>{escape(attribution)} | <a href="{escape(row.get("source_url", row["api_url"]))}">Source</a> | <a href="{LICENSE}">License</a></p><div class="gallery">')
        md += [f'## {title}', attribution, f'[Source]({row.get("source_url", row["api_url"])}) | [License]({LICENSE})', '']
        if not selected:
            html.append('<p>No local images: media collection blocked. See source for original guide.</p>')
            md += ['No local images: media collection blocked. See source for original guide.', '']
        html.append(f'<p>{escape(row.get("summary") or "")}</p>')
        md += [row.get('summary') or '', '']
        for a in selected:
            label = f"Step {a['step_order']} - procedure image, not verified defect evidence"
            html.append(f'<figure><img src="{escape(a["local_path"])}" alt="{escape(label)}"><figcaption>{escape(label)}</figcaption></figure>')
            md += [f'![{label}](<{(root / a["local_path"]).resolve().as_posix()}>)', '']
        html.append('</div>')
        html.append('<details><summary>Collected guide steps (source text)</summary>')
        for step in row.get('steps', []):
            html.append(f'<h3>Step {step["order"]}</h3>')
            for line in step['lines']:
                html.append(f'<p>{escape(line.get("text_raw", ""))}</p>')
        html.append('</details>')
    write_json(root / 'clean.json', rows)
    write_json(root / 'summary.json', summary)
    write_json(root / 'source_holds.json', [{'source': 'AHCD', 'url': 'https://www.australiancentreforhousingresearch.org/ahcdgallery', 'status': 'metadata_only_permission_pending', 'downloaded_images': 0}])
    (root / 'preview.md').write_text('\n'.join(md), encoding='utf-8')
    (root / 'index.html').write_text('<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Repair review</title><style>body{font:16px sans-serif;margin:24px;overflow-wrap:anywhere}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:16px}figure{margin:0}img{width:100%;height:240px;object-fit:contain}</style><h1>Repair image review</h1><p>Review only. Not actual work orders. Usage unconfirmed. Procedure images are not necessarily defect photos. Original source JSON retained; image selection and category labels added locally.</p>' + ''.join(html) + '</html>', encoding='utf-8')
    write_json(root / 'manifest.json', {p.relative_to(root).as_posix(): digest(p.read_bytes()) for p in root.rglob('*') if p.is_file() and p.name != 'manifest.json'})
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    collect(args.output)
